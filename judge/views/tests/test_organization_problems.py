import datetime
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from judge.models import Submission, Language
from judge.models.tests.util import CommonDataMixin, create_user, create_organization, create_problem


class OrganizationProblemsTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        # Create additional admin and members for testing
        cls.users.update({
            'org_admin_2': create_user(username='org_admin_2'),
            'org_member': create_user(username='org_member'),
            'other_admin': create_user(username='other_admin'),
        })

        # Set up organization and membership
        cls.org = cls.organizations['open']
        cls.org.admins.add(cls.users['staff_organization_admin'].profile)
        cls.org.admins.add(cls.users['org_admin_2'].profile)
        cls.org.members.add(cls.users['org_member'].profile)

        # Create problems for this organization
        cls.prob1 = create_problem(code='prob1', organization=cls.org, is_public=True)
        cls.prob1.authors.add(cls.users['staff_organization_admin'].profile)

        cls.prob2 = create_problem(code='prob2', organization=cls.org, is_public=True)
        cls.prob2.authors.add(cls.users['org_admin_2'].profile)

        cls.prob3 = create_problem(code='prob3', organization=cls.org, is_public=True)
        cls.prob3.authors.add(cls.users['org_member'].profile)

        # Create problem for another organization to check isolation
        cls.other_org = create_organization(name='other_org')
        cls.other_org.admins.add(cls.users['other_admin'].profile)
        cls.other_prob = create_problem(code='other_prob', organization=cls.other_org, is_public=True)

        # Create submissions with dates
        # prob1 has a submission 5 days ago
        cls.sub1 = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.prob1,
            language=Language.get_python3(),
            result='AC',
            status='D',
        )
        # Manually force the date to 5 days ago
        Submission.objects.filter(id=cls.sub1.id).update(date=timezone.now() - datetime.timedelta(days=5))

        # prob2 has a submission 2 days ago
        cls.sub2 = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.prob2,
            language=Language.get_python3(),
            result='WA',
            status='D',
        )
        Submission.objects.filter(id=cls.sub2.id).update(date=timezone.now() - datetime.timedelta(days=2))

        # prob3 has no submission

    def test_author_dropdown_only_org_admins(self):
        """Verify org_admins context only contains admins of the organization."""
        self.client.force_login(self.users['staff_organization_admin'])
        response = self.client.get(reverse('organization_monthly_usage', args=[self.org.slug]))
        self.assertEqual(response.status_code, 200)

        admins_in_context = response.context['org_admins']
        admin_profiles = [p.user.username for p in admins_in_context]

        # Should contain staff_organization_admin and org_admin_2, but not org_member
        self.assertIn('staff_organization_admin', admin_profiles)
        self.assertIn('org_admin_2', admin_profiles)
        self.assertNotIn('org_member', admin_profiles)

    def test_filter_by_author(self):
        """Tạo problems với authors khác nhau, filter → chỉ problems đúng author."""
        self.client.force_login(self.users['staff_organization_admin'])
        # Filter for prob1's author
        author_id = self.users['staff_organization_admin'].profile.id
        response = self.client.get(reverse('organization_monthly_usage', args=[self.org.slug]), {'author': author_id})
        self.assertEqual(response.status_code, 200)
        problems = response.context['problems']
        self.assertEqual(len(problems), 1)
        self.assertIn(self.prob1, problems)

    def test_filter_by_author_rejects_non_admin(self):
        """Filter bằng user ID không phải admin → bị ignore và trả về tất cả."""
        self.client.force_login(self.users['staff_organization_admin'])
        # org_member is not an admin
        non_admin_id = self.users['org_member'].profile.id
        response = self.client.get(
            reverse('organization_monthly_usage', args=[self.org.slug]),
            {'author': non_admin_id}
        )
        self.assertEqual(response.status_code, 200)
        # If ignore, it should return all 3 problems of this org
        problems = response.context['problems']
        self.assertEqual(len(problems), 3)

    def test_filter_last_submission_after(self):
        """Submissions ở ngày khác nhau, filter after → đúng."""
        self.client.force_login(self.users['staff_organization_admin'])
        # Date 3 days ago (prob2 is 2 days ago, prob1 is 5 days ago, prob3 has none)
        date_str = (timezone.now() - datetime.timedelta(days=3)).strftime('%Y-%m-%d')
        response = self.client.get(reverse('organization_monthly_usage', args=[self.org.slug]), {
            'last_sub_after': date_str
        })
        self.assertEqual(response.status_code, 200)
        problems = list(response.context['problems'])
        # Only prob2 has submission within the last 3 days
        self.assertEqual(len(problems), 1)
        self.assertIn(self.prob2, problems)

    def test_filter_last_submission_before(self):
        """Filter before → đúng."""
        self.client.force_login(self.users['staff_organization_admin'])
        # Date 3 days ago (prob1 is 5 days ago, prob2 is 2 days ago)
        date_str = (timezone.now() - datetime.timedelta(days=3)).strftime('%Y-%m-%d')
        response = self.client.get(reverse('organization_monthly_usage', args=[self.org.slug]), {
            'last_sub_before': date_str
        })
        self.assertEqual(response.status_code, 200)
        problems = list(response.context['problems'])
        # prob1 is 5 days ago
        self.assertEqual(len(problems), 1)
        self.assertIn(self.prob1, problems)

    def test_filter_last_submission_combined(self):
        """Filter cả after + before (range) → đúng."""
        self.client.force_login(self.users['staff_organization_admin'])
        after_str = (timezone.now() - datetime.timedelta(days=6)).strftime('%Y-%m-%d')
        before_str = (timezone.now() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        response = self.client.get(reverse('organization_monthly_usage', args=[self.org.slug]), {
            'last_sub_after': after_str,
            'last_sub_before': before_str,
        })
        self.assertEqual(response.status_code, 200)
        problems = list(response.context['problems'])
        # prob1 (5 days) and prob2 (2 days) both match
        self.assertEqual(len(problems), 2)
        self.assertIn(self.prob1, problems)
        self.assertIn(self.prob2, problems)

    def test_last_submission_column_visible_for_admin(self):
        """Org admin thấy cột Last Submission."""
        self.client.force_login(self.users['staff_organization_admin'])
        response = self.client.get(reverse('organization_monthly_usage', args=[self.org.slug]))
        # Content check: Last Submission column header should be rendered
        self.assertContains(response, 'Last Submission')

    def test_usage_page_denied_for_member(self):
        """Non-admin member không được vào trang usage."""
        self.client.force_login(self.users['org_member'])
        response = self.client.get(reverse('organization_monthly_usage', args=[self.org.slug]))
        self.assertEqual(response.status_code, 403)

    def test_default_sort_ascending_last_submission(self):
        """Verify sort mặc định: lâu nhất/chưa có submission lên đầu (NULLs first)."""
        self.client.force_login(self.users['staff_organization_admin'])
        response = self.client.get(reverse('organization_monthly_usage', args=[self.org.slug]))
        problems = list(response.context['problems'])
        # Order should be: prob3 (NULL, oldest/no submission), prob1 (5 days ago), prob2 (2 days ago)
        self.assertEqual(problems[0], self.prob3)
        self.assertEqual(problems[1], self.prob1)
        self.assertEqual(problems[2], self.prob2)

    def test_bulk_delete_happy_path(self):
        """POST problem_ids → deleted_at được set."""
        self.client.force_login(self.users['staff_organization_admin'])
        response = self.client.post(
            reverse('organization_problems_bulk_delete', args=[self.org.slug]),
            {'problem_ids': [self.prob1.id, self.prob2.id]}
        )
        # Should redirect back
        self.assertEqual(response.status_code, 302)

        self.prob1.refresh_from_db()
        self.prob2.refresh_from_db()
        self.prob3.refresh_from_db()

        self.assertTrue(self.prob1.is_deleted)
        self.assertTrue(self.prob2.is_deleted)
        self.assertFalse(self.prob3.is_deleted)

    def test_bulk_delete_permission_denied_non_admin(self):
        """Non-admin POST → 403."""
        self.client.force_login(self.users['org_member'])
        response = self.client.post(
            reverse('organization_problems_bulk_delete', args=[self.org.slug]),
            {'problem_ids': [self.prob1.id]}
        )
        self.assertEqual(response.status_code, 403)
        self.prob1.refresh_from_db()
        self.assertFalse(self.prob1.is_deleted)

    def test_bulk_delete_cross_org_protection(self):
        """Problem thuộc org khác → không bị xóa."""
        self.client.force_login(self.users['staff_organization_admin'])
        response = self.client.post(
            reverse('organization_problems_bulk_delete', args=[self.org.slug]),
            {'problem_ids': [self.other_prob.id]}
        )
        self.assertEqual(response.status_code, 302)
        self.other_prob.refresh_from_db()
        self.assertFalse(self.other_prob.is_deleted)

    def test_bulk_delete_already_deleted(self):
        """Problem đã deleted → không crash."""
        self.client.force_login(self.users['staff_organization_admin'])
        self.prob1.mark_as_deleted()
        response = self.client.post(
            reverse('organization_problems_bulk_delete', args=[self.org.slug]),
            {'problem_ids': [self.prob1.id, self.prob2.id]}
        )
        self.assertEqual(response.status_code, 302)
        self.prob2.refresh_from_db()
        self.assertTrue(self.prob2.is_deleted)
