from django.http import Http404
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, UpdateView

from judge.comments import CommentedDetailView
from judge.forms import TagProblemCreateForm, TagProblemEditForm
from judge.models import TagProblem
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


class TagProblemCreate(TitleMixin, CreateView):
    template_name = 'tag/edit.html'
    model = TagProblem
    form_class = TagProblemCreateForm

    def get_title(self):
        return _('Creating new tag problem')

    def get_content_title(self):
        return _('Creating new tag problem')


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
