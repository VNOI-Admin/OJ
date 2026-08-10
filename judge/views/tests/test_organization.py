from django.test import TestCase

from judge.models import Problem
from judge.models.tests.util import CommonDataMixin, create_organization, create_problem
from judge.views.organization import get_organization_problem_filter


class OrganizationProblemFilterTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.organization = create_organization(
            name='filterorg',
            is_unlisted=False,
            admins=('staff_organization_admin',),
        )
        create_problem(
            code='org_public',
            is_public=True,
            is_organization_private=True,
            organization=cls.organization,
        )
        create_problem(
            code='org_private',
            is_public=False,
            is_organization_private=True,
            organization=cls.organization,
        )
        create_problem(
            code='org_authored',
            is_public=False,
            is_organization_private=True,
            organization=cls.organization,
            authors=('normal',),
        )
        create_problem(
            code='not_in_org',
            is_public=True,
        )

    def filtered_codes(self, username):
        user = self.users[username]
        profile = None if user.is_anonymous else user.profile
        return set(
            Problem.objects.filter(
                get_organization_problem_filter(self.organization, user, profile),
            ).distinct().values_list('code', flat=True),
        )

    def test_normal_user_sees_public_and_authored_problems(self):
        self.assertEqual(self.filtered_codes('normal'), {'org_public', 'org_authored'})

    def test_anonymous_user_sees_only_public_problems(self):
        self.assertEqual(self.filtered_codes('anonymous'), {'org_public'})

    def test_see_private_problem_sees_every_problem_in_the_organization(self):
        self.assertEqual(
            self.filtered_codes('staff_problem_see_all'),
            {'org_public', 'org_private', 'org_authored'},
        )
