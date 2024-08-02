import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import translation

from judge.models import Contest, ContestSubmission


class Command(BaseCommand):
    help = 'export data for VNOI Resolver'

    def add_arguments(self, parser):
        parser.add_argument('key', help='contest key')
        parser.add_argument('output', help='output XML file')
        parser.add_argument('--medal',
                            help='the last integer rank (position) in the contest which will be '
                            'awarded Gold, Silver, and Bronze medals respectively',
                            nargs=3,
                            default=[4, 8, 12],
                            metavar=('lastGold', 'lastSilver', 'lastBronze'))

    def handle(self, *args, **options):
        contest_key = options['key']
        output_file = options['output']

        if not output_file.endswith('.json'):
            raise CommandError('output file must end with .json')

        contest = Contest.objects.filter(key=contest_key).first()
        if contest is None:
            raise CommandError('contest not found')

        # Force using English
        translation.activate('en')

        data = {'users': [], 'problems': [], 'submissions': []}

        # Users
        participations = contest.users.filter(virtual=0).select_related('user', 'user__user')
        for participation in participations:
            profile = participation.user
            user = profile.user
            data['users'].append({
                'userId': user.id,
                'username': profile.display_name,
                'fullName': user.first_name or profile.display_name,
            })

        # Problems
        problems = contest.contest_problems.order_by('order').select_related('problem').prefetch_related(
            'problem__cases')
        for prob in problems:
            data['problems'].append({
                'problemId': prob.problem.id,
                'name': prob.problem.name,
                'points': prob.points,
            })

        # Submissions
        for sub in ContestSubmission.objects.filter(participation__contest=contest, participation__virtual=0) \
                                            .exclude(submission__result__isnull=True) \
                                            .exclude(submission__result__in=['IE', 'CE']) \
                                            .select_related('submission', 'submission__problem',
                                                            'submission__user__user'):

            data['submissions'].append({
                'submissionId': sub.submission.id,
                'problemId': sub.submission.problem.id,
                'userId': sub.submission.user.user.id,
                'time': str((sub.submission.date - contest.start_time).total_seconds()),
                'points': sub.points,
            })

        # Write to output file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f)
