import datetime
import itertools
import json
import os
from operator import attrgetter, itemgetter

import pytz
from django.conf import settings
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Permission, User
from django.contrib.auth.views import LoginView, PasswordChangeView, PasswordResetView, redirect_to_login
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db.models import Count, F, FilteredRelation, Max, Min, Prefetch, Q
from django.db.models.expressions import Value
from django.db.models.fields import DateField
from django.db.models.functions import Cast, Coalesce, ExtractYear
from django.forms import Form
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.formats import date_format
from django.utils.functional import cached_property
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _, gettext_lazy
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, FormView, ListView, TemplateView, View
from reversion import revisions

from judge.forms import CustomAuthenticationForm, ProfileForm, UserBanForm, UserDownloadDataForm, UserForm, \
    newsletter_id
from judge.models import BlogPost, Organization, Profile, Submission
from judge.models import Comment
from judge.performance_points import get_pp_breakdown
from judge.ratings import rating_class, rating_progress
from judge.tasks import prepare_user_data
from judge.utils.celery import task_status_by_id, task_status_url_by_id
from judge.utils.infinite_paginator import InfinitePaginationMixin
from judge.utils.problems import contest_completed_ids, user_completed_ids
from judge.utils.pwned import PwnedPasswordsValidator
from judge.utils.ranker import ranker
from judge.utils.subscription import Subscription
from judge.utils.unicode import utf8text
from judge.utils.views import DiggPaginatorMixin, QueryStringSortMixin, SingleObjectFormView, TitleMixin, \
    add_file_response, generic_message
from judge.views.blog import PostListBase
from .contests import ContestRanking

__all__ = ['UserPage', 'UserAboutPage', 'UserProblemsPage', 'UserCommentPage', 'UserDownloadData', 'UserPrepareData',
           'users', 'edit_profile']


def remap_keys(iterable, mapping):
    return [dict((mapping.get(k, k), v) for k, v in item.items()) for item in iterable]


class UserMixin(object):
    model = Profile
    slug_field = 'user__username'
    slug_url_kwarg = 'user'
    context_object_name = 'user'

    def render_to_response(self, context, **response_kwargs):
        return super(UserMixin, self).render_to_response(context, **response_kwargs)


# This is almost the same as UserMixin
# However, I need to write a new class because
# the current mixin is for Profile DetailView.
class CustomUserMixin(object):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.user
        return context

    def dispatch(self, request, *args, **kwargs):
        if 'user' not in kwargs:
            raise ImproperlyConfigured('must pass an username')
        self.user = get_object_or_404(Profile, user__username=kwargs['user'])
        self.object = self.user
        return super(CustomUserMixin, self).dispatch(request, *args, **kwargs)


class UserPage(TitleMixin, UserMixin, DetailView):
    template_name = 'user/user-base.html'

    def get_object(self, queryset=None):
        if self.kwargs.get(self.slug_url_kwarg, None) is None:
            return self.request.profile
        return super(UserPage, self).get_object(queryset)

    def dispatch(self, request, *args, **kwargs):
        if self.kwargs.get(self.slug_url_kwarg, None) is None:
            if not self.request.user.is_authenticated:
                return redirect_to_login(self.request.get_full_path())
        try:
            return super(UserPage, self).dispatch(request, *args, **kwargs)
        except Http404:
            return generic_message(request, _('No such user'), _('No user handle "%s".') %
                                   self.kwargs.get(self.slug_url_kwarg, None), status=404)

    def get_title(self):
        return (_('My account') if self.request.user == self.object.user else
                _('User %s') % self.object.display_name)

    # TODO: the same code exists in problem.py, maybe move to problems.py?
    @cached_property
    def profile(self):
        if not self.request.user.is_authenticated:
            return None
        return self.request.profile

    @cached_property
    def in_contest(self):
        return self.profile is not None and self.profile.current_contest is not None

    def get_completed_problems(self):
        if self.in_contest:
            return contest_completed_ids(self.profile.current_contest)
        else:
            return user_completed_ids(self.profile) if self.profile is not None else ()

    def get_context_data(self, **kwargs):
        context = super(UserPage, self).get_context_data(**kwargs)

        context['hide_solved'] = int(self.hide_solved)
        context['authored'] = self.object.authored_problems.filter(is_public=True, is_organization_private=False) \
                                  .select_related('group').order_by('code')
        rating = self.object.ratings.order_by('-contest__end_time')[:1]
        context['rating'] = rating[0] if rating else None

        context['rank'] = Profile.objects.filter(
            is_unlisted=False, performance_points__gt=self.object.performance_points,
        ).exclude(id=self.object.id).count() + 1

        if rating:
            context['rating_rank'] = Profile.objects.filter(
                is_unlisted=False, rating__gt=self.object.rating,
            ).count() + 1
        context.update(self.object.ratings.aggregate(min_rating=Min('rating'), max_rating=Max('rating'),
                                                     contests=Count('contest')))
        return context

    def get(self, request, *args, **kwargs):
        self.hide_solved = request.GET.get('hide_solved') == '1' if 'hide_solved' in request.GET else False
        return super(UserPage, self).get(request, *args, **kwargs)


