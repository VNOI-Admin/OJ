import json
import logging
import os
import re
from datetime import timedelta
from operator import itemgetter
from random import randrange

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db import transaction
from django.db.models import BooleanField, Case, F, Prefetch, Q, When
from django.db.utils import ProgrammingError
from django.http import Http404, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.functional import cached_property
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _, gettext_lazy
from django.views.generic import CreateView, FormView, ListView, UpdateView, View
from django.views.generic.base import TemplateResponseMixin
from django.views.generic.detail import SingleObjectMixin
from reversion import revisions

from judge.comments import CommentedDetailView
from judge.forms import LanguageLimitFormSet, ProblemCloneForm, ProblemEditForm, ProblemImportPolygonForm, \
    ProblemImportPolygonStatementFormSet, ProblemSubmitForm, ProposeProblemSolutionFormSet
from judge.models import ContestSubmission, Judge, Language, Problem, ProblemGroup, \
    ProblemTranslation, ProblemType, RuntimeVersion, Solution, Submission, SubmissionSource
from judge.tasks import on_new_problem
from judge.template_context import misc_config
from judge.utils.codeforces_polygon import ImportPolygonError, PolygonImporter
from judge.utils.diggpaginator import DiggPaginator
from judge.utils.opengraph import generate_opengraph
from judge.utils.pdfoid import PDF_RENDERING_ENABLED, render_pdf
from judge.utils.problems import hot_problems, user_attempted_ids, \
    user_completed_ids
from judge.utils.strings import safe_float_or_none, safe_int_or_none
from judge.utils.tickets import own_ticket_filter
from judge.utils.views import QueryStringSortMixin, SingleObjectFormView, TitleMixin, add_file_response, generic_message
from judge.views.widgets import pdf_statement_uploader, submission_uploader

recjk = re.compile(r'[\u2E80-\u2E99\u2E9B-\u2EF3\u2F00-\u2FD5\u3005\u3007\u3021-\u3029\u3038-\u303A\u303B\u3400-\u4DB5'
                   r'\u4E00-\u9FC3\uF900-\uFA2D\uFA30-\uFA6A\uFA70-\uFAD9\U00020000-\U0002A6D6\U0002F800-\U0002FA1D]')


def get_contest_problem(problem, profile):
    try:
        return problem.contests.get(contest_id=profile.current_contest.contest_id)
    except ObjectDoesNotExist:
        return None


def get_contest_submission_count(problem, profile, virtual):
    return profile.current_contest.submissions.exclude(submission__status__in=['IE']) \
                  .filter(problem__problem=problem, participation__virtual=virtual).count()


class ProblemMixin(object):
    model = Problem
    slug_url_kwarg = 'problem'
    slug_field = 'code'

    def get_object(self, queryset=None):
        problem = super(ProblemMixin, self).get_object(queryset)
        if not problem.is_accessible_by(self.request.user):
            raise Http404()
        return problem

    def no_such_problem(self):
        code = self.kwargs.get(self.slug_url_kwarg, None)
        return generic_message(self.request, _('No such problem'),
                               _('Could not find a problem with the code "%s".') % code, status=404)

    def get(self, request, *args, **kwargs):
        try:
            return super(ProblemMixin, self).get(request, *args, **kwargs)
        except Http404:
            return self.no_such_problem()


class SolvedProblemMixin(object):
    def get_completed_problems(self):
        return user_completed_ids(self.profile) if self.profile is not None else ()

    def get_attempted_problems(self):
        return user_attempted_ids(self.profile) if self.profile is not None else ()

    @cached_property
    def in_contest(self):
        return self.profile is not None and self.profile.current_contest is not None

    @cached_property
    def contest(self):
        return self.request.profile.current_contest.contest

    @cached_property
    def profile(self):
        if not self.request.user.is_authenticated:
            return None
        return self.request.profile


class ProblemSolution(SolvedProblemMixin, ProblemMixin, TitleMixin, CommentedDetailView):
    context_object_name = 'problem'
    template_name = 'problem/editorial.html'

    def get_title(self):
        return _('Editorial for {0}').format(self.object.name)

    def get_content_title(self):
        return mark_safe(escape(_('Editorial for {0}')).format(
            format_html('<a href="{1}">{0}</a>', self.object.name, reverse('problem_detail', args=[self.object.code])),
        ))

    def get_context_data(self, **kwargs):
        context = super(ProblemSolution, self).get_context_data(**kwargs)

        solution = get_object_or_404(Solution, problem=self.object)

        if not solution.is_accessible_by(self.request.user) or self.request.in_contest:
            raise Http404()
        context['solution'] = solution
        context['has_solved_problem'] = self.object.id in self.get_completed_problems()
        return context

    def get_comment_page(self):
        return 's:' + self.object.code

    def no_such_problem(self):
        code = self.kwargs.get(self.slug_url_kwarg, None)
        return generic_message(self.request, _('No such editorial'),
                               _('Could not find an editorial with the code "%s".') % code, status=404)


