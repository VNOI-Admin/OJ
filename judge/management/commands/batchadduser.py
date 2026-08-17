import csv
import secrets

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from judge.models import Language, Profile, Organization

ALPHABET = 'abcdefghkqtxyz' + 'abcdefghkqtxyz'.upper() + '23456789'


def generate_password():
    return ''.join(secrets.choice(ALPHABET) for _ in range(8))


def add_user(username, fullname, password, username_display=None, org=None, internal_id=None):
    usr = User(username=username, is_active=True)
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


class Command(BaseCommand):
    help = 'batch create users'

    def add_arguments(self, parser):
        parser.add_argument('input', help='csv file containing username and fullname')
        parser.add_argument('output', help='where to store output csv file')

    def handle(self, *args, **options):
        fin = open(options['input'], 'r')
        fout = open(options['output'], 'w', newline='')

        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=['username', 'fullname', 'password'])
        writer.writeheader()

        has_org = 'organization' in reader.fieldnames
        has_internal_id = 'internal_id' in reader.fieldnames
        has_username_display = 'username_display' in reader.fieldnames

        for row in reader:
            username = row['username']
            fullname = row['fullname']
            org = get_org(row['organization']) if has_org else None
            internal_id = row['internal_id'] if has_internal_id else None
            username_display = row['username_display'] if has_username_display else None
            password = generate_password()

            add_user(username, fullname, password, username_display=username_display, org=org, internal_id=internal_id)

            writer.writerow({
                'username': username,
                'fullname': fullname,
                'password': password,
            })

        fin.close()
        fout.close()
