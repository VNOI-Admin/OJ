import csv
import fnmatch
import json
import os
import re
import tempfile
import zipfile

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils.translation import gettext as _

from judge.models import Comment, Problem, Submission
from judge.utils.celery import Progress
from judge.utils.raw_sql import use_straight_join
from judge.utils.unicode import utf8bytes
from judge.utils.users import add_user, generate_password, get_org, validate_user_rows

__all__ = ('prepare_user_data', 'bulk_create_users')
rewildcard = re.compile(r'\*+')


def apply_submission_filter(queryset, options):
    if not options['submission_download']:
        return []

    use_straight_join(queryset)

    if options['submission_results']:
        queryset = queryset.filter(result__in=options['submission_results'])

    # Compress wildcards to avoid exponential complexity on certain glob patterns before Python 3.9.
    # For details, see <https://bugs.python.org/issue40480>.
    problem_glob = rewildcard.sub('*', options['submission_problem_glob'])
    if problem_glob != '*':
        queryset = queryset.filter(
            problem__in=Problem.objects.filter(code__regex=fnmatch.translate(problem_glob)),
        )

    return list(queryset)


def apply_comment_filter(queryset, options):
    if not options['comment_download']:
        return []
    return list(queryset)


@shared_task(bind=True)
def prepare_user_data(self, profile_id, options):
    options = json.loads(options)
    with Progress(self, 2, stage=_('Applying filters')) as p:
        # Force an update so that we get a progress bar.
        p.done = 0
        submissions = apply_submission_filter(
            Submission.objects.select_related('problem', 'language', 'source').filter(user_id=profile_id),
            options,
        )
        p.did(1)
        comments = apply_comment_filter(Comment.objects.filter(author_id=profile_id), options)
        p.did(1)

    with zipfile.ZipFile(os.path.join(settings.DMOJ_USER_DATA_CACHE, '%s.zip' % profile_id), mode='w') as data_file:
        submission_count = len(submissions)
        if submission_count:
            submission_info = {}
            with Progress(self, submission_count, stage=_('Preparing your submission data')) as p:
                prepared = 0
                interval = max(submission_count // 10, 1)
                for submission in submissions:
                    submission_info[submission.id] = {
                        'problem': submission.problem.code,
                        'date': submission.date.isoformat(),
                        'time': submission.time,
                        'memory': submission.memory,
                        'language': submission.language.key,
                        'status': submission.status,
                        'result': submission.result,
                        'case_points': submission.case_points,
                        'case_total': submission.case_total,
                    }
                    with data_file.open(
                        'submissions/%s.%s' % (submission.id, submission.language.extension),
                        'w',
                    ) as f:
                        f.write(utf8bytes(submission.source.source))

                    prepared += 1
                    if prepared % interval == 0:
                        p.done = prepared

                with data_file.open('submissions/info.json', 'w') as f:
                    f.write(utf8bytes(json.dumps(submission_info, sort_keys=True, indent=4)))

        comment_count = len(comments)
        if comment_count:
            comment_info = {}
            with Progress(self, comment_count, stage=_('Preparing your comment data')) as p:
                prepared = 0
                interval = max(comment_count // 10, 1)
                for comment in comments:
                    related_object = {
                        'b': 'blog post',
                        'c': 'contest',
                        'p': 'problem',
                        's': 'problem editorial',
                    }
                    comment_info[comment.id] = {
                        'date': comment.time.isoformat(),
                        'related_object': related_object[comment.page[0]],
                        'page': comment.page[2:],
                        'score': comment.score,
                    }
                    with data_file.open('comments/%s.txt' % comment.id, 'w') as f:
                        f.write(utf8bytes(comment.body))

                    prepared += 1
                    if prepared % interval == 0:
                        p.done = prepared

                with data_file.open('comments/info.json', 'w') as f:
                    f.write(utf8bytes(json.dumps(comment_info, sort_keys=True, indent=4)))

    return submission_count + comment_count


@shared_task(bind=True)
def bulk_create_users(self, rows, admin_user_id):
    """Create users in bulk from a list of row dicts (keyed by field name).

    Reuses the shared helpers from judge.management.commands.batchadduser so the UI and the
    CLI command share one implementation.
    """
    with Progress(self, 1, stage=_('Validating user data')) as p:
        error = validate_user_rows(rows)
        p.did(1)

    if error:
        cache.set(f'bulk_user_errors_{self.request.id}', [error], 3600)  # 1 hour
        raise Exception(_('Validation errors found'))

    created_users = []
    with Progress(self, len(rows), stage=_('Creating user accounts')) as p:
        for row in rows:
            username = str(row.get('username', '')).strip()
            fullname = str(row.get('fullname', '')).strip()
            org_name = str(row.get('organization', '')).strip()
            internal_id = str(row.get('internal_id', '')).strip()
            username_display = str(row.get('username_display', '')).strip()
            password = generate_password()

            add_user(
                username, fullname, password,
                username_display=username_display or None,
                org=get_org(org_name) if org_name else None,
                internal_id=internal_id or None,
            )
            created_users.append({'username': username, 'fullname': fullname, 'password': password})
            p.did(1)

    # Write CSV output (username, fullname, password) matching the CLI command.
    output_path = os.path.join(
        settings.DMOJ_USER_DATA_CACHE or tempfile.gettempdir(),
        f'bulk_users_{self.request.id}.csv',
    )
    with open(output_path, 'w', newline='') as fout:
        writer = csv.DictWriter(fout, fieldnames=['username', 'fullname', 'password'])
        writer.writeheader()
        writer.writerows(created_users)

    return {
        'success': True,
        'created_count': len(created_users),
        'output_file': output_path,
    }