class ProblemRaw(ProblemMixin, TitleMixin, TemplateResponseMixin, SingleObjectMixin, View):
    context_object_name = 'problem'
    template_name = 'problem/raw.html'

    def get_title(self):
        return self.object.name

    def get_context_data(self, **kwargs):
        context = super(ProblemRaw, self).get_context_data(**kwargs)

        try:
            trans = self.object.translations.get(language=self.request.LANGUAGE_CODE)
        except ProblemTranslation.DoesNotExist:
            trans = None

        context['problem_name'] = self.object.name if trans is None else trans.name
        context['url'] = self.request.build_absolute_uri()
        context['description'] = self.object.description if trans is None else trans.description
        return context

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        with translation.override(settings.LANGUAGE_CODE):
            return self.render_to_response(self.get_context_data(
                object=self.object,
            ))


class ProblemDetail(ProblemMixin, SolvedProblemMixin, CommentedDetailView):
    context_object_name = 'problem'
    template_name = 'problem/problem.html'

    def get_object(self, queryset=None):
        problem = super(ProblemDetail, self).get_object(queryset)

        user = self.request.user
        authed = user.is_authenticated
        self.contest_problem = (None if not authed or user.profile.current_contest is None else
                                get_contest_problem(problem, user.profile))

        return problem

    def is_comment_locked(self):
        if self.contest_problem and self.contest_problem.contest.use_clarifications:
            return True

        return super(ProblemDetail, self).is_comment_locked()

    def get_comment_page(self):
        return 'p:%s' % self.object.code

    def get_context_data(self, **kwargs):
        context = super(ProblemDetail, self).get_context_data(**kwargs)
        user = self.request.user
        authed = user.is_authenticated
        contest_problem = self.contest_problem
        context['has_submissions'] = authed and Submission.objects.filter(user=user.profile,
                                                                          problem=self.object).exists()
        context['contest_problem'] = contest_problem
        if contest_problem:
            clarifications = self.object.clarifications
            context['has_clarifications'] = clarifications.count() > 0
            context['clarifications'] = clarifications.order_by('-date')
            context['submission_limit'] = contest_problem.max_submissions
            if contest_problem.max_submissions:
                context['submissions_left'] = max(contest_problem.max_submissions -
                                                  get_contest_submission_count(self.object, user.profile,
                                                                               user.profile.current_contest.virtual), 0)

        context['available_judges'] = Judge.objects.filter(online=True, problems=self.object)
        context['show_languages'] = self.object.allowed_languages.count() != Language.objects.count()
        context['has_pdf_render'] = PDF_RENDERING_ENABLED
        context['completed_problem_ids'] = self.get_completed_problems()
        context['attempted_problems'] = self.get_attempted_problems()

        can_edit = self.object.is_editable_by(user)
        context['can_edit_problem'] = can_edit
        if user.is_authenticated:
            tickets = self.object.tickets
            if not can_edit:
                tickets = tickets.filter(own_ticket_filter(user.profile.id))
            context['has_tickets'] = tickets.exists()
            context['num_open_tickets'] = tickets.filter(is_open=True).values('id').distinct().count()

        try:
            context['editorial'] = Solution.objects.get(problem=self.object)
        except ObjectDoesNotExist:
            pass
        try:
            translation = self.object.translations.get(language=self.request.LANGUAGE_CODE)
        except ProblemTranslation.DoesNotExist:
            context['title'] = self.object.name
            context['language'] = settings.LANGUAGE_CODE
            context['description'] = self.object.description
            context['translated'] = False
        else:
            context['title'] = translation.name
            context['language'] = self.request.LANGUAGE_CODE
            context['description'] = translation.description
            context['translated'] = True

        if not self.object.og_image or not self.object.summary:
            metadata = generate_opengraph('generated-meta-problem:%s:%d' % (context['language'], self.object.id),
                                          context['description'], 'problem')
        context['meta_description'] = self.object.summary or metadata[0]
        context['og_image'] = self.object.og_image or metadata[1]
        return context


class LatexError(Exception):
    pass


