from django.db import IntegrityError
from django.db.models import Q
from django.test import TestCase

from judge.models.role import ContestRole, ProblemRole, ROLE_AUTHOR, ROLE_CURATOR
from judge.models.tests.util import CommonDataMixin, create_contest, create_problem


class ContestRoleTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.contest = create_contest(
            key='role_contest',
            authors=('normal',),
            curators=('staff_problem_edit_own',),
            testers=('staff_problem_see_all',),
        )

    def test_role_properties(self):
        self.assertIn(self.users['normal'].profile, self.contest.authors)
        self.assertIn(self.users['staff_problem_edit_own'].profile, self.contest.curators)
        self.assertIn(self.users['staff_problem_see_all'].profile, self.contest.testers)

    def test_role_id_sets(self):
        self.assertCountEqual(self.contest.author_ids, [self.users['normal'].profile.id])
        self.assertCountEqual(
            self.contest.editor_ids,
            [self.users['normal'].profile.id, self.users['staff_problem_edit_own'].profile.id],
        )
        self.assertCountEqual(self.contest.tester_ids, [self.users['staff_problem_see_all'].profile.id])

    def test_unique_together(self):
        with self.assertRaises(IntegrityError):
            ContestRole.objects.create(
                contest=self.contest, user=self.users['normal'].profile, role=ROLE_AUTHOR,
            )


class ProblemRoleTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.problem = create_problem(
            code='role_problem',
            authors=('normal',),
            curators=('staff_problem_edit_own',),
            testers=('staff_problem_see_all',),
        )

    def test_role_properties(self):
        self.assertIn(self.users['normal'].profile, self.problem.authors)
        self.assertIn(self.users['staff_problem_edit_own'].profile, self.problem.curators)
        self.assertIn(self.users['staff_problem_see_all'].profile, self.problem.testers)

    def test_editor_helpers(self):
        self.assertTrue(self.problem.is_editor(self.users['normal'].profile))
        self.assertTrue(self.problem.is_editor(self.users['staff_problem_edit_own'].profile))
        self.assertFalse(self.problem.is_editor(self.users['staff_problem_see_all'].profile))

    def test_unique_together(self):
        with self.assertRaises(IntegrityError):
            ProblemRole.objects.create(
                problem=self.problem, user=self.users['normal'].profile, role=ROLE_AUTHOR,
            )

    def test_tester_role_is_not_editor(self):
        self.assertFalse(ProblemRole.objects.filter(
            problem=self.problem, user=self.users['staff_problem_see_all'].profile,
        ).filter(Q(role=ROLE_AUTHOR) | Q(role=ROLE_CURATOR)).exists())
