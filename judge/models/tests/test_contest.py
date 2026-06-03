from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from judge.models import Contest, ContestParticipation, ContestTag
from judge.models.contest import ContestProblem, MinValueOrNoneValidator
from judge.models.tests.util import (
    CommonDataMixin, create_contest, create_contest_participation, create_contest_problem, create_problem, create_user,
)


class ContestTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(self):
        super().setUpTestData()
        self.users.update({
            'staff_contest_edit_own': create_user(
                username='staff_contest_edit_own',
                is_staff=True,
                user_permissions=('edit_own_contest',),
            ),
            'staff_contest_see_all': create_user(
                username='staff_contest_see_all',
                user_permissions=('see_private_contest',),
            ),
            'staff_contest_edit_all': create_user(
                username='staff_contest_edit_all',
                is_staff=True,
                user_permissions=('edit_own_contest', 'edit_all_contest'),
            ),
            'normal_during_window': create_user(
                username='normal_during_window',
            ),
            'normal_after_window': create_user(
                username='normal_after_window',
            ),
            'normal_before_window': create_user(
                username='normal_before_window',
            ),
            'non_staff_author': create_user(
                username='non_staff_author',
                is_staff=False,
            ),
            'non_staff_tester': create_user(
                username='non_staff_tester',
                is_staff=False,
            ),
        })

        _now = timezone.now()

        self.basic_contest = create_contest(
            key='basic',
            start_time=_now - timezone.timedelta(days=1),
            end_time=_now + timezone.timedelta(days=100),
            authors=('superuser', 'staff_contest_edit_own'),
            testers=('non_staff_tester',),
        )

        self.hidden_scoreboard_contest = create_contest(
            key='hidden_scoreboard',
            start_time=_now - timezone.timedelta(days=1),
            end_time=_now + timezone.timedelta(days=100),
            is_visible=True,
            scoreboard_visibility=Contest.SCOREBOARD_AFTER_CONTEST,
            problem_label_script="""
                function(n)
                    return tostring(math.floor(n))
                end
            """,
        )

        self.hidden_scoreboard_non_staff_author = create_contest(
            key='non_staff_author',
            start_time=_now - timezone.timedelta(days=1),
            end_time=_now + timezone.timedelta(days=100),
            is_visible=True,
            scoreboard_visibility=Contest.SCOREBOARD_AFTER_CONTEST,
            authors=('non_staff_author',),
            curators=('staff_contest_edit_own',),
        )

        self.contest_hidden_scoreboard_contest = create_contest(
            key='contest_scoreboard',
            start_time=_now - timezone.timedelta(days=10),
            end_time=_now + timezone.timedelta(days=100),
            time_limit=timezone.timedelta(days=1),
            is_visible=True,
            scoreboard_visibility=Contest.SCOREBOARD_AFTER_CONTEST,
            testers=('non_staff_tester',),
        )

        self.particip_hidden_scoreboard_contest = create_contest(
            key='particip_scoreboard',
            start_time=_now - timezone.timedelta(days=10),
            end_time=_now + timezone.timedelta(days=100),
            time_limit=timezone.timedelta(days=1),
            is_visible=True,
            scoreboard_visibility=Contest.SCOREBOARD_AFTER_PARTICIPATION,
            testers=('non_staff_tester',),
        )

        self.visible_scoreboard_contest = create_contest(
            key='visible_scoreboard',
            start_time=_now - timezone.timedelta(days=10),
            end_time=_now + timezone.timedelta(days=100),
            time_limit=timezone.timedelta(days=1),
            is_visible=True,
            scoreboard_visibility=Contest.SCOREBOARD_VISIBLE,
            testers=('non_staff_tester',),
        )

        for contest_key in ('contest_scoreboard', 'particip_scoreboard', 'visible_scoreboard'):
            create_contest_participation(
                contest=contest_key,
                user='normal_during_window',
                real_start=_now - timezone.timedelta(hours=1),
                virtual=ContestParticipation.LIVE,
            )

            create_contest_participation(
                contest=contest_key,
                user='normal_after_window',
                real_start=_now - timezone.timedelta(days=3),
                virtual=ContestParticipation.LIVE,
            )

        create_contest_participation(
            contest='particip_scoreboard',
            user='normal',
            real_start=_now - timezone.timedelta(days=3),
            virtual=ContestParticipation.LIVE,
        )

        create_contest_participation(
            contest='particip_scoreboard',
            user='normal',
            real_start=_now + timezone.timedelta(days=101),
            virtual=ContestParticipation.SPECTATE,
        )

        self.users['normal'].profile.current_contest = create_contest_participation(
            contest='hidden_scoreboard',
            user='normal',
        )
        self.users['normal'].profile.save()

        self.hidden_scoreboard_contest.update_user_count()

        self.private_contest = create_contest(
            key='private',
            start_time=_now - timezone.timedelta(days=5),
            end_time=_now - timezone.timedelta(days=3),
            is_visible=True,
            is_private=True,
            is_organization_private=True,
            private_contestants=('staff_contest_edit_own',),
            testers=('non_staff_tester',),
        )

        self.organization_private_contest = create_contest(
            key='organization_private',
            start_time=_now - timezone.timedelta(days=5),
            end_time=_now + timezone.timedelta(days=6),
            is_visible=True,
            is_organization_private=True,
            organization=self.organizations['open'],
            view_contest_scoreboard=('normal',),
            testers=('non_staff_tester',),
        )

        self.future_organization_private_contest = create_contest(
            key='future_org_private',
            start_time=_now + timezone.timedelta(days=3),
            end_time=_now + timezone.timedelta(days=6),
            is_visible=True,
            is_organization_private=True,
            organization=self.organizations['open'],
            view_contest_scoreboard=('normal',),
            testers=('non_staff_tester',),
        )

        self.private_user_contest = create_contest(
            key='private_user',
            start_time=_now - timezone.timedelta(days=3),
            end_time=_now + timezone.timedelta(days=6),
            is_visible=True,
            is_private=True,
            testers=('non_staff_tester',),
        )

        self.non_visible_contest = create_contest(
            key='non_visible_contest',
            start_time=_now - timezone.timedelta(days=3),
            end_time=_now + timezone.timedelta(days=6),
            is_visible=False,
        )

        self.non_visible_contest_with_tester = create_contest(
            key='non_visible_w_tester',
            start_time=_now - timezone.timedelta(days=3),
            end_time=_now + timezone.timedelta(days=6),
            is_visible=False,
            testers=('non_staff_tester',),
        )

    def setUp(self):
        self.users['normal'].profile.refresh_from_db()

    def test_basic_contest(self):
        self.assertTrue(self.basic_contest.show_scoreboard)
        self.assertEqual(self.basic_contest.contest_window_length, timezone.timedelta(days=101))
        self.assertIsInstance(self.basic_contest._now, timezone.datetime)
        self.assertTrue(self.basic_contest.can_join)
        self.assertIsNone(self.basic_contest.time_before_start)
        self.assertIsInstance(self.basic_contest.time_before_end, timezone.timedelta)
        self.assertFalse(self.basic_contest.ended)
        self.assertEqual(str(self.basic_contest), self.basic_contest.name)
        self.assertEqual(self.basic_contest.get_label_for_problem(0), '1')

    def test_hidden_scoreboard_contest(self):
        self.assertFalse(self.hidden_scoreboard_contest.show_scoreboard)
        for i in range(3):
            with self.subTest(contest_problem_index=i):
                self.assertEqual(self.hidden_scoreboard_contest.get_label_for_problem(i), str(i))
        self.assertEqual(self.hidden_scoreboard_contest.user_count, 1)

    def test_private_contest(self):
        self.assertTrue(self.private_contest.can_join)
        self.assertIsNone(self.private_contest.time_before_start)
        self.assertIsNone(self.private_contest.time_before_end)

    def test_organization_private_contest(self):
        self.assertTrue(self.organization_private_contest.can_join)
        self.assertTrue(self.organization_private_contest.show_scoreboard)
        self.assertFalse(self.organization_private_contest.ended)
        self.assertIsNone(self.organization_private_contest.time_before_start)
        self.assertIsInstance(self.organization_private_contest.time_before_end, timezone.timedelta)

    def test_future_organization_private_contest(self):
        self.assertFalse(self.future_organization_private_contest.can_join)
        self.assertFalse(self.future_organization_private_contest.show_scoreboard)
        self.assertFalse(self.future_organization_private_contest.ended)
        self.assertIsInstance(self.future_organization_private_contest.time_before_start, timezone.timedelta)
        self.assertIsInstance(self.future_organization_private_contest.time_before_end, timezone.timedelta)

    def test_basic_contest_methods(self):
        with self.assertRaises(Contest.Inaccessible):
            self.basic_contest.access_check(self.users['normal'])

        data = {
            'superuser': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertTrue,
                'is_in_contest': self.assertFalse,
            },
            'staff_contest_edit_own': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertTrue,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertTrue,
                'is_in_contest': self.assertFalse,
            },
            'staff_contest_see_all': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'staff_contest_edit_all': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertTrue,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertTrue,
                'is_in_contest': self.assertFalse,
            },
            'normal': {
                # scoreboard checks don't do accessibility checks
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertFalse,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'non_staff_tester': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'anonymous': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertFalse,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
        }
        self._test_object_methods_with_users(self.basic_contest, data)

    def test_hidden_scoreboard_contest_methods(self):
        data = {
            'staff_contest_edit_own': {
                'can_see_own_scoreboard': self.assertFalse,
                'can_see_full_scoreboard': self.assertFalse,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'staff_contest_see_all': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'staff_contest_edit_all': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertTrue,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertTrue,
                'is_in_contest': self.assertFalse,
            },
            'normal': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertFalse,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertTrue,
            },
            'anonymous': {
                'can_see_own_scoreboard': self.assertFalse,
                'can_see_full_scoreboard': self.assertFalse,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
        }
        self._test_object_methods_with_users(self.hidden_scoreboard_contest, data)

    def test_contest_hidden_scoreboard_non_staff_author_contest_methods(self):
        data = {
            'staff_contest_edit_own': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertTrue,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertTrue,
                'is_in_contest': self.assertFalse,
            },
            'non_staff_author': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertTrue,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
        }
        self._test_object_methods_with_users(self.hidden_scoreboard_non_staff_author, data)

    def test_contest_hidden_scoreboard_contest_methods(self):
        data = {
            'normal_before_window': {
                'can_see_own_scoreboard': self.assertFalse,
                'can_see_full_scoreboard': self.assertFalse,
                'can_see_full_submission_list': self.assertFalse,
                'has_completed_contest': self.assertFalse,
            },
            'normal_during_window': {
                'can_see_own_scoreboard': self.assertFalse,
                'can_see_full_scoreboard': self.assertFalse,
                'can_see_full_submission_list': self.assertFalse,
                'has_completed_contest': self.assertFalse,
            },
            'normal_after_window': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertFalse,
                'can_see_full_submission_list': self.assertFalse,
                'has_completed_contest': self.assertTrue,
            },
            'non_staff_tester': {
                'can_see_own_scoreboard': self.assertFalse,
                'can_see_full_scoreboard': self.assertFalse,
                'can_see_full_submission_list': self.assertFalse,
                'has_completed_contest': self.assertFalse,
            },
        }
        self._test_object_methods_with_users(self.contest_hidden_scoreboard_contest, data)

    def test_particip_hidden_scoreboard_contest_methods(self):
        data = {
            'normal_before_window': {
                'can_see_own_scoreboard': self.assertFalse,
                'can_see_full_scoreboard': self.assertFalse,
                'can_see_full_submission_list': self.assertFalse,
                'has_completed_contest': self.assertFalse,
            },
            'normal_during_window': {
                'can_see_own_scoreboard': self.assertFalse,
                'can_see_full_scoreboard': self.assertFalse,
                'can_see_full_submission_list': self.assertFalse,
                'has_completed_contest': self.assertFalse,
            },
            'normal_after_window': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'has_completed_contest': self.assertTrue,
            },
            'normal': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'has_completed_contest': self.assertTrue,
            },
            'non_staff_tester': {
                'can_see_own_scoreboard': self.assertFalse,
                'can_see_full_scoreboard': self.assertFalse,
                'can_see_full_submission_list': self.assertFalse,
                'has_completed_contest': self.assertFalse,
            },
        }
        self._test_object_methods_with_users(self.particip_hidden_scoreboard_contest, data)

    def test_visible_scoreboard_contest_methods(self):
        data = {
            'normal_before_window': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'has_completed_contest': self.assertFalse,
            },
            'normal_during_window': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'has_completed_contest': self.assertFalse,
            },
            'normal_after_window': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'has_completed_contest': self.assertTrue,
            },
            'non_staff_tester': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'has_completed_contest': self.assertFalse,
            },
        }
        self._test_object_methods_with_users(self.visible_scoreboard_contest, data)

    def test_private_contest_methods(self):
        with self.assertRaises(Contest.PrivateContest):
            self.private_contest.access_check(self.users['normal'])
        self.private_contest.private_contestants.add(self.users['normal'].profile)
        with self.assertRaises(Contest.PrivateContest):
            self.private_contest.access_check(self.users['normal'])
        self.private_contest.organization = self.organizations['open']
        self.private_contest.save()
        self.users['normal'].profile.organizations.add(self.organizations['open'])

        data = {
            'normal': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertTrue,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'staff_contest_see_all': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertTrue,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'anonymous': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertTrue,
                'is_accessible_by': self.assertFalse,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'non_staff_tester': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertTrue,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
        }
        self._test_object_methods_with_users(self.private_contest, data)

    def test_organization_private_contest_methods(self):
        data = {
            'staff_contest_edit_own': {
                # scoreboard checks don't do accessibility checks
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertFalse,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'staff_contest_see_all': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'staff_contest_edit_all': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertTrue,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertTrue,
                'is_in_contest': self.assertFalse,
            },
            'normal': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'non_staff_tester': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'anonymous': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertFalse,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
        }
        self._test_object_methods_with_users(self.organization_private_contest, data)

    def test_future_organization_private_contest_methods(self):
        data = {
            'staff_contest_edit_own': {
                'can_see_own_scoreboard': self.assertFalse,
                'can_see_full_scoreboard': self.assertFalse,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertFalse,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'staff_contest_see_all': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'staff_contest_edit_all': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertTrue,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertTrue,
                'is_in_contest': self.assertFalse,
            },
            'normal': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'non_staff_tester': {
                # False because contest has not begun
                'can_see_own_scoreboard': self.assertFalse,
                'can_see_full_scoreboard': self.assertFalse,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'anonymous': {
                # False because contest has not begun
                'can_see_own_scoreboard': self.assertFalse,
                'can_see_full_scoreboard': self.assertFalse,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertFalse,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
        }
        self._test_object_methods_with_users(self.future_organization_private_contest, data)

    def test_private_user_contest_methods(self):
        data = {
            'superuser': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertTrue,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertTrue,
                'is_in_contest': self.assertFalse,
            },
            'normal': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertFalse,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'non_staff_tester': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'anonymous': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertFalse,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
        }
        self._test_object_methods_with_users(self.private_user_contest, data)

    def test_non_visible_contest_contest_methods(self):
        data = {
            'superuser': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertTrue,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertTrue,
                'is_in_contest': self.assertFalse,
            },
            'normal': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertFalse,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            # not set as tester, in case something silly is happening
            'non_staff_tester': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertFalse,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'anonymous': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertFalse,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
        }
        self._test_object_methods_with_users(self.non_visible_contest, data)

    def test_non_visible_contest_with_tester_contest_methods(self):
        data = {
            'superuser': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertTrue,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertTrue,
                'is_in_contest': self.assertFalse,
            },
            'normal': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertFalse,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'non_staff_tester': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertTrue,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
            'anonymous': {
                'can_see_own_scoreboard': self.assertTrue,
                'can_see_full_scoreboard': self.assertTrue,
                'can_see_full_submission_list': self.assertFalse,
                'is_accessible_by': self.assertFalse,
                'is_editable_by': self.assertFalse,
                'is_in_contest': self.assertFalse,
            },
        }
        self._test_object_methods_with_users(self.non_visible_contest_with_tester, data)

    def test_contests_list(self):
        for name, user in self.users.items():
            with self.subTest(user=name):
                # We only care about consistency between Contest.is_accessible_by and Contest.get_visible_contests
                contest_keys = []
                for contest in Contest.objects.prefetch_related('testers', 'private_contestants', 'organization'):
                    if contest.is_accessible_by(user):
                        contest_keys.append(contest.key)

                self.assertCountEqual(
                    Contest.get_visible_contests(user).values_list('key', flat=True),
                    contest_keys,
                )

    def test_contest_clean(self):
        _now = timezone.now()
        contest = create_contest(
            key='contest',
            start_time=_now,
            end_time=_now - timezone.timedelta(days=1),
            problem_label_script='invalid',
            format_config={'invalid': 'invalid'},
        )
        with self.assertRaisesRegex(ValidationError, 'ended before it starts'):
            contest.full_clean()
        contest.end_time = _now
        with self.assertRaisesRegex(ValidationError, 'ended before it starts'):
            contest.full_clean()
        contest.end_time = _now + timezone.timedelta(days=1)
        with self.assertRaisesRegex(ValidationError, 'default contest expects'):
            contest.full_clean()
        contest.format_config = {}
        with self.assertRaisesRegex(ValidationError, 'Contest problem label script'):
            contest.full_clean()
        contest.problem_label_script = """
            function(n)
                return n
            end
        """
        # Test for bad problem label script caching
        with self.assertRaisesRegex(ValidationError, 'Contest problem label script'):
            contest.full_clean()
        del contest.get_label_for_problem
        with self.assertRaisesRegex(ValidationError, 'should return a string'):
            contest.full_clean()
        contest.problem_label_script = ''
        del contest.get_label_for_problem
        contest.full_clean()

    def test_normal_user_current_contest(self):
        current_contest = self.users['normal'].profile.current_contest
        self.assertIsNotNone(current_contest)

        current_contest.set_disqualified(True)
        self.users['normal'].profile.refresh_from_db()
        self.assertTrue(current_contest.is_disqualified)
        self.assertIsNone(self.users['normal'].profile.current_contest)
        self.assertEqual(current_contest.score, -9999)

        current_contest.set_disqualified(False)
        self.users['normal'].profile.refresh_from_db()
        self.assertFalse(current_contest.is_disqualified)
        self.assertIsNone(self.users['normal'].profile.current_contest)
        self.assertEqual(current_contest.score, 0)

    def test_live_participation(self):
        participation = ContestParticipation.objects.get(
            contest=self.hidden_scoreboard_contest,
            user=self.users['normal'].profile,
            virtual=ContestParticipation.LIVE,
        )
        self.assertTrue(participation.live)
        self.assertFalse(participation.spectate)
        self.assertEqual(participation.end_time, participation.contest.end_time)
        self.assertFalse(participation.ended)
        self.assertIsInstance(participation.time_remaining, timezone.timedelta)

    def test_spectating_participation(self):
        participation = create_contest_participation(
            contest='hidden_scoreboard',
            user='superuser',
            virtual=ContestParticipation.SPECTATE,
        )

        self.assertFalse(participation.live)
        self.assertTrue(participation.spectate)
        self.assertEqual(participation.start, participation.contest.start_time)
        self.assertEqual(participation.end_time, participation.contest.end_time)

    def test_virtual_participation(self):
        participation = create_contest_participation(
            contest='private',
            user='superuser',
            virtual=1,
        )

        self.assertFalse(participation.live)
        self.assertFalse(participation.spectate)
        self.assertEqual(participation.start, participation.real_start)
        self.assertIsInstance(participation.end_time, timezone.datetime)


