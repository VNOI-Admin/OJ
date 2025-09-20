#!/usr/bin/env python
import sys
import os

from django.conf import settings

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

settings.configure(
    SITE_ID=1,
    DATABASES={
        'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory;'}
    },
    INSTALLED_APPS=[
        'django.contrib.auth',
        'django.contrib.sessions',
        'django.contrib.contenttypes',
        'django_social_share',
        'django_social_share.tests',
    ],
    TEMPLATES=[
        {
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'DIRS': [
                os.path.join(BASE_DIR, 'templates'),
            ],
            'OPTIONS': {
                'context_processors': [
                    'django.template.context_processors.request',
                ],
            }
        },
    ]
)


def runtests(*test_args):
    import django
    try:
        django.setup()  # Django 1.7+
    except AttributeError:
        pass
    import django.test.utils
    runner_class = django.test.utils.get_runner(settings)
    test_runner = runner_class(verbosity=1, interactive=True)
    failures = test_runner.run_tests(['django_social_share'])
    sys.exit(failures)


if __name__ == '__main__':
    runtests()
