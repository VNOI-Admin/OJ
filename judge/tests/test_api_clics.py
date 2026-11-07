import json
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from judge.models import (
    Contest,
    ContestParticipation,
    ContestProblem,
    ContestSubmission,
    Language,
    Organization,
    Problem,
    ProblemGroup,
    Profile,
    Submission,
)
from judge.utils.clics import format_reltime, format_time, problem_label

URL = '/api/clics/contests/icpc-live/event-feed'
HEADERS = {'X-Global-API-Key': 'test-api-key-123'}


class ClicsFormatTestCase(SimpleTestCase):
    def test_format_reltime(self):
        self.assertEqual(format_reltime(timedelta(hours=5)), '5:00:00.000')
        self.assertEqual(format_reltime(timedelta(minutes=61, seconds=5, milliseconds=7)), '1:01:05.007')
        self.assertEqual(format_reltime(timedelta(seconds=-90)), '-0:01:30.000')

    def test_format_time(self):
        value = datetime(2026, 11, 6, 8, 30, 0, 123456, tzinfo=dt_timezone.utc)
        self.assertEqual(format_time(value), '2026-11-06T08:30:00.123+00:00')

    def test_problem_label(self):
        self.assertEqual([problem_label(i) for i in (1, 2, 26, 27, 28)], ['A', 'B', 'Z', 'AA', 'AB'])


