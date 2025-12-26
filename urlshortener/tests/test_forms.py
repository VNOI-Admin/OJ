from django.contrib.auth.models import User
from django.test import TestCase

from judge.models import Profile
from urlshortener.forms import URLShortenerForm
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
            'short_code': 'myshort_code',
            'is_active': True,
        })
        self.assertTrue(form.is_valid())

    def test_invalid_form_without_short_code(self):
        """Test form is invalid when short_code is not provided (as it's required)."""
        form = URLShortenerForm(data={
            'original_url': 'https://example.com/long/url',
            'short_code': '',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('short_code', form.errors)

    def test_invalid_form_missing_short_code(self):
        """Test form is invalid when short_code field is missing."""
        form = URLShortenerForm(data={
            'original_url': 'https://example.com',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('short_code', form.errors)

    def test_invalid_short_code_special_chars(self):
        """Test form rejects short_code with special characters."""
        form = URLShortenerForm(data={
            'original_url': 'https://example.com',
            'short_code': 'my@short_code!',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('short_code', form.errors)

    def test_invalid_short_code_spaces(self):
        """Test form rejects short_code with spaces."""
        form = URLShortenerForm(data={
            'original_url': 'https://example.com',
            'short_code': 'my short_code',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('short_code', form.errors)

    def test_valid_short_code_with_hyphens_underscores(self):
        """Test form accepts short_code with hyphens and underscores."""
        form = URLShortenerForm(data={
            'original_url': 'https://example.com',
            'short_code': 'my-short_code_123',
            'is_active': True,
        })
        self.assertTrue(form.is_valid())

    def test_short_code_too_long(self):
        """Test form rejects short_code longer than 50 characters."""
        form = URLShortenerForm(data={
            'original_url': 'https://example.com',
            'short_code': 'a' * 51,
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('short_code', form.errors)

    def test_duplicate_short_code(self):
        """Test form rejects duplicate short_code."""
        URLShortener.objects.create(
            original_url='https://existing.com',
            short_code='taken',
        )

        form = URLShortenerForm(data={
            'original_url': 'https://example.com',
            'short_code': 'taken',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('short_code', form.errors)

    def test_missing_original_url(self):
        """Test form requires original_url."""
        form = URLShortenerForm(data={
            'short_code': 'nourl',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('original_url', form.errors)

    def test_invalid_url_format(self):
        """Test form rejects invalid URL format."""
        form = URLShortenerForm(data={
            'original_url': 'not-a-valid-url',
            'short_code': 'invalid',
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
            short_code='edittest',
        )

    def test_edit_form_requires_short_code(self):
        """Test edit form requires short_code (cannot be empty)."""
        form = URLShortenerForm(
            instance=self.shortener,
            data={
                'original_url': 'https://example.com',
                'short_code': '',
                'is_active': True,
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn('short_code', form.errors)

    def test_edit_form_allows_same_short_code(self):
        """Test edit form allows keeping the same short_code."""
        form = URLShortenerForm(
            instance=self.shortener,
            data={
                'original_url': 'https://example.com/updated',
                'short_code': 'edittest',
                'is_active': True,
            },
        )
        self.assertTrue(form.is_valid())

    def test_edit_form_rejects_taken_short_code(self):
        """Test edit form rejects short_code taken by another shortener."""
        URLShortener.objects.create(
            original_url='https://other.com',
            short_code='othershort_code',
        )

        form = URLShortenerForm(
            instance=self.shortener,
            data={
                'original_url': 'https://example.com',
                'short_code': 'othershort_code',
                'is_active': True,
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn('short_code', form.errors)

    def test_edit_form_allows_new_unique_short_code(self):
        """Test edit form allows changing to a new unique short_code."""
        form = URLShortenerForm(
            instance=self.shortener,
            data={
                'original_url': 'https://example.com',
                'short_code': 'newshort_code',
                'is_active': True,
            },
        )
        self.assertTrue(form.is_valid())
