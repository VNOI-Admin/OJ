"""
Seek-based list navigation with signed cursor tokens.

A token carries the ordering position of a row, letting a view resume a listing
with a lexicographic predicate (``WHERE id < :position``) instead of ``OFFSET``,
so the cost of a page stops growing with its depth.

``CursorPaginator`` is the token codec: it signs, validates and decodes a
position. ``CursorPaginationMixin`` drives an ordinary ``ListView`` with it.
Callers that build their own SQL can use the codec alone.

The ordering must end in a unique tie-breaker, usually ``id``, otherwise a
position cannot identify a single row.
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from django.core import signing
from django.core.exceptions import BadRequest, FieldDoesNotExist, ImproperlyConfigured, ValidationError
from django.db.models import Q
from django.http import Http404


CURSOR_VERSION = 1
DEFAULT_CURSOR_MAX_AGE = 24 * 60 * 60
DEFAULT_CURSOR_SALT = 'judge.cursor_paginator'


@dataclass(frozen=True)
class Cursor:
    reverse: bool
    position: tuple


def _reverse_ordering(ordering):
    """``('-created', 'uuid')`` -> ``('created', '-uuid')``."""
    def invert(order):
        return order[1:] if order.startswith('-') else '-' + order

    return tuple(invert(order) for order in ordering)


def _seek_filter(ordering, position):
    """Lexicographic "strictly past this position" predicate for ``ordering``.

    For a single field this is just ``id__lt=...``; for a composite ordering it
    expands to the usual ``a < x OR (a = x AND b < y)`` chain.
    """
    query = Q()
    equal_prefix = Q()

    for order, value in zip(ordering, position):
        field_name = order.lstrip('-')
        lookup = 'lt' if order.startswith('-') else 'gt'
        query |= equal_prefix & Q(**{'%s__%s' % (field_name, lookup): value})
        equal_prefix &= Q(**{field_name: value})

    return query


class CursorPaginator:
    """
    Encodes and decodes signed, timestamped cursor tokens for a given ordering.

    ``ordering`` must end with ``unique_field``. For non-unique sorts, include a
    unique tie-breaker, for example ``('-score', '-id')``.

    ``cursor_salt`` scopes a token: tokens signed under one salt are rejected
    under another, so callers can bind a cursor to the filters it was issued for.
    """

    def __init__(
            self,
            model,
            ordering: tuple[str, ...],
            *,
            unique_field='id',
            cursor_max_age=DEFAULT_CURSOR_MAX_AGE,
            cursor_salt=DEFAULT_CURSOR_SALT):
        self.model = model
        self.ordering = tuple(ordering)
        self.unique_field = unique_field
        self.cursor_max_age = cursor_max_age
        self.cursor_salt = cursor_salt

        self._field_names = tuple(item.lstrip('-') for item in self.ordering)
        self._validate_ordering()

    def decode_cursor(self, token: str | None):
        if token is None:
            return None

        try:
            payload = signing.loads(token, salt=self.cursor_salt, max_age=self.cursor_max_age)
            if payload.get('v') != CURSOR_VERSION:
                raise ValueError()

            raw_position = payload['p']
            if not isinstance(raw_position, list) or len(raw_position) != len(self.ordering):
                raise ValueError()
            reverse = payload.get('r', False)
            if not isinstance(reverse, bool):
                raise ValueError()

            position = tuple(
                self._deserialize_value(field_name, value)
                for field_name, value in zip(self._field_names, raw_position)
            )
            if any(value is None for value in position):
                raise ValueError()
            return Cursor(reverse=reverse, position=position)
        except (KeyError, TypeError, ValueError, signing.BadSignature, ValidationError):
            raise BadRequest('Invalid cursor')

    def encode_cursor(self, cursor: Cursor):
        if len(cursor.position) != len(self.ordering):
            raise ValueError('Cursor position must hold one value per ordering field.')

        if any(value is None for value in cursor.position):
            raise ValueError('Cursor positions cannot contain None.')

        payload = {
            'v': CURSOR_VERSION,
            'r': bool(cursor.reverse),
            'p': [
                self._serialize_value(value)
                for value in cursor.position
            ],
        }
        return signing.dumps(payload, salt=self.cursor_salt, compress=True)

    def _serialize_value(self, value):
        if value is None:
            return None
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        if isinstance(value, (Decimal, UUID)):
            return str(value)
        return value

    def _deserialize_value(self, field_name, value):
        if value is None:
            return None

        field = self._model_field(field_name)
        if field is None:
            return value

        return field.to_python(value)

    def _model_field(self, field_name):
        try:
            return self.model._meta.get_field(field_name)
        except (AttributeError, FieldDoesNotExist):
            return None

    def _validate_ordering(self):
        if not self.ordering:
            raise ValueError('Cursor ordering must not be empty.')

        for order in self.ordering:
            if order in ('', '-'):
                raise ValueError('Cursor ordering contains an invalid field.')

        if self._field_names[-1] != self.unique_field:
            raise ValueError('Cursor ordering must end with a unique field.')

        tie_breaker = self._model_field(self.unique_field)
        if tie_breaker is not None and not (tie_breaker.primary_key or tie_breaker.unique):
            raise ValueError('Cursor unique_field must be unique: a tie-breaker that repeats can skip or '
                             'duplicate rows across pages.')

        for field_name in self._field_names:
            if '__' in field_name:
                raise ValueError('Cursor ordering does not support related fields.')
            field = self._model_field(field_name)
            if field is not None and field.null:
                raise ValueError('Cursor ordering does not support nullable fields.')


class CursorPage:
    """Page object for cursor pagination, shaped like ``django.core.paginator.Page``.

    ``number`` is 1 on the first page and 2 everywhere else. Seek pagination cannot
    know a page's true ordinal without counting, and the point of it is to avoid
    counting. It exists so that existing ``page_obj.number == 1`` checks -- live
    submission updates, for instance -- keep working.
    """

    is_cursor = True
    page_range = ()

    def __init__(self, object_list, previous_href=None, next_href=None):
        self.object_list = object_list
        self.previous_href = previous_href
        self.next_href = next_href
        self.number = 1 if previous_href is None else 2

    def __len__(self):
        return len(self.object_list)

    def __iter__(self):
        return iter(self.object_list)

    def __getitem__(self, index):
        return self.object_list[index]

    def has_previous(self):
        return self.previous_href is not None

    def has_next(self):
        return self.next_href is not None

    def has_other_pages(self):
        return self.has_previous() or self.has_next()


class CursorListPaginator:
    """Stand-in for the paginator a ``ListView`` normally supplies.

    Templates only ever read ``per_page`` off it; there is no page count to give.
    """

    def __init__(self, per_page):
        self.per_page = per_page


class CursorPaginationMixin:
    """Seek pagination for a ``ListView``.

    Pagination links are ordinary URLs carrying a ``cursor`` query parameter, so
    pages stay shareable, the back button works, and the list degrades gracefully
    without JavaScript.

    ``cursor_ordering`` must end in a unique field and is applied to the queryset,
    replacing whatever ordering it already carries.
    """

    cursor_ordering = ('-id',)
    cursor_query_param = 'cursor'
    cursor_salt = DEFAULT_CURSOR_SALT

    def get_cursor_salt(self):
        return self.cursor_salt

    def get_cursor_paginator(self, queryset):
        return CursorPaginator(
            model=queryset.model,
            ordering=self.cursor_ordering,
            cursor_salt=self.get_cursor_salt(),
        )

    def get_cursor_href(self, token):
        """Current URL with ``cursor`` swapped out, so filters survive paging."""
        params = self.request.GET.copy()
        params.pop(self.cursor_query_param, None)
        if token is not None:
            params[self.cursor_query_param] = token
        encoded = params.urlencode()
        return '%s?%s' % (self.request.path, encoded) if encoded else self.request.path

    def get_cursor_position(self, instance):
        return tuple(getattr(instance, order.lstrip('-')) for order in self.cursor_ordering)

    def paginate_queryset(self, queryset, page_size):
        # Seeking only works against the ordering the cursor was minted for, and the
        # order_by below would otherwise silently replace whatever the view asked for.
        # A subclass that re-sorts (RankedSubmissions, say) must not inherit this.
        existing = tuple(queryset.query.order_by)
        if existing and existing != tuple(self.cursor_ordering):
            raise ImproperlyConfigured(
                '%s orders by %r but cursor_ordering is %r. Set cursor_ordering to match, '
                'or page this view some other way.'
                % (type(self).__name__, existing, tuple(self.cursor_ordering)),
            )

        paginator = self.get_cursor_paginator(queryset)
        cursor = paginator.decode_cursor(self.request.GET.get(self.cursor_query_param) or None)

        backwards = bool(cursor and cursor.reverse)
        ordering = _reverse_ordering(self.cursor_ordering) if backwards else self.cursor_ordering

        page_queryset = queryset.order_by(*ordering)
        if cursor is not None:
            page_queryset = page_queryset.filter(_seek_filter(ordering, cursor.position))

        # One extra row answers "is there a next page?" without a second query.
        rows = list(page_queryset[:page_size + 1])
        has_more = len(rows) > page_size
        rows = rows[:page_size]
        if backwards:
            rows.reverse()

        if cursor is not None and not rows:
            raise Http404('That page contains no results.')

        if backwards:
            # Arriving from a later page, so there is always something ahead of us.
            has_previous, has_next = has_more, True
        else:
            has_previous, has_next = cursor is not None, has_more

        def href(reverse, instance):
            return self.get_cursor_href(paginator.encode_cursor(Cursor(
                reverse=reverse,
                position=self.get_cursor_position(instance),
            )))

        page = CursorPage(
            object_list=rows,
            previous_href=href(True, rows[0]) if has_previous and rows else None,
            next_href=href(False, rows[-1]) if has_next and rows else None,
        )
        return CursorListPaginator(page_size), page, page.object_list, page.has_other_pages()
