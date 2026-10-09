import csv

from django.contrib.sites.models import Site
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError
from django.template.loader import render_to_string

from judge.models import Profile


ICPC_CONTEST_NAME = 'ICPC Contest'


class Command(BaseCommand):
    help = 'Send account credentials to teams via email'

    def add_arguments(self, parser):
        parser.add_argument('input', help='CSV file with columns: username,password')
        parser.add_argument('--subject', default=ICPC_CONTEST_NAME, help='Email subject / contest name')
        parser.add_argument('--is-practice', action='store_true', default=False, help='Mark as practice account')
        parser.add_argument('--test-email', help='Send preview of first email here before bulk send')
        parser.add_argument('--preview-console', action='store_true', default=False,
                            help='Print preview of first email to console before bulk send')

    def handle(self, *args, **options):
        domain = Site.objects.first().domain
        subject = options['subject']
        is_practice = options['is_practice']
        test_email = options['test_email']
        preview_console = options['preview_console']

        if not test_email and not preview_console:
            raise CommandError('Specify --test-email and/or --preview-console to preview before bulk send.')

        with open(options['input'], newline='') as f:
            rows = list(csv.DictReader(f))

        if not rows:
            self.stderr.write('No rows found.')
            return

        usernames = [row['username'] for row in rows]
        profiles = {
            p.user.username: p
            for p in Profile.objects.filter(user__username__in=usernames)
                                    .select_related('user').prefetch_related('organizations')
        }

        errors = []
        for username in usernames:
            profile = profiles.get(username)
            if profile is None:
                errors.append(f'{username}: user not found')
                continue
            org_count = len(profile.organizations.all())
            if org_count != 1:
                errors.append(f'{username}: belongs to {org_count} organizations (expected exactly 1)')
            if not profile.user.email:
                errors.append(f'{username}: no email address')
        if errors:
            for error in errors:
                self.stderr.write(error)
            self.stderr.write(self.style.ERROR(f'Validation failed for {len(errors)} issue(s). Aborted.'))
            return

        def build_context(row):
            profile = profiles[row['username']]
            return {
                'subject': subject,
                'domain': domain,
                'teamuni': profile.organizations.all()[0].name,
                'teamname': profile.user.first_name,
                'teamusername': row['username'],
                'teampassword': row['password'],
                'is_practice': is_practice,
            }

        def subject_of(row):
            return f'{subject} - {profiles[row["username"]].user.first_name}'

        def email_of(row):
            return profiles[row['username']].user.email

        # Preview first email before bulk send
        first = rows[0]
        preview_subject = f'[PREVIEW] {subject_of(first)}'
        preview_html = render_to_string('send_account_email.html', build_context(first))
        if preview_console:
            self.stdout.write(f'To: {email_of(first)}')
            self.stdout.write(f'Subject: {preview_subject}')
            self.stdout.write('')
            self.stdout.write(preview_html)
        if test_email:
            msg = EmailMessage(subject=preview_subject, body=preview_html, to=[test_email])
            msg.content_subtype = 'html'
            msg.send()
            self.stdout.write(f'Preview sent to {test_email}')

        confirm = input(f'Send to all {len(rows)} recipient(s)? [y/N] ')
        if confirm.strip().lower() != 'y':
            self.stdout.write('Aborted.')
            return

        for row in rows:
            body = render_to_string('send_account_email.html', build_context(row))
            msg = EmailMessage(subject=subject_of(row), body=body, to=[email_of(row)])
            msg.content_subtype = 'html'
            msg.send()
            self.stdout.write(f'Sent → {email_of(row)}')

        self.stdout.write(self.style.SUCCESS(f'Done. {len(rows)} email(s) sent.'))
