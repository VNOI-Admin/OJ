import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from urlshortener.models import URLShortener


class URLShortenerForm(forms.ModelForm):
    class Meta:
        model = URLShortener
        fields = ['original_url', 'suffix', 'is_active']
        widgets = {
            'original_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://example.com/very/long/url',
            }),
            'suffix': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Leave blank to auto-generate'),
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.is_edit = kwargs.pop('is_edit', False)
        super().__init__(*args, **kwargs)

        if not self.is_edit:
            self.fields['suffix'].required = False

    def clean_suffix(self):
        suffix = self.cleaned_data.get('suffix', '').strip()

        if not suffix:
            if self.is_edit:
                raise ValidationError(_('Suffix cannot be empty.'))
            # Auto-generate suffix for new shorteners
            return URLShortener.generate_unique_suffix()

        # Validate suffix format
        if not re.match(r'^[a-zA-Z0-9_-]{1,50}$', suffix):
            raise ValidationError(
                _('Suffix can only contain letters, numbers, underscores, and hyphens (1-50 characters).')
            )

        # Check uniqueness (exclude current instance when editing)
        queryset = URLShortener.objects.filter(suffix=suffix)
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise ValidationError(_('This suffix is already taken. Please choose another one.'))

        return suffix

    def clean_original_url(self):
        url = self.cleaned_data.get('original_url', '')

        # Block localhost/internal URLs for security
        blocked_patterns = [
            r'^https?://localhost',
            r'^https?://127\.0\.0\.1',
            r'^https?://0\.0\.0\.0',
            r'^https?://\[::1\]',
            r'^https?://10\.',
            r'^https?://172\.(1[6-9]|2[0-9]|3[0-1])\.',
            r'^https?://192\.168\.',
        ]

        for pattern in blocked_patterns:
            if re.match(pattern, url, re.IGNORECASE):
                raise ValidationError(_('Cannot shorten internal or localhost URLs.'))

        return url


class URLShortenerEditForm(URLShortenerForm):
    """Form for editing existing URL shorteners."""

    def __init__(self, *args, **kwargs):
        kwargs['is_edit'] = True
        super().__init__(*args, **kwargs)
