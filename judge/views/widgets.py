import json
import os
import uuid
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import default_storage
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponseRedirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.generic import View
from martor.api import imgur_uploader

from judge.models import Submission
from judge.utils.views import generic_message

__all__ = ['rejudge_submission', 'DetectTimezone']


@login_required
@require_POST
def rejudge_submission(request):
    if 'id' not in request.POST or not request.POST['id'].isdigit():
        return HttpResponseBadRequest()

    try:
        submission = Submission.objects.get(id=request.POST['id'])
    except Submission.DoesNotExist:
        return HttpResponseBadRequest()

    if not submission.problem.is_rejudgeable_by(request.user):
        return HttpResponseForbidden()

    submission.judge(rejudge=True, rejudge_user=request.user)

    redirect = request.POST.get('path', None)

    return HttpResponseRedirect(redirect) if redirect else HttpResponse('success', content_type='text/plain')


class DetectTimezone(View):
    def askgeo(self, lat, long):
        if not hasattr(settings, 'ASKGEO_ACCOUNT_ID') or not hasattr(settings, 'ASKGEO_ACCOUNT_API_KEY'):
            raise ImproperlyConfigured()
        data = requests.get('http://api.askgeo.com/v1/%s/%s/query.json?databases=TimeZone&points=%f,%f' %
                            (settings.ASKGEO_ACCOUNT_ID, settings.ASKGEO_ACCOUNT_API_KEY, lat, long)).json()
        try:
            return HttpResponse(data['data'][0]['TimeZone']['TimeZoneId'], content_type='text/plain')
        except (IndexError, KeyError):
            return HttpResponse(_('Invalid upstream data: %s') % data, content_type='text/plain', status=500)

    def geonames(self, lat, long):
        if not hasattr(settings, 'GEONAMES_USERNAME'):
            raise ImproperlyConfigured()
        data = requests.get('http://api.geonames.org/timezoneJSON?lat=%f&lng=%f&username=%s' %
                            (lat, long, settings.GEONAMES_USERNAME)).json()
        try:
            return HttpResponse(data['timezoneId'], content_type='text/plain')
        except KeyError:
            return HttpResponse(_('Invalid upstream data: %s') % data, content_type='text/plain', status=500)

    def default(self, lat, long):
        raise Http404()

    def get(self, request, *args, **kwargs):
        backend = settings.TIMEZONE_DETECT_BACKEND
        try:
            lat, long = float(request.GET['lat']), float(request.GET['long'])
        except (ValueError, KeyError):
            return HttpResponse(_('Bad latitude or longitude'), content_type='text/plain', status=404)
        return {
            'askgeo': self.askgeo,
            'geonames': self.geonames,
        }.get(backend, self.default)(lat, long)


def django_uploader(image):
    ext = os.path.splitext(image.name)[1]
    if ext not in settings.MARTOR_UPLOAD_SAFE_EXTS:
        ext = '.png'
    name = str(uuid.uuid4()) + ext
    default_storage.save(os.path.join(settings.MARTOR_UPLOAD_MEDIA_DIR, name), image)
    url_base = getattr(settings, 'MARTOR_UPLOAD_URL_PREFIX',
                       urljoin(settings.MEDIA_URL, settings.MARTOR_UPLOAD_MEDIA_DIR))
    if not url_base.endswith('/'):
        url_base += '/'
    return json.dumps({'status': 200, 'name': '', 'link': urljoin(url_base, name)})


def pdf_statement_uploader(statement):
    ext = os.path.splitext(statement.name)[1]
    name = str(uuid.uuid4()) + ext
    default_storage.save(os.path.join(settings.PDF_STATEMENT_UPLOAD_MEDIA_DIR, name), statement)
    url_base = getattr(settings, 'PDF_STATEMENT_UPLOAD_URL_PREFIX',
                       urljoin(settings.MEDIA_URL, settings.PDF_STATEMENT_UPLOAD_MEDIA_DIR))
    if not url_base.endswith('/'):
        url_base += '/'
    return urljoin(url_base, name)


def submission_uploader(submission_file, problem_code, user_id):
    ext = os.path.splitext(submission_file.name)[1]
    name = str(uuid.uuid4()) + ext
    default_storage.save(
        os.path.join(settings.SUBMISSION_FILE_UPLOAD_MEDIA_DIR, problem_code, str(user_id), name),
        submission_file,
    )
    url_base = getattr(settings, 'SUBMISSION_FILE_UPLOAD_URL_PREFIX',
                       urljoin(settings.MEDIA_URL, settings.SUBMISSION_FILE_UPLOAD_MEDIA_DIR))
    if not url_base.endswith('/'):
        url_base += '/'
    return urljoin(url_base, os.path.join(problem_code, str(user_id), name))


@login_required
def martor_image_uploader(request):
    if request.method != 'POST' or not request.is_ajax() or 'markdown-image-upload' not in request.FILES:
        return HttpResponseBadRequest('Invalid request')

    image = request.FILES['markdown-image-upload']
    if request.user.is_staff or request.user.has_perm('judge.can_upload_image'):
        data = django_uploader(image)
    else:
        data = imgur_uploader(image)
    return HttpResponse(data, content_type='application/json')


def csrf_failure(request, reason=''):
    title = _('CSRF verification failed')
    message = _('This error should not happend in normal operation. '
                'Mostly this is because we are under a DDOS attack and we need to raise '
                'our shield to protect the site from the attack.\n\n'
                'If you see this error, please return to the homepage and try again.'
                'DO NOT hit F5/reload/refresh page, it will cause this error again.')
    return generic_message(request, title, message)
