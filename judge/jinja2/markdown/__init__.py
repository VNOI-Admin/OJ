import logging
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

import markdown2
from bleach.sanitizer import Cleaner
from django.conf import settings
from jinja2 import Markup
from lxml import html
from lxml.etree import ParserError, XMLSyntaxError

from judge.highlight_code import highlight_code
from judge.jinja2.markdown.lazy_load import lazy_load as lazy_load_processor
from judge.utils.camo import client as camo_client
from judge.utils.texoid import TEXOID_ENABLED, TexoidRenderer
from .bleach_whitelist import all_styles, mathml_attrs, mathml_tags
from .math import extractLatexeq, recontructString
from .. import registry

logger = logging.getLogger('judge.html')

NOFOLLOW_WHITELIST = settings.NOFOLLOW_EXCLUDED


cleaner_cache = {}


def get_cleaner(name, params):
    if name in cleaner_cache:
        return cleaner_cache[name]

    if params.get('styles') is True:
        params['styles'] = all_styles

    if params.pop('mathml', False):
        params['tags'] = params.get('tags', []) + mathml_tags
        params['attributes'] = params.get('attributes', {}).copy()
        params['attributes'].update(mathml_attrs)

    cleaner = cleaner_cache[name] = Cleaner(**params)
    return cleaner


def fragments_to_tree(fragment):
    tree = html.Element('div')
    try:
        parsed = html.fragments_fromstring(fragment, parser=html.HTMLParser(recover=True))
    except (XMLSyntaxError, ParserError) as e:
        if fragment and (not isinstance(e, ParserError) or e.args[0] != 'Document is empty'):
            logger.exception('Failed to parse HTML string')
        return tree

    if parsed and isinstance(parsed[0], str):
        tree.text = parsed[0]
        parsed = parsed[1:]
    tree.extend(parsed)
    return tree


def fragment_tree_to_str(tree):
    return html.tostring(tree, encoding='unicode')[len('<div>'):-len('</div>')]


def inc_header(text, level):
    s = '#' * level
    pattern = re.compile(
        r'^\#{1,10}',
        re.X | re.M,
    )

    return re.sub(pattern, lambda x: x.group() + s, text)


def add_table_class(text):
    return re.sub(r'<table>', r'<table class="table"', text)


@registry.filter
def markdown(text, style, math_engine=None, lazy_load=False):
    styles = settings.MARKDOWN_STYLES.get(style, settings.MARKDOWN_DEFAULT_STYLE)
    bleach_params = styles.get('bleach', {})

    post_processors = []
    if styles.get('use_camo', False) and camo_client is not None:
        post_processors.append(camo_client.update_tree)
    if lazy_load:
        post_processors.append(lazy_load_processor)

    value = inc_header(text, 2)
    string, latexeqs = extractLatexeq(value)
    string = markdown2.markdown(string, extras=['spoiler', 'fenced-code-blocks', 'cuddled-lists', 'tables'])
    result = recontructString(string, latexeqs)
    result = add_table_class(result)

    if post_processors:
        tree = fragments_to_tree(result)
        for processor in post_processors:
            processor(tree)
        result = fragment_tree_to_str(tree)
    if bleach_params:
        result = get_cleaner(style, bleach_params).clean(result)
    return Markup(result)