class ProblemPdfView(ProblemMixin, SingleObjectMixin, View):
    logger = logging.getLogger('judge.problem.pdf')
    languages = set(map(itemgetter(0), settings.LANGUAGES))

    def get(self, request, *args, **kwargs):
        if not PDF_RENDERING_ENABLED:
            raise Http404()

        language = kwargs.get('language', self.request.LANGUAGE_CODE)
        if language not in self.languages:
            raise Http404()

        problem = self.get_object()
        pdf_basename = '%s.%s.pdf' % (problem.code, language)

        def render_problem_pdf():
            self.logger.info('Rendering PDF in %s: %s', language, problem.code)

            with translation.override(language):
                try:
                    trans = problem.translations.get(language=language)
                except ProblemTranslation.DoesNotExist:
                    trans = None

                problem_name = trans.name if trans else problem.name
                return render_pdf(
                    html=get_template('problem/raw.html').render({
                        'problem': problem,
                        'problem_name': problem_name,
                        'description': trans.description if trans else problem.description,
                        'url': request.build_absolute_uri(),
                    }).replace('"//', '"https://').replace("'//", "'https://"),
                    title=problem_name,
                )

        response = HttpResponse()
        response['Content-Type'] = 'application/pdf'
        response['Content-Disposition'] = f'inline; filename={pdf_basename}'

        if settings.DMOJ_PDF_PROBLEM_CACHE:
            pdf_filename = os.path.join(settings.DMOJ_PDF_PROBLEM_CACHE, pdf_basename)
            if not os.path.exists(pdf_filename):
                with open(pdf_filename, 'wb') as f:
                    f.write(render_problem_pdf())

            if settings.DMOJ_PDF_PROBLEM_INTERNAL:
                url_path = f'{settings.DMOJ_PDF_PROBLEM_INTERNAL}/{pdf_basename}'
            else:
                url_path = None

            add_file_response(request, response, url_path, pdf_filename)
        else:
            response.content = render_problem_pdf()

        return response


