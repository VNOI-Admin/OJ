import csv

from django.core.management.base import BaseCommand

from judge.utils.user import add_user


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

            password = add_user(username, fullname, overwrite_existing=False)

            writer.writerow({
                'username': username,
                'fullname': fullname,
                'password': password,
            })

        fin.close()
        fout.close()
