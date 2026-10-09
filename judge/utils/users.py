import csv
import io
import re
import secrets

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMessage
from django.db.models import Count
from django.template.loader import render_to_string
from django.utils.translation import gettext as _

from judge.models import Language, Organization, Profile
from judge.models.profile import Badge

ALPHABET = 'abcdefghkqtxyz' + 'abcdefghkqtxyz'.upper() + '23456789'
USERNAME_RE = re.compile(r'^[a-zA-Z0-9_]+$')


def generate_password():
    return ''.join(secrets.choice(ALPHABET) for _ in range(8))


def fetch_org_logo_mapping():
    """Fetch org-name → logo path mapping from the VNOI uni-logo repo. Returns {} on failure."""
    try:
        import requests
        data = requests.get(
            'https://raw.githubusercontent.com/VNOI-Admin/uni-logo/master/data.json',
            timeout=10,
        ).json()
        return {x['uniName']: f'/martor/logo/{x["logoURL"]}' for x in data}
    except Exception:
        return {}


def get_badge(country):
    badge, _ = Badge.objects.get_or_create(
        name=country,
        defaults={
            'mini': f'/martor/flag/{country}.png',
            'full_size': f'/martor/flag/{country}.png',
        },
    )
    return badge


def add_user(username, fullname, password, username_display=None, org=None, internal_id=None,
             email=None, group=None, badge=None):
    usr = User(username=username, first_name=fullname or username, is_active=True)
    if email:
        usr.email = email
    usr.set_password(password)
    usr.save()

    profile = Profile(user=usr)

    if username_display:
        profile.username_display_override = username_display

    profile.language = Language.objects.get(key=settings.DEFAULT_USER_LANGUAGE)
    profile.site_theme = 'light'
    if internal_id:
        profile.notes = internal_id  # save the internal id for later use.
    if group:
        profile.group = group
    if badge:
        profile.display_badge = badge
    profile.save()
    if org:
        profile.organizations.set([org])


def get_org(name, logo=None):
    try:
        org = Organization.objects.get(name=name)
    except Organization.DoesNotExist:
        org_id = abs(hash(name) % 1000000007)
        org = Organization.objects.get_or_create(
            name=name,
            slug='org' + str(org_id),
            short_name='org' + str(org_id),
            is_open=False,
            is_unlisted=False,
        )[0]
    if logo and not org.logo_override_image:
        org.logo_override_image = logo
        org.save()
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
        if len(str(row.get('organization', '')).strip()) > 128:
            return _('Row %d: Organization cannot be longer than 128 characters') % row_num
        if len(str(row.get('country', '')).strip()) > 128:
            return _('Row %d: Country cannot be longer than 128 characters') % row_num
        # Extra columns copied into the result, as [name, value] pairs.
        extra = row.get('extra', [])
        if not isinstance(extra, list) or not all(isinstance(e, list) and len(e) == 2 for e in extra):
            return _('Row %d: Invalid extra columns') % row_num

    # get_org() / get_badge() look these up by name, which is not unique, and fail on duplicates.
    for model, field, message in (
        (Organization, 'organization', _('Multiple organizations share the name: %s')),
        (Badge, 'country', _('Multiple badges share the name: %s')),
    ):
        names = {str(r.get(field, '')).strip() for r in rows} - {''}
        duplicates = model.objects.filter(name__in=names).values('name') \
            .annotate(count=Count('id')).filter(count__gt=1).values_list('name', flat=True)
        if duplicates:
            return message % ', '.join(duplicates)

    return None


ACCOUNT_EMAIL_SUBJECT = 'ICPC Contest'


def read_account_rows(file, name):
    """Read a .csv or .xlsx (first sheet) binary file into a list of dicts keyed by the header row."""
    if not name.lower().endswith('.xlsx'):
        return list(csv.DictReader(io.TextIOWrapper(file, encoding='utf-8-sig', newline='')))

    try:
        import openpyxl
    except ImportError:
        raise ValueError('Reading .xlsx files requires openpyxl: pip install openpyxl')
    sheet = openpyxl.load_workbook(file, read_only=True, data_only=True).active
    rows = [['' if cell is None else str(cell).strip() for cell in row] for row in sheet.iter_rows(values_only=True)]
    if not rows:
        return []
    return [dict(zip(rows[0], row)) for row in rows[1:] if any(row)]


def check_account_rows(rows):
    """Check rows (dicts with username, password) can be emailed.

    Returns (profiles by username, list of (username, error message)).
    """
    if not rows:
        return {}, [('', 'No rows found')]
    missing = {'username', 'password'} - rows[0].keys()
    if missing:
        return {}, [('', f'Missing column(s): {", ".join(sorted(missing))}')]

    usernames = [row['username'] for row in rows]
    profiles = {
        p.user.username: p
        for p in Profile.objects.filter(user__username__in=usernames)
                                .select_related('user').prefetch_related('organizations')
    }

    errors = []
    seen = set()
    for username in usernames:
        if username in seen:
            errors.append((username, 'appears more than once'))
        seen.add(username)
        profile = profiles.get(username)
        if profile is None:
            errors.append((username, 'user not found'))
            continue
        org_count = len(profile.organizations.all())
        if org_count != 1:
            errors.append((username, f'belongs to {org_count} organizations (expected exactly 1)'))
        if not profile.user.email:
            errors.append((username, 'no email address'))
    return profiles, errors


def build_account_email(row, profile, subject, is_practice, domain):
    """Returns an unsent EmailMessage with the account credentials in row."""
    body = render_to_string('send_account_email.html', {
        'subject': subject,
        'domain': domain,
        'teamuni': profile.organizations.all()[0].name,
        'teamname': profile.user.first_name,
        'teamusername': row['username'],
        'teampassword': row['password'],
        'is_practice': is_practice,
    })
    msg = EmailMessage(subject=f'{subject} - {profile.user.first_name}', body=body, to=[profile.user.email])
    msg.content_subtype = 'html'
    return msg
