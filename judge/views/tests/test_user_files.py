from datetime import timedelta
from unittest.mock import patch

from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from judge.models import FileAttachment, UserFile
from judge.models.tests.util import create_contest, create_problem, create_user

_MOCK_SERVE = patch('judge.views.user_files.serve_user_file', return_value=HttpResponse('ok'))


class UserFileViewsTestCase(TestCase):
    fixtures = ['language_all.json']

    @classmethod
    def setUpTestData(cls):
        cls.owner = create_user('owner_uf')
        cls.other = create_user('other_uf')
        cls.superuser = create_user('super_uf', is_superuser=True)

        cls.owner_file = UserFile.objects.create(
            user=cls.owner.profile,
            file='user_file/test.txt',
            filename='test.txt',
            file_scope=UserFile.FileScope.ATTACHMENT,
        )

    # --- List view ---

    def test_list_owner(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('user_file_list', args=[self.owner.username]))
        self.assertEqual(response.status_code, 200)

    def test_list_other_forbidden(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse('user_file_list', args=[self.owner.username]))
        self.assertEqual(response.status_code, 403)

    def test_list_superuser(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('user_file_list', args=[self.owner.username]))
        self.assertEqual(response.status_code, 200)

    def test_list_anonymous_redirects(self):
        response = self.client.get(reverse('user_file_list', args=[self.owner.username]))
        self.assertEqual(response.status_code, 302)

    # --- Detail view ---

    def test_detail_owner(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('user_file_detail', args=[self.owner_file.uuid]))
        self.assertEqual(response.status_code, 200)

    def test_detail_other_not_found(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse('user_file_detail', args=[self.owner_file.uuid]))
        self.assertEqual(response.status_code, 404)

    def test_detail_superuser(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('user_file_detail', args=[self.owner_file.uuid]))
        self.assertEqual(response.status_code, 200)

    def test_detail_anonymous_redirects(self):
        response = self.client.get(reverse('user_file_detail', args=[self.owner_file.uuid]))
        self.assertEqual(response.status_code, 302)

    # --- Delete view ---

    def test_delete_owner_removes_file(self):
        file_to_delete = UserFile.objects.create(
            user=self.owner.profile,
            file='user_file/to_delete.txt',
            filename='to_delete.txt',
            file_scope=UserFile.FileScope.ATTACHMENT,
        )
        self.client.force_login(self.owner)
        response = self.client.post(reverse('user_file_delete'), {'uuids': [str(file_to_delete.uuid)]})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(UserFile.objects.filter(uuid=file_to_delete.uuid).exists())

    def test_delete_other_cannot_delete_owners_file(self):
        self.client.force_login(self.other)
        self.client.post(reverse('user_file_delete'), {'uuids': [str(self.owner_file.uuid)]})
        self.assertTrue(UserFile.objects.filter(uuid=self.owner_file.uuid).exists())

    def test_delete_anonymous_redirects(self):
        response = self.client.post(reverse('user_file_delete'), {'uuids': [str(self.owner_file.uuid)]})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(UserFile.objects.filter(uuid=self.owner_file.uuid).exists())

    def test_delete_empty_uuids_shows_error(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('user_file_delete'), {})
        self.assertEqual(response.status_code, 302)

    # --- Access (serve) view ---

    @_MOCK_SERVE
    def test_access_owner(self, _mock):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('user_file_access', args=[self.owner_file.uuid]))
        self.assertEqual(response.status_code, 200)

    @_MOCK_SERVE
    def test_access_other_not_found(self, _mock):
        self.client.force_login(self.other)
        response = self.client.get(reverse('user_file_access', args=[self.owner_file.uuid]))
        self.assertEqual(response.status_code, 404)

    @_MOCK_SERVE
    def test_access_anonymous_redirects(self, _mock):
        response = self.client.get(reverse('user_file_access', args=[self.owner_file.uuid]))
        self.assertEqual(response.status_code, 302)


class AttachmentAccessViewTestCase(TestCase):
    fixtures = ['language_all.json']

    @classmethod
    def setUpTestData(cls):
        _now = timezone.now()

        cls.normal = create_user('normal_att')
        cls.author = create_user('author_att', user_permissions=('edit_own_contest',))

        cls.public_problem = create_problem(code='pub_att', is_public=True)
        cls.private_problem = create_problem(code='priv_att', authors=('author_att',))

        cls.public_contest = create_contest(
            key='pub_contest_att',
            is_visible=True,
            start_time=_now - timedelta(hours=1),
            end_time=_now + timedelta(hours=1),
            authors=('author_att',),
        )

        shared_file = UserFile.objects.create(
            user=cls.author.profile,
            file='user_file/att.txt',
            filename='att.txt',
            file_scope=UserFile.FileScope.ATTACHMENT,
        )

        cls.pub_problem_att = FileAttachment.objects.create(
            linked_item=cls.public_problem,
            file=shared_file,
        )
        cls.priv_problem_att = FileAttachment.objects.create(
            linked_item=cls.private_problem,
            file=shared_file,
        )
        cls.pub_contest_att = FileAttachment.objects.create(
            linked_item=cls.public_contest,
            file=shared_file,
        )

    def _url(self, attachment):
        return reverse('attachment_access', args=[attachment.pk])

    # --- Problem attachments ---

    @_MOCK_SERVE
    def test_public_problem_normal_user(self, _mock):
        self.client.force_login(self.normal)
        self.assertEqual(self.client.get(self._url(self.pub_problem_att)).status_code, 200)

    @_MOCK_SERVE
    def test_public_problem_anonymous(self, _mock):
        self.assertEqual(self.client.get(self._url(self.pub_problem_att)).status_code, 200)

    @_MOCK_SERVE
    def test_private_problem_author(self, _mock):
        self.client.force_login(self.author)
        self.assertEqual(self.client.get(self._url(self.priv_problem_att)).status_code, 200)

    def test_private_problem_normal_user(self):
        self.client.force_login(self.normal)
        self.assertEqual(self.client.get(self._url(self.priv_problem_att)).status_code, 404)

    def test_private_problem_anonymous(self):
        self.assertEqual(self.client.get(self._url(self.priv_problem_att)).status_code, 404)

    # --- Contest attachments ---

    @_MOCK_SERVE
    def test_contest_author_can_view(self, _mock):
        # Author is editable_by, so can_view_attachment_by returns True
        self.client.force_login(self.author)
        self.assertEqual(self.client.get(self._url(self.pub_contest_att)).status_code, 200)

    def test_contest_normal_user_not_in_contest(self):
        # Normal user is not in the contest and not an editor
        self.client.force_login(self.normal)
        self.assertEqual(self.client.get(self._url(self.pub_contest_att)).status_code, 404)
