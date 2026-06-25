from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.test import RequestFactory, TestCase

from judge.models import UserFile
from judge.models.tests.util import create_user
from judge.utils.user_file_access import authorize_file_access


class UserFilePermissionTest(TestCase):
    fixtures = ['language_all.json']

    @classmethod
    def setUpTestData(cls):
        cls.owner = create_user(
            username='owner_user_file',
            user_permissions=('view_userfile', 'add_userfile', 'change_userfile', 'delete_userfile'),
        )
        cls.other = create_user(
            username='other_user_file',
            user_permissions=('view_userfile', 'change_userfile', 'delete_userfile'),
        )
        cls.upload_only = create_user(
            username='upload_only_user_file',
            user_permissions=('add_userfile',),
        )
        cls.superuser = create_user(
            username='superuser_user_file',
            is_superuser=True,
        )

        cls.private_file = UserFile.objects.create(
            user=cls.owner.profile,
            file='user_files/private.txt',
            filename='private.txt',
        )

        cls.request_factory = RequestFactory()

    @classmethod
    def _request_with_user(cls, user):
        request = cls.request_factory.get('/')
        request.user = user
        return request

    def test_private_file_owner_can_view(self):
        self.assertTrue(self.private_file.can_view_by(self.owner))

    def test_private_file_other_cannot_view(self):
        self.assertFalse(self.private_file.can_view_by(self.other))

    def test_private_file_anonymous_cannot_view(self):
        self.assertFalse(self.private_file.can_view_by(AnonymousUser()))

    def test_change_and_delete_require_ownership(self):
        self.assertTrue(self.private_file.can_change_by(self.owner))
        self.assertTrue(self.private_file.can_delete_by(self.owner))
        self.assertFalse(self.private_file.can_change_by(self.other))
        self.assertFalse(self.private_file.can_delete_by(self.other))

    def test_list_and_upload_permissions(self):
        self.assertTrue(UserFile.can_list_by(self.owner))
        self.assertFalse(UserFile.can_list_by(self.upload_only))
        self.assertTrue(UserFile.can_upload_by(self.upload_only))
        self.assertFalse(UserFile.can_upload_by(AnonymousUser()))

    def test_authorize_owner_can_access_private_file(self):
        request = self._request_with_user(self.owner)
        self.assertEqual(authorize_file_access(request, self.private_file), self.private_file)

    def test_authorize_superuser_can_access_private_file(self):
        request = self._request_with_user(self.superuser)
        self.assertEqual(authorize_file_access(request, self.private_file), self.private_file)

    def test_authorize_other_cannot_access_private_file(self):
        request = self._request_with_user(self.other)
        with self.assertRaises(Http404):
            authorize_file_access(request, self.private_file)

    def test_authorize_anonymous_cannot_access_private_file(self):
        request = self._request_with_user(AnonymousUser())
        with self.assertRaises(Http404):
            authorize_file_access(request, self.private_file)
