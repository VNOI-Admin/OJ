import csv
import json
import os
import secrets

import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from judge.models import Language, Organization, Profile
from judge.models.profile import Badge

ALPHABET = 'abcdefghkqtxyz' + 'abcdefghkqtxyz'.upper() + '23456789'

LOGO_MAPPING = {
    x['uniName']:
        x['logoURL']
        for x in json.loads(requests.get('https://raw.githubusercontent.com/VNOI-Admin/uni-logo/master/data.json').text)
}


def generate_password():
    return ''.join(secrets.choice(ALPHABET) for _ in range(8))


def add_user(username, teamname, password, org, org_group, internalid, badge):
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
    if badge is not None:
        profile.display_badge = badge
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


def get_badge(country):
    badge = Badge.objects.get_or_create(
        name=country,
        mini=f'/martor/flag/{country}.png',
        full_size=f'/martor/flag/{country}.png',
    )[0]
    return badge


class Command(BaseCommand):
    help = 'batch create users'

    def add_arguments(self, parser):
        parser.add_argument('input', help='csv file containing username and teamname')
        parser.add_argument('output', help='where to store output csv file')
        parser.add_argument('prefix', help='prefix for username', type=str, nargs='?', default='')
        parser.add_argument('--practice', action='store_true', help='also generate practice accounts with p_ prefix')

    def handle(self, *args, **options):
        fin = open(options['input'], 'r', encoding='utf-8')
        # if output file exists, ask for confirmation
        if os.path.exists(options['output']):
            if not input('Output file exists, overwrite? (y/n) ').lower().startswith('y'):
                return

        fout = open(options['output'], 'w', encoding='utf-8', newline='')
        prefix = options['prefix']
        create_practice = options['practice']

        reader = csv.DictReader(fin)

        fieldnames = ['id', 'username', 'teamname', 'password', 'org', 'email']
        if create_practice:
            fieldnames.extend(['practice_username', 'practice_password'])
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()

        done_team_ids = set()
        has_email = 'email' in reader.fieldnames
        has_group = 'group' in reader.fieldnames
        has_country = 'country' in reader.fieldnames
        processed_count = 0

        for cnt, row in enumerate(reader, start=1):
            username = f'{prefix}{cnt}'.lower()
            teamname = row['name']
            org = get_org(row['instName'])
            password = generate_password()
            internalid = row['id']
            org_group = row['group'] if has_group else None
            email = row['email'] if has_email else None
            badge = get_badge(row['country']) if has_country else None
            if internalid in done_team_ids:
                continue
            done_team_ids.add(internalid)

            add_user(username, teamname, password, org, org_group, internalid, badge)
            processed_count += 1

            output_row = {
                'id': internalid,
                'username': username,
                'teamname': teamname,
                'password': password,
                'org': org,
                'email': email if has_email else '',
            }

            if create_practice:
                practice_username = f'p_{username}'
                practice_password = generate_password()
                add_user(practice_username, teamname, practice_password, org, org_group, internalid)
                output_row['practice_username'] = practice_username
                output_row['practice_password'] = practice_password

            writer.writerow(output_row)

            if processed_count % 10 == 0:
                print(f'Processed {processed_count} teams...')

        fin.close()
        fout.close()

        accounts_created = processed_count * 2 if create_practice else processed_count
        print(f'\nCompleted! Processed {processed_count} teams, created {accounts_created} accounts total.')
