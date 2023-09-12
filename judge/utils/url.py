import urllib.parse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

URL_VALIDATOR = URLValidator(schemes=['http', 'https'])


def get_absolute_url(url, host):
    try:
        URL_VALIDATOR(url)
        return url
    except ValidationError:
        return urllib.parse.urljoin(host, url)


def get_absolute_submission_file_url(source):
    return get_absolute_url(source, settings.SITE_FULL_URL)


def get_absolute_pdf_url(pdf_url):
    return get_absolute_url(pdf_url, settings.SITE_FULL_URL)
