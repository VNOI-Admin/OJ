from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from judge.models import Submission, SubmissionSource, SubmissionTestCase
from judge.models.tests.util import (
    CommonDataMixin,
    create_contest,
    create_contest_problem,
    create_problem,
    create_user,
)
from judge.tasks.problem import delete_problem


class ProblemDeletionPermissionTestCase(CommonDataMixin, TestCase):
    """Test is_deletable_by permission method"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.users.update({
            'delete_perm_author': create_user(
                username='delete_perm_author',
                user_permissions=('delete_own_problem', 'edit_own_problem'),
            ),
            'delete_perm_not_author': create_user(
                username='delete_perm_not_author',
                user_permissions=('delete_own_problem', 'edit_own_problem'),
            ),
            'no_delete_perm_author': create_user(
                username='no_delete_perm_author',
                user_permissions=('edit_own_problem',),
            ),
            'delete_and_edit_all': create_user(
                username='delete_and_edit_all',
                user_permissions=('delete_own_problem', 'edit_own_problem', 'edit_all_problem'),
            ),
        })

        cls.deletable_problem = create_problem(
            code='deletable',
            authors=('delete_perm_author',),
        )

    def test_is_deletable_by_author_with_permission(self):
        """Author with delete_own_problem permission can delete"""
        self.assertTrue(
            self.deletable_problem.is_deletable_by(self.users['delete_perm_author']),
        )

    def test_is_deletable_by_edit_all_permission(self):
        """User with edit_all_problem can delete any problem"""
        self.assertTrue(
            self.deletable_problem.is_deletable_by(self.users['delete_and_edit_all']),
        )

    def test_is_not_deletable_without_permission(self):
        """Author without delete_own_problem permission cannot delete"""
        self.assertFalse(
            self.deletable_problem.is_deletable_by(self.users['no_delete_perm_author']),
        )

    def test_is_not_deletable_by_non_author(self):
        """Non-author with delete_own_problem permission cannot delete"""
        self.assertFalse(
            self.deletable_problem.is_deletable_by(self.users['delete_perm_not_author']),
        )

    def test_is_not_deletable_by_anonymous(self):
        """Anonymous user cannot delete"""
        self.assertFalse(
            self.deletable_problem.is_deletable_by(self.users['anonymous']),
        )


@override_settings(CELERY_ALWAYS_EAGER=True, VNOJ_PROBLEM_DELETE_BATCH_SIZE=2)
class ProblemDeletionTaskTestCase(TestCase):
    """Test delete_problem Celery task"""

    fixtures = ['language_all.json']

    def test_delete_problem_with_submissions(self):
        """Test that problem and related submissions are deleted"""
        # Create problem
        user = create_user(username='testuser')
        problem = create_problem(code='testproblem')

        # Get a language (required for submission)
        from judge.models import Language
        lang = Language.objects.first()

        # Create submissions with related objects
        for i in range(5):
            submission = Submission.objects.create(
                problem=problem,
                user=user.profile,
                language=lang,
                result='AC',
                case_points=100,
                case_total=100,
                points=100,
            )
            SubmissionSource.objects.create(submission=submission, source='print("test")')
            SubmissionTestCase.objects.create(submission=submission, case=1, status='AC')

        problem_id = problem.id
        submission_count = Submission.objects.filter(problem=problem).count()
        self.assertEqual(submission_count, 5)

        # Execute deletion task
        delete_problem.apply(args=[problem_id]).get()

        # Verify problem and submissions are deleted
        self.assertFalse(Submission.objects.filter(problem_id=problem_id).exists())
        self.assertFalse(SubmissionSource.objects.filter(submission__problem_id=problem_id).exists())
        self.assertFalse(SubmissionTestCase.objects.filter(submission__problem_id=problem_id).exists())
        from judge.models import Problem
        self.assertFalse(Problem.objects.filter(id=problem_id).exists())


class ProblemDeleteViewTestCase(CommonDataMixin, TestCase):
    """Test ProblemDelete view"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.users.update({
            'problem_deleter': create_user(
                username='problem_deleter',
                user_permissions=('delete_own_problem', 'edit_own_problem'),
            ),
        })

        cls.test_problem = create_problem(
            code='test_delete',
            authors=('problem_deleter',),
            is_public=True,
        )

        cls.other_problem = create_problem(
            code='other_delete',
            authors=('normal',),
        )

        # Create active contest with problem
        _now = timezone.now()
        cls.active_contest = create_contest(
            key='active',
            start_time=_now - timezone.timedelta(hours=1),
            end_time=_now + timezone.timedelta(hours=1),
        )
        cls.problem_in_active_contest = create_problem(
            code='in_active_contest',
            authors=('problem_deleter',),
        )
        create_contest_problem(
            contest=cls.active_contest,
            problem=cls.problem_in_active_contest,
        )

    def test_get_delete_confirmation_page(self):
        """Authorized user can access delete confirmation page"""
        self.client.force_login(self.users['problem_deleter'])
        response = self.client.get(reverse('problem_delete', args=['test_delete']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'test_delete')

    def test_get_requires_permission(self):
        """User without permission cannot access delete page"""
        self.client.force_login(self.users['normal'])
        response = self.client.get(reverse('problem_delete', args=['test_delete']))
        self.assertEqual(response.status_code, 403)

    def test_post_requires_permission(self):
        """User without permission cannot delete"""
        self.client.force_login(self.users['normal'])
        response = self.client.post(reverse('problem_delete', args=['other_delete']))
        self.assertEqual(response.status_code, 403)

    def test_cannot_delete_problem_in_active_contest(self):
        """Cannot delete problem that's in an active contest"""
        self.client.force_login(self.users['problem_deleter'])
        response = self.client.post(reverse('problem_delete', args=['in_active_contest']))
        self.assertEqual(response.status_code, 400)

    def test_anonymous_user_redirected_to_login(self):
        """Anonymous user is redirected to login"""
        response = self.client.get(reverse('problem_delete', args=['test_delete']))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response.url)