class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    extra_context = {'title': gettext_lazy('Login')}
    authentication_form = CustomAuthenticationForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super(CustomLoginView, self).get_context_data(**kwargs)
        context['oauth'] = context['form']
        return context

    def form_valid(self, form):
        password = form.cleaned_data['password']
        validator = PwnedPasswordsValidator()
        try:
            validator.validate(password)
        except ValidationError:
            self.request.session['password_pwned'] = True
        else:
            self.request.session['password_pwned'] = False
        return super().form_valid(form)


class CustomPasswordChangeView(PasswordChangeView):
    template_name = 'registration/password_change_form.html'

    def form_valid(self, form):
        self.request.session['password_pwned'] = False
        return super().form_valid(form)


EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)


class UserAboutPage(UserPage):
    template_name = 'user/user-about.html'

    def get_context_data(self, **kwargs):
        context = super(UserAboutPage, self).get_context_data(**kwargs)
        ratings = context['ratings'] = self.object.ratings.order_by('-contest__end_time').select_related('contest') \
            .defer('contest__description')

        context['rating_data'] = mark_safe(json.dumps([{
            'label': rating.contest.name,
            'rating': rating.rating,
            'ranking': rating.rank,
            'link': '%s#!%s' % (reverse('contest_ranking', args=(rating.contest.key,)), self.object.user.username),
            'timestamp': (rating.contest.end_time - EPOCH).total_seconds() * 1000,
            'date': date_format(timezone.localtime(rating.contest.end_time), _('M j, Y, G:i')),
            'class': rating_class(rating.rating),
            'height': '%.3fem' % rating_progress(rating.rating),
        } for rating in ratings]))

        user_timezone = settings.DEFAULT_USER_TIME_ZONE
        if self.request is not None and self.request.profile is not None:
            user_timezone = user_timezone or self.request.profile.timezone
        timezone_offset = pytz.timezone(user_timezone).utcoffset(datetime.datetime.utcnow()).seconds

        submissions = (
            self.object.submission_set
            .annotate(date_only=Cast(F('date') + datetime.timedelta(seconds=timezone_offset), DateField()))
            .values('date_only').annotate(cnt=Count('id'))
        )

        context['submission_data'] = mark_safe(json.dumps({
            date_counts['date_only'].isoformat(): date_counts['cnt'] for date_counts in submissions
        }))
        context['submission_metadata'] = mark_safe(json.dumps({
            'min_year': (
                self.object.submission_set
                .annotate(year_only=ExtractYear('date'))
                .aggregate(min_year=Min('year_only'))['min_year']
            ),
        }))
        return context


class UserBan(UserMixin, TitleMixin, SingleObjectFormView):
    template_name = 'user/ban.html'
    form_class = UserBanForm

    def get_title(self):
        return _('Ban {0}').format(self.object.user.username)

    def form_valid(self, form):
        user = self.object
        with revisions.create_revision(atomic=True):
            user.ban_user(form.cleaned_data['ban_reason'])
            revisions.set_user(self.request.user)
            revisions.set_comment(_('Banned by %s') % self.request.user)

        return HttpResponseRedirect(reverse('user_page', args=(user.user.username,)))

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object.can_be_banned_by(self.request.user):
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)


