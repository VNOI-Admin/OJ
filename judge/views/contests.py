import json
from calendar import Calendar, SUNDAY
from collections import defaultdict, namedtuple
from datetime import date, datetime, time, timedelta
from functools import partial
from operator import attrgetter, itemgetter

from django import forms
from django.conf import settings
from django.contrib.auth.context_processors import PermWrapper
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist, PermissionDenied
from django.db import IntegrityError
from django.db.models import Case, Count, F, FloatField, IntegerField, Max, Min, Q, Sum, Value, When
from django.db.models.expressions import CombinedExpression
from django.db.models.query import Prefetch
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template import loader
from django.template.defaultfilters import date as date_filter, floatformat
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.timezone import make_aware
from django.utils.translation import gettext as _, gettext_lazy
from django.views.generic import ListView, TemplateView
from django.views.generic.detail import BaseDetailView, DetailView, SingleObjectMixin, View
from django.views.generic.edit import CreateView, UpdateView
from django.views.generic.list import BaseListView
from icalendar import Calendar as ICalendar, Event
from reversion import revisions

from judge.comments import CommentedDetailView
from judge.contest_format import ICPCContestFormat
from judge.forms import ContestAnnouncementForm, ContestCloneForm, ContestForm, ProposeContestProblemFormSet
from judge.models import Contest, ContestAnnouncement, ContestMoss, ContestParticipation, ContestProblem, ContestTag, \
    Organization, Problem, ProblemClarification, Profile, Submission
from judge.tasks import on_new_contest, run_moss
from judge.utils.celery import redirect_to_task_status
from judge.utils.cms import parse_csv_ranking
from judge.utils.opengraph import generate_opengraph
from judge.utils.problems import _get_result_data, user_attempted_ids, user_completed_ids
from judge.utils.ranker import ranker
from judge.utils.stats import get_bar_chart, get_pie_chart, get_stacked_bar_chart
from judge.utils.views import DiggPaginatorMixin, QueryStringSortMixin, SingleObjectFormView, TitleMixin, \
    generic_message

__all__ = ['ContestList', 'ContestDetail', 'ContestRanking', 'ContestJoin', 'ContestLeave', 'ContestCalendar',
           'ContestClone', 'ContestStats', 'ContestMossView', 'ContestMossDelete', 'contest_ranking_ajax',
           'ContestParticipationList', 'ContestParticipationDisqualify', 'get_contest_ranking_list',
           'base_contest_ranking_list']


def _find_contest(request, key, private_check=True):
    try:
        contest = Contest.objects.get(key=key)
        if private_check and not contest.is_accessible_by(request.user):
            raise ObjectDoesNotExist()
    except ObjectDoesNotExist:
        return generic_message(request, _('No such contest'),
                               _('Could not find a contest with the key "%s".') % key, status=404), False
    return contest, True


