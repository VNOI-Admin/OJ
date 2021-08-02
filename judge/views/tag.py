from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView

from judge.forms import TagProblemCreateForm, TagProblemEditForm
from judge.models import TagProblem
from judge.utils.views import TitleMixin


class TagProblemCreate(TitleMixin, CreateView):
    template_name = 'tag/edit.html'
    model = TagProblem
    form_class = TagProblemCreateForm

    def get_title(self):
        return _('Creating new tag problem')

    def get_content_title(self):
        return _('Creating new tag problem')

    def post(self, request, *args, **kwargs):
        self.object = None
        form = TagProblemEditForm(request.POST or None, user=request.user)
        if form.is_valid():
            problem = form.save(commit=False)
            print("DEBUG", problem.tag)
            return HttpResponseRedirect(self.get_success_url())
        else:
            return self.form_invalid(form)
