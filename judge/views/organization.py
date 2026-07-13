import datetime
from functools import cached_property

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, FilteredRelation, OuterRef, Q, Subquery, Sum
from django.db.models.expressions import F, Value
from django.db.models.functions import Coalesce
from django.forms import Form, modelformset_factory
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.html import format_html
from django.utils.translation import gettext as _, gettext_lazy, ngettext
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView, View
from django.views.generic.detail import SingleObjectMixin, SingleObjectTemplateResponseMixin
from reversion import revisions

from judge.forms import OrganizationForm, QuotaGrantForm
from judge.models import BlogPost, Comment, Contest, Language, Organization, OrganizationRequest, \
    Problem, Profile, Submission
from judge.models.profile import OrganizationMonthlyUsage, OrganizationQuota
from judge.tasks import on_new_problem
from judge.utils.cache_helper import storage_pie_cache_factory
from judge.utils.infinite_paginator import InfinitePaginationMixin
from judge.utils.organization import add_admin_to_group, add_quota_context
from judge.utils.ranker import ranker
from judge.utils.stats import get_lines_chart, get_pie_chart
from judge.utils.views import DiggPaginatorMixin, QueryStringSortMixin, TitleMixin, generic_message, \
    paginate_query_context
from judge.views.blog import BlogPostCreate, PostListBase
from judge.views.contests import ContestList, CreateContest
from judge.views.problem import ProblemCreate, ProblemList
from judge.views.submission import SubmissionsListBase

__all__ = ['OrganizationList', 'OrganizationHome', 'OrganizationUsers', 'OrganizationMembershipChange',
           'JoinOrganization', 'LeaveOrganization', 'EditOrganization', 'RequestJoinOrganization',
           'OrganizationRequestDetail', 'OrganizationRequestView', 'OrganizationRequestLog',
           'KickUserWidgetView', 'OrganizationStorageDashboard',
           'OrganizationQuotaAdd', 'OrganizationQuotaDelete']


MAX_BULK_DELETE_PROBLEMS = 200


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
        return get_object_or_404(Organization.objects.prefetch_related('admins__user'), slug=self.kwargs['slug'])

    def dispatch(self, request, *args, **kwargs):
        try:
            self.object = self.organization

            # block the user from viewing other orgs in the subdomain
            if self.is_in_organization_subdomain() and self.organization.pk != self.request.organization.pk:
                return generic_message(request, _('Cannot view other organizations'),
                                       _('You cannot view other organizations'), status=403)

            return super(OrganizationMixin, self).dispatch(request, *args, **kwargs)
        except Http404:
            return self.organization_not_found(request)

    def organization_not_found(self, request):
        slug = self.kwargs.get('slug', None)
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


class OrganizationByIdMixin(OrganizationMixin):
    @cached_property
    def organization(self):
        return get_object_or_404(Organization, id=self.kwargs['pk'])

    def organization_not_found(self, request):
        pk = self.kwargs.get('pk', None)
        return generic_message(request, _('No such organization'),
                               _('Could not find an organization with ID "%s".') % pk)


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


