from django.urls import path

from urlshortener import views

# Management URLs - for the main domain at /shorteners/
urlpatterns = [
    # List all shorteners
    path('', views.URLShortenerListView.as_view(), name='urlshortener_list'),

    # Create new shortener
    path('create/', views.URLShortenerCreateView.as_view(), name='urlshortener_create'),

    # Edit shortener
    path('<str:suffix>/edit/', views.URLShortenerEditView.as_view(), name='urlshortener_edit'),

    # Delete shortener
    path('<str:suffix>/delete/', views.URLShortenerDeleteView.as_view(), name='urlshortener_delete'),
]
