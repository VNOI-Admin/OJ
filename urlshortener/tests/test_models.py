from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from judge.models import Profile
from urlshortener.models import URLShortener


class URLShortenerModelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='testuser', password='testpass')
        cls.profile = Profile.objects.create(user=cls.user)

        cls.other_user = User.objects.create_user(username='otheruser', password='testpass')
        cls.other_profile = Profile.objects.create(user=cls.other_user)

        cls.shortener = URLShortener.objects.create(
            original_url='https://example.com/very/long/url/path',
            short_code='test1234',
        )

    def test_str_representation_short_url(self):
        """Test __str__ for short URLs."""
        shortener = URLShortener(
            original_url='https://short.com',
            short_code='abc',
        )
        self.assertEqual(str(shortener), 'abc -> https://short.com')

    def test_str_representation_long_url(self):
        """Test __str__ truncates long URLs."""
        long_url = 'https://example.com/' + 'a' * 100
        shortener = URLShortener(
            original_url=long_url,
            short_code='xyz',
        )
        self.assertIn('...', str(shortener))
        self.assertTrue(len(str(shortener)) < len(long_url) + 10)

    def test_get_absolute_url(self):
        """Test get_absolute_url returns correct detail URL."""
        url = self.shortener.get_absolute_url()
        self.assertEqual(url, '/shorteners/test1234/')  # Expect trailing slash

    def test_get_short_url(self):
        """Test get_short_url returns just the short_code path."""
        url = self.shortener.get_short_url()
        self.assertEqual(url, '/test1234')

    @override_settings(URLSHORTENER_DOMAIN='short.example.com')
    def test_get_full_short_url_with_domain(self):
        """Test get_full_short_url with URLSHORTENER_DOMAIN setting."""
        url = self.shortener.get_full_short_url()
        self.assertEqual(url, 'https://short.example.com/test1234')

    @override_settings(URLSHORTENER_DOMAIN='https://s.example.com')
    def test_get_full_short_url_with_scheme(self):
        """Test get_full_short_url when domain already has scheme."""
        url = self.shortener.get_full_short_url()
        self.assertEqual(url, 'https://s.example.com/test1234')

    @override_settings(URLSHORTENER_DOMAIN=None)  # Explicitly unset the domain
    def test_get_full_short_url_without_domain(self):
        """Test get_full_short_url falls back to relative URL."""
        url = self.shortener.get_full_short_url()
        self.assertEqual(url, '/test1234')

    def test_record_access(self):
        """Test record_access increments count and updates time."""
        initial_count = self.shortener.access_count
        initial_time = self.shortener.last_access_time

        self.shortener.record_access()
        self.shortener.refresh_from_db()

        self.assertEqual(self.shortener.access_count, initial_count + 1)
        self.assertIsNotNone(self.shortener.last_access_time)
        self.assertNotEqual(self.shortener.last_access_time, initial_time)

    def test_record_access_multiple_times(self):
        """Test record_access increments correctly for multiple accesses."""
        for i in range(5):
            self.shortener.record_access()

        self.shortener.refresh_from_db()
        self.assertEqual(self.shortener.access_count, 5)

    def test_short_code_uniqueness_constraint(self):
        """Test that duplicate short_codes raise an error."""
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            URLShortener.objects.create(
                original_url='https://another.com',
                short_code='test1234',  # Same as self.shortener
            )

    def test_auto_timestamps(self):
        """Test that created_time is set automatically."""
        shortener = URLShortener.objects.create(
            original_url='https://new.com',
            short_code='newabc',
        )
        self.assertIsNotNone(shortener.created_time)

    def test_default_values(self):
        """Test default values for new shorteners."""
        shortener = URLShortener.objects.create(
            original_url='https://defaults.com',
            short_code='defaults',
        )
        self.assertEqual(shortener.access_count, 0)
        self.assertTrue(shortener.is_active)
        self.assertIsNone(shortener.last_access_time)
