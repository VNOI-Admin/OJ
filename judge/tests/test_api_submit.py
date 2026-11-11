from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from judge.models import Judge, Language, Submission
from judge.models.tests.util import create_problem, create_user
from judge.utils.problem_data_storage import StorageManager

URL = '/api/v2/submit/a'
TABLE_URL = '/api/v2/language/table'


@mock.patch('judge.models.submission.judge_submission')
class APISubmitTestCase(TestCase):
    fixtures = ['language_small.json']

    @classmethod
    def setUpTestData(cls):
        cls.user = create_user(username='contestant')
        cls.auth = {'HTTP_AUTHORIZATION': 'Bearer ' + cls.user.profile.generate_api_token()}
        cls.problem = create_problem(code='a', is_public=True, allowed_languages=('CPP17', 'OUTPUT', 'PY3'))
        cls.hidden = create_problem(code='hidden', allowed_languages=('CPP17',))
        judge = Judge.objects.create(name='judge', auth_key='key', online=True,
                                     storages=[StorageManager.get_instance().default_name])
        judge.runtimes.set(Language.objects.filter(key__in=('CPP17', 'OUTPUT')))
        cls.cpp = Language.objects.get(key='CPP17')
        cls.output = Language.objects.get(key='OUTPUT')

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def submit(self, name, content, language, url=URL):
        return self.client.post(url, {
            'file': SimpleUploadedFile(name, content),
            'language': language.id,
        }, **self.auth)

    def test_text_file_becomes_source(self, judge_submission):
        response = self.submit('a.cpp', b'int main() {}\n', self.cpp)
        self.assertEqual(response.status_code, 201)
        submission = Submission.objects.get(id=response.json()['data']['id'])
        self.assertEqual(submission.source.source, 'int main() {}')
        self.assertEqual(submission.language, self.cpp)
        judge_submission.assert_called_once()

    def test_binary_file_rejected(self, judge_submission):
        response = self.submit('a', b'\x7fELF\x02\x01\x01\x00\x00\x00', self.cpp)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['message'], 'File is not a text file.')
        self.assertFalse(Submission.objects.exists())

    def test_too_big_file_rejected(self, judge_submission):
        response = self.submit('a.cpp', b'/' * (65536 * 4 + 1), self.cpp)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['message'], 'File is too big (maximum 65536 characters).')
        self.assertFalse(Submission.objects.exists())

    def test_multibyte_file_within_character_limit(self, judge_submission):
        response = self.submit('a.cpp', ('// ' + 'ộ' * 30000).encode(), self.cpp)
        self.assertEqual(response.status_code, 201)

    def test_bom_stripped(self, judge_submission):
        response = self.submit('a.cpp', b'\xef\xbb\xbfint main() {}', self.cpp)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Submission.objects.get().source.source, 'int main() {}')

    def test_non_utf8_rejected(self, judge_submission):
        response = self.submit('a.cpp', 'int main() { cout << "Xin chào"; }'.encode('cp1258'), self.cpp)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['message'], 'File is not valid UTF-8 text.')
        self.assertFalse(Submission.objects.exists())

    @mock.patch('judge.views.problem.submission_uploader', return_value='/submission_file/a/1/x.zip')
    def test_zip_for_output_only(self, uploader, judge_submission):
        response = self.submit('out.zip', b'PK\x03\x04\x00\x00', self.output)
        self.assertEqual(response.status_code, 201)
        submission = Submission.objects.get(id=response.json()['data']['id'])
        self.assertEqual(submission.source.source, '/submission_file/a/1/x.zip')
        self.assertEqual(uploader.call_args.kwargs['submission_file'].name, 'out.zip')

    def test_wrong_extension_for_output_only(self, judge_submission):
        response = self.submit('a.cpp', b'int main() {}\n', self.output)
        self.assertEqual(response.status_code, 400)
        self.assertIn('expected zip', response.json()['error']['message'])

    def test_language_without_judge_rejected(self, judge_submission):
        response = self.submit('a.py', b'print(1)\n', Language.objects.get(key='PY3'))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Submission.objects.exists())

    def test_non_numeric_language_rejected(self, judge_submission):
        response = self.client.post(URL, {
            'file': SimpleUploadedFile('a.cpp', b'int main() {}\n'),
            'language': 'abc',
        }, **self.auth)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['message'],
                         'Select a valid choice. That choice is not one of the available choices.')
        self.assertFalse(Submission.objects.exists())

    def test_login_required(self, judge_submission):
        response = self.client.post(URL, {
            'file': SimpleUploadedFile('a.cpp', b'int main() {}\n'),
            'language': self.cpp.id,
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Submission.objects.exists())

    def test_hidden_problem_not_found(self, judge_submission):
        response = self.submit('a.cpp', b'int main() {}\n', self.cpp, url='/api/v2/submit/hidden')
        self.assertEqual(response.status_code, 404)

    def test_banned_user_rejected(self, judge_submission):
        self.problem.banned_users.add(self.user.profile)
        response = self.submit('a.cpp', b'int main() {}\n', self.cpp)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error']['code'], 403)
        self.assertFalse(Submission.objects.exists())

    def test_language_table_requires_problem(self, judge_submission):
        response = self.client.get(TABLE_URL, **self.auth)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['message'], 'problem is required')

    def test_language_table_for_problem(self, judge_submission):
        response = self.client.get(TABLE_URL, {'problem': 'a'}, **self.auth)
        data = response.json()['data']
        languages = data['languages']
        self.assertEqual({language['key'] for language in languages}, {'CPP17', 'OUTPUT'})
        output = next(language for language in languages if language['key'] == 'OUTPUT')
        self.assertEqual((output['extension'], output['file_only'], output['file_size_limit']), ('zip', True, 10))
        # The profile default (CPP20) is not allowed for this problem.
        self.assertNotIn(self.user.profile.language_id, {language['id'] for language in languages})
        self.assertIsNone(data['default_language_id'])

    def test_language_table_default_language_allowed(self, judge_submission):
        self.user.profile.language = self.cpp
        self.user.profile.save(update_fields=['language'])
        response = self.client.get(TABLE_URL, {'problem': 'a'}, **self.auth)
        self.assertEqual(response.json()['data']['default_language_id'], self.cpp.id)

    def test_language_table_anonymous(self, judge_submission):
        response = self.client.get(TABLE_URL, {'problem': 'a'})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['data']['default_language_id'])

    def test_language_table_hidden_problem(self, judge_submission):
        response = self.client.get(TABLE_URL, {'problem': 'hidden'}, **self.auth)
        self.assertEqual(response.status_code, 404)
