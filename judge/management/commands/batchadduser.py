import csv
import secrets
import string

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from judge.models import Language, Profile

ALPHABET = string.ascii_letters + string.digits


def generate_password():
    return ''.join(secrets.choice(ALPHABET) for _ in range(8))


def add_user(username, fullname, password):
    usr = User(username=username, first_name=fullname, is_active=True)
    usr.set_password(password)
    usr.save()

    profile = Profile(user=usr)
    profile.language = Language.objects.get(key=settings.DEFAULT_USER_LANGUAGE)
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

        for row in reader:
            username = row['username']
            fullname = row['fullname']
            password = generate_password()

            add_user(username, fullname, password)

            writer.writerow({
                'username': username,
                'fullname': fullname,
                'password': password,
            })

        fin.close()
        fout.close()
