from functools import cached_property

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.models import Group
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.db.models import Count, FilteredRelation, Q
from django.db.models.expressions import F, Value
from django.db.models.functions import Coalesce
from django.forms import Form, modelformset_factory
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext as _, gettext_lazy, ngettext
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView, View
from django.views.generic.detail import SingleObjectMixin, SingleObjectTemplateResponseMixin
from reversion import revisions

from judge.forms import OrganizationForm
from judge.models import BlogPost, Comment, Contest, Language, Organization, OrganizationRequest, \
    Problem, Profile
from judge.models.profile import OrganizationMonthlyUsage
from judge.tasks import on_new_problem
from judge.utils.infinite_paginator import InfinitePaginationMixin
from judge.utils.ranker import ranker
from judge.utils.stats import get_lines_chart
from judge.utils.views import DiggPaginatorMixin, QueryStringSortMixin, TitleMixin, generic_message
from judge.views.blog import BlogPostCreate, PostListBase
from judge.views.contests import ContestList, CreateContest
from judge.views.problem import ProblemCreate, ProblemList
from judge.views.submission import SubmissionsListBase

__all__ = ['OrganizationList', 'OrganizationHome', 'OrganizationUsers', 'OrganizationMembershipChange',
           'JoinOrganization', 'LeaveOrganization', 'EditOrganization', 'RequestJoinOrganization',
           'OrganizationRequestDetail', 'OrganizationRequestView', 'OrganizationRequestLog',
           'KickUserWidgetView']


class OrganizationMixin(object):
    model = Organization

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['organization'] = self.organization
        context['logo_override_image'] = self.organization.logo_override_image
        context['meta_description'] = self.organization.about[:settings.DESCRIPTION_MAX_LENGTH]
        return context

    @cached_property
    def organization(self):
        return get_object_or_404(Organization, slug=self.kwargs['slug'])

    def dispatch(self, request, *args, **kwargs):
        if 'slug' not in kwargs:
            raise ImproperlyConfigured('Must pass a slug')

        try:
            self.object = self.organization

            # block the user from viewing other orgs in the subdomain
            if self.is_in_organization_subdomain() and self.organization.pk != self.request.organization.pk:
                return generic_message(request, _('Cannot view other organizations'),
                                       _('You cannot view other organizations'), status=403)

            return super(OrganizationMixin, self).dispatch(request, *args, **kwargs)
        except Http404:
            slug = kwargs.get('slug', None)
            if slug:
                return generic_message(request, _('No such organization'),
                                       _('Could not find an organization with the key "%s".') % slug)
            else:
                return generic_message(request, _('No such organization'),
                                       _('Could not find such organization.'))

    def can_edit_organization(self, org=None):
        if org is None:
            org = self.organization
        if not self.request.user.is_authenticated:
            return False
        return org.is_admin(self.request.profile) or self.request.user.has_perm('judge.edit_all_organization')

    def is_in_organization_subdomain(self):
        return hasattr(self.request, 'organization')


# Use this mixin to mark a view is public for all users, including non-members
class PublicOrganizationMixin(OrganizationMixin):
    pass


# Use this mixin to mark a view is private for members only
class PrivateOrganizationMixin(OrganizationMixin):
    # If the user has at least one of the following permissions,
    # they can access the private data even if they are not in the org
    permission_bypass = []

    # Override this method to customize the permission check
    def can_access_this_view(self):
        if self.request.user.is_authenticated:
            if self.request.profile in self.organization:
                return True
            if any(self.request.user.has_perm(perm) for perm in self.permission_bypass):
                return True
        return False

    def generate_error_message(self, request):
        return generic_message(request,
                               _("Cannot view organization's private data"),
                               _('You must join the organization to view its private data.'))

    def dispatch(self, request, *args, **kwargs):
        if not self.can_access_this_view():
            return self.generate_error_message(request)

        return super(PrivateOrganizationMixin, self).dispatch(request, *args, **kwargs)


# Use this mixin to ensure that the user is an admin of the organization
class AdminOrganizationMixin(PrivateOrganizationMixin):
    def can_access_this_view(self):
        return self.can_edit_organization()

    def generate_error_message(self, request):
        return generic_message(request, _("Can't edit organization"),
                               _('You are not allowed to edit this organization.'), status=403)


