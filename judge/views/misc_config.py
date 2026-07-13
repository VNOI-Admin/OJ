from django import forms
from django.db import transaction
from django.http import Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from judge.models import MiscConfig
from judge.utils.views import TitleMixin
from judge.views.widgets import static_uploader

_TEXT_KEYS = [
    'meta_keywords', 'meta_description', 'analytics', 'top_notification',
    'announcement', 'footer', 'home_page_top', 'discord_invite_link',
    'discord_invite_shieldio', 'description_example',
]


class MiscConfigForm(forms.Form):
    logo = forms.FileField(
        required=False,
        label=_('Site logo'),
        help_text=_('The site logo (top left corner). Leave empty to keep current.'),
    )
    favicon = forms.FileField(
        required=False,
        label=_('Site favicon'),
        help_text=_('The site favicon. Leave empty to keep current.'),
    )
    meta_keywords = forms.CharField(
        required=False,
        label=_('Meta keywords'),
        help_text=_('HTML meta keywords for SEO.'),
    )
    meta_description = forms.CharField(
        required=False,
        label=_('Meta description'),
        help_text=_('HTML meta description for SEO.'),
    )
    analytics = forms.CharField(
        required=False,
        label=_('Analytics'),
        widget=forms.Textarea,
        help_text=_('Analytics tracking code (raw HTML/JS, injected into every page).'),
    )
    top_notification = forms.CharField(
        required=False,
        label=_('Top notification'),
        widget=forms.Textarea,
        help_text=_('Notification banner shown at the top of every page. Supports Django template syntax.'),
    )
    announcement = forms.CharField(
        required=False,
        label=_('Announcement'),
        widget=forms.Textarea,
        help_text=_('Site-wide announcement (raw HTML).'),
    )
    footer = forms.CharField(
        required=False,
        label=_('Footer'),
        widget=forms.Textarea,
        help_text=_('Footer content (raw HTML).'),
    )
    home_page_top = forms.CharField(
        required=False,
        label=_('Home page top'),
        widget=forms.Textarea,
        help_text=_('Content rendered at the top of the homepage. Supports Django template syntax.'),
    )
    discord_invite_link = forms.CharField(
        required=False,
        label=_('Discord invite link'),
        help_text=_('Discord server invite URL.'),
    )
    discord_invite_shieldio = forms.CharField(
        required=False,
        label=_('Discord Shield.io badge URL'),
        help_text=_('Shield.io badge URL shown alongside the Discord invite link.'),
    )
    description_example = forms.CharField(
        required=False,
        label=_('Description example'),
        widget=forms.Textarea,
        help_text=_('Example problem description pre-filled when creating new problems.'),
    )


class MiscConfigEdit(TitleMixin, FormView):
    template_name = 'misc_config/edit.html'
    form_class = MiscConfigForm
    title = _('Site settings')

    def get_success_url(self):
        return reverse('misc_config')

    def get_initial(self):
        initial = super().get_initial()
        for config in MiscConfig.objects.filter(key__in=_TEXT_KEYS):
            initial[config.key] = config.value
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context['current_logo'] = MiscConfig.objects.get(key='site_logo').value
        except MiscConfig.DoesNotExist:
            context['current_logo'] = None
        try:
            context['current_favicon'] = MiscConfig.objects.get(key='site_favicon').value
        except MiscConfig.DoesNotExist:
            context['current_favicon'] = None
        return context

    def form_valid(self, form):
        with transaction.atomic():
            logo = form.files.get('logo')
            if logo is not None:
                logo_url = static_uploader(logo)
                MiscConfig.objects.update_or_create(key='site_logo', defaults={'value': logo_url})
            favicon = form.files.get('favicon')
            if favicon is not None:
                favicon_url = static_uploader(favicon)
                MiscConfig.objects.update_or_create(key='site_favicon', defaults={'value': favicon_url})

            current = {
                c.key: c.value
                for c in MiscConfig.objects.filter(key__in=_TEXT_KEYS)
            }
            for key in _TEXT_KEYS:
                new_value = form.cleaned_data.get(key, '')
                if new_value == current.get(key, ''):
                    continue
                if new_value:
                    MiscConfig.objects.update_or_create(key=key, defaults={'value': new_value})
                elif key in current:
                    MiscConfig.objects.filter(key=key).delete()
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise Http404
        return super().dispatch(request, *args, **kwargs)