class UserUnban(UserBan):
    form_class = Form

    def get_title(self):
        return _('Unban {0}').format(self.object.user.username)

    def form_valid(self, form):
        user = self.object
        with revisions.create_revision(atomic=True):
            user.unban_user()
            revisions.set_user(self.request.user)
            revisions.set_comment(_('Unbanned by %s') % self.request.user)

        return HttpResponseRedirect(reverse('user_page', args=(user.user.username,)))


class UserBlogPage(CustomUserMixin, PostListBase):
    template_name = 'user/blog.html'

    def get_queryset(self):
        queryset = BlogPost.objects.filter(authors=self.user, organization=None)

        if self.request.user != self.user.user and not self.request.user.is_superuser:
            queryset = queryset.filter(visible=True, publish_on__lte=timezone.now())

        if self.request.user.is_authenticated:
            profile = self.request.profile
            queryset = queryset.annotate(
                my_vote=FilteredRelation('votes', condition=Q(votes__voter_id=profile.id)),
            ).annotate(vote_score=Coalesce(F('my_vote__score'), Value(0)))

        return queryset.order_by('-sticky', '-publish_on').prefetch_related('authors__user')


class UserCommentPage(CustomUserMixin, DiggPaginatorMixin, ListView):
    template_name = 'user/comment.html'
    model = Comment
    paginate_by = 10
    context_object_name = 'comments'
    title = None

    def get_queryset(self):
        return Comment.get_newest_visible_comments(viewer=self.request.user,
                                                   author=self.user,
                                                   batch=2 * self.paginate_by)

    def get_context_data(self, **kwargs):
        context = super(UserCommentPage, self).get_context_data(**kwargs)
        context['first_page_href'] = None
        context['title'] = self.title or _('Page %d of Comments') % context['page_obj'].number
        context['vote_hide_threshold'] = settings.DMOJ_COMMENT_VOTE_HIDE_THRESHOLD

        if self.request.user.is_authenticated:
            context['is_new_user'] = self.request.profile.is_new_user
            context['interact_min_problem_count_msg'] = \
                _('You need to have solved at least %d problems before your voice can be heard.') \
                % settings.VNOJ_INTERACT_MIN_PROBLEM_COUNT

        return context

    @method_decorator(require_POST)
    def delete_comments(self, request, *args, **kwargs):
        if not request.user.has_perm('judge.change_comment'):
            raise PermissionDenied()

        user_id = User.objects.get(username=kwargs['user']).id
        user = Profile.objects.get(user=user_id)
        for comment in Comment.get_newest_visible_comments(viewer=request.user, author=user,
                                                           batch=2 * self.paginate_by):
            comment.get_descendants(include_self=True).update(hidden=True)
        return HttpResponseRedirect(reverse('user_comment', args=(user.user.username,)))

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm('judge.view_all_user_comment'):
            raise PermissionDenied()
        if request.method == 'POST':
            return self.delete_comments(request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)


class UserProblemsPage(UserPage):
    template_name = 'user/user-problems.html'

    def get_context_data(self, **kwargs):
        context = super(UserProblemsPage, self).get_context_data(**kwargs)

        result = Submission.objects.filter(user=self.object, points__gt=0, problem__is_public=True,
                                           problem__is_organization_private=False) \
            .exclude(problem__in=self.get_completed_problems() if self.hide_solved else []) \
            .values('problem__id', 'problem__code', 'problem__name', 'problem__points', 'problem__group__full_name') \
            .distinct().annotate(points=Max('points')).order_by('problem__group__full_name', 'problem__code')

        def process_group(group, problems_iter):
            problems = list(problems_iter)
            points = sum(map(itemgetter('points'), problems))
            return {'name': group, 'problems': problems, 'points': points}

        context['best_submissions'] = [
            process_group(group, problems) for group, problems in itertools.groupby(
                remap_keys(result, {
                    'problem__code': 'code', 'problem__name': 'name', 'problem__points': 'total',
                    'problem__group__full_name': 'group',
                }), itemgetter('group'))
        ]
        breakdown, has_more = get_pp_breakdown(self.object, start=0, end=10)
        context['pp_breakdown'] = breakdown
        context['pp_has_more'] = has_more

        return context


