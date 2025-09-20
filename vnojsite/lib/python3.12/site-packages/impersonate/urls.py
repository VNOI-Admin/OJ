# -*- coding: utf-8 -*-
from django.urls import path

from . import views

urlpatterns = [
    path('stop/', views.stop_impersonate, name='impersonate-stop'),
    path(
        'list/',
        views.list_users,
        {'template': 'impersonate/list_users.html'},
        name='impersonate-list',
    ),
    path(
        'search/',
        views.search_users,
        {'template': 'impersonate/search_users.html'},
        name='impersonate-search',
    ),
    path('<path:uid>/', views.impersonate, name='impersonate-start'),
]
