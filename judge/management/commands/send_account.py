import csv
import time

from django.conf import settings
from django.core import mail
from django.core.management.base import BaseCommand
from django.template import loader
from django.utils.html import strip_tags

from judge.models import Profile


def send_account(team_uni, team_name, username, password, coach_email):
    html_message = loader.render_to_string('send_account_mail.html', {
        'teamuni': team_uni,
        'teamname': team_name,
        'teamusername': username,
        'teampassword': password,
    })
    subject = f'{team_name} - Thông tin tài khoản thi ICPC Miền Bắc 2022'
    plain_message = strip_tags(html_message)

    mail.send_mail(subject, plain_message, settings.SERVER_EMAIL, [coach_email], html_message=html_message)


class Command(BaseCommand):
    help = 'send email'

    def add_arguments(self, parser):
        parser.add_argument('input', help='csv file containing username and teamname')
        pass

    def handle(self, *args, **options):
        fin = open(options['input'], 'r', encoding='utf-8')

        reader = csv.DictReader(fin)
        for row in reader:
            email = row['email']
            teamname = row['teamname']
            username = row['username']
            print('Processing', username)
            password = row['password']
            p = Profile.objects.filter(user__username=username)[0]
            send_account(p.organization.name, teamname, username, password, email)
            time.sleep(2)
