import logging
import re

import markdown2
import nh3
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from lxml import html
from lxml.etree import ParserError, XMLSyntaxError
from markupsafe import Markup

from judge.jinja2.markdown.lazy_load import lazy_load as lazy_load_processor
from judge.utils.camo import client as camo_client
from .sanitizer_whitelist import all_styles, mathml_attrs, mathml_tags
from .. import registry

logger = logging.getLogger('judge.html')

NOFOLLOW_WHITELIST = settings.NOFOLLOW_EXCLUDED


class Sanitizer:
    """Allowlist HTML sanitizer. Tags outside the allowlist are escaped by markdown2's `html-allowlist` extra,
    this cleans attributes and URLs of the rest."""

    def __init__(self, tags=(), attributes=None, styles=None, mathml=False):
        self.tags = set(tags)
        # for markdown2's `html-allowlist`: MathML names like `int` and `vector` are C++ too, so only `math` is
        # listed and markdown2 leaves what is inside it to nh3
        self.markdown_tags = set(tags)
        attributes = {tag: set(attrs) for tag, attrs in (attributes or {}).items()}
        if mathml:
            self.markdown_tags.add('math')
            self.tags.update(mathml_tags)
            attributes.update({tag: set(attrs) for tag, attrs in mathml_attrs.items()})
        self.cleaner = nh3.Cleaner(
            tags=self.tags,
            attributes=attributes,
            url_schemes={'http', 'https', 'mailto'},
            link_rel=None,
            filter_style_properties=set(all_styles if styles is True else styles) if styles else None,
        )

    def clean(self, text):
        return self.cleaner.clean(text)


cleaner_cache = {}


def get_cleaner(name, params):
    if name not in cleaner_cache:
        cleaner_cache[name] = Sanitizer(**params)
    return cleaner_cache[name]


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


def strip_paragraphs_tags(tree):
    for p in tree.xpath('.//p'):
        for child in p.iterchildren(reversed=True):
            p.addnext(child)
        parent = p.getparent()
        prev = p.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or '') + p.text
        else:
            parent.text = (parent.text or '') + p.text
        parent.remove(p)


def fragment_tree_to_str(tree):
    return html.tostring(tree, encoding='unicode')[len('<div>'):-len('</div>')]


def inc_header(text, level):
    pattern = re.compile(
        r'<(\/?)h([1-9][0-9]*)>',
        re.X | re.M,
    )
    return re.sub(pattern, lambda x: '<' + x.group(1) + 'h' + str(int(x.group(2)) + level) + '>', text)


def add_table_class(text):
    return text.replace(r'<table>', r'<table class="table">')


@registry.filter
def markdown(text, style, math_engine=None, lazy_load=False, strip_paragraphs=False):
    styles = settings.MARKDOWN_STYLES.get(style, settings.MARKDOWN_DEFAULT_STYLE)
    if styles.get('safe_mode', True):
        safe_mode = 'escape'
    else:
        safe_mode = None

    extras = ['vnoj-latex', 'spoiler', 'fenced-code-blocks', 'cuddled-lists', 'tables', 'strike']
    if styles.get('nofollow', True):
        extras.append('nofollow')

    if 'bleach' in styles:
        # renamed from 'bleach', fail loudly instead of rendering unsanitized HTML
        raise ImproperlyConfigured("MARKDOWN_STYLES: rename the 'bleach' key to 'sanitizer'")
    sanitizer_params = styles.get('sanitizer', {})
    cleaner = get_cleaner(style, sanitizer_params) if sanitizer_params else None
    if cleaner:
        extras = dict.fromkeys(extras)
        extras['html-allowlist'] = cleaner.markdown_tags

    post_processors = []
    if styles.get('use_camo', False) and camo_client is not None:
        post_processors.append(camo_client.update_tree)
    if lazy_load:
        post_processors.append(lazy_load_processor)

    result = markdown2.markdown(text, safe_mode=safe_mode, extras=extras)

    result = add_table_class(result)
    result = inc_header(result, 2)

    if post_processors or strip_paragraphs:
        tree = fragments_to_tree(result)
        for processor in post_processors:
            processor(tree)
        if strip_paragraphs:
            strip_paragraphs_tags(tree)
        result = fragment_tree_to_str(tree)
    if cleaner:
        result = cleaner.clean(result)
    return Markup(result)