class UserPerformancePointsAjax(UserProblemsPage):
    template_name = 'user/pp-table-body.html'

    def get_context_data(self, **kwargs):
        context = super(UserPerformancePointsAjax, self).get_context_data(**kwargs)
        try:
            start = int(self.request.GET.get('start', 0))
            end = int(self.request.GET.get('end', settings.DMOJ_PP_ENTRIES))
            if start < 0 or end < 0 or start > end:
                raise ValueError
        except ValueError:
            start, end = 0, 100
        breakdown, self.has_more = get_pp_breakdown(self.object, start=start, end=end)
        context['pp_breakdown'] = breakdown
        return context

    def get(self, request, *args, **kwargs):
        httpresp = super(UserPerformancePointsAjax, self).get(request, *args, **kwargs)
        httpresp.render()

        return JsonResponse({
            'results': utf8text(httpresp.content),
            'has_more': self.has_more,
        })


class UserDataMixin:
    @cached_property
    def data_path(self):
        return os.path.join(settings.DMOJ_USER_DATA_CACHE, '%s.zip' % self.request.profile.id)

    def dispatch(self, request, *args, **kwargs):
        if not settings.DMOJ_USER_DATA_DOWNLOAD or self.request.profile.mute:
            raise Http404()
        return super().dispatch(request, *args, **kwargs)


class UserPrepareData(LoginRequiredMixin, UserDataMixin, TitleMixin, FormView):
    template_name = 'user/prepare-data.html'
    form_class = UserDownloadDataForm

    @cached_property
    def _now(self):
        return timezone.now()

    @cached_property
    def can_prepare_data(self):
        return (
            self.request.profile.data_last_downloaded is None or
            self.request.profile.data_last_downloaded + settings.DMOJ_USER_DATA_DOWNLOAD_RATELIMIT < self._now or
            not os.path.exists(self.data_path)
        )

    @cached_property
    def data_cache_key(self):
        return 'celery_status_id:user_data_download_%s' % self.request.profile.id

    @cached_property
    def in_progress_url(self):
        status_id = cache.get(self.data_cache_key)
        status = task_status_by_id(status_id).status if status_id else None
        return (
            self.build_task_url(status_id)
            if status in ('PENDING', 'PROGRESS', 'STARTED')
            else None
        )

    def build_task_url(self, status_id):
        return task_status_url_by_id(
            status_id, message=_('Preparing your data...'), redirect=reverse('user_prepare_data'),
        )

    def get_title(self):
        return _('Download your data')

    def form_valid(self, form):
        self.request.profile.data_last_downloaded = self._now
        self.request.profile.save()
        status = prepare_user_data.delay(self.request.profile.id, json.dumps(form.cleaned_data))
        cache.set(self.data_cache_key, status.id)
        return HttpResponseRedirect(self.build_task_url(status.id))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_prepare_data'] = self.can_prepare_data
        context['can_download_data'] = os.path.exists(self.data_path)
        context['in_progress_url'] = self.in_progress_url
        context['ratelimit'] = settings.DMOJ_USER_DATA_DOWNLOAD_RATELIMIT

        if not self.can_prepare_data:
            context['time_until_can_prepare'] = (
                settings.DMOJ_USER_DATA_DOWNLOAD_RATELIMIT - (self._now - self.request.profile.data_last_downloaded)
            )
        return context

    def post(self, request, *args, **kwargs):
        if not self.can_prepare_data or self.in_progress_url is not None:
            raise PermissionDenied()
        return super().post(request, *args, **kwargs)


class UserDownloadData(LoginRequiredMixin, UserDataMixin, View):
    def get(self, request, *args, **kwargs):
        if not os.path.exists(self.data_path):
            raise Http404()

        response = HttpResponse()

        if hasattr(settings, 'DMOJ_USER_DATA_INTERNAL'):
            url_path = '%s/%s.zip' % (settings.DMOJ_USER_DATA_INTERNAL, self.request.profile.id)
        else:
            url_path = None
        add_file_response(request, response, url_path, self.data_path)

        response['Content-Type'] = 'application/zip'
        response['Content-Disposition'] = 'attachment; filename=%s-data.zip' % self.request.user.username
        return response


