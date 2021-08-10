from django.core.cache import cache
from django.db.utils import ProgrammingError
from django.forms import ModelForm
from django.http import Http404, HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, ListView, UpdateView

from judge.comments import CommentedDetailView
from judge.forms import TagProblemCreateForm
from judge.models import TagGroup, TagProblem
from judge.utils.diggpaginator import DiggPaginator
from judge.utils.judge_api import APIError, OJAPI
from judge.utils.views import TitleMixin, generic_message


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


class TagProblemCreate(TitleMixin, FormView):
    title = _('Creating new tag problem')
    template_name = 'tag/create.html'
    form_class = TagProblemCreateForm

    def post(self, request, *args, **kwargs):
        form = TagProblemCreateForm(request.POST or None)
        try:
            if form.is_valid():
                url = form.cleaned_data.get('problem_url')
                problem_data = OJAPI.get_problem_data(url)

                # Retrive API result from cache
                # If cache is empty, request API then store the result
                cache_loc = 'OJAPI_data_%s'
                problemset = cache.get(cache_loc % problem_data['judge'], None)
                if problemset is None:
                    API = OJAPI()
                    api_method = API.__getattribute__(problem_data['judge'] + 'ProblemAPI')
                    problemset = api_method()
                    cache.set('OJAPI_data_%s' % problem_data['judge'], problemset, timeout=3600)
                    print('cache set')
                api_problem_data = problemset.get(problem_data['codename'], None)
                if api_problem_data is None:
                    raise APIError('Problem not found in problemset')

                # Initialize model
                problem = TagProblem(code=problem_data['codename'], name=api_problem_data['title'], link=url)
                problem.save()

                return HttpResponseRedirect(problem.get_absolute_url())
            else:
                form.add_error('problem_url', 'Cannot initialize problem')
                return self.form_invalid(form)
        except Exception:
            form.add_error('problem_url', 'Cannot initialize problem')
            return self.form_invalid(form)


class TagProblemEditForm(ModelForm):
    class Meta:
        model = TagProblem
        fields = []


class TagProblemDetail(TagProblemMixin, UpdateView, CommentedDetailView):
    context_object_name = 'problem'
    template_name = 'tag/problem.html'
    form_class = TagProblemEditForm

    def get_comment_page(self):
        return 'p:%s' % self.object.code

    def get_context_data(self, **kwargs):
        context = super(TagProblemDetail, self).get_context_data(**kwargs)

        context['title'] = self.object.name
        return context
