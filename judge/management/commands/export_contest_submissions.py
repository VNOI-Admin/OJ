import os

from django.core.management.base import BaseCommand, CommandError

from judge.models import Contest, ContestParticipation


class Command(BaseCommand):
    help = 'export contest submissions'

    def add_arguments(self, parser):
        parser.add_argument('key', help='contest key')
        parser.add_argument('output', help='output directory')

    def handle(self, *args, **options):
        contest_key = options['key']
        output_dir = options['output']

        contest = Contest.objects.filter(key=contest_key).first()
        if contest is None:
            raise CommandError('contest not found')

        if os.path.exists(output_dir):
            raise CommandError('output directory already exists')

        os.makedirs(output_dir)

        users = contest.users.filter(virtual=ContestParticipation.LIVE).select_related('user__user')

        user_count = 0
        submission_count = 0

        for user in users:
            user_count += 1

            username = user.user.user.username
            user_dir = os.path.join(output_dir, username)
            user_history_dir = os.path.join(user_dir, '$History')

            os.makedirs(user_dir)

            problems = set()
            submissions = user.submissions.order_by('-id') \
                .select_related('problem__problem', 'submission__source', 'submission__language') \
                .values_list('problem__problem__code', 'submission__source__source',
                             'submission__language__extension', 'submission__id')

            for problem, source, ext, sub_id in submissions:
                submission_count += 1

                if problem not in problems:  # Last submission
                    problems.add(problem)
                    with open(os.path.join(user_dir, f'{problem}.{ext}'), 'w') as f:
                        f.write(source)
                else:
                    os.makedirs(user_history_dir, exist_ok=True)
                    with open(os.path.join(user_history_dir, f'{problem}_{sub_id}.{ext}'), 'w') as f:
                        f.write(source)

        print(f'Exported {submission_count} submissions by {user_count} users')
