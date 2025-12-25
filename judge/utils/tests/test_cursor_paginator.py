from base64 import urlsafe_b64encode
from unittest.mock import MagicMock

from django.core.exceptions import BadRequest
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from judge.models import BlogPost
from judge.utils.cursor_paginator import (
    Cursor,
    CursorPaginator,
    _positive_int,
    _reverse_ordering,
)


class PositiveIntTestCase(SimpleTestCase):
    def test_positive_integer(self):
        self.assertEqual(_positive_int('5'), 5)
        self.assertEqual(_positive_int('0'), 0)
        self.assertEqual(_positive_int('100'), 100)

    def test_strict_mode_rejects_zero(self):
        with self.assertRaises(ValueError):
            _positive_int('0', strict=True)

    def test_negative_integer_raises(self):
        with self.assertRaises(ValueError):
            _positive_int('-1')
        with self.assertRaises(ValueError):
            _positive_int('-100')

    def test_cutoff(self):
        self.assertEqual(_positive_int('1000', cutoff=500), 500)
        self.assertEqual(_positive_int('100', cutoff=500), 100)
        self.assertEqual(_positive_int('500', cutoff=500), 500)

    def test_invalid_string_raises(self):
        with self.assertRaises(ValueError):
            _positive_int('abc')
        with self.assertRaises(ValueError):
            _positive_int('')


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


class CursorNamedTupleTestCase(SimpleTestCase):
    def test_cursor_creation(self):
        cursor = Cursor(offset=5, reverse=True, position='abc')
        self.assertEqual(cursor.offset, 5)
        self.assertEqual(cursor.reverse, True)
        self.assertEqual(cursor.position, 'abc')

    def test_cursor_immutable(self):
        cursor = Cursor(offset=5, reverse=True, position='abc')
        with self.assertRaises(AttributeError):
            cursor.offset = 10


class CursorPaginatorEncodingTestCase(SimpleTestCase):
    def setUp(self):
        self.queryset = MagicMock()
        self.paginator = CursorPaginator(
            queryset=self.queryset,
            ordering=('-id',),
            page_size=10,
        )

    def test_encode_cursor_basic(self):
        cursor = Cursor(offset=0, reverse=False, position=None)
        encoded = self.paginator.encode_cursor(cursor)
        self.assertEqual(encoded, '')

    def test_encode_cursor_with_offset(self):
        cursor = Cursor(offset=5, reverse=False, position=None)
        encoded = self.paginator.encode_cursor(cursor)
        decoded = self.paginator.decode_cursor(encoded)
        self.assertEqual(decoded.offset, 5)
        self.assertEqual(decoded.reverse, False)
        self.assertIsNone(decoded.position)

    def test_encode_cursor_with_reverse(self):
        cursor = Cursor(offset=0, reverse=True, position=None)
        encoded = self.paginator.encode_cursor(cursor)
        decoded = self.paginator.decode_cursor(encoded)
        self.assertEqual(decoded.reverse, True)

    def test_encode_cursor_with_position(self):
        cursor = Cursor(offset=0, reverse=False, position='123')
        encoded = self.paginator.encode_cursor(cursor)
        decoded = self.paginator.decode_cursor(encoded)
        self.assertEqual(decoded.position, '123')

    def test_encode_decode_roundtrip(self):
        cursor = Cursor(offset=10, reverse=True, position='abc123')
        encoded = self.paginator.encode_cursor(cursor)
        decoded = self.paginator.decode_cursor(encoded)
        self.assertEqual(decoded.offset, 10)
        self.assertEqual(decoded.reverse, True)
        self.assertEqual(decoded.position, 'abc123')

    def test_decode_none_returns_none(self):
        self.assertIsNone(self.paginator.decode_cursor(None))

    def test_decode_invalid_base64_raises_bad_request(self):
        # binascii.Error is a subclass of ValueError, so it's caught properly
        with self.assertRaises(BadRequest):
            self.paginator.decode_cursor('!!invalid!!')

    def test_decode_invalid_offset_raises_bad_request(self):
        invalid_token = urlsafe_b64encode(b'o=abc').decode('ascii')
        with self.assertRaises(BadRequest):
            self.paginator.decode_cursor(invalid_token)

    def test_offset_cutoff_applied(self):
        paginator = CursorPaginator(
            queryset=self.queryset,
            ordering=('-id',),
            page_size=10,
            offset_cutoff=100,
        )
        token = urlsafe_b64encode(b'o=999').decode('ascii')
        decoded = paginator.decode_cursor(token)
        self.assertEqual(decoded.offset, 100)

    def test_negative_reverse_value_in_token(self):
        token = urlsafe_b64encode(b'r=-1').decode('ascii')
        decoded = self.paginator.decode_cursor(token)
        self.assertEqual(decoded.reverse, True)

    def test_position_with_special_characters(self):
        cursor = Cursor(offset=0, reverse=False, position='test&value=123')
        encoded = self.paginator.encode_cursor(cursor)
        decoded = self.paginator.decode_cursor(encoded)
        self.assertEqual(decoded.position, 'test&value=123')