@override_settings(GLOBAL_API_KEY='test-api-key-123')
@mock.patch('judge.views.api.api_v2.APIContestClicsEventFeed.FINALIZE_DELAY', 0)
class ContestClicsEventFeedTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        now = timezone.now()
        cls.start = now - timedelta(hours=4, minutes=30)
        cls.contest = Contest.objects.create(
            key='icpc-live',
            name='ICPC Live',
            start_time=cls.start,
            end_time=cls.start + timedelta(hours=5),
            is_visible=True,
            frozen_last_minutes=60,
            format_name='icpc',
            format_config={'penalty': 20},
        )
        cls.org = Organization.objects.create(name='University of Science', slug='hcmus', short_name='HCMUS',
                                              about='about')

        def make_team(username, first_name=''):
            user = user_model.objects.create_user(username=username, password='pw', first_name=first_name)
            return Profile.objects.create(user=user)

        cls.alpha = make_team('team_alpha', first_name='Alpha Team')
        cls.alpha.organizations.add(cls.org)
        cls.beta = make_team('team_beta')
        cls.cheater = make_team('team_cheater')
        cls.upsolver = make_team('upsolver')

        group = ProblemGroup.objects.create(name='g', full_name='G')
        cls.language = Language.objects.create(key='CPP17', name='C++17', short_name='C++17', common_name='C++',
                                               ace='c_cpp', pygments='cpp', extension='cpp')
        cls.contest_problems = []
        for order, code in enumerate(['icpcb', 'icpca'], start=1):
            problem = Problem.objects.create(code=code, name=f'Problem {code}', description='', group=group,
                                             time_limit=2, memory_limit=262144, points=1, partial=False)
            cls.contest_problems.append(
                ContestProblem.objects.create(contest=cls.contest, problem=problem, points=1, order=order))

        def participate(profile, virtual=ContestParticipation.LIVE, **kwargs):
            return ContestParticipation.objects.create(contest=cls.contest, user=profile, virtual=virtual,
                                                       real_start=cls.start, **kwargs)

        cls.p_alpha = participate(cls.alpha)
        cls.p_beta = participate(cls.beta)
        cls.p_cheater = participate(cls.cheater, is_disqualified=True)
        cls.p_upsolver = participate(cls.upsolver, virtual=1)

        def submit(participation, contest_problem, minutes, status='D', result='AC'):
            sub = Submission.objects.create(user=participation.user, problem=contest_problem.problem,
                                            language=cls.language, status=status, result=result,
                                            contest_object=cls.contest)
            date = cls.start + timedelta(minutes=minutes)
            sub.date = date
            sub.judged_date = date + timedelta(seconds=10) if result else None
            sub.save(update_fields=['date', 'judged_date'])
            ContestSubmission.objects.create(submission=sub, problem=contest_problem, participation=participation)
            return sub

        cls.wa = submit(cls.p_alpha, cls.contest_problems[0], 10, result='WA')
        cls.ac = submit(cls.p_alpha, cls.contest_problems[0], 25)
        cls.pending = submit(cls.p_beta, cls.contest_problems[1], 250, status='G', result=None)
        cls.virtual_sub = submit(cls.p_upsolver, cls.contest_problems[1], 30)

    def get_events(self, query=''):
        response = self.client.get(URL + query, headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('application/x-ndjson'))
        content = b''.join(response.streaming_content) if response.streaming else response.content
        lines = content.decode().splitlines()
        events = [json.loads(line) for line in lines]
        for event in events:
            self.assertIsNone(event['id'])
            self.assertNotIn('token', event)
        return {event['type']: event['data'] for event in events}, [event['type'] for event in events]

    def test_requires_api_key(self):
        self.assertEqual(self.client.get(URL).status_code, 403)
        self.assertEqual(self.client.get(URL, headers={'X-Global-API-Key': 'wrong'}).status_code, 403)

    def test_unknown_contest(self):
        response = self.client.get('/api/clics/contests/nope/event-feed', headers=HEADERS)
        self.assertEqual(response.status_code, 404)

    def test_event_order(self):
        _, order = self.get_events()
        self.assertEqual(order, ['contest', 'judgement-types', 'languages', 'problems', 'organizations', 'teams',
                                 'submissions', 'judgements', 'state'])

    def test_contest_and_state(self):
        data, _ = self.get_events()
        self.assertEqual(data['contest'], {
            'id': 'icpc-live',
            'name': 'ICPC Live',
            'formal_name': 'ICPC Live',
            'start_time': format_time(self.start),
            'duration': '5:00:00.000',
            'scoreboard_type': 'pass-fail',
            'penalty_time': 20,
            'scoreboard_freeze_duration': '1:00:00.000',
        })
        state = data['state']
        self.assertEqual(state['started'], format_time(self.start))
        self.assertEqual(state['frozen'], format_time(self.start + timedelta(hours=4)))
        self.assertIsNone(state['ended'])
        self.assertIsNone(state['end_of_updates'])

    def test_judgement_types(self):
        data, _ = self.get_events()
        types = {t['id']: (t['solved'], t['penalty']) for t in data['judgement-types']}
        self.assertEqual(types['AC'], (True, False))
        self.assertEqual(types['WA'], (False, True))
        self.assertEqual(types['TLE'], (False, True))
        self.assertEqual(types['CE'], (False, False))
        self.assertEqual(types['IE'], (False, False))

    def test_problems_follow_contest_order(self):
        data, _ = self.get_events()
        self.assertEqual(
            [(p['id'], p['label'], p['ordinal']) for p in data['problems']],
            [('icpcb', 'A', 0), ('icpca', 'B', 1)],
        )
        self.assertIn({'id': 'CPP17', 'name': 'C++17', 'extensions': ['cpp']}, data['languages'])

    def test_teams_and_organizations(self):
        data, _ = self.get_events()
        teams = {team['id']: team for team in data['teams']}
        self.assertEqual(set(teams), {'team_alpha', 'team_beta', 'team_cheater'})
        self.assertEqual(teams['team_alpha']['name'], 'Alpha Team')
        self.assertEqual(teams['team_alpha']['organization_id'], str(self.org.id))
        self.assertEqual(teams['team_beta']['name'], 'team_beta')
        self.assertNotIn('organization_id', teams['team_beta'])
        self.assertTrue(teams['team_cheater']['hidden'])
        self.assertFalse(teams['team_alpha']['hidden'])
        self.assertEqual(data['organizations'], [
            {'id': str(self.org.id), 'name': 'HCMUS', 'formal_name': 'University of Science'},
        ])

    def test_submissions_and_judgements(self):
        data, _ = self.get_events()
        self.assertEqual(
            [(s['id'], s['team_id'], s['problem_id'], s['contest_time']) for s in data['submissions']],
            [
                (str(self.wa.id), 'team_alpha', 'icpcb', '0:10:00.000'),
                (str(self.ac.id), 'team_alpha', 'icpcb', '0:25:00.000'),
                (str(self.pending.id), 'team_beta', 'icpca', '4:10:00.000'),
            ],
        )
        # The pending submission has no judgement yet; frozen results are still sent (live-v3 hides them).
        self.assertEqual(
            [(j['submission_id'], j['judgement_type_id'], j['end_contest_time']) for j in data['judgements']],
            [
                (str(self.wa.id), 'WA', '0:10:10.000'),
                (str(self.ac.id), 'AC', '0:25:10.000'),
            ],
        )

    def test_rejudge_in_progress_drops_judgement(self):
        Submission.objects.filter(id=self.ac.id).update(status='QU', result=None)
        data, _ = self.get_events()
        self.assertEqual([j['submission_id'] for j in data['judgements']], [str(self.wa.id)])

    def test_finalize(self):
        # Not over yet: never finalized.
        self.assertIsNone(self.get_events('?finalize=1')[0]['state']['end_of_updates'])

        Contest.objects.filter(id=self.contest.id).update(end_time=timezone.now() - timedelta(minutes=1))
        self.assertIsNone(self.get_events()[0]['state']['end_of_updates'])
        # Over, but a submission is still being judged.
        self.assertIsNone(self.get_events('?finalize=1')[0]['state']['end_of_updates'])

        Submission.objects.filter(id=self.pending.id).update(status='D', result='WA')
        state = self.get_events('?finalize=1')[0]['state']
        self.assertIsNotNone(state['ended'])
        self.assertEqual(state['finalized'], state['ended'])
        self.assertEqual(state['end_of_updates'], state['ended'])
