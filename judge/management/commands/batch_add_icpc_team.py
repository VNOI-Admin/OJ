import csv
import json
import os
import secrets

import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from judge.models import Language, Organization, Profile

ALPHABET = 'abcdefghkqtxyz' + 'abcdefghkqtxyz'.upper() + '23456789'

LOGO_MAPPING = {
    x['uniName']:
        x['logoURL']
        for x in json.loads(requests.get('https://raw.githubusercontent.com/VNOI-Admin/uni-logo/master/data.json').text)
}


def generate_password():
    return ''.join(secrets.choice(ALPHABET) for _ in range(8))


def add_user(username, teamname, password, org, org_group, internalid):
    usr = User(username=username, is_active=True)
    usr.set_password(password)
    usr.save()

    profile = Profile(user=usr)
    profile.username_display_override = teamname
    profile.language = Language.objects.get(key=settings.DEFAULT_USER_LANGUAGE)
    profile.site_theme = 'light'
    profile.notes = internalid  # save the internal id for later use.
    if org_group is not None:
        profile.group = org_group
    profile.save()
    profile.organizations.set([org])


def get_org(name):
    org_id = abs(hash(name) % 1000000007)

    logo = LOGO_MAPPING.get(name, 'unk.png')
    org = Organization.objects.get_or_create(
        name=name,
        slug='icpc' + str(org_id),
        short_name='icpc' + str(org_id),
        is_open=False,
        is_unlisted=False,
    )[0]
    if not org.logo_override_image:
        org.logo_override_image = f'/martor/logo/{logo}'
        org.save()
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
        writer = csv.DictWriter(fout, fieldnames=['id', 'username', 'teamname', 'password', 'org', 'email'])
        writer.writeheader()

        done_team_ids = set()
        has_email = 'email' in reader.fieldnames
        has_group = 'group' in reader.fieldnames

        for cnt, row in enumerate(reader, start=1):
            username = f'{prefix}{cnt}'.lower()
            teamname = row['name']
            org = get_org(row['instName'])
            password = generate_password()
            internalid = row['id']
            org_group = row['group'] if has_group else None
            email = row['email'] if has_email else None

            if internalid in done_team_ids:
                continue
            done_team_ids.add(internalid)

            add_user(username, teamname, password, org, org_group, internalid)

            writer.writerow({
                'id': internalid,
                'username': username,
                'teamname': teamname,
                'password': password,
                'org': org,
                'email': email if has_email else '',
            })

        fin.close()
        fout.close()
