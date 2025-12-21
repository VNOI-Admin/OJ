from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import Http404
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DeleteView, DetailView, ListView, RedirectView, UpdateView

from judge.utils.views import DiggPaginatorMixin, TitleMixin
from urlshortener.forms import URLShortenerForm
from urlshortener.models import URLShortener


class URLShortenerMixin:
    model = URLShortener
    slug_field = 'short_code'
    slug_url_kwarg = 'short_code'


class URLShortenerListView(PermissionRequiredMixin, TitleMixin, DiggPaginatorMixin, ListView):
    model = URLShortener
    template_name = 'urlshortener/list.html'
    context_object_name = 'shorteners'
    paginate_by = 20
    permission_required = 'urlshortener.view_urlshortener'

    def get_title(self):
        return _('URL Shorteners')


class URLShortenerCreateView(PermissionRequiredMixin, TitleMixin, CreateView):
    model = URLShortener
    form_class = URLShortenerForm
    template_name = 'urlshortener/form.html'
    permission_required = 'urlshortener.add_urlshortener'

    def get_title(self):
        return _('Create URL Shortener')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit'] = False
        return context


class URLShortenerDetailView(PermissionRequiredMixin, URLShortenerMixin, TitleMixin, DetailView):
    model = URLShortener
    template_name = 'urlshortener/detail.html'
    context_object_name = 'shortener'
    permission_required = 'urlshortener.view_urlshortener'

    def get_title(self):
        return _('URL Shortener: %s') % self.object.short_code


class URLShortenerEditView(PermissionRequiredMixin, URLShortenerMixin, TitleMixin, UpdateView):
    model = URLShortener
    form_class = URLShortenerForm
    template_name = 'urlshortener/form.html'
    permission_required = 'urlshortener.change_urlshortener'

    def get_title(self):
        return _('Edit URL Shortener: %s') % self.object.short_code

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit'] = True
        return context


class URLShortenerDeleteView(PermissionRequiredMixin, URLShortenerMixin, TitleMixin, DeleteView):
    model = URLShortener
    template_name = 'urlshortener/confirm_delete.html'
    context_object_name = 'shortener'
    success_url = reverse_lazy('urlshortener_list')
    permission_required = 'urlshortener.delete_urlshortener'

    def get_title(self):
        return _('Delete URL Shortener: %s') % self.object.short_code


class URLShortenerRedirectView(RedirectView):
    """Redirect to the original URL when accessing a shortened URL."""
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        short_code = kwargs.get('short_code')
        try:
            shortener = URLShortener.objects.get(short_code=short_code)
        except URLShortener.DoesNotExist:
            raise Http404(_('URL shortener not found.'))

        if not shortener.is_active:
            raise Http404(_('This shortened URL is not active.'))

        shortener.record_access()
        return shortener.original_url
