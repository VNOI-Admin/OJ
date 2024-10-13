import base64
import hmac
import struct

import requests
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import RegexValidator
from django.db.models import Q
from django.forms import CharField, Form
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import FormView
from django.views.generic.list import BaseListView
from requests.exceptions import HTTPError
from reversion import revisions

from judge.models import Language, Problem, ProblemExportKey, ProblemGroup, ProblemType
from judge.utils.views import TitleMixin
from judge.widgets import HeavySelect2Widget


class ProblemExportMixin:
    def setup(self, request, *args, **kwargs):
        if not settings.VNOJ_PROBLEM_ENABLE_EXPORT:
            raise Http404()
        super().setup(request, *args, **kwargs)
        try:
            id, secret = struct.unpack('>I32s', base64.urlsafe_b64decode(kwargs['secret']))
            self.transfer_key = ProblemExportKey.objects.get(id=id)

            # compare key
            digest = hmac.new(force_bytes(settings.SECRET_KEY), msg=secret, digestmod='sha256').hexdigest()
            if not hmac.compare_digest(digest, self.transfer_key.token):
                raise HTTPError()

        except (ProblemExportKey.DoesNotExist, HTTPError):
            raise Http404('Key not found')


class ProblemExportSelect2View(ProblemExportMixin, BaseListView):
    paginate_by = 20

    def get_queryset(self):
        if self.transfer_key.remaining_uses <= 0:
            return Problem.objects.none()
        return Problem.get_public_problems().filter(Q(code__icontains=self.term) | Q(name__icontains=self.term))

    def get(self, request, *args, **kwargs):
        self.request = request
        self.term = kwargs.get('term', request.GET.get('term', ''))
        self.object_list = self.get_queryset()
        context = self.get_context_data()

        return JsonResponse({
            'results': [
                {
                    'text': obj.name,
                    'id': obj.code,
                } for obj in context['object_list']],
            'more': context['page_obj'].has_next(),
        })


@method_decorator(csrf_exempt, name='dispatch')
class ProblemExportView(ProblemExportMixin, View):
    def get(self, request, *args, **kwargs):
        return JsonResponse({
            'name': self.transfer_key.name,
            'remaining_uses': self.transfer_key.remaining_uses,
        })

    def post(self, request, *args, **kwargs):
        if self.transfer_key.remaining_uses <= 0:
            raise PermissionDenied('No remaining uses')

        try:
            code = request.POST.get('code', '')
            if not code:
                raise HTTPError()
            problem = Problem.objects.get(code=code)
            if not problem.is_accessible_by(AnonymousUser()):
                raise HTTPError()
        except (Problem.DoesNotExist, HTTPError):
            raise Http404('Problem not found')

        self.transfer_key.remaining_uses -= 1
        self.transfer_key.save()

        return JsonResponse({
            'code': problem.code,
            'name': problem.name,
            'description': problem.description,
            'time_limit': problem.time_limit,
            'memory_limit': problem.memory_limit,
            'points': problem.points,
            'partial': problem.partial,
            'short_circuit': problem.short_circuit,
        })


def get_problem_export_select_url(host=settings.VNOJ_PROBLEM_IMPORT_HOST, secret=settings.VNOJ_PROBLEM_IMPORT_SECRET):
    return host + reverse('problem_export_select2_ajax', args=(secret,))


def get_problem_export_url(host=settings.VNOJ_PROBLEM_IMPORT_HOST, secret=settings.VNOJ_PROBLEM_IMPORT_SECRET):
    return host + reverse('problem_export', args=(secret,))


class ProblemImportForm(Form):
    problem = CharField(max_length=32,
                        validators=[RegexValidator('^[a-z0-9_]+$', _('Problem code must be ^[a-z0-9_]+$'))])
    new_code = CharField(max_length=32, validators=[RegexValidator('^[a-z0-9_]+$',
                                                                   _('Problem code must be ^[a-z0-9_]+$'))])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['problem'].widget = HeavySelect2Widget(data_url=get_problem_export_select_url(),
                                                           attrs={'style': 'width: 100%'})

    def clean_new_code(self):
        new_code = self.cleaned_data['new_code']
        if Problem.objects.filter(code=new_code).exists():
            raise ValidationError(_('Problem with code already exists.'))
        return new_code

    def clean(self):
        key_info = requests.get(get_problem_export_url(), timeout=settings.VNOJ_PROBLEM_IMPORT_TIMEOUT).json()
        if not key_info:
            self.add_error(None, _('Request timed out'))
        elif key_info['remaining_uses'] <= 0:
            self.add_error('secret', _('No remaining uses'))


class ProblemImportView(TitleMixin, FormView):
    title = _('Import Problem')
    template_name = 'problem/import.html'
    form_class = ProblemImportForm

    def form_valid(self, form):
        problem_info = requests.post(get_problem_export_url(),
                                     data={'code': form.cleaned_data['problem']},
                                     timeout=settings.VNOJ_PROBLEM_IMPORT_TIMEOUT).json()

        if not problem_info:
            raise Http404('Request timed out')
        problem = Problem()
        problem.code = form.cleaned_data['new_code']
        # Use the exported code
        problem.judge_code = settings.VNOJ_PROBLEM_IMPORT_JUDGE_PREFIX + problem_info['code']
        problem.name = problem_info['name']
        problem.description = problem_info['description']
        problem.time_limit = problem_info['time_limit']
        problem.memory_limit = problem_info['memory_limit']
        problem.points = problem_info['points']
        problem.partial = problem_info['partial']
        problem.short_circuit = problem_info['short_circuit']
        problem.group = ProblemGroup.objects.order_by('id').first()     # Uncategorized
        problem.date = timezone.now()
        problem.is_manually_managed = True
        with revisions.create_revision(atomic=True):
            problem.save()
            problem.allowed_languages.set(Language.objects.filter(include_in_problem=True))
            problem.types.set([ProblemType.objects.order_by('id').first()])  # Uncategorized
            problem.curators.add(self.request.profile)
            revisions.set_user(self.request.user)
            revisions.set_comment(_('Imported from %s%s') % (
                settings.VNOJ_PROBLEM_IMPORT_HOST, reverse('problem_detail', args=(form.cleaned_data['problem'],))))
        return HttpResponseRedirect(reverse('problem_edit', args=(problem.code,)))

    def dispatch(self, request, *args, **kwargs):
        if not settings.VNOJ_PROBLEM_ENABLE_IMPORT:
            raise Http404()
        if not request.user.is_superuser:
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)
