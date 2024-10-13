import glob
import logging
import os
import threading
import time
from contextlib import closing
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.request import urlopen

from django import db
from django.db.models import Q

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


class JudgeControlRequestHandler(BaseHTTPRequestHandler):
    signal = None

    def update_problems(self):
        if self.signal is not None:
            self.signal.set()

    def do_POST(self):
        if self.path == '/update/problems':
            logger.info('Problem update requested')
            self.update_problems()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'As you wish.')
            return
        self.send_error(404)

    def do_GET(self):
        self.send_error(404)


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
    def __init__(self, judges, **config):
        if not has_watchdog_installed:
            raise ImportError('watchdog is not installed')

        self.judges = judges
        self.problem_globs = [(entry['storage_namespaces'], entry['problem_storage_globs'])
                              for entry in config['run_monitor']]

        self.updater_exit = False
        self.updater_signal = threading.Event()
        self.propagation_signal = threading.Event()
        self.updater = threading.Thread(target=self.updater_thread)
        self.propagator = threading.Thread(target=self.propagate_update_signal)

        self.update_pings = config.get('update_pings') or []

        api_listen = config.get('api_listen')
        if api_listen:
            api_listen = (api_listen['host'], api_listen['port'])

            class Handler(JudgeControlRequestHandler):
                signal = self.updater_signal

            api_server = HTTPServer(api_listen, Handler)
            self.api_server_thread = threading.Thread(target=api_server.serve_forever)

        self._handler = SendProblemsHandler(self.updater_signal)
        self._observer = Observer()

        for _, dir_glob in self.problem_globs:
            root = find_glob_root(dir_glob)
            self._observer.schedule(self._handler, root, recursive=True)
            logger.info('Scheduled for monitoring: %s', root)

    def update_supported_problems(self):
        problems = []
        for storage_namespace, dir_glob in self.problem_globs:
            for problem_config in glob.iglob(os.path.join(dir_glob, 'init.yml'), recursive=True):
                if os.access(problem_config, os.R_OK):
                    problem_dir = os.path.dirname(problem_config)
                    problem = os.path.basename(problem_dir)
                    if storage_namespace:
                        problems.append(storage_namespace + '/' + problem)
                    else:
                        problems.append(problem)
        problems = set(problems)

        _ensure_connection()
        problem_ids = list(Problem.objects.filter(Q(code__in=list(problems)) | Q(judge_code__in=list(problems)))
                           .values_list('id', flat=True))
        self.judges.update_problems_all(problems, problem_ids)

    def propagate_update_signal(self):
        while True:
            self.propagation_signal.wait()
            self.propagation_signal.clear()
            if self.updater_exit:
                return

            for url in self.update_pings:
                logger.info('Pinging for problem update: %s', url)
                try:
                    with closing(urlopen(url, data='')) as f:
                        f.read()
                except Exception:
                    logger.exception('Failed to ping for problem update: %s', url)

    def updater_thread(self) -> None:
        while True:
            self.updater_signal.wait()
            self.updater_signal.clear()
            self.propagation_signal.set()
            if self.updater_exit:
                return

            try:
                self.update_supported_problems()
                time.sleep(3)
            except Exception:
                logger.exception('Failed to update problems.')

    def start(self):
        self.updater.start()
        self.propagator.start()
        self.updater_signal.set()
        try:
            if hasattr(self, 'api_server_thread'):
                self.api_server_thread.start()
            self._observer.start()
        except OSError:
            logger.exception('Failed to start problem monitor.')

    def stop(self):
        self._observer.stop()
        self._observer.join(1)
        self.updater_exit = True
        self.updater_signal.set()
