# -*- coding: utf-8 -*-
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'impersonate'
    default_auto_field = 'django.db.models.AutoField'

    def ready(self):
        from . import signals
