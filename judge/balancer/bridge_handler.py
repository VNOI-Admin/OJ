import errno
import json
import logging
import socket
import ssl
import struct
import threading
import time
import zlib
from typing import Optional

from judge.balancer import sysinfo


log = logging.getLogger(__name__)


class JudgeAuthenticationFailed(Exception):
    pass


class BridgeHandler:
    SIZE_PACK = struct.Struct('!I')

    ssl_context: Optional[ssl.SSLContext]

    def __init__(
        self,
        host: str,
        port: int,
        id: str,
        key: str,
        balancer,
        bridge_id: int,
        secure: bool = False,
        no_cert_check: bool = False,
        cert_store: Optional[str] = None,
        **kwargs,
    ):
        self.host = host
        self.port = port
        self.balancer = balancer
        self.name = id
        self.key = key
        self.bridge_id = bridge_id
        self._closed = False

        log.info('Preparing to connect to [%s]:%s as: %s', host, port, id)
        if secure:
            self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
            self.ssl_context.options |= ssl.OP_NO_SSLv2
            self.ssl_context.options |= ssl.OP_NO_SSLv3

            if not no_cert_check:
                self.ssl_context.verify_mode = ssl.CERT_REQUIRED
                self.ssl_context.check_hostname = True

            if cert_store is None:
                self.ssl_context.load_default_certs()
            else:
                self.ssl_context.load_verify_locations(cafile=cert_store)
            log.info('Configured to use TLS.')
        else:
            self.ssl_context = None
            log.info('TLS not enabled.')

        self.secure = secure
        self.no_cert_check = no_cert_check
        self.cert_store = cert_store

        self._lock = threading.RLock()
        self.shutdown_requested = False

        # Exponential backoff: starting at 4 seconds, max 60 seconds.
        # If it fails to connect for something like 7 hours, it could RecursionError.
        self.fallback = 4

        self.conn = None
        self._do_reconnect()

    def _connect(self):
        problems = []  # should be handled by bridged's monitor
        versions = self.balancer.get_runtime_versions()

        log.info('Opening connection to: [%s]:%s', self.host, self.port)

        while True:
            try:
                self.conn = socket.create_connection((self.host, self.port), timeout=5)
            except OSError as e:
                if e.errno != errno.EINTR:
                    raise
            else:
                break

        self.conn.settimeout(300)
        self.conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        if self.ssl_context:
            log.info('Starting TLS on: [%s]:%s', self.host, self.port)
            self.conn = self.ssl_context.wrap_socket(self.conn, server_hostname=self.host)

        log.info('Starting handshake with: [%s]:%s', self.host, self.port)
        self.input = self.conn.makefile('rb')
        self.handshake(problems, versions, self.name, self.key)
        log.info('Judge "%s" online: [%s]:%s', self.name, self.host, self.port)

    def _reconnect(self):
        if self.shutdown_requested:
            log.info('Shutdown requested, not reconnecting.')
            return

        log.warning('Attempting reconnection in %.0fs: [%s]:%s', self.fallback, self.host, self.port)

        if self.conn is not None:
            log.info('Dropping old connection.')
            self.conn.close()
        time.sleep(self.fallback)
        self.fallback = min(self.fallback * 1.5, 60)  # Limit fallback to one minute.
        self._do_reconnect()

    def _do_reconnect(self):
        try:
            self._connect()
        except JudgeAuthenticationFailed:
            log.error('Authentication as "%s" failed on: [%s]:%s', self.name, self.host, self.port)
            self._reconnect()
        except socket.error:
            log.exception('Connection failed due to socket error: [%s]:%s', self.host, self.port)
            self._reconnect()

    def _read_forever(self):
        try:
            while True:
                packet = self._read_single()
                if packet is None:
                    break
                self._receive_packet(packet)
        except Exception:
            self.balancer.abort_submission(self.bridge_id)
            self.balancer.reset_bridge(self.bridge_id)
            self._reconnect()

    def _read_single(self) -> Optional[dict]:
        if self.shutdown_requested:
            return None

        try:
            data = self.input.read(BridgeHandler.SIZE_PACK.size)
        except socket.error:
            self._reconnect()
            return self._read_single()
        if not data:
            self._reconnect()
            return self._read_single()
        size = BridgeHandler.SIZE_PACK.unpack(data)[0]
        try:
            packet = zlib.decompress(self.input.read(size))
        except zlib.error:
            self._reconnect()
            return self._read_single()
        else:
            return json.loads(packet.decode('utf-8', 'strict'))

    def listen(self):
        threading.Thread(target=self._read_forever).start()

    def shutdown(self):
        self.shutdown_requested = True
        self._close()

    def _close(self):
        if self.conn and not self._closed:
            try:
                # May already be closed despite self._closed == False if a network error occurred and `close` is being
                # called as part of cleanup.
                self.conn.shutdown(socket.SHUT_RDWR)
            except socket.error:
                pass
        self._closed = True

    def __del__(self):
        self.shutdown()

    def send_packet(self, packet: dict):
        for k, v in packet.items():
            if isinstance(v, bytes):
                # Make sure we don't have any garbage utf-8 from e.g. weird compilers
                # *cough* fpc *cough* that could cause this routine to crash
                # We cannot use utf8text because it may not be text.
                packet[k] = v.decode('utf-8', 'replace')

        raw = zlib.compress(json.dumps(packet).encode('utf-8'))
        with self._lock:
            try:
                assert self.conn is not None
                self.conn.sendall(BridgeHandler.SIZE_PACK.pack(len(raw)) + raw)
            except Exception:  # connection reset by peer
                self.balancer.abort_submission(self.bridge_id)
                self.balancer.reset_bridge(self.bridge_id)
                self._reconnect()

    def _receive_packet(self, packet: dict):
        name = packet['name']
        if name == 'ping':
            self.ping_packet(packet['when'])
        elif name == 'submission-request':
            self.submission_acknowledged_packet(packet['submission-id'])
            self.balancer.queue_submission(self.bridge_id, packet)
        elif name == 'terminate-submission':
            self.balancer.abort_submission(self.bridge_id)
        elif name == 'disconnect':
            self.balancer.abort_submission(self.bridge_id)
            self._close()
        else:
            log.error('Unknown packet %s, payload %s', name, packet)

    def handshake(self, problems: str, runtimes, id: str, key: str):
        self.send_packet({'name': 'handshake', 'problems': problems, 'executors': runtimes, 'id': id, 'key': key})
        log.info('Awaiting handshake response: [%s]:%s', self.host, self.port)
        try:
            data = self.input.read(BridgeHandler.SIZE_PACK.size)
            size = BridgeHandler.SIZE_PACK.unpack(data)[0]
            packet = zlib.decompress(self.input.read(size)).decode('utf-8', 'strict')
            resp = json.loads(packet)
        except Exception:
            log.exception('Cannot understand handshake response: [%s]:%s', self.host, self.port)
            raise JudgeAuthenticationFailed()
        else:
            if resp['name'] != 'handshake-success':
                log.error('Handshake failed.')
                raise JudgeAuthenticationFailed()

    def ping_packet(self, when: float):
        data = {'name': 'ping-response', 'when': when, 'time': time.time()}
        for fn in sysinfo.report_callbacks:
            key, value = fn()
            data[key] = value
        self.send_packet(data)

    def submission_acknowledged_packet(self, sub_id: int):
        self.send_packet({'name': 'submission-acknowledged', 'submission-id': sub_id})

    def executors_packet(self, executors):
        self.send_packet({'name': 'executors', 'executors': executors})
