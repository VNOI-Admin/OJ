from django.db import models
from django.db.models import CASCADE, F
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from judge.models.profile import Profile


class URLShortener(models.Model):
    original_url = models.URLField(verbose_name=_('original URL'))
    short_code = models.SlugField(verbose_name=_('short code'), unique=True)
    created_user = models.ForeignKey(
        Profile,
        verbose_name=_('created by'),
        on_delete=CASCADE,
        related_name='url_shorteners',
    )
    created_time = models.DateTimeField(
        verbose_name=_('created time'),
        auto_now_add=True,
    )
    last_edited_time = models.DateTimeField(
        verbose_name=_('last edited time'),
        auto_now=True,
    )
    last_access_time = models.DateTimeField(
        verbose_name=_('last access time'),
        null=True,
        blank=True,
    )
    access_count = models.PositiveIntegerField(
        verbose_name=_('access count'),
        default=0,
    )
    is_active = models.BooleanField(
        verbose_name=_('is active'),
        default=True,
        help_text=_('Whether this shortener is active.'),
    )

    class Meta:
        verbose_name = _('URL shortener')
        verbose_name_plural = _('URL shorteners')
        ordering = ['-created_time']
        permissions = (
            ('edit_all_urlshortener', _('Edit all URL shorteners')),
            ('view_all_urlshortener', _('View all URL shorteners')),
        )

    def __str__(self):
        if len(self.original_url) > 50:
            return f'{self.short_code} -> {self.original_url[:50]}...'
        return f'{self.short_code} -> {self.original_url}'

    def get_absolute_url(self):
        return reverse('urlshortener_edit', args=[self.short_code])

    def get_short_url(self):
        """Get the relative short URL path."""
        return f'/{self.short_code}'

    def get_full_short_url(self):
        """
        Get the full short URL including the custom domain.
        Uses URLSHORTENER_DOMAIN setting if available.
        """
        from django.conf import settings
        domain = getattr(settings, 'URLSHORTENER_DOMAIN', None)
        if domain:
            # Ensure domain has scheme
            if not domain.startswith(('http://', 'https://')):
                domain = f'https://{domain}'
            return f'{domain.rstrip("/")}/{self.short_code}'
        # Fallback to relative URL
        return self.get_short_url()

    def is_accessible(self):
        """Check if the shortener is accessible."""
        return self.is_active

    def record_access(self):
        """Record an access to this shortener."""
        self.access_count = F('access_count') + 1
        self.last_access_time = timezone.now()
        self.save(update_fields=['access_count', 'last_access_time'])

    def can_see(self, user):
        """Check if the user can see this shortener."""
        if not user.is_authenticated:
            return False
        if user.has_perm('urlshortener.view_all_urlshortener'):
            return True
        return self.created_user.user == user

    def is_editable_by(self, user):
        """Check if the user can edit this shortener."""
        if not user.is_authenticated:
            return False
        if user.has_perm('urlshortener.edit_all_urlshortener'):
            return True
        return self.created_user.user == user
