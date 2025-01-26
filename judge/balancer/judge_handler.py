import json
import logging
import threading
import time

from django.conf import settings

from judge.bridge.base_handler import ZlibPacketHandler, proxy_list

logger = logging.getLogger('judge.balancer')


class JudgeHandler(ZlibPacketHandler):
    proxies = proxy_list(settings.BRIDGED_JUDGE_PROXIES or [])

    def __init__(self, request, client_address, server, balancer):
        super().__init__(request, client_address, server)

        self.balancer = balancer
        self.handlers = {
            'grading-begin': self.forward_packet,
            'grading-end': self.forward_packet_and_free_self,
            'compile-error': self.forward_packet_and_free_self,
            'compile-message': self.forward_packet,
            'batch-begin': self.forward_packet,
            'batch-end': self.forward_packet,
            'test-case-status': self.forward_packet,
            'internal-error': self.forward_packet_and_free_self,
            'submission-terminated': self.forward_packet_and_free_self,
            'submission-acknowledged': self.on_submission_acknowledged,
            'ping-response': self.ignore_packet,
            'supported-problems': self.ignore_packet,
            'handshake': self.on_handshake,
        }
        self.current_submission_id = None
        self._no_response_job = None
        self.name = None
        self._stop_ping = threading.Event()

    def on_connect(self):
        self.timeout = 15
        logger.info('Judge connected from: %s', self.client_address)

    def on_disconnect(self):
        self._stop_ping.set()
        if self.current_submission_id:
            self.internal_error_packet('Judge disconnected while handling submission')
            bridge_id = self.balancer.get_paired_bridge(self.name)
            self.balancer.reset_bridge(bridge_id)
            logger.error('Judge %s disconnected while handling submission %s', self.name, self.current_submission_id)

        self.balancer.remove_judge(self)
        logger.info('Judge disconnected from: %s with name %s', self.client_address, self.name)

    def send(self, data):
        super().send(json.dumps(data, separators=(',', ':')))

    def on_handshake(self, packet):
        if 'id' not in packet or 'key' not in packet:
            logger.warning('Malformed handshake: %s', self.client_address)
            self.close()
            return

        if not self.balancer.authenticate_judge(packet['id'], packet['key'], self.client_address):
            self.close()
            return

        self.timeout = 60
        self.name = packet['id']

        self.send({'name': 'handshake-success'})
        logger.info('Judge authenticated: %s (%s)', self.client_address, packet['id'])
        self.balancer.set_runtime_versions(packet['executors'])
        self.balancer.register_judge(self)
        threading.Thread(target=self._ping_thread).start()

    @property
    def working(self):
        return bool(self.current_submission_id)

    def disconnect(self, force=False):
        if force:
            # Yank the power out.
            self.close()
        else:
            self.send({'name': 'disconnect'})

    def submit(self, packet):
        self.current_submission_id = packet['submission-id']
        self._no_response_job = threading.Timer(20, self._kill_if_no_response)
        self.send(packet)

    def _kill_if_no_response(self):
        logger.error('Judge failed to acknowledge submission: %s: %s', self.name, self.current_submission_id)
        self.close()

    def on_timeout(self):
        if self.name:
            logger.warning('Judge seems dead: %s: %s', self.name, self.current_submission_id)

    def on_submission_acknowledged(self, packet):
        self.balancer.forward_packet_to_bridge(self.name, packet)
        if not packet.get('submission-id', None) == self.current_submission_id:
            logger.error('Wrong acknowledgement: %s: %s, expected: %s', self.name, packet.get('submission-id', None),
                         self.current_submission_id)
            self.close()
        logger.info('Submission acknowledged: %d', self.current_submission_id)
        if self._no_response_job:
            self._no_response_job.cancel()
            self._no_response_job = None

    def abort(self):
        self.send({'name': 'terminate-submission'})

    def ping(self):
        self.send({'name': 'ping', 'when': time.time()})

    def on_packet(self, data):
        try:
            try:
                data = json.loads(data)
                if 'name' not in data:
                    raise ValueError
            except ValueError:
                self.on_malformed(data)
            else:
                handler = self.handlers.get(data['name'], self.on_malformed)
                handler(data)
        except Exception:
            logger.exception('Error in packet handling (Judge-side): %s', self.name)

    def on_malformed(self, packet):
        logger.error('%s: Malformed packet: %s', self.name, packet)

    def forward_packet(self, packet):
        self.balancer.forward_packet_to_bridge(self.name, packet)

    def forward_packet_and_free_self(self, packet):
        self.balancer.forward_packet_to_bridge(self.name, packet)
        self.current_submission_id = None
        self.balancer.free_judge(self)

    def ignore_packet(self, packet):
        pass

    def internal_error_packet(self, message: str):
        self.forward_packet({'name': 'internal-error', 'submission-id': self.current_submission_id, 'message': message})

    def _ping_thread(self):
        try:
            while True:
                self.ping()
                if self._stop_ping.wait(10):
                    break
        except Exception:
            logger.exception('Ping error in %s', self.name)
            self.close()
            raise
