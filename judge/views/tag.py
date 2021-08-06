from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView

from judge.forms import TagProblemCreateForm
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
