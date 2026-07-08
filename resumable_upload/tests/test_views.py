import json
import os
import tempfile

import jwt
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from resumable_upload.views import create_upload_intent_token

from judge.models import Problem, ProblemGroup, ProblemType, Profile

User = get_user_model()

_JWT_SECRET = 'test-jwt-secret'
_HOOK_SECRET = 'test-hook-secret'
_SETTINGS = {
    'TUSD_JWT_SECRET': _JWT_SECRET,
    'TUSD_JWT_EXPIRY_SECONDS': 7200,
    'TUSD_HOOK_SECRET': _HOOK_SECRET,
    'TUSD_ENDPOINT': 'http://localhost:8080/files/',
    'TUSD_ALLOWED_FILE_TYPES': ('zipfile', 'generator', 'custom_checker', 'custom_grader', 'custom_header'),
    'TUSD_DATA_DIR': None,
}


def _make_user(username, password='pw', perms=()):
    user = User.objects.create_user(username=username, password=password)
    Profile.objects.create(user=user)
    for perm in perms:
        from django.contrib.auth.models import Permission
        user.user_permissions.add(Permission.objects.get(codename=perm))
    return user


def _make_problem(code='testproblem'):
    group = ProblemGroup.objects.get_or_create(name='g', defaults={'full_name': 'Group'})[0]
    ptype = ProblemType.objects.get_or_create(name='t', defaults={'full_name': 'Type'})[0]
    problem = Problem.objects.create(
        code=code,
        name='Test Problem',
        description='',
        group=group,
        time_limit=1,
        memory_limit=65536,
        points=100,
        partial=False,
        is_public=True,
    )
    problem.types.set([ptype])
    return problem


def _make_token(problem_code='testproblem', file_type='zipfile', file_name='tests.zip', **kwargs):
    """Create a valid JWT for use in hook payloads."""
    return create_upload_intent_token(1, problem_code, file_type, file_name)


def _hook_body(hook_type, token, storage_path=''):
    return json.dumps({
        'Type': hook_type,
        'Event': {
            'Upload': {
                'MetaData': {'token': token},
                'Storage': {'Path': storage_path},
            },
        },
    })


