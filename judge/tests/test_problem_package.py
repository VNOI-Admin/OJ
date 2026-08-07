import json
import os
import shutil
import tempfile
import uuid
import zipfile
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from judge.forms import ProblemPackageImportForm
from judge.models import Language, Problem, problem_data_storage
from judge.models.tests.util import create_problem, create_problem_group, create_problem_type, create_user
from judge.tasks.problem_package import import_problem_package
from judge.utils.problem_package import ProblemPackageError, export_problem, import_problem


class ProblemPackageTestMixin:
    fixtures = ['language_all.json']

    def setUp(self):
        super().setUp()
        self.temporary_directory = tempfile.mkdtemp()
        self.data_root = os.path.join(self.temporary_directory, 'problems')
        self.work_root = os.path.join(self.temporary_directory, 'jobs')
        os.makedirs(self.data_root)
        self.settings_override = override_settings(
            DMOJ_PROBLEM_DATA_ROOT=self.data_root,
            VNOJ_PROBLEM_PACKAGE_ENABLED=True,
            VNOJ_PROBLEM_PACKAGE_ROOT=self.work_root,
        )
        self.settings_override.enable()
        self.original_storage_location = problem_data_storage._location
        problem_data_storage._location = self.data_root
        problem_data_storage.__dict__.pop('base_location', None)
        problem_data_storage.__dict__.pop('location', None)

        self.group = create_problem_group('group')
        self.problem_type = create_problem_type('type')
        self.user = create_user('package_admin', is_staff=True, is_superuser=True)

    def tearDown(self):
        problem_data_storage._location = self.original_storage_location
        problem_data_storage.__dict__.pop('base_location', None)
        problem_data_storage.__dict__.pop('location', None)
        self.settings_override.disable()
        shutil.rmtree(self.temporary_directory)
        super().tearDown()

    def make_problem(self, code='source'):
        problem = create_problem(
            code,
            name='Source problem',
            description='Statement',
            time_limit=2.5,
            memory_limit=131072,
            points=100,
            partial=True,
            short_circuit=True,
            allow_view_feedback=True,
            types=('type',),
        )
        problem.allowed_languages.set(Language.objects.filter(include_in_problem=True))
        data_directory = problem_data_storage.path(problem.code)
        os.makedirs(data_directory)
        with open(os.path.join(data_directory, 'init.yml'), 'w') as init_file:
            init_file.write('test_cases: []\n')
        with open(os.path.join(data_directory, 'tests.zip'), 'wb') as tests_file:
            tests_file.write(b'test data')
        return problem

    def make_package(self, problem=None):
        problem = problem or self.make_problem()
        package_path = os.path.join(self.temporary_directory, '%s.zip' % problem.code)
        export_problem(problem, package_path)
        return package_path

    def package_upload(self, package_path):
        with open(package_path, 'rb') as package_file:
            return SimpleUploadedFile('problem.zip', package_file.read(), content_type='application/zip')


