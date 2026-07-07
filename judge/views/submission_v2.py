import hashlib
import json

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import BadRequest
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, gettext_lazy as _
from django.views.generic import ListView

from judge.models import Language, Organization, Submission
from judge.services.submission import RawSubmissionList, SubmissionListFilters, SubmissionService
from judge.utils.cursor_paginator import Cursor, CursorPaginator
from judge.utils.lazy import memo_lazy
from judge.utils.problems import get_result_data, user_completed_ids, user_editable_ids, user_tester_ids


class CursorListPage:
    is_cursor = True
    page_range = ()

    def __init__(self, object_list, number, previous_cursor=None, next_cursor=None):
        self.object_list = object_list
        self.number = number
        self.previous_cursor = previous_cursor
        self.next_cursor = next_cursor

    def __len__(self):
        return len(self.object_list)

    def __getitem__(self, index):
        return self.object_list[index]

    def has_previous(self):
        return self.previous_cursor is not None

    def has_next(self):
        return self.next_cursor is not None

    def has_other_pages(self):
        return self.has_previous() or self.has_next()


class CursorListPaginator:
    is_infinite = True

    def __init__(self, per_page):
        self.per_page = per_page


class AllSubmissions(ListView):
    """
    Dedicated endpoint for the All Submissions page.

    Keep request parsing and template context in the view; delegate submission
    listing work to judge.services.submission.
    """
    model = Submission
    paginate_by = 50
    stats_update_interval = 3600
    show_problem = True
    template_name = 'submission/list_cursor.html'
    context_object_name = 'submissions'
    selected_languages = frozenset()
    selected_statuses = frozenset()
    selected_organization = None
    cursor_query_param = 'cursor'
    cursor_salt = 'judge.all_submissions.cursor'

    def get_queryset(self):
        return RawSubmissionList(
            request=self.request,
            filters=self.get_filters(),
            language_code=self.request.LANGUAGE_CODE,
        )

    def paginate_queryset(self, queryset, page_size):
        cursor = self.get_cursor()
        result = SubmissionService.get_cursor_page(
            request=self.request,
            filters=self.get_filters(),
            cursor=cursor,
            page_size=page_size,
            language_code=self.request.LANGUAGE_CODE,
        )
        if cursor is not None and not result.submissions:
            raise Http404()

        previous_cursor = self.encode_cursor(
            reverse=True,
            position=result.previous_position,
        ) if result.has_previous else None
        next_cursor = self.encode_cursor(
            reverse=False,
            position=result.next_position,
        ) if result.has_next else None

        page = CursorListPage(
            object_list=result.submissions,
            number=1,
            previous_cursor=previous_cursor,
            next_cursor=next_cursor,
        )
        paginator = CursorListPaginator(page_size)
        return paginator, page, page.object_list, page.has_other_pages()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['title'] = _('All submissions')
        context['content_title'] = _('All submissions')
        context['tab'] = 'all_submissions_list'
        context['dynamic_update'] = context['page_obj'].number == 1
        context['dynamic_contest_id'] = False
        context['dynamic_user_id'] = False
        context['dynamic_problem_id'] = False
        context['show_problem'] = self.show_problem
        context['stats_update_interval'] = self.stats_update_interval

        context.update(self.get_rows_context(context['submissions']))

        context['all_languages'] = Language.objects.all().values_list('key', 'name')
        context['selected_languages'] = self.selected_languages

        context['all_statuses'] = self.get_searchable_status_codes()
        context['selected_statuses'] = self.selected_statuses

        context['all_organizations'] = Organization.objects.values_list('pk', 'name')
        context['selected_organization'] = self.selected_organization

        context['results_json'] = mark_safe(json.dumps(self.get_result_data()))
        context['results_colors_json'] = mark_safe(json.dumps(settings.DMOJ_STATS_SUBMISSION_RESULT_COLORS))

        context['submission_pagination_json'] = mark_safe(json.dumps(self.get_pagination_state(
            context['page_obj'],
        )))
        context['first_page_href'] = reverse('all_submissions')
        context['my_submissions_link'] = self.get_my_submissions_page()
        context['all_submissions_link'] = reverse('all_submissions')
        context['is_in_low_power_mode'] = False
        return context

    def get(self, request, *args, **kwargs):
        self._load_filters(request)

        if self.cursor_query_param in request.GET:
            raise Http404()

        if 'results' in request.GET:
            return JsonResponse(self.get_result_data())

        return super().get(request, *args, **kwargs)

    def _load_filters(self, request):
        self.selected_languages = set(request.GET.getlist('language'))
        self.selected_statuses = set(request.GET.getlist('status'))
        self.selected_organization = request.GET.get('organization')

        if self.selected_organization:
            try:
                self.selected_organization = int(self.selected_organization)
            except ValueError:
                raise Http404()
            get_object_or_404(Organization, pk=self.selected_organization)
        else:
            self.selected_organization = None

    def get_filters(self):
        return SubmissionListFilters(
            languages=frozenset(self.selected_languages),
            statuses=frozenset(self.selected_statuses),
            organization_id=self.selected_organization,
        )

    def get_cursor_paginator(self):
        return CursorPaginator(
            queryset=Submission.objects.none(),
            ordering=('-id',),
            page_size=self.paginate_by,
            cursor_salt=self.get_cursor_salt(),
        )

    def get_cursor(self):
        token = self.request.GET.get(self.cursor_query_param)
        if not token:
            return None
        return self.get_cursor_paginator().decode_cursor(token)

    def encode_cursor(self, reverse, position):
        if position is None:
            return None
        return self.get_cursor_paginator().encode_cursor(Cursor(
            reverse=reverse,
            position=(position,),
        ))

    def get_cursor_salt(self):
        return f'{self.cursor_salt}:{self.get_filter_fingerprint()}'

    def get_filter_fingerprint(self):
        user = self.request.user
        payload = {
            'languages': sorted(self.selected_languages),
            'statuses': sorted(self.selected_statuses),
            'organization_id': self.selected_organization,
            'profile_id': self.request.profile.id if user.is_authenticated else None,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
        }
        data = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(data.encode('utf-8')).hexdigest()

    def get_pagination_state(self, page):
        return {
            'pageUrl': reverse('all_submissions_page'),
            'page': page.number,
            'previousCursor': page.previous_cursor,
            'nextCursor': page.next_cursor,
            'hasPrevious': page.has_previous(),
            'hasNext': page.has_next(),
        }

    def get_rows_context(self, submissions):
        authenticated = self.request.user.is_authenticated
        profile = self.request.profile
        return {
            'submissions': submissions,
            'show_problem': self.show_problem,
            'completed_problem_ids': memo_lazy(lambda: user_completed_ids(profile), set) if authenticated else [],
            'editable_problem_ids': memo_lazy(lambda: user_editable_ids(profile), set) if authenticated else [],
            'tester_problem_ids': memo_lazy(lambda: user_tester_ids(profile), set) if authenticated else [],
        }

    def render_rows_html(self, submissions):
        return render_to_string(
            'submission/list-rows.html',
            self.get_rows_context(submissions),
            request=self.request,
        )

    def get_my_submissions_page(self):
        if self.request.user.is_authenticated:
            return reverse('all_user_submissions', kwargs={'user': self.request.user.username})

    def get_searchable_status_codes(self):
        hidden_codes = ['SC']
        if not self.could_filter_by_status():
            hidden_codes += ['IE', 'QU', 'P', 'G', 'D']
        return [(key, value) for key, value in Submission.SEARCHABLE_STATUS if key not in hidden_codes]

    def could_filter_by_status(self):
        return self.request.user.is_superuser or self.request.user.is_staff

    def get_result_data(self):
        if self.are_result_counts_unavailable():
            return {
                'categories': [],
                'total': 0,
                'unavailable': True,
            }

        if self.selected_languages or self.selected_statuses or self.selected_organization:
            result = self._format_result_counts(
                SubmissionService.get_result_counts(
                    self.request,
                    self.get_filters(),
                ),
            )
            self._translate_result_names(result)
            return result

        key = 'global_submission_result_data'
        result = cache.get(key)
        if not result:
            result = get_result_data(Submission.objects.all())
            cache.set(key, result, self.stats_update_interval)
        self._translate_result_names(result)
        return result

    def are_result_counts_unavailable(self):
        return len(self.selected_statuses) > 1

    def _translate_result_names(self, result):
        for category in result['categories']:
            category['name'] = gettext(category['name'])

    def _format_result_counts(self, results):
        return {
            'categories': [
                {'code': 'AC', 'name': 'Accepted', 'count': results['AC']},
                {'code': 'PAC', 'name': 'Partial', 'count': results['PAC']},
                {'code': 'WA', 'name': 'Wrong', 'count': results['WA']},
                {'code': 'CE', 'name': 'Compile Error', 'count': results['CE']},
                {'code': 'TLE', 'name': 'Timeout', 'count': results['TLE']},
                {'code': 'ERR', 'name': 'Error',
                 'count': results['MLE'] + results['OLE'] + results['IR'] + results['RTE'] +
                 results['AB'] + results['IE']},
            ],
            'total': sum(results.values()),
        }


class AllSubmissionsPage(AllSubmissions):
    def get(self, request, *args, **kwargs):
        try:
            self._load_filters(request)
            _, page, _, _ = self.paginate_queryset(self.get_queryset(), self.paginate_by)
        except BadRequest:
            return JsonResponse({'error': 'invalid_cursor'}, status=400)
        except Http404:
            return JsonResponse({'error': 'page_not_found'}, status=404)

        return JsonResponse({
            'rows_html': self.render_rows_html(page.object_list),
            'previous_cursor': page.previous_cursor,
            'next_cursor': page.next_cursor,
            'has_previous': page.has_previous(),
            'has_next': page.has_next(),
        })
