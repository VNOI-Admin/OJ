from django.contrib.auth.models import Permission, User
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
            short_code='test1234',
        )

        # Grant permissions to cls.user
        add_permission = Permission.objects.get(codename='add_urlshortener')
        view_permission = Permission.objects.get(codename='view_urlshortener')
        change_permission = Permission.objects.get(codename='change_urlshortener')
        delete_permission = Permission.objects.get(codename='delete_urlshortener')

        cls.user.user_permissions.add(add_permission, view_permission, change_permission, delete_permission)

    def setUp(self):
        self.client = Client()


class URLShortenerListViewTestCase(URLShortenerViewsTestCase):
    def test_list_requires_login(self):
        """Test that list view requires authentication."""
        response = self.client.get(reverse('urlshortener_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_list_shows_all_shorteners(self):
        """Test that list view shows all shorteners to a user with permission."""
        other_shortener = URLShortener.objects.create(  # noqa: F841
            original_url='https://other.com',
            short_code='other123',
        )

        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('urlshortener_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'test1234')
        self.assertContains(response, 'other123')


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
            'short_code': 'newshort_code',
            'is_active': True,
        })

        # Should redirect to edit page
        self.assertEqual(response.status_code, 302)

        # Verify shortener was created
        shortener = URLShortener.objects.get(short_code='newshort_code')
        self.assertEqual(shortener.original_url, 'https://newsite.com/path')

    def test_create_post_empty_short_code(self):
        """Test creating shortener with empty short_code (should fail validation)."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(reverse('urlshortener_create'), {
            'original_url': 'https://autosite.com',
            'short_code': '',  # Empty
            'is_active': True,
        })

        self.assertEqual(response.status_code, 200)  # Form should re-render
        self.assertContains(response, 'This field is required.')


class URLShortenerEditViewTestCase(URLShortenerViewsTestCase):
    def test_edit_requires_login(self):
        """Test that edit view requires authentication."""
        response = self.client.get(reverse('urlshortener_edit', args=['test1234']))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_edit_denies_user_without_permission(self):
        """Test that user without permission cannot edit shortener."""
        self.client.login(username='otheruser', password='testpass')
        response = self.client.get(reverse('urlshortener_edit', args=['test1234']))
        self.assertEqual(response.status_code, 403)

    def test_edit_post_valid(self):
        """Test editing a shortener."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(
            reverse('urlshortener_edit', args=['test1234']),
            {
                'original_url': 'https://updated.com/path',
                'short_code': 'test1234',
                'is_active': True,
            },
        )

        self.assertEqual(response.status_code, 302)

        self.shortener.refresh_from_db()
        self.assertEqual(self.shortener.original_url, 'https://updated.com/path')


class URLShortenerDeleteViewTestCase(URLShortenerViewsTestCase):
    def test_delete_requires_login(self):
        """Test that delete view requires authentication."""
        response = self.client.get(reverse('urlshortener_delete', args=['test1234']))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_delete_get_confirmation(self):
        """Test that delete shows confirmation page."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('urlshortener_delete', args=['test1234']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'test1234')
        self.assertContains(response, 'Delete')

    def test_delete_denies_user_without_permission(self):
        """Test that user without permission cannot delete shortener."""
        self.client.login(username='otheruser', password='testpass')
        response = self.client.get(reverse('urlshortener_delete', args=['test1234']))
        self.assertEqual(response.status_code, 403)

    def test_delete_post(self):
        """Test deleting a shortener."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(reverse('urlshortener_delete', args=['test1234']))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(URLShortener.objects.filter(short_code='test1234').exists())


class URLShortenerRedirectViewTestCase(URLShortenerViewsTestCase):
    """Tests for the redirect view (on the shortener domain)."""

    def test_redirect_success(self):
        """Test successful redirect to original URL."""
        # Manually construct the URL since it's on a different urlconf
        response = self.client.get(f'/{self.shortener.short_code}', follow=False)

        # Since we're not using the separate urlconf, let's test the view directly
        from urlshortener.views import URLShortenerRedirectView
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get(f'/{self.shortener.short_code}')
        view = URLShortenerRedirectView.as_view()
        response = view(request, short_code=self.shortener.short_code)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://example.com/original')

    def test_redirect_increments_access_count(self):
        """Test that redirect increments access count."""
        from urlshortener.views import URLShortenerRedirectView
        from django.test import RequestFactory

        initial_count = self.shortener.access_count

        factory = RequestFactory()
        request = factory.get(f'/{self.shortener.short_code}')
        view = URLShortenerRedirectView.as_view()
        response = view(request, short_code=self.shortener.short_code)  # noqa: F841

        self.shortener.refresh_from_db()
        self.assertEqual(self.shortener.access_count, initial_count + 1)

    def test_redirect_updates_last_access_time(self):
        """Test that redirect updates last access time."""
        from urlshortener.views import URLShortenerRedirectView
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get(f'/{self.shortener.short_code}')
        view = URLShortenerRedirectView.as_view()
        response = view(request, short_code=self.shortener.short_code)  # noqa: F841

        self.shortener.refresh_from_db()
        self.assertIsNotNone(self.shortener.last_access_time)

    def test_redirect_nonexistent_404(self):
        """Test that nonexistent short_code returns 404."""
        from urlshortener.views import URLShortenerRedirectView
        from django.test import RequestFactory
        from django.http import Http404

        factory = RequestFactory()
        request = factory.get('/nonexistent')
        view = URLShortenerRedirectView.as_view()

        with self.assertRaises(Http404):
            view(request, short_code='nonexistent')

    def test_redirect_inactive_404(self):
        """Test that inactive shortener returns 404."""
        from urlshortener.views import URLShortenerRedirectView
        from django.test import RequestFactory
        from django.http import Http404

        self.shortener.is_active = False
        self.shortener.save()

        factory = RequestFactory()
        request = factory.get(f'/{self.shortener.short_code}')
        view = URLShortenerRedirectView.as_view()

        with self.assertRaises(Http404):
            view(request, short_code=self.shortener.short_code)

    def test_redirect_no_auth_required(self):
        """Test that redirect works without authentication."""
        from urlshortener.views import URLShortenerRedirectView
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get(f'/{self.shortener.short_code}')
        # Don't attach any user to the request
        view = URLShortenerRedirectView.as_view()
        response = view(request, short_code=self.shortener.short_code)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://example.com/original')
