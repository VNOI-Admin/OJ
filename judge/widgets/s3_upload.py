import os

from django import forms
from django.conf import settings
from django.core.signing import Signer
from django.urls import reverse
from django.utils.html import format_html

__all__ = ['S3PresignedUploadWidget', 'S3FileField', 'make_s3_client']


def make_s3_client():
    from django.core.exceptions import ImproperlyConfigured
    import boto3
    required = [
        'S3_PRESIGNED_UPLOAD_BUCKET',
        'S3_PRESIGNED_UPLOAD_ENDPOINT_URL',
        'S3_PRESIGNED_UPLOAD_ACCESS_KEY_ID',
        'S3_PRESIGNED_UPLOAD_SECRET_ACCESS_KEY',
        'S3_PRESIGNED_UPLOAD_REGION',
    ]
    missing = [k for k in required if not getattr(settings, k, None)]
    if missing:
        raise ImproperlyConfigured(f'Missing S3 upload settings: {", ".join(missing)}')
    return boto3.client(
        service_name='s3',
        endpoint_url=settings.S3_PRESIGNED_UPLOAD_ENDPOINT_URL,
        aws_access_key_id=settings.S3_PRESIGNED_UPLOAD_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_PRESIGNED_UPLOAD_SECRET_ACCESS_KEY,
        region_name=settings.S3_PRESIGNED_UPLOAD_REGION,
    )


class S3PresignedUploadWidget(forms.Widget):
    def __init__(self, max_size, fallback_threshold=None, prefix='uploads/', accept=None, attrs=None):
        self.max_size = max_size
        self.fallback_threshold = fallback_threshold  # bytes; files below this go through Django
        self.prefix = prefix.rstrip('/') + '/'
        self.accept = accept
        self.s3_enabled = True  # callers can flip this off per-request (e.g. non-superusers)
        super().__init__(attrs)

    def _s3_configured(self):
        return self.s3_enabled and bool(getattr(settings, 'S3_PRESIGNED_UPLOAD_BUCKET', None))

    @property
    def media(self):
        return forms.Media(js=['s3_upload.js'])

    def _token(self):
        return Signer().sign(f'{self.max_size}:{self.prefix}')

    def render(self, name, value, attrs=None, renderer=None):
        if not self._s3_configured():
            fi_attrs = dict(attrs or {})
            if self.accept:
                fi_attrs['accept'] = self.accept
            # Same data-max-size attribute the S3 branch below stamps on its file input, so any
            # JS reading the file input's size limit doesn't need to know which branch rendered.
            fi_attrs['data-max-size'] = str(self.fallback_threshold or self.max_size)
            return forms.ClearableFileInput().render(name, value, fi_attrs, renderer)
        final_attrs = self.build_attrs(attrs or {})
        wid = final_attrs.get('id', f'id_{name}')
        accept_html = format_html(' accept="{}"', self.accept) if self.accept else ''
        threshold_html = format_html(' data-fallback-threshold="{}"', self.fallback_threshold) \
            if self.fallback_threshold else ''

        current_html = ''
        if value and getattr(value, 'url', None):
            clear_name = f'{name}-clear'
            clear_id = f'{clear_name}_id'  # matches Django's ClearableFileInput id convention
            current_html = format_html(
                '<p class="file-upload">Currently: <a href="{}">{}</a> '
                '&nbsp;<label for="{}">Clear: <input type="checkbox" name="{}" id="{}"></label></p>',
                value.url, os.path.basename(value.name), clear_id, clear_name, clear_id,
            )

        return format_html(
            '{}<span class="s3-upload-widget" data-presign-url="{}" data-token="{}"{}>'
            '<input type="file" name="{}" id="{}" data-max-size="{}"{}>'
            '<input type="hidden" name="{}" id="{}">'
            '<progress class="s3-upload-progress" value="0" max="100" '
            'style="display:none; vertical-align:middle;"></progress>'
            '<span class="s3-upload-status"></span>'
            '</span>',
            current_html,
            reverse('s3_presign_put'), self._token(), threshold_html,
            # The visible file input keeps Django's usual id (id_<name>) so existing page JS
            # written against ClearableFileInput's markup (e.g. $('#id_problem-data-zipfile'))
            # keeps working; the S3 reference value is the one that gets the extra suffix.
            name, wid, str(self.max_size), accept_html,
            name, f'{wid}_s3ref',
        )

    def value_from_datadict(self, data, files, name):
        if not self._s3_configured():
            return forms.ClearableFileInput().value_from_datadict(data, files, name)

        clear = forms.CheckboxInput().value_from_datadict(data, files, f'{name}-clear')
        value = data.get(name, '')

        if value.startswith('s3:'):
            if clear:
                from django.forms.widgets import FILE_INPUT_CONTRADICTION
                return FILE_INPUT_CONTRADICTION
            from django.core.files.uploadedfile import TemporaryUploadedFile
            key = value[len('s3:'):]
            s3 = make_s3_client()
            obj = s3.get_object(Bucket=settings.S3_PRESIGNED_UPLOAD_BUCKET, Key=key)
            body = obj['Body']
            content_type = obj.get('ContentType', 'application/octet-stream')
            filename = os.path.basename(key)
            tmp = TemporaryUploadedFile(filename, content_type, 0, None)
            for chunk in iter(lambda: body.read(65536), b''):
                tmp.write(chunk)
            tmp.size = tmp.tell()
            tmp.seek(0)
            return tmp

        upload = files.get(name)
        if clear:
            if upload:
                from django.forms.widgets import FILE_INPUT_CONTRADICTION
                return FILE_INPUT_CONTRADICTION
            return False
        return upload


class S3FileField(forms.CharField):
    """CharField backed by S3PresignedUploadWidget; cleaned value is the full file URL."""

    def __init__(self, max_size, prefix='uploads/', accept=None, **kwargs):
        kwargs.setdefault('required', False)
        super().__init__(**kwargs)
        self.widget = S3PresignedUploadWidget(max_size=max_size, prefix=prefix, accept=accept)

    def clean(self, value):
        value = super().clean(value)
        if not value:
            return None
        if not value.startswith('s3:'):
            raise forms.ValidationError('Invalid file reference.')
        return value
