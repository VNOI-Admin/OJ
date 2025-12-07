from django.contrib.auth.models import User
from django.test import TestCase

from judge.models import Profile
from urlshortener.forms import URLShortenerEditForm, URLShortenerForm
from urlshortener.models import URLShortener


class URLShortenerFormTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='testuser', password='testpass')
        cls.profile = Profile.objects.create(user=cls.user)

    def test_valid_form_with_all_fields(self):
        """Test form is valid with all fields filled."""
        form = URLShortenerForm(data={
            'original_url': 'https://example.com/long/url',
            'suffix': 'mysuffix',
            'is_active': True,
        })
        self.assertTrue(form.is_valid())

    def test_valid_form_without_suffix(self):
        """Test form auto-generates suffix when not provided."""
        form = URLShortenerForm(data={
            'original_url': 'https://example.com/long/url',
            'suffix': '',
            'is_active': True,
        })
        self.assertTrue(form.is_valid())
        self.assertEqual(len(form.cleaned_data['suffix']), 8)

    def test_valid_form_minimal_fields(self):
        """Test form is valid with only required fields."""
        form = URLShortenerForm(data={
            'original_url': 'https://example.com',
            'is_active': True,
        })
        self.assertTrue(form.is_valid())

    def test_invalid_suffix_special_chars(self):
        """Test form rejects suffix with special characters."""
        form = URLShortenerForm(data={
            'original_url': 'https://example.com',
            'suffix': 'my@suffix!',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('suffix', form.errors)

    def test_invalid_suffix_spaces(self):
        """Test form rejects suffix with spaces."""
        form = URLShortenerForm(data={
            'original_url': 'https://example.com',
            'suffix': 'my suffix',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('suffix', form.errors)

    def test_valid_suffix_with_hyphens_underscores(self):
        """Test form accepts suffix with hyphens and underscores."""
        form = URLShortenerForm(data={
            'original_url': 'https://example.com',
            'suffix': 'my-suffix_123',
            'is_active': True,
        })
        self.assertTrue(form.is_valid())

    def test_suffix_too_long(self):
        """Test form rejects suffix longer than 50 characters."""
        form = URLShortenerForm(data={
            'original_url': 'https://example.com',
            'suffix': 'a' * 51,
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('suffix', form.errors)

    def test_duplicate_suffix(self):
        """Test form rejects duplicate suffix."""
        URLShortener.objects.create(
            original_url='https://existing.com',
            suffix='taken',
            created_user=self.profile,
        )

        form = URLShortenerForm(data={
            'original_url': 'https://example.com',
            'suffix': 'taken',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('suffix', form.errors)

    def test_invalid_localhost_url(self):
        """Test form rejects localhost URLs."""
        form = URLShortenerForm(data={
            'original_url': 'http://localhost/admin',
            'suffix': 'local',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('original_url', form.errors)

    def test_invalid_127_0_0_1_url(self):
        """Test form rejects 127.0.0.1 URLs."""
        form = URLShortenerForm(data={
            'original_url': 'http://127.0.0.1:8000/admin',
            'suffix': 'local2',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('original_url', form.errors)

    def test_invalid_private_ip_10(self):
        """Test form rejects 10.x.x.x URLs."""
        form = URLShortenerForm(data={
            'original_url': 'http://10.0.0.1/internal',
            'suffix': 'internal',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('original_url', form.errors)

    def test_invalid_private_ip_192_168(self):
        """Test form rejects 192.168.x.x URLs."""
        form = URLShortenerForm(data={
            'original_url': 'http://192.168.1.1/router',
            'suffix': 'router',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('original_url', form.errors)

    def test_invalid_private_ip_172(self):
        """Test form rejects 172.16-31.x.x URLs."""
        form = URLShortenerForm(data={
            'original_url': 'http://172.16.0.1/internal',
            'suffix': 'internal2',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('original_url', form.errors)

    def test_valid_public_ip(self):
        """Test form accepts public IP URLs."""
        form = URLShortenerForm(data={
            'original_url': 'http://8.8.8.8/something',
            'suffix': 'google',
            'is_active': True,
        })
        self.assertTrue(form.is_valid())

    def test_missing_original_url(self):
        """Test form requires original_url."""
        form = URLShortenerForm(data={
            'suffix': 'nourl',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('original_url', form.errors)

    def test_invalid_url_format(self):
        """Test form rejects invalid URL format."""
        form = URLShortenerForm(data={
            'original_url': 'not-a-valid-url',
            'suffix': 'invalid',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('original_url', form.errors)


class URLShortenerEditFormTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='testuser', password='testpass')
        cls.profile = Profile.objects.create(user=cls.user)
        cls.shortener = URLShortener.objects.create(
            original_url='https://example.com',
            suffix='edittest',
            created_user=cls.profile,
        )

    def test_edit_form_requires_suffix(self):
        """Test edit form requires suffix (cannot be empty)."""
        form = URLShortenerEditForm(
            instance=self.shortener,
            data={
                'original_url': 'https://example.com',
                'suffix': '',
                'is_active': True,
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn('suffix', form.errors)

    def test_edit_form_allows_same_suffix(self):
        """Test edit form allows keeping the same suffix."""
        form = URLShortenerEditForm(
            instance=self.shortener,
            data={
                'original_url': 'https://example.com/updated',
                'suffix': 'edittest',
                'is_active': True,
            },
        )
        self.assertTrue(form.is_valid())

    def test_edit_form_rejects_taken_suffix(self):
        """Test edit form rejects suffix taken by another shortener."""
        URLShortener.objects.create(
            original_url='https://other.com',
            suffix='othersuffix',
            created_user=self.profile,
        )

        form = URLShortenerEditForm(
            instance=self.shortener,
            data={
                'original_url': 'https://example.com',
                'suffix': 'othersuffix',
                'is_active': True,
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn('suffix', form.errors)

    def test_edit_form_allows_new_unique_suffix(self):
        """Test edit form allows changing to a new unique suffix."""
        form = URLShortenerEditForm(
            instance=self.shortener,
            data={
                'original_url': 'https://example.com',
                'suffix': 'newsuffix',
                'is_active': True,
            },
        )
        self.assertTrue(form.is_valid())