@login_required
def edit_profile(request):
    if request.profile.mute:
        return generic_message(request, _("Can't edit profile"), _('Your part is silent, little toad.'), status=403)
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.profile, user=request.user)
        form_user = UserForm(request.POST, instance=request.user)
        if form.is_valid() and form_user.is_valid():
            with revisions.create_revision(atomic=True):
                form_user.save()
                form.save()
                revisions.set_user(request.user)
                revisions.set_comment(_('Updated on site'))

            if newsletter_id is not None:
                try:
                    subscription = Subscription.objects.get(user=request.user, newsletter_id=newsletter_id)
                except Subscription.DoesNotExist:
                    if form.cleaned_data['newsletter']:
                        Subscription(user=request.user, newsletter_id=newsletter_id, subscribed=True).save()
                else:
                    if subscription.subscribed != form.cleaned_data['newsletter']:
                        subscription.update(('unsubscribe', 'subscribe')[form.cleaned_data['newsletter']])

            perm = Permission.objects.get(codename='test_site', content_type=ContentType.objects.get_for_model(Profile))
            if form.cleaned_data['test_site']:
                request.user.user_permissions.add(perm)
            else:
                request.user.user_permissions.remove(perm)

            return HttpResponseRedirect(request.path)
    else:
        form = ProfileForm(instance=request.profile, user=request.user)
        form_user = UserForm(instance=request.user)
        if newsletter_id is not None:
            try:
                subscription = Subscription.objects.get(user=request.user, newsletter_id=newsletter_id)
            except Subscription.DoesNotExist:
                form.fields['newsletter'].initial = False
            else:
                form.fields['newsletter'].initial = subscription.subscribed
        form.fields['test_site'].initial = request.user.has_perm('judge.test_site')

    return render(request, 'user/edit-profile.html', {
        'require_staff_2fa': settings.DMOJ_REQUIRE_STAFF_2FA, 'form_user': form_user,
        'form': form, 'title': _('Edit profile'), 'profile': request.profile,
        'can_download_data': bool(settings.DMOJ_USER_DATA_DOWNLOAD),
        'has_math_config': bool(settings.MATHOID_URL),
        'ignore_user_script': True,
        'TIMEZONE_MAP': settings.TIMEZONE_MAP,
    })


@require_POST
@login_required
def generate_api_token(request):
    profile = request.profile
    with revisions.create_revision(atomic=True):
        revisions.set_user(request.user)
        revisions.set_comment(_('Generated API token for user'))
        return JsonResponse({'data': {'token': profile.generate_api_token()}})


@require_POST
@login_required
def remove_api_token(request):
    profile = request.profile
    with revisions.create_revision(atomic=True):
        profile.api_token = None
        profile.save()
        revisions.set_user(request.user)
        revisions.set_comment(_('Removed API token for user'))
    return JsonResponse({})


@require_POST
@login_required
def generate_scratch_codes(request):
    profile = request.profile
    with revisions.create_revision(atomic=True):
        revisions.set_user(request.user)
        revisions.set_comment(_('Generated scratch codes for user'))
    return JsonResponse({'data': {'codes': profile.generate_scratch_codes()}})


class UserList(QueryStringSortMixin, InfinitePaginationMixin, DiggPaginatorMixin, TitleMixin, ListView):
    model = Profile
    title = gettext_lazy('Leaderboard')
    context_object_name = 'users'
    template_name = 'user/list.html'
    paginate_by = 100
    all_sorts = frozenset(('points', 'problem_count', 'rating', 'performance_points'))
    default_desc = all_sorts
    default_sort = '-rating'

    def get_queryset(self):
        return (Profile.objects.filter(is_unlisted=False).order_by(self.order, 'id')
                .prefetch_related(Prefetch('user', queryset=User.objects.only('username', 'first_name')))
                .prefetch_related(Prefetch('organizations',
                                  queryset=Organization.objects.filter(is_unlisted=False).only('name', 'id', 'slug')))
                .select_related('display_badge')
                .only('display_rank', 'display_badge', 'user', 'points', 'rating', 'performance_points',
                      'problem_count', 'organizations', 'username_display_override'))

    def get_context_data(self, **kwargs):
        context = super(UserList, self).get_context_data(**kwargs)
        context['users'] = ranker(
            context['users'],
            key=attrgetter('performance_points', 'problem_count'),
            rank=self.paginate_by * (context['page_obj'].number - 1),
        )
        context['first_page_href'] = '.'
        context.update(self.get_sort_context())
        context.update(self.get_sort_paginate_context())
        return context


