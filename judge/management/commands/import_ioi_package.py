import json
import os
import shutil
import tempfile
import zipfile

import yaml
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.urls import reverse
from django.utils import translation

from judge.models import Language, Problem, ProblemGroup, ProblemType, Profile


def parse_assets_and_tests(problem_meta, root, package):
    init = {}
    init['archive'] = 'tests.zip'

    # Parse checker
    checker_files = [file for file in package.namelist() if not file.endswith('/') and
                     file.startswith(problem_meta['zip_prefix'] + 'checker/')]
    if len(checker_files) > 0:
        files = []
        for file in checker_files:
            basename = os.path.basename(file)
            files.append(basename)
            with open(os.path.join(problem_meta['tmp_dir'].name, basename), 'wb') as f:
                f.write(package.read(file))

        init['checker'] = {
            'name': 'bridged',
            'args': {
                'lang': 'CPP17',
                'type': 'cms',
                'files': files,
            },
        }

    # Parse grader
    grader_files = [file for file in package.namelist() if not file.endswith('/') and
                    file.startswith(problem_meta['zip_prefix'] + 'graders/')]
    for file in grader_files:
        basename = os.path.basename(file)
        with open(os.path.join(problem_meta['tmp_dir'].name, basename), 'wb') as f:
            f.write(package.read(file))

    if root['task_type'] == 'Batch':
        assert len(grader_files) == 2
        assert problem_meta['zip_prefix'] + 'graders/grader.cpp' in grader_files

        header = [file for file in grader_files if file.endswith('.h') and not file.endswith('testlib.h')]
        assert len(header) == 1
        header = os.path.basename(header[0])

        init['signature_grader'] = {
            'entry': 'grader.cpp',
            'header': header,
        }
    elif root['task_type'] == 'Communication':
        assert problem_meta['zip_prefix'] + 'graders/manager.cpp' in grader_files
        assert problem_meta['zip_prefix'] + 'graders/stub.cpp' in grader_files

        header = [file for file in grader_files if file.endswith('.h') and not file.endswith('testlib.h')]
        assert len(header) == 1
        header = os.path.basename(header[0])

        task_type_params = json.loads(root['task_type_params'])
        if 'task_type_parameters_Communication_num_processes' in task_type_params:
            num_processes = task_type_params['task_type_parameters_Communication_num_processes']
        else:
            num_processes = 1

        init['communication'] = {
            'type': 'cms',
            'manager': {
                'files': 'manager.cpp',
            },
            'signature': {
                'entry': 'stub.cpp',
                'header': header,
            },
            'num_processes': num_processes,
        }
    else:
        raise CommandError('unknown task type')

    # IOI specifies the time limit in seconds and memory limit in bytes,
    # while DMOJ uses seconds and kilobytes.
    problem_meta['time_limit'] = root['time_limit']
    problem_meta['memory_limit'] = root['memory_limit'] // 1024

    if hasattr(settings, 'DMOJ_PROBLEM_MIN_MEMORY_LIMIT'):
        problem_meta['memory_limit'] = max(problem_meta['memory_limit'], settings.DMOJ_PROBLEM_MIN_MEMORY_LIMIT)
    if hasattr(settings, 'DMOJ_PROBLEM_MAX_MEMORY_LIMIT'):
        problem_meta['memory_limit'] = min(problem_meta['memory_limit'], settings.DMOJ_PROBLEM_MAX_MEMORY_LIMIT)

    problem_meta['zipfile'] = os.path.join(problem_meta['tmp_dir'].name, 'tests.zip')

    test_files = [file for file in package.namelist() if not file.endswith('/') and
                  file.startswith(problem_meta['zip_prefix'] + 'tests/')]
    test_files.sort()
    assert len(test_files) % 2 == 0
    with zipfile.ZipFile(problem_meta['zipfile'], 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as tests_zip:
        for file in test_files:
            basename = os.path.basename(file)
            tests_zip.writestr(basename, package.read(file))

    init['test_cases'] = []
    subtask_files = [file for file in package.namelist() if not file.endswith('/') and
                     file.startswith(problem_meta['zip_prefix'] + 'subtasks/')]
    subtask_files.sort()
    for file in subtask_files:
        data = json.loads(package.read(file))
        if data['score'] == 0:
            continue

        batch = {
            'points': data['score'],
            'batched': [],
        }
        for case in data['testcases']:
            batch['batched'].append({
                'in': case + '.in',
                'out': case + '.out',
            })

        init['test_cases'].append(batch)

    print(f'Found {len(test_files) // 2} tests!')
    print(f'Parsed as {len(init["test_cases"])} batches!')

    problem_meta['partial'] = True

    print('Generating init.yml')
    with open(os.path.join(problem_meta['tmp_dir'].name, 'init.yml'), 'w', encoding='utf8') as f:
        yaml.safe_dump(init, f, sort_keys=False)


@transaction.atomic
def create_problem(problem_meta):
    print('Creating problem in database')
    problem = Problem(
        code=problem_meta['code'],
        name=problem_meta['name'],
        time_limit=problem_meta['time_limit'],
        memory_limit=problem_meta['memory_limit'],
        description=problem_meta['description'],
        partial=problem_meta['partial'],
        group=ProblemGroup.objects.get(name='IOI'),
        points=0.0,
        is_manually_managed=True,
    )
    problem.save()
    problem.allowed_languages.set(Language.objects.filter(include_in_problem=True, key__startswith='CPP'))
    problem.authors.set(problem_meta['authors'])
    problem.curators.set(problem_meta['curators'])
    problem.types.set([ProblemType.objects.order_by('id').first()])  # Uncategorized
    problem.save()

    # Copy test data
    shutil.move(problem_meta['tmp_dir'].name, os.path.join(settings.DMOJ_PROBLEM_DATA_ROOT, problem.code))


class Command(BaseCommand):
    help = 'import IOI package'

    def add_arguments(self, parser):
        parser.add_argument('package', help='path to package in zip format')
        parser.add_argument('code', help='problem code')
        parser.add_argument('--authors', help='username of problem author', nargs='*')
        parser.add_argument('--curators', help='username of problem curator', nargs='*')

    def handle(self, *args, **options):
        # Force using English
        translation.activate('en')

        # Let's validate the problem code right now.
        # We don't want to have done everything and still fail because
        # of invalid problem code.
        problem_code = options['code']
        Problem._meta.get_field('code').run_validators(problem_code)
        if Problem.objects.filter(code=problem_code).exists():
            raise CommandError(f'problem with code {problem_code} already exists')

        package = zipfile.ZipFile(options['package'], 'r')
        zip_prefix = os.path.commonprefix(package.namelist())
        if zip_prefix + 'problem.json' not in package.namelist():
            raise CommandError('problem.json not found')

        root = json.loads(package.read(zip_prefix + 'problem.json'))

        problem_authors_args = options['authors'] or []
        problem_authors = []
        for username in problem_authors_args:
            try:
                profile = Profile.objects.get(user__username=username)
            except Profile.DoesNotExist:
                raise CommandError(f'user {username} does not exist')

            problem_authors.append(profile)

        problem_curators_args = options['curators'] or []
        problem_curators = []
        for username in problem_curators_args:
            try:
                profile = Profile.objects.get(user__username=username)
            except Profile.DoesNotExist:
                raise CommandError(f'user {username} does not exist')

            problem_curators.append(profile)

        # A dictionary to hold all problem information.
        problem_meta = {}
        problem_meta['zip_prefix'] = zip_prefix
        problem_meta['code'] = problem_code
        problem_meta['name'] = problem_code
        problem_meta['description'] = ''
        problem_meta['tmp_dir'] = tempfile.TemporaryDirectory()
        problem_meta['authors'] = problem_authors
        problem_meta['curators'] = problem_curators

        try:
            parse_assets_and_tests(problem_meta, root, package)
            create_problem(problem_meta)
        finally:
            problem_meta['tmp_dir'].cleanup()

        problem_url = 'https://' + Site.objects.first().domain + reverse('problem_detail', args=[problem_code])
        print(f'Imported successfully. View problem at {problem_url}')
