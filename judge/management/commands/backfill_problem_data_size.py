import os

from django.conf import settings
from django.core.management.base import BaseCommand

from judge.models import ProblemData


class Command(BaseCommand):
    help = 'Backfill storage sizes for existing problems (test data + submission files)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without saving to database',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))

        problem_data_list = ProblemData.objects.all().iterator(chunk_size=5000)
        total_count = ProblemData.objects.count()
        updated_count = 0
        batch_size = 1000
        batch = []
        root = settings.DMOJ_PROBLEM_DATA_ROOT

        self.stdout.write(f'Processing {total_count} problems...\n')

        for problem_data in problem_data_list:
            old_zipfile_size = problem_data.zipfile_size
            total_size = 0

            # Calculate new sizes directly via OS to bypass Storage abstractions overhead
            for field in ['zipfile', 'generator', 'custom_checker', 'custom_grader', 'custom_header']:
                val = getattr(problem_data, field)
                if val and val.name:
                    path = os.path.join(root, val.name)
                    try:
                        total_size += os.path.getsize(path)
                    except (OSError, FileNotFoundError):
                        pass

            new_zipfile_size = total_size

            # Check if anything changed
            if old_zipfile_size != new_zipfile_size:
                problem_data.zipfile_size = new_zipfile_size
                batch.append(problem_data)
                updated_count += 1

                self.stdout.write(
                    f'Problem: {problem_data.problem_id}\n'
                    f'  Total Storage: {self._format_size(old_zipfile_size)} '
                    f'-> {self._format_size(new_zipfile_size)}\n',
                )

                if len(batch) >= batch_size and not dry_run:
                    ProblemData.objects.bulk_update(batch, ['zipfile_size'])
                    batch = []

        if batch and not dry_run:
            ProblemData.objects.bulk_update(batch, ['zipfile_size'])

        if dry_run:
            self.stdout.write(self.style.WARNING(f'\nDRY RUN: Would update {updated_count}/{total_count} problems'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\nSuccessfully updated {updated_count}/{total_count} problems'))

    def _format_size(self, size_bytes):
        """Format bytes into human-readable format."""
        if size_bytes == 0:
            return '0 B'

        units = ['B', 'KB', 'MB', 'GB', 'TB']
        unit_index = 0
        size = float(size_bytes)

        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1

        if unit_index == 0:
            return f'{int(size)} {units[unit_index]}'
        return f'{size:.2f} {units[unit_index]}'
