from dataclasses import FrozenInstanceError

from django.core import signing
from django.core.exceptions import BadRequest
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from judge.models import BlogPost
from judge.utils.cursor_paginator import (
    CURSOR_VERSION,
    DEFAULT_CURSOR_SALT,
    Cursor,
    CursorPaginator,
    _reverse_ordering,
)


class ReverseOrderingTestCase(SimpleTestCase):
    def test_reverse_ascending(self):
        self.assertEqual(_reverse_ordering(('created',)), ('-created',))

    def test_reverse_descending(self):
        self.assertEqual(_reverse_ordering(('-created',)), ('created',))

    def test_reverse_multiple_fields(self):
        self.assertEqual(
            _reverse_ordering(('-created', 'uuid')),
            ('created', '-uuid'),
        )

    def test_reverse_empty_tuple(self):
        self.assertEqual(_reverse_ordering(()), ())


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
            queryset=BlogPost.objects.none(),
            ordering=('-id',),
            page_size=10,
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


class CursorPaginatorValidationTestCase(SimpleTestCase):
    def test_empty_ordering_rejected(self):
        with self.assertRaises(ValueError):
            CursorPaginator(BlogPost.objects.none(), (), 10)

    def test_non_positive_page_size_rejected(self):
        with self.assertRaises(ValueError):
            CursorPaginator(BlogPost.objects.none(), ('-id',), 0)

    def test_non_unique_single_field_ordering_rejected(self):
        with self.assertRaises(ValueError):
            CursorPaginator(BlogPost.objects.none(), ('-score',), 10)

    def test_non_unique_ordering_requires_unique_tie_breaker(self):
        with self.assertRaises(ValueError):
            CursorPaginator(BlogPost.objects.none(), ('-score', '-publish_on'), 10)

    def test_unique_single_field_ordering_allowed(self):
        paginator = CursorPaginator(BlogPost.objects.none(), ('-id',), 10)

        self.assertEqual(('-id',), paginator.ordering)

    def test_composite_ordering_with_tie_breaker_allowed(self):
        paginator = CursorPaginator(BlogPost.objects.none(), ('-score', '-id'), 10)

        self.assertEqual(('-score', '-id'), paginator.ordering)

    def test_related_ordering_rejected(self):
        with self.assertRaises(ValueError):
            CursorPaginator(BlogPost.objects.none(), ('authors__id', 'id'), 10)

    def test_nullable_model_field_ordering_rejected(self):
        with self.assertRaises(ValueError):
            CursorPaginator(BlogPost.objects.none(), ('organization', 'id'), 10)


class CursorPaginatorWithBlogPostTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.posts = []
        for i in range(25):
            post = BlogPost.objects.create(
                title=f'Test Post {i:03d}',
                slug=f'test-post-{i:03d}',
                publish_on=now,
                content=f'Content {i}',
                score=i % 5,
            )
            cls.posts.append(post)

    def _queryset(self):
        return BlogPost.objects.filter(id__in=[post.id for post in self.posts])

    def _create_paginator(self, ordering=('-id',), page_size=10):
        return CursorPaginator(
            queryset=self._queryset(),
            ordering=ordering,
            page_size=page_size,
        )

    def _collect_forward_ids(self, ordering=('-id',), page_size=10):
        paginator = self._create_paginator(ordering=ordering, page_size=page_size)
        cursor = None
        result = []

        while True:
            page, _, next_link = paginator.paginate(cursor)
            result.extend(post.id for post in page)

            if next_link is None:
                break
            cursor = next_link

        return result

    def test_paginate_first_page(self):
        paginator = self._create_paginator()
        page, prev_link, next_link = paginator.paginate(None)

        self.assertEqual(10, len(page))
        self.assertIsNone(prev_link)
        self.assertIsNotNone(next_link)

    def test_paginate_empty_queryset(self):
        paginator = CursorPaginator(
            queryset=BlogPost.objects.none(),
            ordering=('-id',),
            page_size=10,
        )

        page, prev_link, next_link = paginator.paginate(None)

        self.assertEqual([], page)
        self.assertIsNone(prev_link)
        self.assertIsNone(next_link)

    def test_paginate_single_page(self):
        queryset = BlogPost.objects.filter(id__in=[post.id for post in self.posts[:5]])
        paginator = CursorPaginator(
            queryset=queryset,
            ordering=('-id',),
            page_size=10,
        )

        page, prev_link, next_link = paginator.paginate(None)

        self.assertEqual(5, len(page))
        self.assertIsNone(prev_link)
        self.assertIsNone(next_link)

    def test_paginate_exact_page_size(self):
        queryset = BlogPost.objects.filter(id__in=[post.id for post in self.posts[:10]])
        paginator = CursorPaginator(
            queryset=queryset,
            ordering=('-id',),
            page_size=10,
        )

        page, prev_link, next_link = paginator.paginate(None)

        self.assertEqual(10, len(page))
        self.assertIsNone(prev_link)
        self.assertIsNone(next_link)

    def test_full_forward_traversal_by_id(self):
        expected_ids = list(self._queryset().order_by('-id').values_list('id', flat=True))

        self.assertEqual(expected_ids, self._collect_forward_ids(ordering=('-id',), page_size=7))

    def test_full_forward_traversal_with_duplicate_sort_key(self):
        expected_ids = list(self._queryset().order_by('-score', '-id').values_list('id', flat=True))

        self.assertEqual(expected_ids, self._collect_forward_ids(ordering=('-score', '-id'), page_size=7))

    def test_paginate_backward_navigation(self):
        paginator = self._create_paginator()

        page1, _, next_link = paginator.paginate(None)
        page2, prev_link2, _ = paginator.paginate(next_link)
        page1_again, prev_link1, next_link1 = paginator.paginate(prev_link2)

        self.assertEqual([post.id for post in page1], [post.id for post in page1_again])
        self.assertNotEqual([post.id for post in page1], [post.id for post in page2])
        self.assertIsNone(prev_link1)
        self.assertIsNotNone(next_link1)

    def test_paginate_backward_navigation_with_duplicate_sort_key(self):
        paginator = self._create_paginator(ordering=('-score', '-id'), page_size=7)

        page1, _, next_link = paginator.paginate(None)
        page2, prev_link2, _ = paginator.paginate(next_link)
        page1_again, prev_link1, next_link1 = paginator.paginate(prev_link2)

        self.assertEqual([post.id for post in page1], [post.id for post in page1_again])
        self.assertNotEqual([post.id for post in page1], [post.id for post in page2])
        self.assertIsNone(prev_link1)
        self.assertIsNotNone(next_link1)

    def test_paginate_ascending_order(self):
        paginator = self._create_paginator(ordering=('id',))
        page, prev_link, next_link = paginator.paginate(None)

        self.assertEqual([post.id for post in page], sorted(post.id for post in page))
        self.assertIsNone(prev_link)
        self.assertIsNotNone(next_link)

    def test_all_pages_forward_then_backward(self):
        paginator = self._create_paginator(ordering=('-score', '-id'), page_size=6)
        forward_pages = []
        cursor = None
        last_prev_link = None

        while True:
            page, prev_link, next_link = paginator.paginate(cursor)
            forward_pages.append([post.id for post in page])

            if next_link is None:
                last_prev_link = prev_link
                break
            cursor = next_link

        backward_pages = []
        cursor = last_prev_link
        while cursor is not None:
            page, prev_link, _ = paginator.paginate(cursor)
            backward_pages.append([post.id for post in page])
            cursor = prev_link

        backward_pages.reverse()
        self.assertEqual(forward_pages[:-1], backward_pages)