class OrganizationList(DiggPaginatorMixin, TitleMixin, ListView):
    model = Organization
    context_object_name = 'organizations'
    template_name = 'organization/list.html'
    title = gettext_lazy('Organizations')
    paginate_by = 200

    @cached_property
    def can_manage_organizations(self):
        return self.request.user.has_perm('judge.edit_all_organization')

    def GET_with_session(self, key):
        if key not in self.request.GET:
            return self.request.session.get(key, False)
        return self.request.GET.get(key, None) == '1'

    @cached_property
    def show_all_orgs(self):
        return self.can_manage_organizations and self.GET_with_session('show_all_orgs')

    def get_queryset(self):
        if self.show_all_orgs:
            queryset = Organization.objects.prefetch_related('admins__user')
        else:
            queryset = Organization.objects.filter(is_unlisted=False)

        self.search_query = None
        if self.show_all_orgs and 'search' in self.request.GET:
            self.search_query = search_query = ' '.join(self.request.GET.getlist('search')).strip()
            if search_query:
                queryset = queryset.filter(
                    Q(name__icontains=search_query) |
                    Q(slug__icontains=search_query) |
                    Q(short_name__icontains=search_query) |
                    Q(admins__user__username__icontains=search_query),
                ).distinct()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['show_all_orgs'] = self.show_all_orgs
        context['search_query'] = self.search_query
        context.update(paginate_query_context(self.request))
        if self.request.user.is_authenticated:
            user_organizations = self.request.profile.organizations.all()
            if self.show_all_orgs:
                user_organizations = user_organizations.prefetch_related('admins__user')
            context['user_organizations'] = user_organizations
        return context

    def post(self, request, *args, **kwargs):
        if 'show_all_orgs' in request.GET:
            request.session['show_all_orgs'] = request.GET.get('show_all_orgs') == '1'
        else:
            request.session.pop('show_all_orgs', None)
        return HttpResponseRedirect(request.get_full_path())


class OrganizationUsers(QueryStringSortMixin, DiggPaginatorMixin, BaseOrganizationListView):
    template_name = 'organization/users.html'
    all_sorts = frozenset(('points', 'problem_count', 'rating', 'performance_points'))
    default_desc = all_sorts
    default_sort = '-performance_points'
    paginate_by = 100
    context_object_name = 'users'

    def get_queryset(self):
        return self.object.members.filter(is_unlisted=False).order_by(self.order, 'id') \
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


def org_user_ranking_redirect(request, slug):
    try:
        username = request.GET['handle']
    except KeyError:
        raise Http404()
    user = get_object_or_404(Profile, user__username=username)
    org = get_object_or_404(Organization, slug=slug)
    rank = org.members.filter(is_unlisted=False, performance_points__gt=user.performance_points).count()
    rank += org.members.filter(
        is_unlisted=False, performance_points__exact=user.performance_points, id__lt=user.id,
    ).count()
    page = rank // OrganizationUsers.paginate_by
    return HttpResponseRedirect('%s%s#!%s' % (reverse('organization_users', args=(org.slug,)),
                                              '?page=%d' % (page + 1) if page else '', username))


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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        with revisions.create_revision(atomic=True):
            revisions.set_comment(_('Created on site'))
            revisions.set_user(self.request.user)

            self.object = org = form.save(commit=False)
            # slug is show in url
            # short_name is show in ranking
            org.short_name = org.slug[:20]
            org.free_credit = org.monthly_free_credit_limit
            add_admin_to_group(form)
            # don't need to org.save, the form.save() in `add_admin_to_group` will do it
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.has_perm('judge.add_organizationquota'):
            context['quota_form'] = QuotaGrantForm()
            context['existing_quotas'] = self.organization.quotas.order_by('start_date')
        return context

    def form_valid(self, form):
        with revisions.create_revision(atomic=True):
            revisions.set_comment(_('Edited from site'))
            revisions.set_user(self.request.user)
            add_admin_to_group(form)
            return super(EditOrganization, self).form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request  # Pass the request object to the form
        return kwargs


class OrganizationQuotaAdd(LoginRequiredMixin, AdminOrganizationMixin, View):
    def post(self, request, *args, **kwargs):
        if not request.user.has_perm('judge.add_organizationquota'):
            raise PermissionDenied()
        form = QuotaGrantForm(request.POST)
        if form.is_valid():
            packages = form.cleaned_data['packages']
            OrganizationQuota.objects.create(
                organization=self.organization,
                start_date=form.cleaned_data['start_date'],
                end_date=form.cleaned_data['end_date'],
                added_problems=packages * settings.VNOJ_QUOTA_PACKAGE_PROBLEMS,
                added_storage=packages * settings.VNOJ_QUOTA_PACKAGE_STORAGE,
            )
        return HttpResponseRedirect(reverse('edit_organization', args=[self.organization.slug]))


