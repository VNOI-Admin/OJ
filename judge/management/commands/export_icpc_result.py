import csv

from django.core.management.base import BaseCommand, CommandError

from judge.models import Contest, ContestParticipation


class Command(BaseCommand):
    help = 'export icpc result'

    def add_arguments(self, parser):
        parser.add_argument('key', help='contest key')
        parser.add_argument('output', help='output file')
        parser.add_argument('--extra', action='store_true', help='export team name and uni name')

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

            header = ['external id', 'rank', 'prize', 'solved', 'penalty', 'last AC']
            if options['extra']:
                header = ['team name', 'uni name'] + header

            result_writer.writerow(header)
            for rank, p in enumerate(participations, start=1):
                user = p.user

                row = [user.notes, rank, '', int(p.score), p.cumtime, int(p.tiebreaker)]
                if options['extra']:
                    row = [user.display_name, user.organization.name] + row

                result_writer.writerow(row)

            print(f'Exported result to {output_path}')
