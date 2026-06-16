from django.core.cache import cache
from django.db import models
from django.utils.translation import gettext_lazy as _

from judge import event_poster as event
from judge.models.profile import Profile

__all__ = ['Notification', 'make_notification']


class Notification(models.Model):
    TICKET = 'ticket'
    CONTEST = 'contest'
    STORAGE = 'storage'
    CATEGORY_CHOICES = [
        (TICKET, _('Ticket')),
        (CONTEST, _('Contest')),
        (STORAGE, _('Storage')),
    ]

    owner = models.ForeignKey(Profile, verbose_name=_('owner'), related_name='notifications',
                              on_delete=models.CASCADE)
    category = models.CharField(verbose_name=_('category'), max_length=50, choices=CATEGORY_CHOICES)
    title = models.CharField(verbose_name=_('title'), max_length=255)
    html = models.TextField(verbose_name=_('body'), blank=True)
    url = models.CharField(verbose_name=_('target link'), max_length=255, blank=True)
    time = models.DateTimeField(verbose_name=_('creation time'), auto_now_add=True)
    read = models.BooleanField(verbose_name=_('is read?'), default=False)
    popup = models.BooleanField(verbose_name=_('pop up on arrival?'), default=False)

    class Meta:
        ordering = ['-time']
        indexes = [
            models.Index(fields=['owner', 'read', '-time']),
        ]
        verbose_name = _('notification')
        verbose_name_plural = _('notifications')

    def __str__(self):
        return f'{self.owner}: {self.title}'


def make_notification(recipients, *, category, title, html='', url='', popup=False):
    """Persist a notification for each recipient and push it over the event daemon.

    ``recipients`` may be a queryset or iterable of ``Profile`` (or profile ids).
    """
    profiles = []
    for recipient in recipients:
        if isinstance(recipient, Profile):
            profiles.append(recipient)
        else:
            profiles.append(Profile(id=recipient))

    notifications = [
        Notification(owner=profile, category=category, title=title, html=html, url=url, popup=popup)
        for profile in profiles
    ]
    Notification.objects.bulk_create(notifications)

    for profile in profiles:
        cache.delete(Profile.unread_notification_count_cache_key(profile.id))

    if event.real:
        for profile in profiles:
            event.post(f'notification_{Profile.get_notification_secret(profile.id)}', {
                'type': 'notification',
                'category': category,
                'title': title,
                'body': html,
                'url': url,
                'popup': popup,
            })
