from judge.utils.raw_sql import join_sql_subquery

class DeferredPaginationMixin:
    def deferred_paginate(self, queryset):
        return queryset

    def paginate_queryset(self, queryset, *args, **kwargs):
        queryset_pks = queryset.values_list('pk', flat=True)
        paginator, page, object_list, has_other = super().paginate_queryset(queryset_pks, *args, **kwargs)

        object_list = queryset.model.objects.all().filter(pk__in=object_list)
        object_list = self.deferred_paginate(object_list)

        page.object_list = object_list
        return paginator, page, object_list, has_other


class DeferredPaginationListViewMixin:
    paginated_model = None

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

            page.object_list = object_list
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
