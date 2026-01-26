from django.conf import settings
from django.contrib.auth.models import Group


def add_admin_to_group(form):
    org = form.save()
    all_admins = org.admins.all()
    g = Group.objects.get(name=settings.GROUP_PERMISSION_FOR_ORG_ADMIN)
    for admin in all_admins:
        admin.user.groups.add(g)


def rename_organization_contests(organization, old_slug, new_slug):
    from judge.models import Contest

    # Generate old and new prefixes (alphanumeric characters only)
    old_prefix = ''.join(x for x in old_slug.lower() if x.isalnum()) + '_'
    new_prefix = ''.join(x for x in new_slug.lower() if x.isalnum()) + '_'

    if old_prefix == new_prefix:
        return 0

    # Find all contests belonging to this organization that start with the old prefix
    org_contests = Contest.objects.filter(
        organizations=organization,
        is_organization_private=True,
        key__startswith=old_prefix,
    )

    renamed_count = 0
    for contest in org_contests:
        # Replace the old prefix with the new prefix
        new_key = new_prefix + contest.key[len(old_prefix):]

        # Check if the new key already exists
        if not Contest.objects.filter(key=new_key).exists():
            contest.key = new_key
            contest.save()
            renamed_count += 1

    return renamed_count
