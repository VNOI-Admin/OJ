from random import randrange

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError
from django.db.models import Prefetch, Q
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _, gettext_lazy
from django.views.generic import FormView, ListView, View
from requests.exceptions import ReadTimeout
from reversion import revisions

from judge.comments import CommentedDetailView
from judge.forms import TagProblemAssignForm, TagProblemCreateForm
from judge.models import Tag, TagData, TagGroup, TagProblem
from judge.tasks import on_new_tag, on_new_tag_problem
from judge.utils.diggpaginator import DiggPaginator
from judge.utils.judge_api import APIError, OJAPI
from judge.utils.views import SingleObjectFormView, TitleMixin, generic_message, paginate_query_context


class TagAllowingMixin(object):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or (not request.profile.can_tag_problems):
            return generic_message(request, _('Cannot tag'),
                                   _('You are not allowed to tag problem.'))
        return super(TagAllowingMixin, self).dispatch(request, *args, **kwargs)


class TagProblemMixin(object):
    model = TagProblem
    slug_url_kwarg = 'tagproblem'
    slug_field = 'code'

    def get_object(self, queryset=None):
        problem = super(TagProblemMixin, self).get_object(queryset)
        return problem

    def no_such_problem(self):
        code = self.kwargs.get(self.slug_url_kwarg, None)
        return generic_message(self.request, _('No such problem'),
                               _('Could not find a problem with the code "%s".') % code, status=404)

    def get(self, request, *args, **kwargs):
        try:
            return super(TagProblemMixin, self).get(request, *args, **kwargs)
        except Http404:
            return self.no_such_problem()


class TagProblemList(TitleMixin, ListView):
    model = TagProblem
    title = gettext_lazy('Tag problem list')
    context_object_name = 'tagproblems'
    template_name = 'tag/list.html'
    paginate_by = 50
    paginator_class = DiggPaginator

    def get_queryset(self):
        self.tag_id = None
        self.search_query = None
        self.selected_judges = []

        queryset = TagProblem.objects.order_by('code').prefetch_related('tag')

        if 'tag_id' in self.request.GET:
            self.tag_id = self.request.GET.get('tag_id')
            if self.tag_id:
                queryset = queryset.filter(tag__code=self.tag_id)

        if 'search' in self.request.GET:
            self.search_query = ' '.join(self.request.GET.getlist('search')).strip()
            if self.search_query:
                queryset = queryset.filter(Q(code__icontains=self.search_query) | Q(name__icontains=self.search_query))

        if 'judge' in self.request.GET:
            try:
                self.selected_judges = self.request.GET.getlist('judge')
            except ValueError:
                pass

            if self.selected_judges:
                queryset = queryset.filter(judge__in=self.selected_judges)

        return queryset

    def get_tag_context(self):
        # Clear tag_id and page but keep everything else
        query = self.request.GET.copy()
        query.pop('tag_id', None)
        query.pop('page', None)
        query = query.urlencode()
        return {'tag_prefix': query}

    def get_context_data(self, **kwargs):
        context = super(TagProblemList, self).get_context_data(**kwargs)
        context['selected_tag'] = self.tag_id
        context['search_query'] = self.search_query
        context['groups'] = TagGroup.objects.prefetch_related('tags').all()
        context['judges'] = settings.OJ_LIST
        context['selected_judges'] = self.selected_judges

        context.update(self.get_tag_context())
        context.update(paginate_query_context(self.request))

        return context


class TagRandomProblem(TagProblemList):
    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        count = queryset.count()
        if not count:
            return HttpResponseRedirect('%s%s%s' % (reverse('tagproblem_list'), request.META['QUERY_STRING'] and '?',
                                                    request.META['QUERY_STRING']))
        return HttpResponseRedirect(queryset[randrange(count)].get_absolute_url())


class TagFindProblem(View):
    def get(self, request, *args, **kwargs):
        problem_url = self.request.GET.get('problem_url')
        if not problem_url:
            return HttpResponseRedirect(reverse('tagproblem_list'))

        try:
            problem_data = OJAPI.get_problem_data(problem_url)
        except APIError:
            return HttpResponseRedirect(reverse('tagproblem_list'))

        try:
            problem = TagProblem.objects.get(code=problem_data['codename'])
            return HttpResponseRedirect(problem.get_absolute_url())
        except TagProblem.DoesNotExist:
            return HttpResponseRedirect('%s?problem_url=%s' % (reverse('tagproblem_create'), problem_url))


