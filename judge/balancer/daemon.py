import logging
import signal
import threading

from judge.balancer.balancer import JudgeBalancer

logger = logging.getLogger('judge.balancer')


def balancer_daemon(config):
    balancer = JudgeBalancer(config)
    balancer.run()

    stop = threading.Event()

    def signal_handler(signum, _):
        logger.info('Exiting due to %s', signal.Signals(signum).name)
        stop.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGQUIT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        stop.wait()
    finally:
        balancer.shutdown()
