"""
Signed cursor tokens for stable, seek-based list navigation.

A token carries the ordering position of a row, letting a view resume a listing
with a lexicographic predicate (``WHERE id < :position``) instead of ``OFFSET``.
Building and running that predicate is the caller's job; this module only
encodes, signs, and validates the position.

The ordering must end in a unique tie-breaker, usually ``id``, otherwise a
position cannot identify a single row.
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from django.core import signing
from django.core.exceptions import BadRequest, FieldDoesNotExist, ValidationError


CURSOR_VERSION = 1
DEFAULT_CURSOR_MAX_AGE = 24 * 60 * 60
DEFAULT_CURSOR_SALT = 'judge.cursor_paginator'


@dataclass(frozen=True)
class Cursor:
    reverse: bool
    position: tuple


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
