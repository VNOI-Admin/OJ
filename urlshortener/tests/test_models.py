from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from judge.models import Profile
from urlshortener.models import URLShortener, generate_suffix


class GenerateSuffixTestCase(TestCase):
    def test_generate_suffix_default_length(self):
        """Test that generate_suffix creates an 8-character string by default."""
        suffix = generate_suffix()
        self.assertEqual(len(suffix), 8)

    def test_generate_suffix_custom_length(self):
        """Test that generate_suffix respects custom length."""
        suffix = generate_suffix(length=12)
        self.assertEqual(len(suffix), 12)

    def test_generate_suffix_alphanumeric(self):
        """Test that generate_suffix only uses alphanumeric characters."""
        suffix = generate_suffix(length=100)
        self.assertTrue(suffix.isalnum())

    def test_generate_suffix_uniqueness(self):
        """Test that multiple calls generate different suffixes."""
        suffixes = {generate_suffix() for _ in range(100)}
        # With 62^8 possible combinations, collisions should be extremely rare
        self.assertEqual(len(suffixes), 100)


class URLShortenerModelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='testuser', password='testpass')
        cls.profile = Profile.objects.create(user=cls.user)

        cls.other_user = User.objects.create_user(username='otheruser', password='testpass')
        cls.other_profile = Profile.objects.create(user=cls.other_user)

        cls.shortener = URLShortener.objects.create(
            original_url='https://example.com/very/long/url/path',
            suffix='test1234',
            created_user=cls.profile,
        )

    def test_str_representation_short_url(self):
        """Test __str__ for short URLs."""
        shortener = URLShortener(
            original_url='https://short.com',
            suffix='abc',
            created_user=self.profile,
        )
        self.assertEqual(str(shortener), 'abc -> https://short.com')

    def test_str_representation_long_url(self):
        """Test __str__ truncates long URLs."""
        long_url = 'https://example.com/' + 'a' * 100
        shortener = URLShortener(
            original_url=long_url,
            suffix='xyz',
            created_user=self.profile,
        )
        self.assertIn('...', str(shortener))
        self.assertTrue(len(str(shortener)) < len(long_url) + 10)

    def test_get_absolute_url(self):
        """Test get_absolute_url returns correct edit URL."""
        url = self.shortener.get_absolute_url()
        self.assertEqual(url, '/shorteners/test1234/edit/')

    def test_get_short_url(self):
        """Test get_short_url returns just the suffix path."""
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

    def test_get_full_short_url_without_domain(self):
        """Test get_full_short_url falls back to relative URL."""
        url = self.shortener.get_full_short_url()
        self.assertEqual(url, '/test1234')

    def test_is_accessible_active(self):
        """Test is_accessible returns True for active shortener."""
        self.assertTrue(self.shortener.is_accessible())

    def test_is_accessible_inactive(self):
        """Test is_accessible returns False for inactive shortener."""
        self.shortener.is_active = False
        self.shortener.save()
        self.assertFalse(self.shortener.is_accessible())

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

    def test_can_see_owner(self):
        """Test can_see returns True for owner."""
        self.assertTrue(self.shortener.can_see(self.user))

    def test_can_see_other_user(self):
        """Test can_see returns False for non-owner."""
        self.assertFalse(self.shortener.can_see(self.other_user))

    def test_can_see_anonymous(self):
        """Test can_see returns False for anonymous user."""
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(self.shortener.can_see(AnonymousUser()))

    def test_is_editable_by_owner(self):
        """Test is_editable_by returns True for owner."""
        self.assertTrue(self.shortener.is_editable_by(self.user))

    def test_is_editable_by_other_user(self):
        """Test is_editable_by returns False for non-owner."""
        self.assertFalse(self.shortener.is_editable_by(self.other_user))

    def test_is_editable_by_anonymous(self):
        """Test is_editable_by returns False for anonymous user."""
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(self.shortener.is_editable_by(AnonymousUser()))

    def test_generate_unique_suffix(self):
        """Test generate_unique_suffix creates a unique suffix."""
        suffix = URLShortener.generate_unique_suffix()
        self.assertEqual(len(suffix), 8)
        self.assertFalse(URLShortener.objects.filter(suffix=suffix).exists())

    def test_generate_unique_suffix_avoids_existing(self):
        """Test generate_unique_suffix doesn't return existing suffixes."""
        # Create a shortener with a known suffix
        existing_suffix = 'existing'
        URLShortener.objects.create(
            original_url='https://example.com',
            suffix=existing_suffix,
            created_user=self.profile,
        )

        # Generate many suffixes and verify none match the existing one
        for _ in range(10):
            new_suffix = URLShortener.generate_unique_suffix()
            self.assertNotEqual(new_suffix, existing_suffix)

    def test_suffix_uniqueness_constraint(self):
        """Test that duplicate suffixes raise an error."""
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            URLShortener.objects.create(
                original_url='https://another.com',
                suffix='test1234',  # Same as self.shortener
                created_user=self.profile,
            )

    def test_auto_timestamps(self):
        """Test that created_time and last_edited_time are set automatically."""
        shortener = URLShortener.objects.create(
            original_url='https://new.com',
            suffix='newabc',
            created_user=self.profile,
        )
        self.assertIsNotNone(shortener.created_time)
        self.assertIsNotNone(shortener.last_edited_time)

    def test_last_edited_time_updates(self):
        """Test that last_edited_time updates on save."""
        original_edited_time = self.shortener.last_edited_time

        # Wait a tiny bit and update
        import time
        time.sleep(0.01)

        self.shortener.original_url = 'https://updated.com'
        self.shortener.save()

        self.assertGreater(self.shortener.last_edited_time, original_edited_time)

    def test_default_values(self):
        """Test default values for new shorteners."""
        shortener = URLShortener.objects.create(
            original_url='https://defaults.com',
            suffix='defaults',
            created_user=self.profile,
        )
        self.assertEqual(shortener.access_count, 0)
        self.assertTrue(shortener.is_active)
        self.assertIsNone(shortener.last_access_time)
