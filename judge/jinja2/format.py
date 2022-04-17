from django.utils.html import format_html
from django.utils.safestring import mark_safe

from . import registry


@registry.function
def bold(text):
    return format_html('<b>{0}</b>', text)


@registry.function
def safe(text):
    return mark_safe(text)
