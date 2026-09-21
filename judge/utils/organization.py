from django.conf import settings
from django.contrib.auth.models import Group
from django.shortcuts import render
from django.template.defaultfilters import filesizeformat
from django.utils import timezone
from django.utils.translation import gettext as _
from reversion import revisions

from judge.models import Organization, OrganizationRegistrationForm, Problem, make_notification


def archived_problems_queryset(organization):
    """The problems listed on the Archived problems tab, before annotation and ordering.

    The permalink ranks over this same set to work out which page a problem lands on, so the two
    must not be allowed to drift apart.
    """
    return Problem.available.filter(organization=organization, archived_at__isnull=False)


def quota_error_response(request, organization):
    return render(request, 'organization/quota-error.html', {
        'title': _('Problem limit reached'),
        'message': _('This organization has reached its maximum number of problems (%d) and/or storage (%s). '
                     'Please delete some problems or free up storage before creating new ones.')
        % (organization.max_problems, filesizeformat(organization.max_storage)),
        'quota_warning_suffix': settings.VNOJ_QUOTA_WARNING_SUFFIX,
    })


def add_quota_context(org, context, total_storage=None):
    threshold = settings.VNOJ_QUOTA_WARNING_THRESHOLD
    max_storage = org.max_storage
    max_problems = org.max_problems
    current_storage = org.current_storage if total_storage is None else total_storage
    problem_count = org.current_problem_count

    storage_exceeded = current_storage >= max_storage
    problem_limit_reached = problem_count >= max_problems

    context['max_storage'] = max_storage
    context['max_problems'] = max_problems
    context['current_storage'] = current_storage
    context['problem_count'] = problem_count
    context['storage_exceeded'] = storage_exceeded
    context['problem_limit_reached'] = problem_limit_reached
    context['storage_warning'] = (
        not storage_exceeded and
        max_storage > 0 and
        current_storage / max_storage >= threshold
    )
    context['problem_warning'] = (
        not problem_limit_reached and
        max_problems > 0 and
        problem_count / max_problems >= threshold
    )
    context['quota_warning_suffix'] = settings.VNOJ_QUOTA_WARNING_SUFFIX


def add_admin_to_group(form):
    org = form.save()
    all_admins = org.admins.all()
    g = Group.objects.get(name=settings.GROUP_PERMISSION_FOR_ORG_ADMIN)
    for admin in all_admins:
        admin.user.groups.add(g)


def approve_organization_registration(registration, reviewer):
    """Approve a pending registration form, creating its organization when it asks for a new one."""
    if registration.state != OrganizationRegistrationForm.State.PENDING:
        return

    with revisions.create_revision(atomic=True):
        revisions.set_comment(_('Created from an organization registration form'))
        revisions.set_user(reviewer.user)

        if registration.is_new_organization:
            organization = Organization(
                name=registration.name,
                slug=registration.slug,
                short_name=registration.short_name,
                about=registration.about,
            )
            organization.free_credit = organization.monthly_free_credit_limit
            organization.save()
            organization.admins.add(registration.user)
            org_admin_group, _created = Group.objects.get_or_create(name=settings.GROUP_PERMISSION_FOR_ORG_ADMIN)
            registration.user.user.groups.add(org_admin_group)
            registration.organization = organization

        registration.state = OrganizationRegistrationForm.State.APPROVED
        registration.reviewer = reviewer
        registration.review_time = timezone.now()
        registration.save(update_fields=['organization', 'state', 'reviewer', 'review_time', 'review_note'])

    make_notification(
        [registration.user], _('Organization registration approved'), registration.review_note,
        registration.organization.get_absolute_url(),
    )


def reject_organization_registration(registration, reviewer, note=''):
    """Reject a pending registration form, telling the applicant why."""
    if registration.state != OrganizationRegistrationForm.State.PENDING:
        return

    registration.state = OrganizationRegistrationForm.State.REJECTED
    registration.reviewer = reviewer
    registration.review_time = timezone.now()
    registration.review_note = note
    registration.save(update_fields=['state', 'reviewer', 'review_time', 'review_note'])

    make_notification(
        [registration.user], _('Organization registration rejected'), note, registration.get_absolute_url(),
    )
