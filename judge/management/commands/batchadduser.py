import csv
import secrets

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from judge.models import Language, Profile

ALPHABET = 'abcdefghkqtxyz' + 'abcdefghkqtxyz'.upper() + '23456789'

DEFAULT_LANGUAGE = Language.objects.get(key=settings.DEFAULT_USER_LANGUAGE)


def generate_password():
    return ''.join(secrets.choice(ALPHABET) for _ in range(8))


def add_user(username, fullname, password, username_override):
    usr = User(username=username, first_name=fullname, is_active=True)
    usr.set_password(password)
    usr.save()

    profile = Profile(user=usr)
    profile.username_display_override = username_override
    profile.language = DEFAULT_LANGUAGE
    profile.save()


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

        has_username_override = 'username_override' in (reader.fieldnames or [])

        for row in reader:
            username = row['username']
            fullname = row['fullname']
            password = generate_password()
            username_override = row['username_override'] if has_username_override else username

            add_user(username, fullname, password, username_override)

            writer.writerow({
                'username': username,
                'fullname': fullname,
                'password': password,
            })

        fin.close()
        fout.close()
