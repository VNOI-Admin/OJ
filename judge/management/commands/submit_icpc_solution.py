import os
import json

from django.core.management.base import BaseCommand, CommandError

from judge.models import Language, Problem, SubmissionSource, Submission
from judge.models.profile import Profile
from judge.utils.icpc import get_icpc_folder, get_problem_code, list_icpc_problems

SUBMISSION_STATUS_MAP = {
    'accepted': 'admin_ac',
    'time_limit_exceeded': 'admin_tle',
    'wrong_answer': 'admin_wa',
}


def get_submissions(submissions_path):
    submissions = []
    whitelisted_subfolders = SUBMISSION_STATUS_MAP.keys()
    for subfolder in os.listdir(submissions_path):
        if subfolder not in whitelisted_subfolders:
            continue
        user_to_submit = SUBMISSION_STATUS_MAP[subfolder]
        for name in os.listdir(os.path.join(submissions_path, subfolder)):
            prefix = ''
            if name.lower().endswith('.cpp'):
                language = Language.objects.get(key='CPPICPC')
                prefix = '// '
            elif name.lower().endswith('.py'):
                language = Language.objects.get(key='PYPY3')
                prefix = '# '
            elif name.lower().endswith('.java'):
                language = Language.objects.get(key='JAVA')
                prefix = '// '
            elif name.lower().endswith('.kt'):
                language = Language.objects.get(key='KOTLIN')
                prefix = '// '
            else:
                print(f'Invalid file extension `{name}`')
                continue

            submission_path = os.path.join(submissions_path, subfolder, name)
            source = open(submission_path, 'r').read()

            related_path = os.path.join(subfolder, name)
            submission = prefix + related_path + '\n' + source
            submissions.append((submission, language, user_to_submit))

    return submissions


def check_submit_users():
    for user in SUBMISSION_STATUS_MAP.values():
        if Profile.objects.filter(user__username=user).count() == 0:
            raise CommandError(f'User `{user}` not found. Please create the user first.')


def delete_old_submissions(problem_name=None):
    submissions = Submission.objects.filter(user__user__username__in=SUBMISSION_STATUS_MAP.values())
    if problem_name is not None:
        submissions = submissions.filter(problem__code=get_problem_code(problem_name))
    submissions.delete()


def submit_submissions(problem_name, icpc_folder, replace_old=False):
    problem_code = get_problem_code(problem_name)
    problem_folder = os.path.join(icpc_folder, problem_name)
    submissions_path = os.path.join(problem_folder, 'submissions')

    if not os.path.exists(submissions_path):
        raise CommandError(f'Submissions folder `{submissions_path}` not found.')

    if Problem.objects.filter(code=problem_code).count() == 0:
        raise CommandError(f'Problem `{problem_code}` not found.')

    problem = Problem.objects.get(code=problem_code)

    if not problem.has_test_data:
        raise CommandError(f'Problem `{problem_code}` has no test data.')

    submissions = get_submissions(submissions_path)
    if replace_old:
        delete_old_submissions(problem_name)

    for [code, lang, user_to_submit] in submissions:
        submission = Submission()
        submission.problem = problem
        submission.language = lang
        submission.user = Profile.objects.get(user__username=user_to_submit)
        submission.save()
        source = SubmissionSource(submission=submission, source=code)
        source.save()
        # set batch_rejudge=True to set the lowest priority
        submission.judge(force_judge=True, batch_rejudge=True)
        submission.refresh_from_db(fields=['status'])
        if submission.status == 'IE':
            print(f'[{problem_code}] WARNING: submission {submission.id} by {user_to_submit} '
                  f'could not be sent to the judge')
        else:
            print(f'[{problem_code}] Submitted {submission.id} by {user_to_submit}')
    return len(submissions)


class Command(BaseCommand):
    help = 'create icpc problem from kattis repo'

    def handle(self, *args, **options):
        icpc_folder = get_icpc_folder()

        os.system(f'cd {icpc_folder} && git pull origin master')
        # check if required users exist & delete all submissions
        check_submit_users()
        delete_old_submissions()

        problems = list_icpc_problems(icpc_folder)
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
