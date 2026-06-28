from enum import IntEnum

from django.db import models
from django.utils.translation import gettext_lazy as _

from judge import event_poster as event
from judge.models.profile import Profile
from judge.utils.cache_helper import bulk_invalidate_notification_caches

__all__ = ['Notification', 'make_notification']


class Notification(models.Model):
    class Priority(IntEnum):
        DEFAULT = 0
        TICKET = 10
        CONTEST_ANNOUNCEMENT = 30

    recipient = models.ForeignKey(Profile, verbose_name=_('recipient'), related_name='notifications',
                                  on_delete=models.CASCADE)
    title = models.CharField(verbose_name=_('title'), max_length=255)
    body = models.TextField(verbose_name=_('body'), blank=True)
    url = models.CharField(verbose_name=_('target link'), max_length=255, blank=True)
    time = models.DateTimeField(verbose_name=_('creation time'), auto_now_add=True)
    read = models.BooleanField(verbose_name=_('is read?'), default=False)
    priority = models.IntegerField(verbose_name=_('priority'), default=Priority.DEFAULT)

    class Meta:
        ordering = ['-time']
        indexes = [
            models.Index(fields=['recipient', 'read', '-priority', '-time']),
        ]
        verbose_name = _('notification')
        verbose_name_plural = _('notifications')

    def __str__(self):
        return f'{self.recipient}: {self.title}'


def make_notification(recipients, title, body='', url='', popup=False,
                      broadcast_channel=None, priority=Notification.Priority.DEFAULT):
    """Persist a notification for each recipient and push it over the event daemon.

    ``recipients`` may be a queryset or iterable of ``Profile`` (or profile ids).
    Pass ``broadcast_channel`` to post a single event to that channel instead of
    sending one event per recipient (use for large fanouts like contest announcements).
    """
    profiles = []
    for recipient in recipients:
        if isinstance(recipient, Profile):
            profiles.append(recipient)
        else:
            profiles.append(Profile(id=recipient))

    notifications = [
        Notification(recipient=profile, title=title, body=body, url=url, priority=int(priority))
        for profile in profiles
    ]
    Notification.objects.bulk_create(notifications)

    bulk_invalidate_notification_caches(p.id for p in profiles)

    if event.real:
        payload = {'type': 'notification', 'title': title, 'body': body, 'url': url, 'popup': popup}
        if broadcast_channel:
            event.post(broadcast_channel, payload)
        else:
            for profile in profiles:
                event.post(f'notification_{Profile.get_notification_secret(profile.id)}', payload)
