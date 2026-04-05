from django.db import IntegrityError
from django.test import TestCase

from judge.models.role import ContestRole, ROLE_AUTHOR
from judge.models.tests.util import CommonDataMixin, create_contest


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
                contest=self.contest,
                user=self.users['normal'].profile,
                role=ROLE_AUTHOR,
            )
