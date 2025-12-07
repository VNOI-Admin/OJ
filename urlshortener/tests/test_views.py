from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from judge.models import Profile
from urlshortener.models import URLShortener


class URLShortenerViewsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='testuser', password='testpass')
        cls.profile = Profile.objects.create(user=cls.user)

        cls.other_user = User.objects.create_user(username='otheruser', password='testpass')
        cls.other_profile = Profile.objects.create(user=cls.other_user)

        cls.shortener = URLShortener.objects.create(
            original_url='https://example.com/original',
            suffix='test1234',
            created_user=cls.profile,
        )

    def setUp(self):
        self.client = Client()


class URLShortenerListViewTestCase(URLShortenerViewsTestCase):
    def test_list_requires_login(self):
        """Test that list view requires authentication."""
        response = self.client.get(reverse('urlshortener_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_list_shows_own_shorteners(self):
        """Test that list view shows user's own shorteners."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('urlshortener_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'test1234')

    def test_list_hides_other_users_shorteners(self):
        """Test that list view hides other users' shorteners."""
        other_shortener = URLShortener.objects.create(
            original_url='https://other.com',
            suffix='other123',
            created_user=self.other_profile,
        )

        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('urlshortener_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'test1234')
        self.assertNotContains(response, 'other123')


class URLShortenerCreateViewTestCase(URLShortenerViewsTestCase):
    def test_create_requires_login(self):
        """Test that create view requires authentication."""
        response = self.client.get(reverse('urlshortener_create'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_create_get(self):
        """Test that create form is displayed."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('urlshortener_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Create')

    def test_create_post_valid(self):
        """Test creating a new shortener."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(reverse('urlshortener_create'), {
            'original_url': 'https://newsite.com/path',
            'suffix': 'newsuffix',
            'is_active': True,
        })

        # Should redirect to edit page
        self.assertEqual(response.status_code, 302)

        # Verify shortener was created
        shortener = URLShortener.objects.get(suffix='newsuffix')
        self.assertEqual(shortener.original_url, 'https://newsite.com/path')
        self.assertEqual(shortener.created_user, self.profile)

    def test_create_post_auto_suffix(self):
        """Test creating shortener with auto-generated suffix."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(reverse('urlshortener_create'), {
            'original_url': 'https://autosite.com',
            'suffix': '',  # Empty to auto-generate
            'is_active': True,
        })

        self.assertEqual(response.status_code, 302)

        # Verify shortener was created with generated suffix
        shortener = URLShortener.objects.get(original_url='https://autosite.com')
        self.assertEqual(len(shortener.suffix), 8)

    def test_create_post_invalid_url(self):
        """Test that invalid URL is rejected."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(reverse('urlshortener_create'), {
            'original_url': 'http://localhost/admin',
            'suffix': 'localtest',
            'is_active': True,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cannot shorten internal')


class URLShortenerEditViewTestCase(URLShortenerViewsTestCase):
    def test_edit_requires_login(self):
        """Test that edit view requires authentication."""
        response = self.client.get(
            reverse('urlshortener_edit', args=['test1234'])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_edit_get_owner(self):
        """Test that owner can access edit form."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(
            reverse('urlshortener_edit', args=['test1234'])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'test1234')

    def test_edit_denies_other_user(self):
        """Test that non-owner cannot edit shortener."""
        self.client.login(username='otheruser', password='testpass')
        response = self.client.get(
            reverse('urlshortener_edit', args=['test1234'])
        )
        self.assertEqual(response.status_code, 403)

    def test_edit_post_valid(self):
        """Test editing a shortener."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(
            reverse('urlshortener_edit', args=['test1234']),
            {
                'original_url': 'https://updated.com/path',
                'suffix': 'test1234',
                'is_active': True,
            },
        )

        self.assertEqual(response.status_code, 302)

        self.shortener.refresh_from_db()
        self.assertEqual(self.shortener.original_url, 'https://updated.com/path')


class URLShortenerDeleteViewTestCase(URLShortenerViewsTestCase):
    def test_delete_requires_login(self):
        """Test that delete view requires authentication."""
        response = self.client.get(
            reverse('urlshortener_delete', args=['test1234'])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_delete_get_confirmation(self):
        """Test that delete shows confirmation page."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(
            reverse('urlshortener_delete', args=['test1234'])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'test1234')
        self.assertContains(response, 'Delete')

    def test_delete_denies_other_user(self):
        """Test that non-owner cannot delete shortener."""
        self.client.login(username='otheruser', password='testpass')
        response = self.client.get(
            reverse('urlshortener_delete', args=['test1234'])
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_post(self):
        """Test deleting a shortener."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(
            reverse('urlshortener_delete', args=['test1234'])
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            URLShortener.objects.filter(suffix='test1234').exists()
        )


class URLShortenerRedirectViewTestCase(URLShortenerViewsTestCase):
    """Tests for the redirect view (on the shortener domain)."""

    def test_redirect_success(self):
        """Test successful redirect to original URL."""
        # Import the redirect view URL pattern
        from urlshortener.urls_redirect import urlpatterns
        from django.urls import reverse as url_reverse

        # Manually construct the URL since it's on a different urlconf
        response = self.client.get(f'/{self.shortener.suffix}', follow=False)

        # Since we're not using the separate urlconf, let's test the view directly
        from urlshortener.views import URLShortenerRedirectView
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get(f'/{self.shortener.suffix}')
        view = URLShortenerRedirectView.as_view()
        response = view(request, suffix=self.shortener.suffix)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://example.com/original')

    def test_redirect_increments_access_count(self):
        """Test that redirect increments access count."""
        from urlshortener.views import URLShortenerRedirectView
        from django.test import RequestFactory

        initial_count = self.shortener.access_count

        factory = RequestFactory()
        request = factory.get(f'/{self.shortener.suffix}')
        view = URLShortenerRedirectView.as_view()
        response = view(request, suffix=self.shortener.suffix)

        self.shortener.refresh_from_db()
        self.assertEqual(self.shortener.access_count, initial_count + 1)

    def test_redirect_updates_last_access_time(self):
        """Test that redirect updates last access time."""
        from urlshortener.views import URLShortenerRedirectView
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get(f'/{self.shortener.suffix}')
        view = URLShortenerRedirectView.as_view()
        response = view(request, suffix=self.shortener.suffix)

        self.shortener.refresh_from_db()
        self.assertIsNotNone(self.shortener.last_access_time)

    def test_redirect_nonexistent_404(self):
        """Test that nonexistent suffix returns 404."""
        from urlshortener.views import URLShortenerRedirectView
        from django.test import RequestFactory
        from django.http import Http404

        factory = RequestFactory()
        request = factory.get('/nonexistent')
        view = URLShortenerRedirectView.as_view()

        with self.assertRaises(Http404):
            view(request, suffix='nonexistent')

    def test_redirect_inactive_404(self):
        """Test that inactive shortener returns 404."""
        from urlshortener.views import URLShortenerRedirectView
        from django.test import RequestFactory
        from django.http import Http404

        self.shortener.is_active = False
        self.shortener.save()

        factory = RequestFactory()
        request = factory.get(f'/{self.shortener.suffix}')
        view = URLShortenerRedirectView.as_view()

        with self.assertRaises(Http404):
            view(request, suffix=self.shortener.suffix)

    def test_redirect_no_auth_required(self):
        """Test that redirect works without authentication."""
        from urlshortener.views import URLShortenerRedirectView
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get(f'/{self.shortener.suffix}')
        # Don't attach any user to the request
        view = URLShortenerRedirectView.as_view()
        response = view(request, suffix=self.shortener.suffix)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://example.com/original')
