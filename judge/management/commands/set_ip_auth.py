import json
from django.core.management.base import BaseCommand

from judge.models import Profile


class Command(BaseCommand):
    help = 'Set IP authentication for users from a JSON file'

    def add_arguments(self, parser):
        parser.add_argument('file', help='Path to JSON file containing username and vpnIpAddress')

    def handle(self, *args, **options):
        file_path = options['file']

        data = json.load(open(file_path, 'r'))

        updated_count = 0
        error_count = 0
        not_found_count = 0

        for entry in data:
            username = entry.get('username')
            ip_address = entry.get('vpnIpAddress')

            if not username or not ip_address:
                self.stderr.write(self.style.WARNING(
                    f'Skipping entry with missing username or vpnIpAddress: {entry}'
                ))
                error_count += 1
                continue

            try:
                profile = Profile.objects.get(user__username=username)
                profile.ip_auth = ip_address
                profile.save(update_fields=['ip_auth'])
                updated_count += 1
            except Profile.DoesNotExist:
                self.stderr.write(self.style.WARNING(
                    f'User not found: {username}'
                ))
                not_found_count += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f'Error updating {username}: {e}'
                ))
                error_count += 1

        self.stdout.write(self.style.SUCCESS(f'Total entries processed: {len(data)}'))
        self.stdout.write(self.style.SUCCESS(f'Successfully updated: {updated_count}'))
        if not_found_count > 0:
            self.stdout.write(self.style.WARNING(f'Users not found: {not_found_count}'))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))