class OrganizationQuotaDelete(LoginRequiredMixin, AdminOrganizationMixin, View):
    def post(self, request, *args, **kwargs):
        # We use `add_organizationquota` permission to indicate that this user has all edit permissions.
        # I don't want to make this too complex.
        if not request.user.has_perm('judge.add_organizationquota'):
            raise PermissionDenied()
        quota_id = kwargs.get('quota_id')
        OrganizationQuota.objects.filter(id=quota_id, organization=self.organization).delete()
        return HttpResponseRedirect(reverse('edit_organization', args=[self.organization.slug]))


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
                is_public=True,
                organization=self.object) \
                .order_by('-id')[:settings.DMOJ_BLOG_NEW_PROBLEM_COUNT]

        see_private_contest = user.has_perm('judge.see_private_contest') or user.has_perm('judge.edit_all_contest')
        if context['is_member'] or see_private_contest:
            new_contests = Contest.objects.filter(
                is_visible=True,
                organization=self.object) \
                .order_by('-end_time', '-id')

            if not see_private_contest:
                _filter = Q(is_private=False)
                if user.is_authenticated:
                    _filter |= Q(private_contestants=user.profile)
                new_contests = new_contests.filter(_filter)

            context['new_contests'] = new_contests[:settings.DMOJ_BLOG_NEW_PROBLEM_COUNT]

        return context


class OrganizationHomeById(OrganizationByIdMixin, OrganizationHome):
    pass


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
            return Q(organization=self.organization)

        _filter = Q(is_public=True)

        # Authors, curators, and testers should always have access, so OR at the very end.
        if self.profile is not None:
            _filter |= Q(authors=self.profile)
            _filter |= Q(curators=self.profile)
            _filter |= Q(testers=self.profile)

        return _filter & Q(organization=self.organization)


class BulkDeleteOrganizationProblems(LoginRequiredMixin, AdminOrganizationMixin, View):
    def post(self, request, *args, **kwargs):
        org = self.organization
        problem_ids = request.POST.getlist('problem_ids')
        if not problem_ids:
            messages.warning(request, _('No problems selected for deletion.'))
            return HttpResponseRedirect(reverse('organization_monthly_usage', args=[org.slug]))

        if len(problem_ids) > MAX_BULK_DELETE_PROBLEMS:
            messages.error(request, _('Cannot delete more than %d problems at once.') % MAX_BULK_DELETE_PROBLEMS)
            return HttpResponseRedirect(reverse('organization_monthly_usage', args=[org.slug]))

        problems = Problem.available.filter(
            id__in=problem_ids,
            organization=org,
        )

        if not request.user.is_superuser:
            all_count = problems.count()
            problems = problems.filter(Q(authors=request.profile) | Q(curators=request.profile))
            skipped = all_count - problems.count()
            if skipped > 0:
                messages.error(request, ngettext(
                    '%d problem was skipped because you are not its author.',
                    '%d problems were skipped because you are not their author.',
                    skipped,
                ) % skipped)

        count = problems.count()
        if count > 0:
            with revisions.create_revision(atomic=True):
                for problem in problems:
                    problem.mark_as_deleted(invalidate_storage_cache=False)
                revisions.set_user(request.user)
                revisions.set_comment(_('Bulk marked as deleted'))

            storage_pie_cache_factory(org.id).delete_cache()
            messages.success(request, ngettext(
                'Successfully deleted %d problem.',
                'Successfully deleted %d problems.',
                count,
            ) % count)
        else:
            messages.error(request, _('No valid problems could be deleted.'))

        return HttpResponseRedirect(reverse('organization_monthly_usage', args=[org.slug]))


class ContestListOrganization(PrivateOrganizationMixin, ContestList):
    template_name = 'organization/contest-list.html'
    permission_bypass = ['judge.see_private_contest', 'judge.edit_all_contest']
    hide_private_contests = None

    def _get_queryset(self):
        query_set = super(ContestListOrganization, self)._get_queryset()
        query_set = query_set.filter(is_organization_private=True, organization=self.organization)
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
        query_set = query_set.filter(problem__organization=self.organization)
        return query_set

    def get_context_data(self, **kwargs):
        context = super(SubmissionListOrganization, self).get_context_data(**kwargs)
        if not self.is_in_organization_subdomain():
            context['title'] = self.organization.name
            context['content_title'] = self.organization.name
        return context


