from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from judge.models import Organization, Problem
from judge.models.tests.util import CommonDataMixin, create_problem
from judge.utils.problem_archive import ArchiveServiceError


class OrganizationArchivedProblemsTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls._org_pk = cls.organizations['open'].pk
        org = cls.organizations['open']

        cls.archived = create_problem(
            code='archived_problem',
            organization=org,
            is_organization_private=True,
            archived_at=timezone.now(),
            authors=('staff_problem_edit_all',),
        )
        cls.live = create_problem(
            code='live_problem',
            organization=org,
            is_organization_private=True,
            authors=('staff_problem_edit_all',),
        )

    def setUp(self):
        # OrganizationMixin.organization and Organization.admins_list are cached properties,
        # so start every test from a freshly fetched organization.
        self.organization = Organization.objects.get(pk=self._org_pk)

    def _url(self):
        return reverse('organization_archived_problems', args=[self.organization.slug])

    def test_lists_only_archived_problems(self):
        self.client.force_login(self.users['staff_organization_admin'])
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        codes = [problem.code for problem in response.context['problems']]
        self.assertEqual(codes, ['archived_problem'])

    def test_excludes_soft_deleted_problems(self):
        Problem.objects.filter(pk=self.archived.pk).update(deleted_at=timezone.now())
        self.client.force_login(self.users['staff_organization_admin'])
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['problems']), [])

    def test_download_link_is_shown_when_the_archive_service_is_configured(self):
        self.client.force_login(self.users['staff_organization_admin'])
        with mock.patch('judge.views.organization.ARCHIVE_DOWNLOAD_ENABLED', True):
            response = self.client.get(self._url())
        self.assertContains(response, reverse('problem_download_archived_data', args=['archived_problem']))

    def test_download_link_is_disabled_when_the_archive_service_is_not_configured(self):
        self.client.force_login(self.users['staff_organization_admin'])
        with mock.patch('judge.views.organization.ARCHIVE_DOWNLOAD_ENABLED', False):
            response = self.client.get(self._url())
        self.assertNotContains(response, reverse('problem_download_archived_data', args=['archived_problem']))
        self.assertContains(response, 'btn-archive-disabled')

    def test_non_admin_is_forbidden(self):
        self.client.force_login(self.users['normal'])
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)

    def test_storage_tab_still_renders_and_keeps_archived_problems(self):
        # The storage table shares its markup with the archived tab and still lists archived problems.
        self.client.force_login(self.users['staff_organization_admin'])
        response = self.client.get(reverse('organization_monthly_usage', args=[self.organization.slug]))
        self.assertEqual(response.status_code, 200)
        codes = sorted(problem.code for problem in response.context['problems'])
        self.assertEqual(codes, ['archived_problem', 'live_problem'])
        # The storage tab renders the non-archived variant of the shared table.
        self.assertContains(response, reverse('problem_download_full_package', args=['archived_problem']))
        self.assertNotContains(response, reverse('problem_download_archived_data', args=['archived_problem']))


class BulkDeleteNextUrlTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls._org_pk = cls.organizations['open'].pk

    def setUp(self):
        self.organization = Organization.objects.get(pk=self._org_pk)
        self.client.force_login(self.users['staff_organization_admin'])

    def _url(self):
        return reverse('organization_problems_bulk_delete', args=[self.organization.slug])

    def test_honours_same_host_next(self):
        archived_url = reverse('organization_archived_problems', args=[self.organization.slug])
        response = self.client.post(self._url(), {'next': archived_url})
        self.assertRedirects(response, archived_url)

    def test_ignores_off_host_next(self):
        response = self.client.post(self._url(), {'next': 'https://evil.example.com/'})
        self.assertRedirects(
            response,
            reverse('organization_monthly_usage', args=[self.organization.slug]),
        )


class DownloadArchivedProblemDataTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        org = cls.organizations['open']
        cls.archived = create_problem(
            code='archived_download',
            organization=org,
            is_organization_private=True,
            archived_at=timezone.now(),
        )
        cls.live = create_problem(
            code='live_download',
            organization=org,
            is_organization_private=True,
        )

    def setUp(self):
        self.client.force_login(self.users['superuser'])

    def _url(self, problem):
        return reverse('problem_download_archived_data', args=[problem.code])

    def test_404_for_problem_that_is_not_archived(self):
        response = self.client.get(self._url(self.live))
        self.assertEqual(response.status_code, 404)

    def test_redirects_to_presigned_url(self):
        with mock.patch('judge.views.problem_download.get_archive_download_url',
                        return_value='https://s3.example.com/archived_download.zip?sig=abc') as get_url:
            response = self.client.get(self._url(self.archived))
        get_url.assert_called_once_with('archived_download')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://s3.example.com/archived_download.zip?sig=abc')

    def test_redirects_back_when_the_service_fails(self):
        with mock.patch('judge.views.problem_download.get_archive_download_url',
                        side_effect=ArchiveServiceError('boom')):
            response = self.client.get(self._url(self.archived))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('problem_detail', args=[self.archived.code]))
