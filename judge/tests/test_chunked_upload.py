import json
import os
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


class ChunkedUploadTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        # Dynamically create temporary test media directory
        cls.test_media_dir = tempfile.mkdtemp()
        cls.settings_override = override_settings(
            MEDIA_ROOT=cls.test_media_dir,
            CHUNKED_UPLOAD_CHUNK_SIZE=1024,
            CHUNKED_UPLOAD_MAX_FILE_SIZE=5000,
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
        # Clear cache for each test to keep it isolated
        cache.clear()
        # Clean up chunked_uploads directory to prevent 429 Too Many Requests
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
        # Clean up temporary test media directory
        if os.path.exists(cls.test_media_dir):
            shutil.rmtree(cls.test_media_dir)

    def test_endpoints_require_login(self):
        self.client.logout()
        endpoints = [
            ('chunked_upload_init', {}),
            ('chunked_upload_chunk', {}),
            ('chunked_upload_complete', {}),
        ]
        for name, kwargs in endpoints:
            url = reverse(name, kwargs=kwargs)
            # GET should be rejected, POST should redirect or return 302/403
            response = self.client.post(url)
            self.assertEqual(response.status_code, 302)  # Redirects to login

    def test_init_validation_and_creation(self):
        url = reverse('chunked_upload_init')

        # Test missing params
        response = self.client.post(url, data=json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 400)

        # Test over limit file size
        data = {
            'filename': 'large_file.zip',
            'file_size': 10000,
            'chunk_size': 1024,
            'total_chunks': 10,
            'file_id': 'test-large-file',
        }
        response = self.client.post(url, data=json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('File size exceeds', response.json().get('error', ''))

        # Test successful initialization
        data['file_size'] = 3000
        data['total_chunks'] = 3
        response = self.client.post(url, data=json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertIn('upload_id', res_data)
        self.assertEqual(res_data['uploaded_chunks'], [])
        self.assertEqual(res_data['chunk_size'], 1024)

        # Verify directory and file pre-allocated
        upload_id = res_data['upload_id']
        expected_dir = os.path.join(self.test_media_dir, 'chunked_uploads', str(self.user.id), upload_id)
        self.assertTrue(os.path.exists(expected_dir))

        files_in_dir = os.listdir(expected_dir)
        self.assertEqual(len(files_in_dir), 1)
        assembled_file_path = os.path.join(expected_dir, files_in_dir[0])
        self.assertEqual(os.path.getsize(assembled_file_path), 3000)

    def test_resume_session(self):
        url = reverse('chunked_upload_init')
        data = {
            'filename': 'resume_file.zip',
            'file_size': 2048,
            'chunk_size': 1024,
            'total_chunks': 2,
            'file_id': 'unique-file-id-123',
        }
        # First initialization
        response = self.client.post(url, data=json.dumps(data), content_type='application/json')
        upload_id_1 = response.json()['upload_id']

        # Simulate upload of chunk 0
        chunk_url = reverse('chunked_upload_chunk')
        chunk_file = SimpleUploadedFile('chunk', b'a' * 1024)
        response = self.client.post(chunk_url, {
            'upload_id': upload_id_1,
            'chunk_index': 0,
            'file': chunk_file,
        })
        self.assertEqual(response.status_code, 200)

        # Call init again with the same file_id
        response2 = self.client.post(url, data=json.dumps(data), content_type='application/json')
        self.assertEqual(response2.status_code, 200)
        res_data = response2.json()
        self.assertEqual(res_data['upload_id'], upload_id_1)
        self.assertEqual(res_data['uploaded_chunks'], [0])

    def test_chunk_upload_out_of_order_and_zero_concatenation(self):
        # Initialize
        url = reverse('chunked_upload_init')
        data = {
            'filename': 'test_data.zip',
            'file_size': 3000,
            'chunk_size': 1024,
            'total_chunks': 3,
            'file_id': 'test-data-id',
        }
        res = self.client.post(url, data=json.dumps(data), content_type='application/json').json()
        upload_id = res['upload_id']

        chunk_url = reverse('chunked_upload_chunk')

        # Upload chunk 2 first (out of order test)
        chunk_2_content = b'2' * 952  # Last chunk size is 3000 - 2048 = 952
        chunk_file_2 = SimpleUploadedFile('chunk_2', chunk_2_content)
        res_chunk_2 = self.client.post(chunk_url, {
            'upload_id': upload_id,
            'chunk_index': 2,
            'file': chunk_file_2,
        })
        self.assertEqual(res_chunk_2.status_code, 200)

        # Upload chunk 0
        chunk_0_content = b'0' * 1024
        chunk_file_0 = SimpleUploadedFile('chunk_0', chunk_0_content)
        res_chunk_0 = self.client.post(chunk_url, {
            'upload_id': upload_id,
            'chunk_index': 0,
            'file': chunk_file_0,
        })
        self.assertEqual(res_chunk_0.status_code, 200)

        # Verify content written using seek (out of order verification)
        upload_dir = os.path.join(self.test_media_dir, 'chunked_uploads', str(self.user.id), upload_id)
        filenames = os.listdir(upload_dir)
        self.assertEqual(len(filenames), 1)
        target_path = os.path.join(upload_dir, filenames[0])

        with open(target_path, 'rb') as f:
            content = f.read()
            self.assertEqual(content[0:1024], chunk_0_content)
            # Chunk 1 was not uploaded, should be null bytes
            self.assertEqual(content[1024:2048], b'\x00' * 1024)
            self.assertEqual(content[2048:3000], chunk_2_content)

        # Test incomplete status on complete endpoint
        complete_url = reverse('chunked_upload_complete')
        res_complete = self.client.post(complete_url, {'upload_id': upload_id})
        self.assertEqual(res_complete.status_code, 400)
        self.assertIn('missing_chunks', res_complete.json())
        self.assertEqual(res_complete.json()['missing_chunks'], [1])

        # Upload missing chunk 1
        chunk_1_content = b'1' * 1024
        chunk_file_1 = SimpleUploadedFile('chunk_1', chunk_1_content)
        res_chunk_1 = self.client.post(chunk_url, {
            'upload_id': upload_id,
            'chunk_index': 1,
            'file': chunk_file_1,
        })
        self.assertEqual(res_chunk_1.status_code, 200)

        # Complete upload
        res_complete_success = self.client.post(complete_url, {'upload_id': upload_id})
        self.assertEqual(res_complete_success.status_code, 200)
        self.assertEqual(res_complete_success.json()['status'], 'completed')
        self.assertEqual(res_complete_success.json()['safe_filename'], filenames[0])

        with open(target_path, 'rb') as f:
            final_content = f.read()
            self.assertEqual(final_content, chunk_0_content + chunk_1_content + chunk_2_content)

    def test_security_preventions(self):
        url = reverse('chunked_upload_init')
        # Path traversal name
        data = {
            'filename': '../../../../etc/passwd',
            'file_size': 100,
            'chunk_size': settings.CHUNKED_UPLOAD_CHUNK_SIZE,
            'total_chunks': 1,
            'file_id': 'malicious-file',
        }
        response = self.client.post(url, data=json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        upload_id = response.json()['upload_id']

        # Ensure safe filename is a UUID without any path traversal chars
        upload_dir = os.path.join(self.test_media_dir, 'chunked_uploads', str(self.user.id), upload_id)
        filenames = os.listdir(upload_dir)
        self.assertEqual(len(filenames), 1)
        self.assertNotIn('..', filenames[0])
        self.assertNotIn('/', filenames[0])
        self.assertNotIn('etc', filenames[0])
        self.assertNotIn('passwd', filenames[0])

        # Check other user cannot upload chunks to this upload_id
        self.client.login(username='otheruser', password=self.password)
        chunk_url = reverse('chunked_upload_chunk')
        chunk_file = SimpleUploadedFile('chunk', b'x' * 100)
        response = self.client.post(chunk_url, {
            'upload_id': upload_id,
            'chunk_index': 0,
            'file': chunk_file,
        })
        self.assertEqual(response.status_code, 403)

    def test_uuid_validation(self):
        # Try chunk upload with invalid upload_id
        chunk_url = reverse('chunked_upload_chunk')
        chunk_file = SimpleUploadedFile('chunk', b'a' * 100)
        response = self.client.post(chunk_url, {
            'upload_id': 'invalid-uuid-format',
            'chunk_index': 0,
            'file': chunk_file,
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid upload ID format', response.json().get('error', ''))

        # Try complete upload with invalid upload_id
        complete_url = reverse('chunked_upload_complete')
        response = self.client.post(complete_url, {
            'upload_id': 'invalid-uuid-format',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid upload ID format', response.json().get('error', ''))

    def test_filename_extension_sanitization_and_limit(self):
        url = reverse('chunked_upload_init')
        data = {
            'filename': 'malicious_file.php.longextensionhere',
            'file_size': 100,
            'chunk_size': settings.CHUNKED_UPLOAD_CHUNK_SIZE,
            'total_chunks': 1,
            'file_id': 'ext-sanitize-file',
        }
        response = self.client.post(url, data=json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        upload_id = response.json()['upload_id']

        upload_dir = os.path.join(self.test_media_dir, 'chunked_uploads', str(self.user.id), upload_id)
        filenames = os.listdir(upload_dir)
        self.assertEqual(len(filenames), 1)

        # Get extension of safe_filename
        ext = os.path.splitext(filenames[0])[1]
        # Should be truncated to 10 characters (including dot, e.g., '.longextens')
        self.assertLessEqual(len(ext), 11)  # dot + 10 chars = 11 chars max
        # Check that it only contains alphanumeric and dot
        import re
        self.assertTrue(re.match(r'^\.[a-zA-Z0-9]+$', ext))
