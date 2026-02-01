import os

from django.conf import settings
from django.core.management.base import BaseCommand

from judge.models import Problem


class Command(BaseCommand):
    help = 'backfill data_size for all problems by calculating ZIP file sizes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--update-all',
            action='store_true',
            help='Update all problems including those with non-zero data_size',
        )

    def calculate_problem_data_size(self, problem):
        """Calculate the size of the test data ZIP file for a problem."""
        if not settings.DMOJ_PROBLEM_DATA_ROOT:
            return 0

        # Construct path to the test data ZIP file
        zip_path = os.path.join(
            settings.DMOJ_PROBLEM_DATA_ROOT,
            problem.code,
            'testdata.zip',
        )

        if os.path.exists(zip_path) and os.path.isfile(zip_path):
            return os.path.getsize(zip_path)
        return 0

    def handle(self, *args, **options):
        update_all = options['update_all']

        if update_all:
            problems = Problem.objects.all()
            self.stdout.write('Updating data_size for all problems...')
        else:
            problems = Problem.objects.filter(data_size=0)
            self.stdout.write('Updating data_size for problems with zero size...')

        total_problems = problems.count()
        updated_count = 0
        skipped_count = 0

        for idx, problem in enumerate(problems, 1):
            if idx % 100 == 0:
                self.stdout.write(f'Processed {idx}/{total_problems} problems...')

            new_size = self.calculate_problem_data_size(problem)

            if new_size != problem.data_size:
                problem.data_size = new_size
                problem.save(update_fields=['data_size'])
                updated_count += 1
            else:
                skipped_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully updated {updated_count} problems, skipped {skipped_count}',
            ),
        )
