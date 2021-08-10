from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError
from django.db.utils import ProgrammingError
from django.http import Http404, HttpResponseRedirect
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, ListView

from judge.comments import CommentedDetailView
from judge.forms import TagProblemAddTagForm, TagProblemCreateForm
from judge.models import TagData, TagGroup, TagProblem
from judge.utils.diggpaginator import DiggPaginator
from judge.utils.judge_api import APIError, OJAPI
from judge.utils.views import SingleObjectFormView, TitleMixin, generic_message


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
    title = _('Tag problem list')
    context_object_name = 'tagproblems'
    template_name = 'tag/list.html'
    paginate_by = 50
    paginator_class = DiggPaginator

    def get_queryset(self):
        queryset = TagProblem.objects.order_by('code')

        if self.tag_id is not None:
            queryset = queryset.filter(tag__code=self.tag_id)

        return queryset

    def get_context_data(self, **kwargs):
        context = super(TagProblemList, self).get_context_data(**kwargs)
        context['selected_tag'] = self.tag_id
        context['groups'] = TagGroup.objects.all()

        return context

    def get(self, request, *args, **kwargs):
        self.tag_id = request.GET.get('tag_id', None)

        try:
            return super(TagProblemList, self).get(request, *args, **kwargs)
        except ProgrammingError as e:
            return generic_message(request, 'FTS syntax error', e.args[1], status=400)


class TagProblemCreate(LoginRequiredMixin, TitleMixin, FormView):
    title = _('Create new tag problem')
    template_name = 'tag/create.html'
    form_class = TagProblemCreateForm

    def post(self, request, *args, **kwargs):
        form = TagProblemCreateForm(request.POST or None)
        try:
            if form.is_valid():
                url = form.cleaned_data.get('problem_url')
                problem_data = OJAPI.get_problem_data(url)

                # Check if problem is in database or not
                try:
                    _ = TagProblem.objects.get(code=problem_data['codename'])
                    raise IntegrityError('Problem already existed.')
                except TagProblem.DoesNotExist:
                    pass

                # Retrive API result from cache
                # If cache is empty, request API then store the result
                API = OJAPI()
                api_method = API.__getattribute__(problem_data['judge'] + 'ProblemAPI')  # Get method based on judge
                api_problem_data = api_method(problem_data['codename'])

                # No problem found
                if api_problem_data is None:
                    raise APIError('Problem not found in problemset')

                # Initialize model
                problem = TagProblem(code=problem_data['codename'], name=api_problem_data['title'], link=url)
                problem.save()
                return HttpResponseRedirect(problem.get_absolute_url())
            else:
                form.add_error('problem_url', 'An error occured during problem initialization. Please try again.')
                return self.form_invalid(form)
        except (APIError, IntegrityError) as e:
            form.add_error('problem_url', e)
            return self.form_invalid(form)


class TagProblemAddTag(LoginRequiredMixin, TagProblemMixin, TitleMixin, SingleObjectFormView):
    template_name = 'tag/add-tag.html'
    form_class = TagProblemAddTagForm

    def get_content_title(self):
        return mark_safe(
            escape(_('Add new tag for %s')) % format_html(
                '<a href="{0}">{1}</a>',
                self.object.get_absolute_url(),
                self.object.name,
            ),
        )

    def get_title(self):
        return _('Add new tag for %s') % self.object.name

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = TagData(assigner=self.request.profile, problem=self.object)
        return kwargs

    def form_valid(self, form):
        form.save()
        return HttpResponseRedirect(self.object.get_absolute_url())


class TagProblemDetail(TagProblemMixin, CommentedDetailView):
    context_object_name = 'problem'
    template_name = 'tag/problem.html'

    def get_comment_page(self):
        return 'p:%s' % self.object.code

    def get_context_data(self, **kwargs):
        context = super(TagProblemDetail, self).get_context_data(**kwargs)

        context['title'] = self.object.name
        return context