class TagProblemCreate(LoginRequiredMixin, TagAllowingMixin, TitleMixin, FormView):
    title = gettext_lazy('Create new tag problem')
    template_name = 'tag/create.html'
    form_class = TagProblemCreateForm

    def get_form_kwargs(self):
        kwargs = super(TagProblemCreate, self).get_form_kwargs()
        kwargs['problem_url'] = self.request.GET.get('problem_url')
        return kwargs

    def form_valid(self, form):
        try:
            url = form.cleaned_data.get('problem_url')
            problem_data = OJAPI.get_problem_data(url)

            # Check if problem is in database or not
            try:
                problem = TagProblem.objects.get(code=problem_data['codename'])
                return HttpResponseRedirect(problem.get_absolute_url())
            except TagProblem.DoesNotExist:
                pass

            # Retrive API result from cache
            # If cache is empty, request API then store the result
            try:
                API = OJAPI()
                api_method = API.__getattribute__(problem_data['judge'] + 'ProblemAPI')  # Get method based on judge
                api_problem_data = api_method(problem_data['codename'])
            except ReadTimeout:
                raise APIError('Connection timeout')

            # No problem found
            if api_problem_data is None:
                raise APIError('Problem not found in problemset')

            # Initialize model
            with revisions.create_revision(atomic=True):
                problem = TagProblem(code=problem_data['codename'], name=api_problem_data['title'], link=url,
                                     judge=problem_data['judge'])
                problem.save()

                revisions.set_comment(_('Created on site'))
                revisions.set_user(self.request.user)

            on_new_tag_problem.delay(problem_data['codename'])
            return HttpResponseRedirect(problem.get_absolute_url())
        except (APIError, IntegrityError) as e:
            form.add_error('problem_url', e)
            return self.form_invalid(form)


class TagProblemAssign(LoginRequiredMixin, TagAllowingMixin, TagProblemMixin, TitleMixin, SingleObjectFormView):
    template_name = 'tag/assign.html'
    form_class = TagProblemAssignForm

    def get_content_title(self):
        return mark_safe(
            escape(_('Assign new tags for %s')) % format_html(
                '<a href="{0}">{1}</a>',
                self.object.get_absolute_url(),
                self.object.name,
            ),
        )

    def get_title(self):
        return _('Assign new tags for %s') % self.object.name

    def get_context_data(self, **kwargs):
        context = super(TagProblemAssign, self).get_context_data(**kwargs)
        context['groups'] = TagGroup.objects.prefetch_related('tags').all()
        return context

    def form_valid(self, form):
        tags = form.cleaned_data['tags']
        for tag in tags:
            tag = get_object_or_404(Tag, code=tag)
            try:
                with revisions.create_revision(atomic=True):
                    tag_data = TagData(assigner=self.request.profile, problem=self.object, tag=tag)
                    tag_data.save()

                    revisions.set_comment(_('Assigned new tag %s from site') % tag.name)
                    revisions.set_user(self.request.user)
            except IntegrityError:
                pass
        on_new_tag.delay(self.object.code, tags)

        return HttpResponseRedirect(self.object.get_absolute_url())


class TagProblemDetail(TagProblemMixin, TitleMixin, CommentedDetailView):
    context_object_name = 'problem'
    template_name = 'tag/problem.html'

    def get_title(self):
        return self.object.name

    def get_content_title(self):
        return mark_safe(format_html('<a href="{0}">{1}</a>', self.object.link, self.object.name))

    def get_comment_page(self):
        return 't:%s' % self.object.code

    def get_queryset(self):
        queryset = TagData.objects.select_related('tag', 'assigner__user') \
            .only('id', 'problem', 'tag', 'assigner__user__username',
                  'assigner__display_rank', 'assigner__rating')

        return super(TagProblemDetail, self).get_queryset() \
            .prefetch_related(Prefetch('tagdata_set', queryset=queryset))
