from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from judge.models import UserUpload
from judge.models.tests.util import create_user


class UserUploadPermissionTest(TestCase):
    fixtures = ['language_all.json']

    @classmethod
    def setUpTestData(cls):
        cls.owner = create_user(
            username='owner_user_upload',
            user_permissions=('view_userupload', 'add_userupload', 'change_userupload', 'delete_userupload'),
        )
        cls.other = create_user(
            username='other_user_upload',
            user_permissions=('view_userupload', 'change_userupload', 'delete_userupload'),
        )
        cls.upload_only = create_user(
            username='upload_only_user_upload',
            user_permissions=('add_userupload',),
        )
        cls.superuser = create_user(
            username='superuser_user_upload',
            is_superuser=True,
        )

        cls.private_file = UserUpload.objects.create(
            user=cls.owner.profile,
            file='user_uploads/private.txt',
            filename='private.txt',
        )

    def test_private_file_owner_can_view(self):
        self.assertTrue(self.private_file.is_accessible_by(self.owner))

    def test_private_file_superuser_can_view(self):
        self.assertTrue(self.private_file.is_accessible_by(self.superuser))

    def test_private_file_other_cannot_view(self):
        self.assertFalse(self.private_file.is_accessible_by(self.other))

    def test_private_file_anonymous_cannot_view(self):
        self.assertFalse(self.private_file.is_accessible_by(AnonymousUser()))

    def test_change_and_delete_require_ownership(self):
        self.assertTrue(self.private_file.can_change_by(self.owner))
        self.assertTrue(self.private_file.can_delete_by(self.owner))
        self.assertFalse(self.private_file.can_change_by(self.other))
        self.assertFalse(self.private_file.can_delete_by(self.other))

    def test_upload_permissions(self):
        self.assertTrue(UserUpload.can_upload_by(self.upload_only))
        self.assertFalse(UserUpload.can_upload_by(AnonymousUser()))
