from django.views.generic import TemplateView

from judge.utils.views import TitleMixin


class MagazinePage(TitleMixin, TemplateView):
    title = 'VNOI Magazine 2024'
    template_name = 'magazine.html'
