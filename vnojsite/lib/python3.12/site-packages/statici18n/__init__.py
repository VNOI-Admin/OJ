# following PEP 386
__version__ = "2.6.0"

import django

if django.VERSION < (3, 2):
    default_app_config = "statici18n.apps.StaticI18NConfig"
