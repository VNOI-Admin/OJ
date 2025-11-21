import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.conf import settings

from judge.forms import URLShortenerForm
from judge.models import Profile, URLShortener


class URLShortenerFormTest(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='alice', password='pwd')
        self.profile = Profile.objects.create(user=user)

    def test_blank_short_code_generates_random_code(self):
        form = URLShortenerForm(
            data={
                'short_code': '',
                'long_url': 'https://example.com/docs',
                'description': '',
            },
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(len(form.cleaned_data['short_code']), 5)

    def test_rejects_reserved_and_length_constraints(self):
        form = URLShortenerForm(
            data={
                'short_code': 'ad',
                'long_url': 'https://example.com',
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn('Độ dài tên rút gọn phải từ 3 đến 30 ký tự', form.errors['short_code'][0])

        form = URLShortenerForm(
            data={
                'short_code': 'admin',
                'long_url': 'https://example.com',
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn('được hệ thống sử dụng', form.errors['short_code'][0])

    def test_unique_case_insensitive(self):
        URLShortener.objects.create(
            short_code='CaseCode',
            long_url='https://example.com',
            creator=self.profile,
        )
        form = URLShortenerForm(
            data={
                'short_code': 'casecode',
                'long_url': 'https://example.org',
            },
            instance=URLShortener(short_code='casecode', creator=self.profile),
        )
        self.assertFalse(form.is_valid())
        self.assertIn('đã tồn tại', form.errors['short_code'][0])

    def test_generate_unique_code_collision_retry(self):
        URLShortener.objects.create(
            short_code='abcde',
            long_url='https://example.com',
            creator=self.profile,
        )
        with patch('judge.models.interface.get_random_string', side_effect=['abcde', 'fghij']):
            code = URLShortener.generate_unique_code()
        self.assertEqual(code, 'fghij')


class URLShortenerViewsTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.creator_user = user_model.objects.create_user(username='bob', password='pwd')
        self.other_user = user_model.objects.create_user(username='carol', password='pwd')
        self.admin_user = user_model.objects.create_user(username='dave', password='pwd')
        self.creator_profile = Profile.objects.create(user=self.creator_user)
        self.other_profile = Profile.objects.create(user=self.other_user)
        self.admin_profile = Profile.objects.create(user=self.admin_user)

        perm_create = Permission.objects.get(codename='create_url_shortener')
        perm_view_all = Permission.objects.get(codename='view_all_url_stats')
        self.creator_user.user_permissions.add(perm_create)
        self.admin_user.user_permissions.add(perm_create, perm_view_all)

        self.shortener = URLShortener.objects.create(
            short_code='hello',
            long_url='https://example.com/hello',
            creator=self.creator_profile,
        )
        self._ensure_jsi18n_stub()

    def _ensure_jsi18n_stub(self):
        locale = settings.LANGUAGE_CODE or 'en'
        target_dir = os.path.join(settings.BASE_DIR, 'static', 'jsi18n', locale)
        os.makedirs(target_dir, exist_ok=True)
        target_file = os.path.join(target_dir, 'djangojs.js')
        if not os.path.exists(target_file):
            with open(target_file, 'w', encoding='utf-8') as f:
                f.write('// stub for tests\n')

    def test_list_shows_only_owned_without_permission(self):
        self.client.login(username='carol', password='pwd')
        response = self.client.get(reverse('url_shortener_list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'hello')

    def test_list_shows_all_with_permission(self):
        self.client.login(username='dave', password='pwd')
        response = self.client.get(reverse('url_shortener_list'))
        self.assertContains(response, 'hello')

    def test_create_requires_permission(self):
        self.client.login(username='carol', password='pwd')
        response = self.client.get(reverse('url_shortener_create'))
        self.assertEqual(response.status_code, 403)

        self.client.login(username='bob', password='pwd')
        response = self.client.post(
            reverse('url_shortener_create'),
            data={
                'short_code': 'newcode',
                'long_url': 'https://example.com/new',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(URLShortener.objects.filter(short_code='newcode').exists())

    def test_update_and_delete_authorization(self):
        self.client.login(username='bob', password='pwd')
        response = self.client.post(
            reverse('url_shortener_edit', args=['hello']),
            data={
                'short_code': 'hello',
                'long_url': 'https://example.com/updated',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.shortener.refresh_from_db()
        self.assertEqual(self.shortener.long_url, 'https://example.com/updated')

        self.client.logout()
        self.client.login(username='carol', password='pwd')
        response = self.client.get(reverse('url_shortener_edit', args=['hello']))
        self.assertEqual(response.status_code, 404)

        self.client.logout()
        self.client.login(username='dave', password='pwd')
        response = self.client.post(reverse('url_shortener_delete', args=['hello']))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(URLShortener.objects.filter(short_code='hello').exists())

    def test_redirect_increments_clicks(self):
        before_clicks = self.shortener.click_count
        response = self.client.get(reverse('url_shortener_redirect', args=['hello']))
        self.assertEqual(response.status_code, 302)
        self.shortener.refresh_from_db()
        self.assertEqual(self.shortener.click_count, before_clicks + 1)
        self.assertIsNotNone(self.shortener.last_accessed)
