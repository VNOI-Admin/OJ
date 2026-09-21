from django.conf import settings
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from judge.models import Organization, OrganizationRegistrationForm
from judge.models.tests.util import CommonDataMixin, create_user


class OrganizationRegistrationFormAdminTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(self):
        super().setUpTestData()
        self.users.update({
            'applicant': create_user(username='applicant'),
        })
        Group.objects.get_or_create(name=settings.GROUP_PERMISSION_FOR_ORG_ADMIN)

    def setUp(self):
        self.registration = OrganizationRegistrationForm.objects.create(
            user=self.users['applicant'].profile,
            name='New Org',
            slug='neworg',
            short_name='NewOrg',
            about='We teach competitive programming.',
            applicant_name='Nguyen Van A',
            facebook='https://facebook.com/applicant',
            email='applicant@example.com',
            reason='We want to host contests for our school.',
            proof_files=['/organization_form/proof.png'],
        )
        self.client.force_login(self.users['superuser'])
        self.changelist_url = reverse('admin:judge_organizationregistrationform_changelist')

    def run_action(self, action):
        return self.client.post(self.changelist_url, {
            'action': action,
            '_selected_action': [str(self.registration.pk)],
        }, follow=True)

    def change_url(self):
        return reverse('admin:judge_organizationregistrationform_change', args=(self.registration.pk,))

    def change_state(self, state, review_note=''):
        return self.client.post(self.change_url(), {'state': state, 'review_note': review_note}, follow=True)

    def test_changing_the_state_to_approved_creates_the_organization(self):
        self.change_state(OrganizationRegistrationForm.State.APPROVED)

        self.registration.refresh_from_db()
        self.assertEqual(self.registration.state, OrganizationRegistrationForm.State.APPROVED)
        self.assertEqual(self.registration.organization, Organization.objects.get(slug='neworg'))
        self.assertEqual(self.registration.reviewer, self.users['superuser'].profile)
        self.assertIsNotNone(self.registration.review_time)

    def test_changing_the_state_to_rejected_stores_the_note(self):
        self.change_state(OrganizationRegistrationForm.State.REJECTED, 'Ảnh minh chứng bị mờ.')

        self.registration.refresh_from_db()
        self.assertEqual(self.registration.state, OrganizationRegistrationForm.State.REJECTED)
        self.assertEqual(self.registration.review_note, 'Ảnh minh chứng bị mờ.')
        self.assertFalse(Organization.objects.filter(slug='neworg').exists())

    def test_rejecting_without_a_note_is_refused(self):
        response = self.change_state(OrganizationRegistrationForm.State.REJECTED)

        self.registration.refresh_from_db()
        self.assertEqual(self.registration.state, OrganizationRegistrationForm.State.PENDING)
        self.assertIn('review_note', response.context['adminform'].form.errors)

    def test_a_reviewed_form_keeps_its_state(self):
        self.change_state(OrganizationRegistrationForm.State.APPROVED)

        self.change_state(OrganizationRegistrationForm.State.REJECTED, 'Changed my mind.')

        self.registration.refresh_from_db()
        self.assertEqual(self.registration.state, OrganizationRegistrationForm.State.APPROVED)
        self.assertEqual(Organization.objects.filter(slug='neworg').count(), 1)

    def test_saving_without_changing_the_state_keeps_it_pending(self):
        self.change_state(OrganizationRegistrationForm.State.PENDING, 'Waiting for a clearer photo.')

        self.registration.refresh_from_db()
        self.assertEqual(self.registration.state, OrganizationRegistrationForm.State.PENDING)
        self.assertEqual(self.registration.review_note, 'Waiting for a clearer photo.')
        self.assertFalse(Organization.objects.filter(slug='neworg').exists())

    def test_changelist_shows_the_pending_form(self):
        response = self.client.get(self.changelist_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'New Org')

    def test_change_page_links_to_the_uploaded_proof(self):
        response = self.client.get(
            reverse('admin:judge_organizationregistrationform_change', args=(self.registration.pk,)),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '/organization_form/proof.png')

    def test_approve_action_creates_the_organization(self):
        self.run_action('approve_registrations')

        self.registration.refresh_from_db()
        self.assertEqual(self.registration.state, OrganizationRegistrationForm.State.APPROVED)
        self.assertEqual(self.registration.organization, Organization.objects.get(slug='neworg'))
        self.assertEqual(self.registration.reviewer, self.users['superuser'].profile)

    def test_reject_action_keeps_the_review_note(self):
        self.registration.review_note = 'Proof is unreadable.'
        self.registration.save(update_fields=['review_note'])

        self.run_action('reject_registrations')

        self.registration.refresh_from_db()
        self.assertEqual(self.registration.state, OrganizationRegistrationForm.State.REJECTED)
        self.assertEqual(self.registration.review_note, 'Proof is unreadable.')
        self.assertFalse(Organization.objects.filter(slug='neworg').exists())
