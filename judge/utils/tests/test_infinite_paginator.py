from django.core.paginator import EmptyPage
from django.test import SimpleTestCase, override_settings

from judge.utils.infinite_paginator import infinite_paginate


class InfinitePaginatorTestCase(SimpleTestCase):
    @override_settings(VNOJ_LOW_POWER_MODE=True)
    def test_low_power_mode(self):
        # Empty list
        page_empty = infinite_paginate([], 1, 10, 1)
        self.assertEqual(page_empty.object_list, [])
        self.assertFalse(page_empty.has_next())
        self.assertEqual(page_empty.page_range, [1])

        # Multiple of page_size: exactly 10 items with page_size=10
        page = infinite_paginate(range(1, 11), 1, 10, 1)
        self.assertEqual(page.object_list, list(range(1, 11)))
        self.assertFalse(page.has_next())
        self.assertEqual(page.page_range, [1])

        with self.assertRaises(EmptyPage):
            infinite_paginate(range(1, 11), 2, 10, 1)

        # Exactly 20 items with page_size=10:
        # Page 1 should have next
        page1 = infinite_paginate(range(1, 21), 1, 10, 1)
        self.assertEqual(page1.object_list, list(range(1, 11)))
        self.assertTrue(page1.has_next())
        self.assertEqual(page1.page_range, [1, 2, False])

        # Page 2 should not have next
        page2 = infinite_paginate(range(1, 21), 2, 10, 1)
        self.assertEqual(page2.object_list, list(range(11, 21)))
        self.assertFalse(page2.has_next())
        self.assertEqual(page2.page_range, [1, 2])

        with self.assertRaises(EmptyPage):
            infinite_paginate(range(1, 21), 3, 10, 1)

        # More than multiple: 11 items with page_size=10
        page_11 = infinite_paginate(range(1, 12), 1, 10, 1)
        self.assertTrue(page_11.has_next())
        self.assertEqual(page_11.page_range, [1, 2, False])

        page_11_2 = infinite_paginate(range(1, 12), 2, 10, 1)
        self.assertEqual(page_11_2.object_list, [11])
        self.assertFalse(page_11_2.has_next())
        self.assertEqual(page_11_2.page_range, [1, 2])

    def test_first_page(self):
        self.assertEqual(infinite_paginate(range(1, 101), 1, 10, 2).object_list, list(range(1, 11)))

        self.assertEqual(infinite_paginate(range(1, 101), 1, 10, 2).page_range, [1, 2, 3, False])
        self.assertEqual(infinite_paginate(range(1, 31), 1, 10, 2).page_range, [1, 2, 3])
        self.assertEqual(infinite_paginate(range(1, 22), 1, 10, 2).page_range, [1, 2, 3])
        self.assertEqual(infinite_paginate(range(1, 21), 1, 10, 2).page_range, [1, 2])
        self.assertEqual(infinite_paginate(range(1, 12), 1, 10, 2).page_range, [1, 2])
        self.assertEqual(infinite_paginate(range(1, 11), 1, 10, 2).page_range, [1])
        self.assertEqual(infinite_paginate(range(1, 2), 1, 10, 2).page_range, [1])
        self.assertEqual(infinite_paginate([], 1, 10, 2).page_range, [1])

    def test_gaps(self):
        self.assertEqual(infinite_paginate(range(1, 101), 1, 10, 2).page_range, [1, 2, 3, False])
        self.assertEqual(infinite_paginate(range(1, 101), 2, 10, 2).page_range, [1, 2, 3, 4, False])
        self.assertEqual(infinite_paginate(range(1, 101), 3, 10, 2).page_range, [1, 2, 3, 4, 5, False])
        self.assertEqual(infinite_paginate(range(1, 101), 5, 10, 2).page_range, [1, 2, 3, 4, 5, 6, 7, False])
        self.assertEqual(infinite_paginate(range(1, 101), 6, 10, 2).page_range, [1, 2, False, 4, 5, 6, 7, 8, False])

    def test_end(self):
        self.assertEqual(infinite_paginate(range(1, 101), 7, 10, 2).page_range, [1, 2, False, 5, 6, 7, 8, 9, False])
        self.assertEqual(infinite_paginate(range(1, 101), 8, 10, 2).page_range, [1, 2, False, 6, 7, 8, 9, 10])
        self.assertEqual(infinite_paginate(range(1, 101), 9, 10, 2).page_range, [1, 2, False, 7, 8, 9, 10])
        self.assertEqual(infinite_paginate(range(1, 101), 10, 10, 2).page_range, [1, 2, False, 8, 9, 10])
        self.assertEqual(infinite_paginate(range(1, 100), 10, 10, 2).page_range, [1, 2, False, 8, 9, 10])
        self.assertEqual(infinite_paginate(range(1, 100), 10, 10, 2).object_list, list(range(91, 100)))