@override_settings(**_SETTINGS)
class UploadIntentViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.problem = _make_problem()
        cls.editor = _make_user('editor', perms=['edit_own_problem', 'edit_all_problem'])
        cls.regular = _make_user('regular', perms=['edit_own_problem'])
        cls.intent_url = reverse('resumable_upload:upload_intent')

    def _post(self, user, data):
        self.client.force_login(user)
        return self.client.post(
            self.intent_url,
            data=json.dumps(data),
            content_type='application/json',
        )

    def test_intent_requires_login(self):
        response = self.client.post(
            self.intent_url,
            data=json.dumps({'problem_code': 'testproblem', 'file_type': 'zipfile', 'file_name': 'x.zip'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_intent_valid_request(self):
        resp = self._post(self.editor, {
            'problem_code': 'testproblem',
            'file_type': 'zipfile',
            'file_name': 'tests.zip',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('token', data)
        self.assertIn('tusd_endpoint', data)
        payload = jwt.decode(data['token'], _JWT_SECRET, algorithms=['HS256'])
        self.assertEqual(payload['problem_code'], 'testproblem')

    def test_intent_invalid_problem_code(self):
        resp = self._post(self.editor, {
            'problem_code': 'does_not_exist',
            'file_type': 'zipfile',
            'file_name': 'x.zip',
        })
        self.assertEqual(resp.status_code, 404)

    def test_intent_requires_edit_permission(self):
        resp = self._post(self.regular, {
            'problem_code': 'testproblem',
            'file_type': 'zipfile',
            'file_name': 'x.zip',
        })
        self.assertEqual(resp.status_code, 404)

    def test_intent_invalid_file_type(self):
        resp = self._post(self.editor, {
            'problem_code': 'testproblem',
            'file_type': 'malware',
            'file_name': 'x.zip',
        })
        self.assertEqual(resp.status_code, 400)

    def test_intent_missing_fields(self):
        resp = self._post(self.editor, {'problem_code': 'testproblem'})
        self.assertEqual(resp.status_code, 400)


@override_settings(**_SETTINGS)
class TusdHookViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.problem = _make_problem()

    def setUp(self):
        self.hooks_url = reverse('resumable_upload:tusd_hooks')

    def _post(self, body, secret=_HOOK_SECRET):
        headers = {}
        if secret is not None:
            headers['HTTP_X_TUSD_HOOK_SECRET'] = secret
        return self.client.post(
            self.hooks_url,
            data=body,
            content_type='application/json',
            **headers,
        )

    def test_hook_missing_secret(self):
        token = _make_token()
        resp = self._post(_hook_body('pre-create', token), secret=None)
        self.assertEqual(resp.status_code, 403)

    def test_hook_wrong_secret(self):
        token = _make_token()
        resp = self._post(_hook_body('pre-create', token), secret='wrong')
        self.assertEqual(resp.status_code, 403)

    def test_hook_pre_create_valid_token(self):
        token = _make_token()
        resp = self._post(_hook_body('pre-create', token))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertNotIn('RejectUpload', data)

    def test_hook_pre_create_invalid_token(self):
        resp = self._post(_hook_body('pre-create', 'not.a.jwt'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('RejectUpload'))

    def test_hook_pre_finish_moves_file(self):
        with tempfile.TemporaryDirectory() as data_root:
            src_file = os.path.join(data_root, 'upload-id')
            with open(src_file, 'wb') as f:
                f.write(b'zip content')

            token = _make_token(problem_code='testproblem', file_name='tests.zip')
            body = _hook_body('pre-finish', token, storage_path=src_file)
            with override_settings(DMOJ_PROBLEM_DATA_ROOT=data_root):
                resp = self._post(body)

            self.assertEqual(resp.status_code, 200)
            dest = os.path.join(data_root, 'testproblem', 'tests.zip')
            self.assertTrue(os.path.exists(dest))

    def test_hook_pre_finish_error_rejects(self):
        """If the source file does not exist, pre-finish returns RejectUpload."""
        token = _make_token()
        body = _hook_body('pre-finish', token, storage_path='/nonexistent/path/upload-id')
        with tempfile.TemporaryDirectory() as data_root:
            with override_settings(DMOJ_PROBLEM_DATA_ROOT=data_root):
                resp = self._post(body)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get('RejectUpload'))

    def test_hook_unknown_type(self):
        token = _make_token()
        resp = self._post(_hook_body('post-terminate', token))
        self.assertEqual(resp.status_code, 400)


@override_settings(**_SETTINGS)
class ProblemDataViewIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.problem = _make_problem('testproblem')
        cls.editor = _make_user('editor', perms=['edit_own_problem', 'edit_all_problem'])
        cls.url = reverse('problem_data', args=[cls.problem.code])

    def test_post_with_tus_upload_completed(self):
        import zipfile
        from judge.models import ProblemData
        from judge.models.problem_data import problem_data_storage

        with tempfile.TemporaryDirectory() as data_root:
            prob_dir = os.path.join(data_root, self.problem.code)
            os.makedirs(prob_dir, exist_ok=True)

            zip_path = os.path.join(prob_dir, 'tests.zip')
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr('init.yml', 'testcases: []')

            self.client.force_login(self.editor)

            post_data = {
                'problem-data-checker': 'standard',
                'problem-data-grader': 'standard',
                'problem-data-checker_type': 'testlib',
                'problem-data-io_method': 'standard',
                'problem-data-output_limit': '',
                'cases-TOTAL_FORMS': '0',
                'cases-INITIAL_FORMS': '0',
                'cases-MIN_NUM_FORMS': '0',
                'cases-MAX_NUM_FORMS': '1',
                'tus_upload_completed': 'tests.zip',
            }

            old_location = problem_data_storage._location
            old_base_location = problem_data_storage.base_location
            problem_data_storage._location = data_root
            problem_data_storage.base_location = data_root

            try:
                with override_settings(DMOJ_PROBLEM_DATA_ROOT=data_root):
                    resp = self.client.post(self.url, data=post_data)
            finally:
                problem_data_storage._location = old_location
                problem_data_storage.base_location = old_base_location

            self.assertEqual(resp.status_code, 302)

            prob_data = ProblemData.objects.get(problem=self.problem)
            self.assertEqual(prob_data.zipfile.name, 'testproblem/tests.zip')
            self.assertTrue(prob_data.zipfile_size > 0)
