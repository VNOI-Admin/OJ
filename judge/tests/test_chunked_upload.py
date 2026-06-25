import json
import math
import os
import re
import shutil
import tempfile
from unittest.mock import patch

import fakeredis
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from judge.models import Profile

_CHUNK_SIZE = 1024
_MAX_FILE_SIZE = 5000
_TEST_QUOTA = 4000


class ChunkedUploadTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_media_dir = tempfile.mkdtemp()
        cls.settings_override = override_settings(
            MEDIA_ROOT=cls.test_media_dir,
            CHUNKED_UPLOAD_CHUNK_SIZE=_CHUNK_SIZE,
            CHUNKED_UPLOAD_MAX_FILE_SIZE=_MAX_FILE_SIZE,
        )
        cls.settings_override.enable()
        super().setUpClass()

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.password = 'testpass123'
        cls.user = user_model.objects.create_user(username='testuploader', password=cls.password)
        cls.user_profile = Profile.objects.create(user=cls.user)
        cls.other_user = user_model.objects.create_user(username='otheruser', password=cls.password)
        cls.other_user_profile = Profile.objects.create(user=cls.other_user)

    def setUp(self):
        self.client.login(username='testuploader', password=self.password)
        cache.clear()
        upload_dir = os.path.join(self.test_media_dir, 'chunked_uploads')
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir)
        self.fake_redis = fakeredis.FakeRedis()
        self.redis_patcher = patch('judge.views.chunked_upload.get_redis_connection', return_value=self.fake_redis)
        self.redis_patcher.start()

    def tearDown(self):
        self.redis_patcher.stop()
        super().tearDown()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.settings_override.disable()
        if os.path.exists(cls.test_media_dir):
            shutil.rmtree(cls.test_media_dir)

    def _init_upload(self, file_id, file_size=None, filename='test.zip'):
        chunk_size = settings.CHUNKED_UPLOAD_CHUNK_SIZE
        if file_size is None:
            file_size = 3 * chunk_size
        return self.client.post(reverse('chunked_upload_init'), data=json.dumps({
            'filename': filename,
            'file_size': file_size,
            'chunk_size': chunk_size,
            'total_chunks': math.ceil(file_size / chunk_size),
            'file_id': file_id,
        }), content_type='application/json')

    def test_endpoints_require_login(self):
        self.client.logout()
        for name in ('chunked_upload_init', 'chunked_upload_chunk', 'chunked_upload_complete'):
            self.assertEqual(self.client.post(reverse(name)).status_code, 302)

    def test_init_validation_and_creation(self):
        chunk_size = settings.CHUNKED_UPLOAD_CHUNK_SIZE
        max_file_size = settings.CHUNKED_UPLOAD_MAX_FILE_SIZE

        self.assertEqual(
            self.client.post(
                reverse('chunked_upload_init'), data=json.dumps({}), content_type='application/json',
            ).status_code,
            400,
        )

        oversized = max_file_size * 2
        response = self.client.post(reverse('chunked_upload_init'), data=json.dumps({
            'filename': 'large.zip',
            'file_size': oversized,
            'chunk_size': chunk_size,
            'total_chunks': math.ceil(oversized / chunk_size),
            'file_id': 'test-large',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('File size exceeds', response.json().get('error', ''))

        response = self._init_upload('test-create')
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertIn('upload_id', res_data)
        self.assertEqual(res_data['uploaded_chunks'], [])
        self.assertEqual(res_data['chunk_size'], chunk_size)

        upload_dir = os.path.join(self.test_media_dir, 'chunked_uploads', str(self.user.id), res_data['upload_id'])
        self.assertTrue(os.path.exists(upload_dir))
        files = os.listdir(upload_dir)
        self.assertEqual(len(files), 1)
        self.assertEqual(os.path.getsize(os.path.join(upload_dir, files[0])), 3 * chunk_size)

    def test_resume_session(self):
        chunk_size = settings.CHUNKED_UPLOAD_CHUNK_SIZE
        file_size = 2 * chunk_size
        response = self._init_upload('unique-file-id-123', file_size=file_size)
        upload_id = response.json()['upload_id']

        self.client.post(reverse('chunked_upload_chunk'), {
            'upload_id': upload_id,
            'chunk_index': 0,
            'file': SimpleUploadedFile('chunk', b'a' * chunk_size),
        })

        response2 = self._init_upload('unique-file-id-123', file_size=file_size)
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2.json()['upload_id'], upload_id)
        self.assertEqual(response2.json()['uploaded_chunks'], [0])

    def test_chunk_upload_out_of_order_and_zero_concatenation(self):
        chunk_size = settings.CHUNKED_UPLOAD_CHUNK_SIZE
        file_size = 3 * chunk_size
        upload_id = self._init_upload('test-data-id', file_size=file_size).json()['upload_id']
        chunk_url = reverse('chunked_upload_chunk')

        chunk_0 = b'0' * chunk_size
        chunk_1 = b'1' * chunk_size
        chunk_2 = b'2' * chunk_size

        self.assertEqual(self.client.post(chunk_url, {
            'upload_id': upload_id, 'chunk_index': 2,
            'file': SimpleUploadedFile('chunk_2', chunk_2),
        }).status_code, 200)
        self.assertEqual(self.client.post(chunk_url, {
            'upload_id': upload_id, 'chunk_index': 0,
            'file': SimpleUploadedFile('chunk_0', chunk_0),
        }).status_code, 200)

        upload_dir = os.path.join(self.test_media_dir, 'chunked_uploads', str(self.user.id), upload_id)
        filenames = os.listdir(upload_dir)
        self.assertEqual(len(filenames), 1)
        target_path = os.path.join(upload_dir, filenames[0])

        with open(target_path, 'rb') as f:
            content = f.read()
        self.assertEqual(content[0:chunk_size], chunk_0)
        self.assertEqual(content[chunk_size:2 * chunk_size], b'\x00' * chunk_size)
        self.assertEqual(content[2 * chunk_size:], chunk_2)

        complete_url = reverse('chunked_upload_complete')
        res = self.client.post(complete_url, {'upload_id': upload_id})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()['missing_chunks'], [1])

        self.client.post(chunk_url, {
            'upload_id': upload_id, 'chunk_index': 1,
            'file': SimpleUploadedFile('chunk_1', chunk_1),
        })
        res = self.client.post(complete_url, {'upload_id': upload_id})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status'], 'completed')

        with open(target_path, 'rb') as f:
            self.assertEqual(f.read(), chunk_0 + chunk_1 + chunk_2)

    def test_security_preventions(self):
        response = self._init_upload('malicious-file', file_size=100, filename='../../../../etc/passwd')
        self.assertEqual(response.status_code, 200)
        upload_id = response.json()['upload_id']

        upload_dir = os.path.join(self.test_media_dir, 'chunked_uploads', str(self.user.id), upload_id)
        filenames = os.listdir(upload_dir)
        self.assertEqual(len(filenames), 1)
        self.assertNotIn('..', filenames[0])
        self.assertNotIn('/', filenames[0])
        self.assertNotIn('passwd', filenames[0])

        self.client.login(username='otheruser', password=self.password)
        self.assertEqual(self.client.post(reverse('chunked_upload_chunk'), {
            'upload_id': upload_id,
            'chunk_index': 0,
            'file': SimpleUploadedFile('chunk', b'x' * 100),
        }).status_code, 403)

    def test_uuid_validation(self):
        invalid_id = 'invalid-uuid-format'

        response = self.client.post(reverse('chunked_upload_chunk'), {
            'upload_id': invalid_id, 'chunk_index': 0,
            'file': SimpleUploadedFile('chunk', b'a' * 100),
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid upload ID format', response.json().get('error', ''))

        response = self.client.post(reverse('chunked_upload_complete'), {'upload_id': invalid_id})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid upload ID format', response.json().get('error', ''))

    def test_filename_extension_sanitization_and_limit(self):
        response = self._init_upload('ext-sanitize-file', file_size=100, filename='malicious.php.longextensionhere')
        self.assertEqual(response.status_code, 200)

        upload_id = response.json()['upload_id']
        upload_dir = os.path.join(self.test_media_dir, 'chunked_uploads', str(self.user.id), upload_id)
        filenames = os.listdir(upload_dir)
        self.assertEqual(len(filenames), 1)

        ext = os.path.splitext(filenames[0])[1]
        self.assertLessEqual(len(ext), 10)
        self.assertTrue(re.match(r'^\.[a-zA-Z0-9]+$', ext))

    @override_settings(CHUNKED_UPLOAD_MAX_USER_DISK=_TEST_QUOTA)
    def test_disk_quota_reject_when_exceeded(self):
        chunk_size = settings.CHUNKED_UPLOAD_CHUNK_SIZE
        self.assertEqual(self._init_upload('quota-first', file_size=3 * chunk_size).status_code, 200)
        response = self._init_upload('quota-second', file_size=chunk_size)
        self.assertEqual(response.status_code, 400)
        self.assertIn('quota', response.json().get('error', '').casefold())

    @override_settings(CHUNKED_UPLOAD_MAX_USER_DISK=_TEST_QUOTA)
    def test_disk_quota_released_on_cancel(self):
        chunk_size = settings.CHUNKED_UPLOAD_CHUNK_SIZE
        init_resp = self._init_upload('quota-cancel', file_size=3 * chunk_size)
        self.assertEqual(init_resp.status_code, 200)
        upload_id = init_resp.json()['upload_id']

        self.assertEqual(self._init_upload('quota-cancel-2', file_size=chunk_size).status_code, 400)

        cancel_resp = self.client.post(reverse('chunked_upload_cancel'), {'upload_id': upload_id})
        self.assertEqual(cancel_resp.status_code, 200)

        self.assertEqual(self._init_upload('quota-cancel-2-retry', file_size=chunk_size).status_code, 200)

    @override_settings(CHUNKED_UPLOAD_MAX_USER_DISK=_MAX_FILE_SIZE)
    def test_disk_quota_exact_boundary(self):
        response = self._init_upload('quota-boundary', file_size=_MAX_FILE_SIZE)
        self.assertEqual(response.status_code, 200)

    @override_settings(CHUNKED_UPLOAD_MAX_USER_DISK=_MAX_FILE_SIZE - 1)
    def test_disk_quota_one_byte_over(self):
        response = self._init_upload('quota-over', file_size=_MAX_FILE_SIZE)
        self.assertEqual(response.status_code, 400)
        self.assertIn('quota', response.json().get('error', '').casefold())

    @override_settings(CHUNKED_UPLOAD_MAX_USER_DISK=_TEST_QUOTA)
    def test_resume_does_not_double_count_quota(self):
        chunk_size = settings.CHUNKED_UPLOAD_CHUNK_SIZE
        r1 = self._init_upload('quota-resume', file_size=3 * chunk_size)
        self.assertEqual(r1.status_code, 200)

        r2 = self._init_upload('quota-resume', file_size=3 * chunk_size)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()['upload_id'], r1.json()['upload_id'])

        self.client.post(reverse('chunked_upload_cancel'), {'upload_id': r1.json()['upload_id']})

        r3 = self._init_upload('quota-resume-after', file_size=chunk_size)
        self.assertEqual(r3.status_code, 200)
