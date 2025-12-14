from django.urls import path

from urlshortener import views

urlpatterns = [
    path('', views.URLShortenerListView.as_view(), name='urlshortener_list'),
    path('create/', views.URLShortenerCreateView.as_view(), name='urlshortener_create'),
    path('<str:short_code>/', views.URLShortenerDetailView.as_view(), name='urlshortener_detail'),
    path('<str:short_code>/edit/', views.URLShortenerEditView.as_view(), name='urlshortener_edit'),
    path('<str:short_code>/delete/', views.URLShortenerDeleteView.as_view(), name='urlshortener_delete'),
]
