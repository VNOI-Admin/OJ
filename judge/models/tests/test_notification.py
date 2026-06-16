from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from judge.models import Notification, make_notification
from judge.models.tests.util import create_user


class NotificationTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = create_user(username='alice').profile
        cls.bob = create_user(username='bob').profile

    def setUp(self):
        # The cache is not rolled back between tests, unlike the database.
        cache.clear()

    def test_make_notification_fans_out_per_recipient(self):
        make_notification(
            [self.alice, self.bob], category=Notification.CONTEST,
            title='Hello', html='Body', url='/contest/x', popup=True,
        )
        self.assertEqual(Notification.objects.count(), 2)
        self.assertEqual(self.alice.notifications.count(), 1)
        self.assertEqual(self.bob.notifications.count(), 1)

        notification = self.alice.notifications.get()
        self.assertEqual(notification.title, 'Hello')
        self.assertEqual(notification.category, Notification.CONTEST)
        self.assertTrue(notification.popup)
        self.assertFalse(notification.read)

    def test_make_notification_accepts_profile_ids(self):
        make_notification([self.alice.id], category=Notification.TICKET, title='By id')
        self.assertEqual(self.alice.notifications.count(), 1)

    def test_unread_count_reflects_make_notification(self):
        self.assertEqual(self.alice.unread_notification_count, 0)
        make_notification([self.alice], category=Notification.TICKET, title='One')
        self.assertEqual(self.alice.unread_notification_count, 1)

    def test_mark_read_is_scoped_to_owner(self):
        make_notification([self.alice], category=Notification.TICKET, title='Alice only')
        alice_notification = self.alice.notifications.get()

        # Bob must not be able to mark Alice's notification as read.
        self.client.force_login(self.bob.user)
        response = self.client.post(reverse('notification_mark_read'), {'id': alice_notification.id, 'read': '1'})
        self.assertEqual(response.status_code, 200)
        alice_notification.refresh_from_db()
        self.assertFalse(alice_notification.read)

        # Alice can mark her own as read.
        self.client.force_login(self.alice.user)
        response = self.client.post(reverse('notification_mark_read'), {'id': alice_notification.id, 'read': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 0)
        alice_notification.refresh_from_db()
        self.assertTrue(alice_notification.read)

    def test_mark_all_read(self):
        make_notification([self.alice], category=Notification.TICKET, title='One')
        make_notification([self.alice], category=Notification.TICKET, title='Two')
        self.assertEqual(self.alice.unread_notification_count, 2)

        self.client.force_login(self.alice.user)
        response = self.client.post(reverse('notification_mark_read'), {'all': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 0)
        self.assertFalse(self.alice.notifications.filter(read=False).exists())
