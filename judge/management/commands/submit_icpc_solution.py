import os
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from judge.models import Language, Problem, SubmissionSource, Submission
from judge.models.profile import Profile


def get_submissions(submissions_path):
    submissions = []

    for path, subdirs, files in os.walk(submissions_path):
        for name in files:
            relative_path = os.path.join(path, name)[len(submissions_path) + 1:]
            prefix = ''
            if name.lower().endswith('.cpp'):
                language = Language.objects.get(key='CPP17')
                prefix = '// '
            elif name.lower().endswith('.py'):
                language = Language.objects.get(key='PYPY3')
                prefix = '# '
            elif name.lower().endswith('.java'):
                language = Language.objects.get(key='JAVA17')
                prefix = '// '
            else:
                raise CommandError(f'Invalid file extension `{name}`')

            submission = prefix + relative_path + '\n' + open(os.path.join(path, name), 'r').read()
            submissions.append((submission, language))

    return submissions


def submit_submissions(problem_name, icpc_folder):
    problem_code = 'icpc_' + problem_name[0]
    problem_folder = os.path.join(icpc_folder, problem_name)
    submissions_path = os.path.join(problem_folder, 'submissions')

    if not os.path.exists(submissions_path):
        raise CommandError(f'Submissions folder `{submissions_path}` not found.')

    if Problem.objects.filter(code=problem_code).count() == 0:
        raise CommandError(f'Problem `{problem_code}` not found.')

    problem = Problem.objects.get(code=problem_code)

    submissions = get_submissions(submissions_path)
    for [code, lang] in submissions:
        submission = Submission()
        submission.problem = problem
        submission.language = lang
        submission.user = Profile.objects.get(user__username='admin')
        submission.save()
        source = SubmissionSource(submission=submission, source=code)
        source.save()
        submission.judge(force_judge=True)
        print(f'Submitted {submission.id}')


class Command(BaseCommand):
    help = 'create icpc problem from kattis repo'

    def handle(self, *args, **options):

        icpc_folder = getattr(settings, 'ICPC_GITHUB_FOLDER', None)
        if icpc_folder is None:
            raise CommandError('You should declare `ICPC_GITHUB_FOLDER` in settings')

        if not os.path.exists(icpc_folder):
            raise CommandError(f'Folder {icpc_folder} not found. Make sure to clone the repo to that folder')

        os.system(f'cd {icpc_folder} && git pull origin master')

        blacklist = ['template_package', '.github', '.git', 'xx-mien-nam', 'yy-mien-nam', '6-mien-trung', '_other_docs_']
        problems = [
            name for name in os.listdir(icpc_folder)
            if os.path.isdir(os.path.join(icpc_folder, name)) and
            name not in blacklist
        ]
        problems.sort()
        errors = {}
        for problem in problems:
            try:
                print('=============================')
                submit_submissions(problem, icpc_folder)
                print('Succeed.')
            except Exception as e:
                print(f'Cannot submit problem {problem}. Please check error message.')
                errors[problem] = str(e)
        if errors:
            print(json.dumps(errors, indent=4))
