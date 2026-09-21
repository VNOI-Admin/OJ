from django.core.exceptions import ValidationError
from django.test import TestCase
from django.test.utils import override_settings

from judge.models import Organization, OrganizationRegistrationForm
from judge.models.tests.util import CommonDataMixin, create_organization, create_user


class OrganizationRegistrationFormTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(self):
        super().setUpTestData()
        self.users.update({
            'applicant': create_user(username='applicant'),
            'other_applicant': create_user(username='other_applicant'),
        })

    def build_form(self, username='applicant', **kwargs):
        defaults = {
            'user': self.users[username].profile,
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
        return OrganizationRegistrationForm(**defaults)

    def test_new_organization_form_is_pending_and_valid(self):
        form = self.build_form()
        form.full_clean()
        self.assertEqual(form.state, OrganizationRegistrationForm.State.PENDING)
        self.assertTrue(form.is_new_organization)

    def test_new_organization_form_requires_organization_fields(self):
        form = self.build_form(name='', slug='', short_name='', about='', reason='')
        with self.assertRaises(ValidationError) as context:
            form.full_clean()
        self.assertCountEqual(context.exception.message_dict.keys(),
                              ['name', 'slug', 'short_name', 'about', 'reason'])

    def test_facebook_and_email_are_required_but_phone_is_not(self):
        self.build_form(phone='').full_clean()
        for field in ('facebook', 'email'):
            with self.subTest(field=field), self.assertRaises(ValidationError) as context:
                self.build_form(**{field: ''}).full_clean()
            self.assertIn(field, context.exception.message_dict)

    def test_slug_must_not_collide_with_existing_organization(self):
        create_organization(name='taken', slug='taken')
        form = self.build_form(slug='taken')
        with self.assertRaises(ValidationError) as context:
            form.full_clean()
        self.assertIn('slug', context.exception.message_dict)

    def test_slug_must_not_collide_with_another_pending_form(self):
        self.build_form().save()
        form = self.build_form(username='other_applicant')
        with self.assertRaises(ValidationError) as context:
            form.full_clean()
        self.assertIn('slug', context.exception.message_dict)

    def test_slug_may_reuse_a_rejected_form_slug(self):
        self.build_form(state=OrganizationRegistrationForm.State.REJECTED).save()
        self.build_form(username='other_applicant').full_clean()

    def test_user_may_only_have_one_pending_form(self):
        self.build_form().save()
        form = self.build_form(slug='anotherorg')
        with self.assertRaises(ValidationError):
            form.full_clean()

    def test_existing_organization_form_ignores_organization_and_reason_fields(self):
        organization = create_organization(name='existing', slug='existing', admins=('applicant',))
        form = self.build_form(organization=organization, name='Ignored', slug='ignored', short_name='Ignored',
                               about='Ignored', reason='Ignored')
        form.full_clean()
        self.assertFalse(form.is_new_organization)
        self.assertEqual((form.name, form.slug, form.short_name, form.about, form.reason), ('', '', '', '', ''))

    def test_existing_organization_form_requires_the_applicant_to_be_an_admin(self):
        organization = create_organization(name='not_mine', slug='notmine')
        form = self.build_form(organization=organization, name='', slug='', short_name='', about='', reason='')
        with self.assertRaises(ValidationError) as context:
            form.full_clean()
        self.assertIn('organization', context.exception.message_dict)

    @override_settings(VNOJ_ORGANIZATION_ADMIN_LIMIT=1)
    def test_new_organization_form_is_refused_at_the_admin_limit(self):
        create_organization(name='already', slug='already', admins=('applicant',))
        form = self.build_form()
        with self.assertRaises(ValidationError):
            form.full_clean()

    @override_settings(VNOJ_ORGANIZATION_ADMIN_LIMIT=1)
    def test_admin_limit_does_not_apply_to_spam_organization_permission(self):
        user = create_user(username='spammer', user_permissions=('spam_organization',))
        create_organization(name='spammed', slug='spammed', admins=('spammer',))
        self.build_form(user=user.profile).full_clean()

    def test_string_representation_names_the_organization(self):
        self.assertEqual(str(self.build_form()), 'applicant: New Org')
        organization = create_organization(name='existing', slug='existing', admins=('applicant',))
        self.assertEqual(str(self.build_form(organization=organization, name='')), 'applicant: existing')

    def test_organization_is_not_created_by_submitting(self):
        self.build_form().save()
        self.assertFalse(Organization.objects.filter(slug='neworg').exists())
