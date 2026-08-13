import logging
import os
import shutil
import tempfile
import uuid

from celery.result import AsyncResult
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext as _

from judge.forms import ProblemPackageImportForm
from judge.models import Problem
from judge.tasks.problem_package import import_problem_package
from judge.utils.problem_package import can_use_problem_packages, export_problem, get_problem_package_staging_path
from judge.views import tasks as task_views


logger = logging.getLogger(__name__)
_SESSION_TASKS_KEY = 'problem_package_import_tasks'


def _require_access(user):
    if not can_use_problem_packages(user):
        raise Http404()


def _stage_upload(uploaded_package):
    os.makedirs(settings.VNOJ_PROBLEM_PACKAGE_ROOT, exist_ok=True)
    staged_token = uuid.uuid4().hex
    staged_directory = get_problem_package_staging_path(staged_token)
    os.mkdir(staged_directory, mode=0o700)
    package_path = os.path.join(staged_directory, 'package.zip')
    try:
        with open(package_path, 'wb') as package_file:
            for chunk in uploaded_package.chunks():
                package_file.write(chunk)
    except Exception:
        shutil.rmtree(staged_directory, ignore_errors=True)
        raise
    return staged_token


def _remember_task(request, task_id):
    task_id = str(task_id)
    task_ids = [item for item in request.session.get(_SESSION_TASKS_KEY, ()) if item != task_id]
    task_ids.append(task_id)
    request.session[_SESSION_TASKS_KEY] = task_ids[-settings.VNOJ_PROBLEM_PACKAGE_SESSION_TASK_LIMIT:]


def _forget_task(request, task_id):
    task_id = str(task_id)
    request.session[_SESSION_TASKS_KEY] = [
        item for item in request.session.get(_SESSION_TASKS_KEY, ()) if item != task_id
    ]


def _require_task_access(request, task_id):
    _require_access(request.user)
    task_id = str(task_id)
    if task_id not in request.session.get(_SESSION_TASKS_KEY, ()):
        raise Http404()
    return task_id


def _task_status_url(result, message, redirect):
    query = urlencode({'message': message, 'redirect': redirect})
    return '%s?%s' % (reverse('problem_package_import_status', args=(result.id,)), query)


@login_required
def import_problem_package_view(request):
    _require_access(request.user)
    if request.method == 'POST':
        form = ProblemPackageImportForm(request.POST, request.FILES)
        if form.is_valid():
            task_kwargs = {'user_id': request.user.pk, 'code': form.cleaned_data['code']}
            staged_token = None
            try:
                if form.cleaned_data['source'] == form.SOURCE_UPLOAD:
                    staged_token = _stage_upload(form.cleaned_data['package'])
                    task_kwargs['staged_token'] = staged_token
                else:
                    task_kwargs['package_url'] = form.cleaned_data['package_url']
                result = import_problem_package.delay(**task_kwargs)
            except Exception:
                logger.exception('Unable to stage or queue a problem package import')
                if staged_token:
                    shutil.rmtree(get_problem_package_staging_path(staged_token), ignore_errors=True)
                form.add_error(None, _('Unable to queue the problem package import.'))
            else:
                _remember_task(request, result.id)
                success_url = reverse('problem_package_import_success', args=(result.id,))
                return HttpResponseRedirect(_task_status_url(
                    result, message=_('Importing problem package...'), redirect=success_url,
                ))
    else:
        form = ProblemPackageImportForm()
    return render(request, 'problem/import-package.html', {'form': form})


@login_required
def import_problem_package_status(request, task_id):
    task_id = _require_task_access(request, task_id)
    return task_views.task_status(
        request, task_id, ajax_url=reverse('problem_package_import_status_ajax'),
    )


@login_required
def import_problem_package_status_ajax(request):
    if 'id' not in request.GET:
        return HttpResponseBadRequest('Need to pass GET parameter "id"', content_type='text/plain')
    try:
        task_id = str(uuid.UUID(request.GET['id']))
    except (AttributeError, TypeError, ValueError):
        raise Http404()
    _require_task_access(request, task_id)
    return JsonResponse(task_views.get_task_status(task_id))


@login_required
def import_problem_package_success(request, task_id):
    task_id = _require_task_access(request, task_id)
    result = AsyncResult(task_id)
    if not result.successful() or not isinstance(result.result, str):
        raise Http404()
    _forget_task(request, task_id)
    return HttpResponseRedirect(reverse('problem_detail', args=(result.result,)))


@login_required
def export_problem_package_view(request, problem):
    _require_access(request.user)
    problem = get_object_or_404(Problem.available, code=problem)
    package_file = tempfile.NamedTemporaryFile(suffix='.zip')
    try:
        export_problem(problem, package_file.name)
        package_file.seek(0)
    except Exception:
        package_file.close()
        raise
    return FileResponse(package_file, as_attachment=True, filename='%s.zip' % problem.code,
                        content_type='application/zip')
