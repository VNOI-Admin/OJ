from django.contrib.auth.models import User
from django.test import TestCase

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
