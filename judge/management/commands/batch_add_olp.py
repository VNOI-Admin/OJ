import csv
import os
import secrets

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from judge.models import Language, Organization, Profile

ALPHABET = 'abcdefghkqtxyz' + 'abcdefghkqtxyz'.upper() + '23456789'


def generate_password():
    return ''.join(secrets.choice(ALPHABET) for _ in range(8))


def add_user(username, fullname, password, org):
    usr = User(username=username, is_active=True)
    usr.set_password(password)
    usr.save()

    profile = Profile(user=usr)
    profile.username_display_override = fullname
    profile.language = Language.objects.get(key=settings.DEFAULT_USER_LANGUAGE)
    profile.site_theme = 'light'
    profile.save()
    profile.organizations.set([org])


def get_org(name):
    org_id = abs(hash(name) % 1000000007)

    org = Organization.objects.get_or_create(
        name=name,
        slug='olp' + str(org_id),
        short_name='olp' + str(org_id),
        is_open=False,
        is_unlisted=False)[0]
    return org


class Command(BaseCommand):
    help = 'batch create users'

    def add_arguments(self, parser):
        parser.add_argument('input', help='csv file containing username and teamname')
        parser.add_argument('output', help='where to store output csv file')
        parser.add_argument('prefix', help='prefix for username')

    def handle(self, *args, **options):
        fin = open(options['input'], 'r', encoding='utf-8')
        # if output file exists, ask for confirmation
        if os.path.exists(options['output']):
            if not input('Output file exists, overwrite? (y/n) ').lower().startswith('y'):
                return
        fout = open(options['output'], 'w', encoding='utf-8', newline='')
        prefix = options['prefix']

        reader = csv.DictReader(fin)

        writer = csv.DictWriter(fout, fieldnames=['username', 'fullname', 'password'])
        writer.writeheader()

        for row in reader:
            username = row['username']

            username = f'{prefix}{username}'.lower()
            fullname = row['name']
            org = get_org(row['org'])
            password = generate_password()

            add_user(username, fullname, password, org)

            writer.writerow({
                'username': username,
                'fullname': fullname,
                'password': password,
            })

        fin.close()
        fout.close()
