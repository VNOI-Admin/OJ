from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from judge.models import Language, Problem, Submission
from judge.models.tests.util import CommonDataMixin, create_organization, create_problem, create_problem_type, \
    create_user
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


class OrganizationUserSolvedAccessTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.organization = cls.organizations['open']
        cls.member = create_user(username='solved_member')
        cls.member.profile.organizations.add(cls.organization)
        cls.url = reverse('organization_user_solved', args=[cls.organization.slug, 'solved_member'])

    def test_organization_admin_can_view(self):
        self.client.force_login(self.users['staff_organization_admin'])
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_plain_member_is_refused(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_anonymous_user_is_refused(self):
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_non_member_username_is_not_found(self):
        self.client.force_login(self.users['staff_organization_admin'])
        url = reverse('organization_user_solved', args=[self.organization.slug, 'normal'])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_unknown_username_is_not_found(self):
        self.client.force_login(self.users['staff_organization_admin'])
        url = reverse('organization_user_solved', args=[self.organization.slug, 'nobody'])
        self.assertEqual(self.client.get(url).status_code, 404)


class OrganizationUserSolvedContextTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.organization = create_organization(
            name='solvedorg',
            is_unlisted=False,
            admins=('staff_organization_admin',),
        )
        cls.member = create_user(username='solver')
        cls.member.profile.organizations.add(cls.organization)

        create_problem_type(name='dp', full_name='Dynamic Programming')
        create_problem_type(name='graph', full_name='Graph Theory')

        cls.solved_two_types = create_problem(
            code='two_types',
            is_public=True,
            is_organization_private=True,
            organization=cls.organization,
            types=('dp', 'graph'),
        )
        cls.solved_no_type = create_problem(
            code='no_type',
            is_public=True,
            is_organization_private=True,
            organization=cls.organization,
        )
        cls.unsolved = create_problem(
            code='unsolved',
            is_public=True,
            is_organization_private=True,
            organization=cls.organization,
            types=('dp',),
        )
        cls.outside_org = create_problem(
            code='outside_org',
            is_public=True,
            types=('dp',),
        )
        cls.private_other_admin = create_problem(
            code='private_other_admin',
            is_public=False,
            is_organization_private=True,
            organization=cls.organization,
            types=('dp',),
            authors=('normal',),
        )

        cls._now = timezone.now()
        cls.create_ac(cls.solved_two_types, cls._now - timezone.timedelta(days=5))
        cls.create_ac(cls.solved_two_types, cls._now - timezone.timedelta(days=1))
        cls.create_ac(cls.solved_no_type, cls._now - timezone.timedelta(days=3))
        cls.create_ac(cls.outside_org, cls._now - timezone.timedelta(days=2))
        cls.create_submission(cls.unsolved, cls._now, result='WA')
        cls.create_ac(cls.private_other_admin, cls._now - timezone.timedelta(days=4))

        cls.url = reverse('organization_user_solved', args=[cls.organization.slug, 'solver'])

    @classmethod
    def create_submission(cls, problem, date, result):
        submission = Submission.objects.create(
            user=cls.member.profile,
            problem=problem,
            language=Language.get_python3(),
            result=result,
            status='D',
        )
        # `date` is auto_now_add, so it can only be set after the row exists.
        Submission.objects.filter(pk=submission.pk).update(date=date)
        return submission

    @classmethod
    def create_ac(cls, problem, date):
        return cls.create_submission(problem, date, result='AC')

    def get_context(self):
        self.client.force_login(self.users['staff_organization_admin'])
        return self.client.get(self.url).context

    def sections_by_name(self):
        return {section['name']: section for section in self.get_context()['type_sections']}

    def test_only_solved_organization_problems_are_listed(self):
        codes = {
            problem['code']
            for section in self.get_context()['type_sections']
            for problem in section['problems']
        }
        self.assertEqual(codes, {'two_types', 'no_type'})

    def test_problem_with_two_types_appears_once_under_the_first_type(self):
        sections = self.sections_by_name()
        self.assertIn('Dynamic Programming', sections)
        self.assertNotIn('Graph Theory', sections)
        self.assertEqual([problem['code'] for problem in sections['Dynamic Programming']['problems']], ['two_types'])

    def test_problem_without_type_is_uncategorized(self):
        sections = self.sections_by_name()
        self.assertEqual([problem['code'] for problem in sections['Uncategorized']['problems']], ['no_type'])

    def test_uncategorized_section_sorts_last(self):
        names = [section['name'] for section in self.get_context()['type_sections']]
        self.assertEqual(names[-1], 'Uncategorized')

    def test_first_solved_is_the_earliest_accepted_submission(self):
        sections = self.sections_by_name()
        problem = sections['Dynamic Programming']['problems'][0]
        self.assertEqual(problem['first_solved'], self._now - timezone.timedelta(days=5))

    def test_counts(self):
        context = self.get_context()
        self.assertEqual(context['solved_count'], 2)
        self.assertEqual(context['total_count'], 3)
        self.assertEqual(self.sections_by_name()['Dynamic Programming']['count'], 1)

    def test_organization_private_problem_hidden_from_other_admin_is_excluded(self):
        codes = {
            problem['code']
            for section in self.get_context()['type_sections']
            for problem in section['problems']
        }
        self.assertNotIn('private_other_admin', codes)
        self.assertEqual(self.get_context()['total_count'], 3)


class OrganizationUserSolvedTemplateTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.organization = create_organization(
            name='templateorg',
            is_unlisted=False,
            admins=('staff_organization_admin',),
        )
        cls.member = create_user(username='renderer')
        cls.member.profile.organizations.add(cls.organization)
        cls.empty_member = create_user(username='idler')
        cls.empty_member.profile.organizations.add(cls.organization)

        create_problem_type(name='dp', full_name='Dynamic Programming')
        cls.problem = create_problem(
            code='render_me',
            name='Render Me',
            is_public=True,
            is_organization_private=True,
            organization=cls.organization,
            types=('dp',),
        )
        submission = Submission.objects.create(
            user=cls.member.profile,
            problem=cls.problem,
            language=Language.get_python3(),
            result='AC',
            status='D',
        )
        Submission.objects.filter(pk=submission.pk).update(date=timezone.now())

    def get_page(self, username):
        self.client.force_login(self.users['staff_organization_admin'])
        return self.client.get(reverse('organization_user_solved', args=[self.organization.slug, username]))

    def test_page_renders_the_solved_problem_row(self):
        response = self.get_page('renderer')
        self.assertTemplateUsed(response, 'organization/user-solved.html')
        self.assertContains(response, 'Render Me')
        self.assertContains(response, reverse('problem_detail', args=['render_me']))
        self.assertContains(response, reverse('user_submissions', args=['render_me', 'renderer']))
        self.assertContains(response, 'Dynamic Programming')

    def test_section_exposes_the_page_size_to_the_script(self):
        self.assertContains(self.get_page('renderer'), 'data-page-size="10"')

    def test_member_with_no_solved_problems_sees_the_empty_state(self):
        self.assertContains(self.get_page('idler'), 'hasn&#x27;t solved any problems')


class OrganizationUsersSolvedLinkTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.organization = create_organization(
            name='linkorg',
            is_unlisted=False,
            admins=('staff_organization_admin',),
        )
        cls.member = create_user(username='linked')
        cls.member.profile.organizations.add(cls.organization)
        cls.url = reverse('organization_users', args=[cls.organization.slug])
        cls.solved_url = reverse('organization_user_solved', args=[cls.organization.slug, 'linked'])

    def test_admin_sees_the_solved_link(self):
        self.client.force_login(self.users['staff_organization_admin'])
        self.assertContains(self.client.get(self.url), self.solved_url)

    def test_plain_member_does_not_see_the_solved_link(self):
        self.client.force_login(self.member)
        self.assertNotContains(self.client.get(self.url), self.solved_url)
