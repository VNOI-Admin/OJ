import os

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from judge.models import Language, Problem, ProblemData, ProblemGroup, ProblemTestCase, ProblemType
from judge.models.profile import Profile
from judge.utils.problem_data import ProblemDataCompiler
from judge.views.widgets import pdf_statement_uploader


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
    with open(test_file_path, 'rb') as f:
        try:
            problem_data = problem.data_files
            problem_data.zipfile.save('data.zip', File(f))
        except Exception:
            problem_data = ProblemData(
                problem=problem,
                zipfile=File(f),
            )
        problem_data.output_limit = 100 * 1024 * 1024
        problem_data.save()

    print('Generating init.yml')
    ProblemDataCompiler.generate(
        problem=problem,
        data=problem_data,
        cases=problem.cases.order_by('order'),
        files=files,
    )


def create_problem(problem_name, icpc_folder):
    problem_code = 'icpc_' + problem_name[0]
    problem_folder = os.path.join(icpc_folder, problem_name)
    test_path = os.path.join(problem_folder, 'data')

    if not os.path.exists(test_path):
        raise CommandError(f'Test data folder `{test_path}` not found.')

    if Problem.objects.filter(code=problem_code).count() == 0:
        pdf_path = os.path.join(problem_folder, f'{problem_name}.pdf')

        print(f'Creating problem {problem_name}')
        with open(pdf_path, 'rb') as f:
            file_url = pdf_statement_uploader(f)
            problem = Problem(code=problem_code)
            problem.name = problem_name
            problem.pdf_url = file_url
            problem.time_limit = 1
            problem.memory_limit = 512 * 1024
            problem.partial = False
            problem.points = 1
            problem.group = ProblemGroup.objects.order_by('id').first()  # Uncategorized
            problem.date = timezone.now()
            problem.save()

            problem.allowed_languages.set(Language.objects.filter(include_in_problem=True))
            problem.types.set([ProblemType.objects.order_by('id').first()])  # Uncategorized
            problem.authors.set(Profile.objects.filter(user__username='admin'))
            problem.save()
    else:
        print(f'Skipped create problem {problem_name}.')
        problem = Problem.objects.get(code=problem_code)

    testcases = get_testcases(test_path)

    print('Creating zip file')
    test_zip_name = 'data.zip'
    os.system(f'cd {test_path} && zip -rq {test_zip_name} .')

    update_problem_testcases(problem, testcases, os.path.join(test_path, test_zip_name))


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
