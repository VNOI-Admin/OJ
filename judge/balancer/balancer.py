import hmac
import logging
import threading
from collections import deque
from functools import partial
from threading import RLock

from django.conf import settings

from judge.balancer.bridge_handler import BridgeHandler
from judge.balancer.judge_handler import JudgeHandler
from judge.bridge.server import Server


logger = logging.getLogger('judge.balancer')


class JudgeBalancer:
    def __init__(self, config):
        self.executors = {}
        self.config = config
        self.judges = set()
        self.queue = deque()
        self.lock = RLock()
        self.judge_to_bridge = {}
        self.bridge_to_judge = {}

        self.judge_server = Server(
            settings.BALANCER_JUDGE_ADDRESS,
            partial(JudgeHandler, balancer=self),
        )

        self.bridges = []
        for bridge in config['bridges']:
            bridge_id = len(self.bridges)
            self.bridges.append(BridgeHandler(balancer=self, bridge_id=bridge_id, **bridge))

    def run(self):
        threading.Thread(target=self.judge_server.serve_forever).start()
        for bridge in self.bridges:
            bridge.listen()

    def shutdown(self):
        self.judge_server.shutdown()
        for bridge in self.bridges:
            bridge.shutdown()

    def get_paired_bridge(self, judge_name):
        return self.judge_to_bridge.get(judge_name)

    def reset_bridge(self, bridge_id):
        with self.lock:
            if bridge_id in self.bridge_to_judge:
                judge = self.bridge_to_judge[bridge_id]
                del self.judge_to_bridge[judge.name]
                del self.bridge_to_judge[bridge_id]

    def _try_judge(self):
        with self.lock:
            available = [judge for judge in self.judges if not judge.working]
            while available and self.queue:
                judge = available.pop()
                bridge_id, packet = self.queue.popleft()
                self.judge_to_bridge[judge.name] = bridge_id
                self.bridge_to_judge[bridge_id] = judge

                packet['storage-namespace'] = self.config['bridges'][bridge_id].get('storage_namespace')
                judge.submit(packet)

    def free_judge(self, judge):
        with self.lock:
            bridge_id = self.judge_to_bridge[judge.name]
            del self.judge_to_bridge[judge.name]
            del self.bridge_to_judge[bridge_id]

        self._try_judge()

    def authenticate_judge(self, judge_id, key, client_address):
        judge_config = ([judge for judge in self.config['judges'] if judge['id'] == judge_id] or [None])[0]
        if judge_config is None:
            return False

        if not hmac.compare_digest(judge_config.get('key'), key):
            logger.warning('Judge authentication failure: %s', client_address)
            return False

        return True

    def register_judge(self, judge):
        with self.lock:
            # Disconnect all judges with the same name, see <https://github.com/DMOJ/online-judge/issues/828>
            self.disconnect(judge, force=True)
            self.judges.add(judge)
            self._try_judge()

    def disconnect(self, judge_id, force=False):
        with self.lock:
            for judge in self.judges:
                if judge.name == judge_id:
                    judge.disconnect(force=force)

    def remove_judge(self, judge):
        with self.lock:
            bridge_id = self.judge_to_bridge.get(judge.name)
            if bridge_id is not None:
                del self.judge_to_bridge[judge.name]
                del self.bridge_to_judge[bridge_id]
            self.judges.discard(judge)

    def set_runtime_versions(self, executors):
        self.executors = executors
        for bridge in self.bridges:
            bridge.executors_packet(executors)

    def get_runtime_versions(self):
        return self.executors

    def queue_submission(self, bridge_id: int, packet: dict):
        with self.lock:
            self.queue.append((bridge_id, packet))
        self._try_judge()

    def abort_submission(self, bridge_id):
        try:
            judge = self.bridge_to_judge[bridge_id]
            judge.abort()
        except KeyError:
            pass

    def forward_packet_to_bridge(self, judge_name, packet: dict):
        try:
            bridge_id = self.judge_to_bridge[judge_name]
            self.bridges[bridge_id].send_packet(packet)
        except KeyError:
            pass
