from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from judge.models import ContestSubmission, Judge, Language, Submission
from judge.models.tests.util import (
    create_contest,
    create_contest_participation,
    create_contest_problem,
    create_problem,
    create_solution,
    create_user,
)


class ContestProblemTestCaseBase(TestCase):
    fixtures = ['language_all.json']

    @classmethod
    def setUpTestData(cls):
        cls._now = timezone.now()

        cls.editor = create_user(username='cp_editor', is_staff=True, user_permissions=('edit_own_contest',))
        cls.tester = create_user(username='cp_tester')
        cls.participant = create_user(username='cp_participant')
        cls.outsider = create_user(username='cp_outsider')

        cls.public_problem = create_problem(code='cp_public', is_public=True, allowed_languages=('PY3',))
        cls.hidden_problem = create_problem(code='cp_hidden', is_public=False, allowed_languages=('PY3',))

        cls.contest = create_contest(
            key='cp_running',
            is_visible=True,
            start_time=cls._now - timezone.timedelta(days=1),
            end_time=cls._now + timezone.timedelta(days=1),
            authors=('cp_editor',),
            testers=('cp_tester',),
        )
        create_contest_problem(contest=cls.contest, problem=cls.public_problem, order=1)
        create_contest_problem(contest=cls.contest, problem=cls.hidden_problem, order=2)

        cls.participation = create_contest_participation(contest=cls.contest, user=cls.participant.profile)

        language = Language.objects.get(key='PY3')
        cls.judge = Judge.objects.create(name='cp_judge', auth_key='cp_judge_key', online=True)
        cls.judge.problems.set([cls.public_problem, cls.hidden_problem])
        cls.judge.runtimes.set([language])
        cls.language = language

    def enter_contest(self):
        profile = self.participant.profile
        profile.current_contest = self.participation
        profile.save()

    def leave_contest(self):
        profile = self.participant.profile
        profile.current_contest = None
        profile.save()


class ContestProblemAccessTestCase(ContestProblemTestCaseBase):
    def detail_url(self, order, contest='cp_running'):
        return reverse('contest_problem_detail', args=[contest, order])

    def test_public_problem_visible_to_outsider_during_contest(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.detail_url(1)).status_code, 200)

    def test_public_problem_visible_to_anonymous(self):
        self.assertEqual(self.client.get(self.detail_url(1)).status_code, 200)

    def test_hidden_problem_404_for_outsider(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.detail_url(2)).status_code, 404)

    def test_hidden_problem_visible_to_participant(self):
        self.enter_contest()
        self.client.force_login(self.participant)
        self.assertEqual(self.client.get(self.detail_url(2)).status_code, 200)

    def test_hidden_problem_visible_to_participant_without_session_contest(self):
        # URL-derived access: the participation grants access even when
        # current_contest is not bound to this contest.
        self.leave_contest()
        self.client.force_login(self.participant)
        self.assertEqual(self.client.get(self.detail_url(2)).status_code, 200)

    def test_hidden_problem_visible_to_editor_and_tester(self):
        for user in (self.editor, self.tester):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.detail_url(2)).status_code, 200)

    def test_before_start_only_editors_and_testers(self):
        create_contest_problem(
            contest=create_contest(
                key='cp_future',
                is_visible=True,
                start_time=self._now + timezone.timedelta(days=1),
                end_time=self._now + timezone.timedelta(days=2),
                authors=('cp_editor',),
                testers=('cp_tester',),
            ),
            problem=self.public_problem,
            order=1,
        )
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.detail_url(1, 'cp_future')).status_code, 404)
        for user in (self.editor, self.tester):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.detail_url(1, 'cp_future')).status_code, 200)

    def test_ended_contest_archive_mode(self):
        ended = create_contest(
            key='cp_ended',
            is_visible=True,
            start_time=self._now - timezone.timedelta(days=10),
            end_time=self._now - timezone.timedelta(days=1),
        )
        create_contest_problem(contest=ended, problem=self.public_problem, order=1)
        create_contest_problem(contest=ended, problem=self.hidden_problem, order=2)
        create_contest_participation(contest=ended, user=self.participant.profile)

        # Public problem stays browsable for everyone after the contest.
        self.assertEqual(self.client.get(self.detail_url(1, 'cp_ended')).status_code, 200)
        # Ex-participants lose access to hidden problems once the contest ends.
        self.client.force_login(self.participant)
        self.assertEqual(self.client.get(self.detail_url(2, 'cp_ended')).status_code, 404)

    def test_invisible_contest_404(self):
        invisible = create_contest(key='cp_invisible', is_visible=False)
        create_contest_problem(contest=invisible, problem=self.public_problem, order=1)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.detail_url(1, 'cp_invisible')).status_code, 404)

    def test_unknown_order_404(self):
        self.client.force_login(self.participant)
        self.assertEqual(self.client.get(self.detail_url(99)).status_code, 404)

    def test_no_global_problem_links_for_participant(self):
        self.enter_contest()
        self.client.force_login(self.participant)
        response = self.client.get(self.detail_url(2))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '/problem/cp_hidden')
        self.assertNotContains(response, 'cp_hidden/raw')
        self.assertContains(response, '/contest/cp_running/2')

    def test_pdf_button_uses_contest_scoped_url(self):
        self.enter_contest()
        self.client.force_login(self.participant)
        content = self.client.get(self.detail_url(1)).content.decode()
        self.assertTrue('/contest/cp_running/1/raw' in content or '/contest/cp_running/1/pdf' in content)
        self.assertNotIn('cp_public/raw', content)

    def test_editorial_hidden_while_running(self):
        create_solution(problem=self.public_problem)
        self.enter_contest()
        self.client.force_login(self.participant)
        response = self.client.get(reverse('contest_problem_editorial', args=['cp_running', 1]))
        self.assertEqual(response.status_code, 404)

    def test_editorial_available_after_end(self):
        create_solution(problem=self.public_problem)
        ended = create_contest(
            key='cp_ended_editorial',
            is_visible=True,
            start_time=self._now - timezone.timedelta(days=10),
            end_time=self._now - timezone.timedelta(days=1),
        )
        create_contest_problem(contest=ended, problem=self.public_problem, order=1)
        self.client.force_login(self.outsider)
        response = self.client.get(reverse('contest_problem_editorial', args=['cp_ended_editorial', 1]))
        self.assertEqual(response.status_code, 200)


