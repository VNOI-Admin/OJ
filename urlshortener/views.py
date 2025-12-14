from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DeleteView, ListView, RedirectView, UpdateView

from judge.utils.views import DiggPaginatorMixin, TitleMixin

from urlshortener.forms import URLShortenerForm
from urlshortener.models import URLShortener


class URLShortenerMixin:
    """Mixin for URL shortener views that require permission checks."""
    model = URLShortener
    slug_field = 'short_code'
    slug_url_kwarg = 'short_code'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not obj.is_editable_by(self.request.user):
            raise PermissionDenied()
        return obj


class URLShortenerListView(LoginRequiredMixin, TitleMixin, DiggPaginatorMixin, ListView):
    """List all URL shorteners for the current user."""
    model = URLShortener
    template_name = 'urlshortener/list.html'
    context_object_name = 'shorteners'
    paginate_by = 20

    def get_title(self):
        return _('My URL Shorteners')

    def get_queryset(self):
        user = self.request.user
        if user.has_perm('urlshortener.view_all_urlshortener'):
            return URLShortener.objects.all()
        return URLShortener.objects.filter(created_user=user.profile)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_view_all'] = self.request.user.has_perm('urlshortener.view_all_urlshortener')
        return context


class URLShortenerCreateView(LoginRequiredMixin, TitleMixin, CreateView):
    """Create a new URL shortener."""
    model = URLShortener
    form_class = URLShortenerForm
    template_name = 'urlshortener/form.html'

    def get_title(self):
        return _('Create URL Shortener')

    def form_valid(self, form):
        form.instance.created_user = self.request.profile
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit'] = False
        return context


class URLShortenerEditView(URLShortenerMixin, LoginRequiredMixin, TitleMixin, UpdateView):
    """Edit an existing URL shortener."""
    model = URLShortener
    form_class = URLShortenerForm
    template_name = 'urlshortener/form.html'

    def get_title(self):
        return _('Edit URL Shortener: %s') % self.object.short_code

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit'] = True
        return context


class URLShortenerDeleteView(URLShortenerMixin, LoginRequiredMixin, TitleMixin, DeleteView):
    """Delete a URL shortener."""
    model = URLShortener
    template_name = 'urlshortener/confirm_delete.html'
    context_object_name = 'shortener'
    success_url = reverse_lazy('urlshortener_list')

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

        if not shortener.is_accessible():
            raise Http404(_('This shortened URL is not active.'))

        shortener.record_access()
        return shortener.original_url
