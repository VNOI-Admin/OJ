import datetime

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from judge.models import ProblemData
from judge.models.tests.util import CommonDataMixin, create_organization, create_problem


class OrganizationQuotaTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.org = cls.organizations['open']

    def test_get_max_problems_default(self):
        """When max_problems is None, should return setting."""
        self.org.max_problems = None
        self.assertEqual(
            self.org.get_max_problems(),
            settings.VNOJ_ORGANIZATION_DEFAULT_MAX_PROBLEMS,
        )

    def test_get_max_problems_override(self):
        """When max_problems is set, should return that value."""
        self.org.max_problems = 500
        self.assertEqual(self.org.get_max_problems(), 500)

    def test_get_max_storage_default(self):
        """When max_storage is None, should return setting."""
        self.org.max_storage = None
        self.assertEqual(
            self.org.get_max_storage(),
            settings.VNOJ_ORGANIZATION_DEFAULT_MAX_STORAGE,
        )

    def test_get_max_storage_override(self):
        """When max_storage is set, should return that value."""
        self.org.max_storage = 1024
        self.assertEqual(self.org.get_max_storage(), 1024)

    def test_can_create_problem_under_limit(self):
        """Org with 0 problems and max_problems=1000 should allow creation."""
        self.org.max_problems = None
        self.assertTrue(self.org.can_create_problem())

    @override_settings(VNOJ_ORGANIZATION_DEFAULT_MAX_PROBLEMS=2)
    def test_can_create_problem_at_limit(self):
        """Org at problem limit should block creation."""
        self.org.max_problems = None
        create_problem(code='quota_test_1', organization=self.org, is_organization_private=True)
        create_problem(code='quota_test_2', organization=self.org, is_organization_private=True)
        self.assertFalse(self.org.can_create_problem())

    @override_settings(VNOJ_ORGANIZATION_DEFAULT_MAX_PROBLEMS=2)
    def test_can_create_problem_below_limit(self):
        """Org below limit should allow creation."""
        self.org.max_problems = None
        create_problem(code='quota_test_3', organization=self.org, is_organization_private=True)
        self.assertTrue(self.org.can_create_problem())

    def test_can_create_problem_per_org_override(self):
        """Per-org max_problems override should take precedence."""
        self.org.max_problems = 1
        create_problem(code='quota_test_4', organization=self.org, is_organization_private=True)
        self.assertFalse(self.org.can_create_problem())

    def test_can_upload_data_under_limit(self):
        """Org with no data should allow upload."""
        self.org.max_storage = None
        self.assertTrue(self.org.can_upload_data())

    def test_can_upload_data_at_limit(self):
        """Org at storage limit should block upload."""
        self.org.max_storage = 100
        problem = create_problem(code='storage_test_1', organization=self.org, is_organization_private=True)
        ProblemData.objects.get_or_create(problem=problem)
        ProblemData.objects.filter(problem=problem).update(zipfile_size=101)
        self.assertFalse(self.org.can_upload_data())

    def test_can_upload_data_exactly_at_limit(self):
        """Org exactly at storage limit should still allow (<=)."""
        self.org.max_storage = 100
        problem = create_problem(code='storage_test_2', organization=self.org, is_organization_private=True)
        ProblemData.objects.get_or_create(problem=problem)
        ProblemData.objects.filter(problem=problem).update(zipfile_size=100)
        self.assertTrue(self.org.can_upload_data())

    def test_get_current_problem_count(self):
        """Should count only problems belonging to this org."""
        org2 = create_organization(name='other_org')
        create_problem(code='org1_p1', organization=self.org, is_organization_private=True)
        create_problem(code='org2_p1', organization=org2, is_organization_private=True)
        create_problem(code='no_org_p1')
        self.assertEqual(self.org.get_current_problem_count(), 1)

    def test_get_current_storage(self):
        """Should sum zipfile_size only for this org's problems."""
        org2 = create_organization(name='storage_other_org')
        p1 = create_problem(code='st_org1', organization=self.org, is_organization_private=True)
        p2 = create_problem(code='st_org2', organization=org2, is_organization_private=True)

        ProblemData.objects.get_or_create(problem=p1)
        ProblemData.objects.filter(problem=p1).update(zipfile_size=500)

        ProblemData.objects.get_or_create(problem=p2)
        ProblemData.objects.filter(problem=p2).update(zipfile_size=300)

        self.assertEqual(self.org.get_current_storage(), 500)


class StorageExpirationTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.org = cls.organizations['open']

    def _today(self):
        return timezone.now().date()

    def test_is_storage_expired_when_none(self):
        """storage_expiration=None → not expired (org has no set expiry)."""
        self.org.storage_expiration = None
        self.assertFalse(self.org.is_storage_expired())

    def test_is_storage_expired_with_past_date(self):
        """storage_expiration = yesterday → expired."""
        self.org.storage_expiration = self._today() - datetime.timedelta(days=1)
        self.assertTrue(self.org.is_storage_expired())

    def test_is_storage_expired_on_expiry_day(self):
        """storage_expiration = today → not yet expired (< today, not <=)."""
        self.org.storage_expiration = self._today()
        self.assertFalse(self.org.is_storage_expired())

    def test_is_storage_expired_with_future_date(self):
        """storage_expiration = tomorrow → not expired."""
        self.org.storage_expiration = self._today() + datetime.timedelta(days=1)
        self.assertFalse(self.org.is_storage_expired())

    def test_can_create_problem_blocked_when_expired(self):
        """Expired org is blocked from creating problems even when under quota."""
        self.org.max_problems = 1000
        self.org.storage_expiration = self._today() - datetime.timedelta(days=1)
        self.assertFalse(self.org.can_create_problem())

    def test_can_create_problem_allowed_when_not_expired(self):
        """Non-expired org with room under quota can create problems."""
        self.org.max_problems = 1000
        self.org.storage_expiration = self._today() + datetime.timedelta(days=1)
        self.assertTrue(self.org.can_create_problem())

    def test_can_upload_data_blocked_when_expired(self):
        """Expired org cannot upload data even when under storage quota."""
        self.org.max_storage = 10 * 1024 * 1024 * 1024  # 10 GB
        self.org.storage_expiration = self._today() - datetime.timedelta(days=1)
        self.assertFalse(self.org.can_upload_data())

    def test_can_upload_data_allowed_when_not_expired(self):
        """Non-expired org under storage limit can upload data."""
        self.org.max_storage = 10 * 1024 * 1024 * 1024
        self.org.storage_expiration = self._today() + datetime.timedelta(days=1)
        self.assertTrue(self.org.can_upload_data())

    @override_settings(VNOJ_ORGANIZATION_DEFAULT_STORAGE_EXPIRATION_DAYS=365)
    def test_default_expiration_days_not_expired(self):
        """Org with expiration = today + default days should not be expired."""
        self.org.storage_expiration = (
            self._today() +
            datetime.timedelta(days=settings.VNOJ_ORGANIZATION_DEFAULT_STORAGE_EXPIRATION_DAYS)
        )
        self.assertFalse(self.org.is_storage_expired())

    @override_settings(VNOJ_ORGANIZATION_DEFAULT_MAX_STORAGE=5 * 1024 * 1024 * 1024)
    def test_get_max_storage_resets_when_expired(self):
        """Expired org should return default max_storage, ignoring custom override."""
        self.org.max_storage = 50 * 1024 * 1024 * 1024  # 50GB custom
        self.org.storage_expiration = self._today() - datetime.timedelta(days=1)
        self.assertEqual(self.org.get_max_storage(), settings.VNOJ_ORGANIZATION_DEFAULT_MAX_STORAGE)

    def test_get_max_storage_keeps_override_when_not_expired(self):
        """Non-expired org should keep its custom max_storage."""
        self.org.max_storage = 50 * 1024 * 1024 * 1024
        self.org.storage_expiration = self._today() + datetime.timedelta(days=30)
        self.assertEqual(self.org.get_max_storage(), 50 * 1024 * 1024 * 1024)

    def test_get_days_remaining_with_future_date(self):
        """Should return positive days when not expired."""
        self.org.storage_expiration = self._today() + datetime.timedelta(days=30)
        self.assertEqual(self.org.get_days_remaining(), 30)

    def test_get_days_remaining_with_past_date(self):
        """Should return 0 when expired."""
        self.org.storage_expiration = self._today() - datetime.timedelta(days=5)
        self.assertEqual(self.org.get_days_remaining(), 0)

    def test_get_days_remaining_when_none(self):
        """Should return None when no expiration is set."""
        self.org.storage_expiration = None
        self.assertIsNone(self.org.get_days_remaining())

    def test_get_days_remaining_on_expiry_day(self):
        """Should return 0 on the expiry day itself."""
        self.org.storage_expiration = self._today()
        self.assertEqual(self.org.get_days_remaining(), 0)
