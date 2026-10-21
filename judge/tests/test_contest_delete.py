from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from judge.models import Contest, Profile


class ContestDeleteTestCase(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.editor = user_model.objects.create_user(username='editor', password='pw')
        self.editor.user_permissions.add(Permission.objects.get(codename='edit_own_contest'))
        editor_profile = Profile.objects.create(user=self.editor)
        self.other = user_model.objects.create_user(username='other', password='pw')
        Profile.objects.create(user=self.other)

        now = timezone.now()
        self.contest = Contest.objects.create(key='todelete', name='To delete', start_time=now,
                                              end_time=now + timedelta(hours=1))
        self.contest.authors.add(editor_profile)
        self.url = reverse('contest_delete', args=[self.contest.key])

    def test_non_editor_cannot_delete(self):
        self.client.login(username='other', password='pw')
        self.client.post(self.url)
        self.assertTrue(Contest.objects.filter(key='todelete').exists())

    def test_editor_can_delete(self):
        self.client.login(username='editor', password='pw')
        resp = self.client.post(self.url)
        self.assertRedirects(resp, reverse('contest_list'), fetch_redirect_response=False)
        self.assertFalse(Contest.objects.filter(key='todelete').exists())