class ProblemCreateOrganization(AdminOrganizationMixin, ProblemCreate):
    permission_required = 'judge.create_organization_problem'

    def _quota_error_response(self):
        return render(self.request, 'organization/quota-error.html', {
            'title': _('Problem limit reached'),
            'message': _('This organization has reached its maximum number of problems (%d). '
                         'Please delete some problems before creating new ones.')
            % self.organization.max_problems,
            'quota_warning_suffix': settings.VNOJ_QUOTA_WARNING_SUFFIX,
        })

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        add_quota_context(self.organization, context)
        return context

    def get(self, request, *args, **kwargs):
        if settings.VNOJ_QUOTA_ENFORCEMENT_ENABLED and not self.organization.can_create_problem():
            return self._quota_error_response()
        return super().get(request, *args, **kwargs)

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
        if settings.VNOJ_QUOTA_ENFORCEMENT_ENABLED and not self.organization.can_create_problem():
            return self._quota_error_response()
        with revisions.create_revision(atomic=True):
            self.object = problem = form.save()
            problem.authors.add(self.request.user.profile)
            problem.allowed_languages.set(Language.objects.filter(include_in_problem=True))

            problem.is_organization_private = True
            problem.organization = self.organization
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
        self.object.organization = self.organization
        self.object.save()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['contest_org'] = self.organization
        return context