class ProblemList(QueryStringSortMixin, TitleMixin, SolvedProblemMixin, ListView):
    model = Problem
    title = gettext_lazy('Problem list')
    context_object_name = 'problems'
    template_name = 'problem/list.html'
    paginate_by = 50
    sql_sort = frozenset(('points', 'ac_rate', 'user_count', 'code', 'date'))
    manual_sort = frozenset(('name', 'group', 'solved', 'type', 'editorial'))
    all_sorts = sql_sort | manual_sort
    default_desc = frozenset(('points', 'ac_rate', 'user_count'))
    # Default sort by date
    default_sort = '-date'

    def get_paginator(self, queryset, per_page, orphans=0,
                      allow_empty_first_page=True, **kwargs):
        paginator = DiggPaginator(queryset, per_page, body=6, padding=2, orphans=orphans,
                                  count=queryset.values('pk').count(),
                                  allow_empty_first_page=allow_empty_first_page, **kwargs)
        queryset = queryset.add_i18n_name(self.request.LANGUAGE_CODE)
        sort_key = self.order.lstrip('-')
        if sort_key in self.sql_sort:
            queryset = queryset.order_by(self.order, 'id')
        elif sort_key == 'name':
            queryset = queryset.order_by('i18n_name', self.order, 'name', 'id')
        elif sort_key == 'group':
            queryset = queryset.order_by(self.order + '__name', 'name', 'id')
        elif sort_key == 'editorial':
            queryset = queryset.order_by(self.order.replace('editorial', 'has_public_editorial'), 'id')
        elif sort_key == 'solved':
            if self.request.user.is_authenticated:
                profile = self.request.profile
                solved = user_completed_ids(profile)
                attempted = user_attempted_ids(profile)

                def _solved_sort_order(problem):
                    if problem.id in solved:
                        return 1
                    if problem.id in attempted:
                        return 0
                    return -1

                queryset = list(queryset)
                queryset.sort(key=_solved_sort_order, reverse=self.order.startswith('-'))
        elif sort_key == 'type':
            if self.show_types:
                queryset = list(queryset)
                queryset.sort(key=lambda problem: problem.types_list[0] if problem.types_list else '',
                              reverse=self.order.startswith('-'))
        paginator.object_list = queryset
        return paginator

    @cached_property
    def profile(self):
        if not self.request.user.is_authenticated:
            return None
        return self.request.profile

    @staticmethod
    def apply_full_text(queryset, query):
        if recjk.search(query):
            # MariaDB can't tokenize CJK properly, fallback to LIKE '%term%' for each term.
            for term in query.split():
                queryset = queryset.filter(Q(code__icontains=term) | Q(name__icontains=term) |
                                           Q(description__icontains=term))
            return queryset
        return queryset.search(query, queryset.BOOLEAN).extra(order_by=['-relevance'])

    def get_filter(self):
        _filter = Q(is_public=True) & Q(is_organization_private=False)
        if self.profile is not None:
            _filter = Problem.q_add_author_curator_tester(_filter, self.profile)
        return _filter

    def get_normal_queryset(self):
        _filter = self.get_filter()
        queryset = Problem.objects.filter(_filter).select_related('group').defer('description', 'summary')

        if self.profile is not None and self.hide_solved:
            queryset = queryset.exclude(id__in=Submission.objects
                                        .filter(user=self.profile, result='AC', case_points__gte=F('case_total'))
                                        .values_list('problem_id', flat=True))
        if self.show_types:
            queryset = queryset.prefetch_related('types')
        queryset = queryset.annotate(has_public_editorial=Case(
            When(solution__is_public=True, solution__publish_on__lte=timezone.now(), then=True),
            default=False,
            output_field=BooleanField(),
        ))
        if self.has_public_editorial:
            queryset = queryset.filter(has_public_editorial=True)
        if self.category is not None:
            queryset = queryset.filter(group__id=self.category)
        if self.selected_types:
            queryset = queryset.filter(types__in=self.selected_types)
        if 'search' in self.request.GET:
            self.search_query = query = ' '.join(self.request.GET.getlist('search')).strip()
            if query:
                if settings.ENABLE_FTS and self.full_text:
                    queryset = self.apply_full_text(queryset, query)
                else:
                    queryset = queryset.filter(
                        Q(code__icontains=query) | Q(name__icontains=query) | Q(source__icontains=query) |
                        Q(translations__name__icontains=query, translations__language=self.request.LANGUAGE_CODE))
        self.prepoint_queryset = queryset
        if self.point_start is not None:
            queryset = queryset.filter(points__gte=self.point_start)
        if self.point_end is not None:
            queryset = queryset.filter(points__lte=self.point_end)
        return queryset.distinct()

    def get_queryset(self):
        return self.get_normal_queryset()

    def get_hot_problems(self):
        return hot_problems(timedelta(days=1), settings.DMOJ_PROBLEM_HOT_PROBLEM_COUNT)

    def get_context_data(self, **kwargs):
        context = super(ProblemList, self).get_context_data(**kwargs)
        context['hide_solved'] = int(self.hide_solved)
        context['show_types'] = int(self.show_types)
        context['has_public_editorial'] = int(self.has_public_editorial)
        context['full_text'] = int(self.full_text)
        context['category'] = self.category
        context['categories'] = ProblemGroup.objects.all()
        context['selected_types'] = self.selected_types
        context['problem_types'] = ProblemType.objects.all()
        context['has_fts'] = settings.ENABLE_FTS
        context['search_query'] = self.search_query
        context['completed_problem_ids'] = self.get_completed_problems()
        context['attempted_problems'] = self.get_attempted_problems()
        context['hot_problems'] = self.get_hot_problems()
        context['point_start'], context['point_end'], context['point_values'] = self.get_noui_slider_points()
        context.update(self.get_sort_context())
        context.update(self.get_sort_paginate_context())
        return context

    def get_noui_slider_points(self):
        points = sorted(self.prepoint_queryset.values_list('points', flat=True).distinct())
        if not points:
            return 0, 0, {}
        if len(points) == 1:
            return points[0] - 1, points[0] + 1, {
                'min': points[0] - 1,
                '50%': points[0],
                'max': points[0] + 1,
            }

        start, end = points[0], points[-1]
        if self.point_start is not None:
            start = self.point_start
        if self.point_end is not None:
            end = self.point_end
        points_map = {0.0: 'min', 1.0: 'max'}
        size = len(points) - 1
        return start, end, {points_map.get(i / size, '%.2f%%' % (100 * i / size,)): j for i, j in enumerate(points)}

    def GET_with_session(self, request, key):
        if not request.GET:
            return request.session.get(key, False)
        return request.GET.get(key, None) == '1'

    def setup_problem_list(self, request):
        self.hide_solved = self.GET_with_session(request, 'hide_solved')
        self.show_types = self.GET_with_session(request, 'show_types')
        self.full_text = self.GET_with_session(request, 'full_text')
        self.has_public_editorial = self.GET_with_session(request, 'has_public_editorial')

        self.search_query = None
        self.category = None
        self.selected_types = []

        # This actually copies into the instance dictionary...
        self.all_sorts = set(self.all_sorts)
        if not self.show_types:
            self.all_sorts.discard('type')

        self.category = safe_int_or_none(request.GET.get('category'))
        if 'type' in request.GET:
            try:
                self.selected_types = list(map(int, request.GET.getlist('type')))
            except ValueError:
                pass

        self.point_start = safe_float_or_none(request.GET.get('point_start'))
        self.point_end = safe_float_or_none(request.GET.get('point_end'))

    def get(self, request, *args, **kwargs):
        self.setup_problem_list(request)

        try:
            return super(ProblemList, self).get(request, *args, **kwargs)
        except ProgrammingError as e:
            return generic_message(request, 'FTS syntax error', e.args[1], status=400)

    def post(self, request, *args, **kwargs):
        to_update = ('hide_solved', 'show_types', 'has_public_editorial', 'full_text')
        for key in to_update:
            if key in request.GET:
                val = request.GET.get(key) == '1'
                request.session[key] = val
            else:
                request.session.pop(key, None)
        return HttpResponseRedirect(request.get_full_path())


