import csv

from django.core.management.base import BaseCommand

from judge.utils.users import add_user, generate_password, get_org


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
