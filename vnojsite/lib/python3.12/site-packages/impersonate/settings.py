# -*- coding: utf-8 -*-
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model

User = get_user_model()
username_field = getattr(User, 'USERNAME_FIELD', 'username')

_settings = {
    'MAX_FILTER_SIZE': 100,
    'REDIRECT_FIELD_NAME': None,
    'PAGINATE_COUNT': 20,
    'REQUIRE_SUPERUSER': False,
    'CUSTOM_USER_QUERYSET': None,
    'ALLOW_SUPERUSER': False,
    'CUSTOM_ALLOW': None,
    'URI_EXCLUSIONS': (r'^admin/',),
    'DISABLE_LOGGING': False,
    'USE_HTTP_REFERER': False,
    'LOOKUP_TYPE': 'icontains',
    'SEARCH_FIELDS': [username_field, 'first_name', 'last_name', 'email'],
    'REDIRECT_URL': getattr(django_settings, 'LOGIN_REDIRECT_URL', u'/'),
    'READ_ONLY': False,
    'CUSTOM_READ_ONLY': None,
    'ADMIN_DELETE_PERMISSION': False,
    'ADMIN_ADD_PERMISSION': False,
    'ADMIN_READ_ONLY': True,
    'MAX_DURATION': None,
}


class Settings(object):
    def __getattribute__(self, name):
        sdict = getattr(django_settings, 'IMPERSONATE', {})
        return sdict.get(name, _settings.get(name))


settings = Settings()
