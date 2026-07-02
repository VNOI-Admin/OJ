from django.test import TestCase
from django.urls import reverse

from judge.models.tests.util import create_contest, create_contest_problem, create_problem, create_user
from judge.utils.contest_problems import problem_label, problem_url


class ContestProblemUrlHelperTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user(username='helper_user')
        cls.contest = create_contest(key='helper_contest')
        cls.in_contest = create_problem(code='helper_in')
        cls.out_of_contest = create_problem(code='helper_out')
        cls.contest_problem = create_contest_problem(contest=cls.contest, problem=cls.in_contest, order=1)

    def test_contest_scoped_url(self):
        self.assertEqual(problem_url(self.in_contest, 'detail', self.contest),
                         reverse('contest_problem_detail', args=[self.contest.key, 1]))
        self.assertEqual(problem_url(self.in_contest, 'submit', self.contest),
                         reverse('contest_problem_submit', args=[self.contest.key, 1]))

    def test_global_fallback_without_contest(self):
        self.assertEqual(problem_url(self.in_contest), reverse('problem_detail', args=[self.in_contest.code]))

    def test_global_fallback_for_out_of_contest_problem(self):
        self.assertEqual(problem_url(self.out_of_contest, 'detail', self.contest),
                         reverse('problem_detail', args=[self.out_of_contest.code]))

    def test_extra_args(self):
        self.assertEqual(
            problem_url(self.in_contest, 'user_submissions', self.contest, extra=('helper_user',)),
            reverse('contest_problem_user_submissions', args=[self.contest.key, 1, 'helper_user']),
        )
        self.assertEqual(
            problem_url(self.out_of_contest, 'user_submissions', self.contest, extra=('helper_user',)),
            reverse('user_submissions', args=[self.out_of_contest.code, 'helper_user']),
        )

    def test_problem_label(self):
        expected = self.contest.get_label_for_problem(0)
        self.assertEqual(problem_label(self.in_contest, self.contest), expected)
        self.assertEqual(problem_label(self.out_of_contest, self.contest), self.out_of_contest.code)
        self.assertEqual(problem_label(self.in_contest, None), self.in_contest.code)

    def test_order_map_memoized_on_contest_instance(self):
        with self.assertNumQueries(1):
            problem_url(self.in_contest, 'detail', self.contest)
            problem_url(self.in_contest, 'submit', self.contest)
            problem_label(self.in_contest, self.contest)

    def test_contest_problem_get_absolute_url(self):
        self.assertEqual(self.contest_problem.get_absolute_url(),
                         reverse('contest_problem_detail', args=[self.contest.key, 1]))