class ContestListMixin(object):
    hide_private_contests = False

    def get_queryset(self):
        if self.hide_private_contests is not None:
            if 'hide_private_contests' in self.request.GET:
                self.hide_private_contests = self.request.session['hide_private_contests'] \
                                           = self.request.GET.get('hide_private_contests').lower() == 'true'
            else:
                self.hide_private_contests = self.request.session.get('hide_private_contests', False)

            if self.hide_private_contests:
                return Contest.get_public_contests()

        return Contest.get_visible_contests(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['hide_private_contests'] = self.hide_private_contests
        return context


class ContestList(QueryStringSortMixin, DiggPaginatorMixin, TitleMixin, ContestListMixin, ListView):
    model = Contest
    paginate_by = 20
    template_name = 'contest/list.html'
    title = gettext_lazy('Contests')
    context_object_name = 'past_contests'
    all_sorts = frozenset(('name', 'user_count', 'start_time'))
    default_desc = frozenset(('name', 'user_count'))
    default_sort = '-start_time'

    @cached_property
    def _now(self):
        return timezone.now()

    def _get_queryset(self):
        return super().get_queryset().prefetch_related('tags', 'organizations', 'authors', 'curators', 'testers')

    def get_queryset(self):
        self.search_query = None
        query_set = self._get_queryset().order_by(self.order, 'key').filter(end_time__lt=self._now)
        if 'search' in self.request.GET:
            self.search_query = search_query = ' '.join(self.request.GET.getlist('search')).strip()
            if search_query:
                query_set = query_set.filter(Q(key__icontains=search_query) | Q(name__icontains=search_query))
        return query_set

    def get_context_data(self, **kwargs):
        context = super(ContestList, self).get_context_data(**kwargs)
        present, active, future = [], [], []
        finished = set()
        for contest in self._get_queryset().exclude(end_time__lt=self._now):
            if contest.start_time > self._now:
                future.append(contest)
            else:
                present.append(contest)

        if self.request.user.is_authenticated:
            for participation in ContestParticipation.objects.filter(virtual=0, user=self.request.profile,
                                                                     contest_id__in=present) \
                    .select_related('contest') \
                    .prefetch_related('contest__authors', 'contest__curators', 'contest__testers') \
                    .annotate(key=F('contest__key')):
                if participation.ended:
                    finished.add(participation.contest.key)
                else:
                    active.append(participation)
                    present.remove(participation.contest)

        active.sort(key=attrgetter('end_time', 'key'))
        present.sort(key=attrgetter('end_time', 'key'))
        future.sort(key=attrgetter('start_time'))
        context['active_participations'] = active
        context['current_contests'] = present
        context['future_contests'] = future
        context['finished_contests'] = finished
        context['now'] = self._now
        context['first_page_href'] = '.'
        context['page_suffix'] = '#past-contests'
        context['search_query'] = self.search_query
        context.update(self.get_sort_context())
        context.update(self.get_sort_paginate_context())
        return context


class PrivateContestError(Exception):
    def __init__(self, name, is_private, is_organization_private, orgs):
        self.name = name
        self.is_private = is_private
        self.is_organization_private = is_organization_private
        self.orgs = orgs


class ContestMixin(object):
    context_object_name = 'contest'
    model = Contest
    slug_field = 'key'
    slug_url_kwarg = 'contest'

    @cached_property
    def is_editor(self):
        if not self.request.user.is_authenticated:
            return False
        return self.request.profile.id in self.object.editor_ids

    @cached_property
    def is_tester(self):
        if not self.request.user.is_authenticated:
            return False
        return self.request.profile.id in self.object.tester_ids

    @cached_property
    def can_edit(self):
        return self.object.is_editable_by(self.request.user)

    def get_context_data(self, **kwargs):
        context = super(ContestMixin, self).get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            try:
                context['live_participation'] = (
                    self.request.profile.contest_history.get(
                        contest=self.object,
                        virtual=ContestParticipation.LIVE,
                    )
                )
            except ContestParticipation.DoesNotExist:
                context['live_participation'] = None
                context['has_joined'] = False
            else:
                context['has_joined'] = True
        else:
            context['live_participation'] = None
            context['has_joined'] = False

        context['now'] = timezone.now()
        context['is_editor'] = self.is_editor
        context['is_tester'] = self.is_tester
        context['can_edit'] = self.can_edit

        if not self.object.og_image or not self.object.summary:
            metadata = generate_opengraph('generated-meta-contest:%d' % self.object.id,
                                          self.object.description, 'contest')
        context['meta_description'] = self.object.summary or metadata[0]
        context['og_image'] = self.object.og_image or metadata[1]
        context['has_moss_api_key'] = settings.MOSS_API_KEY is not None
        context['logo_override_image'] = self.object.logo_override_image
        if not context['logo_override_image'] and self.object.organizations.count() == 1:
            context['logo_override_image'] = self.object.organizations.first().logo_override_image

        context['is_ICPC_format'] = (self.object.format.name == ICPCContestFormat.name)
        return context

    def get_object(self, queryset=None):
        contest = super(ContestMixin, self).get_object(queryset)

        profile = self.request.profile
        if (profile is not None and
                ContestParticipation.objects.filter(id=profile.current_contest_id, contest_id=contest.id).exists()):
            return contest

        try:
            contest.access_check(self.request.user)
        except Contest.PrivateContest:
            raise PrivateContestError(contest.name, contest.is_private, contest.is_organization_private,
                                      contest.organizations.all())
        except Contest.Inaccessible:
            raise Http404()
        else:
            return contest

    def dispatch(self, request, *args, **kwargs):
        try:
            return super(ContestMixin, self).dispatch(request, *args, **kwargs)
        except Http404:
            key = kwargs.get(self.slug_url_kwarg, None)
            if key:
                return generic_message(request, _('No such contest'),
                                       _('Could not find a contest with the key "%s".') % key)
            else:
                return generic_message(request, _('No such contest'),
                                       _('Could not find such contest.'))
        except PrivateContestError as e:
            return render(request, 'contest/private.html', {
                'error': e, 'title': _('Access to contest "%s" denied') % e.name,
            }, status=403)


class ContestDetail(ContestMixin, TitleMixin, CommentedDetailView):
    template_name = 'contest/contest.html'

    def is_comment_locked(self):
        if self.object.use_clarifications:
            now = timezone.now()
            if self.object.is_in_contest(self.request.user) or \
                    (self.object.start_time <= now and now <= self.object.end_time):
                return True

        return super(ContestDetail, self).is_comment_locked()

    def get_comment_page(self):
        return 'c:%s' % self.object.key

    def get_title(self):
        return self.object.name

    def get_context_data(self, **kwargs):
        context = super(ContestDetail, self).get_context_data(**kwargs)
        context['contest_problems'] = Problem.objects.filter(contests__contest=self.object) \
            .order_by('contests__order').defer('description') \
            .annotate(has_public_editorial=Sum(Case(When(solution__is_public=True, then=1),
                                                    default=0, output_field=IntegerField()))) \
            .add_i18n_name(self.request.LANGUAGE_CODE)

        # convert to problem points in contest instead of actual points
        points_list = self.object.contest_problems.values_list('points').order_by('order')
        for idx, p in enumerate(context['contest_problems']):
            p.points = points_list[idx][0]

        context['metadata'] = {
            'has_public_editorials': any(
                problem.is_public and problem.has_public_editorial for problem in context['contest_problems']
            ),
        }
        context['metadata'].update(
            **self.object.contest_problems
            .annotate(
                partials_enabled=F('partial').bitand(F('problem__partial')),
                pretests_enabled=F('is_pretested').bitand(F('contest__run_pretests_only')),
            )
            .aggregate(
                has_partials=Sum('partials_enabled'),
                has_pretests=Sum('pretests_enabled'),
                has_submission_cap=Sum('max_submissions'),
                problem_count=Count('id'),
            ),
        )

        clarifications = ProblemClarification.objects.filter(problem__in=self.object.problems.all())
        context['has_clarifications'] = clarifications.count() > 0
        context['clarifications'] = clarifications.order_by('-date')
        announcements = ContestAnnouncement.objects.filter(contest=self.object)
        context['has_announcements'] = announcements.count() > 0
        context['announcements'] = announcements.order_by('-date')
        context['can_announce'] = self.object.is_editable_by(self.request.user)

        authenticated = self.request.user.is_authenticated
        context['completed_problem_ids'] = user_completed_ids(self.request.profile) if authenticated else []
        context['attempted_problem_ids'] = user_attempted_ids(self.request.profile) if authenticated else []

        return context


class ContestClone(ContestMixin, PermissionRequiredMixin, TitleMixin, SingleObjectFormView):
    title = _('Clone Contest')
    template_name = 'contest/clone.html'
    form_class = ContestCloneForm
    permission_required = 'judge.clone_contest'

    def form_valid(self, form):
        contest = self.object

        tags = contest.tags.all()
        organizations = contest.organizations.all()
        private_contestants = contest.private_contestants.all()
        view_contest_scoreboard = contest.view_contest_scoreboard.all()
        contest_problems = contest.contest_problems.all()
        old_key = contest.key

        contest.pk = None
        contest.is_visible = False
        contest.user_count = 0
        contest.locked_after = None
        contest.key = form.cleaned_data['key']
        with revisions.create_revision(atomic=True):
            contest.save()
            contest.tags.set(tags)
            contest.organizations.set(organizations)
            contest.private_contestants.set(private_contestants)
            contest.view_contest_scoreboard.set(view_contest_scoreboard)
            contest.authors.add(self.request.profile)

            for problem in contest_problems:
                problem.contest = contest
                problem.pk = None
            ContestProblem.objects.bulk_create(contest_problems)

            revisions.set_user(self.request.user)
            revisions.set_comment(_('Cloned contest from %s') % old_key)

        return HttpResponseRedirect(reverse('contest_edit', args=(contest.key,)))

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.can_edit:
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)


