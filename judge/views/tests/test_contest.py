from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from judge.models import Solution
from judge.models.tests.util import (
    create_contest,
    create_contest_problem,
    create_problem,
    create_solution,
    create_user,
)


class ContestProblemMakePublicTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._now = timezone.now()

        cls.staff_editor = create_user(
            username='staff_editor',
            is_staff=True,
            is_superuser=True,
        )

        cls.normal_user = create_user(
            username='normal_user',
        )

        cls.contest = create_contest(
            key='test_publish',
            start_time=cls._now - timezone.timedelta(days=10),
            end_time=cls._now - timezone.timedelta(days=1),
            is_visible=True,
            authors=('staff_editor',),
        )

        # Private problem WITH editorial
        cls.problem_with_editorial = create_problem(
            code='prob_with_editorial',
            is_public=False,
            authors=('staff_editor',),
        )
        cls.solution = create_solution(
            problem=cls.problem_with_editorial,
            is_public=False,
            publish_on=cls._now + timezone.timedelta(days=100),
            content='Editorial content',
        )
        create_contest_problem(
            contest=cls.contest,
            problem=cls.problem_with_editorial,
            order=1,
        )

        # Private problem WITHOUT editorial
        cls.problem_without_editorial = create_problem(
            code='prob_no_editorial',
            is_public=False,
            authors=('staff_editor',),
        )
        create_contest_problem(
            contest=cls.contest,
            problem=cls.problem_without_editorial,
            order=2,
        )

        # Already-public problem with unpublished editorial
        cls.public_problem = create_problem(
            code='prob_already_public',
            is_public=True,
            authors=('staff_editor',),
        )
        cls.public_problem_solution = create_solution(
            problem=cls.public_problem,
            is_public=False,
            publish_on=cls._now + timezone.timedelta(days=100),
            content='Hidden editorial for public problem',
        )
        create_contest_problem(
            contest=cls.contest,
            problem=cls.public_problem,
            order=3,
        )

    def _get_url(self):
        return reverse('contest_problems_make_public', args=[self.contest.key])

    @patch('judge.views.contests.rescore_problem')
    def test_publishes_problems_and_editorials(self, mock_rescore):
        self.client.force_login(self.staff_editor)
        response = self.client.post(self._get_url())

        self.assertEqual(response.status_code, 302)

        self.problem_with_editorial.refresh_from_db()
        self.assertTrue(self.problem_with_editorial.is_public)

        self.solution.refresh_from_db()
        self.assertTrue(self.solution.is_public)
        self.assertLessEqual(self.solution.publish_on, timezone.now())

    @patch('judge.views.contests.rescore_problem')
    def test_no_editorial_does_not_break(self, mock_rescore):
        self.client.force_login(self.staff_editor)
        response = self.client.post(self._get_url())

        self.assertEqual(response.status_code, 302)

        self.problem_without_editorial.refresh_from_db()
        self.assertTrue(self.problem_without_editorial.is_public)
        self.assertFalse(Solution.objects.filter(problem=self.problem_without_editorial).exists())

    @patch('judge.views.contests.rescore_problem')
    def test_already_public_problem_editorial_should_be_published(self, mock_rescore):
        self.client.force_login(self.staff_editor)
        self.client.post(self._get_url())

        self.public_problem_solution.refresh_from_db()
        self.assertTrue(self.public_problem_solution.is_public)
        self.assertLessEqual(self.public_problem_solution.publish_on, timezone.now())

    @patch('judge.views.contests.rescore_problem')
    def test_rescore_called_for_published_problems(self, mock_rescore):
        self.client.force_login(self.staff_editor)
        self.client.post(self._get_url())

        rescore_ids = {call.args[0] for call in mock_rescore.delay.call_args_list}
        self.assertIn(self.problem_with_editorial.id, rescore_ids)
        self.assertIn(self.problem_without_editorial.id, rescore_ids)
        self.assertNotIn(self.public_problem.id, rescore_ids)

    def test_get_request_forbidden(self):
        self.client.force_login(self.staff_editor)
        response = self.client.get(self._get_url())
        self.assertEqual(response.status_code, 403)

    @patch('judge.views.contests.rescore_problem')
    def test_normal_user_permission_denied(self, mock_rescore):
        self.client.force_login(self.normal_user)
        self.client.post(self._get_url())

        self.problem_with_editorial.refresh_from_db()
        self.assertFalse(self.problem_with_editorial.is_public)
        mock_rescore.delay.assert_not_called()
