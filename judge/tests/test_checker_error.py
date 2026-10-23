from collections import defaultdict
from unittest.mock import Mock, patch

from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from judge.admin.submission import SubmissionStatusFilter
from judge.bridge.judge_handler import JudgeHandler
from judge.contest_format.icpc import ICPCContestFormat
from judge.models import ContestSubmission, Language, Submission, SubmissionSource
from judge.models.problem import SubmissionSourceAccess
from judge.models.submission import SubmissionTestCase as SubmissionTestCaseModel
from judge.models.tests.util import (
    CommonDataMixin,
    create_contest,
    create_contest_participation,
    create_contest_problem,
    create_problem,
    create_user,
)
from judge.utils.problems import _get_result_data
from judge.views.problem import get_contest_submission_count
from judge.views.stats import submission_data


class CheckerErrorBridgeTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.problem = create_problem(
            code='checker_error_bridge',
            is_public=True,
            authors=('staff_problem_edit_own',),
            submission_source_visibility_mode=SubmissionSourceAccess.ALWAYS,
        )
        cls.submission = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.problem,
            language=Language.get_python3(),
        )

    def test_internal_error_maps_only_checker_tag_to_cke_and_finishes(self):
        handler = object.__new__(JudgeHandler)
        handler.name = 'test-judge'
        handler.judge_address = None
        handler.judges = Mock()
        handler._submission_cache_id = None
        handler._submission_cache = {}
        message = 'Traceback (most recent call last):\nchecker failure'

        cases = (('checker', 'CKE'), ('legacy', 'IE'), (None, 'IE'), ('unknown', 'IE'))
        for call_count, (error_type, expected) in enumerate(cases, start=1):
            with self.subTest(error_type=error_type):
                starting_status = 'G' if error_type == 'checker' else 'QU'
                Submission.objects.filter(pk=self.submission.pk).update(
                    status=starting_status, result=None, error=None,
                )
                handler._submission_cache_id = None
                handler._submission_cache = {}
                if error_type == 'checker':
                    handler._get_submission_cache(self.submission.pk)
                packet = {'submission-id': self.submission.pk, 'message': message}
                if error_type is not None:
                    packet['error-type'] = error_type

                with patch('judge.bridge.judge_handler.event.post') as post, \
                        patch('judge.bridge.judge_handler.json_log.info'):
                    handler.on_internal_error(packet)

                self.submission.refresh_from_db()
                self.assertEqual((self.submission.status, self.submission.result), (expected, expected))
                self.assertEqual(self.submission.error, message)
                handler.judges.on_judge_free.assert_called_with(handler, self.submission.pk)
                self.assertEqual(handler.judges.on_judge_free.call_count, call_count)
                events = [args for args, _ in post.call_args_list]
                self.assertIn(('sub_%s' % self.submission.id_secret, {'type': 'internal-error'}), events)
                done = [event for topic, event in events if topic == 'submissions']
                self.assertEqual(done[-1]['type'], 'done-submission')
                self.assertEqual(done[-1]['state'], 'internal-error')
                self.assertEqual(done[-1]['status'], expected)

    def test_checker_error_is_a_valid_graded_submission_result(self):
        submission = Submission(
            user=self.users['normal'].profile,
            problem=self.problem,
            language=Language.get_python3(),
            status='CKE',
            result='CKE',
        )

        status_field = Submission._meta.get_field('status')
        result_field = Submission._meta.get_field('result')
        self.assertEqual(status_field.max_length, 3)
        self.assertIn('CKE', dict(status_field.choices))
        status_field.clean('CKE', submission)
        result_field.clean('CKE', submission)
        self.assertEqual(submission.short_status, 'CKE')
        self.assertEqual(submission.result_class, 'CKE')
        self.assertEqual(submission.long_status, _('Checker Error'))
        self.assertTrue(submission.is_graded)


class CheckerErrorUserInterfaceTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.users['other'] = create_user(username='checker_error_other')
        cls.problem = create_problem(
            code='checker_error_ui',
            is_public=True,
            authors=('staff_problem_edit_own',),
            submission_source_visibility_mode=SubmissionSourceAccess.ALWAYS,
        )
        cls.submission = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.problem,
            language=Language.get_python3(),
            status='CKE',
            result='CKE',
            error='private checker traceback',
            case_points=731,
            case_total=941,
            time=13.79,
            memory=82731,
        )

    def test_only_problem_editor_sees_checker_traceback(self):
        url = reverse('submission_status', args=(self.submission.pk,))
        for username in ('normal', 'other', 'staff_problem_edit_own'):
            with self.subTest(username=username):
                self.client.force_login(self.users[username])
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                page = response.content.decode()
                self.assertIn('A checker error occurred while grading.', page)
                self.assertNotIn('An internal error occurred', page)
                if username == 'staff_problem_edit_own':
                    self.assertIn('private checker traceback', page)
                else:
                    self.assertNotIn('private checker traceback', page)

        self.client.logout()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('private checker traceback', response.content.decode())

    def test_checker_error_row_hides_score_time_and_memory(self):
        response = self.client.get(reverse('submission_single_query'), {'id': self.submission.pk})
        self.assertEqual(response.status_code, 200)
        row = response.content.decode()
        self.assertIn('CKE', row)
        self.assertIn('---', row)
        for hidden_value in ('731', '941', '13.79', '82731'):
            self.assertNotIn(hidden_value, row)


class CheckerErrorAccountingTestCase(CommonDataMixin, TestCase):
    def test_checker_error_does_not_increment_engine_attempt_number(self):
        problem = create_problem(code='checker_error_attempt')
        old = Submission.objects.create(
            user=self.users['normal'].profile,
            problem=problem,
            language=Language.get_python3(),
            status='CKE',
            result='CKE',
        )
        current = Submission.objects.create(
            user=self.users['normal'].profile,
            problem=problem,
            language=Language.get_python3(),
        )
        now = timezone.now()
        Submission.objects.filter(pk=old.pk).update(date=now - timezone.timedelta(minutes=2))
        Submission.objects.filter(pk=current.pk).update(date=now)

        with patch('judge.bridge.judge_handler._ensure_connection'):
            data = JudgeHandler.get_related_submission_data(None, current.pk)

        self.assertEqual(data.attempt_no, 1)

    def test_checker_error_is_done_in_admin_not_done_filter(self):
        problem = create_problem(code='checker_error_admin_filter')
        Submission.objects.create(
            user=self.users['normal'].profile,
            problem=problem,
            language=Language.get_python3(),
            status='CKE',
            result='CKE',
        )
        queued = Submission.objects.create(
            user=self.users['normal'].profile,
            problem=problem,
            language=Language.get_python3(),
        )
        request = RequestFactory().get('/', {'status': 'NotDone'})
        status_filter = SubmissionStatusFilter(request, {'status': 'NotDone'}, Submission, None)

        self.assertCountEqual(
            status_filter.queryset(request, Submission.objects.all()).values_list('pk', flat=True),
            [queued.pk],
        )

    def test_checker_error_is_ignored_by_contest_submission_count_and_penalty(self):
        now = timezone.now()
        contest = create_contest(
            key='checker_error_accounting',
            format_name='icpc',
            start_time=now - timezone.timedelta(hours=1),
            end_time=now + timezone.timedelta(hours=2),
        )
        problem = create_problem(code='checker_error_accounting')
        contest_problem = create_contest_problem(contest=contest, problem=problem)
        participation = create_contest_participation(
            contest=contest,
            user=self.users['normal'].profile,
            real_start=now - timezone.timedelta(hours=1),
        )
        self.users['normal'].profile.current_contest = participation
        self.users['normal'].profile.save(update_fields=['current_contest'])

        checker_error = Submission.objects.create(
            user=self.users['normal'].profile,
            problem=problem,
            language=Language.get_python3(),
            contest_object=contest,
            status='CKE',
            result='CKE',
        )
        accepted = Submission.objects.create(
            user=self.users['normal'].profile,
            problem=problem,
            language=Language.get_python3(),
            contest_object=contest,
            status='D',
            result='AC',
        )
        Submission.objects.filter(pk=checker_error.pk).update(date=now - timezone.timedelta(minutes=30))
        Submission.objects.filter(pk=accepted.pk).update(date=now)
        ContestSubmission.objects.create(
            submission=checker_error,
            problem=contest_problem,
            participation=participation,
            points=0,
        )
        ContestSubmission.objects.create(
            submission=accepted,
            problem=contest_problem,
            participation=participation,
            points=contest_problem.points,
        )

        self.assertEqual(get_contest_submission_count(problem, self.users['normal'].profile, participation.virtual), 1)
        ICPCContestFormat(contest, {}).update_participation(participation)
        self.assertEqual(participation.format_data[str(contest_problem.pk)]['tries'], 1)
        self.assertEqual(participation.cumtime, 60)


