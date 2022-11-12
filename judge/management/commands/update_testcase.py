import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from judge.management.commands.create_icpc_problem import create_problem

class Command(BaseCommand):
    help = 'update testcase from github'

    def add_arguments(self, parser):
        parser.add_argument('name', help='name of problem in the github repo')

    def handle(self, *args, **options):
        problem_repo_name = options['name']

        icpc_folder = getattr(settings, 'ICPC_GITHUB_FOLDER', None)
        if icpc_folder is None:
            raise CommandError('You should declare `ICPC_GITHUB_FOLDER` in settings')

        if not os.path.exists(icpc_folder):
            raise CommandError(f'Folder {icpc_folder} not found. Make sure to clone the repo to that folder')
        os.system(f'cd {icpc_folder} && git pull origin master')
        create_problem(problem_repo_name, icpc_folder)
