from django.db.models import F, Window
from django.db.models.functions import RowNumber
from django.http import Http404
from django.urls import reverse
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from judge.models import Submission
from judge.utils.problems import get_result_data
from judge.views.submission import ForceContestMixin, ProblemSubmissions

__all__ = ['RankedSubmissions', 'ContestRankedSubmission']


class RankedSubmissions(ProblemSubmissions):
    tab = 'best_submissions_list'
    dynamic_update = False

    def access_check(self, request):
        # only show ranked submissions for public problems
        if not self.problem.is_public:
            raise Http404()

        super().access_check(request)

    def _base_queryset(self):
        # Rankings are viewer-independent: rank all submissions of the problem,
        # regardless of any contest visibility the viewer has.
        queryset = Submission.objects.filter(problem_id=self.problem.id)
        if self.is_contest_scoped:
            queryset = queryset.filter(contest_object=self.contest)
        return queryset

    def get_queryset(self):
        points = 'contest__points' if self.is_contest_scoped else 'points'
        # This queryset must stay free of display joins (language, badge, ...) so the
        # window scan is answered entirely from the (problem, user, -points, -time)
        # index. DeferredPaginationListView paginates its pks and hydrates only the
        # page's rows via deferred_paginate.
        return self._base_queryset() \
            .filter(user__is_unlisted=False, **{points + '__gt': 0}) \
            .annotate(user_rank=Window(
                RowNumber(),
                partition_by=F('user_id'),
                order_by=[F(points).desc(), F('time').asc(nulls_last=True), F('id').asc()],
            )) \
            .filter(user_rank=1) \
            .order_by('-' + points, 'time')

    # if you want to use the default pagination, you can uncomment the following method
    # and use `.values('id')` in the `get_queryset`

    # def paginate_queryset(self, queryset, page_size):
    #     paginator, page, object_list, has_other = super().paginate_queryset(queryset, page_size)
    #     # Fetch the display joins only for the rows on this page.
    #     ids = [row['id'] for row in object_list]
    #     subs = {sub.id: sub for sub in submission_related(Submission.objects.filter(id__in=ids))}
    #     page.object_list = object_list = [subs[i] for i in ids]
    #     return paginator, page, object_list, has_other

    def get_ordering(self):
        if self.is_contest_scoped:
            return ('-contest__points', 'time')
        else:
            return ('-points', 'time')

    def get_title(self):
        return _('Best solutions for %s') % self.problem_name

    def get_content_title(self):
        return mark_safe(escape(_('Best solutions for %s')) % (
            format_html('<a href="{1}">{0}</a>', self.problem_name,
                        reverse('problem_detail', args=[self.problem.code])),
        ))

    def _get_result_data(self, queryset=None):
        if queryset is None:
            queryset = self._base_queryset()
        return get_result_data(queryset.order_by())


class ContestRankedSubmission(ForceContestMixin, RankedSubmissions):
    def get_title(self):
        if self.problem.is_accessible_by(self.request.user):
            return _('Best solutions for %(problem)s in %(contest)s') % {
                'problem': self.problem_name, 'contest': self.contest.name,
            }
        return _('Best solutions for problem %(number)s in %(contest)s') % {
            'number': self.get_problem_number(self.problem), 'contest': self.contest.name,
        }

    def get_content_title(self):
        if self.problem.is_accessible_by(self.request.user):
            return mark_safe(escape(_('Best solutions for %(problem)s in %(contest)s')) % {
                'problem': format_html('<a href="{1}">{0}</a>', self.problem_name,
                                       reverse('problem_detail', args=[self.problem.code])),
                'contest': format_html('<a href="{1}">{0}</a>', self.contest.name,
                                       reverse('contest_view', args=[self.contest.key])),
            })
        return mark_safe(escape(_('Best solutions for problem %(number)s in %(contest)s')) % {
            'number': self.get_problem_number(self.problem),
            'contest': format_html('<a href="{1}">{0}</a>', self.contest.name,
                                   reverse('contest_view', args=[self.contest.key])),
        })
