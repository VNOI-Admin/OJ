from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection, reset_queries
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from judge.models import Contest, Profile

User = get_user_model()

NUM_CONTESTS = 10
QUERY_BUDGET = 35


class ContestListPerfTest(TestCase):
    """Ensure ContestList does not generate N+1 queries for hidden-scoreboard contests."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='perf_user', password='pass')
        Profile.objects.create(user=cls.user)

        now = timezone.now()
        for i in range(NUM_CONTESTS):
            Contest.objects.create(
                key=f'hidden_contest_{i}',
                name=f'Hidden Contest {i}',
                start_time=now - timedelta(hours=2),
                end_time=now - timedelta(hours=1),
                is_visible=True,
                scoreboard_visibility=Contest.SCOREBOARD_HIDDEN,
            )

    def setUp(self):
        self.client = Client()
        self.client.login(username='perf_user', password='pass')

    def test_query_count_bounded(self):
        """Query count must stay within budget regardless of number of hidden-scoreboard contests."""
        with override_settings(DEBUG=True):
            reset_queries()
            response = self.client.get('/contests/')
            query_count = len(connection.queries)

        self.assertEqual(response.status_code, 200)
        print(f'\n  [{NUM_CONTESTS} hidden-scoreboard contests] query count: {query_count} (budget: {QUERY_BUDGET})')
        self.assertLessEqual(
            query_count, QUERY_BUDGET,
            msg=f'Expected <= {QUERY_BUDGET} queries for {NUM_CONTESTS} contests, got {query_count}.',
        )