class CheckerErrorApiAndRejudgeTestCase(CommonDataMixin, TestCase):
    def test_sync_api_reports_cke(self):
        now = timezone.now()
        contest = create_contest(
            key='checker_error_api',
            start_time=now - timezone.timedelta(hours=1),
            end_time=now + timezone.timedelta(hours=1),
        )
        submission = Submission.objects.create(
            user=self.users['normal'].profile,
            problem=create_problem(code='checker_error_api'),
            language=Language.get_python3(),
            contest_object=contest,
            status='CKE',
            result='CKE',
            judged_date=now,
        )

        with self.settings(GLOBAL_API_KEY='checker-error-test-key'):
            response = self.client.get(
                reverse('api_contest_sync_submissions', args=(contest.key,)),
                {'from_timestamp': (now - timezone.timedelta(minutes=1)).isoformat()},
                headers={'X-Global-API-Key': 'checker-error-test-key'},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]['id'], str(submission.pk))
        self.assertEqual(response.json()[0]['submissionStatus'], 'CKE')

    def test_rejudge_clears_cke_state_before_dispatch(self):
        problem = create_problem(code='checker_error_rejudge', is_public=True)
        submission = Submission.objects.create(
            user=self.users['normal'].profile,
            problem=problem,
            language=Language.get_python3(),
            status='CKE',
            result='CKE',
            error='checker traceback',
            time=1.5,
            memory=1024,
            points=0,
            case_points=0,
            case_total=100,
        )
        SubmissionSource.objects.create(submission=submission, source='print(1)')
        SubmissionTestCaseModel.objects.create(
            submission=submission,
            case=1,
            status='WA',
            time=1,
            memory=100,
            points=0,
            total=100,
            batch=None,
        )

        with patch(
            'judge.judgeapi.judge_request',
            return_value={'name': 'submission-received', 'submission-id': submission.pk},
        ) as judge_request, patch('judge.judgeapi.event.post'):
            submission.judge(rejudge=True)

        judge_request.assert_called_once()
        submission.refresh_from_db()
        self.assertEqual(submission.status, 'QU')
        self.assertIsNone(submission.result)
        self.assertIsNone(submission.error)
        self.assertIsNone(submission.time)
        self.assertIsNone(submission.memory)
        self.assertIsNone(submission.points)
        self.assertEqual((submission.case_points, submission.case_total), (0, 0))
        self.assertFalse(submission.test_cases.exists())


class CheckerErrorStatsTestCase(CommonDataMixin, TestCase):
    def test_checker_error_appears_in_result_error_category(self):
        data = _get_result_data(defaultdict(int, {'CKE': 2}))
        error = next(category for category in data['categories'] if category['code'] == 'ERR')

        self.assertEqual(error['count'], 2)

    def test_checker_error_is_counted_under_err_in_daily_stats(self):
        start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        submission = Submission.objects.create(
            user=self.users['normal'].profile,
            problem=create_problem(code='checker_error_stats'),
            language=Language.get_python3(),
            status='CKE',
            result='CKE',
        )
        Submission.objects.filter(pk=submission.pk).update(date=start + timezone.timedelta(hours=1))

        data = submission_data(start, start + timezone.timedelta(days=1), timezone.timedelta())
        err = next(dataset for dataset in data['by_day']['datasets'] if dataset['label'] == 'ERR')

        self.assertEqual(err['data'][0], 1)
        self.assertIn('Checker Error', data['result']['labels'])