class SuggestList(ProblemList):
    title = gettext_lazy('Suggested problem list')
    template_name = 'problem/suggest-list.html'
    permission_required = 'superuser'

    def get_filter(self):
        return Q(is_public=False) & ~Q(suggester=None)

    def get(self, request, *args, **kwargs):
        if not request.user.has_perm('judge.suggest_new_problem'):
            raise Http404
        return super(SuggestList, self).get(request, *args, **kwargs)


class LanguageTemplateAjax(View):
    def get(self, request, *args, **kwargs):
        try:
            language = get_object_or_404(Language, id=int(request.GET.get('id', 0)))
        except ValueError:
            raise Http404()
        return HttpResponse(language.template, content_type='text/plain')


class RandomProblem(ProblemList):
    def get(self, request, *args, **kwargs):
        self.setup_problem_list(request)
        if self.in_contest:
            raise Http404()

        queryset = self.get_normal_queryset()
        count = queryset.count()
        if not count:
            return HttpResponseRedirect('%s%s%s' % (reverse('problem_list'), request.META['QUERY_STRING'] and '?',
                                                    request.META['QUERY_STRING']))
        return HttpResponseRedirect(queryset[randrange(count)].get_absolute_url())


user_logger = logging.getLogger('judge.user')
user_submit_ip_logger = logging.getLogger('judge.user_submit_ip_logger')


