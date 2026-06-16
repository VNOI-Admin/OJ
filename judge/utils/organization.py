from django.conf import settings
from django.contrib.auth.models import Group


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
