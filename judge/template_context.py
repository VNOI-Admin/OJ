import re
from functools import partial

from django.conf import settings
from django.contrib.auth.context_processors import PermWrapper
from django.contrib.sites.shortcuts import get_current_site
from django.core.cache import cache
from django.utils.functional import SimpleLazyObject, new_method_proxy

from judge import event_poster as event
from judge.utils.caniuse import CanIUse, SUPPORT
from .models import NavigationBar, Profile


class FixedSimpleLazyObject(SimpleLazyObject):
    if not hasattr(SimpleLazyObject, '__iter__'):
        __iter__ = new_method_proxy(iter)


def get_resource(request):
    use_https = settings.DMOJ_SSL
    if use_https == 1:
        scheme = 'https' if request.is_secure() else 'http'
    elif use_https > 1:
        scheme = 'https'
    else:
        scheme = 'http'
    return {
        'INLINE_JQUERY': settings.INLINE_JQUERY,
        'INLINE_FONTAWESOME': settings.INLINE_FONTAWESOME,
        'JQUERY_JS': settings.JQUERY_JS,
        'FONTAWESOME_CSS': settings.FONTAWESOME_CSS,
        'DMOJ_SCHEME': scheme,
        'DMOJ_CANONICAL': settings.DMOJ_CANONICAL,
        'DMOJ_SELECT2_THEME': settings.DMOJ_SELECT2_THEME,
    }


def get_profile(request):
    if request.user.is_authenticated:
        return Profile.objects.get_or_create(user=request.user)[0]
    return None


def comet_location(request):
    if request.is_secure():
        websocket = getattr(settings, 'EVENT_DAEMON_GET_SSL', settings.EVENT_DAEMON_GET)
        poll = getattr(settings, 'EVENT_DAEMON_POLL_SSL', settings.EVENT_DAEMON_POLL)
    else:
        websocket = settings.EVENT_DAEMON_GET
        poll = settings.EVENT_DAEMON_POLL
    return {'EVENT_DAEMON_LOCATION': websocket,
            'EVENT_DAEMON_POLL_LOCATION': poll,
            'EVENT_LAST_MSG': event.last()}


NAVIGATION_BAR_CACHE_KEY = 'navigation_bar'


def nav_bar_items():
    items = cache.get(NAVIGATION_BAR_CACHE_KEY)
    if items is None:
        items = list(NavigationBar.objects.all())
        cache.set(NAVIGATION_BAR_CACHE_KEY, items, 86400)
    return items


def nav_tab_keys(path, items):
    by_id = {item.id: item for item in items}
    node = next((item for item in items if re.search(item.regex, path)), None)
    keys = []
    while node is not None:
        keys.append(node.key)
        node = by_id.get(node.parent_id)
    return keys[::-1]


def __nav_tab(path):
    return nav_tab_keys(path, nav_bar_items())


def general_info(request):
    path = request.get_full_path()
    info = {
        'nav_tab': FixedSimpleLazyObject(partial(__nav_tab, request.path)),
        'nav_bar': nav_bar_items(),
        'LOGIN_RETURN_PATH': '' if path.startswith('/accounts/') else path,
        'REGISTRATION_OPEN': settings.REGISTRATION_OPEN,
        'perms': PermWrapper(request.user),
        'HAS_WEBAUTHN': bool(settings.WEBAUTHN_RP_ID),
    }
    if hasattr(request.user, 'profile'):
        info['NOTIFICATION_SECRET'] = request.profile.notification_secret
        info['UNREAD_NOTIFICATION_COUNT'] = request.profile.unread_notification_count
    return info


def site(request):
    return {'site': get_current_site(request)}


def misc_config(request):
    return {'misc_config': request.misc_config}


def site_name(request):
    return {'SITE_NAME': settings.SITE_NAME,
            'SITE_LONG_NAME': settings.SITE_LONG_NAME,
            'SITE_ADMIN_EMAIL': settings.SITE_ADMIN_EMAIL}


def site_theme(request):
    # Middleware populating `profile` may not have loaded at this point if we're called from an error context.
    if hasattr(request.user, 'profile'):
        site_theme = request.profile.site_theme
    else:
        site_theme = request.COOKIES.get(settings.SITE_THEME_COOKIE_NAME, 'auto')
        if site_theme not in settings.DMOJ_THEME_CSS and site_theme != 'auto':
            site_theme = 'auto'
    preferred_css = settings.DMOJ_THEME_CSS.get(site_theme)
    return {
        'DARK_STYLE_CSS': settings.DMOJ_THEME_CSS['dark'],
        'LIGHT_STYLE_CSS': settings.DMOJ_THEME_CSS['light'],
        'PREFERRED_STYLE_CSS': preferred_css,
        'SITE_THEME_NAME': site_theme,
    }


def math_setting(request):
    caniuse = CanIUse(request.headers.get('user-agent', ''))

    # Middleware populating `profile` may not have loaded at this point if we're called from an error context.
    if hasattr(request.user, 'profile'):
        engine = request.profile.math_engine
    else:
        engine = settings.MATHOID_DEFAULT_TYPE
    if engine == 'auto':
        engine = 'mml' if bool(settings.MATHOID_URL) and caniuse.mathml == SUPPORT else 'jax'
    return {'MATH_ENGINE': engine, 'REQUIRE_JAX': engine == 'jax', 'caniuse': caniuse}
