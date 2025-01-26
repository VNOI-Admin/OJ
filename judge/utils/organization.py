from django.conf import settings
from django.contrib.auth.models import Group


def add_admin_to_group(form):
    org = form.save()
    all_admins = org.admins.all()
    g = Group.objects.get(name=settings.GROUP_PERMISSION_FOR_ORG_ADMIN)
    for admin in all_admins:
        admin.user.groups.add(g)
