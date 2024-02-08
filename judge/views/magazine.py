from judge.utils.views import TitleMixin
from django.views.generic import TemplateView


class MagazinePage(TitleMixin, TemplateView):
    title = 'VNOI Magazine 2024'
    template_name = 'magazine.html'