class ProblemSubmit(LoginRequiredMixin, ProblemMixin, TitleMixin, SingleObjectFormView):
    template_name = 'problem/submit.html'
    form_class = ProblemSubmitForm

    @cached_property
    def contest_problem(self):
        if self.request.profile.current_contest is None:
            return None
        return get_contest_problem(self.object, self.request.profile)

    @cached_property
    def remaining_submission_count(self):
        max_subs = self.contest_problem and self.contest_problem.max_submissions
        if max_subs is None:
            return None
        # When an IE submission is rejudged into a non-IE status, it will count towards the
        # submission limit. We max with 0 to ensure that `remaining_submission_count` returns
        # a non-negative integer, which is required for future checks in this view.
        return max(
            0,
            max_subs - get_contest_submission_count(
                self.object, self.request.profile, self.request.profile.current_contest.virtual,
            ),
        )

    @cached_property
    def default_language(self):
        # If the old submission exists, use its language, otherwise use the user's default language.
        if self.old_submission is not None:
            return self.old_submission.language
        return self.request.profile.language

    def get_content_title(self):
        return mark_safe(
            escape(_('Submit to %s')) % format_html(
                '<a href="{0}">{1}</a>',
                reverse('problem_detail', args=[self.object.code]),
                self.object.translated_name(self.request.LANGUAGE_CODE),
            ),
        )

    def get_title(self):
        return _('Submit to %s') % self.object.translated_name(self.request.LANGUAGE_CODE)

    def get_initial(self):
        initial = {'language': self.default_language}
        if self.old_submission is not None:
            initial['source'] = self.old_submission.source.source
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = Submission(user=self.request.profile, problem=self.object)

        if self.object.is_editable_by(self.request.user):
            kwargs['judge_choices'] = tuple(
                Judge.objects.filter(online=True, problems=self.object).values_list('name', 'name'),
            )
        else:
            kwargs['judge_choices'] = ()

        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)

        form.fields['language'].queryset = (
            self.object.usable_languages.order_by('name', 'key')
            .prefetch_related(Prefetch('runtimeversion_set', RuntimeVersion.objects.order_by('priority')))
        )

        form_data = getattr(form, 'cleaned_data', form.initial)
        if 'language' in form_data:
            form.fields['source'].widget.mode = form_data['language'].ace
        form.fields['source'].widget.theme = self.request.profile.resolved_ace_theme

        return form

    def get_success_url(self):
        return reverse('submission_status', args=(self.new_submission.id,))

    def form_valid(self, form):
        if (
            not self.request.user.has_perm('judge.spam_submission') and
            Submission.objects.filter(user=self.request.profile, rejudged_date__isnull=True)
                              .exclude(status__in=['D', 'IE', 'CE', 'AB']).count() >= settings.DMOJ_SUBMISSION_LIMIT
        ):
            return HttpResponse(format_html('<h1>{0}</h1>', _('You submitted too many submissions.')), status=429)
        if not self.object.allowed_languages.filter(id=form.cleaned_data['language'].id).exists():
            raise PermissionDenied()
        if not self.request.user.is_superuser and self.object.banned_users.filter(id=self.request.profile.id).exists():
            return generic_message(self.request, _('Banned from submitting'),
                                   _('You have been declared persona non grata for this problem. '
                                     'You are permanently barred from submitting to this problem.'))
        # Must check for zero and not None. None means infinite submissions remaining.
        if self.remaining_submission_count == 0:
            return generic_message(self.request, _('Too many submissions'),
                                   _('You have exceeded the submission limit for this problem.'))

        if settings.VNOJ_ENABLE_ORGANIZATION_CREDIT_LIMITATION:
            # check if the problem belongs to any organization
            organizations = []
            if self.object.is_organization_private:
                organizations = self.object.organizations.all()

            if len(organizations) == 0:
                # check if the contest belongs to any organization
                if self.contest_problem is not None:
                    contest_object = self.request.profile.current_contest.contest

                    if contest_object.is_organization_private:
                        organizations = contest_object.organizations.all()

            # check if org have credit to execute this submission
            for org in organizations:
                if not org.has_credit_left():
                    org_name = org.name
                    return generic_message(
                        self.request,
                        _('No credit'),
                        _(
                            'The organization %s has no credit left to execute this submission. '
                            'Ask the organization to buy more credit.',
                        )
                        % org_name,
                    )

        with transaction.atomic():
            self.new_submission = form.save(commit=False)

            contest_problem = self.contest_problem
            if contest_problem is not None:
                # Use the contest object from current_contest.contest because we already use it
                # in profile.update_contest().
                self.new_submission.contest_object = self.request.profile.current_contest.contest
                if self.request.profile.current_contest.live:
                    self.new_submission.locked_after = self.new_submission.contest_object.locked_after
                self.new_submission.save()
                ContestSubmission(
                    submission=self.new_submission,
                    problem=contest_problem,
                    participation=self.request.profile.current_contest,
                ).save()
            else:
                self.new_submission.save()

            submission_file = form.files.get('submission_file', None)
            source_url = submission_uploader(
                submission_file=submission_file,
                problem_code=self.new_submission.problem.code,
                user_id=self.new_submission.user.user.id,
            ) if submission_file else ''

            source = SubmissionSource(submission=self.new_submission, source=form.cleaned_data['source'] + source_url)
            source.save()

        # Save a query.
        self.new_submission.source = source
        self.new_submission.judge(force_judge=True, judge_id=form.cleaned_data['judge'])

        # In contest mode, we should log the ip
        if settings.VNOJ_OFFICIAL_CONTEST_MODE:
            ip = self.request.META['REMOTE_ADDR']
            # I didn't log the timestamp here because
            # the logger can handle it.
            user_submit_ip_logger.info(
                '%s,%s,%s',
                self.request.user.username,
                ip,
                self.new_submission.problem.code,
            )

        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['langs'] = Language.objects.all()
        context['no_judges'] = not context['form'].fields['language'].queryset
        context['submission_limit'] = self.contest_problem and self.contest_problem.max_submissions
        context['submissions_left'] = self.remaining_submission_count
        context['ACE_URL'] = settings.ACE_URL
        context['default_lang'] = self.default_language
        return context

    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except Http404:
            # Is this really necessary? This entire post() method could be removed if we don't log this.
            user_logger.info(
                'Naughty user %s wants to submit to %s without permission',
                request.user.username,
                kwargs.get(self.slug_url_kwarg),
            )
            return HttpResponseForbidden(
                format_html('<h1>{0}</h1>', _('You are not allowed to submit to this problem.')),
            )

    def dispatch(self, request, *args, **kwargs):
        submission_id = kwargs.get('submission')
        if submission_id is not None:
            self.old_submission = get_object_or_404(
                Submission.objects.select_related('source', 'language'),
                id=submission_id,
            )
            if self.old_submission.language.file_only:
                raise Http404()
            if not request.user.has_perm('judge.resubmit_other') and self.old_submission.user != request.profile:
                raise PermissionDenied()
        else:
            self.old_submission = None

        return super().dispatch(request, *args, **kwargs)


