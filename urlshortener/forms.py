from django import forms
from django.utils.html import format_html

from urlshortener.models import URLShortener


class ShortCodeWidget(forms.TextInput):
    def render(self, name, value, attrs=None, renderer=None):
        input_html = super().render(name, value, attrs, renderer)
        return format_html(
            '<div style="display: inline-flex; align-items: stretch; gap: 8px;">{}'
            '<button type="button" class="button" onclick="generateShortCode()" '
            'style="margin: 0; padding-top: 0; padding-bottom: 0;">'
            '<i class="fa fa-random"></i></button></div>',
            input_html,
        )


class URLShortenerForm(forms.ModelForm):
    class Meta:
        model = URLShortener
        fields = ['original_url', 'short_code', 'is_active']
        widgets = {
            'short_code': ShortCodeWidget(),
        }