class CursorPaginatorWithBlogPostTestCase(TestCase):
    """Tests using BlogPost model with real database queries."""

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

    def _create_paginator(self, ordering=('-id',), page_size=10):
        queryset = BlogPost.objects.filter(id__in=[p.id for p in self.posts])
        paginator = CursorPaginator(
            queryset=queryset,
            ordering=ordering,
            page_size=page_size,
        )
        return paginator

    def test_paginate_first_page(self):
        paginator = self._create_paginator()
        page, prev_link, next_link = paginator.paginate(None)

        self.assertEqual(len(page), 10)
        self.assertIsNone(prev_link)
        self.assertIsNotNone(next_link)

    def test_paginate_empty_queryset(self):
        queryset = BlogPost.objects.none()
        paginator = CursorPaginator(
            queryset=queryset,
            ordering=('-id',),
            page_size=10,
        )

        page, prev_link, next_link = paginator.paginate(None)

        self.assertEqual(len(page), 0)
        self.assertIsNone(prev_link)
        self.assertIsNone(next_link)

    def test_paginate_single_page(self):
        # Use only first 5 posts
        queryset = BlogPost.objects.filter(id__in=[p.id for p in self.posts[:5]])
        paginator = CursorPaginator(
            queryset=queryset,
            ordering=('-id',),
            page_size=10,
        )

        page, prev_link, next_link = paginator.paginate(None)

        self.assertEqual(len(page), 5)
        self.assertIsNone(prev_link)
        self.assertIsNone(next_link)

    def test_paginate_exact_page_size(self):
        # Use only first 10 posts
        queryset = BlogPost.objects.filter(id__in=[p.id for p in self.posts[:10]])
        paginator = CursorPaginator(
            queryset=queryset,
            ordering=('-id',),
            page_size=10,
        )

        page, prev_link, next_link = paginator.paginate(None)

        self.assertEqual(len(page), 10)
        self.assertIsNone(prev_link)
        self.assertIsNone(next_link)

    def test_paginate_forward_navigation(self):
        paginator = self._create_paginator()

        # First page
        page1, _, next_link1 = paginator.paginate(None)
        self.assertEqual(len(page1), 10)
        page1_ids = [p.id for p in page1]

        # Second page
        page2, prev_link2, next_link2 = paginator.paginate(next_link1)
        self.assertEqual(len(page2), 10)
        self.assertIsNotNone(prev_link2)
        self.assertIsNotNone(next_link2)
        page2_ids = [p.id for p in page2]

        # Verify pages don't overlap
        self.assertEqual(len(set(page1_ids) & set(page2_ids)), 0)

        # Third page (last)
        page3, prev_link3, next_link3 = paginator.paginate(next_link2)
        self.assertEqual(len(page3), 5)
        self.assertIsNotNone(prev_link3)
        self.assertIsNone(next_link3)

    def test_paginate_backward_navigation(self):
        paginator = self._create_paginator()

        # Navigate forward to page 2
        _, _, next_link = paginator.paginate(None)
        page2, prev_link2, _ = paginator.paginate(next_link)
        page2_ids = [p.id for p in page2]

        # Navigate back to page 1
        page1_again, prev_link1, next_link1 = paginator.paginate(prev_link2)

        self.assertIsNone(prev_link1)
        self.assertIsNotNone(next_link1)
        self.assertEqual(len(page1_again), 10)

        page1_ids = [p.id for p in page1_again]
        self.assertEqual(len(set(page1_ids) & set(page2_ids)), 0)

    def test_paginate_ascending_order(self):
        paginator = self._create_paginator(ordering=('id',))

        page, prev_link, next_link = paginator.paginate(None)

        self.assertEqual(len(page), 10)
        self.assertEqual(page[0].id, min(p.id for p in page))
        self.assertIsNone(prev_link)
        self.assertIsNotNone(next_link)

    def test_paginate_descending_order(self):
        paginator = self._create_paginator(ordering=('-id',))

        page, _, _ = paginator.paginate(None)

        self.assertEqual(len(page), 10)
        self.assertEqual(page[0].id, max(p.id for p in page))

    def test_paginate_by_score_field(self):
        paginator = self._create_paginator(ordering=('-score',))

        page, _, _ = paginator.paginate(None)

        scores = [p.score for p in page]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_paginate_with_position_filter(self):
        paginator = self._create_paginator()

        page1, _, next_link = paginator.paginate(None)
        page2, _, _ = paginator.paginate(next_link)

        max_page2_id = max(p.id for p in page2)
        min_page1_id = min(p.id for p in page1)
        self.assertLess(max_page2_id, min_page1_id)

    def test_paginate_different_page_sizes(self):
        for page_size in [1, 5, 10, 20, 100]:
            with self.subTest(page_size=page_size):
                paginator = self._create_paginator(page_size=page_size)
                page, _, _ = paginator.paginate(None)
                self.assertLessEqual(len(page), page_size)


