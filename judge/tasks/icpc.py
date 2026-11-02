import io
import time
from contextlib import redirect_stdout

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import gettext as _

from judge.utils.celery import Progress

__all__ = ('run_icpc_job',)


@shared_task(bind=True)
def run_icpc_job(self, problem=None, import_problems=True, submit=False):
    # These commands import judge.views, which in turn import judge.tasks.
    from judge.management.commands.create_icpc_problem import create_problem, describe_import
    from judge.management.commands.submit_icpc_solution import check_submit_users, submit_submissions
    from judge.utils.icpc import LAST_JOB_CACHE_KEY, get_icpc_folder, get_problem_code, git_pull, \
        list_icpc_problems

    log = io.StringIO()
    results = {}
    error = None
    with redirect_stdout(log), Progress(self, 1, stage=_('Running git pull')) as progress:
        try:
            icpc_folder = get_icpc_folder()
            git_pull(icpc_folder)

            if submit:
                check_submit_users()

            problems = list_icpc_problems(icpc_folder)
            if problem is not None:
                if problem not in problems:
                    raise ValueError(f'Problem `{problem}` not found in {icpc_folder}')
                problems = [problem]

            progress.total = len(problems) or 1
            for done, name in enumerate(problems):
                progress.done = done
                progress.stage = _('Processing %s') % name
                print('=============================')
                print(name)
                results[name] = result = {
                    'code': get_problem_code(name), 'ok': True, 'message': '', 'submit_error': None,
                }
                if import_problems:
                    try:
                        result['message'] = describe_import(*create_problem(name, icpc_folder))
                        print('Imported.')
                    except Exception as e:
                        print(f'Cannot import problem {name}: {e}')
                        result['ok'] = False
                        result['message'] = str(e)
                        continue

                if submit:
                    if import_problems:
                        # Give the judges time to pick up the newly imported problem data.
                        time.sleep(5)
                    try:
                        count = submit_submissions(name, icpc_folder, replace_old=True)
                        result['message'] = f"{result['message']} {count} solutions submitted.".strip()
                    except Exception as e:
                        print(f'Cannot submit problem {name}: {e}')
                        result['submit_error'] = str(e)
        except Exception as e:
            print(f'Job failed: {e}')
            error = str(e)

    # Kept without expiry so the job page can still show it after the celery result expires.
    cache.set(LAST_JOB_CACHE_KEY, {
        'id': self.request.id, 'finished': timezone.now(), 'problem': problem,
        'import_problems': import_problems, 'submit': submit, 'results': results, 'error': error,
    }, None)
    return {'log': log.getvalue(), 'results': results, 'error': error}
