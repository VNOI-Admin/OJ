from dataclasses import FrozenInstanceError

from django.core import signing
from django.core.exceptions import BadRequest
from django.test import SimpleTestCase

from judge.models import BlogPost, BlogPostTag
from judge.utils.cursor_paginator import (
    CURSOR_VERSION,
    Cursor,
    CursorPaginator,
    DEFAULT_CURSOR_SALT,
)


class CursorTestCase(SimpleTestCase):
    def test_cursor_creation(self):
        cursor = Cursor(reverse=True, position=(5, 'abc'))
        self.assertIs(cursor.reverse, True)
        self.assertEqual(cursor.position, (5, 'abc'))

    def test_cursor_immutable(self):
        cursor = Cursor(reverse=True, position=(5,))
        with self.assertRaises(FrozenInstanceError):
            cursor.position = (10,)


class CursorPaginatorEncodingTestCase(SimpleTestCase):
    def setUp(self):
        self.paginator = CursorPaginator(
            model=BlogPost,
            ordering=('-id',),
        )

    def test_decode_none_returns_none(self):
        self.assertIsNone(self.paginator.decode_cursor(None))

    def test_encode_decode_roundtrip(self):
        cursor = Cursor(reverse=True, position=(123,))
        encoded = self.paginator.encode_cursor(cursor)
        decoded = self.paginator.decode_cursor(encoded)

        self.assertIsInstance(encoded, str)
        self.assertNotEqual('', encoded)
        self.assertEqual(cursor, decoded)

    def test_decode_invalid_token_raises_bad_request(self):
        with self.assertRaises(BadRequest):
            self.paginator.decode_cursor('not-a-valid-signed-cursor')

    def test_decode_tampered_token_raises_bad_request(self):
        cursor = Cursor(reverse=False, position=(123,))
        encoded = self.paginator.encode_cursor(cursor)
        tampered = encoded[:-1] + ('a' if encoded[-1] != 'a' else 'b')

        with self.assertRaises(BadRequest):
            self.paginator.decode_cursor(tampered)

    def test_decode_wrong_salt_raises_bad_request(self):
        encoded = self.paginator.encode_cursor(Cursor(reverse=False, position=(123,)))
        other = CursorPaginator(model=BlogPost, ordering=('-id',), cursor_salt='some.other.salt')

        with self.assertRaises(BadRequest):
            other.decode_cursor(encoded)

    def test_decode_wrong_version_raises_bad_request(self):
        token = signing.dumps({'v': CURSOR_VERSION + 1, 'r': False, 'p': [123]}, salt=DEFAULT_CURSOR_SALT)

        with self.assertRaises(BadRequest):
            self.paginator.decode_cursor(token)

    def test_decode_wrong_position_length_raises_bad_request(self):
        token = signing.dumps({'v': CURSOR_VERSION, 'r': False, 'p': [123, 456]}, salt=DEFAULT_CURSOR_SALT)

        with self.assertRaises(BadRequest):
            self.paginator.decode_cursor(token)

    def test_decode_non_boolean_reverse_raises_bad_request(self):
        token = signing.dumps({'v': CURSOR_VERSION, 'r': '1', 'p': [123]}, salt=DEFAULT_CURSOR_SALT)

        with self.assertRaises(BadRequest):
            self.paginator.decode_cursor(token)

    def test_decode_null_position_raises_bad_request(self):
        token = signing.dumps({'v': CURSOR_VERSION, 'r': False, 'p': [None]}, salt=DEFAULT_CURSOR_SALT)

        with self.assertRaises(BadRequest):
            self.paginator.decode_cursor(token)

    def test_encode_null_position_rejected(self):
        with self.assertRaises(ValueError):
            self.paginator.encode_cursor(Cursor(reverse=False, position=(None,)))

    def test_encode_short_position_rejected(self):
        paginator = CursorPaginator(model=BlogPost, ordering=('-score', '-id'))

        with self.assertRaises(ValueError):
            paginator.encode_cursor(Cursor(reverse=False, position=(123,)))

    def test_encode_long_position_rejected(self):
        with self.assertRaises(ValueError):
            self.paginator.encode_cursor(Cursor(reverse=False, position=(123, 456)))

    def test_decode_coerces_value_to_model_field_type(self):
        cursor = self.paginator.decode_cursor(
            signing.dumps({'v': CURSOR_VERSION, 'r': False, 'p': ['123']}, salt=DEFAULT_CURSOR_SALT),
        )

        self.assertEqual((123,), cursor.position)

    def test_composite_position_roundtrip(self):
        paginator = CursorPaginator(model=BlogPost, ordering=('-score', '-id'))
        cursor = Cursor(reverse=False, position=(7, 123))

        self.assertEqual(cursor, paginator.decode_cursor(paginator.encode_cursor(cursor)))


class CursorPaginatorValidationTestCase(SimpleTestCase):
    def test_empty_ordering_rejected(self):
        with self.assertRaises(ValueError):
            CursorPaginator(BlogPost, ())

    def test_non_unique_single_field_ordering_rejected(self):
        with self.assertRaises(ValueError):
            CursorPaginator(BlogPost, ('-score',))

    def test_non_unique_ordering_requires_unique_tie_breaker(self):
        with self.assertRaises(ValueError):
            CursorPaginator(BlogPost, ('-score', '-publish_on'))

    def test_unique_single_field_ordering_allowed(self):
        paginator = CursorPaginator(BlogPost, ('-id',))

        self.assertEqual(('-id',), paginator.ordering)

    def test_composite_ordering_with_tie_breaker_allowed(self):
        paginator = CursorPaginator(BlogPost, ('-score', '-id'))

        self.assertEqual(('-score', '-id'), paginator.ordering)

    def test_related_ordering_rejected(self):
        with self.assertRaises(ValueError):
            CursorPaginator(BlogPost, ('authors__id', 'id'))

    def test_nullable_model_field_ordering_rejected(self):
        with self.assertRaises(ValueError):
            CursorPaginator(BlogPost, ('organization', 'id'))

    def test_non_unique_tie_breaker_rejected(self):
        # BlogPost.score is not unique, so it cannot identify a single row.
        with self.assertRaises(ValueError):
            CursorPaginator(BlogPost, ('score',), unique_field='score')

    def test_unique_non_pk_tie_breaker_allowed(self):
        # BlogPostTag.slug carries unique=True, so it is a valid tie-breaker.
        paginator = CursorPaginator(BlogPostTag, ('slug',), unique_field='slug')

        self.assertEqual(('slug',), paginator.ordering)
