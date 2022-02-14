import os


from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from judge.models import Problem, ProblemTestCase
from judge.utils.problem_data import ProblemDataCompiler


def get_testcases(test_path):
    def get_input_output(test_type):
        inputs = []
        outputs = []
        test_type_path = os.path.join(test_path, test_type)

        for path, subdirs, files in os.walk(test_type_path):
            for name in files:
                relative_path = os.path.join(path, name)[len(test_path) + 1:]

                if not relative_path.startswith(test_type):
                    raise CommandError(f'Invalid relative path `{relative_path}`')

                if name.endswith('.in'):
                    inputs.append(relative_path)
                elif name.endswith('.ans'):
                    outputs.append(relative_path)

        if len(inputs) != len(outputs):
            raise CommandError(
                f'In {test_type}, found {len(inputs)} input files, which is differ from {len(outputs)} output files.',
            )

        if len(inputs) == 0:
            raise CommandError(f'Found nothing in {test_type} folder.')

        print(f'Found {len(inputs)} {test_type} testcases')

        inputs.sort()
        outputs.sort()
        return inputs, outputs

    sample_in, sample_out = get_input_output('sample')
    secret_in, secret_out = get_input_output('secret')

    return list(zip(sample_in + secret_in, sample_out + secret_out))


@transaction.atomic
def update_problem_testcases(problem, testcases, test_file_path):
    # delete old testcases
    problem.cases.all().delete()
    files = []
    for order, case_data in enumerate(testcases, start=1):
        case = ProblemTestCase(
            dataset=problem,
            order=order,
            input_file=case_data[0],
            output_file=case_data[1],
            points=1 if order == len(testcases) else 0,
            is_pretest=False,
        )
        files += case_data
        case.save()

    problem_data = problem.data_files
    problem_data.zipfile.name = test_file_path
    problem_data.save()

    print('Generating init.yml')
    ProblemDataCompiler.generate(
        problem=problem,
        data=problem_data,
        cases=problem.cases.order_by('order'),
        files=files,
    )


class Command(BaseCommand):
    help = 'update testcase from github'

    def add_arguments(self, parser):
        parser.add_argument('code', help='problem code')
        parser.add_argument('name', help='name of problem in the github repo')

    def handle(self, *args, **options):
        problem_code = options['code']
        problem_repo_name = options['name']
        problem = Problem.objects.filter(code=problem_code).first()
        if problem is None:
            raise CommandError(f'problem {problem_code} not found')

        try:
            problem.data_files
        except Exception:
            raise CommandError('Please create testcase via web UI before using this command.')

        icpc_folder = getattr(settings, 'ICPC_GITHUB_FOLDER', None)
        if icpc_folder is None:
            raise CommandError('You should declare `ICPC_GITHUB_FOLDER` in settings')

        if not os.path.exists(icpc_folder):
            raise CommandError(f'Folder {icpc_folder} not found. Make sure to clone the repo to that folder')

        os.system(f'cd {icpc_folder} && git pull origin master')

        problem_folder = os.path.join(icpc_folder, problem_repo_name)

        if not os.path.exists(problem_folder):
            raise CommandError(f'Folder {problem_folder} not found. Did you misspell the problem name?')

        test_path = os.path.join(problem_folder, 'data')

        if not os.path.exists(test_path):
            raise CommandError('Test data folder not found.')

        testcases = get_testcases(test_path)

        test_zip_name = 'data.zip'
        print('Creating zip file')
        os.system(f'cd {test_path} && zip -rq {test_zip_name} .')
        os.rename(
            os.path.join(test_path, test_zip_name),
            os.path.join(settings.DMOJ_PROBLEM_DATA_ROOT, problem_code, test_zip_name),
        )

        update_problem_testcases(problem, testcases, os.path.join(problem_code, test_zip_name))