class ContestAnnounce(ContestMixin, TitleMixin, SingleObjectFormView):
    title = _('Create contest announcement')
    template_name = 'contest/create-announcement.html'
    form_class = ContestAnnouncementForm

    def form_valid(self, form):
        contest = self.object

        announcement = form.save(commit=False)
        announcement.contest = contest
        announcement.save()
        announcement.send()

        return HttpResponseRedirect(reverse('contest_view', args=(contest.key,)))

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.can_edit:
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)


class ContestAccessDenied(Exception):
    pass


class ContestAccessCodeForm(forms.Form):
    access_code = forms.CharField(max_length=255)

    def __init__(self, *args, **kwargs):
        super(ContestAccessCodeForm, self).__init__(*args, **kwargs)
        self.fields['access_code'].widget.attrs.update({'autocomplete': 'off'})


class ContestJoin(LoginRequiredMixin, ContestMixin, BaseDetailView):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self.ask_for_access_code()

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        try:
            return self.join_contest(request)
        except ContestAccessDenied:
            if request.POST.get('access_code'):
                return self.ask_for_access_code(ContestAccessCodeForm(request.POST))
            else:
                return HttpResponseRedirect(request.path)

    def join_contest(self, request, access_code=None):
        contest = self.object

        if not contest.can_join and not (self.is_editor or self.is_tester):
            return generic_message(request, _('Contest not ongoing'),
                                   _('"%s" is not currently ongoing.') % contest.name)

        profile = request.profile

        if not request.user.is_superuser and contest.banned_users.filter(id=profile.id).exists():
            return generic_message(request, _('Banned from joining'),
                                   _('You have been declared persona non grata for this contest. '
                                     'You are permanently barred from joining this contest.'))

        requires_access_code = (not self.can_edit and contest.access_code and access_code != contest.access_code)
        if contest.ended:
            if requires_access_code:
                raise ContestAccessDenied()

            while True:
                virtual_id = max((ContestParticipation.objects.filter(contest=contest, user=profile)
                                  .aggregate(virtual_id=Max('virtual'))['virtual_id'] or 0) + 1, 1)
                try:
                    participation = ContestParticipation.objects.create(
                        contest=contest, user=profile, virtual=virtual_id,
                        real_start=timezone.now(),
                    )
                # There is obviously a race condition here, so we keep trying until we win the race.
                except IntegrityError:
                    pass
                else:
                    break
        else:
            SPECTATE = ContestParticipation.SPECTATE
            LIVE = ContestParticipation.LIVE
            try:
                participation = ContestParticipation.objects.get(
                    contest=contest, user=profile, virtual=(SPECTATE if self.is_editor or self.is_tester else LIVE),
                )
            except ContestParticipation.DoesNotExist:
                if requires_access_code:
                    raise ContestAccessDenied()

                participation = ContestParticipation.objects.create(
                    contest=contest, user=profile, virtual=(SPECTATE if self.is_editor or self.is_tester else LIVE),
                    real_start=timezone.now(),
                )
            else:
                if participation.ended:
                    participation = ContestParticipation.objects.get_or_create(
                        contest=contest, user=profile, virtual=SPECTATE,
                        defaults={'real_start': timezone.now()},
                    )[0]

        profile.current_contest = participation
        profile.save()
        contest._updating_stats_only = True
        contest.update_user_count()
        return HttpResponseRedirect(reverse('contest_view', args=(contest.key,)))

    def ask_for_access_code(self, form=None):
        contest = self.object
        wrong_code = False
        if form:
            if form.is_valid():
                if form.cleaned_data['access_code'] == contest.access_code:
                    return self.join_contest(self.request, form.cleaned_data['access_code'])
                wrong_code = True
        else:
            form = ContestAccessCodeForm()
        return render(self.request, 'contest/access_code.html', {
            'form': form, 'wrong_code': wrong_code,
            'title': _('Enter access code for "%s"') % contest.name,
        })


