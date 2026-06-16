import json
import os
import re
import uuid
from urllib.parse import urljoin, urlparse

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, \
    HttpResponseRedirect
from django.urls import Resolver404, resolve
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from judge.models import Contest, FileUsage, Problem, Submission, UserFile
from martor.api import imgur_uploader

__all__ = ['rejudge_submission']

_PROBLEM_PATH_RE = re.compile(r'^/problem/(?P<code>[a-z0-9_]+)(?:/|$)')
_CONTEST_PATH_RE = re.compile(r'^/contest/(?P<key>[a-z0-9_]+)(?:/|$)')


def _resolve_admin_change_pk(referer_path, model_name):
    """Return the object pk if ``referer_path`` is the admin change page for
    ``judge.<model_name>`` (e.g. /admin/judge/problem/123/change/), else None."""
    if not referer_path:
        return None
    try:
        match = resolve(referer_path)
    except Resolver404:
        return None
    if match.url_name == f'judge_{model_name}_change':
        return match.kwargs.get('object_id')
    return None


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


def _extract_referer_path(request):
    referer = request.META.get('HTTP_REFERER', '')
    if not referer:
        return ''
    return urlparse(referer).path


def _normalize_uploaded_image_name(image):
    original_name = os.path.basename(image.name)
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in settings.MARTOR_UPLOAD_SAFE_EXTS:
        ext = '.png'
    image.name = f'{uuid.uuid4()}{ext}'
    return original_name


def _resolve_problem_context(request):
    referer_path = _extract_referer_path(request)

    # Editing happens in the Django admin (/admin/judge/problem/<pk>/change/),
    # which carries the pk rather than the code.
    admin_pk = _resolve_admin_change_pk(referer_path, 'problem')
    if admin_pk:
        try:
            problem = Problem.objects.get(pk=admin_pk)
        except (Problem.DoesNotExist, ValueError, TypeError):
            problem = None
        if problem is not None and problem.is_editable_by(request.user):
            return problem

    candidate_codes = []
    code_from_form = request.POST.get('code', '').strip()
    if code_from_form:
        candidate_codes.append(code_from_form)

    path_match = _PROBLEM_PATH_RE.match(referer_path)
    if path_match:
        candidate_codes.append(path_match.group('code'))

    seen = set()
    for code in candidate_codes:
        if code in seen:
            continue
        seen.add(code)

        try:
            problem = Problem.objects.get(code=code)
        except Problem.DoesNotExist:
            continue

        if problem.is_editable_by(request.user):
            return problem

    return None


def _resolve_contest_context(request):
    referer_path = _extract_referer_path(request)

    # Editing happens in the Django admin (/admin/judge/contest/<pk>/change/),
    # which carries the pk rather than the key.
    admin_pk = _resolve_admin_change_pk(referer_path, 'contest')
    if admin_pk:
        try:
            contest = Contest.objects.get(pk=admin_pk)
        except (Contest.DoesNotExist, ValueError, TypeError):
            contest = None
        if contest is not None and contest.is_editable_by(request.user):
            return contest

    candidate_keys = []
    key_from_form = request.POST.get('key', '').strip()
    if key_from_form:
        candidate_keys.append(key_from_form)

    path_match = _CONTEST_PATH_RE.match(referer_path)
    if path_match:
        candidate_keys.append(path_match.group('key'))

    seen = set()
    for key in candidate_keys:
        if key in seen:
            continue
        seen.add(key)

        try:
            contest = Contest.objects.get(key=key)
        except Contest.DoesNotExist:
            continue

        if contest.is_editable_by(request.user):
            return contest

    return None


def _resolve_upload_scope(request):
    problem = _resolve_problem_context(request)
    if problem is not None:
        return UserFile.STORAGE_SCOPE_PROBLEM, problem, None

    contest = _resolve_contest_context(request)
    if contest is not None:
        return UserFile.STORAGE_SCOPE_CONTEST, None, contest

    return UserFile.STORAGE_SCOPE_USER, None, None


def django_uploader(request, image):
    original_name = _normalize_uploaded_image_name(image)
    storage_scope, problem, contest = _resolve_upload_scope(request)

    # Keep non-problem/contest markdown uploads public by default to preserve
    # legacy behavior (images must render inline in blog posts, comments, etc.).
    is_public = storage_scope == UserFile.STORAGE_SCOPE_USER

    with transaction.atomic():
        user_file = UserFile.objects.create(
            user=request.profile,
            file=image,
            filename=original_name,
            storage_scope=storage_scope,
            is_public=is_public,
        )

        usage_kwargs = {
            'file': user_file,
            'usage_type': 'markdown_content',
            'context_description': 'Martor markdown content',
        }

        if problem is not None:
            usage_kwargs['problem_id'] = problem.id
            usage_kwargs['context_description'] = f'Problem {problem.code} description'
        elif contest is not None:
            usage_kwargs['contest_id'] = contest.id
            usage_kwargs['context_description'] = f'Contest {contest.key} description'

        FileUsage.objects.create(**usage_kwargs)

    return json.dumps({'status': 200, 'name': user_file.filename, 'link': user_file.get_access_url()})


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
        data = django_uploader(request, image)
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
