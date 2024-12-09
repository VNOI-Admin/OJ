import os
import json
import yaml
import io

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from judge.models import Language, Problem, ProblemData, ProblemGroup, ProblemTestCase, ProblemType
from judge.models.profile import Profile
from judge.utils.problem_data import ProblemDataCompiler
from judge.views.widgets import pdf_statement_uploader


NORMAL = 0
INTERACTIVE = 1
CHECKER = 2


def get_testcases(test_path):
    def get_input_output(test_type, required=True):
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

        if len(inputs) == 0 and required:
            raise CommandError(f'Found nothing in {test_type} folder.')

        print(f'Found {len(inputs)} {test_type} testcases')

        inputs.sort()
        outputs.sort()
        for input_file, output_file in zip(inputs, outputs):
            if input_file[:-3] != output_file[:-4]:
                raise CommandError(
                    f'found input file `{input_file}` and output file `{output_file}` which is not matched.',
                )
        return inputs, outputs

    sample_in, sample_out = get_input_output('sample', False)
    secret_in, secret_out = get_input_output('secret')

    return list(zip(sample_in + secret_in, sample_out + secret_out)), len(sample_in), len(secret_in)

def get_checker(validators_path):
    results = []
    for path, subdirs, files in os.walk(validators_path):
        for name in files:
            if name.endswith('.cpp'):
                results.append(os.path.join(path, name))
    if len(results) != 1:
        raise CommandError(f'Found {len(results)} validators, which is not 1.')

    return results[0]


@transaction.atomic
def update_problem_testcases(problem, testcases, test_file_path, checker_path, problem_type, float_checker):
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

    with open(test_file_path, 'rb') as f, open(checker_path, 'rb') as checker_raw:
        checker_source = checker_raw.read().replace(b'#include "testlib_for_kattis.h"', b'#include "testlib.h"')
        checker_source = checker_source.replace(b'#include "testlib_kattis.h"', b'#include "testlib.h"')
        checker_source = checker_source.replace(b'#include "./testlib_kattis.h"', b'#include "testlib.h"')
        checker = io.BytesIO(checker_source)

        try:
            problem_data = problem.data_files
            problem_data.zipfile.save('data.zip', File(f))

            if problem_type == CHECKER:
                problem_data.checker = 'bridged'
                problem_data.custom_checker.save('checker.cpp', File(checker))
                problem_data.checker_args = json.dumps({
                    "files": "checker.cpp",
                    "lang": "CPP20",
                    "type": "testlib"
                })
            elif problem_type == INTERACTIVE:
                problem_data.interactive = True
                problem_data.grader = 'interactive'
                problem_data.custom_grader.save('checker.cpp', File(checker))

            if float_checker is not None:
                problem_data.checker = float_checker[0]
                problem_data.checker_args = json.dumps({
                    "precision": float_checker[1],
                })
        except Exception:
            problem_data = ProblemData(
                problem=problem,
                zipfile=File(f),
            )

            if problem_type == CHECKER:
                problem_data.checker = 'bridged'
                problem_data.custom_checker.save('checker.cpp', File(checker))
                problem_data.checker_args = json.dumps({
                    "files": "checker.cpp",
                    "lang": "CPP20",
                    "type": "testlib"
                })
            elif problem_type == INTERACTIVE:
                problem_data.interactive = True
                problem_data.grader = 'interactive'
                problem_data.custom_grader.save('checker.cpp', File(checker))

        problem_data.output_limit = 100 * 1024 * 1024
        problem_data.save()

    print('Generating init.yml')
    ProblemDataCompiler.generate(
        problem=problem,
        data=problem_data,
        cases=problem.cases.order_by('order'),
        files=files,
    )


def get_problem_full_name(problem_folder):
    try:
        statement_path = os.path.join(problem_folder, 'problem_statement', 'problem.en.tex')
        with open(statement_path, 'r') as f:
            for line in f:
                if '\\problemname{' in line:
                    return line[line.index('{') + 1:line.index('}')].strip()
        return None
    except Exception:
        raise CommandError(f'Cannot find problem name in {statement_path}')