class ContestLeave(LoginRequiredMixin, ContestMixin, BaseDetailView):
    def dispatch(self, request, *args, **kwargs):
        if request.method != 'POST':
            return HttpResponseForbidden()

        return super(ContestLeave, self).dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        contest = self.get_object()

        profile = request.profile
        if profile.current_contest is None or profile.current_contest.contest_id != contest.id:
            return generic_message(request, _('No such contest'),
                                   _('You are not in contest "%s".') % contest.key, 404)

        profile.remove_contest()
        return HttpResponseRedirect(reverse('contest_view', args=(contest.key,)))


ContestDay = namedtuple('ContestDay', 'date weekday is_pad is_today starts ends oneday')


class ContestCalendar(TitleMixin, ContestListMixin, TemplateView):
    firstweekday = SUNDAY
    weekday_classes = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']
    template_name = 'contest/calendar.html'

    def get(self, request, *args, **kwargs):
        try:
            self.year = int(kwargs['year'])
            self.month = int(kwargs['month'])
        except (KeyError, ValueError):
            raise ImproperlyConfigured(_('ContestCalendar requires integer year and month'))
        self.today = timezone.now().date()
        return self.render()

    def render(self):
        context = self.get_context_data()
        return self.render_to_response(context)

    def get_contest_data(self, start, end):
        end += timedelta(days=1)
        contests = self.get_queryset().filter(Q(start_time__gte=start, start_time__lt=end) |
                                              Q(end_time__gte=start, end_time__lt=end))
        starts, ends, oneday = (defaultdict(list) for i in range(3))
        for contest in contests:
            start_date = timezone.localtime(contest.start_time).date()
            end_date = timezone.localtime(contest.end_time - timedelta(seconds=1)).date()
            if start_date == end_date:
                oneday[start_date].append(contest)
            else:
                starts[start_date].append(contest)
                ends[end_date].append(contest)
        return starts, ends, oneday

    def get_table(self):
        calendar = Calendar(self.firstweekday).monthdatescalendar(self.year, self.month)
        starts, ends, oneday = self.get_contest_data(make_aware(datetime.combine(calendar[0][0], time.min)),
                                                     make_aware(datetime.combine(calendar[-1][-1], time.min)))
        return [[ContestDay(
            date=date, weekday=self.weekday_classes[weekday], is_pad=date.month != self.month,
            is_today=date == self.today, starts=starts[date], ends=ends[date], oneday=oneday[date],
        ) for weekday, date in enumerate(week)] for week in calendar]

    def get_context_data(self, **kwargs):
        context = super(ContestCalendar, self).get_context_data(**kwargs)

        try:
            month = date(self.year, self.month, 1)
        except ValueError:
            raise Http404()
        else:
            context['title'] = _('Contests in %(month)s') % {'month': date_filter(month, _('F Y'))}

        dates = Contest.objects.aggregate(min=Min('start_time'), max=Max('end_time'))
        min_month = (self.today.year, self.today.month)
        if dates['min'] is not None:
            min_month = dates['min'].year, dates['min'].month
        max_month = (self.today.year, self.today.month)
        if dates['max'] is not None:
            max_month = max((dates['max'].year, dates['max'].month), (self.today.year, self.today.month))

        month = (self.year, self.month)
        if month < min_month or month > max_month:
            # 404 is valid because it merely declares the lack of existence, without any reason
            raise Http404()

        context['now'] = timezone.now()
        context['calendar'] = self.get_table()
        context['curr_month'] = date(self.year, self.month, 1)

        if month > min_month:
            context['prev_month'] = date(self.year - (self.month == 1), 12 if self.month == 1 else self.month - 1, 1)
        else:
            context['prev_month'] = None

        if month < max_month:
            context['next_month'] = date(self.year + (self.month == 12), 1 if self.month == 12 else self.month + 1, 1)
        else:
            context['next_month'] = None
        return context


