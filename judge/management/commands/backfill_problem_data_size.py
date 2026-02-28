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

        problem_data_list = ProblemData.objects.select_related('problem').all()
        total_count = problem_data_list.count()
        updated_count = 0

        self.stdout.write(f'Processing {total_count} problems...\n')

        for problem_data in problem_data_list:
            problem_code = problem_data.problem.code
            old_zipfile_size = problem_data.zipfile_size

            # Calculate new sizes
            problem_data.update_zipfile_size()

            new_zipfile_size = problem_data.zipfile_size

            # Check if anything changed
            if old_zipfile_size != new_zipfile_size:
                updated_count += 1

                self.stdout.write(
                    f'Problem: {problem_code}\n'
                    f'  Test data: {self._format_size(old_zipfile_size)} -> {self._format_size(new_zipfile_size)}\n',
                )

                if not dry_run:
                    # Use update_fields to avoid triggering save hooks again
                    problem_data.save(update_fields=['zipfile_size'])

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