class ContestScopeRedirectTestCase(ContestProblemTestCaseBase):
    def test_participant_redirected_from_global_problem_page(self):
        self.enter_contest()
        self.client.force_login(self.participant)
        response = self.client.get(reverse('problem_detail', args=['cp_public']))
        self.assertRedirects(response, reverse('contest_problem_detail', args=['cp_running', 1]),
                             fetch_redirect_response=False)

    def test_participant_redirected_from_global_submit_page(self):
        self.enter_contest()
        self.client.force_login(self.participant)
        response = self.client.get(reverse('problem_submit', args=['cp_public']))
        self.assertRedirects(response, reverse('contest_problem_submit', args=['cp_running', 1]),
                             fetch_redirect_response=False)

    def test_outsider_not_redirected(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse('problem_detail', args=['cp_public'])).status_code, 200)

    def test_participant_not_redirected_for_out_of_contest_problem(self):
        create_problem(code='cp_elsewhere', is_public=True)
        self.enter_contest()
        self.client.force_login(self.participant)
        self.assertEqual(self.client.get(reverse('problem_detail', args=['cp_elsewhere'])).status_code, 200)


class ContestProblemSubmitTestCase(ContestProblemTestCaseBase):
    def submit_url(self, order, contest='cp_running'):
        return reverse('contest_problem_submit', args=[contest, order])

    def post_submission(self, url):
        with patch('judge.models.submission.Submission.judge'):
            return self.client.post(url, {'language': self.language.id, 'source': 'print(1)'})

    def test_participant_submission_attributed_to_url_contest(self):
        self.enter_contest()
        self.client.force_login(self.participant)
        response = self.post_submission(self.submit_url(1))
        self.assertEqual(response.status_code, 302)

        submission = Submission.objects.get()
        self.assertEqual(submission.contest_object_id, self.contest.id)
        contest_submission = ContestSubmission.objects.get()
        self.assertEqual(contest_submission.participation_id, self.participation.id)
        self.assertEqual(contest_submission.problem.problem_id, self.public_problem.id)

    def test_submission_attributed_without_session_contest(self):
        # URL-derived attribution: the URL contest wins even when the session
        # is not bound to any contest.
        self.leave_contest()
        self.client.force_login(self.participant)
        response = self.post_submission(self.submit_url(1))
        self.assertEqual(response.status_code, 302)

        contest_submission = ContestSubmission.objects.get()
        self.assertEqual(contest_submission.participation_id, self.participation.id)

    def test_outsider_cannot_submit_during_contest(self):
        self.client.force_login(self.outsider)
        response = self.post_submission(self.submit_url(1))
        self.assertEqual(response.status_code, 200)  # generic "join the contest" message
        self.assertFalse(Submission.objects.exists())

    def test_practice_submission_after_contest_end(self):
        ended = create_contest(
            key='cp_ended_practice',
            is_visible=True,
            start_time=self._now - timezone.timedelta(days=10),
            end_time=self._now - timezone.timedelta(days=1),
        )
        create_contest_problem(contest=ended, problem=self.public_problem, order=1)
        create_contest_participation(contest=ended, user=self.participant.profile)
        self.judge.problems.add(self.public_problem)

        self.client.force_login(self.participant)
        response = self.post_submission(self.submit_url(1, 'cp_ended_practice'))
        self.assertEqual(response.status_code, 302)

        submission = Submission.objects.get()
        self.assertIsNone(submission.contest_object_id)
        self.assertFalse(ContestSubmission.objects.exists())

    def test_global_route_post_keeps_session_attribution(self):
        # POSTs to the global route are not redirected and keep the legacy
        # session-based attribution, so open submit tabs survive the rollout.
        self.enter_contest()
        self.client.force_login(self.participant)
        with patch('judge.models.submission.Submission.judge'):
            response = self.client.post(reverse('problem_submit', args=['cp_public']),
                                        {'language': self.language.id, 'source': 'print(1)'})
        self.assertEqual(response.status_code, 302)
        contest_submission = ContestSubmission.objects.get()
        self.assertEqual(contest_submission.participation_id, self.participation.id)

    def test_submission_page_keeps_contest_scope(self):
        # Even without a session-bound contest, the submission detail page must
        # link the problem inside the submission's contest, never /problem/<code>.
        self.leave_contest()
        self.client.force_login(self.participant)
        response = self.post_submission(self.submit_url(1))
        self.assertEqual(response.status_code, 302)

        page = self.client.get(response['Location'])
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, '/contest/cp_running/1')
        self.assertNotContains(page, '/problem/cp_public')

        source_page = self.client.get(reverse('submission_source', args=[Submission.objects.get().id]))
        self.assertEqual(source_page.status_code, 200)
        self.assertContains(source_page, '/contest/cp_running/1')
        self.assertNotContains(source_page, '/problem/cp_public')