class ContestICal(TitleMixin, ContestListMixin, BaseListView):
    def generate_ical(self):
        cal = ICalendar()
        cal.add('prodid', '-//DMOJ//NONSGML Contests Calendar//')
        cal.add('version', '2.0')

        now = timezone.now().astimezone(timezone.utc)
        domain = self.request.get_host()
        for contest in self.get_queryset():
            event = Event()
            event.add('uid', f'contest-{contest.key}@{domain}')
            event.add('summary', contest.name)
            event.add('location', self.request.build_absolute_uri(contest.get_absolute_url()))
            event.add('dtstart', contest.start_time.astimezone(timezone.utc))
            event.add('dtend', contest.end_time.astimezone(timezone.utc))
            event.add('dtstamp', now)
            cal.add_component(event)
        return cal.to_ical()

    def render_to_response(self, context, **kwargs):
        return HttpResponse(self.generate_ical(), content_type='text/calendar')


class ContestStats(TitleMixin, ContestMixin, DetailView):
    template_name = 'contest/stats.html'

    def get_title(self):
        return _('%s Statistics') % self.object.name

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not self.object.can_see_full_submission_list(self.request.user):
            raise Http404()

        queryset = Submission.objects.filter(contest_object=self.object, date__gt=self.object.start_time)

        ac_count = Count(Case(When(result='AC', then=Value(1)), output_field=IntegerField()))
        ac_rate = CombinedExpression(ac_count / Count('problem'), '*', Value(100.0), output_field=FloatField())

        status_count_queryset = list(
            queryset.values('problem__code', 'result').annotate(count=Count('result'))
                    .values_list('problem__code', 'result', 'count'),
        )
        labels, codes = [], []
        contest_problems = self.object.contest_problems.order_by('order').values_list('problem__name', 'problem__code')
        if contest_problems:
            labels, codes = zip(*contest_problems)
        num_problems = len(labels)
        status_counts = [[] for i in range(num_problems)]
        for problem_code, result, count in status_count_queryset:
            if problem_code in codes:
                status_counts[codes.index(problem_code)].append((result, count))

        result_data = defaultdict(partial(list, [0] * num_problems))
        for i in range(num_problems):
            for category in _get_result_data(defaultdict(int, status_counts[i]))['categories']:
                result_data[category['code']][i] = category['count']

        stats = {
            'problem_status_count': get_stacked_bar_chart(
                labels, result_data, settings.DMOJ_STATS_SUBMISSION_RESULT_COLORS,
            ),
            'problem_ac_rate': get_bar_chart(
                queryset.values('contest__problem__order', 'problem__name').annotate(ac_rate=ac_rate)
                        .order_by('contest__problem__order').values_list('problem__name', 'ac_rate'),
            ),
            'language_count': get_pie_chart(
                queryset.values('language__name').annotate(count=Count('language__name'))
                        .filter(count__gt=0).order_by('-count').values_list('language__name', 'count'),
            ),
            'language_ac_rate': get_bar_chart(
                queryset.values('language__name').annotate(ac_rate=ac_rate)
                        .filter(ac_rate__gt=0).values_list('language__name', 'ac_rate'),
            ),
        }

        context['stats'] = mark_safe(json.dumps(stats))

        return context


ContestRankingProfile = namedtuple(
    'ContestRankingProfile',
    'id user css_class username points cumtime tiebreaker organization participation '
    'participation_rating problem_cells result_cell virtual display_name',
)

BestSolutionData = namedtuple('BestSolutionData', 'code points time state is_pretested')


