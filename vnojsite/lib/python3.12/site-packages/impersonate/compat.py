# compatibility module for handling Django upgrade namespace changes
try:
    from django.urls import reverse
except ImportError:
    from django.core.urlresolvers import reverse

__all__ = ["reverse"]