class ContestEndedLinkTestCase(ContestProblemTestCaseBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.past = create_contest(
            key='cp_past',
            is_visible=True,
            start_time=cls._now - timezone.timedelta(days=10),
            end_time=cls._now - timezone.timedelta(days=1),
        )
        create_contest_problem(contest=cls.past, problem=cls.public_problem, order=1)

    def test_ended_contest_links_original_problem(self):
        response = self.client.get(reverse('contest_view', args=['cp_past']))
        self.assertContains(response, '/problem/cp_public')
        self.assertNotContains(response, '/contest/cp_past/1')

    def test_running_contest_links_contest_problem(self):
        self.enter_contest()
        self.client.force_login(self.participant)
        response = self.client.get(reverse('contest_view', args=['cp_running']))
        self.assertContains(response, '/contest/cp_running/1')
        self.assertNotContains(response, '/problem/cp_public')

    def test_virtual_participant_keeps_contest_links(self):
        virtual = create_contest_participation(contest=self.past, user=self.participant.profile, virtual=1)
        profile = self.participant.profile
        profile.current_contest = virtual
        profile.save()
        self.client.force_login(self.participant)
        response = self.client.get(reverse('contest_view', args=['cp_past']))
        self.assertContains(response, '/contest/cp_past/1')
        self.assertNotContains(response, '/problem/cp_public')


class ContestProblemStatusIconTestCase(ContestProblemTestCaseBase):
    def setUp(self):
        cache.clear()  # user/contest completed-id caches are keyed by db ids that recur across tests

    def make_ac_submission(self, participation=None):
        submission = Submission.objects.create(user=self.participant.profile, problem=self.public_problem,
                                               language=self.language, result='AC', points=1)
        if participation is not None:
            contest_problem = self.contest.contest_problems.get(order=1)
            ContestSubmission.objects.create(submission=submission, problem=contest_problem,
                                             participation=participation, points=contest_problem.points)
        return submission

    def test_general_solve_not_shown_while_in_contest(self):
        self.make_ac_submission()  # solved outside the contest
        self.enter_contest()
        self.client.force_login(self.participant)
        response = self.client.get(reverse('contest_view', args=['cp_running']))
        self.assertNotIn(self.public_problem.id, response.context['completed_problem_ids'])
        self.assertNotIn(self.public_problem.id, response.context['attempted_problem_ids'])

    def test_participation_solve_shown_while_in_contest(self):
        self.make_ac_submission(participation=self.participation)
        self.enter_contest()
        self.client.force_login(self.participant)
        response = self.client.get(reverse('contest_view', args=['cp_running']))
        self.assertIn(self.public_problem.id, response.context['completed_problem_ids'])
        self.assertIn(self.public_problem.id, response.context['attempted_problem_ids'])

    def test_general_status_outside_contest(self):
        self.make_ac_submission()
        self.leave_contest()
        self.client.force_login(self.participant)
        response = self.client.get(reverse('contest_view', args=['cp_running']))
        self.assertIn(self.public_problem.id, response.context['completed_problem_ids'])


class ContestProblemDualResolutionTestCase(ContestProblemTestCaseBase):
    def test_legacy_contest_route_accepts_order_and_code(self):
        self.enter_contest()
        self.client.force_login(self.participant)
        by_order = self.client.get(reverse('contest_user_submissions',
                                           args=['cp_running', 'cp_participant', '1']))
        by_code = self.client.get(reverse('contest_user_submissions',
                                          args=['cp_running', 'cp_participant', 'cp_public']))
        self.assertEqual(by_order.status_code, 200)
        self.assertEqual(by_code.status_code, 200)
        self.assertEqual(by_order.context['title'], by_code.context['title'])

    def test_order_based_submission_list_route(self):
        self.enter_contest()
        self.client.force_login(self.participant)
        response = self.client.get(reverse('contest_problem_user_submissions',
                                           args=['cp_running', 1, 'cp_participant']))
        self.assertEqual(response.status_code, 200)
