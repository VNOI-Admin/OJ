from django import forms
from django.db import transaction
from django.http import Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from judge.models import MiscConfig
from judge.utils.views import TitleMixin
from judge.views.widgets import static_uploader


class MiscConfigForm(forms.Form):
    logo = forms.FileField(help_text='The site logo e.g. the image in the top left corner.')


class MiscConfigEdit(TitleMixin, FormView):
    template_name = 'misc_config/edit.html'
    form_class = MiscConfigForm
    title = _('Site settings')

    def get_success_url(self):
        return reverse('home')

    def form_valid(self, form):
        with transaction.atomic():
            logo = form.files.get('logo', default=None)
            if logo is not None:
                logo_url = static_uploader(logo)
                config, _ = MiscConfig.objects.update_or_create(key='site_logo', defaults={'value': logo_url})
                config.save()
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise Http404
        return super().dispatch(request, *args, **kwargs)
