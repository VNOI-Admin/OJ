import json

from django.core.management.base import BaseCommand, CommandError


def merge_replay(a, b):
    """Merge replay data b into a (mutating a), marking b's participations as ghosts.

    Both dicts are in ContestReplayData._build_data shape. b's problem ids are remapped
    to a's by position in the ordered `problems` list; b's participation ids are offset
    past a's to avoid collisions.
    """
    a_problems, b_problems = a.get('problems'), b.get('problems')
    if a_problems is None or b_problems is None:
        raise CommandError('Both files must contain a "problems" list; regenerate the replay data.')
    if len(a_problems) != len(b_problems):
        raise CommandError('Contests have a different number of problems (%d vs %d).'
                           % (len(a_problems), len(b_problems)))
    pmap = dict(zip(b_problems, a_problems))

    offset = max([p['id'] for p in a['participations']] +
                 [s[0] for s in a['subs']] + [0]) + 1

    for p in b['participations']:
        p['id'] += offset
        p['ghost'] = True
        a['participations'].append(p)

    for part_id, prob_id, points, t in b['subs']:
        a['subs'].append([part_id + offset, pmap[prob_id], points, t])

    return a


class Command(BaseCommand):
    help = 'merge one contest replay JSON (b, shown as ghosts) into another (a), overwriting a'

    def add_arguments(self, parser):
        parser.add_argument('a_json', help='replay data to merge into (overwritten)')
        parser.add_argument('b_json', help='replay data whose participations become ghosts')

    def handle(self, *args, **options):
        with open(options['a_json']) as f:
            a = json.load(f)
        with open(options['b_json']) as f:
            b = json.load(f)

        if a.get('duration') != b.get('duration'):
            self.stderr.write(self.style.WARNING(
                'Warning: durations differ (%s vs %s); ghosts may not line up with the contest.'
                % (a.get('duration'), b.get('duration')),
            ))

        merge_replay(a, b)

        with open(options['a_json'], 'w') as f:
            json.dump(a, f, separators=(',', ':'))

        self.stdout.write(self.style.SUCCESS(
            'Merged %d ghost participations into %s.' % (len(b['participations']), options['a_json']),
        ))
