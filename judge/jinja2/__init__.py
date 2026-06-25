import itertools
import json
from urllib.parse import quote

from django.template.defaultfilters import filesizeformat
from django.templatetags.static import static as django_static
from jinja2 import pass_context
from jinja2.ext import Extension
from markupsafe import Markup
from mptt.utils import get_cached_trees
from statici18n.templatetags.statici18n import inlinei18n

from judge.highlight_code import highlight_code
from judge.user_translations import gettext
from . import (camo, datetime, filesize, format, gravatar, language, markdown, rating, reference, render, social,
               spaceless, submission, timedelta)
from . import registry

registry.function('str', str)
registry.filter('str', str)
registry.filter('json', json.dumps)
registry.filter('highlight', highlight_code)
registry.filter('urlquote', quote)
registry.filter('roundfloat', round)
registry.function('ordinal', lambda n: '%d%s' % (n, 'tsnrhtdd'[(n // 10 % 10 != 1) * (n % 10 < 4) * n % 10::4]))
registry.function('inlinei18n', inlinei18n)
registry.function('mptt_tree', get_cached_trees)
registry.function('user_trans', gettext)


@registry.function
def counter(start=1):
    return itertools.count(start).__next__


@registry.function
@pass_context
def select_css_theme(context, light, dark):
    theme = context.get('SITE_THEME_NAME', 'auto')
    if theme == 'dark':
        return Markup(f'<link rel="stylesheet" href="{django_static(dark)}">')
    elif theme == 'light':
        return Markup(f'<link rel="stylesheet" href="{django_static(light)}">')
    else:  # 'auto'
        return Markup(
            f'<link rel="stylesheet" href="{django_static(light)}">'
            f'<link rel="stylesheet" href="{django_static(dark)}" media="(prefers-color-scheme: dark)">',
        )


class DMOJExtension(Extension):
    def __init__(self, env):
        super(DMOJExtension, self).__init__(env)
        env.globals.update(registry.globals)
        env.filters.update(registry.filters)
        env.tests.update(registry.tests)

        env.filters['filesizeformat'] = filesizeformat