user_list_view = UserList.as_view()


class ContribList(QueryStringSortMixin, DiggPaginatorMixin, TitleMixin, ListView):
    model = Profile
    title = gettext_lazy('Contributors')
    context_object_name = 'users'
    template_name = 'user/contrib-list.html'
    paginate_by = 100
    all_sorts = frozenset(('contribution_points', ))
    default_desc = all_sorts
    default_sort = '-contribution_points'

    def get_queryset(self):
        return (Profile.objects.filter(is_unlisted=False).order_by(self.order, 'id')
                .prefetch_related(Prefetch('user', queryset=User.objects.only('username', 'first_name')))
                .prefetch_related(Prefetch('organizations',
                                  queryset=Organization.objects.filter(is_unlisted=False).only('name', 'id', 'slug')))
                .select_related('display_badge')
                .only('display_rank', 'display_badge', 'user', 'organizations', 'rating', 'contribution_points',
                      'username_display_override'))

    def get_context_data(self, **kwargs):
        context = super(ContribList, self).get_context_data(**kwargs)
        context['users'] = ranker(
            context['users'],
            key=attrgetter('contribution_points'),
            rank=self.paginate_by * (context['page_obj'].number - 1),
        )
        context['first_page_href'] = '.'
        context.update(self.get_sort_context())
        context.update(self.get_sort_paginate_context())
        return context


contrib_list_view = ContribList.as_view()


class FixedContestRanking(ContestRanking):
    contest = None

    def get_object(self, queryset=None):
        return self.contest


def users(request):
    return user_list_view(request)


def user_ranking_redirect(request):
    try:
        username = request.GET['handle']
    except KeyError:
        raise Http404()
    user = get_object_or_404(Profile, user__username=username)
    # Assume using MySQL. NULL is considered smaller than any non-NULL value.
    if user.rating is None:
        rank = Profile.objects.filter(is_unlisted=False, rating__isnull=False).count()
    else:
        rank = Profile.objects.filter(is_unlisted=False, rating__gt=user.rating).count()
    rank += Profile.objects.filter(
        is_unlisted=False, rating__exact=user.rating, id__lt=user.id,
    ).count()
    page = rank // UserList.paginate_by
    return HttpResponseRedirect('%s%s#!%s' % (reverse('user_list'), '?page=%d' % (page + 1) if page else '', username))


def user_contributor_redirect(request):
    try:
        username = request.GET['handle']
    except KeyError:
        raise Http404()
    user = get_object_or_404(Profile, user__username=username)
    rank = Profile.objects.filter(is_unlisted=False, contribution_points__gt=user.contribution_points).count()
    rank += Profile.objects.filter(
        is_unlisted=False, contribution_points__exact=user.contribution_points, id__lt=user.id,
    ).count()
    page = rank // ContribList.paginate_by
    return HttpResponseRedirect('%s%s#!%s' % (reverse('contributors_list'), '?page=%d' % (page + 1) if page else '',
                                              username))


class UserLogoutView(TitleMixin, TemplateView):
    template_name = 'registration/logout.html'
    title = gettext_lazy('You have been successfully logged out.')

    def post(self, request, *args, **kwargs):
        auth_logout(request)
        return HttpResponseRedirect(request.get_full_path())


class CustomPasswordResetView(PasswordResetView):
    title = gettext_lazy('Password reset')
    from_email = settings.SERVER_EMAIL
    template_name = 'registration/password_reset.html'
    html_email_template_name = 'registration/password_reset_email.html'
    email_template_name = 'registration/password_reset_email.txt'

    def post(self, request, *args, **kwargs):
        key = f'pwreset!{request.META["REMOTE_ADDR"]}'
        cache.add(key, 0, timeout=settings.DMOJ_PASSWORD_RESET_LIMIT_WINDOW)
        if cache.incr(key) > settings.DMOJ_PASSWORD_RESET_LIMIT_COUNT:
            return HttpResponse(_('You have sent too many password reset requests. Please try again later.'),
                                content_type='text/plain', status=429)

        self.extra_email_context = {
            'misc_config': request.misc_config,
        }

        return super().post(request, *args, **kwargs)
