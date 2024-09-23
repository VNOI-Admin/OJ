from django.core.management.base import BaseCommand

from judge.bridge.daemon import judge_daemon


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--monitor', action='store_true', default=False,
                            help='if specified, run a monitor to automatically update problems')
        parser.add_argument('--problem-storage-globs', nargs='*', default=[],
                            help='globs to monitor for problem updates')

    def handle(self, *args, **options):
        judge_daemon(options['monitor'], options['problem_storage_globs'])