class ContestTagTestCase(TestCase):
    @classmethod
    def setUpTestData(self):
        self.basic_tag = ContestTag.objects.create(
            name='basic',
            color='#fff',
        )
        self.dark_tag = ContestTag.objects.create(
            name='dark',
            color='#010001',
        )

    def test_basic_tag(self):
        self.assertEqual(str(self.basic_tag), self.basic_tag.name)
        self.assertEqual(self.basic_tag.text_color, '#000')

    def test_dark_tag(self):
        self.assertEqual(self.dark_tag.text_color, '#fff')


class MinValueOrNoneValidatorTestCase(SimpleTestCase):
    def test_both_integers(self):
        self.assertIsNone(MinValueOrNoneValidator(-1)(100))
        self.assertIsNone(MinValueOrNoneValidator(0)(0))
        self.assertIsNone(MinValueOrNoneValidator(100)(100))

    def test_integer_bound_none_value(self):
        self.assertIsNone(MinValueOrNoneValidator(-100)(None))
        self.assertIsNone(MinValueOrNoneValidator(0)(None))
        self.assertIsNone(MinValueOrNoneValidator(100)(None))

    def test_none_bound_integer_value(self):
        self.assertIsNone(MinValueOrNoneValidator(None)(-100))
        self.assertIsNone(MinValueOrNoneValidator(None)(0))
        self.assertIsNone(MinValueOrNoneValidator(None)(100))

    def test_both_none(self):
        self.assertIsNone(MinValueOrNoneValidator(None)(None))

    def test_fail(self):
        with self.assertRaises(ValidationError):
            MinValueOrNoneValidator(0)(-1)

        with self.assertRaises(ValidationError):
            MinValueOrNoneValidator(100)(0)


