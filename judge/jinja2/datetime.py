import functools
from datetime import timezone

from django.template.defaultfilters import date, time
from django.templatetags.tz import localtime
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django.utils.translation import ngettext_lazy

from . import registry


def localtime_wrapper(func):
    @functools.wraps(func)
    def wrapper(datetime, *args, **kwargs):
        if getattr(datetime, 'convert_to_local_time', True):
            datetime = localtime(datetime)
        return func(datetime, *args, **kwargs)

    return wrapper


registry.filter(localtime_wrapper(date))
registry.filter(localtime_wrapper(time))


@registry.function
def relative_time(time, **kwargs):
    abs_time = date(time, kwargs.get('format', _('N j, Y, g:i a')))
    return mark_safe(f'<span data-iso="{time.astimezone(timezone.utc).isoformat()}" class="time-with-rel"'
                     f' title="{escape(abs_time)}" data-format="{escape(kwargs.get("rel", _("{time}")))}">'
                     f'{escape(kwargs.get("abs", _("on {time}")).replace("{time}", abs_time))}</span>')


# Coarsest-first, so `time_ago` reports a single unit: "3 months ago", never "3 months, 1 week ago".
TIME_AGO_UNITS = (
    (365 * 24 * 60 * 60, ngettext_lazy('%(count)d year ago', '%(count)d years ago', 'count')),
    (30 * 24 * 60 * 60, ngettext_lazy('%(count)d month ago', '%(count)d months ago', 'count')),
    (24 * 60 * 60, ngettext_lazy('%(count)d day ago', '%(count)d days ago', 'count')),
    (60 * 60, ngettext_lazy('%(count)d hour ago', '%(count)d hours ago', 'count')),
    (60, ngettext_lazy('%(count)d minute ago', '%(count)d minutes ago', 'count')),
)


@registry.filter
def time_ago(value):
    """How long ago `value` was, rounded down to one unit: "5 hours ago", "2 months ago"."""
    if value is None:
        return ''

    seconds = (now() - value).total_seconds()
    for unit_seconds, message in TIME_AGO_UNITS:
        count = int(seconds // unit_seconds)
        if count > 0:
            return message % {'count': count}
    # Anything under a minute, and anything in the future (clock skew), reads as just now.
    return _('just now')
