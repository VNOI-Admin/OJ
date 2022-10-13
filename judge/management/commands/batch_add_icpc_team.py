import csv
import secrets

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from judge.models import Language, Organization, Profile

ALPHABET = 'abcdefghkqtxyz' + 'abcdefghkqtxyz'.upper() + '23456789'

def generate_password():
    return ''.join(secrets.choice(ALPHABET) for _ in range(8))


def add_user(username, teamname, password, org, internalid):
    usr = User(username=username, is_active=True)
    usr.set_password(password)
    usr.save()

    profile = Profile(user=usr)
    profile.username_display_override = teamname
    profile.language = Language.objects.get(key=settings.DEFAULT_USER_LANGUAGE)
    profile.notes = internalid  # save the internal id for later use.
    profile.save()
    profile.organizations.set([org])


def get_org(name):
    return Organization.objects.get_or_create(
        name=name,
        slug='icpc',
        short_name='icpc',
        is_open=False,
        is_unlisted=False)[0]


class Command(BaseCommand):
    help = 'batch create users'

    def add_arguments(self, parser):
        parser.add_argument('input', help='csv file containing username and teamname')
        parser.add_argument('output', help='where to store output csv file')

    def handle(self, *args, **options):
        fin = open(options['input'], 'r', encoding='utf-8')
        fout = open(options['output'], 'w', encoding='utf-8', newline='')

        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=['username', 'teamname', 'password'])
        writer.writeheader()

        for cnt, row in enumerate(reader, start=100):
            username = f'team{cnt}'
            teamname = row['name']
            org = get_org(row['instName'])
            password = generate_password()
            internalid = row['id']

            add_user(username, teamname, password, org, internalid)

            writer.writerow({
                'username': username,
                'teamname': teamname,
                'password': password,
            })

        fin.close()
        fout.close()
