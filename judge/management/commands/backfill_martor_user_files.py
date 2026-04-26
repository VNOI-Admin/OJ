import os
import re

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction

from judge.models import Contest, FileUsage, Problem, UserFile


class Command(BaseCommand):
    help = 'Backfill UserFile entries for existing martor uploads referenced by problems.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without saving to database',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of files to create',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))

        pattern = re.compile(r'\((?P<url>/martor/[^)\s]+)\)')
        base_prefix = settings.MARTOR_UPLOAD_URL_PREFIX.rstrip('/') + '/'

        created = 0
        processed = 0

        def backfill_problem(problem):
            nonlocal created, processed

            matches = pattern.findall(problem.description or '')
            if not matches:
                return

            for url in matches:
                filename = os.path.basename(url)
                if not filename:
                    continue

                storage_path = os.path.join(settings.MARTOR_UPLOAD_MEDIA_DIR, filename)
                if not default_storage.exists(storage_path):
                    continue

                processed += 1
                if limit and created >= limit:
                    break

                if dry_run:
                    self.stdout.write(
                        f'Would create UserFile for {storage_path} (problem {problem.code})',
                    )
                    created += 1
                    continue

                with transaction.atomic():
                    user_profile = problem.suggester or (problem.authors.first() if problem.authors.exists() else None)
                    if user_profile is None:
                        continue

                    content = default_storage.open(storage_path, 'rb').read()
                    content_file = ContentFile(content, name=filename)

                    user_file = UserFile.objects.create(
                        user=user_profile,
                        file=content_file,
                        filename=filename,
                        file_type='image',
                        storage_scope=UserFile.STORAGE_SCOPE_PROBLEM,
                        is_public=problem.is_public,
                    )

                    FileUsage.objects.create(
                        file=user_file,
                        usage_type='markdown_content',
                        problem_id=problem.id,
                        context_description=f'Problem {problem.code} description',
                    )

                created += 1

        def backfill_contest(contest):
            nonlocal created, processed

            matches = pattern.findall(contest.description or '')
            if not matches:
                return

            for url in matches:
                filename = os.path.basename(url)
                if not filename:
                    continue

                storage_path = os.path.join(settings.MARTOR_UPLOAD_MEDIA_DIR, filename)
                if not default_storage.exists(storage_path):
                    continue

                processed += 1
                if limit and created >= limit:
                    break

                if dry_run:
                    self.stdout.write(
                        f'Would create UserFile for {storage_path} (contest {contest.key})',
                    )
                    created += 1
                    continue

                with transaction.atomic():
                    user_profile = contest.authors.first()
                    if user_profile is None and contest.curators.exists():
                        user_profile = contest.curators.first()
                    if user_profile is None:
                        continue

                    content = default_storage.open(storage_path, 'rb').read()
                    content_file = ContentFile(content, name=filename)

                    user_file = UserFile.objects.create(
                        user=user_profile,
                        file=content_file,
                        filename=filename,
                        file_type='image',
                        storage_scope=UserFile.STORAGE_SCOPE_CONTEST,
                        is_public=contest.is_visible and not contest.is_private,
                    )

                    FileUsage.objects.create(
                        file=user_file,
                        usage_type='markdown_content',
                        contest_id=contest.id,
                        context_description=f'Contest {contest.key} description',
                    )

                created += 1

        for problem in Problem.objects.only('id', 'code', 'description', 'is_public', 'suggester_id').iterator():
            backfill_problem(problem)
            if limit and created >= limit:
                break

        if not limit or created < limit:
            for contest in Contest.objects.only('id', 'key', 'description', 'is_visible', 'is_private').iterator():
                backfill_contest(contest)
                if limit and created >= limit:
                    break

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'DRY RUN: Would create {created} UserFile entries (processed {processed} links)',
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Successfully created {created} UserFile entries (processed {processed} links)',
            ))
