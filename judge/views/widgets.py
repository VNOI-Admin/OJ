import json
import os
import uuid
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.core.signing import BadSignature, Signer
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, \
    HttpResponseRedirect, JsonResponse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from judge.models import Submission
from judge.widgets.s3_upload import make_s3_client

__all__ = ['rejudge_submission']


@login_required
@require_POST
def rejudge_submission(request):
    if 'id' not in request.POST or not request.POST['id'].isdigit():
        return HttpResponseBadRequest()

    try:
        submission = Submission.objects.select_related('problem').get(id=request.POST['id'])
    except Submission.DoesNotExist:
        return HttpResponseBadRequest()

    problem = submission.problem

    if problem.is_archived or problem.is_deleted:
        return HttpResponseForbidden()

    if not problem.is_rejudgeable_by(request.user):
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
        return HttpResponseForbidden(_('You do not have permission to upload images'))
    return HttpResponse(data, content_type='application/json')


def static_uploader(static_file):
    ext = os.path.splitext(static_file.name)[1]
    name = str(uuid.uuid4()) + ext
    default_storage.save(os.path.join(settings.STATIC_UPLOAD_MEDIA_DIR, name), static_file)
    url_base = getattr(settings, 'STATIC_UPLOAD_URL_PREFIX',
                       urljoin(settings.MEDIA_URL, settings.STATIC_UPLOAD_MEDIA_DIR))
    if not url_base.endswith('/'):
        url_base += '/'
    return urljoin(url_base, name)


@login_required
@require_POST
def s3_presign_post(request):
    if not getattr(settings, 'S3_PRESIGNED_UPLOAD_BUCKET', None):
        return JsonResponse({'error': 'S3 upload not configured'}, status=503)
    try:
        body = json.loads(request.body)
        token, filename, content_type = body['token'], body['filename'], body['content_type']
    except (ValueError, KeyError):
        return JsonResponse({'error': 'Invalid request'}, status=400)

    try:
        value = Signer().unsign(token)
        max_size_str, prefix = value.split(':', 1)
        max_size = int(max_size_str)
    except (BadSignature, ValueError):
        return JsonResponse({'error': 'Invalid token'}, status=400)

    ext = os.path.splitext(filename)[1]
    key = prefix + str(uuid.uuid4()) + ext

    s3 = make_s3_client()
    presigned = s3.generate_presigned_post(
        Bucket=settings.S3_PRESIGNED_UPLOAD_BUCKET,
        Key=key,
        Fields={'Content-Type': content_type},
        Conditions=[
            {'Content-Type': content_type},
            ['content-length-range', 0, max_size],  # enforced by S3, not JS
        ],
        ExpiresIn=getattr(settings, 'S3_PRESIGNED_UPLOAD_EXPIRY', 3600),
    )
    presigned['file_url'] = 's3:' + key
    return JsonResponse(presigned)


def csrf_failure(request: HttpRequest, reason=''):
    # Redirect to the same page in case of CSRF failure
    # So that we can turn on cloudflare DDOS protection without
    # showing the CSRF failure page to user
    return HttpResponseRedirect(request.path)
