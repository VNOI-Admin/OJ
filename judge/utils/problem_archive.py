import logging

import requests
from django.conf import settings

logger = logging.getLogger('judge.problem.archive')


class ArchiveServiceError(Exception):
    """Raised when the archive service could not be reached or gave an unusable answer."""


class ArchiveService:
    """The single place that talks to the external problem-archive service."""

    def _request(self, method, path='', **kwargs):
        base = settings.VNOJ_PROBLEM_ARCHIVE_SERVICE_URL  # read lazily so override_settings works in tests
        if not base:
            raise ArchiveServiceError('the problem archive service is not configured')

        headers = {}
        if settings.VNOJ_PROBLEM_ARCHIVE_SERVICE_TOKEN:
            headers['Authorization'] = 'Bearer %s' % settings.VNOJ_PROBLEM_ARCHIVE_SERVICE_TOKEN

        try:
            response = requests.request(
                method, base.rstrip('/') + path,
                headers=headers, timeout=settings.OJ_REQUESTS_TIMEOUT, **kwargs,
            )
            response.raise_for_status()
        except requests.RequestException:
            logger.exception('archive service request failed: %s %s', method, path)
            raise ArchiveServiceError('could not reach the archive service')
        return response

    def get_download_url(self, problem_code: str) -> str:
        """Ask the archive service for a presigned URL to the archived data of `problem_code`."""
        response = self._request('GET', '/download', params={'problem': problem_code})

        try:
            data = response.json()
            return data.get('url')
        except ValueError:
            logger.exception('archive service returned an invalid URL for problem %s', problem_code)
            raise ArchiveServiceError('archive service returned an invalid URL')

    def restore(self, problem_code: str) -> None:
        """Ask the archive service to move `problem_code`'s data back to local storage."""
        self._request('POST', '/restore', params={'problem': problem_code})

    def archive(self, problem_code: str, organization_slug: str) -> None:
        """Ask the archive service to move `problem_code`'s data to cold storage."""
        self._request('POST', '/archive', params={'problem': problem_code, 'organization': organization_slug})


archive_service = ArchiveService()