def make_contest_ranking_profile(contest, participation, contest_problems, frozen=False):
    def display_user_problem(contest_problem):
        # When the contest format is changed, `format_data` might be invalid.
        # This will cause `display_user_problem` to error, so we display '???' instead.
        try:
            return contest.format.display_user_problem(participation, contest_problem, frozen)
        except (KeyError, TypeError, ValueError):
            return mark_safe('<td>???</td>')

    user = participation.user
    return ContestRankingProfile(
        id=user.id,
        user=user.user,
        css_class=user.css_class,
        username=user.username,
        points=participation.score if not frozen else participation.frozen_score,
        cumtime=participation.cumtime if not frozen else participation.frozen_cumtime,
        tiebreaker=participation.tiebreaker if not frozen else participation.frozen_tiebreaker,
        organization=user.organization,
        participation_rating=participation.rating.rating if hasattr(participation, 'rating') else None,
        problem_cells=[display_user_problem(contest_problem) for contest_problem in contest_problems],
        result_cell=contest.format.display_participation_result(participation, frozen),
        participation=participation,
        virtual=participation.virtual,
        display_name=user.display_name,
    )


def base_contest_ranking_list(contest, problems, queryset, frozen=False):
    return [make_contest_ranking_profile(contest, participation, problems, frozen) for participation in
            queryset.select_related('user__user', 'rating').defer('user__about', 'user__organizations__about')]


def base_contest_ranking_queryset(contest):
    return contest.users.filter(virtual__gt=ContestParticipation.SPECTATE) \
        .prefetch_related(Prefetch('user__organizations',
                                   queryset=Organization.objects.filter(is_unlisted=False))) \
        .annotate(submission_count=Count('submission')) \
        .order_by('is_disqualified', '-score', 'cumtime', 'tiebreaker', '-submission_count')


def base_contest_frozen_ranking_queryset(contest):
    return contest.users.filter(virtual__gt=ContestParticipation.SPECTATE) \
        .prefetch_related(Prefetch('user__organizations',
                                   queryset=Organization.objects.filter(is_unlisted=False))) \
        .annotate(submission_count=Count('submission')) \
        .order_by('is_disqualified', '-frozen_score', 'frozen_cumtime', 'frozen_tiebreaker', '-submission_count')


def contest_ranking_list(contest, problems, frozen=False):
    return base_contest_ranking_list(contest, problems, base_contest_ranking_queryset(contest), frozen=frozen)


def get_contest_ranking_list(request, contest, participation=None, ranking_list=contest_ranking_list, ranker=ranker):
    problems = list(contest.contest_problems.select_related('problem').defer('problem__description').order_by('order'))
    users = ranker(ranking_list(contest, problems), key=attrgetter('points', 'cumtime', 'tiebreaker'))

    return users, problems


def contest_ranking_ajax(request, contest, participation=None):
    contest, exists = _find_contest(request, contest)
    if not exists:
        return HttpResponseBadRequest('Invalid contest', content_type='text/plain')

    if not contest.can_see_full_scoreboard(request.user):
        raise Http404()

    is_frozen = contest.is_frozen and not contest.is_editable_by(request.user)

    if is_frozen:
        queryset = base_contest_frozen_ranking_queryset(contest)
    else:
        queryset = base_contest_ranking_queryset(contest)

    queryset = queryset.filter(virtual=ContestParticipation.LIVE)

    users, problems = get_contest_ranking_list(
        request, contest, participation,
        ranking_list=partial(base_contest_ranking_list, queryset=queryset, frozen=is_frozen),
    )

    return render(request, 'contest/ranking-table.html', {
        'users': users,
        'problems': problems,
        'contest': contest,
        'has_rating': contest.ratings.exists(),
        'is_frozen': is_frozen,
        'is_ICPC_format': contest.format.name == ICPCContestFormat.name,
        'perms': PermWrapper(request.user),
        'can_edit': contest.is_editable_by(request.user),
    })


class ContestRankingBase(ContestMixin, TitleMixin, DetailView):
    template_name = 'contest/ranking.html'
    ranking_table_template_name = 'contest/ranking-table.html'
    tab = None

    def get_title(self):
        raise NotImplementedError()

    def get_content_title(self):
        return self.object.name

    def get_ranking_list(self):
        raise NotImplementedError()

    @property
    def is_frozen(self):
        return False

    def get_rendered_ranking_table(self):
        users, problems = self.get_ranking_list()

        return loader.render_to_string(self.ranking_table_template_name, request=self.request, context={
            'users': users,
            'problems': problems,
            'contest': self.object,
            'has_rating': self.object.ratings.exists(),
            'is_frozen': self.is_frozen,
            'perms': PermWrapper(self.request.user),
            'can_edit': self.can_edit,
            'is_ICPC_format': (self.object.format.name == ICPCContestFormat.name),
        })

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not self.object.can_see_own_scoreboard(self.request.user):
            raise Http404()

        context['rendered_ranking_table'] = self.get_rendered_ranking_table()
        context['tab'] = self.tab
        return context


