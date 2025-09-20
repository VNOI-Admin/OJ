# -*- coding: utf-8 -*-
import re
from importlib import import_module

from django.core.paginator import EmptyPage, Paginator
from django.utils.html import format_html

from .settings import User, settings


def get_redir_path(request=None):
    nextval = None
    redirect_field_name = settings.REDIRECT_FIELD_NAME
    if request and redirect_field_name:
        nextval = request.GET.get(redirect_field_name, None)
    return nextval or settings.REDIRECT_URL


def get_redir_arg(request):
    redirect_field_name = settings.REDIRECT_FIELD_NAME
    if redirect_field_name:
        nextval = request.GET.get(redirect_field_name, None)
        if nextval:
            return u'?{0}={1}'.format(redirect_field_name, nextval)
    return u''


def get_redir_field(request):
    redirect_field_name = settings.REDIRECT_FIELD_NAME
    if redirect_field_name:
        nextval = request.GET.get(redirect_field_name, None)
        if nextval:
            return format_html(
                u'<input type="hidden" name="{0}" value="{1}"/>',
                redirect_field_name,
                nextval,
            )
    return u''


def get_paginator(request, qs):
    try:
        page_number = int(request.GET.get('page', 1))
    except ValueError:
        page_number = 1

    paginator = Paginator(qs, int(settings.PAGINATE_COUNT),)
    try:
        page = paginator.page(page_number)
    except EmptyPage:
        page = None

    return (paginator, page, page_number)


def check_allow_staff():
    return not settings.REQUIRE_SUPERUSER


def users_impersonable(request):
    ''' Returns a QuerySet of users that this user can impersonate.
        Uses the CUSTOM_USER_QUERYSET if set, else, it
        returns all users
    '''
    if settings.CUSTOM_USER_QUERYSET is not None:
        custom_queryset_func = import_func_from_string(
            settings.CUSTOM_USER_QUERYSET
        )
        return custom_queryset_func(request)
    else:
        qs = User.objects.all()
        if not qs.query.order_by:
            qs = qs.order_by('pk')
        return qs


def check_allow_for_user(request, end_user):
    ''' Return True if some request can impersonate end_user
    '''
    if check_allow_impersonate(request):
        # start user can impersonate
        # Can impersonate superusers if ALLOW_SUPERUSER is True
        # Can impersonate anyone who is in your queryset of 'who i can impersonate'.
        allow_superusers = settings.ALLOW_SUPERUSER
        upk = end_user.pk
        return (
            (request.user.is_superuser and allow_superusers)
            or not end_user.is_superuser
        ) and users_impersonable(request).filter(pk=upk).exists()

    # start user not allowed impersonate at all
    return False


def import_func_from_string(string_name):
    ''' Given a string like 'mod.mod2.funcname' which refers to a function,
        return that function so it can be called
    '''
    mod_name, func_name = string_name.rsplit('.', 1)
    mod = import_module(mod_name)
    return getattr(mod, func_name)


def check_allow_impersonate(request):
    ''' Returns True if this request is allowed to do any impersonation.
        Uses the CUSTOM_ALLOW function if required, else
        looks at superuser/staff status and REQUIRE_SUPERUSER
    '''
    if settings.CUSTOM_ALLOW is not None:
        custom_allow_func = import_func_from_string(settings.CUSTOM_ALLOW)
        return custom_allow_func(request)
    else:
        # default allow checking:
        if not request.user.is_superuser:
            if not request.user.is_staff or not check_allow_staff():
                return False
    return True


def check_allow_for_uri(uri):
    uri = uri.lstrip('/')

    exclusions = settings.URI_EXCLUSIONS
    if not isinstance(exclusions, (list, tuple)):
        exclusions = (exclusions,)

    for exclusion in exclusions:
        if re.search(exclusion, uri):
            return False
    return True


def check_read_only(request):
    ''' Returns True if can only do read only requests.
        Uses the CUSTOM_READ_ONLY function if required, else
        looks at the READ_ONLY setting.
    '''
    if settings.CUSTOM_READ_ONLY is not None:
        custom_read_only_func = import_func_from_string(settings.CUSTOM_READ_ONLY)
        return custom_read_only_func(request)
    return settings.READ_ONLY
