import os
import shutil
import tempfile

from celery.result import AsyncResult
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _

from judge.forms import ProblemPackageImportForm
from judge.models import Problem
from judge.tasks.problem_package import import_problem_package
from judge.utils.celery import redirect_to_task_status
from judge.utils.problem_package import can_use_problem_packages, export_problem


def _require_access(user):
    if not can_use_problem_packages(user):
        raise Http404()


def _stage_upload(uploaded_package):
    os.makedirs(settings.VNOJ_PROBLEM_PACKAGE_ROOT, exist_ok=True)
    staged_directory = tempfile.mkdtemp(prefix='upload-', dir=settings.VNOJ_PROBLEM_PACKAGE_ROOT)
    try:
        with open(os.path.join(staged_directory, 'package.zip'), 'wb') as package_file:
            for chunk in uploaded_package.chunks():
                package_file.write(chunk)
    except Exception:
        shutil.rmtree(staged_directory, ignore_errors=True)
        raise
    return staged_directory


@login_required
def import_problem_package_view(request):
    _require_access(request.user)
    if request.method == 'POST':
        form = ProblemPackageImportForm(request.POST, request.FILES)
        if form.is_valid():
            task_kwargs = {'user_id': request.user.pk, 'code': form.cleaned_data['code']}
            staged_directory = None
            try:
                if form.cleaned_data['source'] == form.SOURCE_UPLOAD:
                    staged_directory = _stage_upload(form.cleaned_data['package'])
                    task_kwargs['staged_directory'] = staged_directory
                else:
                    task_kwargs['package_url'] = form.cleaned_data['package_url']
                result = import_problem_package.delay(**task_kwargs)
            except Exception:
                if staged_directory:
                    shutil.rmtree(staged_directory, ignore_errors=True)
                form.add_error(None, _('Unable to queue the problem package import.'))
            else:
                success_url = reverse('problem_package_import_success', args=(result.id,))
                return redirect_to_task_status(
                    result,
                    message=_('Importing problem package...'),
                    redirect=success_url,
                )
    else:
        form = ProblemPackageImportForm()
    return render(request, 'problem/import-package.html', {'form': form})


@login_required
def import_problem_package_success(request, task_id):
    _require_access(request.user)
    result = AsyncResult(str(task_id))
    if not result.successful() or not isinstance(result.result, str):
        raise Http404()
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
