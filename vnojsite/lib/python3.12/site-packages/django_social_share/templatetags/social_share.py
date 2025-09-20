# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import re

from django import template

from django.db.models import Model
from django.template.defaultfilters import urlencode
from django.utils.safestring import mark_safe

try:
    from django_bitly.templatetags.bitly import bitlify
    DJANGO_BITLY = True
except ImportError:
    DJANGO_BITLY = False


register = template.Library()


TWITTER_ENDPOINT = 'https://twitter.com/intent/tweet?text=%s'
FACEBOOK_ENDPOINT = 'https://www.facebook.com/sharer/sharer.php?u=%s'
GPLUS_ENDPOINT = 'https://plus.google.com/share?url=%s'
MAIL_ENDPOINT = 'mailto:?subject=%s&body=%s'
LINKEDIN_ENDPOINT = 'https://www.linkedin.com/shareArticle?mini=true&title=%s&url=%s'
REDDIT_ENDPOINT = 'https://www.reddit.com/submit?title=%s&url=%s'
TELEGRAM_ENDPOINT = 'https://t.me/share/url?text=%s&url=%s'
WHATSAPP_ENDPOINT = 'https://api.whatsapp.com/send?text=%s'
PINTEREST_ENDPOINT = 'https://www.pinterest.com/pin/create/button/?url=%s'


BITLY_REGEX = re.compile(r'^https?://bit\.ly/')


def compile_text(context, text):
    ctx = template.context.Context(context)
    return template.Template(text).render(ctx)


def _build_url(request, obj_or_url):
    if obj_or_url is not None:
        if isinstance(obj_or_url, Model):
            if DJANGO_BITLY:
                url = bitlify(obj_or_url)  # type: str
                if not BITLY_REGEX.match(url):
                    return request.build_absolute_uri(
                        obj_or_url.get_absolute_url()
                    )
                else:
                    return url
            else:
                return request.build_absolute_uri(obj_or_url.get_absolute_url())
        else:
            return request.build_absolute_uri(obj_or_url)
    return ''


def _compose_tweet(text, url=None):
    TWITTER_MAX_NUMBER_OF_CHARACTERS = 140
    TWITTER_LINK_LENGTH = 23  # "A URL of any length will be altered to 23 characters, even if the link itself is less than 23 characters long.

    # Compute length of the tweet
    url_length = len(' ') + TWITTER_LINK_LENGTH if url else 0
    total_length = len(text) + url_length

    # Check that the text respects the max number of characters for a tweet
    if total_length > TWITTER_MAX_NUMBER_OF_CHARACTERS:
        text = text[:(TWITTER_MAX_NUMBER_OF_CHARACTERS - url_length - 1)] + "…"  # len("…") == 1

    return "%s %s" % (text, url) if url else text


@register.simple_tag(takes_context=True)
def post_to_twitter_url(context, text, obj_or_url=None):
    text = compile_text(context, text)
    request = context['request']

    url = _build_url(request, obj_or_url)

    tweet = _compose_tweet(text, url)
    context['tweet_url'] = TWITTER_ENDPOINT % urlencode(tweet)
    return context


@register.inclusion_tag('django_social_share/templatetags/post_to_twitter.html', takes_context=True)
def post_to_twitter(context, text, obj_or_url=None, link_text='',link_class=""):
    context = post_to_twitter_url(context, text, obj_or_url)

    request = context['request']
    url = _build_url(request, obj_or_url)
    tweet = _compose_tweet(text, url)

    context['link_class'] = link_class 
    context['link_text'] = link_text or 'Post to Twitter'
    context['full_text'] = tweet
    return context


@register.simple_tag(takes_context=True)
def post_to_facebook_url(context, obj_or_url=None):
    request = context['request']
    url = _build_url(request, obj_or_url)
    context['facebook_url'] = FACEBOOK_ENDPOINT % urlencode(url)
    return context


@register.inclusion_tag('django_social_share/templatetags/post_to_facebook.html', takes_context=True)
def post_to_facebook(context, obj_or_url=None, link_text='',link_class=''):
    context = post_to_facebook_url(context, obj_or_url)
    context['link_class'] = link_class  or ''
    context['link_text'] = link_text or 'Post to Facebook'
    return context


@register.simple_tag(takes_context=True)
def post_to_gplus_url(context, obj_or_url=None):
    request = context['request']
    url = _build_url(request, obj_or_url)
    context['gplus_url'] = GPLUS_ENDPOINT % urlencode(url)
    return context


@register.inclusion_tag('django_social_share/templatetags/post_to_gplus.html', takes_context=True)
def post_to_gplus(context, obj_or_url=None, link_text='',link_class=''):
    context = post_to_gplus_url(context, obj_or_url)
    context['link_class'] = link_class 
    context['link_text'] = link_text or 'Post to Google+'
    return context