class OrganizationStorageDashboard(LoginRequiredMixin, TitleMixin, AdminOrganizationMixin,
                                   InfinitePaginationMixin, ListView):
    """Dashboard showing storage usage for organization admins."""
    template_name = 'organization/usage.html'
    context_object_name = 'problems'
    paginate_by = MAX_BULK_DELETE_PROBLEMS

    def get_title(self):
        return _('Organization cost - %s') % self.organization.name

    def get_queryset(self):
        queryset = Problem.available.filter(
            organization=self.organization,
        ).annotate(
            data_size=Coalesce(F('data_files__zipfile_size'), Value(0)),
        ).only(
            'code', 'name',
        ).prefetch_related('authors__user', 'curators__user')

        # Annotate with the latest submission date

        last_sub_query = Submission.objects.filter(problem=OuterRef('pk')).order_by('-date').values('date')[:1]
        queryset = queryset.annotate(last_submission_date=Subquery(last_sub_query))

        # Filter by author
        author_id = self.request.GET.get('author')
        if author_id:
            try:
                author_id = int(author_id)
                if self.organization.admins.filter(id=author_id).exists():
                    queryset = queryset.filter(Q(authors__id=author_id) | Q(curators__id=author_id))
            except ValueError:
                pass

        # Filter by last submission time (after / before / never)
        if self.request.GET.get('no_submission'):
            queryset = queryset.filter(last_submission_date__isnull=True)
        else:
            for key, lookup, time_val in [('last_sub_after', '__gte', datetime.time.min),
                                          ('last_sub_before', '__lte', datetime.time.max)]:
                val = self.request.GET.get(key)
                if val:
                    try:
                        date_val = parse_date(val)
                        if date_val:
                            dt_val = timezone.make_aware(datetime.datetime.combine(date_val, time_val))
                            queryset = queryset.filter(**{f'last_submission_date{lookup}': dt_val})
                    except ValueError:
                        pass

        return queryset.order_by('-data_size', 'id')

    def _get_storage_pie_charts(self, now):
        org = self.organization

        def ago(days):
            return now - datetime.timedelta(days=days)

        bucket_ranges = [
            (None, None),
            (ago(365), None),
            (ago(274), ago(365)),
            (ago(183), ago(274)),
            (ago(91), ago(183)),
            (now, ago(91)),
        ]

        cache = storage_pie_cache_factory(org.id)
        raw = cache.get_cache()
        if raw is None:
            all_problems = Problem.available.filter(organization=org).annotate(
                data_size=Coalesce(F('data_files__zipfile_size'), Value(0)),
            )
            last_sub_qs = Submission.objects.filter(
                problem=OuterRef('pk'),
            ).order_by('-date').values('date')[:1]
            all_problems = all_problems.annotate(last_submission_date=Subquery(last_sub_qs))

            raw = []
            for after, before in bucket_ranges:
                if after is None:
                    qs = all_problems.filter(last_submission_date__isnull=True)
                else:
                    filters = {'last_submission_date__lte': after}
                    if before is not None:
                        filters['last_submission_date__gt'] = before
                    qs = all_problems.filter(**filters)
                agg = qs.aggregate(cnt=Count('id'), total=Coalesce(Sum('data_size'), Value(0)))
                raw.append((agg['cnt'], agg['total']))
            cache.set_cache(raw)

        label_threshold = _('Last submission %(months)d+ months ago')
        label_range = _('Last submission %(from)d-%(to)d months ago')
        label_recent = _('Last submission < %(months)d months ago')
        labels = [
            _('No submissions'),
            label_threshold % {'months': 12},
            label_range % {'from': 9, 'to': 12},
            label_range % {'from': 6, 'to': 9},
            label_range % {'from': 3, 'to': 6},
            label_recent % {'months': 3},
        ]

        total_cnt = sum(r[0] for r in raw) or 1
        total_size = sum(r[1] for r in raw) or 1

        count_data, size_data = [], []
        for label, (cnt, size) in zip(labels, raw):
            cnt_pct = round(cnt / total_cnt * 100)
            size_pct = round(size / total_size * 100)
            count_data.append(('{} ({}%, {} {})'.format(label, cnt_pct, cnt, _('problems')), cnt))
            size_data.append(('{} ({}%, {})'.format(label, size_pct, filesizeformat(size)), size))

        return get_pie_chart(count_data), get_pie_chart(size_data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        org = self.organization
        add_quota_context(org, context)

        today = timezone.now()
        context['active_quotas'] = list(
            org.quotas.filter(start_date__lte=today.date(), end_date__gte=today.date()).order_by('end_date'),
        )

        context['storage_count_chart'], context['storage_size_chart'] = self._get_storage_pie_charts(today)

        # Credit/cost chart context (merged from usage page)
        usages = OrganizationMonthlyUsage.objects.filter(organization=org) \
            .order_by('time').values('time', 'consumed_credit')
        context['usages'] = usages
        days = [usage['time'].isoformat() for usage in usages] + [_('Current month')]
        used_credits = [usage['consumed_credit'] for usage in usages] + [org.current_consumed_credit]
        sec_per_hour = 60 * 60
        context['credit_chart'] = get_lines_chart(days, {
            _('Credit usage (hour)'): [round(c / sec_per_hour, 2) for c in used_credits],
        })
        context['cost_chart'] = get_lines_chart(days, {
            _('Cost (thousand vnd)'): [
                round(max(0, c - settings.VNOJ_MONTHLY_FREE_CREDIT) / sec_per_hour * settings.VNOJ_PRICE_PER_HOUR, 3)
                for c in used_credits
            ],
        })
        free_credit = int(org.free_credit)
        context['free_credit'] = {
            'hour': free_credit // sec_per_hour,
            'minute': (free_credit % sec_per_hour) // 60,
            'second': free_credit % 60,
        }
        paid_credit = int(org.paid_credit)
        context['paid_credit'] = {
            'hour': paid_credit // sec_per_hour,
            'minute': (paid_credit % sec_per_hour) // 60,
            'second': paid_credit % 60,
        }

        context['org_admins'] = org.admins.select_related('user')
        context['selected_author'] = self.request.GET.get('author')
        context['last_sub_after'] = self.request.GET.get('last_sub_after')
        context['last_sub_before'] = self.request.GET.get('last_sub_before')

        context.update(paginate_query_context(self.request))

        return context
