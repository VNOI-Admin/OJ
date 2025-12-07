"""
URL patterns for the URL shortener redirect domain.

This file should be used as the ROOT_URLCONF for the shortener domain
(e.g., short.vnoj.com). It handles redirects at the root level:
    {CUSTOM_DOMAIN}/<suffix> -> original URL

To use this, configure your Django settings or middleware to use
'urlshortener.urls_redirect' as ROOT_URLCONF for requests to the
shortener domain.

Example nginx configuration:
    server {
        server_name short.vnoj.com;
        # ... other config
    }

Then in Django, you can use a middleware to switch ROOT_URLCONF based on
the Host header, or use django-hosts package.
"""

from django.urls import path

from urlshortener import views

urlpatterns = [
    # Root path - could show a landing page or redirect to main site
    path('', views.URLShortenerRedirectLandingView.as_view(), name='urlshortener_landing'),

    # Redirect by suffix - this is the main functionality
    # {CUSTOM_DOMAIN}/<suffix> redirects to original URL
    path('<str:suffix>', views.URLShortenerRedirectView.as_view(), name='urlshortener_redirect'),
]
