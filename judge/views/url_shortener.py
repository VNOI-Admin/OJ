from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from judge.forms import URLShortenerForm
from judge.models import URLShortener
from judge.utils.views import DiggPaginatorMixin, TitleMixin


class URLShortenerListView(LoginRequiredMixin, TitleMixin, DiggPaginatorMixin, ListView):
    model = URLShortener
    template_name = 'url_shortener/list.html'
    title = 'Quản lý URLs rút gọn'
    paginate_by = 50

    def get_queryset(self):
        queryset = URLShortener.objects.select_related('creator__user', 'organization')
        if self.request.user.has_perm('judge.view_all_url_stats'):
            return queryset
        return queryset.filter(creator=self.request.profile)


class URLShortenerCreateView(LoginRequiredMixin, PermissionRequiredMixin, TitleMixin, CreateView):
    model = URLShortener
    form_class = URLShortenerForm
    template_name = 'url_shortener/create.html'
    title = 'Tạo URL rút gọn'
    permission_required = 'judge.create_url_shortener'
    raise_exception = True
    success_url = reverse_lazy('url_shortener_list')

    def form_valid(self, form):
        form.instance.creator = self.request.profile
        return super().form_valid(form)


class URLShortenerUpdateView(LoginRequiredMixin, TitleMixin, UpdateView):
    model = URLShortener
    form_class = URLShortenerForm
    template_name = 'url_shortener/edit.html'
    title = 'Chỉnh sửa URL rút gọn'
    slug_field = 'short_code'
    slug_url_kwarg = 'code'
    success_url = reverse_lazy('url_shortener_list')

    def get_object(self):
        obj = super().get_object()
        if obj.creator != self.request.profile and not self.request.user.has_perm('judge.view_all_url_stats'):
            raise Http404()
        return obj


class URLShortenerDeleteView(LoginRequiredMixin, DeleteView):
    model = URLShortener
    http_method_names = ['post']
    slug_field = 'short_code'
    slug_url_kwarg = 'code'
    success_url = reverse_lazy('url_shortener_list')

    def get_object(self):
        obj = super().get_object()
        if obj.creator != self.request.profile and not self.request.user.has_perm('judge.view_all_url_stats'):
            raise Http404()
        return obj


def url_shortener_redirect(request, code):
    shortener = get_object_or_404(URLShortener, short_code=code, is_active=True)
    shortener.increment_clicks()
    return redirect(shortener.long_url)