class ProblemClone(ProblemMixin, PermissionRequiredMixin, TitleMixin, SingleObjectFormView):
    title = gettext_lazy('Clone Problem')
    template_name = 'problem/clone.html'
    form_class = ProblemCloneForm
    permission_required = 'judge.clone_problem'

    def form_valid(self, form):
        problem = self.object

        languages = problem.allowed_languages.all()
        language_limits = problem.language_limits.all()
        organizations = problem.organizations.all()
        types = problem.types.all()
        old_code = problem.code

        problem.pk = None
        problem.is_public = False
        problem.ac_rate = 0
        problem.user_count = 0
        problem.code = form.cleaned_data['code']
        problem.date = timezone.now()
        with revisions.create_revision(atomic=True):
            problem.save(is_clone=True)
            problem.curators.add(self.request.profile)
            problem.allowed_languages.set(languages)
            problem.language_limits.set(language_limits)
            problem.organizations.set(organizations)
            problem.types.set(types)
            revisions.set_user(self.request.user)
            revisions.set_comment(_('Cloned problem from %s') % old_code)

        return HttpResponseRedirect(reverse('problem_edit', args=(problem.code,)))

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object.is_editable_by(request.user):
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)


class ProblemCreate(PermissionRequiredMixin, TitleMixin, CreateView):
    template_name = 'problem/suggest.html'
    model = Problem
    form_class = ProblemEditForm
    permission_required = 'judge.add_problem'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_title(self):
        return _('Creating new problem')

    def get_content_title(self):
        return _('Creating new problem')

    def save_statement(self, form, problem):
        statement_file = form.files.get('statement_file', None)
        if statement_file is not None:
            problem.pdf_url = pdf_statement_uploader(statement_file)

    def form_valid(self, form):
        with revisions.create_revision(atomic=True):
            self.object = problem = form.save()
            problem.curators.add(self.request.user.profile)
            problem.allowed_languages.set(Language.objects.filter(include_in_problem=True))
            problem.date = timezone.now()
            self.save_statement(form, problem)
            problem.save()

            revisions.set_comment(_('Created on site'))
            revisions.set_user(self.request.user)

        return HttpResponseRedirect(self.get_success_url())

    def get_initial(self):
        initial = super(ProblemCreate, self).get_initial()
        initial = initial.copy()
        initial['description'] = misc_config(self.request)['misc_config']['description_example']
        initial['memory_limit'] = 262144  # 256 MB
        initial['partial'] = True
        try:
            initial['group'] = ProblemGroup.objects.get(name='Uncategorized').pk
        except ProblemGroup.DoesNotExist:
            initial['group'] = ProblemGroup.objects.order_by('id').first().pk
        try:
            initial['types'] = ProblemType.objects.get(name='uncategorized').pk
        except ProblemType.DoesNotExist:
            initial['types'] = ProblemType.objects.order_by('id').first().pk
        return initial


class ProblemSuggest(ProblemCreate):
    permission_required = 'judge.suggest_new_problem'

    def get_title(self):
        return _('Suggesting new problem')

    def get_content_title(self):
        return _('Suggesting new problem')

    def form_valid(self, form):
        with revisions.create_revision(atomic=True):
            self.object = problem = form.save()
            problem.suggester = self.request.user.profile
            problem.allowed_languages.set(Language.objects.filter(include_in_problem=True))
            problem.date = timezone.now()
            self.save_statement(form, problem)
            problem.save()

            revisions.set_comment(_('Created on site'))
            revisions.set_user(self.request.user)

        on_new_problem.delay(problem.code, is_suggested=True)
        return HttpResponseRedirect(self.get_success_url())


