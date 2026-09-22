import json

from django.test import SimpleTestCase, TestCase
from django.test.client import RequestFactory

from judge.views.widgets import MAX_REFERENCES, resolve_references


class TestResolveReferencesValidation(SimpleTestCase):
    def get(self, refs):
        return resolve_references(RequestFactory().get('/widgets/references', {'refs': refs}))

    def test_empty(self):
        self.assertJSONEqual(self.get('').content, {})

    def test_too_many(self):
        refs = ','.join('user:u%d' % i for i in range(MAX_REFERENCES + 1))
        self.assertEqual(self.get(refs).status_code, 400)

    def test_invalid_tokens_skipped(self):
        self.assertJSONEqual(self.get('evil:admin,user:bad name,user:x>nope,colonless').content, {})


class TestResolveReferences(TestCase):
    def test_unknown_user_and_dedup(self):
        response = self.client.get('/widgets/references', {'refs': 'user:no_such_user_x,user:no_such_user_x'})
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content,
                             {'user:no_such_user_x': '<span class="deleted-user">no_such_user_x</span>'})

    def test_existing_user(self):
        from judge.models.tests.util import create_user
        create_user(username='refcheck_user')
        response = self.client.get('/widgets/references', {'refs': 'user:refcheck_user,ruser:refcheck_user'})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('user:refcheck_user', data)
        self.assertIn('/user/refcheck_user', data['user:refcheck_user'])
        self.assertIn('ruser:refcheck_user', data)
