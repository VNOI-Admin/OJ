import logging
import signal
import threading
from functools import partial

from django.conf import settings

from judge.bridge.django_handler import DjangoHandler
from judge.bridge.judge_handler import JudgeHandler
from judge.bridge.judge_list import JudgeList
from judge.bridge.server import Server
from judge.models import Judge, Submission

logger = logging.getLogger('judge.bridge')


def reset_judges():
    Judge.objects.update(online=False, ping=None, load=None)


def judge_daemon(run_monitor=False, problem_storage_globs=None):
    reset_judges()
    Submission.objects.filter(status__in=Submission.IN_PROGRESS_GRADING_STATUS) \
        .update(status='IE', result='IE', error=None)
    judges = JudgeList()

    monitor = None
    if run_monitor:
        from judge.bridge.monitor import Monitor
        monitor = Monitor(judges, problem_storage_globs or [])

    judge_server = Server(
        settings.BRIDGED_JUDGE_ADDRESS,
        partial(JudgeHandler, judges=judges, ignore_problems_packet=run_monitor),
    )
    django_server = Server(settings.BRIDGED_DJANGO_ADDRESS, partial(DjangoHandler, judges=judges))

    if monitor is not None:
        monitor.start()
    threading.Thread(target=django_server.serve_forever).start()
    threading.Thread(target=judge_server.serve_forever).start()

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
        if monitor is not None:
            monitor.stop()
        django_server.shutdown()
        judge_server.shutdown()