class CursorPaginatorEdgeCasesTestCase(TestCase):
    """Test edge cases and known bugs."""

    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.posts = []
        for i in range(15):
            post = BlogPost.objects.create(
                title=f'Edge Case Post {i}',
                slug=f'edge-case-post-{i}',
                publish_on=now,
                content=f'Content {i}',
                score=100,  # All same score for duplicate position test
            )
            cls.posts.append(post)

    def test_duplicate_position_values(self):
        """Test handling of items with same position value."""
        queryset = BlogPost.objects.filter(id__in=[p.id for p in self.posts])
        paginator = CursorPaginator(
            queryset=queryset,
            ordering=('-score',),
            page_size=10,
        )

        page, _, next_link = paginator.paginate(None)

        self.assertEqual(len(page), 10)
        self.assertIsNotNone(next_link)

    def test_get_position_from_dict_instance(self):
        paginator = CursorPaginator(
            queryset=MagicMock(),
            ordering=('-id',),
            page_size=10,
        )

        instance = {'id': 42, 'name': 'test'}
        position = paginator._get_position_from_instance(instance, ('-id',))
        self.assertEqual(position, '42')

    def test_get_position_from_model_instance(self):
        post = self.posts[0]

        paginator = CursorPaginator(
            queryset=BlogPost.objects.none(),
            ordering=('-id',),
            page_size=10,
        )

        position = paginator._get_position_from_instance(post, ('-id',))
        self.assertEqual(position, str(post.id))


class CursorPaginatorConsistencyTestCase(TestCase):
    """Test that pagination is consistent across multiple traversals."""

    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.posts = []
        for i in range(50):
            post = BlogPost.objects.create(
                title=f'Consistency Post {i:03d}',
                slug=f'consistency-post-{i:03d}',
                publish_on=now,
                content=f'Content {i}',
                score=i % 10,
            )
            cls.posts.append(post)

    def _create_paginator(self, ordering=('-id',), page_size=10):
        queryset = BlogPost.objects.filter(id__in=[p.id for p in self.posts])
        paginator = CursorPaginator(
            queryset=queryset,
            ordering=ordering,
            page_size=page_size,
        )
        return paginator

    def test_full_forward_traversal_covers_all_items(self):
        """Verify that paginating forward covers all items exactly once."""
        queryset = BlogPost.objects.filter(id__in=[p.id for p in self.posts])
        expected_ids = set(queryset.values_list('id', flat=True))

        paginator = CursorPaginator(
            queryset=queryset,
            ordering=('-id',),
            page_size=7,
        )

        collected_ids = set()
        cursor = None

        while True:
            page, _, next_link = paginator.paginate(cursor)
            for item in page:
                self.assertNotIn(item.id, collected_ids, 'Duplicate item found')
                collected_ids.add(item.id)

            if next_link is None:
                break
            cursor = next_link

        self.assertEqual(collected_ids, expected_ids)

    def test_forward_and_backward_consistency(self):
        """Test that going forward then backward returns to the same items."""
        paginator = self._create_paginator()

        page1, _, next_link = paginator.paginate(None)
        page1_ids = [p.id for p in page1]

        _, prev_link, _ = paginator.paginate(next_link)

        page1_again, _, _ = paginator.paginate(prev_link)
        page1_again_ids = [p.id for p in page1_again]

        self.assertEqual(page1_ids, page1_again_ids)

    def test_all_pages_forward_then_backward(self):
        """Test traversing all pages forward then all backward."""
        paginator = self._create_paginator()

        forward_pages = []
        cursor = None
        last_prev_link = None
        while True:
            page, prev_link, next_link = paginator.paginate(cursor)
            forward_pages.append([p.id for p in page])

            if next_link is None:
                last_prev_link = prev_link
                break
            cursor = next_link

        backward_pages = []
        cursor = last_prev_link
        while cursor is not None:
            page, prev_link, _ = paginator.paginate(cursor)
            backward_pages.append([p.id for p in page])
            cursor = prev_link

        backward_pages.reverse()
        self.assertEqual(forward_pages[:-1], backward_pages)
