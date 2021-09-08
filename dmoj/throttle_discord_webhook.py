import logging
import traceback
from copy import copy

from discord_webhook import DiscordWebhook
from django.conf import settings
from django.core.cache import cache
from django.views.debug import ExceptionReporter


def new_webhook():
    cache.add('error_discord_webhook_throttle', 0, settings.VNOJ_DISCORD_WEBHOOK_THROTTLING[1])
    return cache.incr('error_discord_webhook_throttle')


class ThrottledDiscordWebhookHandler(logging.Handler):
    """An exception log handler that send log entries to discord webhook.

    If the request is passed as the first argument to the log record,
    request data will be provided in the message report.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Send at most (VNOJ_DISCORD_WEBHOOK_THROTTLING[0]) message in
        # (VNOJ_DISCORD_WEBHOOK_THROTTLING[1]) seconds
        self.throttle = settings.VNOJ_DISCORD_WEBHOOK_THROTTLING[0]

    def emit(self, record):
        # Adapt from `dmoj.throttle_mail.ThrottledEmailHandler`
        try:
            count = new_webhook()
        except Exception:
            traceback.print_exc()
        else:
            if count >= self.throttle:
                return

        # Adapt from `django.utils.log.AdminEmailHandler`
        try:
            request = record.request
            subject = '%s (%s IP): %s' % (
                record.levelname,
                ('internal' if request.META.get('REMOTE_ADDR') in settings.INTERNAL_IPS
                 else 'EXTERNAL'),
                record.getMessage(),
            )
        except Exception:
            subject = '%s: %s' % (
                record.levelname,
                record.getMessage(),
            )
            request = None

        # Since we add a nicely formatted traceback on our own, create a copy
        # of the log record without the exception data.
        no_exc_record = copy(record)
        no_exc_record.exc_info = None
        no_exc_record.exc_text = None

        if record.exc_info:
            exc_info = record.exc_info
        else:
            exc_info = (None, record.getMessage(), None)

        reporter = ExceptionReporter(request, is_email=True, *exc_info)
        message = '%s\n\n%s' % (self.format(no_exc_record), reporter.get_traceback_text())
        self.send_webhook(subject, message)

    def send_webhook(self, subject, message):
        webhook = settings.DISCORD_WEBHOOK.get('on_error', None)
        if webhook is None:
            return
        webhook = DiscordWebhook(url=webhook, content=subject)
        # Discord has a limit 8 MB file size for normal server (without boost)
        # Use 7MB just for safe.
        webhook.add_file(file=message[:7 * 1024 * 1024], filename='log.txt')
        webhook.execute()
