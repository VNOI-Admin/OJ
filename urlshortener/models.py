from django.db import models
from django.db.models import F
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class URLShortener(models.Model):
    original_url = models.URLField(verbose_name=_('original URL'))
    short_code = models.SlugField(verbose_name=_('short code'), unique=True)
    created_time = models.DateTimeField(
        verbose_name=_('created time'),
        auto_now_add=True,
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
    )

    class Meta:
        verbose_name = _('URL shortener')
        verbose_name_plural = _('URL shorteners')
        ordering = ['-created_time']

    def __str__(self):
        if len(self.original_url) > 50:
            return f'{self.short_code} -> {self.original_url[:50]}...'
        return f'{self.short_code} -> {self.original_url}'

    def get_absolute_url(self):
        return reverse('urlshortener_detail', args=[self.short_code])

    def get_short_url(self):
        return f'/{self.short_code}'

    def get_full_short_url(self):
        from django.conf import settings
        domain = getattr(settings, 'URLSHORTENER_DOMAIN', None)
        if domain:
            if not domain.startswith(('http://', 'https://')):
                domain = f'https://{domain}'
            return f'{domain.rstrip("/")}/{self.short_code}'
        return self.get_short_url()

    def record_access(self):
        self.access_count = F('access_count') + 1
        self.last_access_time = timezone.now()
        self.save(update_fields=['access_count', 'last_access_time'])
