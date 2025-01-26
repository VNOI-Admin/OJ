import yaml
from django.core.management.base import BaseCommand

from judge.balancer.daemon import balancer_daemon


class Command(BaseCommand):
    def add_arguments(self, parser) -> None:
        parser.add_argument('-c', '--config', type=str, help='file to load balancer configurations from')

    def handle(self, *args, **options):
        with open(options['config'], 'r') as f:
            config = yaml.safe_load(f)
        balancer_daemon(config)
