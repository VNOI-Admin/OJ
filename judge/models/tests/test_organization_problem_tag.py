from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from judge.forms import ProblemEditForm
from judge.models import OrganizationProblemTag
from judge.models.tests.util import CommonDataMixin, create_organization, create_problem


class OrganizationProblemTagTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.org = cls.organizations['open']
        cls.other_org = create_organization(name='other_org')

    # ---- unique_together(organization, name) ----

    def test_duplicate_name_same_org_raises(self):
        """Two tags with the same name in one org violate the unique constraint."""
        OrganizationProblemTag.objects.create(name='dp', organization=self.org)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationProblemTag.objects.create(name='dp', organization=self.org)

    def test_same_name_across_orgs_ok(self):
        """The same tag name is allowed in two different orgs."""
        tag_a = OrganizationProblemTag.objects.create(name='dp', organization=self.org)
        tag_b = OrganizationProblemTag.objects.create(name='dp', organization=self.other_org)
        self.assertNotEqual(tag_a.pk, tag_b.pk)

    # ---- ProblemEditForm tag scoping ----

    def test_edit_form_scopes_tags_to_org(self):
        """An org-scoped form only offers that org's tags, never another org's."""
        own = OrganizationProblemTag.objects.create(name='own', organization=self.org)
        foreign = OrganizationProblemTag.objects.create(name='foreign', organization=self.other_org)
        form = ProblemEditForm(org_pk=self.org.pk)
        self.assertIn(own, form.fields['tags'].queryset)
        self.assertNotIn(foreign, form.fields['tags'].queryset)

    def test_edit_form_global_problem_has_no_tags_field(self):
        """A global (non-org) problem form drops the tags field entirely."""
        form = ProblemEditForm()
        self.assertNotIn('tags', form.fields)

    # ---- tag management view permissions ----

    def _add_url(self):
        return reverse('organization_tag_add', args=[self.org.slug])

    def test_tag_list_forbidden_for_non_admin(self):
        """A non-admin user cannot open the tag management page."""
        self.client.force_login(self.users['normal'])
        response = self.client.get(reverse('organization_tag_list', args=[self.org.slug]))
        self.assertEqual(response.status_code, 403)

    def test_tag_list_allowed_for_org_admin(self):
        """An org admin can open the tag management page."""
        self.client.force_login(self.users['staff_organization_admin'])
        response = self.client.get(reverse('organization_tag_list', args=[self.org.slug]))
        self.assertEqual(response.status_code, 200)

    def test_org_admin_can_create_tag(self):
        """An org admin can create a tag for their organization."""
        self.client.force_login(self.users['staff_organization_admin'])
        response = self.client.post(self._add_url(), {'name': 'greedy'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.org.problem_tags.filter(name='greedy').exists())

    def test_non_admin_cannot_create_tag(self):
        """A non-admin user cannot create a tag."""
        self.client.force_login(self.users['normal'])
        response = self.client.post(self._add_url(), {'name': 'greedy'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.org.problem_tags.filter(name='greedy').exists())

    def test_duplicate_tag_create_shows_error(self):
        """Creating a duplicate tag re-renders the form with an error instead of crashing."""
        OrganizationProblemTag.objects.create(name='dup', organization=self.org)
        self.client.force_login(self.users['staff_organization_admin'])
        response = self.client.post(self._add_url(), {'name': 'dup'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.org.problem_tags.filter(name='dup').count(), 1)

    def test_org_admin_can_delete_normal_tag(self):
        """An org admin can delete an ordinary tag."""
        tag = OrganizationProblemTag.objects.create(name='temp', organization=self.org)
        self.client.force_login(self.users['staff_organization_admin'])
        response = self.client.post(reverse('organization_tag_delete', args=[self.org.slug, tag.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.org.problem_tags.filter(pk=tag.pk).exists())

    def test_org_problem_list_sort_solved_ok(self):
        """Sorting the org problem list by 'solved' must not 500 (prefetch-on-list regression)."""
        self.client.force_login(self.users['staff_problem_see_organization'])
        url = reverse('problem_list_organization', args=[self.org.slug])
        response = self.client.get(url, {'order': 'solved'})
        self.assertEqual(response.status_code, 200)

    def test_org_problem_list_tag_filter(self):
        """The org problem list filters by tag id, by ?untagged=1, and by the 'untagged' sentinel."""
        tag = OrganizationProblemTag.objects.create(name='dp', organization=self.org)
        tagged = create_problem(code='open_tagged', organization=self.org,
                                is_organization_private=True, is_public=True)
        tagged.tags.add(tag)
        create_problem(code='open_untagged', organization=self.org,
                       is_organization_private=True, is_public=True)

        self.client.force_login(self.users['staff_problem_see_organization'])
        url = reverse('problem_list_organization', args=[self.org.slug])

        codes = {p.code for p in self.client.get(url, {'tag': tag.id}).context['problems']}
        self.assertEqual(codes, {'open_tagged'})

        codes = {p.code for p in self.client.get(url, {'untagged': '1'}).context['problems']}
        self.assertEqual(codes, {'open_untagged'})

        codes = {p.code for p in self.client.get(url, {'tag': 'untagged'}).context['problems']}
        self.assertEqual(codes, {'open_untagged'})

    def test_org_random_respects_tag_filter(self):
        """Random on the org list honors the tag filter and stays within the org."""
        tag = OrganizationProblemTag.objects.create(name='dp', organization=self.org)
        tagged = create_problem(code='open_rand_tagged', organization=self.org,
                                is_organization_private=True, is_public=True)
        tagged.tags.add(tag)
        create_problem(code='open_rand_untagged', organization=self.org,
                       is_organization_private=True, is_public=True)

        self.client.force_login(self.users['staff_problem_see_organization'])
        url = reverse('problem_random_organization', args=[self.org.slug])
        response = self.client.get(url, {'tag': tag.id})
        self.assertEqual(response.status_code, 302)
        self.assertIn('open_rand_tagged', response.url)