class ProblemPackageCoreTests(ProblemPackageTestMixin, TestCase):
    def test_export_contains_manifest_and_problem_data(self):
        problem = self.make_problem()

        with zipfile.ZipFile(self.make_package(problem)) as package:
            manifest = json.loads(package.read('problem.json'))
            self.assertEqual(manifest['code'], problem.code)
            self.assertEqual(manifest['name'], problem.name)
            self.assertEqual(package.read('init.yml'), b'test_cases: []\n')
            self.assertEqual(package.read('tests.zip'), b'test data')

    def test_import_replaces_code_and_sets_defaults(self):
        imported = import_problem(self.make_package(), 'target', self.user)

        self.assertEqual(imported.code, 'target')
        self.assertEqual(imported.name, 'Source problem')
        self.assertTrue(imported.is_manually_managed)
        self.assertFalse(imported.is_public)
        self.assertEqual(imported.group, self.group)
        self.assertTrue(imported.types.filter(pk=self.problem_type.pk).exists())
        self.assertTrue(imported.curators.filter(pk=self.user.profile.pk).exists())
        with open(problem_data_storage.path('target/init.yml')) as init_file:
            self.assertEqual(init_file.read(), 'test_cases: []\n')

    def test_reexport_uses_replacement_code(self):
        imported = import_problem(self.make_package(), 'target', self.user)
        reexported_path = os.path.join(self.temporary_directory, 'reexported.zip')

        export_problem(imported, reexported_path)

        with zipfile.ZipFile(reexported_path) as package:
            self.assertEqual(json.loads(package.read('problem.json'))['code'], 'target')

    def test_import_rejects_existing_code_without_overwriting(self):
        package_path = self.make_package()
        existing = create_problem('existing', name='Keep me')

        with self.assertRaisesRegex(ProblemPackageError, 'already exists'):
            import_problem(package_path, existing.code, self.user)

        existing.refresh_from_db()
        self.assertEqual(existing.name, 'Keep me')

    def test_import_rejects_invalid_package(self):
        invalid_path = os.path.join(self.temporary_directory, 'invalid.zip')
        with open(invalid_path, 'wb') as package:
            package.write(b'not a zip')

        with self.assertRaisesRegex(ProblemPackageError, 'valid ZIP'):
            import_problem(invalid_path, 'target', self.user)

        missing_manifest_path = os.path.join(self.temporary_directory, 'missing-manifest.zip')
        with zipfile.ZipFile(missing_manifest_path, 'w') as package:
            package.writestr('init.yml', 'test_cases: []')
        with self.assertRaisesRegex(ProblemPackageError, 'problem.json'):
            import_problem(missing_manifest_path, 'target', self.user)
        self.assertFalse(Problem.objects.filter(code='target').exists())