class ProblemImportPolygon(PermissionRequiredMixin, TitleMixin, FormView):
    title = gettext_lazy('Import problem from Codeforces Polygon package')
    template_name = 'problem/import-polygon.html'
    model = Problem
    form_class = ProblemImportPolygonForm
    permission_required = 'judge.import_polygon_package'

    def get_formset(self):
        return ProblemImportPolygonStatementFormSet(
            data=self.request.POST if self.request.POST else None,
            prefix='statements',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['formset'] = self.get_formset()
        context['site_languages_json'] = mark_safe(json.dumps({code: str(name) for code, name in settings.LANGUAGES}))
        return context

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        formset = self.get_formset()
        if form.is_valid() and formset.is_valid():
            package = form.cleaned_data['package'].file
            code = form.cleaned_data['code']
            do_update = form.cleaned_data['do_update']
            config = {
                'ignore_zero_point_batches': form.cleaned_data['ignore_zero_point_batches'],
                'ignore_zero_point_cases': form.cleaned_data['ignore_zero_point_cases'],
                'append_main_solution_to_tutorial': form.cleaned_data['append_main_solution_to_tutorial'],
                'main_tutorial_language': form.cleaned_data.get('main_tutorial_language', None),
                'main_statement_language': None,
                'polygon_to_site_language_map': {},
            }
            if len(formset) > 1:
                for statement in formset:
                    polygon_language = statement.cleaned_data['polygon_language']
                    site_language = statement.cleaned_data['site_language']

                    if site_language == settings.LANGUAGE_CODE:
                        config['main_statement_language'] = polygon_language
                    else:
                        config['polygon_to_site_language_map'][polygon_language] = site_language

            try:
                importer = PolygonImporter(
                    package=package,
                    code=code,
                    authors=[self.request.profile],
                    curators=[],
                    do_update=do_update,
                    interactive=False,
                    config=config,
                )
                importer.run()
            except ImportPolygonError as e:
                return generic_message(request, _('Failed to import problem'), str(e), status=400)

            return HttpResponseRedirect(reverse('problem_detail', args=[code]))

        return self.render_to_response(self.get_context_data())


class ProblemUpdatePolygon(ProblemImportPolygon, ProblemMixin, SingleObjectMixin):
    title = gettext_lazy('Update problem from Codeforces Polygon package')

    def get_object(self, queryset=None):
        problem = super().get_object(queryset)
        if not problem.is_editable_by(self.request.user):
            raise PermissionDenied()
        return problem

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['code'] = self.object.code
        return kwargs

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)


class ProblemEdit(ProblemMixin, TitleMixin, UpdateView):
    template_name = 'problem/editor.html'
    model = Problem
    form_class = ProblemEditForm

    def get_title(self):
        return _('Editing problem {0}').format(self.object.name)

    def get_content_title(self):
        return mark_safe(escape(_('Editing problem %s')) % (
            format_html('<a href="{1}">{0}</a>', self.object.name,
                        reverse('problem_detail', args=[self.object.code]))))

    def get_object(self, queryset=None):
        problem = super(ProblemEdit, self).get_object(queryset)
        if not problem.is_editable_by(self.request.user):
            raise PermissionDenied()
        return problem

    def get_solution_formset(self):
        if self.request.POST:
            return ProposeProblemSolutionFormSet(self.request.POST, instance=self.get_object())
        return ProposeProblemSolutionFormSet(instance=self.get_object())

    def get_language_limit_formset(self):
        if self.request.POST:
            return LanguageLimitFormSet(self.request.POST, instance=self.get_object(),
                                        form_kwargs={'user': self.request.user})
        return LanguageLimitFormSet(instance=self.get_object(), form_kwargs={'user': self.request.user})

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data['lang_limit_formset'] = self.get_language_limit_formset()
        data['solution_formset'] = self.get_solution_formset()
        return data

    def get_form_kwargs(self):
        kwargs = super(ProblemEdit, self).get_form_kwargs()
        # Due to some limitation with query set in select2
        # We only support this if the problem is private for only
        # 1 organization
        if self.object.organizations.count() == 1:
            kwargs['org_pk'] = self.object.organizations.values_list('pk', flat=True)[0]

        kwargs['user'] = self.request.user
        return kwargs

    def save_statement(self, form, problem):
        statement_file = form.files.get('statement_file', None)
        if statement_file is not None:
            problem.pdf_url = pdf_statement_uploader(statement_file)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        form_lang_limit = self.get_language_limit_formset()
        form_edit = self.get_solution_formset()
        if form.is_valid() and form_edit.is_valid() and form_lang_limit.is_valid():
            with revisions.create_revision(atomic=True):
                problem = form.save()
                self.save_statement(form, problem)
                problem.save()
                form_lang_limit.save()
                form_edit.save()

                revisions.set_comment(_('Edited from site'))
                revisions.set_user(self.request.user)

            return HttpResponseRedirect(reverse('problem_detail', args=[self.object.code]))

        return self.render_to_response(self.get_context_data(object=self.object))

    def dispatch(self, request, *args, **kwargs):
        try:
            return super(ProblemEdit, self).dispatch(request, *args, **kwargs)
        except PermissionDenied:
            return generic_message(request, _("Can't edit problem"),
                                   _('You are not allowed to edit this problem.'), status=403)
