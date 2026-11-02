import os

from django.core.management.base import BaseCommand

from judge.management.commands.create_icpc_problem import create_problem
from judge.utils.icpc import get_icpc_folder


class Command(BaseCommand):
    help = 'update testcase from github'

    def add_arguments(self, parser):
        parser.add_argument('name', help='name of problem in the github repo')

    def handle(self, *args, **options):
        problem_repo_name = options['name']

        icpc_folder = get_icpc_folder()
        os.system(f'cd {icpc_folder} && git pull')
        print(create_problem(problem_repo_name, icpc_folder))
