from unittest import mock

import requests
from django.test import SimpleTestCase

from judge.utils import problem_archive
from judge.utils.problem_archive import ArchiveServiceError, get_archive_download_url

PRESIGNED_URL = 'https://s3.example.com/archive/foo.zip?sig=abc'


def fake_response(json_data=None, text=None):
    response = mock.Mock()
    response.raise_for_status.return_value = None
    if json_data is None:
        response.json.side_effect = ValueError('not json')
        response.text = text
    else:
        response.json.return_value = json_data
    return response


class GetArchiveDownloadURLTestCase(SimpleTestCase):
    def setUp(self):
        # The module reads the setting once at import time, like judge.utils.pdfoid does.
        patcher = mock.patch.multiple(
            problem_archive,
            ARCHIVE_SERVICE_URL='https://archive.example.com/presign',
            ARCHIVE_DOWNLOAD_ENABLED=True,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_raises_when_not_configured(self):
        with mock.patch.object(problem_archive, 'ARCHIVE_DOWNLOAD_ENABLED', False):
            with self.assertRaises(ArchiveServiceError):
                get_archive_download_url('foo')

    def test_passes_the_problem_code_and_returns_the_url(self):
        with mock.patch('requests.get', return_value=fake_response({'url': PRESIGNED_URL})) as get:
            self.assertEqual(get_archive_download_url('foo'), PRESIGNED_URL)
        self.assertEqual(get.call_args.kwargs['params'], {'problem': 'foo'})

    def test_accepts_the_alternative_url_keys(self):
        for key in ('download_url', 'presigned_url'):
            with self.subTest(key=key):
                with mock.patch('requests.get', return_value=fake_response({key: PRESIGNED_URL})):
                    self.assertEqual(get_archive_download_url('foo'), PRESIGNED_URL)

    def test_accepts_a_bare_url_body(self):
        with mock.patch('requests.get', return_value=fake_response(text=PRESIGNED_URL + '\n')):
            self.assertEqual(get_archive_download_url('foo'), PRESIGNED_URL)

    def test_sends_the_token_when_one_is_configured(self):
        with self.settings(VNOJ_PROBLEM_ARCHIVE_SERVICE_TOKEN='s3cret'):
            with mock.patch('requests.get', return_value=fake_response({'url': PRESIGNED_URL})) as get:
                get_archive_download_url('foo')
        self.assertEqual(get.call_args.kwargs['headers']['Authorization'], 'Bearer s3cret')

    def test_wraps_transport_errors(self):
        with mock.patch('requests.get', side_effect=requests.ConnectionError('down')):
            with self.assertRaises(ArchiveServiceError):
                get_archive_download_url('foo')

    def test_rejects_a_response_without_a_url(self):
        with mock.patch('requests.get', return_value=fake_response({'status': 'pending'})):
            with self.assertRaises(ArchiveServiceError):
                get_archive_download_url('foo')

    def test_rejects_a_non_http_url(self):
        # We redirect the browser to this value, so anything but http(s) must be refused.
        with mock.patch('requests.get', return_value=fake_response({'url': 'javascript:alert(1)'})):
            with self.assertRaises(ArchiveServiceError):
                get_archive_download_url('foo')
