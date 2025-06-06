import json
import os
import uuid
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, \
    HttpResponseRedirect
from django.views.decorators.http import require_POST

from judge.models import Submission
from martor.api import imgur_uploader

__all__ = ['rejudge_submission']


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
    if request.method != 'POST' or 'markdown-image-upload' not in request.FILES:
        return HttpResponseBadRequest('Invalid request')

    image = request.FILES['markdown-image-upload']
    if request.user.is_staff or request.user.has_perm('judge.can_upload_image'):
        data = django_uploader(image)
    else:
        data = imgur_uploader(image)
    return HttpResponse(data, content_type='application/json')


def csrf_failure(request: HttpRequest, reason=''):
    # Redirect to the same page in case of CSRF failure
    # So that we can turn on cloudflare DDOS protection without
    # showing the CSRF failure page to user
    return HttpResponseRedirect(request.path)