class ProblemPackageFormTests(ProblemPackageTestMixin, TestCase):
    def test_form_accepts_http_and_https_urls(self):
        for package_url in ('http://example.com/problem.zip', 'https://example.com/problem.zip'):
            with self.subTest(package_url=package_url):
                form = ProblemPackageImportForm({
                    'source': ProblemPackageImportForm.SOURCE_URL,
                    'package_url': package_url,
                    'code': 'target',
                })
                self.assertTrue(form.is_valid(), form.errors)

    def test_form_rejects_unsupported_url_scheme(self):
        form = ProblemPackageImportForm({
            'source': ProblemPackageImportForm.SOURCE_URL,
            'package_url': 'ftp://example.com/problem.zip',
            'code': 'target',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('package_url', form.errors)

    def test_form_requires_selected_source_and_rejects_duplicate_code(self):
        create_problem('existing')
        form = ProblemPackageImportForm({
            'source': ProblemPackageImportForm.SOURCE_UPLOAD,
            'code': 'existing',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('package', form.errors)
        self.assertIn('code', form.errors)


class ProblemPackageViewTests(ProblemPackageTestMixin, TransactionTestCase):
    def test_import_requires_superuser(self):
        problem_admin = create_user('problem_admin', user_permissions=('add_problem', 'edit_own_problem'))
        self.client.force_login(problem_admin)

        response = self.client.get(reverse('problem_package_import'))

        self.assertEqual(response.status_code, 404)

    @override_settings(VNOJ_PROBLEM_PACKAGE_ENABLED=False)
    def test_feature_flag_disables_ui_and_endpoints(self):
        problem = self.make_problem()
        self.client.force_login(self.user)

        self.assertEqual(self.client.get(reverse('problem_package_import')).status_code, 404)
        self.assertEqual(
            self.client.get(reverse('problem_package_export', args=(problem.code,))).status_code,
            404,
        )
        detail = self.client.get(reverse('problem_detail', args=(problem.code,)))
        problem_list = self.client.get(reverse('problem_list'))
        self.assertNotContains(detail, reverse('problem_package_export', args=(problem.code,)))
        self.assertNotContains(problem_list, reverse('problem_package_import'))

    @patch('judge.views.problem_package.import_problem_package.delay')
    def test_upload_is_staged_and_queued(self, delay):
        delay.return_value.id = str(uuid.uuid4())
        package_path = self.make_package()
        self.client.force_login(self.user)

        response = self.client.post(reverse('problem_package_import'), {
            'source': ProblemPackageImportForm.SOURCE_UPLOAD,
            'package': self.package_upload(package_path),
            'code': 'target',
        })

        self.assertEqual(response.status_code, 302)
        _, kwargs = delay.call_args
        self.assertEqual(kwargs['user_id'], self.user.pk)
        self.assertEqual(kwargs['code'], 'target')
        self.assertTrue(os.path.isfile(os.path.join(kwargs['staged_directory'], 'package.zip')))
        shutil.rmtree(kwargs['staged_directory'])

    @patch('judge.views.problem_package.import_problem_package.delay')
    def test_url_is_queued(self, delay):
        delay.return_value.id = str(uuid.uuid4())
        self.client.force_login(self.user)

        response = self.client.post(reverse('problem_package_import'), {
            'source': ProblemPackageImportForm.SOURCE_URL,
            'package_url': 'http://example.com/problem.zip',
            'code': 'target',
        })

        self.assertEqual(response.status_code, 302)
        delay.assert_called_once_with(
            user_id=self.user.pk,
            code='target',
            package_url='http://example.com/problem.zip',
        )

    def test_export_response_can_be_reimported(self):
        problem = self.make_problem()
        self.client.force_login(self.user)

        response = self.client.get(reverse('problem_package_export', args=(problem.code,)))

        content = b''.join(response.streaming_content)
        package_path = os.path.join(self.temporary_directory, 'download.zip')
        with open(package_path, 'wb') as package:
            package.write(content)
        imported = import_problem(package_path, 'downloaded', self.user)
        self.assertEqual(imported.name, problem.name)


class ProblemPackageTaskTests(ProblemPackageTestMixin, TestCase):
    def stage_package(self, package_path):
        os.makedirs(self.work_root, exist_ok=True)
        staged_directory = tempfile.mkdtemp(dir=self.work_root)
        shutil.copyfile(package_path, os.path.join(staged_directory, 'package.zip'))
        return staged_directory

    def test_upload_task_imports_and_cleans_staged_directory(self):
        staged_directory = self.stage_package(self.make_package())

        code = import_problem_package(
            user_id=self.user.pk,
            code='target',
            staged_directory=staged_directory,
        )

        self.assertEqual(code, 'target')
        self.assertTrue(Problem.objects.get(code='target').is_manually_managed)
        self.assertFalse(os.path.exists(staged_directory))

    @patch('judge.tasks.problem_package.requests.get')
    def test_url_task_downloads_and_imports(self, get):
        with open(self.make_package(), 'rb') as package:
            content = package.read()
        response = Mock()
        response.iter_content.return_value = [content]
        response.raise_for_status.return_value = None
        get.return_value.__enter__.return_value = response

        code = import_problem_package(
            user_id=self.user.pk,
            code='target',
            package_url='https://example.com/problem.zip',
        )

        self.assertEqual(code, 'target')
        get.assert_called_once()

    def test_task_cleans_staged_directory_after_failure(self):
        os.makedirs(self.work_root, exist_ok=True)
        staged_directory = tempfile.mkdtemp(dir=self.work_root)
        with open(os.path.join(staged_directory, 'package.zip'), 'wb') as package:
            package.write(b'not a zip')

        with self.assertRaisesRegex(ProblemPackageError, 'valid ZIP'):
            import_problem_package(
                user_id=self.user.pk,
                code='target',
                staged_directory=staged_directory,
            )

        self.assertFalse(os.path.exists(staged_directory))

    @override_settings(VNOJ_PROBLEM_PACKAGE_ENABLED=False)
    def test_task_rejects_when_feature_is_disabled(self):
        os.makedirs(self.work_root, exist_ok=True)
        staged_directory = tempfile.mkdtemp(dir=self.work_root)
        with self.assertRaisesRegex(ProblemPackageError, 'not available'):
            import_problem_package(
                user_id=self.user.pk,
                code='target',
                staged_directory=staged_directory,
            )
        self.assertFalse(Problem.objects.filter(code='target').exists())
        self.assertFalse(os.path.exists(staged_directory))
