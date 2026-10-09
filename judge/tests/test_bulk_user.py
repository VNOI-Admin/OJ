import csv
import html
import json
import os
import re
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import gettext as _

from judge.models import Language, Organization, Profile
from judge.models.profile import Badge
from judge.tasks.user import bulk_create_users, send_account_emails
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


class SendAccountViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        language = Language.objects.get_or_create(key=settings.DEFAULT_USER_LANGUAGE, defaults={'name': 'C++20'})[0]
        cls.admin = User.objects.create_superuser('root', password='root')
        Profile.objects.create(user=cls.admin, language=language)
        org = Organization.objects.create(name='HCMUS', slug='hcmus', short_name='hcmus')
        for username, email in (('team1', 't1@example.com'), ('team2', '')):
            user = User.objects.create(username=username, first_name=username.upper(), email=email)
            Profile.objects.create(user=user, language=language).organizations.set([org])

    def setUp(self):
        self.client.force_login(self.admin)

    def upload(self, content, name='accounts.csv'):
        return self.client.post(reverse('send_account'), {
            'file': SimpleUploadedFile(name, content.encode('utf-8-sig')), 'subject': 'VNOI Cup', 'is_practice': 'on',
        })

    def test_page_loads(self):
        response = self.client.get(reverse('send_account'))
        self.assertContains(response, 'name="file"')
        self.assertContains(response, 'value="ICPC Contest"')
        self.assertContains(response, '<input type="checkbox" name="is_practice" checked>', html=True)

    def test_remembers_contest_name(self):
        self.upload('username,password\nteam1,pw1\n')
        self.assertContains(self.client.get(reverse('send_account')), 'value="VNOI Cup"')

    def test_superuser_only(self):
        self.client.force_login(User.objects.get(username='team1'))
        self.assertEqual(self.client.get(reverse('send_account')).status_code, 403)

    def test_review_shows_problems_and_blocks_send(self):
        response = self.upload('username,password\nteam1,pw1\nteam2,pw2\nghost,pw3\n')
        self.assertContains(response, 'no email address')
        self.assertContains(response, 'user not found')
        self.assertNotContains(response, '<input type="hidden" name="send" value="1">', html=True)

    def test_pick_columns(self):
        # Headers that match nothing: no review until the columns are picked.
        response = self.upload('STT,Tài khoản,MK\n1,team1,pw1\n')
        self.assertContains(response, 'Choose which columns hold the username and password.')
        self.assertContains(response, '<option value="Tài khoản">Tài khoản</option>', html=True)
        self.assertNotContains(response, '<input type="hidden" name="send" value="1">', html=True)

        response = self.client.post(reverse('send_account'), {
            'raw_json': response.context['raw_json'], 'subject': 'VNOI Cup',
            'username_col': 'Tài khoản', 'password_col': 'MK',
        })
        self.assertContains(response, '<input type="hidden" name="send" value="1">', html=True)
        self.assertEqual(json.loads(response.context['rows_json']), [{'username': 'team1', 'password': 'pw1'}])

    def test_guess_columns(self):
        # English labels, and the translated labels the old result page's Excel used.
        for header in ('Username,Password', '%s,%s' % (_('Username'), _('Password'))):
            response = self.upload(f'{header}\nteam1,pw1\n')
            self.assertEqual(response.context['username_col'], header.split(',')[0])
            self.assertContains(response, '<input type="hidden" name="send" value="1">', html=True)

    def test_review_then_send(self):
        response = self.upload('username,password\nteam1,pw1\n')
        self.assertContains(response, '<input type="hidden" name="send" value="1">', html=True)
        self.assertContains(response, 'VNOI Cup - TEAM1')  # preview subject
        self.assertContains(response, 'srcdoc="&lt;div style=&quot;')  # preview body escaped into the attribute
        self.assertIn('pw1', response.context['preview'].body)
        # Post only the send form's own inputs, as a browser does (button names are not sent, see common.js).
        send_form = re.search(r'<form[^>]*id="send-account-send".*?</form>', response.content.decode(), re.S).group()
        data = {html.unescape(name): html.unescape(value)
                for name, value in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', send_form)}

        with mock.patch('judge.views.user.send_account_emails.delay',
                        side_effect=lambda *args: send_account_emails.apply(args=args)):
            response = self.client.post(reverse('send_account'), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['t1@example.com'])
        self.assertEqual(mail.outbox[0].subject, 'VNOI Cup - TEAM1')
        self.assertIn('pw1', mail.outbox[0].body)
        self.assertIn('thi thử', mail.outbox[0].body)  # practice notice
        self.assertIn('href="https://', mail.outbox[0].body)

    def test_send_rechecks_rows(self):
        with mock.patch('judge.views.user.send_account_emails.delay') as delay:
            self.client.post(reverse('send_account'), {
                'send': '', 'rows_json': '[{"username": "team2", "password": "x"}]', 'subject': 'VNOI Cup',
            })
        delay.assert_not_called()
