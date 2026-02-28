from django.conf import settings


class URLShortenerMiddleware:
    """
    Middleware to handle URL shortener redirects based on the Host header.

    When a request comes from the URL shortener domain (URLSHORTENER_DOMAIN),
    this middleware switches the ROOT_URLCONF to use the shortener-specific
    URL patterns that handle redirects at the root level.

    Configuration:
        Add 'urlshortener.middleware.URLShortenerMiddleware' to MIDDLEWARE
        (should be placed early, before URL resolution happens).

        Set URLSHORTENER_DOMAIN in settings to the shortener domain:
            URLSHORTENER_DOMAIN = 'short.vnoj.com'
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.shortener_domain = getattr(settings, 'URLSHORTENER_DOMAIN', None)

    def __call__(self, request):
        if self.shortener_domain and request.get_host() == self.shortener_domain:
            request.urlconf = 'urlshortener.urls_redirect'

        return self.get_response(request)