def create_problem(problem_name, icpc_folder):
    problem_code = 'icpc_' + problem_name[0]
    problem_folder = os.path.join(icpc_folder, problem_name)
    test_path = os.path.join(problem_folder, 'data')

    if not os.path.exists(test_path):
        raise CommandError(f'Test data folder `{test_path}` not found.')

    if Problem.objects.filter(code=problem_code).count() == 0:
        print(f'Creating problem {problem_name}')

        problem = Problem(code=problem_code)
        problem.name = get_problem_full_name(problem_folder) or problem_name
        problem.time_limit = 1
        problem.memory_limit = 512 * 1024
        problem.partial = False
        problem.points = 1
        problem.group = ProblemGroup.objects.order_by('id').first()  # Uncategorized
        problem.date = timezone.now()
        problem.testcase_result_visibility_mode = 'S'
        problem.save()

        problem.allowed_languages.set(Language.objects.filter(include_in_problem=True))
        problem.types.set([ProblemType.objects.order_by('id').first()])  # Uncategorized
        problem.authors.set(Profile.objects.filter(user__username='admin'))

        problem.save()
    else:
        print(f'Skipped create problem {problem_name}.')
        problem = Problem.objects.get(code=problem_code)
        problem.name = get_problem_full_name(problem_folder) or problem_name

    # pdf_path = os.path.join(problem_folder, f'{problem_name}.pdf')
    # with open(pdf_path, 'rb') as f:
    #     problem.pdf_url = pdf_statement_uploader(f)
    #     problem.save()

    testcases, n_sample, n_secret = get_testcases(test_path)

    print('Creating zip file')
    test_zip_name = 'data.zip'
    os.system(f'cd {test_path} && zip -rq {test_zip_name} .')

    problem_setting = yaml.load(open(os.path.join(problem_folder, 'problem.yaml'), 'r'), Loader=yaml.SafeLoader)

    validation = problem_setting.get('validation', '')
    if validation == 'custom interactive':
        problem_type = INTERACTIVE
        checker_path = get_checker(os.path.join(problem_folder, 'output_validators'))
    elif validation == 'custom':
        problem_type = CHECKER
        checker_path = get_checker(os.path.join(problem_folder, 'output_validators'))
    else:
        problem_type = NORMAL
        # small hack to make the `open with` work without any modification
        checker_path = os.path.join(problem_folder, 'problem.yaml')

    float_checker = None
    if problem_setting.get('validator_flags', None):
        flags = problem_setting['validator_flags'].split(' ')
        if len(flags) != 2:
            raise CommandError(f'Unsupported validator flags: {flags}')
        if flags[0] == 'float_tolerance':
            flags[0] = 'floats'
        elif flags[0] == 'float_relative_tolerance':
            flags[0] = 'floatsrel'
        elif flags[0] == 'float_absolute_tolerance':
            flags[0] = 'floatsabs'
        else:
            raise CommandError(f'Unsupported validator flags: {flags}')
        if not flags[1].startswith('1e-'):
            raise CommandError(f'Unsupported validator flags: {flags}')

        float_checker = (flags[0], int(flags[1][3:]))

    if float_checker and problem_type != NORMAL:
        raise CommandError('Float checker only support normal problem type')

    if problem_type != INTERACTIVE:
        print('Add sample testcases into problem')
        description = ''
        for test_id, testcase_data in enumerate(testcases[:n_sample], start=1):
            input_file, output_file = testcase_data
            with open(os.path.join(test_path, input_file), 'r') as fin, open(os.path.join(test_path, output_file), 'r') as fout:
                input_data = fin.read()
                output_data = fout.read()
                description += f'## Sample Input {test_id}\n```\n{input_data}```\n\n'
                description += f'## Sample Output {test_id}\n```\n{output_data}```\n\n'

        problem.description = description
        problem.save()

    update_problem_testcases(problem, testcases, os.path.join(test_path, test_zip_name), checker_path, problem_type, float_checker)
    return n_sample, n_secret, problem_type, float_checker


class Command(BaseCommand):
    help = 'create icpc problem from kattis repo'

    def handle(self, *args, **options):

        icpc_folder = getattr(settings, 'ICPC_GITHUB_FOLDER', None)
        if icpc_folder is None:
            raise CommandError('You should declare `ICPC_GITHUB_FOLDER` in settings')

        if not os.path.exists(icpc_folder):
            raise CommandError(f'Folder {icpc_folder} not found. Make sure to clone the repo to that folder')

        os.system(f'cd {icpc_folder} && git pull')

        blacklist = ['xx-mien-nam', 'yy-mien-nam', '6-mien-trung']
        problems = [
            name for name in os.listdir(icpc_folder)
            if os.path.isdir(os.path.join(icpc_folder, name)) and
            name not in blacklist and not name.startswith('_') and not name.startswith('.')
        ]
        problems.sort()
        messages = {}
        for problem in problems:
            try:
                print('=============================')
                n_sample, n_secret, problem_type, float_checker = create_problem(problem, icpc_folder)
                msg = ''
                if problem_type == CHECKER:
                    msg = ' [custom checker]'
                elif problem_type == INTERACTIVE:
                    msg = ' [interactive]'
                if float_checker is not None:
                    msg = f' [float checker {float_checker[0]}, precisions: {float_checker[1]}]'

                messages[problem] = f'{n_sample} samples, {n_secret} secrets{msg}.'
                print('Succeed.')
            except Exception as e:
                print(f'Cannot import problem {problem}. Please check error message.')
                messages[problem] = str(e)

        print(json.dumps(messages, indent=4))
