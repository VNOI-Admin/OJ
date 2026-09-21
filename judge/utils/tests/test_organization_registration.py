from django.conf import settings
from django.contrib.auth.models import Group
from django.test import TestCase

from judge.models import Notification, Organization, OrganizationRegistrationForm
from judge.models.tests.util import CommonDataMixin, create_organization, create_user
from judge.utils.organization import approve_organization_registration, reject_organization_registration


class OrganizationRegistrationApprovalTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(self):
        super().setUpTestData()
        self.users.update({
            'applicant': create_user(username='applicant'),
            'reviewer': create_user(username='reviewer', is_staff=True, is_superuser=True),
        })
        Group.objects.get_or_create(name=settings.GROUP_PERMISSION_FOR_ORG_ADMIN)

    def setUp(self):
        self.applicant = self.users['applicant'].profile
        self.reviewer = self.users['reviewer'].profile

    def create_registration(self, **kwargs):
        defaults = {
            'user': self.applicant,
            'name': 'New Org',
            'slug': 'neworg',
            'short_name': 'NewOrg',
            'about': 'We teach competitive programming.',
            'applicant_name': 'Nguyen Van A',
            'facebook': 'https://facebook.com/applicant',
            'email': 'applicant@example.com',
            'reason': 'We want to host contests for our school.',
            'proof_files': ['/organization_form/proof.png'],
        }
        defaults.update(kwargs)
        return OrganizationRegistrationForm.objects.create(**defaults)

    def test_approving_creates_the_organization_from_the_submitted_fields(self):
        registration = self.create_registration()

        approve_organization_registration(registration, self.reviewer)

        organization = Organization.objects.get(slug='neworg')
        self.assertEqual(organization.name, 'New Org')
        self.assertEqual(organization.short_name, 'NewOrg')
        self.assertEqual(organization.about, 'We teach competitive programming.')
        self.assertEqual(organization.free_credit, organization.monthly_free_credit_limit)
        self.assertEqual(registration.organization, organization)

    def test_approving_makes_the_applicant_an_organization_admin(self):
        registration = self.create_registration()

        approve_organization_registration(registration, self.reviewer)

        organization = Organization.objects.get(slug='neworg')
        self.assertIn(self.applicant, organization.admins.all())
        self.assertTrue(self.applicant.user.groups.filter(name=settings.GROUP_PERMISSION_FOR_ORG_ADMIN).exists())

    def test_approving_works_when_the_org_admin_group_is_missing(self):
        Group.objects.filter(name=settings.GROUP_PERMISSION_FOR_ORG_ADMIN).delete()
        registration = self.create_registration()

        approve_organization_registration(registration, self.reviewer)

        self.assertTrue(Organization.objects.filter(slug='neworg').exists())
        self.assertTrue(self.applicant.user.groups.filter(name=settings.GROUP_PERMISSION_FOR_ORG_ADMIN).exists())

    def test_approving_records_the_review(self):
        registration = self.create_registration()

        approve_organization_registration(registration, self.reviewer)

        registration.refresh_from_db()
        self.assertEqual(registration.state, OrganizationRegistrationForm.State.APPROVED)
        self.assertEqual(registration.reviewer, self.reviewer)
        self.assertIsNotNone(registration.review_time)

    def test_approving_notifies_the_applicant(self):
        registration = self.create_registration()

        approve_organization_registration(registration, self.reviewer)

        self.assertEqual(Notification.objects.filter(recipient=self.applicant).count(), 1)

    def test_approving_twice_creates_only_one_organization(self):
        registration = self.create_registration()

        approve_organization_registration(registration, self.reviewer)
        review_time = OrganizationRegistrationForm.objects.get(pk=registration.pk).review_time
        approve_organization_registration(registration, self.reviewer)

        self.assertEqual(Organization.objects.filter(slug='neworg').count(), 1)
        self.assertEqual(OrganizationRegistrationForm.objects.get(pk=registration.pk).review_time, review_time)

    def test_approving_a_rejected_form_does_nothing(self):
        registration = self.create_registration(state=OrganizationRegistrationForm.State.REJECTED)

        approve_organization_registration(registration, self.reviewer)

        self.assertFalse(Organization.objects.filter(slug='neworg').exists())
        self.assertEqual(registration.state, OrganizationRegistrationForm.State.REJECTED)

    def test_approving_an_existing_organization_form_creates_nothing(self):
        organization = create_organization(name='existing', slug='existing', admins=('applicant',))
        registration = self.create_registration(organization=organization, name='', slug='', short_name='', about='')
        organization_count = Organization.objects.count()

        approve_organization_registration(registration, self.reviewer)

        registration.refresh_from_db()
        self.assertEqual(registration.state, OrganizationRegistrationForm.State.APPROVED)
        self.assertEqual(registration.organization, organization)
        self.assertEqual(Organization.objects.count(), organization_count)

    def test_rejecting_records_the_note_and_notifies(self):
        registration = self.create_registration()

        reject_organization_registration(registration, self.reviewer, 'Proof is unreadable.')

        registration.refresh_from_db()
        self.assertEqual(registration.state, OrganizationRegistrationForm.State.REJECTED)
        self.assertEqual(registration.review_note, 'Proof is unreadable.')
        self.assertEqual(registration.reviewer, self.reviewer)
        self.assertIsNotNone(registration.review_time)
        self.assertEqual(Notification.objects.filter(recipient=self.applicant).count(), 1)
        self.assertFalse(Organization.objects.filter(slug='neworg').exists())

    def test_rejecting_an_approved_form_does_nothing(self):
        registration = self.create_registration()
        approve_organization_registration(registration, self.reviewer)

        reject_organization_registration(registration, self.reviewer, 'Too late.')

        registration.refresh_from_db()
        self.assertEqual(registration.state, OrganizationRegistrationForm.State.APPROVED)
        self.assertEqual(registration.review_note, '')
