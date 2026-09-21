import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from judge.models import OrganizationRegistrationForm
from judge.models.tests.util import CommonDataMixin, create_organization, create_user


def proof(name='cccd.png', size=1024, content_type='image/png'):
    return SimpleUploadedFile(name, b'x' * size, content_type=content_type)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class OrganizationRegisterViewTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(self):
        super().setUpTestData()
        self.users.update({
            'applicant': create_user(username='applicant'),
            'stranger': create_user(username='stranger'),
            'reviewer': create_user(
                username='reviewer',
                is_staff=True,
                user_permissions=('change_organizationregistrationform',),
            ),
        })

    def post_data(self, **kwargs):
        data = {
            'name': 'New Org',
            'slug': 'neworg',
            'short_name': 'NewOrg',
            'about': 'We teach competitive programming.',
            'applicant_name': 'Nguyen Van A',
            'facebook': 'https://facebook.com/applicant',
            'email': 'applicant@example.com',
            'reason': 'We want to host contests for our school.',
            'proof_files': [proof()],
        }
        data.update(kwargs)
        return data

    def register(self, **kwargs):
        return self.client.post(reverse('organization_register'), self.post_data(**kwargs))

    def test_anonymous_user_is_sent_to_login(self):
        response = self.client.get(reverse('organization_register'))
        self.assertRedirects(response, '%s?next=%s' % (reverse('auth_login'), reverse('organization_register')))

    def test_logged_in_user_sees_the_form(self):
        self.client.force_login(self.users['applicant'])
        self.assertEqual(self.client.get(reverse('organization_register')).status_code, 200)

    def test_submitting_stores_the_form_and_uploads_the_proof(self):
        self.client.force_login(self.users['applicant'])

        response = self.register(proof_files=[proof('front.png'), proof('back.jpg')])

        registration = OrganizationRegistrationForm.objects.get(slug='neworg')
        self.assertRedirects(response, registration.get_absolute_url())
        self.assertEqual(registration.user, self.users['applicant'].profile)
        self.assertEqual(registration.state, OrganizationRegistrationForm.State.PENDING)
        self.assertEqual(len(registration.proof_files), 2)
        for url in registration.proof_files:
            self.assertTrue(url.startswith('/organization_form/'))

    def test_submitting_does_not_trust_the_posted_state(self):
        self.client.force_login(self.users['applicant'])

        self.register(state=OrganizationRegistrationForm.State.APPROVED)

        registration = OrganizationRegistrationForm.objects.get(slug='neworg')
        self.assertEqual(registration.state, OrganizationRegistrationForm.State.PENDING)

    @override_settings(VNOJ_ORGANIZATION_FORM_MAX_FILES=2)
    def test_too_many_proof_files_are_rejected(self):
        self.client.force_login(self.users['applicant'])

        response = self.register(proof_files=[proof('a.png'), proof('b.png'), proof('c.png')])

        self.assertEqual(response.status_code, 200)
        self.assertIn('proof_files', response.context['form'].errors)
        self.assertFalse(OrganizationRegistrationForm.objects.exists())

    @override_settings(VNOJ_ORGANIZATION_FORM_MAX_FILE_SIZE=1024)
    def test_oversized_proof_file_is_rejected(self):
        self.client.force_login(self.users['applicant'])

        response = self.register(proof_files=[proof('big.png', size=2048)])

        self.assertEqual(response.status_code, 200)
        self.assertIn('proof_files', response.context['form'].errors)
        self.assertFalse(OrganizationRegistrationForm.objects.exists())

    def test_proof_file_with_a_disallowed_extension_is_rejected(self):
        self.client.force_login(self.users['applicant'])

        response = self.register(proof_files=[proof('malware.exe', content_type='application/octet-stream')])

        self.assertEqual(response.status_code, 200)
        self.assertIn('proof_files', response.context['form'].errors)
        self.assertFalse(OrganizationRegistrationForm.objects.exists())

    def test_proof_is_required(self):
        self.client.force_login(self.users['applicant'])

        response = self.register(proof_files=[])

        self.assertEqual(response.status_code, 200)
        self.assertIn('proof_files', response.context['form'].errors)
        self.assertFalse(OrganizationRegistrationForm.objects.exists())

    def test_the_registration_form_ignores_a_posted_organization(self):
        organization = create_organization(name='not_mine', slug='notmine')
        self.client.force_login(self.users['applicant'])

        self.register(organization=organization.id)

        self.assertTrue(OrganizationRegistrationForm.objects.get(slug='neworg').is_new_organization)

    def test_a_second_pending_form_is_refused(self):
        self.client.force_login(self.users['applicant'])
        self.register()

        response = self.register(slug='otherorg')

        self.assertEqual(OrganizationRegistrationForm.objects.count(), 1)
        self.assertNotEqual(response.status_code, 302)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class OrganizationRegisterDetailViewTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(self):
        super().setUpTestData()
        self.users.update({
            'applicant': create_user(username='applicant'),
            'stranger': create_user(username='stranger'),
            'reviewer': create_user(
                username='reviewer',
                is_staff=True,
                user_permissions=('change_organizationregistrationform',),
            ),
        })

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

    def test_owner_can_see_their_form(self):
        self.client.force_login(self.users['applicant'])
        response = self.client.get(self.registration.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '/organization_form/proof.png')

    def test_stranger_cannot_see_the_form(self):
        self.client.force_login(self.users['stranger'])
        self.assertEqual(self.client.get(self.registration.get_absolute_url()).status_code, 403)

    def test_reviewer_can_see_the_form(self):
        self.client.force_login(self.users['reviewer'])
        self.assertEqual(self.client.get(self.registration.get_absolute_url()).status_code, 200)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class OrganizationKycViewTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(self):
        super().setUpTestData()
        self.users.update({
            'org_admin': create_user(username='org_admin'),
            'applicant': create_user(username='applicant'),
        })
        self.organizations.update({
            'mine': create_organization(name='mine', slug='mine', admins=('org_admin',)),
            'not_mine': create_organization(name='not_mine', slug='notmine'),
        })

    def post_data(self, **kwargs):
        data = {
            'organization': self.organizations['mine'].id,
            'applicant_name': 'Nguyen Van A',
            'facebook': 'https://facebook.com/org_admin',
            'email': 'org_admin@example.com',
            'proof_files': [proof()],
        }
        data.update(kwargs)
        return data

    def submit(self, **kwargs):
        return self.client.post(reverse('organization_kyc'), self.post_data(**kwargs))

    def test_organization_admin_sees_the_form(self):
        self.client.force_login(self.users['org_admin'])
        self.assertEqual(self.client.get(reverse('organization_kyc')).status_code, 200)

    def test_submitting_proof_for_an_administered_organization_is_stored(self):
        self.client.force_login(self.users['org_admin'])

        response = self.submit()

        registration = OrganizationRegistrationForm.objects.get()
        self.assertRedirects(response, registration.get_absolute_url())
        self.assertEqual(registration.organization, self.organizations['mine'])
        self.assertFalse(registration.is_new_organization)
        self.assertEqual(registration.state, OrganizationRegistrationForm.State.PENDING)
        self.assertEqual(len(registration.proof_files), 1)

    def test_submitting_proof_for_an_organization_the_user_does_not_administer_is_rejected(self):
        self.client.force_login(self.users['org_admin'])

        response = self.submit(organization=self.organizations['not_mine'].id)

        self.assertEqual(response.status_code, 200)
        self.assertIn('organization', response.context['form'].errors)
        self.assertFalse(OrganizationRegistrationForm.objects.exists())

    def test_the_kyc_form_does_not_ask_for_a_reason(self):
        self.client.force_login(self.users['org_admin'])
        response = self.client.get(reverse('organization_kyc'))
        self.assertNotIn('reason', response.context['form'].fields)

    def test_proof_is_required(self):
        self.client.force_login(self.users['org_admin'])

        response = self.submit(proof_files=[])

        self.assertEqual(response.status_code, 200)
        self.assertIn('proof_files', response.context['form'].errors)
        self.assertFalse(OrganizationRegistrationForm.objects.exists())

    def test_a_user_administering_nothing_is_turned_away(self):
        self.client.force_login(self.users['applicant'])
        self.assertEqual(self.client.get(reverse('organization_kyc')).status_code, 403)


class OrganizationListTabsTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(self):
        super().setUpTestData()
        self.users.update({
            'applicant': create_user(username='applicant'),
        })

    def test_organization_list_offers_registration(self):
        self.client.force_login(self.users['applicant'])
        response = self.client.get(reverse('organization_list'))
        self.assertContains(response, 'href="%s"' % reverse('organization_register'))
        self.assertNotContains(response, reverse('organization_kyc'))

    def submit_form(self, **kwargs):
        defaults = {
            'user': self.users['applicant'].profile,
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

    def test_an_applicant_with_a_pending_form_is_linked_to_it_instead(self):
        registration = self.submit_form()
        self.client.force_login(self.users['applicant'])

        response = self.client.get(reverse('organization_list'))

        self.assertContains(response, registration.get_absolute_url())
        self.assertNotContains(response, 'href="%s"' % reverse('organization_register'))

    def test_an_applicant_whose_form_was_rejected_may_register_again(self):
        registration = self.submit_form(state=OrganizationRegistrationForm.State.REJECTED)
        self.client.force_login(self.users['applicant'])

        response = self.client.get(reverse('organization_list'))

        self.assertContains(response, registration.get_absolute_url())
        self.assertContains(response, 'href="%s"' % reverse('organization_register'))

    def test_organization_list_offers_the_kyc_form_to_organization_admins(self):
        create_organization(name='mine', slug='mine', admins=('applicant',))
        self.client.force_login(self.users['applicant'])
        response = self.client.get(reverse('organization_list'))
        self.assertContains(response, reverse('organization_kyc'))
