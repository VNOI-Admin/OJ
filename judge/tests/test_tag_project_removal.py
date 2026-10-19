from django.apps import apps
from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse


class TagProjectRemovalTestCase(SimpleTestCase):
    def test_legacy_tag_routes_and_models_are_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse('tagproblem_list')
        with self.assertRaises(LookupError):
            apps.get_model('judge', 'TagProblem')

    def test_active_problem_taxonomies_are_preserved(self):
        self.assertEqual(apps.get_model('judge', 'ProblemType').__name__, 'ProblemType')
        self.assertEqual(apps.get_model('judge', 'OrganizationProblemTag').__name__, 'OrganizationProblemTag')
