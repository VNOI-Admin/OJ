import os
import subprocess

from django.conf import settings
from django.core.management.base import CommandError

IGNORED_PROBLEM_FOLDERS = ['xx-mien-nam', 'yy-mien-nam', '6-mien-trung']
GIT_PULL_TIMEOUT = 120  # seconds
LAST_JOB_CACHE_KEY = 'icpc_last_job'


def get_icpc_folder():
    icpc_folder = getattr(settings, 'ICPC_GITHUB_FOLDER', None)
    if icpc_folder is None:
        raise CommandError('You should declare `ICPC_GITHUB_FOLDER` in settings')

    icpc_folder = os.path.expanduser(icpc_folder)
    if not os.path.exists(icpc_folder):
        raise CommandError(f'Folder {icpc_folder} not found. Make sure to clone the repo to that folder')
    return icpc_folder


def get_problem_code(problem_name):
    return 'icpc_' + problem_name[0]


def list_icpc_problems(icpc_folder):
    return sorted(
        name for name in os.listdir(icpc_folder)
        if os.path.isdir(os.path.join(icpc_folder, name)) and
        name not in IGNORED_PROBLEM_FOLDERS and not name.startswith('_') and not name.startswith('.')
    )


def git_pull(icpc_folder):
    """Pull without ever prompting. Failures are printed, not raised, so that the caller can carry on."""
    print(f'$ git pull ({icpc_folder})')
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_SSH_COMMAND='ssh -o BatchMode=yes')
    try:
        result = subprocess.run(
            ['git', 'pull'], cwd=icpc_folder, env=env, timeout=GIT_PULL_TIMEOUT, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace',
        )
    except (OSError, subprocess.SubprocessError) as e:
        print(f'git pull failed: {e}. Continuing with the current files.')
        return False

    print(result.stdout, end='')
    if result.returncode != 0:
        print(f'git pull failed with exit code {result.returncode}. Continuing with the current files.')
        return False
    return True


def git_last_commit(icpc_folder):
    """Return a one-line description of HEAD, or None if git fails."""
    try:
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%h %s (%an, %cd, %cr)', '--date=format:%Y-%m-%d %H:%M'],
            cwd=icpc_folder, timeout=10, stdin=subprocess.DEVNULL, capture_output=True, text=True, errors='replace',
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None
