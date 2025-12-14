from django import forms

from urlshortener.models import URLShortener


class URLShortenerForm(forms.ModelForm):
    class Meta:
        model = URLShortener
        fields = ['original_url', 'short_code', 'is_active']