class ContestRanking(ContestRankingBase):
    tab = 'ranking'
    show_virtual = False

    def get_title(self):
        return _('%s Rankings') % self.object.name

    @cached_property
    def is_frozen(self):
        return self.object.is_frozen and not self.can_edit

    @property
    def cache_key(self):
        return f'contest_ranking_cache_{self.object.key}_{self.show_virtual}_{self.is_frozen}'

    @property
    def bypass_cache_ranking(self):
        return self.object.scoreboard_cache_timeout == 0 or self.can_edit

    def get_ranking_queryset(self):
        if self.is_frozen:
            queryset = base_contest_frozen_ranking_queryset(self.object)
        else:
            queryset = base_contest_ranking_queryset(self.object)
        if not self.show_virtual:
            queryset = queryset.filter(virtual=ContestParticipation.LIVE)
        return queryset

    def get_ranking_list(self):
        if not self.object.can_see_full_scoreboard(self.request.user):
            queryset = self.object.users.filter(user=self.request.profile, virtual=ContestParticipation.LIVE)
            return get_contest_ranking_list(
                self.request, self.object,
                ranking_list=partial(base_contest_ranking_list, queryset=queryset),
                ranker=lambda users, key: ((_('???'), user) for user in users),
            )

        if 'show_virtual' in self.request.GET:
            self.show_virtual = self.request.session['show_virtual'] \
                              = self.request.GET.get('show_virtual').lower() == 'true'
        else:
            self.show_virtual = self.request.session.get('show_virtual', False)

        queryset = self.get_ranking_queryset()

        return get_contest_ranking_list(
            self.request, self.object,
            ranking_list=partial(base_contest_ranking_list, queryset=queryset, frozen=self.is_frozen),
        )

    def get_rendered_ranking_table(self):
        if self.bypass_cache_ranking:
            return super().get_rendered_ranking_table()

        rendered_ranking_table = cache.get(self.cache_key, None)
        if rendered_ranking_table is None:
            rendered_ranking_table = super().get_rendered_ranking_table()
            cache.set(self.cache_key, rendered_ranking_table, self.object.scoreboard_cache_timeout)

        return rendered_ranking_table

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['has_rating'] = self.object.ratings.exists()
        context['show_virtual'] = self.show_virtual
        context['is_frozen'] = self.is_frozen
        context['cache_timeout'] = 0 if self.bypass_cache_ranking else self.object.scoreboard_cache_timeout
        return context


class ContestOfficialRanking(ContestRankingBase):
    template_name = 'contest/official-ranking.html'
    ranking_table_template_name = 'contest/official-ranking-table.html'
    tab = 'official_ranking'

    def get_title(self):
        return _('%s Official Rankings') % self.object.name

    def get_ranking_list(self):
        def display_points(points):
            return format_html(
                u'<td class="user-points">{points}</td>',
                points=floatformat(points),
            )

        users, problems = parse_csv_ranking(self.object.csv_ranking)

        for user in users:
            user['result_cell'] = display_points(user['total_score'])
            user['problem_cells'] = [display_points(points) for points in user['scores']]

        users = list(zip(range(1, len(users) + 1), users))

        return users, problems

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['has_rating'] = False
        return context


class ContestParticipationList(LoginRequiredMixin, ContestRankingBase):
    tab = 'participation'

    def get_title(self):
        if self.profile == self.request.profile:
            return _('Your participation in %s') % self.object.name
        return _("%s's participation in %s") % (self.profile.username, self.object.name)

    def get_ranking_list(self):
        if not self.object.can_see_full_scoreboard(self.request.user) and self.profile != self.request.profile:
            raise Http404()

        queryset = self.object.users.filter(user=self.profile, virtual__gte=0).order_by('-virtual')
        live_link = format_html('<a href="{2}#!{1}">{0}</a>', _('Live'), self.profile.username,
                                reverse('contest_ranking', args=[self.object.key]))

        return get_contest_ranking_list(
            self.request, self.object,
            ranking_list=partial(base_contest_ranking_list, queryset=queryset),
            ranker=lambda users, key: ((user.participation.virtual or live_link, user) for user in users))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['has_rating'] = False
        context['now'] = timezone.now()
        context['rank_header'] = _('Participation')
        return context

    def get(self, request, *args, **kwargs):
        if 'user' in kwargs:
            self.profile = get_object_or_404(Profile, user__username=kwargs['user'])
        else:
            self.profile = self.request.profile
        return super().get(request, *args, **kwargs)


class ContestParticipationDisqualify(ContestMixin, SingleObjectMixin, View):
    def get_object(self, queryset=None):
        contest = super().get_object(queryset)
        if not contest.is_editable_by(self.request.user):
            raise Http404()
        return contest

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        try:
            participation = self.object.users.get(pk=request.POST.get('participation'))
        except ObjectDoesNotExist:
            pass
        else:
            participation.set_disqualified(not participation.is_disqualified)
        return HttpResponseRedirect(reverse('contest_ranking', args=(self.object.key,)))


class ContestMossMixin(ContestMixin, PermissionRequiredMixin):
    permission_required = 'judge.moss_contest'

    def get_object(self, queryset=None):
        contest = super().get_object(queryset)
        if settings.MOSS_API_KEY is None or not contest.is_editable_by(self.request.user):
            raise Http404()
        return contest


