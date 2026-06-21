"""
Cursor pagination helpers for stable, seek-based list navigation.

The paginator requires an ordering that ends in a unique tie-breaker, usually
``id``. This lets us page with lexicographic predicates instead of OFFSET.
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from django.core import signing
from django.core.exceptions import BadRequest, FieldDoesNotExist, ValidationError
from django.db.models import Q
from django.db.models.query import QuerySet


CURSOR_VERSION = 1
DEFAULT_CURSOR_MAX_AGE = 24 * 60 * 60
DEFAULT_CURSOR_SALT = 'judge.cursor_paginator'


def _reverse_ordering(ordering_tuple):
    """
    Given an order_by tuple such as ``('-created', 'uuid')``, reverse the
    ordering and return a new tuple, e.g. ``('created', '-uuid')``.
    """
    def invert(x):
        return x[1:] if x.startswith('-') else '-' + x

    return tuple(invert(item) for item in ordering_tuple)


@dataclass(frozen=True)
class Cursor:
    reverse: bool
    position: tuple


class CursorPaginator:
    """
    QuerySet cursor paginator using signed, timestamped cursor tokens.

    ``ordering`` must end with ``unique_field``. For non-unique sorts, include
    a unique tie-breaker, for example ``('-score', '-id')``.
    """

    def __init__(
            self,
            queryset: QuerySet,
            ordering: tuple[str, ...],
            page_size: int,
            *,
            unique_field='id',
            cursor_max_age=DEFAULT_CURSOR_MAX_AGE,
            cursor_salt=DEFAULT_CURSOR_SALT):
        self.queryset = queryset
        self.ordering = tuple(ordering)
        self.page_size = page_size
        self.unique_field = unique_field
        self.cursor_max_age = cursor_max_age
        self.cursor_salt = cursor_salt

        self._field_names = tuple(item.lstrip('-') for item in self.ordering)
        self._validate_ordering()

    def paginate(self, token):
        self.cursor = self.decode_cursor(token)
        reverse = bool(self.cursor and self.cursor.reverse)
        query_ordering = _reverse_ordering(self.ordering) if reverse else self.ordering

        queryset = self.queryset.order_by(*query_ordering)
        if self.cursor is not None:
            queryset = queryset.filter(self._seek_filter(self.cursor.position, query_ordering))

        results = list(queryset[:self.page_size + 1])
        has_more = len(results) > self.page_size
        self.page = list(results[:self.page_size])

        if reverse:
            self.page.reverse()
            self.has_previous = has_more
            self.has_next = bool(self.page)
        else:
            self.has_next = has_more
            self.has_previous = self.cursor is not None and bool(self.page)

        return self.page, self.get_previous_link(), self.get_next_link()

    def get_next_link(self):
        if not self.has_next:
            return None

        if self.page:
            position = self._get_position_from_instance(self.page[-1])
        elif self.cursor is not None:
            position = self.cursor.position
        else:
            return None

        return self.encode_cursor(Cursor(reverse=False, position=position))

    def get_previous_link(self):
        if not self.has_previous:
            return None

        if self.page:
            position = self._get_position_from_instance(self.page[0])
        elif self.cursor is not None:
            position = self.cursor.position
        else:
            return None

        return self.encode_cursor(Cursor(reverse=True, position=position))

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

    def _seek_filter(self, position, ordering):
        query = Q()
        equal_prefix = Q()

        for order, value in zip(ordering, position):
            if value is None:
                raise ValueError('Cursor positions cannot contain None.')
            field_name = order.lstrip('-')
            lookup = 'lt' if order.startswith('-') else 'gt'
            query |= equal_prefix & Q(**{f'{field_name}__{lookup}': value})
            equal_prefix &= Q(**{field_name: value})

        return query

    def _get_position_from_instance(self, instance):
        position = []
        for field_name in self._field_names:
            if isinstance(instance, dict):
                position.append(instance[field_name])
            else:
                position.append(getattr(instance, field_name))
        return tuple(position)

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
            return self.queryset.model._meta.get_field(field_name)
        except (AttributeError, FieldDoesNotExist):
            return None

    def _validate_ordering(self):
        if self.page_size <= 0:
            raise ValueError('Cursor page size must be positive.')

        if not self.ordering:
            raise ValueError('Cursor ordering must not be empty.')

        for order in self.ordering:
            if order in ('', '-'):
                raise ValueError('Cursor ordering contains an invalid field.')

        if self._field_names[-1] != self.unique_field:
            raise ValueError('Cursor ordering must end with a unique field.')

        for field_name in self._field_names:
            if '__' in field_name:
                raise ValueError('Cursor ordering does not support related fields.')
            field = self._model_field(field_name)
            if field is not None and field.null:
                raise ValueError('Cursor ordering does not support nullable fields.')
