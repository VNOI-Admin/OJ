import datetime

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from judge.models import Organization, ProblemData
from judge.models.profile import OrganizationQuota
from judge.models.tests.util import CommonDataMixin, create_organization, create_problem


class OrganizationQuotaTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls._org_pk = cls.organizations['open'].pk

    def setUp(self):
        # Fresh instance per test so cached_property values don't bleed between tests.
        self.org = Organization.objects.get(pk=self._org_pk)

    def _today(self):
        return timezone.now().date()

    def _make_quota(self, added_problems=0, added_storage=0, start_offset=0, end_offset=30):
        """Create an OrganizationQuota relative to today. end_offset=30 by default (active)."""
        today = self._today()
        return OrganizationQuota.objects.create(
            organization=self.org,
            start_date=today + datetime.timedelta(days=start_offset),
            end_date=today + datetime.timedelta(days=end_offset),
            added_problems=added_problems,
            added_storage=added_storage,
        )

    # ---- max_problems ----

    def test_get_max_problems_default_no_quotas(self):
        """With no quota records, returns the settings default."""
        self.assertEqual(
            self.org.max_problems,
            settings.VNOJ_ORGANIZATION_DEFAULT_MAX_PROBLEMS,
        )

    @override_settings(VNOJ_ORGANIZATION_DEFAULT_MAX_PROBLEMS=1000)
    def test_get_max_problems_single_active_quota(self):
        """Active quota adds to the default."""
        self._make_quota(added_problems=500)
        self.assertEqual(self.org.max_problems, 1500)

    @override_settings(VNOJ_ORGANIZATION_DEFAULT_MAX_PROBLEMS=1000)
    def test_get_max_problems_multiple_active_quotas_summed(self):
        """Multiple active quotas are summed."""
        self._make_quota(added_problems=200)
        self._make_quota(added_problems=300)
        self.assertEqual(self.org.max_problems, 1500)

    @override_settings(VNOJ_ORGANIZATION_DEFAULT_MAX_PROBLEMS=1000)
    def test_get_max_problems_expired_quota_excluded(self):
        """Expired quota (end_date < today) is not counted."""
        self._make_quota(added_problems=500, end_offset=-1)
        self.assertEqual(self.org.max_problems, 1000)

    @override_settings(VNOJ_ORGANIZATION_DEFAULT_MAX_PROBLEMS=1000)
    def test_get_max_problems_future_quota_excluded(self):
        """Quota with start_date in the future is not counted."""
        self._make_quota(added_problems=500, start_offset=1)
        self.assertEqual(self.org.max_problems, 1000)

    @override_settings(VNOJ_ORGANIZATION_DEFAULT_MAX_PROBLEMS=1000)
    def test_get_max_problems_quota_expiring_today_is_active(self):
        """Quota whose end_date == today is still active (end_date >= today)."""
        self._make_quota(added_problems=500, end_offset=0)
        self.assertEqual(self.org.max_problems, 1500)

    # ---- max_storage ----

    def test_get_max_storage_default_no_quotas(self):
        """With no quota records, returns the settings default."""
        self.assertEqual(
            self.org.max_storage,
            settings.VNOJ_ORGANIZATION_DEFAULT_MAX_STORAGE,
        )

    @override_settings(VNOJ_ORGANIZATION_DEFAULT_MAX_STORAGE=5 * 1024 * 1024 * 1024)
    def test_get_max_storage_single_active_quota(self):
        """Active quota adds to default storage."""
        self._make_quota(added_storage=1024)
        self.assertEqual(self.org.max_storage, 5 * 1024 * 1024 * 1024 + 1024)

    @override_settings(VNOJ_ORGANIZATION_DEFAULT_MAX_STORAGE=5 * 1024 * 1024 * 1024)
    def test_get_max_storage_multiple_active_quotas_summed(self):
        """Multiple active storage quotas are summed."""
        self._make_quota(added_storage=1024)
        self._make_quota(added_storage=2048)
        self.assertEqual(self.org.max_storage, 5 * 1024 * 1024 * 1024 + 3072)

    @override_settings(VNOJ_ORGANIZATION_DEFAULT_MAX_STORAGE=5 * 1024 * 1024 * 1024)
    def test_get_max_storage_expired_quota_excluded(self):
        """Expired storage quota is not counted."""
        self._make_quota(added_storage=10 * 1024 * 1024 * 1024, end_offset=-1)
        self.assertEqual(self.org.max_storage, 5 * 1024 * 1024 * 1024)

    # ---- can_create_problem ----

    def test_can_create_problem_under_limit(self):
        """Org with 0 problems and no quota grants should allow creation."""
        self.assertTrue(self.org.can_create_problem())

    @override_settings(VNOJ_ORGANIZATION_DEFAULT_MAX_PROBLEMS=2)
    def test_can_create_problem_at_default_limit(self):
        """Org at the default limit should block creation."""
        create_problem(code='quota_test_1', organization=self.org, is_organization_private=True)
        create_problem(code='quota_test_2', organization=self.org, is_organization_private=True)
        self.assertFalse(self.org.can_create_problem())

    @override_settings(VNOJ_ORGANIZATION_DEFAULT_MAX_PROBLEMS=2)
    def test_can_create_problem_active_quota_extends_limit(self):
        """Active quota grant raises the effective limit."""
        self._make_quota(added_problems=1)  # limit becomes 3
        create_problem(code='quota_test_3', organization=self.org, is_organization_private=True)
        create_problem(code='quota_test_4', organization=self.org, is_organization_private=True)
        self.assertTrue(self.org.can_create_problem())  # 2 problems, limit is 3

    @override_settings(VNOJ_ORGANIZATION_DEFAULT_MAX_PROBLEMS=2)
    def test_can_create_problem_expired_quota_does_not_extend_limit(self):
        """Expired quota grant does not raise the effective limit."""
        self._make_quota(added_problems=100, end_offset=-1)
        create_problem(code='quota_test_5', organization=self.org, is_organization_private=True)
        create_problem(code='quota_test_6', organization=self.org, is_organization_private=True)
        self.assertFalse(self.org.can_create_problem())

    @override_settings(VNOJ_ORGANIZATION_DEFAULT_MAX_PROBLEMS=1)
    def test_can_create_problem_ignores_deleted_problems(self):
        """Deleted problems should not count against the problem quota."""
        problem = create_problem(code='quota_deleted_1', organization=self.org, is_organization_private=True)
        problem.mark_as_deleted()
        self.assertTrue(self.org.can_create_problem())

    # ---- can_upload_data ----

    def test_can_upload_data_under_limit(self):
        """Org with no data should allow upload."""
        self.assertTrue(self.org.can_upload_data())

    def test_can_upload_data_at_limit(self):
        """Org at or above storage limit should block upload."""
        problem = create_problem(code='storage_test_1', organization=self.org, is_organization_private=True)
        ProblemData.objects.get_or_create(problem=problem)
        ProblemData.objects.filter(problem=problem).update(
            zipfile_size=settings.VNOJ_ORGANIZATION_DEFAULT_MAX_STORAGE,
        )
        self.assertFalse(self.org.can_upload_data())

    def test_can_upload_data_active_quota_extends_limit(self):
        """Active storage quota raises the effective storage limit."""
        problem = create_problem(code='storage_test_2', organization=self.org, is_organization_private=True)
        ProblemData.objects.get_or_create(problem=problem)
        ProblemData.objects.filter(problem=problem).update(
            zipfile_size=settings.VNOJ_ORGANIZATION_DEFAULT_MAX_STORAGE,
        )
        self._make_quota(added_storage=1024)
        self.assertTrue(self.org.can_upload_data())

    def test_can_upload_data_expired_quota_does_not_extend_limit(self):
        """Expired storage quota does not raise the effective limit."""
        problem = create_problem(code='storage_test_3', organization=self.org, is_organization_private=True)
        ProblemData.objects.get_or_create(problem=problem)
        ProblemData.objects.filter(problem=problem).update(
            zipfile_size=settings.VNOJ_ORGANIZATION_DEFAULT_MAX_STORAGE,
        )
        self._make_quota(added_storage=10 * 1024 * 1024 * 1024, end_offset=-1)
        self.assertFalse(self.org.can_upload_data())

    def test_can_upload_data_ignores_deleted_problems(self):
        """Deleted problems' storage should not count against the storage quota."""
        problem = create_problem(code='storage_deleted_1', organization=self.org, is_organization_private=True)
        ProblemData.objects.get_or_create(problem=problem)
        ProblemData.objects.filter(problem=problem).update(
            zipfile_size=settings.VNOJ_ORGANIZATION_DEFAULT_MAX_STORAGE,
        )
        problem.mark_as_deleted()
        self.assertTrue(self.org.can_upload_data())

    # ---- current_problem_count / current_storage ----

    def test_get_current_problem_count(self):
        """Should count only problems belonging to this org."""
        org2 = create_organization(name='other_org')
        create_problem(code='org1_p1', organization=self.org, is_organization_private=True)
        create_problem(code='org2_p1', organization=org2, is_organization_private=True)
        create_problem(code='no_org_p1')
        self.assertEqual(self.org.current_problem_count, 1)

    def test_get_current_storage(self):
        """Should sum zipfile_size only for this org's problems."""
        org2 = create_organization(name='storage_other_org')
        p1 = create_problem(code='st_org1', organization=self.org, is_organization_private=True)
        p2 = create_problem(code='st_org2', organization=org2, is_organization_private=True)
        ProblemData.objects.get_or_create(problem=p1)
        ProblemData.objects.filter(problem=p1).update(zipfile_size=500)
        ProblemData.objects.get_or_create(problem=p2)
        ProblemData.objects.filter(problem=p2).update(zipfile_size=300)
        self.assertEqual(self.org.current_storage, 500)