class ContestMossView(ContestMossMixin, TitleMixin, DetailView):
    template_name = 'contest/moss.html'

    def get_title(self):
        return _('%s MOSS Results') % self.object.name

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        problems = list(map(attrgetter('problem'), self.object.contest_problems.order_by('order')
                                                              .select_related('problem')))
        languages = list(map(itemgetter(0), ContestMoss.LANG_MAPPING))

        results = ContestMoss.objects.filter(contest=self.object)
        moss_results = defaultdict(list)
        for result in results:
            moss_results[result.problem].append(result)

        for result_list in moss_results.values():
            result_list.sort(key=lambda x: languages.index(x.language))

        context['languages'] = languages
        context['has_results'] = results.exists()
        context['moss_results'] = [(problem, moss_results[problem]) for problem in problems]

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        status = run_moss.delay(self.object.key)
        return redirect_to_task_status(
            status, message=_('Running MOSS for %s...') % (self.object.name,),
            redirect=reverse('contest_moss', args=(self.object.key,)),
        )


class ContestMossDelete(ContestMossMixin, SingleObjectMixin, View):
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        ContestMoss.objects.filter(contest=self.object).delete()
        return HttpResponseRedirect(reverse('contest_moss', args=(self.object.key,)))


class ContestTagDetailAjax(DetailView):
    model = ContestTag
    slug_field = slug_url_kwarg = 'name'
    context_object_name = 'tag'
    template_name = 'contest/tag-ajax.html'


class ContestTagDetail(TitleMixin, ContestTagDetailAjax):
    template_name = 'contest/tag.html'

    def get_title(self):
        return _('Contest tag: %s') % self.object.name


class CreateContest(PermissionRequiredMixin, TitleMixin, CreateView):
    template_name = 'contest/create.html'
    model = Contest
    form_class = ContestForm
    permission_required = 'judge.add_contest'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_title(self):
        return _('Create new contest')

    def get_content_title(self):
        return _('Create new contest')

    def get_contest_problem_formset(self):
        if self.request.POST:
            return ProposeContestProblemFormSet(self.request.POST)
        return ProposeContestProblemFormSet()

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data['contest_problem_formset'] = self.get_contest_problem_formset()
        return data

    def save_contest_form(self, form):
        self.object = form.save()
        self.object.authors.add(self.request.profile)
        self.object.save()

    def post(self, request, *args, **kwargs):
        self.object = None
        form = ContestForm(request.POST or None)
        form_set = self.get_contest_problem_formset()
        if form.is_valid() and form_set.is_valid():
            with revisions.create_revision(atomic=True):
                self.save_contest_form(form)
                for problem in form_set.save(commit=False):
                    problem.contest = self.object
                    problem.save()

                revisions.set_comment(_('Created on site'))
                revisions.set_user(self.request.user)
            on_new_contest.delay(self.object.key)
            return HttpResponseRedirect(self.get_success_url())
        else:
            return self.render_to_response(self.get_context_data(*args, **kwargs))


class EditContest(ContestMixin, TitleMixin, UpdateView):
    template_name = 'contest/edit.html'
    model = Contest
    form_class = ContestForm

    def get_object(self, queryset=None):
        contest = super(EditContest, self).get_object(queryset)
        if not contest.is_editable_by(self.request.user):
            raise PermissionDenied()
        return contest

    def get_form_kwargs(self):
        kwargs = super(EditContest, self).get_form_kwargs()
        # Due to some limitation with query set in select2
        # We only support this if the contest is private for only
        # 1 organization
        if self.object.organizations.count() == 1:
            kwargs['org_pk'] = self.object.organizations.values_list('pk', flat=True)[0]

        kwargs['user'] = self.request.user
        return kwargs

    def get_title(self):
        return _('Editing contest {0}').format(self.object.name)

    def get_content_title(self):
        return mark_safe(escape(_('Editing contest %s')) % (
            format_html('<a href="{1}">{0}</a>', self.object.name,
                        reverse('contest_view', args=[self.object.key]))))

    def get_contest_problem_formset(self):
        if self.request.POST:
            return ProposeContestProblemFormSet(self.request.POST, instance=self.get_object())
        return ProposeContestProblemFormSet(instance=self.get_object())

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data['contest_problem_formset'] = self.get_contest_problem_formset()
        return data

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        form_set = self.get_contest_problem_formset()

        if form.is_valid() and form_set.is_valid():
            with revisions.create_revision(atomic=True):
                form.save()
                problems = form_set.save(commit=False)

                for problem in form_set.deleted_objects:
                    problem.delete()

                for problem in problems:
                    problem.contest = self.object
                    problem.save()

                revisions.set_comment(_('Edited from site'))
                revisions.set_user(self.request.user)

            return HttpResponseRedirect(self.get_success_url())
        else:
            return self.render_to_response(self.get_context_data(object=self.object))
