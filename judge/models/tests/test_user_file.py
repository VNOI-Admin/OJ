from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.test import RequestFactory, TestCase

from judge.models import FileUsage, UserFile
from judge.models.tests.util import create_contest, create_problem, create_user
from judge.utils.user_file_access import UserFileAccessChain


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

        cls.public_problem = create_problem(
            code='user_file_public_problem',
            authors=('owner_user_file',),
            is_public=True,
        )
        cls.private_problem = create_problem(
            code='user_file_private_problem',
            authors=('owner_user_file',),
            is_public=False,
        )

        cls.public_contest = create_contest(
            key='user_file_public_contest',
            authors=('owner_user_file',),
            is_visible=True,
            is_private=False,
        )
        cls.private_contest = create_contest(
            key='user_file_private_contest',
            authors=('owner_user_file',),
            is_visible=True,
            is_private=True,
            private_contestants=('other_user_file',),
        )

        cls.private_file = UserFile.objects.create(
            user=cls.owner.profile,
            file='user_files/private.txt',
            filename='private.txt',
            file_type='document',
            is_public=False,
        )
        cls.public_file = UserFile.objects.create(
            user=cls.owner.profile,
            file='user_files/public.txt',
            filename='public.txt',
            file_type='document',
            is_public=True,
        )

        cls.problem_scoped_file = UserFile.objects.create(
            user=cls.owner.profile,
            file='user_files/problem-scoped.png',
            filename='problem-scoped.png',
            file_type='image',
            storage_scope=UserFile.STORAGE_SCOPE_PROBLEM,
            is_public=False,
        )
        FileUsage.objects.create(
            file=cls.problem_scoped_file,
            usage_type='markdown_content',
            problem_id=cls.public_problem.id,
        )

        cls.contest_scoped_file = UserFile.objects.create(
            user=cls.owner.profile,
            file='user_files/contest-scoped.png',
            filename='contest-scoped.png',
            file_type='image',
            storage_scope=UserFile.STORAGE_SCOPE_CONTEST,
            is_public=False,
        )
        FileUsage.objects.create(
            file=cls.contest_scoped_file,
            usage_type='markdown_content',
            contest_id=cls.private_contest.id,
        )

        cls.access_chain = UserFileAccessChain()
        cls.request_factory = RequestFactory()

    @classmethod
    def _request_with_user(cls, user):
        request = cls.request_factory.get('/')
        request.user = user
        return request

    def test_private_file_requires_owner_and_view_permission(self):
        self.assertTrue(self.private_file.can_view_by(self.owner))
        self.assertFalse(self.private_file.can_view_by(self.other))
        self.assertFalse(self.private_file.can_view_by(AnonymousUser()))

    def test_public_file_can_be_viewed_without_permission(self):
        self.assertTrue(self.public_file.can_view_by(self.other))
        self.assertTrue(self.public_file.can_view_by(AnonymousUser()))

    def test_change_and_delete_require_owner_permission(self):
        self.assertTrue(self.private_file.can_change_by(self.owner))
        self.assertTrue(self.private_file.can_delete_by(self.owner))
        self.assertFalse(self.private_file.can_change_by(self.other))
        self.assertFalse(self.private_file.can_delete_by(self.other))

    def test_list_and_upload_permissions(self):
        self.assertTrue(UserFile.can_list_by(self.owner))
        self.assertFalse(UserFile.can_list_by(self.upload_only))
        self.assertTrue(UserFile.can_upload_by(self.upload_only))
        self.assertFalse(UserFile.can_upload_by(AnonymousUser()))

    def test_scoped_problem_file_requires_authentication(self):
        request = self._request_with_user(AnonymousUser())
        with self.assertRaises(Http404):
            self.access_chain.authorize(request, self.problem_scoped_file)

    def test_scoped_problem_file_checks_problem_access(self):
        request = self._request_with_user(self.other)
        self.assertEqual(
            self.access_chain.authorize(request, self.problem_scoped_file),
            self.problem_scoped_file,
        )

    def test_scoped_contest_file_checks_contest_access(self):
        allowed_request = self._request_with_user(self.other)
        denied_request = self._request_with_user(self.upload_only)

        self.assertEqual(
            self.access_chain.authorize(allowed_request, self.contest_scoped_file),
            self.contest_scoped_file,
        )
        with self.assertRaises(Http404):
            self.access_chain.authorize(denied_request, self.contest_scoped_file)
