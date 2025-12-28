from django.views.generic import ListView

from judge.utils.raw_sql import join_sql_subquery


class DeferredPaginationListView(ListView):
    paginated_model = None

    def deferred_paginate(self, queryset):
        return queryset

    def get_context_data(self, *, object_list=None, **kwargs):
        """Get the context for this view."""
        queryset = object_list if object_list is not None else self.object_list
        page_size = self.get_paginate_by(queryset)
        context_object_name = self.get_context_object_name(queryset)
        if page_size:
            queryset_pks = queryset.values_list('pk', flat=True)
            paginator, page, queryset_pks, is_paginated = self.paginate_queryset(
                queryset_pks, page_size
            )
            query, params = queryset_pks.query.sql_with_params()
            queryset = self.__class__.paginated_model.objects.all()
            join_sql_subquery(
                queryset,
                subquery=query,
                params=list(params),
                join_fields=[('id', 'id')],
                alias='deferred_object',
                related_model=self.__class__.paginated_model,
            )
            queryset = self.deferred_paginate(queryset)
            ordering = self.get_ordering()
            if ordering:
                if isinstance(ordering, str):
                    ordering = (ordering,)
                queryset = queryset.order_by(*ordering)

            page.object_list = queryset
            context = {
                "paginator": paginator,
                "page_obj": page,
                "is_paginated": is_paginated,
                "object_list": queryset,
            }
        else:
            context = {
                "paginator": None,
                "page_obj": None,
                "is_paginated": False,
                "object_list": queryset,
            }
        if context_object_name is not None:
            context[context_object_name] = queryset
        context.update(kwargs)

        context.setdefault("view", self)
        if self.extra_context is not None:
            context.update(self.extra_context)
        return context
