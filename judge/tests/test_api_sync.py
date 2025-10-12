from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from judge.models import (
    Contest,
    ContestParticipation,
    ContestProblem,
    Language,
    Problem,
    ProblemGroup,
    ProblemType,
    Profile,
    Submission,
)


class ContestSyncAPITestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.password = 'testpass123'
        cls.user = user_model.objects.create_user(username='syncer', password=cls.password)
        cls.user_profile = Profile.objects.create(user=cls.user)

        cls.team_foo_user = user_model.objects.create_user(username='team_foo', password='pw')
        cls.team_foo_profile = Profile.objects.create(user=cls.team_foo_user)

        cls.team_bar_user = user_model.objects.create_user(username='team_bar', password='pw')
        cls.team_bar_profile = Profile.objects.create(user=cls.team_bar_user)

        now = timezone.now()
        cls.contest = Contest.objects.create(
            key='icpc-2025',
            name='ICPC 2025',
            start_time=now,
            end_time=now + timedelta(hours=5),
            is_visible=True,
            frozen_last_minutes=60,
            show_submission_list=True,
            format_name='icpc',
        )

        cls.problem_group = ProblemGroup.objects.create(name='default-group', full_name='Default Group')
        cls.problem_type = ProblemType.objects.create(name='algorithms', full_name='Algorithms')
        cls.language = Language.objects.create(
            key='PY',
            name='Python',
            short_name='PY',
            common_name='Python',
            ace='python',
            pygments='python',
            extension='py',
        )

        cls.problem_a = Problem.objects.create(
            code='A',
            name='Problem A',
            description='Statement',
            group=cls.problem_group,
            time_limit=1,
            memory_limit=65536,
            points=100,
            partial=False,
            is_public=True,
        )
        cls.problem_a.types.set([cls.problem_type])
        cls.problem_a.allowed_languages.set([cls.language])

        cls.problem_b = Problem.objects.create(
            code='B',
            name='Problem B',
            description='Statement',
            group=cls.problem_group,
            time_limit=1,
            memory_limit=65536,
            points=100,
            partial=False,
            is_public=True,
        )
        cls.problem_b.types.set([cls.problem_type])
        cls.problem_b.allowed_languages.set([cls.language])

        ContestProblem.objects.create(
            contest=cls.contest,
            problem=cls.problem_a,
            points=100,
            order=1,
        )
        ContestProblem.objects.create(
            contest=cls.contest,
            problem=cls.problem_b,
            points=100,
            order=2,
        )

        ContestParticipation.objects.create(
            contest=cls.contest,
            user=cls.team_foo_profile,
            score=500,
            cumtime=120,
            tiebreaker=0,
            virtual=ContestParticipation.LIVE,
        )
        ContestParticipation.objects.create(
            contest=cls.contest,
            user=cls.team_bar_profile,
            score=400,
            cumtime=150,
            tiebreaker=10,
            virtual=ContestParticipation.LIVE,
        )

        base_time = timezone.now()
        cls.final_submission = Submission.objects.create(
            user=cls.team_foo_profile,
            problem=cls.problem_b,
            language=cls.language,
            status='D',
            result='AC',
            points=100,
            contest_object=cls.contest,
        )
        cls.final_submission.date = base_time - timedelta(minutes=2)
        cls.final_submission.judged_date = base_time - timedelta(minutes=1)
        cls.final_submission.save(update_fields=['date', 'judged_date'])

        cls.processing_submission = Submission.objects.create(
            user=cls.team_bar_profile,
            problem=cls.problem_b,
            language=cls.language,
            status='P',
            result=None,
            contest_object=cls.contest,
        )
        cls.processing_submission.date = base_time
        cls.processing_submission.judged_date = base_time
        cls.processing_submission.save(update_fields=['date', 'judged_date'])

        cls.old_submission = Submission.objects.create(
            user=cls.team_bar_profile,
            problem=cls.problem_a,
            language=cls.language,
            status='D',
            result='WA',
            points=0,
            contest_object=cls.contest,
        )
        cls.old_submission.date = base_time - timedelta(days=1)
        cls.old_submission.judged_date = base_time - timedelta(days=1)
        cls.old_submission.save(update_fields=['date', 'judged_date'])

    def login(self):
        self.assertTrue(
            self.client.login(username=self.user.username, password=self.password),
            msg='Login failed for test user.',
        )

    def test_requires_login(self):
        endpoints = [
            '/api/contests/icpc-2025',
            '/api/contests/icpc-2025/problems',
            '/api/contests/icpc-2025/participants',
            '/api/contests/icpc-2025/submissions?from_timestamp=2020-01-01T00:00:00Z',
        ]
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint)
                self.assertEqual(response.status_code, 403)

    def test_contest_metadata(self):
        self.login()
        response = self.client.get('/api/contests/icpc-2025')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            data,
            {
                'code': self.contest.key,
                'start_time': self.contest.start_time.isoformat(),
                'end_time': self.contest.end_time.isoformat(),
                'frozen_at': (self.contest.end_time - timedelta(minutes=self.contest.frozen_last_minutes)).isoformat(),
            },
        )

    def test_problem_list(self):
        self.login()
        response = self.client.get('/api/contests/icpc-2025/problems')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {'code': 'A', 'contest': 'icpc-2025'},
                {'code': 'B', 'contest': 'icpc-2025'},
            ],
        )

    def test_participants_ranking(self):
        self.login()
        response = self.client.get('/api/contests/icpc-2025/participants')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {'user': 'team_foo', 'contest': 'icpc-2025', 'rank': 1},
                {'user': 'team_bar', 'contest': 'icpc-2025', 'rank': 2},
            ],
        )

    def test_submissions_filtering_and_status(self):
        self.login()
        from_ts = (self.final_submission.judged_date - timedelta(minutes=5)).isoformat()
        response = self.client.get(
            '/api/contests/icpc-2025/submissions',
            {'from_timestamp': from_ts},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]['id'], str(self.final_submission.id))

        response_all = self.client.get(
            '/api/contests/icpc-2025/submissions',
            {'from_timestamp': from_ts, 'status': 'all'},
        )
        self.assertEqual(response_all.status_code, 200)
        ids = [entry['id'] for entry in response_all.json()]
        self.assertListEqual(ids, [str(self.final_submission.id), str(self.processing_submission.id)])

    def test_submissions_requires_timestamp(self):
        self.login()
        response = self.client.get('/api/contests/icpc-2025/submissions')
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())