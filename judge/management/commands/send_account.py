import csv
import time

from django.conf import settings
from django.core import mail
from django.core.management.base import BaseCommand
from django.template import loader
from django.utils.html import strip_tags

from judge.models import Profile


def send_account(team_uni, team_name, username, password, receiver_emails):
    html_message = loader.render_to_string('send_account_mail.html', {
        'teamuni': team_uni,
        'teamname': team_name,
        'teamusername': username,
        'teampassword': password,
    })
    subject = f'{team_name} - Thông tin tài khoản thi ICPC Miền Trung 2023'
    plain_message = strip_tags(html_message)

    mail.send_mail(subject, plain_message, settings.SERVER_EMAIL, receiver_emails, html_message=html_message)


class Command(BaseCommand):
    help = 'send email'

    def add_arguments(self, parser):
        parser.add_argument('input', help='csv file containing username and teamname')
        pass

    def handle(self, *args, **options):
        fin = open(options['input'], 'r', encoding='utf-8')

        reader = csv.DictReader(fin)
        team_email_map = {}
        for row in reader:
            email = row['email']
            teamname: str = row['teamname']
            username: str = row['username']
            password: str = row['password']

            # create a map from (username) to: (teamname, password, emails)
            if username not in team_email_map:
                team_email_map[username] = (teamname, password, [email])
            else:
                team_email_map[username][2].append(email)

        for username in team_email_map:
            print('Processing', username)
            p = Profile.objects.filter(user__username=username)[0]
            teamname, password, emails = team_email_map[username]

            print('Processing', username, 'sending to', emails)
            send_account(p.organization.name, teamname, username, password, emails)
            time.sleep(2)
