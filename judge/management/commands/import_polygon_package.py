import os
import tempfile
import zipfile

from django.core.management.base import BaseCommand, CommandError
from django.utils import translation
from lxml import etree as ET

from judge.models import Problem


def parse_checker(problem_meta, root, package):
    checker = root.find('.//checker')
    if checker is None:
        raise CommandError('checker not found')

    if checker.get('type') != 'testlib':
        raise CommandError('not a testlib checker. how possible?')

    checker_name = checker.get('name')
    if checker_name is None:
        problem_meta['checker'] = 'bridged'
    else:
        if checker_name in ['std::hcmp.cpp', 'std::ncmp.cpp', 'std::wcmp.cpp']:
            problem_meta['checker'] = 'standard'
        elif checker_name in ['std::rcmp4.cpp', 'std::rcmp6.cpp', 'std::rcmp9.cpp']:
            problem_meta['checker'] = 'floats'
            problem_meta['checker_args'] = {'precision': int(checker_name[9])}
        elif checker_name == 'std::fcmp.cpp':
            problem_meta['checker'] = 'identical'
        elif checker_name == 'std::lcmp.cpp':
            problem_meta['checker'] = 'linecount'
        else:
            problem_meta['checker'] = 'bridged'

    if problem_meta['checker'] == 'bridged':
        source = checker.find('source')
        if source is not None:
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

        with open(os.path.join(problem_meta['tmp_dir'].name, 'checker.cpp'), 'w') as f:
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
    problem_meta['cases'] = []

    tests_zip = zipfile.ZipFile(os.path.join(problem_meta['tmp_dir'].name, 'tests.zip'), 'w')
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

    if total_points:
        print('Total points of all testcases is zero. Set point of last testcase to 1.')
        problem_meta['cases'][-1]['points'] = 1


def parse_statements(problem_meta, root, package):
    pass


def create_problem(problem_meta):
    pass


class Command(BaseCommand):
    help = 'import Codeforces Polygon package'

    def add_arguments(self, parser):
        parser.add_argument('package', help='path to package in zip file format')
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
            print(problem_meta)
            problem_meta['tmp_dir'].cleanup()
