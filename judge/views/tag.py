from django.db.utils import ProgrammingError
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, ListView, UpdateView

from judge.comments import CommentedDetailView
from judge.forms import TagProblemCreateForm, TagProblemEditForm
from judge.models import TagGroup, TagProblem
from judge.utils.diggpaginator import DiggPaginator
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


class TagProblemCreate(TitleMixin, CreateView):
    model = TagProblem
    title = _('Creating new tag problem')
    template_name = 'tag/edit.html'
    form_class = TagProblemCreateForm


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