class BaseOrganizationListView(PublicOrganizationMixin, ListView):
    model = None
    context_object_name = None

    def get_object(self, queryset=None):
        if queryset is None:
            return self.organization
        return super(BaseOrganizationListView, self).get_object(queryset)


class OrganizationList(TitleMixin, ListView):
    model = Organization
    context_object_name = 'organizations'
    template_name = 'organization/list.html'
    title = gettext_lazy('Organizations')

    def get_queryset(self):
        return Organization.objects.filter(is_unlisted=False)


class OrganizationUsers(QueryStringSortMixin, DiggPaginatorMixin, BaseOrganizationListView):
    template_name = 'organization/users.html'
    all_sorts = frozenset(('points', 'problem_count', 'rating', 'performance_points'))
    default_desc = all_sorts
    default_sort = '-performance_points'
    paginate_by = 100
    context_object_name = 'users'

    def get_queryset(self):
        return self.object.members.filter(is_unlisted=False).order_by(self.order) \
            .select_related('user', 'display_badge').defer('about', 'user_script', 'notes')

    def get_context_data(self, **kwargs):
        context = super(OrganizationUsers, self).get_context_data(**kwargs)
        if not self.is_in_organization_subdomain():
            context['title'] = self.organization.name
        else:
            context['title'] = _('Members')
        context['users'] = ranker(context['users'])
        context['partial'] = True
        context['is_admin'] = self.can_edit_organization()
        context['kick_url'] = reverse('organization_user_kick', args=[self.object.slug])
        context['first_page_href'] = '.'
        context.update(self.get_sort_context())
        context.update(self.get_sort_paginate_context())
        return context


class OrganizationMembershipChange(LoginRequiredMixin, PublicOrganizationMixin, SingleObjectMixin, View):
    def post(self, request, *args, **kwargs):
        org = self.get_object()
        response = self.handle(request, org, request.profile)
        if response is not None:
            return response
        return HttpResponseRedirect(org.get_absolute_url())

    def handle(self, request, org, profile):
        raise NotImplementedError()


class JoinOrganization(OrganizationMembershipChange):
    def handle(self, request, org, profile):
        if profile.organizations.filter(id=org.id).exists():
            return generic_message(request, _('Joining organization'), _('You are already in the organization.'))

        if not org.is_open:
            return generic_message(request, _('Joining organization'), _('This organization is not open.'))

        max_orgs = settings.DMOJ_USER_MAX_ORGANIZATION_COUNT
        if profile.organizations.filter(is_open=True).count() >= max_orgs:
            return generic_message(
                request, _('Joining organization'),
                ngettext('You may not be part of more than {count} public organization.',
                         'You may not be part of more than {count} public organizations.',
                         max_orgs).format(count=max_orgs),
            )

        profile.organizations.add(org)
        profile.save()


class LeaveOrganization(OrganizationMembershipChange):
    def handle(self, request, org, profile):
        if not profile.organizations.filter(id=org.id).exists():
            return generic_message(request, _('Leaving organization'), _('You are not in "%s".') % org.short_name)
        if org.is_admin(profile):
            return generic_message(request, _('Leaving organization'), _('You cannot leave an organization you own.'))
        profile.organizations.remove(org)


class OrganizationRequestForm(Form):
    reason = forms.CharField(widget=forms.Textarea)


