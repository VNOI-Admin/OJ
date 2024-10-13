import yaml
from django.core.management.base import BaseCommand

from judge.bridge.daemon import judge_daemon


class Command(BaseCommand):
    def add_arguments(self, parser) -> None:
        parser.add_argument('-c', '--config', type=str, help='file to load bridged configurations from')

    def handle(self, *args, **options):
        if options['config']:
            with open(options['config'], 'r') as f:
                config = yaml.safe_load(f)
        else:
            config = {}
        judge_daemon(config)
