from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
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


@override_settings(GLOBAL_API_KEY='test-api-key-123')
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

    def test_requires_api_key(self):
        endpoints = [
            '/api/v2/sync/contest/icpc-2025',
            '/api/v2/sync/contest/icpc-2025/problems',
            '/api/v2/sync/contest/icpc-2025/participants',
            '/api/v2/sync/contest/icpc-2025/submissions?from_timestamp=2020-01-01T00:00:00Z',
        ]
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint)
                self.assertEqual(response.status_code, 403)

    def test_contest_metadata(self):
        response = self.client.get('/api/v2/sync/contest/icpc-2025', headers={'X-Global-API-Key': 'test-api-key-123'})
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
        response = self.client.get(
            '/api/v2/sync/contest/icpc-2025/problems',
            headers={'X-Global-API-Key': 'test-api-key-123'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {'code': 'A', 'contest': 'icpc-2025'},
                {'code': 'B', 'contest': 'icpc-2025'},
            ],
        )

    def test_participants_ranking(self):
        response = self.client.get(
            '/api/v2/sync/contest/icpc-2025/participants',
            headers={'X-Global-API-Key': 'test-api-key-123'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {'user': 'team_foo', 'contest': 'icpc-2025', 'rank': 1},
                {'user': 'team_bar', 'contest': 'icpc-2025', 'rank': 2},
            ],
        )

    def test_submissions_filtering_and_status(self):
        from_ts = (self.final_submission.judged_date - timedelta(minutes=5)).isoformat()
        response = self.client.get(
            '/api/v2/sync/contest/icpc-2025/submissions',
            {'from_timestamp': from_ts},
            headers={'X-Global-API-Key': 'test-api-key-123'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]['id'], str(self.final_submission.id))

        response_all = self.client.get(
            '/api/v2/sync/contest/icpc-2025/submissions',
            {'from_timestamp': from_ts, 'status': 'all'},
            headers={'X-Global-API-Key': 'test-api-key-123'},
        )
        self.assertEqual(response_all.status_code, 200)
        ids = [entry['id'] for entry in response_all.json()]
        self.assertListEqual(ids, [str(self.final_submission.id), str(self.processing_submission.id)])

    def test_submissions_requires_timestamp(self):
        response = self.client.get(
            '/api/v2/sync/contest/icpc-2025/submissions',
            headers={'X-Global-API-Key': 'test-api-key-123'},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    def test_global_api_key_authentication_header(self):
        """Test API access using X-Global-API-Key header"""
        with self.settings(GLOBAL_API_KEY='test-api-key-123'):
            response = self.client.get(
                '/api/v2/sync/contest/icpc-2025',
                headers={'X-Global-API-Key': 'test-api-key-123'},
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data['code'], self.contest.key)

    def test_global_api_key_authentication_query_param(self):
        """Test API access using global_api_key query parameter"""
        with self.settings(GLOBAL_API_KEY='test-api-key-456'):
            response = self.client.get(
                '/api/v2/sync/contest/icpc-2025/problems?global_api_key=test-api-key-456',
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(len(data), 2)

    def test_invalid_global_api_key(self):
        """Test API access with invalid API key returns 403"""
        with self.settings(GLOBAL_API_KEY='correct-api-key'):
            response = self.client.get(
                '/api/v2/sync/contest/icpc-2025',
                headers={'X-Global-API-Key': 'wrong-api-key'},
            )
            self.assertEqual(response.status_code, 403)

    def test_missing_global_api_key(self):
        """Test API access without API key returns 403"""
        with self.settings(GLOBAL_API_KEY='some-api-key'):
            response = self.client.get('/api/v2/sync/contest/icpc-2025')
            self.assertEqual(response.status_code, 403)

    def test_no_global_api_key_configured(self):
        """Test API access when GLOBAL_API_KEY is not configured"""
        with self.settings(GLOBAL_API_KEY=None):
            response = self.client.get('/api/v2/sync/contest/icpc-2025')
            self.assertEqual(response.status_code, 403)
