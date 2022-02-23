import csv

from django.core.management.base import BaseCommand, CommandError

from judge.models import Contest, ContestParticipation


class Command(BaseCommand):
    help = 'export icpc result'

    def add_arguments(self, parser):
        parser.add_argument('key', help='contest key')
        parser.add_argument('output', help='output file')

    def handle(self, *args, **options):
        contest_key = options['key']
        output_path = options['output']

        contest = Contest.objects.filter(key=contest_key).first()
        if contest is None:
            raise CommandError('contest not found')

        participations = contest.users.filter(virtual=ContestParticipation.LIVE).select_related('user') \
            .order_by('is_disqualified', '-score', 'cumtime', 'tiebreaker')

        with open(output_path, mode='w') as result_file:
            result_writer = csv.writer(result_file, delimiter='\t')
            result_writer.writerow(['external id', 'rank', 'prize', 'solved', 'penalty', 'last AC'])
            for rank, p in enumerate(participations, start=1):
                user = p.user
                result_writer.writerow([user.notes, rank, '', int(p.score), p.cumtime, int(p.tiebreaker)])

            print(f'Exported result to {output_path}')
