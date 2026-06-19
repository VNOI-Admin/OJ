from functools import cached_property

from django.contrib.admin.views.main import PAGE_VAR
from django.core.paginator import Paginator


# Source - https://stackoverflow.com/a/58929378
# Posted by Paul
# Retrieved 2026-06-19, License - CC BY-SA 4.0
class FastCountPaginator(Paginator):
    """A faster paginator that avoids COUNT(*) by using the requested page
    to generate a synthetic count. Fetches per_page+1 rows to detect
    whether a next page exists.
    """
    use_fast_pagination = True

    def __init__(self, page_number, *args, **kwargs):
        self.page_number = page_number
        super().__init__(*args, **kwargs)

    @cached_property
    def count(self):
        return self.populate_object_list()

    def page(self, page_number):
        page_number = self.validate_number(page_number)
        return self._get_page(self.object_list, page_number, self)

    def populate_object_list(self):
        bottom = self.page_number * self.per_page
        top = bottom + self.per_page + 1
        object_list = list(self.object_list[bottom:top])
        if len(object_list) == self.per_page + 1:
            object_list = object_list[:-1]
        else:
            top = bottom + len(object_list)
        self.object_list = object_list
        return top


class AdminFastPaginationMixin:
    show_full_result_count = False
    list_max_show_all = 1

    def changelist_view(self, request, extra_context=None):
        request.GET = request.GET.copy()
        request.GET.paginator_count_all = request.GET.pop('count_all', False)
        return super().changelist_view(request, extra_context)

    def get_paginator(self, request, queryset, per_page, orphans=0, allow_empty_first_page=True):
        if getattr(request.GET, 'paginator_count_all', False):
            return Paginator(queryset, per_page, orphans, allow_empty_first_page)
        page = self._get_page_number(request.GET.get(PAGE_VAR, '0'))
        return FastCountPaginator(page, queryset, per_page, orphans, allow_empty_first_page)

    @staticmethod
    def _get_page_number(number):
        try:
            number = int(number)
        except (TypeError, ValueError):
            return 0
        return max(number, 0)
