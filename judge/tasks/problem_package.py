import os
import shutil
import tempfile
from urllib.parse import urlsplit

import requests
from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model

from judge.utils.problem_package import ProblemPackageError, can_use_problem_packages, import_problem

__all__ = ('import_problem_package',)


def _download(package_url, destination):
    if urlsplit(package_url).scheme.casefold() not in ('http', 'https'):
        raise ProblemPackageError('Only HTTP and HTTPS URLs are accepted.')
    with requests.get(package_url, stream=True, timeout=settings.VNOJ_PROBLEM_PACKAGE_DOWNLOAD_TIMEOUT) as response:
        response.raise_for_status()
        with open(destination, 'wb') as package_file:
            for chunk in response.iter_content(chunk_size=settings.VNOJ_PROBLEM_PACKAGE_DOWNLOAD_CHUNK_SIZE):
                if chunk:
                    package_file.write(chunk)


@shared_task
def import_problem_package(user_id, code, package_url=None, staged_directory=None):
    try:
        user = get_user_model().objects.get(pk=user_id)
        if not can_use_problem_packages(user):
            raise ProblemPackageError('Problem package import is not available.')
        if bool(package_url) == bool(staged_directory):
            raise ProblemPackageError('Exactly one package source is required.')

        os.makedirs(settings.VNOJ_PROBLEM_PACKAGE_ROOT, exist_ok=True)
        if package_url:
            with tempfile.TemporaryDirectory(dir=settings.VNOJ_PROBLEM_PACKAGE_ROOT) as work_directory:
                package_path = os.path.join(work_directory, 'package.zip')
                _download(package_url, package_path)
                problem = import_problem(package_path, code, user, temporary_root=work_directory)
        else:
            package_path = os.path.join(staged_directory, 'package.zip')
            problem = import_problem(package_path, code, user, temporary_root=staged_directory)
        return problem.code
    finally:
        if staged_directory:
            shutil.rmtree(staged_directory, ignore_errors=True)