class ContestProblemIsAccessibleByTestCase(CommonDataMixin, TestCase):
    """
    Unit tests for ContestProblem.is_accessible_by(user).

    Matrix of cases:
        problem:  public  / private
        contest:  public (visible, not private) / private (is_private=True)
        user:     anonymous, no-participation, participant,
                  contest-editor (no participation), problem-author (no participation),
                  see_private_problem perm, see_private_contest perm
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls._now = timezone.now()

        cls.users.update({
            'see_private_problem': create_user(
                username='cp_see_priv_prob',
                user_permissions=('see_private_problem',),
            ),
            'see_private_contest': create_user(
                username='cp_see_priv_cont',
                user_permissions=('see_private_contest',),
            ),
            'problem_author': create_user(username='cp_prob_author'),
            'contest_editor': create_user(username='cp_cont_editor'),
            'participant': create_user(username='cp_participant'),
            'private_allowed': create_user(username='cp_priv_allowed'),
            'private_not_allowed': create_user(username='cp_priv_not_allowed'),
        })

        cls.public_problem = create_problem(code='cp_pub_prob', is_public=True)
        cls.private_problem = create_problem(
            code='cp_priv_prob',
            is_public=False,
            authors=('cp_prob_author',),
        )

        cls.public_contest = create_contest(
            key='cp_public_contest',
            start_time=cls._now - timezone.timedelta(hours=1),
            end_time=cls._now + timezone.timedelta(days=1),
            is_visible=True,
            authors=('cp_cont_editor',),
        )
        cls.pub_contest_pub_cp = create_contest_problem(
            contest=cls.public_contest, problem=cls.public_problem, order=1,
        )
        cls.pub_contest_priv_cp = create_contest_problem(
            contest=cls.public_contest, problem=cls.private_problem, order=2,
        )
        create_contest_participation(contest=cls.public_contest, user='cp_participant')

        cls.private_contest = create_contest(
            key='cp_private_contest',
            start_time=cls._now - timezone.timedelta(hours=1),
            end_time=cls._now + timezone.timedelta(days=1),
            is_visible=True,
            is_private=True,
            private_contestants=('cp_priv_allowed',),
        )
        cls.priv_contest_pub_cp = create_contest_problem(
            contest=cls.private_contest, problem=cls.public_problem, order=1,
        )
        cls.priv_contest_priv_cp = create_contest_problem(
            contest=cls.private_contest, problem=cls.private_problem, order=2,
        )
        create_contest_participation(contest=cls.private_contest, user='cp_priv_allowed')

    def test_pub_contest_pub_problem_methods(self):
        # Public problem -> always accessible regardless of contest or participation
        data = {
            'anonymous':      {'is_accessible_by': self.assertTrue},
            'normal':         {'is_accessible_by': self.assertTrue},
            'participant':    {'is_accessible_by': self.assertTrue},
            'contest_editor': {'is_accessible_by': self.assertTrue},
            'superuser':      {'is_accessible_by': self.assertTrue},
        }
        self._test_object_methods_with_users(self.pub_contest_pub_cp, data)

    def test_pub_contest_priv_problem_methods(self):
        # Private problem in public contest:
        #   - participant/problem_author/see_private_problem/superuser -> True
        #   - all others -> False
        data = {
            'anonymous':          {'is_accessible_by': self.assertFalse},
            'normal':             {'is_accessible_by': self.assertFalse},
            'participant':        {'is_accessible_by': self.assertTrue},
            'problem_author':     {'is_accessible_by': self.assertTrue},
            'see_private_problem':{'is_accessible_by': self.assertTrue},
            'see_private_contest':{'is_accessible_by': self.assertFalse},
            'contest_editor':     {'is_accessible_by': self.assertFalse},
            'superuser':          {'is_accessible_by': self.assertTrue},
        }
        self._test_object_methods_with_users(self.pub_contest_priv_cp, data)

    def test_priv_contest_pub_problem_methods(self):
        # Public problem -> problem.is_accessible_by() returns True before contest check
        data = {
            'anonymous':           {'is_accessible_by': self.assertTrue},
            'private_not_allowed': {'is_accessible_by': self.assertTrue},
            'private_allowed':     {'is_accessible_by': self.assertTrue},
            'see_private_contest': {'is_accessible_by': self.assertTrue},
            'superuser':           {'is_accessible_by': self.assertTrue},
        }
        self._test_object_methods_with_users(self.priv_contest_pub_cp, data)

    def test_priv_contest_priv_problem_methods(self):
        # Private problem in private contest:
        #   - allowed+participation / problem_author / see_private_problem / superuser -> True
        #   - see_private_contest has contest access but no participation -> False
        data = {
            'anonymous':           {'is_accessible_by': self.assertFalse},
            'private_not_allowed': {'is_accessible_by': self.assertFalse},
            'private_allowed':     {'is_accessible_by': self.assertTrue},
            'problem_author':      {'is_accessible_by': self.assertTrue},
            'see_private_problem': {'is_accessible_by': self.assertTrue},
            'see_private_contest': {'is_accessible_by': self.assertFalse},
            'superuser':           {'is_accessible_by': self.assertTrue},
        }
        self._test_object_methods_with_users(self.priv_contest_priv_cp, data)


class ProblemIsAccessibleByNoContestCheckTestCase(CommonDataMixin, TestCase):
    """
    After the refactor, Problem.is_accessible_by() must NOT grant access based on
    contest membership (current_contest). ContestProblem.is_accessible_by() is the
    correct method for that check.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls._now = timezone.now()

        cls.users.update({
            'in_contest': create_user(username='prob_in_contest'),
        })

        cls.private_problem = create_problem(code='refactor_priv_prob', is_public=False)

        cls.contest = create_contest(
            key='refactor_contest',
            start_time=cls._now - timezone.timedelta(hours=1),
            end_time=cls._now + timezone.timedelta(days=1),
            is_visible=True,
        )
        create_contest_problem(contest=cls.contest, problem=cls.private_problem, order=1)

        participation = create_contest_participation(
            contest=cls.contest, user='prob_in_contest',
        )
        cls.users['in_contest'].profile.current_contest = participation
        cls.users['in_contest'].profile.save()

        cls.contest_problem = ContestProblem.objects.get(
            contest=cls.contest, problem=cls.private_problem,
        )

    def test_problem_is_accessible_by_methods(self):
        # Problem.is_accessible_by() is pure — contest membership must not affect it.
        # 'in_contest' has current_contest set but is NOT a problem author/tester/curator
        # and has no see_private_problem perm -> must be False.
        data = {
            'in_contest': {'is_accessible_by': self.assertFalse},
            'normal':     {'is_accessible_by': self.assertFalse},
            'anonymous':  {'is_accessible_by': self.assertFalse},
        }
        self._test_object_methods_with_users(self.private_problem, data)

    def test_contest_problem_is_accessible_by_methods(self):
        # ContestProblem.is_accessible_by() correctly grants access for participants.
        data = {
            'in_contest': {'is_accessible_by': self.assertTrue},
            'normal':     {'is_accessible_by': self.assertFalse},
            'anonymous':  {'is_accessible_by': self.assertFalse},
        }
        self._test_object_methods_with_users(self.contest_problem, data)
