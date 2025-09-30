import csv
import os

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from judge.models import Language, Organization, Profile
from judge.models.profile import Badge
from judge.tasks.user import bulk_create_users
from judge.utils.users import validate_user_rows


def row(**kw):
    base = {'username': 'alice', 'fullname': 'Alice A'}
    base.update(kw)
    return base


class ValidateUserRowsTest(TestCase):
    def test_valid_minimal(self):
        self.assertIsNone(validate_user_rows([row()]))

    def test_empty(self):
        self.assertIsNotNone(validate_user_rows([]))

    def test_missing_username(self):
        self.assertIsNotNone(validate_user_rows([row(username='')]))

    def test_missing_fullname_is_allowed(self):
        self.assertIsNone(validate_user_rows([row(fullname='')]))

    def test_bad_username_chars(self):
        self.assertIsNotNone(validate_user_rows([row(username='bad name!')]))
        self.assertIsNotNone(validate_user_rows([row(username='john.doe')]))
        self.assertIsNotNone(validate_user_rows([row(username='john-doe')]))

    def test_username_too_long(self):
        self.assertIsNotNone(validate_user_rows([row(username='a' * 21)]))

    def test_duplicate_in_batch(self):
        self.assertIsNotNone(validate_user_rows([row(), row(fullname='Other')]))

    def test_existing_in_db(self):
        User.objects.create(username='alice')
        self.assertIsNotNone(validate_user_rows([row()]))

    def test_organization_too_long(self):
        self.assertIsNotNone(validate_user_rows([row(organization='a' * 129)]))

    def test_duplicate_organization_in_db(self):
        self.assertIsNone(validate_user_rows([row(organization='Uni')]))
        Organization.objects.create(name='Uni', slug='uni1', short_name='uni1')
        self.assertIsNone(validate_user_rows([row(organization='Uni')]))
        Organization.objects.create(name='Uni', slug='uni2', short_name='uni2')
        self.assertIsNotNone(validate_user_rows([row(organization='Uni')]))
        self.assertIsNone(validate_user_rows([row(organization='Other')]))

    def test_duplicate_badge_in_db(self):
        Badge.objects.create(name='VN')
        self.assertIsNone(validate_user_rows([row(country='VN')]))
        Badge.objects.create(name='VN')
        self.assertIsNotNone(validate_user_rows([row(country='VN')]))

    def test_invalid_extra(self):
        self.assertIsNone(validate_user_rows([row(extra=[['School', 'X']])]))
        self.assertIsNotNone(validate_user_rows([row(extra='School')]))
        self.assertIsNotNone(validate_user_rows([row(extra=[['School']])]))


class BulkCreateUsersTaskTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        Language.objects.get_or_create(key=settings.DEFAULT_USER_LANGUAGE, defaults={'name': 'C++20'})

    def test_extra_columns_in_result(self):
        task = bulk_create_users.apply(args=([
            row(username='bob', email='bob@example.com', extra=[['School', 'HCMUS'], ['2024', '7']]),
            row(username='carol', extra=[['School', 'HUST'], ['2024', '']]),
        ], None))
        result = dict(task.get(), task_id=task.id)
        self.addCleanup(os.remove, result['output_file'])
        with open(result['output_file'], newline='') as f:
            reader = csv.DictReader(f)
            users = list(reader)
        self.assertEqual(reader.fieldnames, ['username', 'fullname', 'password', 'email', 'School', '2024'])
        self.assertEqual([(u['username'], u['School'], u['2024']) for u in users],
                         [('bob', 'HCMUS', '7'), ('carol', 'HUST', '')])
        self.assertTrue(User.objects.filter(username='carol').exists())

        admin = User.objects.create_superuser('root', password='root')
        Profile.objects.create(user=admin, language=Language.objects.get(key=settings.DEFAULT_USER_LANGUAGE))
        self.client.force_login(admin)
        response = self.client.get(reverse('bulk_user_result', args=[result['task_id']]))
        self.assertContains(response, '<th data-key="School">School</th>', html=True)
        self.assertContains(response, '<td>HCMUS</td>', html=True)

    def test_email_column_only_when_present(self):
        task = bulk_create_users.apply(args=([row(username='dave')], None))
        output_file = task.get()['output_file']
        self.addCleanup(os.remove, output_file)
        with open(output_file, newline='') as f:
            self.assertEqual(csv.DictReader(f).fieldnames, ['username', 'fullname', 'password'])
