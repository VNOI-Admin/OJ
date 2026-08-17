import re
import secrets

from django.conf import settings
from django.contrib.auth.models import User
from django.utils.translation import gettext as _

from judge.models import Language, Organization, Profile

ALPHABET = 'abcdefghkqtxyz' + 'abcdefghkqtxyz'.upper() + '23456789'
USERNAME_RE = re.compile(r'^[a-zA-Z0-9_]+$')


def generate_password():
    return ''.join(secrets.choice(ALPHABET) for _ in range(8))


def add_user(username, fullname, password, username_display=None, org=None, internal_id=None):
    usr = User(username=username, first_name=fullname or username, is_active=True)
    usr.set_password(password)
    usr.save()

    profile = Profile(user=usr)

    if username_display:
        profile.username_display_override = username_display

    profile.language = Language.objects.get(key=settings.DEFAULT_USER_LANGUAGE)
    profile.site_theme = 'light'
    if internal_id:
        profile.notes = internal_id  # save the internal id for later use.
    profile.save()
    if org:
        profile.organizations.set([org])


def get_org(name):
    org_id = abs(hash(name) % 1000000007)

    org = Organization.objects.get_or_create(
        name=name,
        slug='org' + str(org_id),
        short_name='org' + str(org_id),
        is_open=False,
        is_unlisted=False)[0]
    return org


def validate_user_rows(rows):
    """Validate rows (list of dicts keyed by field name). Returns an error string or None.

    Only username is required; fullname defaults to username at creation time.
    """
    if not rows:
        return _('No user data provided')

    seen_usernames = set()
    usernames = [str(r.get('username', '')).strip() for r in rows]
    existing = User.objects.filter(username__in=[u for u in usernames if u])
    if existing.exists():
        return _('Some usernames already exist in the database: %s') % \
            ', '.join(existing.values_list('username', flat=True))

    for i, row in enumerate(rows):
        row_num = i + 1
        username = str(row.get('username', '')).strip()

        if not username:
            return _('Row %d: Username is required') % row_num
        if not USERNAME_RE.match(username):
            return _('Row %d: Username can only contain letters, numbers, and underscores') % row_num
        if len(username) > 20:
            return _('Row %d: Username cannot be longer than 20 characters') % row_num
        if username in seen_usernames:
            return _('Row %d: Username "%s" appears multiple times') % (row_num, username)
        seen_usernames.add(username)

    return None
