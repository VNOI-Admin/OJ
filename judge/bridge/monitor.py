import glob
import logging
import os
import threading
import time
from pathlib import Path

from django import db

from judge.models import Problem

try:
    from watchdog.observers import Observer
    from watchdog.events import (
        FileSystemEventHandler,
        EVENT_TYPE_MOVED,
        EVENT_TYPE_DELETED,
        EVENT_TYPE_MODIFIED,
        EVENT_TYPE_CREATED,
    )

    has_watchdog_installed = True
except ImportError:
    has_watchdog_installed = False


logger = logging.getLogger('judge.monitor')


def _ensure_connection():
    db.connection.close_if_unusable_or_obsolete()


def find_glob_root(g: str) -> Path:
    """
    Given a glob, find a directory that contains all its possible patterns
    """
    root = Path(g)
    while str(root) != glob.escape(str(root)):
        root = root.parent
    return root


class SendProblemsHandler(FileSystemEventHandler):
    ALLOWED_EVENT_TYPES = (
        EVENT_TYPE_MOVED,
        EVENT_TYPE_DELETED,
        EVENT_TYPE_MODIFIED,
        EVENT_TYPE_CREATED,
    )

    def __init__(self, signal):
        self.signal = signal

    def on_any_event(self, event):
        if event.event_type not in self.ALLOWED_EVENT_TYPES:
            return
        self.signal.set()


class Monitor:
    def __init__(self, judges, problem_globs):
        if not has_watchdog_installed:
            raise ImportError('watchdog is not installed')

        self.judges = judges
        self.problem_globs = problem_globs

        self.updater_exit = False
        self.updater_signal = threading.Event()
        self.updater = threading.Thread(target=self.updater_thread)

        self._handler = SendProblemsHandler(self.updater_signal)
        self._observer = Observer()

        for root in set(map(find_glob_root, problem_globs)):
            self._observer.schedule(self._handler, root, recursive=True)
            logger.info('Scheduled for monitoring: %s', root)

    def update_supported_problems(self):
        problems = []
        for dir_glob in self.problem_globs:
            for problem_config in glob.iglob(os.path.join(dir_glob, 'init.yml'), recursive=True):
                if os.access(problem_config, os.R_OK):
                    problem_dir = os.path.dirname(problem_config)
                    problem = os.path.basename(problem_dir)
                    problems.append(problem)
        problems = set(problems)

        _ensure_connection()
        problem_ids = list(Problem.objects.filter(code__in=list(problems)).values_list('id', flat=True))
        self.judges.update_problems_all(problems, problem_ids)

    def updater_thread(self) -> None:
        while True:
            self.updater_signal.wait()
            self.updater_signal.clear()
            if self.updater_exit:
                return

            try:
                self.update_supported_problems()
                time.sleep(3)
            except Exception:
                logger.exception('Failed to update problems.')

    def start(self):
        self.updater.start()
        self.updater_signal.set()
        try:
            self._observer.start()
        except OSError:
            logger.exception('Failed to start problem monitor.')

    def stop(self):
        self._observer.stop()
        self._observer.join(1)
        self.updater_exit = True
        self.updater_signal.set()