class RequestJoinOrganization(LoginRequiredMixin, SingleObjectMixin, FormView):
    model = Organization
    template_name = 'organization/requests/request.html'
    form_class = OrganizationRequestForm

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.requests.filter(user=self.request.profile, state='P').exists():
            return generic_message(self.request, _("Can't request to join %s") % self.object.name,
                                   _('You already have a pending request to join %s.') % self.object.name)
        return super(RequestJoinOrganization, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(RequestJoinOrganization, self).get_context_data(**kwargs)
        if self.object.is_open:
            raise Http404()
        context['title'] = _('Request to join %s') % self.object.name
        return context

    def form_valid(self, form):
        request = OrganizationRequest()
        request.organization = self.get_object()
        request.user = self.request.profile
        request.reason = form.cleaned_data['reason']
        request.state = 'P'
        request.save()
        return HttpResponseRedirect(reverse('request_organization_detail', args=(
            request.organization.slug, request.id,
        )))


class OrganizationRequestDetail(LoginRequiredMixin, TitleMixin, DetailView):
    model = OrganizationRequest
    template_name = 'organization/requests/detail.html'
    title = gettext_lazy('Join request detail')
    pk_url_kwarg = 'rpk'

    def get_object(self, queryset=None):
        object = super(OrganizationRequestDetail, self).get_object(queryset)
        profile = self.request.profile
        if object.user_id != profile.id and not object.organization.is_admin(profile):
            raise PermissionDenied()
        return object


OrganizationRequestFormSet = modelformset_factory(OrganizationRequest, extra=0, fields=('state',), can_delete=True)


class OrganizationRequestBaseView(LoginRequiredMixin, SingleObjectTemplateResponseMixin, SingleObjectMixin, View):
    model = Organization
    tab = None

    def get_object(self, queryset=None):
        organization = super(OrganizationRequestBaseView, self).get_object(queryset)
        if not organization.is_admin(self.request.profile):
            raise PermissionDenied()
        return organization

    def get_requests(self):
        queryset = self.object.requests.select_related('user__user').defer(
            'user__about', 'user__notes', 'user__user_script',
        ).order_by('-id')
        return queryset

    def get_context_data(self, **kwargs):
        context = super(OrganizationRequestBaseView, self).get_context_data(**kwargs)
        context['title'] = _('Managing join requests for %s') % self.object.name
        context['content_title'] = format_html(_('Managing join requests for %s') %
                                               ' <a href="{1}">{0}</a>', self.object.name,
                                               self.object.get_absolute_url())
        context['tab'] = self.tab
        return context


class OrganizationRequestView(OrganizationRequestBaseView):
    template_name = 'organization/requests/pending.html'
    tab = 'pending'

    def get_context_data(self, **kwargs):
        context = super(OrganizationRequestView, self).get_context_data(**kwargs)
        context['formset'] = self.formset
        return context

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.formset = OrganizationRequestFormSet(queryset=self.get_requests())
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_requests(self):
        return super().get_requests().filter(state='P')

    def post(self, request, *args, **kwargs):
        self.object = organization = self.get_object()
        self.formset = formset = OrganizationRequestFormSet(request.POST, request.FILES, queryset=self.get_requests())
        if formset.is_valid():
            if organization.slots is not None:
                deleted_set = set(formset.deleted_forms)
                to_approve = sum(form.cleaned_data['state'] == 'A' for form in formset.forms if form not in deleted_set)
                can_add = organization.slots - organization.members.count()
                if to_approve > can_add:
                    msg1 = ngettext('Your organization can only receive %d more member.',
                                    'Your organization can only receive %d more members.', can_add) % can_add
                    msg2 = ngettext('You cannot approve %d user.',
                                    'You cannot approve %d users.', to_approve) % to_approve
                    messages.error(request, msg1 + '\n' + msg2)
                    return self.render_to_response(self.get_context_data(object=organization))

            approved, rejected = 0, 0
            for obj in formset.save():
                if obj.state == 'A':
                    obj.user.organizations.add(obj.organization)
                    approved += 1
                elif obj.state == 'R':
                    rejected += 1
            messages.success(request,
                             ngettext('Approved %d user.', 'Approved %d users.', approved) % approved + '\n' +
                             ngettext('Rejected %d user.', 'Rejected %d users.', rejected) % rejected)
            return HttpResponseRedirect(request.get_full_path())
        return self.render_to_response(self.get_context_data(object=organization))

    put = post


class OrganizationRequestLog(OrganizationRequestBaseView):
    states = ('A', 'R')
    tab = 'log'
    template_name = 'organization/requests/log.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super(OrganizationRequestLog, self).get_context_data(**kwargs)
        context['requests'] = self.get_requests().filter(state__in=self.states)
        return context


class CreateOrganization(PermissionRequiredMixin, TitleMixin, CreateView):
    template_name = 'organization/edit.html'
    model = Organization
    form_class = OrganizationForm
    permission_required = 'judge.add_organization'

    def get_title(self):
        return _('Create new organization')

    def form_valid(self, form):
        with revisions.create_revision(atomic=True):
            revisions.set_comment(_('Created on site'))
            revisions.set_user(self.request.user)

            self.object = org = form.save()
            # slug is show in url
            # short_name is show in ranking
            org.short_name = org.slug[:20]
            org.save()
            all_admins = org.admins.all()
            g = Group.objects.get(name=settings.GROUP_PERMISSION_FOR_ORG_ADMIN)
            for admin in all_admins:
                admin.user.groups.add(g)

            return HttpResponseRedirect(self.get_success_url())

    def dispatch(self, request, *args, **kwargs):
        if self.has_permission():
            if self.request.user.profile.admin_of.count() >= settings.VNOJ_ORGANIZATION_ADMIN_LIMIT and \
               not self.request.user.has_perm('spam_organization'):
                return render(request, 'organization/create-limit-error.html', {
                    'admin_of': self.request.user.profile.admin_of.all(),
                    'admin_limit': settings.VNOJ_ORGANIZATION_ADMIN_LIMIT,
                    'title': _("Can't create organization"),
                }, status=403)
            return super(CreateOrganization, self).dispatch(request, *args, **kwargs)
        else:
            return generic_message(request, _("Can't create organization"),
                                   _('You are not allowed to create new organizations.'), status=403)


class EditOrganization(LoginRequiredMixin, TitleMixin, AdminOrganizationMixin, UpdateView):
    template_name = 'organization/edit.html'
    model = Organization
    form_class = OrganizationForm

    def get_title(self):
        return _('Editing %s') % self.object.name

    def get_object(self, queryset=None):
        object = super(EditOrganization, self).get_object()
        if not self.can_edit_organization(object):
            raise PermissionDenied()
        return object

    def form_valid(self, form):
        with revisions.create_revision(atomic=True):
            revisions.set_comment(_('Edited from site'))
            revisions.set_user(self.request.user)
            return super(EditOrganization, self).form_valid(form)


class KickUserWidgetView(LoginRequiredMixin, AdminOrganizationMixin, SingleObjectMixin, View):
    def post(self, request, *args, **kwargs):
        organization = self.organization

        try:
            user = Profile.objects.get(id=request.POST.get('user', None))
        except Profile.DoesNotExist:
            return generic_message(request, _("Can't kick user"),
                                   _('The user you are trying to kick does not exist!'), status=400)

        if not organization.members.filter(id=user.id).exists():
            return generic_message(request, _("Can't kick user"),
                                   _('The user you are trying to kick is not in organization: %s') %
                                   organization.name, status=400)

        if organization.admins.filter(id=user.id).exists():
            return generic_message(request, _("Can't kick user"),
                                   _('The user you are trying to kick is an admin of organization: %s.') %
                                   organization.name, status=400)

        organization.members.remove(user)
        return HttpResponseRedirect(organization.get_users_url())


# using PublicOrganizationMixin to allow user to view org's public information
# like name, request join org, ...
# However, they cannot see the organization private blog
class OrganizationHome(TitleMixin, PublicOrganizationMixin, PostListBase):
    template_name = 'organization/home.html'

    def get_queryset(self):
        queryset = BlogPost.objects.filter(organization=self.organization)

        if not self.request.user.has_perm('judge.edit_all_post'):
            if not self.can_edit_organization():
                if self.request.profile in self.object:
                    # Normal user can only view public posts
                    queryset = queryset.filter(publish_on__lte=timezone.now(), visible=True)
                else:
                    # User cannot view organization blog
                    # if they are not in the org
                    # even if the org is public
                    return BlogPost.objects.none()
            else:
                # Org admin can view public posts & their own posts
                queryset = queryset.filter(Q(visible=True) | Q(authors=self.request.profile))

        if self.request.user.is_authenticated:
            profile = self.request.profile
            queryset = queryset.annotate(
                my_vote=FilteredRelation('votes', condition=Q(votes__voter_id=profile.id)),
            ).annotate(vote_score=Coalesce(F('my_vote__score'), Value(0)))

        return queryset.order_by('-sticky', '-publish_on').prefetch_related('authors__user')

    def get_context_data(self, **kwargs):
        context = super(OrganizationHome, self).get_context_data(**kwargs)
        context['page_prefix'] = reverse('organization_home', args=[self.object.slug]) + '/'
        context['first_page_href'] = reverse('organization_home', args=[self.object.slug])
        context['title'] = self.object.name
        context['can_edit'] = self.can_edit_organization()
        context['is_member'] = self.request.profile in self.object

        context['post_comment_counts'] = {
            int(page[2:]): count for page, count in
            Comment.objects
                   .filter(page__in=['b:%d' % post.id for post in context['posts']], hidden=False)
                   .values_list('page').annotate(count=Count('page')).order_by()
        }

        if not self.object.is_open:
            context['num_requests'] = OrganizationRequest.objects.filter(
                state='P',
                organization=self.object).count()

        user = self.request.user
        if context['is_member'] or \
           user.has_perm('judge.see_organization_problem') or \
           user.has_perm('judge.edit_all_problem'):
            context['new_problems'] = Problem.objects.filter(
                is_public=True, is_organization_private=True,
                organizations=self.object) \
                .order_by('-date', '-id')[:settings.DMOJ_BLOG_NEW_PROBLEM_COUNT]

        see_private_contest = user.has_perm('judge.see_private_contest') or user.has_perm('judge.edit_all_contest')
        if context['is_member'] or see_private_contest:
            new_contests = Contest.objects.filter(
                is_visible=True, is_organization_private=True,
                organizations=self.object) \
                .order_by('-end_time', '-id')

            if not see_private_contest:
                _filter = Q(is_private=False)
                if user.is_authenticated:
                    _filter |= Q(private_contestants=user.profile)
                new_contests = new_contests.filter(_filter)

            context['new_contests'] = new_contests[:settings.DMOJ_BLOG_NEW_PROBLEM_COUNT]

        return context


class ProblemListOrganization(PrivateOrganizationMixin, ProblemList):
    context_object_name = 'problems'
    template_name = 'organization/problem-list.html'
    permission_bypass = ['judge.see_organization_problem', 'judge.edit_all_problem']

    def get_hot_problems(self):
        return None

    def get_context_data(self, **kwargs):
        context = super(ProblemListOrganization, self).get_context_data(**kwargs)
        if not self.is_in_organization_subdomain():
            context['title'] = self.organization.name
        return context

    def get_filter(self):
        """Get filter for visible problems in an organization

        The logic of this is:
            - If user has perm `see_private_problem`, they
            can view all org's problem (including private problems)
            - Otherwise, they can view all public problems and
            problems that they are authors/curators/testers

        With that logic, Organization admins cannot view private
        problems of other admins unless they are authors/curators/testers
        """
        if self.request.user.has_perm('judge.see_private_problem'):
            return Q(organizations=self.organization)

        _filter = Q(is_public=True)

        # Authors, curators, and testers should always have access, so OR at the very end.
        if self.profile is not None:
            _filter |= Q(authors=self.profile)
            _filter |= Q(curators=self.profile)
            _filter |= Q(testers=self.profile)

        return _filter & Q(organizations=self.organization)


class MonthlyCreditUsageOrganization(TitleMixin, PublicOrganizationMixin, ListView):
    model = OrganizationMonthlyUsage
    template_name = 'organization/usage.html'
    context_object_name = 'usages'

    def get_queryset(self):
        return OrganizationMonthlyUsage.objects.filter(organization=self.organization)\
            .order_by('time').values('time', 'consumed_credit')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.organization.name

        usages = context['usages']
        days = [usage['time'].isoformat() for usage in usages] + [_('Current month')]
        used_credits = [usage['consumed_credit'] for usage in usages] + [self.organization.current_consumed_credit]
        sec_per_hour = 60 * 60
        chart = get_lines_chart(days, {
            _('Credit usage (hour)'): [
                round(credit / sec_per_hour, 2) for credit in used_credits
            ],
        })

        cost_chart = get_lines_chart(days, {
            _('Cost (thousand vnd)'): [
                round(
                    max(0, credit - settings.VNOJ_MONTHLY_FREE_CREDIT) / sec_per_hour * settings.VNOJ_PRICE_PER_HOUR, 3,
                ) for credit in used_credits
            ],
        })

        monthly_credit = int(self.organization.monthly_credit)

        context['monthly_credit'] = {
            'hour': monthly_credit // sec_per_hour,
            'minute': (monthly_credit % sec_per_hour) // 60,
            'second': monthly_credit % 60,
        }

        available_credit = int(self.organization.available_credit)

        context['available_credit'] = {
            'hour': available_credit // sec_per_hour,
            'minute': (available_credit % sec_per_hour) // 60,
            'second': available_credit % 60,
        }

        context['credit_chart'] = chart
        context['cost_chart'] = cost_chart
        return context


class ContestListOrganization(PrivateOrganizationMixin, ContestList):
    template_name = 'organization/contest-list.html'
    permission_bypass = ['judge.see_private_contest', 'judge.edit_all_contest']
    hide_private_contests = None

    def _get_queryset(self):
        query_set = super(ContestListOrganization, self)._get_queryset()
        query_set = query_set.filter(is_organization_private=True, organizations=self.organization)
        return query_set

    def get_context_data(self, **kwargs):
        context = super(ContestListOrganization, self).get_context_data(**kwargs)
        if not self.is_in_organization_subdomain():
            context['title'] = self.organization.name
        return context


class SubmissionListOrganization(InfinitePaginationMixin, PrivateOrganizationMixin, SubmissionsListBase):
    template_name = 'organization/submission-list.html'
    permission_bypass = ['judge.view_all_submission']

    def _get_queryset(self):
        query_set = super(SubmissionListOrganization, self)._get_queryset()
        query_set = query_set.filter(problem__organizations=self.organization)
        return query_set

    def get_context_data(self, **kwargs):
        context = super(SubmissionListOrganization, self).get_context_data(**kwargs)
        if not self.is_in_organization_subdomain():
            context['title'] = self.organization.name
            context['content_title'] = self.organization.name
        return context


class ProblemCreateOrganization(AdminOrganizationMixin, ProblemCreate):
    permission_required = 'judge.create_organization_problem'

    def get_initial(self):
        initial = super(ProblemCreateOrganization, self).get_initial()
        initial = initial.copy()
        initial['code'] = ''.join(x for x in self.organization.slug.lower() if x.isalnum()) + '_'
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['org_pk'] = self.organization.pk
        return kwargs

    def form_valid(self, form):
        with revisions.create_revision(atomic=True):
            self.object = problem = form.save()
            problem.authors.add(self.request.user.profile)
            problem.allowed_languages.set(Language.objects.filter(include_in_problem=True))

            problem.is_organization_private = True
            problem.organizations.add(self.organization)
            problem.date = timezone.now()
            self.save_statement(form, problem)
            problem.save()

            revisions.set_comment(_('Created on site'))
            revisions.set_user(self.request.user)

        on_new_problem.delay(problem.code)
        return HttpResponseRedirect(self.get_success_url())


class BlogPostCreateOrganization(AdminOrganizationMixin, PermissionRequiredMixin, BlogPostCreate):
    permission_required = 'judge.edit_organization_post'

    def get_initial(self):
        initial = super(BlogPostCreateOrganization, self).get_initial()
        initial = initial.copy()
        initial['publish_on'] = timezone.now()
        return initial

    def form_valid(self, form):
        with revisions.create_revision(atomic=True):
            post = form.save()
            post.authors.add(self.request.user.profile)
            post.slug = ''.join(x for x in self.organization.slug.lower() if x.isalnum())  # Initial post slug
            post.organization = self.organization
            post.save()

            revisions.set_comment(_('Created on site'))
            revisions.set_user(self.request.user)

        return HttpResponseRedirect(post.get_absolute_url())


class ContestCreateOrganization(AdminOrganizationMixin, CreateContest):
    permission_required = 'judge.create_private_contest'

    def get_initial(self):
        initial = super(ContestCreateOrganization, self).get_initial()
        initial = initial.copy()
        initial['key'] = ''.join(x for x in self.organization.slug.lower() if x.isalnum()) + '_'
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['org_pk'] = self.organization.pk
        return kwargs

    def save_contest_form(self, form):
        self.object = form.save()
        self.object.authors.add(self.request.profile)
        self.object.is_organization_private = True
        self.object.organizations.add(self.organization)
        self.object.save()
