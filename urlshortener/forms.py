from django import forms
from django.utils.html import format_html

from urlshortener.models import URLShortener


class ShortCodeWidget(forms.TextInput):
    def render(self, name, value, attrs=None, renderer=None):
        final_attrs = self.build_attrs(self.attrs, attrs)
        field_id = final_attrs.get('id')

        # Add a class for styling
        final_attrs['class'] = final_attrs.get('class', '') + ' short-code-input'

        input_html = super().render(name, value, final_attrs, renderer)
        return format_html(
            '<div class="short-code-widget-container">{}'
            '<button type="button" class="button short-code-widget-button" onclick="generateShortCode(\'{}\')">'
            '<i class="fa fa-random"></i></button></div>',
            input_html,
            field_id,
        )

    class Media:
        css = {
            'all': ['urlshortener/css/short_code_widget.css'],
        }
        js = ['urlshortener/js/short_code_widget.js']


class URLShortenerForm(forms.ModelForm):
    class Meta:
        model = URLShortener
        fields = ['original_url', 'short_code', 'is_active']
        widgets = {
            'short_code': ShortCodeWidget(),
        }
