import json
import os
import tempfile
import zipfile

from django.contrib.sites.models import Site
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse
from django.utils import translation
from lxml import etree as ET

from judge.models import Problem, ProblemData, ProblemGroup, ProblemTestCase
from judge.utils.problem_data import ProblemDataCompiler


def parse_checker(problem_meta, root, package):
    checker = root.find('.//checker')
    if checker is None:
        raise CommandError('checker not found')

    if checker.get('type') != 'testlib':
        raise CommandError('not a testlib checker. how possible?')

    print('Use standard grader')
    problem_meta['grader'] = 'standard'

    checker_name = checker.get('name')
    if checker_name is None:
        problem_meta['checker'] = 'bridged'
    else:
        if checker_name in ['std::hcmp.cpp', 'std::ncmp.cpp', 'std::wcmp.cpp']:
            problem_meta['checker'] = 'standard'
            print('Use standard checker')
        elif checker_name in ['std::rcmp4.cpp', 'std::rcmp6.cpp', 'std::rcmp9.cpp']:
            problem_meta['checker'] = 'floats'
            problem_meta['checker_args'] = {'precision': int(checker_name[9])}
            print(f'Use floats checker with precision {problem_meta["checker_args"]["precision"]}')
        elif checker_name == 'std::fcmp.cpp':
            problem_meta['checker'] = 'identical'
            print('Use identical checker')
        elif checker_name == 'std::lcmp.cpp':
            problem_meta['checker'] = 'linecount'
            print('Use linecount checker')
        else:
            problem_meta['checker'] = 'bridged'

    if problem_meta['checker'] == 'bridged':
        print('Use custom checker')

        source = checker.find('source')
        if source is None:
            raise CommandError('checker source not found. how possible?')

        # TODO: support more checkers?
        path = source.get('path')
        if not path.lower().endswith('.cpp'):
            raise CommandError('checker must use C++')

        problem_meta['checker_args'] = {
            'files': 'checker.cpp',
            'lang': 'CPP17',
            'type': 'testlib',
        }

        problem_meta['custom_checker'] = os.path.join(problem_meta['tmp_dir'].name, 'checker.cpp')
        with open(problem_meta['custom_checker'], 'wb') as f:
            f.write(package.read(path))


def parse_tests(problem_meta, root, package):
    # TODO: support input/output via files?

    testset = root.find('.//testset[@name="tests"]')
    if testset is None:
        raise CommandError('testset tests not found')

    # Polygon specifies the time limit in ms and memory limit in bytes,
    # while DMOJ uses seconds and kilobytes.
    problem_meta['time_limit'] = float(testset.find('time-limit').text) / 1000
    problem_meta['memory_limit'] = int(testset.find('memory-limit').text) // 1024
    print(f'Time limit: {problem_meta["time_limit"]}s')
    print(f'Memory limit: {problem_meta["memory_limit"]}KB')

    problem_meta['cases'] = []
    problem_meta['zipfile'] = os.path.join(problem_meta['tmp_dir'].name, 'tests.zip')
    tests_zip = zipfile.ZipFile(problem_meta['zipfile'], 'w')

    input_path_pattern = testset.find('input-path-pattern').text
    answer_path_pattern = testset.find('answer-path-pattern').text
    total_points = 0

    for i, test in enumerate(testset.find('tests').getchildren(), start=1):
        input_path = input_path_pattern % i
        answer_path = answer_path_pattern % i
        points = int(float(test.get('points')))
        total_points += points

        tests_zip.writestr(f'{i:02d}.inp', package.read(input_path))
        tests_zip.writestr(f'{i:02d}.out', package.read(answer_path))
        problem_meta['cases'].append({
            'input_file': f'{i:02d}.inp',
            'output_file': f'{i:02d}.out',
            'points': points,
        })

    tests_zip.close()

    if len(problem_meta['cases']) == 0:
        raise CommandError('no testcases found')

    print(f'Found {len(problem_meta["cases"])} testcases!')

    if total_points == 0:
        print('Total points of all testcases is zero. Set points of last testcase to 1.')
        problem_meta['cases'][-1]['points'] = 1


def parse_statements(problem_meta, root, package):
    problem_meta['statement'] = ''


def create_problem(problem_meta):
    print('Creating problem in database')
    problem = Problem(
        code=problem_meta['code'],
        name=problem_meta['name'],
        time_limit=problem_meta['time_limit'],
        memory_limit=problem_meta['memory_limit'],
        description=problem_meta['statement'],
        group=ProblemGroup.objects.first(),
        points=0.0,
        partial=True,
    )
    problem.save()

    with open(problem_meta['zipfile'], 'rb') as f:
        problem_data = ProblemData(
            problem=problem,
            zipfile=File(open(problem_meta['zipfile'], 'rb')),
            grader=problem_meta['grader'],
            checker=problem_meta['checker'],
        )
        problem_data.save()

    if 'checker_args' in problem_meta:
        with open(problem_meta['custom_checker'], 'rb') as f:
            problem_data.custom_checker = File(f)
            problem_data.checker_args = json.dumps(problem_meta['checker_args'])
            problem_data.save()

    for order, case_data in enumerate(problem_meta['cases'], start=1):
        case = ProblemTestCase(
            dataset=problem,
            order=order,
            input_file=case_data['input_file'],
            output_file=case_data['output_file'],
            points=case_data['points'],
            is_pretest=False,
        )
        case.save()

    print('Generating init.yml')
    ProblemDataCompiler.generate(
        problem=problem, data=problem_data,
        cases=problem.cases.order_by('order'),
        files=zipfile.ZipFile(problem_data.zipfile.path).namelist()
    )


class Command(BaseCommand):
    help = 'import Codeforces Polygon package'

    def add_arguments(self, parser):
        parser.add_argument('package', help='path to package in zip format')
        parser.add_argument('code', help='problem code')

    def handle(self, *args, **options):
        # Force using English
        translation.activate('en')

        package = zipfile.ZipFile(options['package'], 'r')
        if 'problem.xml' not in package.namelist():
            raise CommandError('problem.xml not found')

        # Let's validate the problem code right now.
        # We don't want to have done everything and still fail because
        # of invalid problem code.
        problem_code = options['code']
        Problem._meta.get_field('code').run_validators(problem_code)
        if Problem.objects.filter(code=problem_code).exists():
            raise CommandError(f'problem with code {problem_code} already exists')

        root = ET.fromstring(package.read('problem.xml'))

        # A dictionary to hold all problem information.
        problem_meta = {}
        problem_meta['code'] = problem_code
        problem_meta['name'] = root.find('.//name').get('value')
        problem_meta['tmp_dir'] = tempfile.TemporaryDirectory()

        try:
            parse_checker(problem_meta, root, package)
            parse_tests(problem_meta, root, package)
            parse_statements(problem_meta, root, package)
            create_problem(problem_meta)
        except Exception:
            raise
        finally:
            problem_meta['tmp_dir'].cleanup()

        problem_url = 'https://' + Site.objects.first().domain + reverse('problem_detail', args=[problem_code])
        print(f'Imported successfully. View problem at {problem_url}')
