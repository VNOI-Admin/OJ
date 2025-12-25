from unittest.mock import PropertyMock

from django.http import Http404
from django.test import RequestFactory, TestCase
from django.utils import timezone

from judge.models import Contest, Language, Submission
from judge.models.tests.util import (
    CommonDataMixin,
    create_contest,
    create_contest_participation,
    create_contest_problem,
    create_organization,
    create_problem,
    create_user,
)
from judge.views.submission import (
    AllContestSubmissions,
    AllSubmissions,
    AllUserSubmissions,
    ProblemSubmissions,
    SubmissionsListBase,
    UserAllContestSubmissions,
    UserContestSubmissions,
    UserProblemSubmissions,
)


class SubmissionsListBaseQuerysetTestCase(CommonDataMixin, TestCase):
    """Test cases for SubmissionsListBase.get_queryset method.

    This test class covers all branches and conditions in the get_queryset function:
    1. Contest scoped cases (is_contest_scoped=True)
    2. Non-contest scoped cases (is_contest_scoped=False)
    3. Filter cases (language, status, organization)
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls._now = timezone.now()

        # Create additional users for testing
        cls.users.update({
            'contest_author': create_user(
                username='contest_author',
            ),
            'contest_curator': create_user(
                username='contest_curator',
            ),
            'see_private_contest': create_user(
                username='see_private_contest',
                user_permissions=('see_private_contest',),
            ),
            'other_user': create_user(
                username='other_user',
            ),
        })

        # Create problems
        cls.public_problem = create_problem(
            code='public_problem',
            is_public=True,
        )
        cls.private_problem = create_problem(
            code='private_problem',
            is_public=False,
        )
        cls.org_problem = create_problem(
            code='org_problem',
            is_public=True,
            is_organization_private=True,
            organizations=('open',),
        )

        # Create contests with different configurations
        cls.visible_scoreboard_contest = create_contest(
            key='visible_scoreboard',
            start_time=cls._now - timezone.timedelta(days=1),
            end_time=cls._now + timezone.timedelta(days=100),
            is_visible=True,
            scoreboard_visibility=Contest.SCOREBOARD_VISIBLE,
        )

        cls.hidden_scoreboard_contest = create_contest(
            key='hidden_scoreboard',
            start_time=cls._now - timezone.timedelta(days=1),
            end_time=cls._now + timezone.timedelta(days=100),
            is_visible=True,
            scoreboard_visibility=Contest.SCOREBOARD_AFTER_CONTEST,
        )

        cls.ended_contest = create_contest(
            key='ended_contest',
            start_time=cls._now - timezone.timedelta(days=10),
            end_time=cls._now - timezone.timedelta(days=1),
            is_visible=True,
            scoreboard_visibility=Contest.SCOREBOARD_AFTER_CONTEST,
        )

        cls.author_contest = create_contest(
            key='author_contest',
            start_time=cls._now - timezone.timedelta(days=1),
            end_time=cls._now + timezone.timedelta(days=100),
            is_visible=True,
            scoreboard_visibility=Contest.SCOREBOARD_AFTER_CONTEST,
            authors=('contest_author',),
        )

        cls.curator_contest = create_contest(
            key='curator_contest',
            start_time=cls._now - timezone.timedelta(days=1),
            end_time=cls._now + timezone.timedelta(days=100),
            is_visible=True,
            scoreboard_visibility=Contest.SCOREBOARD_AFTER_CONTEST,
            curators=('contest_curator',),
        )

        cls.full_submission_list_contest = create_contest(
            key='full_list_contest',
            start_time=cls._now - timezone.timedelta(days=1),
            end_time=cls._now + timezone.timedelta(days=100),
            is_visible=True,
            scoreboard_visibility=Contest.SCOREBOARD_VISIBLE,
            authors=('contest_author',),
        )

        # Create submissions for various test cases
        # Submission without contest (normal user)
        cls.sub_no_contest_normal = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
        )

        # Submission without contest (other user)
        cls.sub_no_contest_other = Submission.objects.create(
            user=cls.users['other_user'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='WA',
            status='D',
        )

        # Submission in visible scoreboard contest
        cls.sub_visible_scoreboard = Submission.objects.create(
            user=cls.users['other_user'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
            contest_object=cls.visible_scoreboard_contest,
        )

        # Submission in hidden scoreboard contest
        cls.sub_hidden_scoreboard = Submission.objects.create(
            user=cls.users['other_user'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
            contest_object=cls.hidden_scoreboard_contest,
        )

        # Submission in ended contest
        cls.sub_ended_contest = Submission.objects.create(
            user=cls.users['other_user'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
            contest_object=cls.ended_contest,
        )

        # Submission in author's contest
        cls.sub_author_contest = Submission.objects.create(
            user=cls.users['other_user'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
            contest_object=cls.author_contest,
        )

        # Submission in curator's contest
        cls.sub_curator_contest = Submission.objects.create(
            user=cls.users['other_user'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
            contest_object=cls.curator_contest,
        )

        # Own submission in hidden scoreboard contest
        cls.sub_hidden_own = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
            contest_object=cls.hidden_scoreboard_contest,
        )

        # Submission for full list contest testing
        cls.sub_full_list_normal = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
            contest_object=cls.full_submission_list_contest,
        )

        cls.sub_full_list_other = Submission.objects.create(
            user=cls.users['other_user'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='WA',
            status='D',
            contest_object=cls.full_submission_list_contest,
        )

        # Submission with C++ language for filter testing
        # Get or create a C++ language for testing
        cls.cpp_language, _ = Language.objects.get_or_create(
            key='CPP14',
            defaults={
                'name': 'C++ 14',
                'short_name': 'C++14',
                'common_name': 'C++',
            },
        )
        cls.sub_cpp = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.public_problem,
            language=cls.cpp_language,
            result='AC',
            status='D',
        )

        # Submission with TLE result for filter testing
        cls.sub_tle = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='TLE',
            status='D',
        )

        # Submission with Processing status for filter testing
        cls.sub_processing = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result=None,
            status='P',
        )

        # Private problem with normal user as author
        cls.private_problem_no_access = create_problem(
            code='private_problem_no_access',
            is_public=False,
            authors=('normal',),
        )
        cls.sub_private_no_access = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.private_problem_no_access,
            language=Language.get_python3(),
            result='AC',
            status='D',
        )

        # Private problem in a public contest
        cls.private_problem_in_public_contest = create_problem(
            code='private_in_pub_contest',
            is_public=False,
        )
        cls.public_contest_with_private_problem = create_contest(
            key='pub_contest_w_private_prob',
            start_time=cls._now - timezone.timedelta(days=1),
            end_time=cls._now + timezone.timedelta(days=100),
            is_visible=True,
            scoreboard_visibility=Contest.SCOREBOARD_VISIBLE,
            show_submission_list=True,  # Critical for this test
        )
        create_contest_problem(
            contest=cls.public_contest_with_private_problem,
            problem=cls.private_problem_in_public_contest,
        )
        # Participate both normal and other_user in this contest
        create_contest_participation(contest=cls.public_contest_with_private_problem, user='normal')
        create_contest_participation(contest=cls.public_contest_with_private_problem, user='other_user')

        cls.sub_private_in_pub_contest_normal = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.private_problem_in_public_contest,
            language=Language.get_python3(),
            result='AC',
            status='D',
            contest_object=cls.public_contest_with_private_problem,
        )
        cls.sub_private_in_pub_contest_other = Submission.objects.create(
            user=cls.users['other_user'].profile,
            problem=cls.private_problem_in_public_contest,
            language=Language.get_python3(),
            result='WA',
            status='D',
            contest_object=cls.public_contest_with_private_problem,
        )

        # Organization-private problem in a public contest
        cls.public_contest_with_org_problem = create_contest(
            key='pub_contest_w_org_prob',
            start_time=cls._now - timezone.timedelta(days=1),
            end_time=cls._now + timezone.timedelta(days=100),
            is_visible=True,
            scoreboard_visibility=Contest.SCOREBOARD_VISIBLE,
            show_submission_list=True,  # Critical for this test
        )
        create_contest_problem(
            contest=cls.public_contest_with_org_problem,
            problem=cls.org_problem,  # The problem 'org_problem' is organization-private
        )
        # Participate both normal and other_user in this contest
        create_contest_participation(contest=cls.public_contest_with_org_problem, user='normal')
        create_contest_participation(contest=cls.public_contest_with_org_problem, user='other_user')

        cls.sub_org_in_pub_contest_normal = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.org_problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
            contest_object=cls.public_contest_with_org_problem,
        )
        cls.sub_org_in_pub_contest_other = Submission.objects.create(
            user=cls.users['other_user'].profile,
            problem=cls.org_problem,
            language=Language.get_python3(),
            result='WA',
            status='D',
            contest_object=cls.public_contest_with_org_problem,
        )

        # Add normal user to organization for filter testing
        cls.users['normal'].profile.organizations.add(cls.organizations['open'])

    def _create_view_instance(self, user, is_contest_scoped=False, contest=None,
                              selected_languages=None, selected_statuses=None,
                              selected_organization=None, show_problem=True):
        """Helper to create a mock SubmissionsListBase instance for testing."""
        factory = RequestFactory()
        request = factory.get('/submissions/')
        request.user = user
        request.profile = user.profile if hasattr(user, 'profile') else None
        request.LANGUAGE_CODE = 'en'

        view = SubmissionsListBase()
        view.request = request
        view.show_problem = show_problem
        view.selected_languages = selected_languages or set()
        view.selected_statuses = selected_statuses or set()
        view.selected_organization = selected_organization

        # Mock is_contest_scoped property
        type(view).is_contest_scoped = PropertyMock(return_value=is_contest_scoped)

        if is_contest_scoped and contest:
            type(view).contest = PropertyMock(return_value=contest)

        return view

    # =========================================================================
    # Contest Scoped Tests (is_contest_scoped=True)
    # =========================================================================

    def test_contest_scoped_private_problem_in_public_contest(self):
        """
        Test that a participant in a public contest can see other participants' submissions
        to a private problem within that contest's submission list.
        """
        # User 'normal' views contest-scoped submissions
        view = self._create_view_instance(
            user=self.users['normal'],
            is_contest_scoped=True,
            contest=self.public_contest_with_private_problem,
        )
        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should see both their own and other_user's submissions to the private problem
        self.assertIn(self.sub_private_in_pub_contest_normal.id, submission_ids)
        self.assertIn(self.sub_private_in_pub_contest_other.id, submission_ids)

        # User 'normal' views non-contest-scoped (global) submissions
        view = self._create_view_instance(
            user=self.users['normal'],
            is_contest_scoped=False,
        )
        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should NOT see other_user's submission to the private problem on global list
        # because the problem itself is private and 'normal' is not its author/curator/tester
        self.assertNotIn(self.sub_private_in_pub_contest_other.id, submission_ids)
        # Should also NOT see their own submission to this private problem on global list
        # if they are not considered an author/curator/tester of the private problem itself
        # (they are just a participant in the contest). The Problem.get_visible_problems
        # logic will filter this out as well.
        self.assertNotIn(self.sub_private_in_pub_contest_normal.id, submission_ids)

        # Superuser should see all submissions for the private problem in the public contest globally
        view = self._create_view_instance(
            user=self.users['superuser'],
            is_contest_scoped=False,
        )
        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))
        self.assertIn(self.sub_private_in_pub_contest_normal.id, submission_ids)
        self.assertIn(self.sub_private_in_pub_contest_other.id, submission_ids)

    def test_contest_scoped_org_problem_in_public_contest(self):
        """
        Test that a participant in a public contest (who is NOT in the problem's organization)
        can see other participants' submissions to an organization-private problem
        within that contest's submission list.
        """
        # User 'other_user' is NOT in 'open' organization, but is a participant in the contest.
        view = self._create_view_instance(
            user=self.users['other_user'],
            is_contest_scoped=True,
            contest=self.public_contest_with_org_problem,
        )
        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should see both their own and normal user's submissions to the org-private problem
        # because contest rules override problem-level visibility here.
        self.assertIn(self.sub_org_in_pub_contest_normal.id, submission_ids)
        self.assertIn(self.sub_org_in_pub_contest_other.id, submission_ids)

        # User 'other_user' views non-contest-scoped (global) submissions
        view = self._create_view_instance(
            user=self.users['other_user'],
            is_contest_scoped=False,
        )
        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should NOT see normal user's submission to the org-private problem on global list
        # because other_user is not in the 'open' organization.
        self.assertNotIn(self.sub_org_in_pub_contest_normal.id, submission_ids)
        # Should also NOT see their own submission to this org-private problem on global list.
        self.assertNotIn(self.sub_org_in_pub_contest_other.id, submission_ids)

        # Superuser should see all submissions for the org-private problem in the public contest globally
        view = self._create_view_instance(
            user=self.users['superuser'],
            is_contest_scoped=False,
        )
        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))
        self.assertIn(self.sub_org_in_pub_contest_normal.id, submission_ids)
        self.assertIn(self.sub_org_in_pub_contest_other.id, submission_ids)

    def test_contest_scoped_user_can_see_full_submission_list(self):
        """Test that when user can see full submission list, all contest submissions are returned."""
        view = self._create_view_instance(
            user=self.users['contest_author'],
            is_contest_scoped=True,
            contest=self.full_submission_list_contest,
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should include both submissions in the contest
        self.assertIn(self.sub_full_list_normal.id, submission_ids)
        self.assertIn(self.sub_full_list_other.id, submission_ids)

    def test_contest_scoped_user_cannot_see_full_submission_list(self):
        """Test that when user cannot see full submission list, only own submissions are returned."""
        # Create a participation for normal user in hidden scoreboard contest
        create_contest_participation(
            contest=self.hidden_scoreboard_contest,
            user='normal',
        )

        view = self._create_view_instance(
            user=self.users['normal'],
            is_contest_scoped=True,
            contest=self.hidden_scoreboard_contest,
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should only include normal user's own submissions
        self.assertIn(self.sub_hidden_own.id, submission_ids)
        self.assertNotIn(self.sub_hidden_scoreboard.id, submission_ids)

    def test_contest_scoped_filters_by_contest(self):
        """Test that contest scoped view only returns submissions from that contest."""
        view = self._create_view_instance(
            user=self.users['contest_author'],
            is_contest_scoped=True,
            contest=self.full_submission_list_contest,
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should not include submissions from other contests or no contest
        self.assertNotIn(self.sub_no_contest_normal.id, submission_ids)
        self.assertNotIn(self.sub_visible_scoreboard.id, submission_ids)
        self.assertNotIn(self.sub_hidden_scoreboard.id, submission_ids)

    # =========================================================================
    # Non-Contest Scoped Tests (is_contest_scoped=False)
    # =========================================================================

    def test_non_contest_scoped_private_problem_visibility(self):
        """Test visibility of submissions to a truly private problem."""
        # Other user should not see submissions to a private problem authored by 'normal' user
        view = self._create_view_instance(
            user=self.users['other_user'],
            is_contest_scoped=False,
        )
        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))
        self.assertNotIn(self.sub_private_no_access.id, submission_ids)

        # Author ('normal' user) should see their own submissions to their private problem
        view = self._create_view_instance(
            user=self.users['normal'],
            is_contest_scoped=False,
        )
        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))
        self.assertIn(self.sub_private_no_access.id, submission_ids)

        # Superuser should see submissions to a private problem
        view = self._create_view_instance(
            user=self.users['superuser'],
            is_contest_scoped=False,
        )
        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))
        self.assertIn(self.sub_private_no_access.id, submission_ids)

    def test_non_contest_scoped_with_see_private_contest_permission(self):
        """Test that user with see_private_contest permission sees all submissions."""
        view = self._create_view_instance(
            user=self.users['see_private_contest'],
            is_contest_scoped=False,
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should include all submissions (for visible problems)
        self.assertIn(self.sub_no_contest_normal.id, submission_ids)
        self.assertIn(self.sub_no_contest_other.id, submission_ids)
        self.assertIn(self.sub_visible_scoreboard.id, submission_ids)
        self.assertIn(self.sub_hidden_scoreboard.id, submission_ids)
        self.assertIn(self.sub_ended_contest.id, submission_ids)

    def test_non_contest_scoped_own_submissions(self):
        """Test that user sees their own submissions without see_private_contest permission."""
        view = self._create_view_instance(
            user=self.users['normal'],
            is_contest_scoped=False,
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should include own submissions
        self.assertIn(self.sub_no_contest_normal.id, submission_ids)
        self.assertIn(self.sub_hidden_own.id, submission_ids)

    def test_non_contest_scoped_visible_scoreboard_contest(self):
        """Test that submissions from visible scoreboard contests are visible."""
        view = self._create_view_instance(
            user=self.users['normal'],
            is_contest_scoped=False,
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should include submissions from visible scoreboard contest
        self.assertIn(self.sub_visible_scoreboard.id, submission_ids)

    def test_non_contest_scoped_ended_contest(self):
        """Test that submissions from ended contests are visible."""
        view = self._create_view_instance(
            user=self.users['normal'],
            is_contest_scoped=False,
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should include submissions from ended contest
        self.assertIn(self.sub_ended_contest.id, submission_ids)

    def test_non_contest_scoped_author_sees_contest_submissions(self):
        """Test that contest author can see submissions from their contest."""
        view = self._create_view_instance(
            user=self.users['contest_author'],
            is_contest_scoped=False,
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should include submissions from contest where user is author
        self.assertIn(self.sub_author_contest.id, submission_ids)
        self.assertIn(self.sub_full_list_other.id, submission_ids)

    def test_non_contest_scoped_curator_sees_contest_submissions(self):
        """Test that contest curator can see submissions from their contest."""
        view = self._create_view_instance(
            user=self.users['contest_curator'],
            is_contest_scoped=False,
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should include submissions from contest where user is curator
        self.assertIn(self.sub_curator_contest.id, submission_ids)

    def test_non_contest_scoped_hidden_scoreboard_not_visible_to_others(self):
        """Test that submissions from hidden scoreboard ongoing contests are not visible to others."""
        view = self._create_view_instance(
            user=self.users['normal'],
            is_contest_scoped=False,
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should not include other users' submissions from hidden scoreboard ongoing contest
        self.assertNotIn(self.sub_hidden_scoreboard.id, submission_ids)

    def test_non_contest_scoped_no_contest_visible(self):
        """Test that submissions without contest are visible."""
        view = self._create_view_instance(
            user=self.users['normal'],
            is_contest_scoped=False,
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should include submissions without contest
        self.assertIn(self.sub_no_contest_normal.id, submission_ids)
        self.assertIn(self.sub_no_contest_other.id, submission_ids)

    def test_non_contest_scoped_superuser_sees_all(self):
        """Test that superuser can see all submissions."""
        view = self._create_view_instance(
            user=self.users['superuser'],
            is_contest_scoped=False,
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Superuser should see all submissions
        self.assertIn(self.sub_no_contest_normal.id, submission_ids)
        self.assertIn(self.sub_hidden_scoreboard.id, submission_ids)
        self.assertIn(self.sub_author_contest.id, submission_ids)

    # =========================================================================
    # Filter Tests
    # =========================================================================

    def test_filter_by_language(self):
        """Test filtering by selected languages."""
        view = self._create_view_instance(
            user=self.users['superuser'],
            is_contest_scoped=False,
            selected_languages={'PY3'},
        )

        queryset = view.get_queryset()

        # All submissions should be Python 3
        for submission in queryset:
            self.assertEqual(submission.language.key, 'PY3')

    def test_filter_by_multiple_languages(self):
        """Test filtering by multiple selected languages."""
        view = self._create_view_instance(
            user=self.users['superuser'],
            is_contest_scoped=False,
            selected_languages={'PY3', 'CPP14'},
        )

        queryset = view.get_queryset()

        # All submissions should be Python 3 or C++14
        for submission in queryset:
            self.assertIn(submission.language.key, {'PY3', 'CPP14'})

    def test_filter_by_result_status(self):
        """Test filtering by result status."""
        view = self._create_view_instance(
            user=self.users['superuser'],
            is_contest_scoped=False,
            selected_statuses={'AC'},
        )

        queryset = view.get_queryset()

        # All submissions should have AC result
        for submission in queryset:
            self.assertEqual(submission.result, 'AC')

    def test_filter_by_processing_status(self):
        """Test filtering by processing status (status field, not result)."""
        view = self._create_view_instance(
            user=self.users['superuser'],
            is_contest_scoped=False,
            selected_statuses={'P'},
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should include processing submission
        self.assertIn(self.sub_processing.id, submission_ids)

    def test_filter_by_multiple_statuses(self):
        """Test filtering by multiple statuses."""
        view = self._create_view_instance(
            user=self.users['superuser'],
            is_contest_scoped=False,
            selected_statuses={'AC', 'TLE'},
        )

        queryset = view.get_queryset()

        # All submissions should have AC or TLE result
        for submission in queryset:
            self.assertIn(submission.result, {'AC', 'TLE'})

    def test_filter_by_organization(self):
        """Test filtering by user organization."""
        view = self._create_view_instance(
            user=self.users['superuser'],
            is_contest_scoped=False,
            selected_organization=self.organizations['open'].pk,
        )

        queryset = view.get_queryset()

        # All submissions should be from users in the organization
        for submission in queryset:
            self.assertTrue(
                submission.user.organizations.filter(pk=self.organizations['open'].pk).exists(),
            )

    def test_combined_filters(self):
        """Test combining multiple filters."""
        view = self._create_view_instance(
            user=self.users['superuser'],
            is_contest_scoped=False,
            selected_languages={'PY3'},
            selected_statuses={'AC'},
            selected_organization=self.organizations['open'].pk,
        )

        queryset = view.get_queryset()

        # All submissions should match all filters
        for submission in queryset:
            self.assertEqual(submission.language.key, 'PY3')
            self.assertEqual(submission.result, 'AC')
            self.assertTrue(
                submission.user.organizations.filter(pk=self.organizations['open'].pk).exists(),
            )

    def test_empty_language_filter(self):
        """Test that empty language filter returns all languages."""
        view = self._create_view_instance(
            user=self.users['superuser'],
            is_contest_scoped=False,
            selected_languages=set(),
        )

        queryset = view.get_queryset()

        # Should return submissions with different languages
        languages = set(queryset.values_list('language__key', flat=True))
        self.assertGreater(len(languages), 1)

    def test_empty_status_filter(self):
        """Test that empty status filter returns all statuses."""
        view = self._create_view_instance(
            user=self.users['superuser'],
            is_contest_scoped=False,
            selected_statuses=set(),
        )

        queryset = view.get_queryset()

        # Should return submissions with different results
        results = set(queryset.values_list('result', flat=True))
        self.assertGreater(len(results), 1)

    # =========================================================================
    # Edge Cases
    # =========================================================================

    def test_show_problem_false(self):
        """Test that get_queryset works when show_problem is False."""
        view = self._create_view_instance(
            user=self.users['superuser'],
            is_contest_scoped=False,
            show_problem=False,
        )

        queryset = view.get_queryset()

        # Should still return submissions
        self.assertGreater(queryset.count(), 0)

    def test_ordering_by_id_descending(self):
        """Test that submissions are ordered by id descending."""
        view = self._create_view_instance(
            user=self.users['superuser'],
            is_contest_scoped=False,
        )

        queryset = view.get_queryset()
        ids = list(queryset.values_list('id', flat=True))

        # Check that IDs are in descending order
        self.assertEqual(ids, sorted(ids, reverse=True))


class AllUserSubmissionsTestCase(CommonDataMixin, TestCase):
    """Test cases for AllUserSubmissions view."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls._now = timezone.now()

        cls.users.update({
            'other_user': create_user(username='other_user'),
        })

        cls.public_problem = create_problem(code='public_problem', is_public=True)

        # Create submissions for different users
        cls.sub_normal = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
        )

        cls.sub_other = Submission.objects.create(
            user=cls.users['other_user'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='WA',
            status='D',
        )

    def _create_view_instance(self, request_user, target_user):
        """Helper to create AllUserSubmissions view instance."""
        factory = RequestFactory()
        request = factory.get(f'/user/{target_user.username}/submissions/')
        request.user = request_user
        request.profile = request_user.profile if hasattr(request_user, 'profile') else None
        request.LANGUAGE_CODE = 'en'

        view = AllUserSubmissions()
        view.request = request
        view.profile = target_user.profile
        view.username = target_user.username
        view.show_problem = True
        view.selected_languages = set()
        view.selected_statuses = set()
        view.selected_organization = None

        return view

    def test_filters_by_user(self):
        """Test that only target user's submissions are returned."""
        view = self._create_view_instance(
            request_user=self.users['superuser'],
            target_user=self.users['normal'],
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should only include normal user's submissions
        self.assertIn(self.sub_normal.id, submission_ids)
        self.assertNotIn(self.sub_other.id, submission_ids)

    def test_viewing_other_users_submissions(self):
        """Test that one user can view another user's submissions."""
        view = self._create_view_instance(
            request_user=self.users['normal'],
            target_user=self.users['other_user'],
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should include other user's submissions
        self.assertIn(self.sub_other.id, submission_ids)
        self.assertNotIn(self.sub_normal.id, submission_ids)


class ProblemSubmissionsTestCase(CommonDataMixin, TestCase):
    """Test cases for ProblemSubmissions and ProblemSubmissionsBase views."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls._now = timezone.now()

        cls.users.update({
            'other_user': create_user(username='other_user'),
        })

        cls.public_problem = create_problem(code='public_problem', is_public=True)
        cls.other_problem = create_problem(code='other_problem', is_public=True)

        # Create submissions for different problems
        cls.sub_public_problem = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
        )

        cls.sub_other_problem = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.other_problem,
            language=Language.get_python3(),
            result='WA',
            status='D',
        )

        # Truly private problem, not part of any contest, no authors/curators by default
        cls.super_private_problem = create_problem(
            code='super_private_problem',
            is_public=False,
        )
        cls.sub_super_private_normal = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.super_private_problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
        )

        # A contest that 'normal' user participates in, but doesn't contain `super_private_problem`
        cls.other_contest_for_normal_user = create_contest(
            key='other_contest',
            start_time=cls._now - timezone.timedelta(days=1),
            end_time=cls._now + timezone.timedelta(days=100),
        )
        create_contest_participation(contest=cls.other_contest_for_normal_user, user='normal')

    def _create_view_instance(self, user, problem):
        """Helper to create ProblemSubmissions view instance."""
        factory = RequestFactory()
        request = factory.get(f'/problem/{problem.code}/submissions/')
        request.user = user
        request.profile = user.profile if hasattr(user, 'profile') else None
        request.LANGUAGE_CODE = 'en'

        view = ProblemSubmissions()
        view.request = request
        view.problem = problem
        view.problem_name = problem.name
        view.show_problem = False
        view.selected_languages = set()
        view.selected_statuses = set()
        view.selected_organization = None

        return view

    def test_filters_by_problem(self):
        """Test that only submissions for the specified problem are returned."""
        view = self._create_view_instance(
            user=self.users['superuser'],
            problem=self.public_problem,
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should only include submissions for public_problem
        self.assertIn(self.sub_public_problem.id, submission_ids)
        self.assertNotIn(self.sub_other_problem.id, submission_ids)

    def test_global_access_to_super_private_problem_not_in_current_contest(self):
        """
        Test that a normal user cannot access submissions for a truly private problem
        globally if it's not in their current contest AND they are not problem author.
        """
        normal_user_profile = self.users['normal'].profile
        original_current_contest = normal_user_profile.current_contest

        try:
            # Set normal user to be in a contest, but one that does NOT contain super_private_problem
            normal_user_profile.current_contest = self.other_contest_for_normal_user.users.get(user=normal_user_profile)

            # Use RequestFactory to simulate a request
            factory = RequestFactory()
            request = factory.get(f'/problem/{self.super_private_problem.code}/submissions/')
            request.user = self.users['normal']
            request.profile = self.users['normal'].profile
            request.LANGUAGE_CODE = 'en'

            view = ProblemSubmissions()
            # Manually set up view attributes
            view.setup(request, problem=self.super_private_problem.code)  # This populates view.kwargs, etc.
            view.request = request  # Assign request to view
            view.problem = self.super_private_problem  # Assign problem instance
            view.problem_name = self.super_private_problem.translated_name(request.LANGUAGE_CODE)

            # Call the dispatch method which orchestrates the view logic, including access_check
            with self.assertRaises(Http404):
                view.dispatch(request, problem=self.super_private_problem.code)

        finally:
            # Restore original current_contest
            normal_user_profile.current_contest = original_current_contest

    def test_global_access_to_super_private_problem_with_permission(self):
        """
        Test that superuser can access submissions for a truly private problem globally.
        """
        view = self._create_view_instance(
            user=self.users['superuser'],
            problem=self.super_private_problem,
        )
        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))
        self.assertIn(self.sub_super_private_normal.id, submission_ids)


class UserProblemSubmissionsTestCase(CommonDataMixin, TestCase):
    """Test cases for UserProblemSubmissions view."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls._now = timezone.now()

        cls.users.update({
            'other_user': create_user(username='other_user'),
        })

        cls.public_problem = create_problem(code='public_problem', is_public=True)

        # Create submissions for different users on same problem
        cls.sub_normal = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
        )

        cls.sub_other = Submission.objects.create(
            user=cls.users['other_user'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='WA',
            status='D',
        )

    def _create_view_instance(self, request_user, target_user, problem):
        """Helper to create UserProblemSubmissions view instance."""
        factory = RequestFactory()
        request = factory.get(f'/problem/{problem.code}/submissions/{target_user.username}/')
        request.user = request_user
        request.profile = request_user.profile if hasattr(request_user, 'profile') else None
        request.LANGUAGE_CODE = 'en'

        view = UserProblemSubmissions()
        view.request = request
        view.profile = target_user.profile
        view.username = target_user.username
        view.problem = problem
        view.problem_name = problem.name
        view.show_problem = False
        view.selected_languages = set()
        view.selected_statuses = set()
        view.selected_organization = None

        return view

    def test_filters_by_user_and_problem(self):
        """Test that only target user's submissions for the specified problem are returned."""
        view = self._create_view_instance(
            request_user=self.users['superuser'],
            target_user=self.users['normal'],
            problem=self.public_problem,
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should only include normal user's submissions for public_problem
        self.assertIn(self.sub_normal.id, submission_ids)
        self.assertNotIn(self.sub_other.id, submission_ids)


class AllSubmissionsTestCase(CommonDataMixin, TestCase):
    """Test cases for AllSubmissions view."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls._now = timezone.now()

        cls.public_problem = create_problem(code='public_problem', is_public=True)

        cls.sub_1 = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
        )

        cls.sub_2 = Submission.objects.create(
            user=cls.users['superuser'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='WA',
            status='D',
        )

    def _create_view_instance(self, user):
        """Helper to create AllSubmissions view instance."""
        factory = RequestFactory()
        request = factory.get('/submissions/')
        request.user = user
        request.profile = user.profile if hasattr(user, 'profile') else None
        request.LANGUAGE_CODE = 'en'

        view = AllSubmissions()
        view.request = request
        view.show_problem = True
        view.selected_languages = set()
        view.selected_statuses = set()
        view.selected_organization = None

        return view

    def test_returns_all_visible_submissions(self):
        """Test that all visible submissions are returned."""
        view = self._create_view_instance(user=self.users['superuser'])

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should include all submissions
        self.assertIn(self.sub_1.id, submission_ids)
        self.assertIn(self.sub_2.id, submission_ids)


class AllContestSubmissionsTestCase(CommonDataMixin, TestCase):
    """Test cases for AllContestSubmissions view (ForceContestMixin)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls._now = timezone.now()

        cls.users.update({
            'contest_author': create_user(username='contest_author'),
            'other_user': create_user(username='other_user'),
        })

        cls.public_problem = create_problem(code='public_problem', is_public=True)

        cls.contest = create_contest(
            key='test_contest',
            start_time=cls._now - timezone.timedelta(days=1),
            end_time=cls._now + timezone.timedelta(days=100),
            is_visible=True,
            scoreboard_visibility=Contest.SCOREBOARD_VISIBLE,
            authors=('contest_author',),
        )

        # Add problem to contest
        create_contest_problem(
            contest=cls.contest,
            problem=cls.public_problem,
        )

        # Create submissions in and out of contest
        cls.sub_in_contest = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
            contest_object=cls.contest,
        )

        cls.sub_outside_contest = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='WA',
            status='D',
        )

    def _create_view_instance(self, user, contest):
        """Helper to create AllContestSubmissions view instance."""
        factory = RequestFactory()
        request = factory.get(f'/contest/{contest.key}/submissions/')
        request.user = user
        request.profile = user.profile if hasattr(user, 'profile') else None
        request.LANGUAGE_CODE = 'en'

        view = AllContestSubmissions()
        view.request = request
        view._contest = contest
        view.show_problem = True
        view.selected_languages = set()
        view.selected_statuses = set()
        view.selected_organization = None

        return view

    def test_filters_by_contest(self):
        """Test that only submissions from the contest are returned."""
        view = self._create_view_instance(
            user=self.users['contest_author'],
            contest=self.contest,
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should only include submissions from the contest
        self.assertIn(self.sub_in_contest.id, submission_ids)
        self.assertNotIn(self.sub_outside_contest.id, submission_ids)


class UserAllContestSubmissionsTestCase(CommonDataMixin, TestCase):
    """Test cases for UserAllContestSubmissions view."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls._now = timezone.now()

        cls.users.update({
            'contest_author': create_user(username='contest_author'),
            'other_user': create_user(username='other_user'),
        })

        cls.public_problem = create_problem(code='public_problem', is_public=True)

        cls.contest = create_contest(
            key='test_contest',
            start_time=cls._now - timezone.timedelta(days=1),
            end_time=cls._now + timezone.timedelta(days=100),
            is_visible=True,
            scoreboard_visibility=Contest.SCOREBOARD_VISIBLE,
            authors=('contest_author',),
        )

        create_contest_problem(contest=cls.contest, problem=cls.public_problem)

        # Create submissions from different users in the contest
        cls.sub_normal_in_contest = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
            contest_object=cls.contest,
        )

        cls.sub_other_in_contest = Submission.objects.create(
            user=cls.users['other_user'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='WA',
            status='D',
            contest_object=cls.contest,
        )

    def _create_view_instance(self, request_user, target_user, contest):
        """Helper to create UserAllContestSubmissions view instance."""
        factory = RequestFactory()
        request = factory.get(f'/contest/{contest.key}/submissions/{target_user.username}/')
        request.user = request_user
        request.profile = request_user.profile if hasattr(request_user, 'profile') else None
        request.LANGUAGE_CODE = 'en'

        view = UserAllContestSubmissions()
        view.request = request
        view._contest = contest
        view.profile = target_user.profile
        view.username = target_user.username
        view.show_problem = True
        view.selected_languages = set()
        view.selected_statuses = set()
        view.selected_organization = None

        return view

    def test_filters_by_user_and_contest(self):
        """Test that only target user's submissions in the contest are returned."""
        view = self._create_view_instance(
            request_user=self.users['contest_author'],
            target_user=self.users['normal'],
            contest=self.contest,
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should only include normal user's submissions in the contest
        self.assertIn(self.sub_normal_in_contest.id, submission_ids)
        self.assertNotIn(self.sub_other_in_contest.id, submission_ids)


class UserContestSubmissionsTestCase(CommonDataMixin, TestCase):
    """Test cases for UserContestSubmissions view."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls._now = timezone.now()

        cls.users.update({
            'contest_author': create_user(username='contest_author'),
            'other_user': create_user(username='other_user'),
        })

        cls.public_problem = create_problem(code='public_problem', is_public=True)
        cls.other_problem = create_problem(code='other_problem', is_public=True)

        cls.contest = create_contest(
            key='test_contest',
            start_time=cls._now - timezone.timedelta(days=1),
            end_time=cls._now + timezone.timedelta(days=100),
            is_visible=True,
            scoreboard_visibility=Contest.SCOREBOARD_VISIBLE,
            authors=('contest_author',),
        )

        create_contest_problem(contest=cls.contest, problem=cls.public_problem)
        create_contest_problem(contest=cls.contest, problem=cls.other_problem)

        # Create contest participation for normal user
        create_contest_participation(contest=cls.contest, user='normal')

        # Create submissions for different problems
        cls.sub_public_problem = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
            contest_object=cls.contest,
        )

        cls.sub_other_problem = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.other_problem,
            language=Language.get_python3(),
            result='WA',
            status='D',
            contest_object=cls.contest,
        )

    def _create_view_instance(self, request_user, target_user, contest, problem):
        """Helper to create UserContestSubmissions view instance."""
        factory = RequestFactory()
        request = factory.get(
            f'/contest/{contest.key}/submissions/{target_user.username}/{problem.code}/',
        )
        request.user = request_user
        request.profile = request_user.profile if hasattr(request_user, 'profile') else None
        request.LANGUAGE_CODE = 'en'

        view = UserContestSubmissions()
        view.request = request
        view._contest = contest
        view.profile = target_user.profile
        view.username = target_user.username
        view.problem = problem
        view.problem_name = problem.name
        view.show_problem = False
        view.selected_languages = set()
        view.selected_statuses = set()
        view.selected_organization = None

        return view

    def test_filters_by_user_contest_and_problem(self):
        """Test that only target user's submissions for problem in contest are returned."""
        view = self._create_view_instance(
            request_user=self.users['contest_author'],
            target_user=self.users['normal'],
            contest=self.contest,
            problem=self.public_problem,
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should only include submissions for public_problem in the contest
        self.assertIn(self.sub_public_problem.id, submission_ids)
        self.assertNotIn(self.sub_other_problem.id, submission_ids)


class SubmissionListOrganizationQuerysetTestCase(CommonDataMixin, TestCase):
    """Test cases for SubmissionListOrganization.get_queryset method."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls._now = timezone.now()

        # Create a second organization
        cls.organizations['private_org'] = create_organization(
            name='private_org',
            is_unlisted=True,
        )

        # Create problems for different organizations
        cls.org_problem_open = create_problem(
            code='org_problem_open',
            is_public=True,
            is_organization_private=True,
            organizations=('open',),
        )

        cls.org_problem_private = create_problem(
            code='org_problem_private',
            is_public=True,
            is_organization_private=True,
            organizations=('private_org',),
        )

        cls.public_problem = create_problem(
            code='public_problem_org_test',
            is_public=True,
        )

        # Create submissions for org problems
        cls.sub_open_org = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.org_problem_open,
            language=Language.get_python3(),
            result='AC',
            status='D',
        )

        cls.sub_private_org = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.org_problem_private,
            language=Language.get_python3(),
            result='AC',
            status='D',
        )

        cls.sub_public_problem = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.public_problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
        )

        # Add user to open organization
        cls.users['normal'].profile.organizations.add(cls.organizations['open'])

    def _create_org_view_instance(self, user, organization):
        """Helper to create a mock SubmissionListOrganization-like instance."""
        from judge.views.organization import SubmissionListOrganization

        factory = RequestFactory()
        request = factory.get('/organization/submissions/')
        request.user = user
        request.profile = user.profile if hasattr(user, 'profile') else None
        request.LANGUAGE_CODE = 'en'

        view = SubmissionListOrganization()
        view.request = request
        view.kwargs = {'slug': organization.slug}
        view.show_problem = True
        view.selected_languages = set()
        view.selected_statuses = set()
        view.selected_organization = None

        # Mock organization property
        type(view).organization = PropertyMock(return_value=organization)
        type(view).is_contest_scoped = PropertyMock(return_value=False)

        return view

    def test_filters_by_organization_problems(self):
        """Test that only submissions for organization's problems are returned."""
        view = self._create_org_view_instance(
            user=self.users['normal'],
            organization=self.organizations['open'],
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should include submission for open org problem
        self.assertIn(self.sub_open_org.id, submission_ids)

        # Should not include submissions for other org or public problems
        self.assertNotIn(self.sub_private_org.id, submission_ids)
        self.assertNotIn(self.sub_public_problem.id, submission_ids)

    def test_different_organization_shows_different_submissions(self):
        """Test that different organizations show their respective submissions."""
        view = self._create_org_view_instance(
            user=self.users['superuser'],
            organization=self.organizations['private_org'],
        )

        queryset = view.get_queryset()
        submission_ids = set(queryset.values_list('id', flat=True))

        # Should include submission for private org problem
        self.assertIn(self.sub_private_org.id, submission_ids)

        # Should not include submissions for other org problems
        self.assertNotIn(self.sub_open_org.id, submission_ids)
        self.assertNotIn(self.sub_public_problem.id, submission_ids)

    def test_organization_with_no_submissions(self):
        """Test organization with no submissions returns empty queryset."""
        empty_org = create_organization(
            name='empty_org',
            is_unlisted=False,
        )

        view = self._create_org_view_instance(
            user=self.users['superuser'],
            organization=empty_org,
        )

        queryset = view.get_queryset()

        self.assertEqual(queryset.count(), 0)

    def test_inherits_base_filters(self):
        """Test that organization view inherits base class filters."""
        view = self._create_org_view_instance(
            user=self.users['normal'],
            organization=self.organizations['open'],
        )
        view.selected_languages = {'PY3'}

        queryset = view.get_queryset()

        # All submissions should be Python 3 and from org problems
        for submission in queryset:
            self.assertEqual(submission.language.key, 'PY3')
            self.assertTrue(
                submission.problem.organizations.filter(pk=self.organizations['open'].pk).exists(),
            )
