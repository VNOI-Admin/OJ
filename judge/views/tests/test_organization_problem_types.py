from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from judge.forms import ProblemEditForm
from judge.models import Language, Submission
from judge.models.tests.util import CommonDataMixin, create_problem, create_problem_type, create_user


class OrganizationProblemTypesTestCase(CommonDataMixin, TestCase):
    """Organization problems use the public problem types, not organization tags."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.org = cls.organizations['open']
        cls.member = create_user(username='org_types_member')
        cls.member.profile.organizations.add(cls.org)
        cls.org.admins.add(cls.member.profile)
        cls.graph = create_problem_type('graph', full_name='Graph')
        cls.greedy = create_problem_type('greedy', full_name='Greedy')
        cls.graph_problem = create_problem(
            code='open_graph', is_public=True, is_organization_private=True, organization=cls.org, types=('graph',),
        )
        cls.greedy_problem = create_problem(
            code='open_greedy', is_public=True, is_organization_private=True, organization=cls.org, types=('greedy',),
        )

    def setUp(self):
        cache.clear()
        self.client.force_login(self.member)

    def test_types_list_uses_types(self):
        self.assertEqual(self.graph_problem.types_list, ['Graph'])

    def test_edit_form_has_types_not_tags(self):
        form = ProblemEditForm(org_pk=self.org.pk, instance=self.graph_problem)
        self.assertIn('types', form.fields)
        self.assertNotIn('tags', form.fields)
        self.assertFalse(form.fields['group'].widget.is_hidden)

    def test_problem_list_filters_by_type(self):
        url = reverse('problem_list_organization', args=[self.org.slug])
        response = self.client.get(url, {'type': self.graph.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([problem.code for problem in response.context['problems']], ['open_graph'])
        content = response.content.decode()
        self.assertIn('name="type"', content)
        self.assertNotIn('name="tag"', content)
        self.assertIn(reverse('problem_random_organization', args=[self.org.slug]), content)

    def test_global_random_url_unchanged(self):
        content = self.client.get(reverse('problem_list')).content.decode()
        self.assertIn("var random_url = '%s'" % reverse('problem_random'), content)

    def test_solved_problems_grouped_by_type(self):
        Submission.objects.create(
            user=self.member.profile, problem=self.graph_problem, language=Language.get_default_language(),
            result='AC', points=1, case_points=1, case_total=1,
        )
        url = reverse('organization_user_solved', args=[self.org.slug, self.member.username])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([section['name'] for section in response.context['tag_sections']], ['Graph'])
