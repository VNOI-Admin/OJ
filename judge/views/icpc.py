from uuid import UUID

from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.management.base import CommandError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.generic import FormView

from judge.forms import ICPCJobForm
from judge.tasks import run_icpc_job
from judge.utils.celery import task_status_by_id, task_status_url_by_id
from judge.utils.icpc import LAST_JOB_CACHE_KEY, get_icpc_folder, git_last_commit, list_icpc_problems
from judge.utils.views import TitleMixin

JOB_CACHE_KEY = 'icpc_job_id'
JOB_CACHE_TIMEOUT = 3600  # 1 hour
RUNNING_STATES = ('PENDING', 'STARTED', 'PROGRESS')


def get_running_job_id():
    job_id = cache.get(JOB_CACHE_KEY)
    if job_id and task_status_by_id(job_id).status in RUNNING_STATES:
        return job_id
    return None


def job_progress_url(job_id):
    return task_status_url_by_id(
        job_id, message=_('Running ICPC job...'), redirect=reverse('icpc_job_status', args=[job_id]),
    )


class ICPCJobView(TitleMixin, FormView):
    template_name = 'icpc/job.html'
    form_class = ICPCJobForm
    title = 'ICPC problem import'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied(_('Only superusers can run ICPC jobs'))

        self.folder_error = None
        self.problems = []
        self.last_commit = None
        try:
            icpc_folder = get_icpc_folder()
            self.problems = list_icpc_problems(icpc_folder)
            self.last_commit = git_last_commit(icpc_folder)
        except CommandError as e:
            self.folder_error = str(e)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['problems'] = self.problems
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['folder_error'] = self.folder_error
        context['running_job_id'] = get_running_job_id()
        context['last_commit'] = self.last_commit
        context['last_job'] = cache.get(LAST_JOB_CACHE_KEY)
        return context

    def form_valid(self, form):
        job_id = get_running_job_id()
        if job_id is None:
            action = form.cleaned_data['action']
            job_id = run_icpc_job.delay(
                problem=form.cleaned_data['problem'] or None,
                import_problems=action != ICPCJobForm.SUBMIT,
                submit=action != ICPCJobForm.IMPORT,
            ).id
            cache.set(JOB_CACHE_KEY, job_id, JOB_CACHE_TIMEOUT)
        return HttpResponseRedirect(job_progress_url(job_id))


def icpc_job_status(request, task_id):
    if not request.user.is_superuser:
        raise PermissionDenied(_('Only superusers can view ICPC jobs'))
    try:
        UUID(task_id)
    except ValueError:
        raise Http404()

    job = task_status_by_id(task_id)
    if job.state != 'SUCCESS':
        return HttpResponseRedirect(job_progress_url(task_id))

    return render(request, 'icpc/job-status.html', {
        'title': _('ICPC problem import'),
        'log': job.result['log'],
        'results': job.result['results'],
        'error': job.result['error'],
    })
