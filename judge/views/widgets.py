import json
import os
import re
import uuid
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, \
    HttpResponseRedirect, JsonResponse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_POST
from lxml.html import tostring

from judge.jinja2.reference import reference_map
from judge.models import Submission

__all__ = ['rejudge_submission', 'resolve_references']


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


MAX_REFERENCES = 500
_reference_name_re = re.compile(r'\w+$')


@require_GET
def resolve_references(request):
    """Batch-resolve [user:name]/[ruser:name] tokens to their rendered link HTML.

    The client (resources/markdown-client.js) collects every reference on the page after
    client-side markdown rendering and requests them all here in one round-trip. `refs` is a
    comma-separated list of `type:name` tokens; the response maps each token back to its HTML.
    Read-only public data (username -> rating link), so no auth/CSRF is required.
    """
    tokens = request.GET.get('refs', '').split(',')
    if len(tokens) > MAX_REFERENCES:
        return HttpResponseBadRequest('too many references')

    by_type = {}
    for token in tokens:
        rtype, sep, name = token.strip().partition(':')
        if sep and rtype in reference_map and _reference_name_re.match(name):
            by_type.setdefault(rtype, set()).add(name)

    result = {}
    for rtype, names in by_type.items():
        render_fn, info_fn = reference_map[rtype]
        info = info_fn(names)  # one DB query per reference type
        for name in names:
            result['%s:%s' % (rtype, name)] = tostring(render_fn(name, info.get(name)), encoding='unicode')
    return JsonResponse(result)


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


def csrf_failure(request: HttpRequest, reason=''):
    # Redirect to the same page in case of CSRF failure
    # So that we can turn on cloudflare DDOS protection without
    # showing the CSRF failure page to user
    return HttpResponseRedirect(request.path)
