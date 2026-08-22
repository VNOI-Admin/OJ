import logging

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

logger = logging.getLogger('judge.problem.archive')


ARCHIVE_SERVICE_URL = settings.VNOJ_PROBLEM_ARCHIVE_SERVICE_URL

# The archive service is not part of this codebase and its exact response shape is not pinned down yet,
# so every assumption about it lives in `_extract_url` and nowhere else.
_URL_KEYS = ('url', 'download_url', 'presigned_url')

validate_archive_url = URLValidator(schemes=['http', 'https'])


class ArchiveServiceError(Exception):
    """Raised when the archive service could not hand us a usable download URL."""


def _extract_url(data):
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, dict):
        for key in _URL_KEYS:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    raise ArchiveServiceError('archive service response did not contain a download URL')


def get_archive_download_url(problem_code: str) -> str:
    """Ask the archive service for a presigned URL to the archived data of `problem_code`."""
    if not ARCHIVE_SERVICE_URL:
        raise ArchiveServiceError('the problem archive service is not configured')

    headers = {}
    if settings.VNOJ_PROBLEM_ARCHIVE_SERVICE_TOKEN:
        headers['Authorization'] = 'Bearer %s' % settings.VNOJ_PROBLEM_ARCHIVE_SERVICE_TOKEN

    try:
        response = requests.get(
            ARCHIVE_SERVICE_URL,
            params={'problem': problem_code},
            headers=headers,
            timeout=settings.OJ_REQUESTS_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.exception('failed to reach the archive service for problem %s', problem_code)
        raise ArchiveServiceError('could not reach the archive service')

    try:
        data = response.json()
    except ValueError:
        data = response.text

    url = _extract_url(data)

    # We redirect the browser to whatever comes back, so never trust it unvalidated.
    try:
        validate_archive_url(url)
    except ValidationError:
        logger.error('archive service returned an invalid URL for problem %s', problem_code)
        raise ArchiveServiceError('archive service returned an invalid URL')

    return url