@register.simple_tag(takes_context=True)
def send_email_url(context, subject, text, obj_or_url=None):
    text = compile_text(context, text)
    subject = compile_text(context, subject)
    request = context['request']
    url = _build_url(request, obj_or_url)
    full_text = "%s %s" % (text, url)
    context['mailto_url'] = MAIL_ENDPOINT % (urlencode(subject), urlencode(full_text))
    return context


@register.inclusion_tag('django_social_share/templatetags/send_email.html', takes_context=True)
def send_email(context, subject, text, obj_or_url=None, link_text='',link_class=''):
    context = send_email_url(context, subject, text, obj_or_url)
    context['link_class'] = link_class 
    context['link_text'] = link_text or 'Share via email'
    return context


@register.filter(name='linkedin_locale')
def linkedin_locale(value):
    if "-" not in value:
        return value

    lang, country = value.split('-')
    return '_'.join([lang, country.upper()])


@register.simple_tag(takes_context=True)
def post_to_linkedin_url(context, obj_or_url=None):
    request = context['request']
    url = _build_url(request, obj_or_url)
    context['linkedin_url'] = url
    return context


@register.inclusion_tag('django_social_share/templatetags/post_to_linkedin.html', takes_context=True)
def post_to_linkedin(context, obj_or_url=None,link_class=''):
    context = post_to_linkedin_url(context, obj_or_url)
    context['link_class'] = link_class 
    return context


@register.simple_tag(takes_context=True)
def post_to_reddit_url(context, title, obj_or_url=None):
    request = context['request']
    title = compile_text(context, title)
    url = _build_url(request, obj_or_url)
    context['reddit_url'] = mark_safe(REDDIT_ENDPOINT % (urlencode(title), urlencode(url)))
    return context


@register.inclusion_tag('django_social_share/templatetags/post_to_reddit.html', takes_context=True)
def post_to_reddit(context, title, obj_or_url=None, link_text='',link_class=''):
    context = post_to_reddit_url(context, title, obj_or_url)
    context['link_class'] = link_class 
    context['link_text'] = link_text or 'Post to Reddit' 
    return context


@register.simple_tag(takes_context=True)
def post_to_telegram_url(context, title, obj_or_url):
    request = context['request']
    title = compile_text(context, title)
    url = _build_url(request, obj_or_url)
    context['telegram_url'] = mark_safe(TELEGRAM_ENDPOINT % (urlencode(title), urlencode(url)))
    return context


@register.inclusion_tag('django_social_share/templatetags/post_to_telegram.html', takes_context=True)
def post_to_telegram(context, title, obj_or_url=None, link_text='',link_class=''):
    context = post_to_telegram_url(context, title, obj_or_url)
    context['link_class'] = link_class 
    context['link_text'] = link_text or 'Post to Telegram'
    return context


@register.simple_tag(takes_context=True)
def post_to_whatsapp_url(context, obj_or_url=None):
    request = context['request']
    url = _build_url(request, obj_or_url)
    context['whatsapp_url'] = WHATSAPP_ENDPOINT % urlencode(url)
    return context


@register.inclusion_tag('django_social_share/templatetags/post_to_whatsapp.html', takes_context=True)
def post_to_whatsapp(context, obj_or_url=None, link_text='',link_class=''):
    context = post_to_whatsapp_url(context, obj_or_url)
    context['link_class'] = link_class 
    context['link_text'] = link_text or 'Post to WhatsApp'
    return context


@register.simple_tag(takes_context=True)
def save_to_pinterest_url(context, obj_or_url=None):
    request = context['request']
    url = _build_url(request, obj_or_url)
    context['pinterest_url'] = PINTEREST_ENDPOINT % urlencode(url)
    return context


@register.inclusion_tag('django_social_share/templatetags/save_to_pinterest.html', takes_context=True)
def save_to_pinterest(context, obj_or_url=None, pin_count=False, link_class=''):
    context = save_to_pinterest_url(context, obj_or_url)
    context['link_class'] = link_class 
    context['pin_count'] = pin_count
    return context


@register.inclusion_tag('django_social_share/templatetags/pinterest_script.html', takes_context=False)
def add_pinterest_script():
    pass

@register.simple_tag(takes_context=True)
def copy_to_clipboard_url(context, obj_or_url=None):
    request = context['request']
    url = _build_url(request, obj_or_url)
    context['copy_url'] = url
    return context

@register.inclusion_tag('django_social_share/templatetags/copy_to_clipboard.html', takes_context=True)
def copy_to_clipboard(context, obj_or_url, link_text='', link_class=''):
    context = copy_to_clipboard_url(context, obj_or_url)
    
    context['link_class'] = link_class
    context['link_text'] = link_text or 'Copy to clipboard'
    return context

@register.inclusion_tag('django_social_share/templatetags/copy_script.html', takes_context=False)
def add_copy_script():
    pass