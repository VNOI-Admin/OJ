import csv

from django.core.management.base import BaseCommand, CommandError

from judge.models import Contest, ContestParticipation


def write_icpc_result(contest, result_file, extra=False):
    participations = contest.users.filter(virtual=ContestParticipation.LIVE) \
        .select_related('user').prefetch_related('user__organizations') \
        .order_by('is_disqualified', '-score', 'cumtime', 'tiebreaker')

    result_writer = csv.writer(result_file, delimiter='\t')

    header = ['external id', 'rank', 'prize', 'solved', 'penalty', 'last AC']
    if extra:
        header = ['team name', 'uni name', 'group'] + header

    result_writer.writerow(header)
    for rank, p in enumerate(participations, start=1):
        user = p.user

        row = [user.notes, rank, '', int(p.score), p.cumtime, int(p.tiebreaker)]
        if extra:
            org = user.organization
            row = [user.display_name, org.name if org else '', user.group] + row

        result_writer.writerow(row)


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

        with open(output_path, mode='w') as result_file:
            write_icpc_result(contest, result_file, options['extra'])

        print(f'Exported result to {output_path}')
