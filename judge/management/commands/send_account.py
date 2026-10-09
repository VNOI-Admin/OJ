from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand, CommandError

from judge.utils.users import ACCOUNT_EMAIL_SUBJECT, build_account_email, check_account_rows, read_account_rows


class Command(BaseCommand):
    help = 'Send account credentials to teams via email'

    def add_arguments(self, parser):
        parser.add_argument('input', help='CSV or XLSX file with columns: username,password')
        parser.add_argument('--subject', default=ACCOUNT_EMAIL_SUBJECT, help='Email subject / contest name')
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

        try:
            with open(options['input'], 'rb') as f:
                rows = read_account_rows(f, options['input'])
        except ValueError as e:
            raise CommandError(str(e))

        profiles, errors = check_account_rows(rows)
        if errors:
            for username, error in errors:
                self.stderr.write(f'{username}: {error}' if username else error)
            self.stderr.write(self.style.ERROR(f'Validation failed for {len(errors)} issue(s). Aborted.'))
            return

        def email_of(row):
            return build_account_email(row, profiles[row['username']], subject, is_practice, domain)

        # Preview first email before bulk send
        preview = email_of(rows[0])
        preview.subject = f'[PREVIEW] {preview.subject}'
        if preview_console:
            self.stdout.write(f'To: {preview.to[0]}')
            self.stdout.write(f'Subject: {preview.subject}')
            self.stdout.write('')
            self.stdout.write(preview.body)
        if test_email:
            preview.to = [test_email]
            preview.send()
            self.stdout.write(f'Preview sent to {test_email}')

        confirm = input(f'Send to all {len(rows)} recipient(s)? [y/N] ')
        if confirm.strip().lower() != 'y':
            self.stdout.write('Aborted.')
            return

        for row in rows:
            msg = email_of(row)
            msg.send()
            self.stdout.write(f'Sent → {msg.to[0]}')

        self.stdout.write(self.style.SUCCESS(f'Done. {len(rows)} email(s) sent.'))
