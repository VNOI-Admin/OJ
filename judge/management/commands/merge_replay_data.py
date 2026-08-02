import json

from django.core.management.base import BaseCommand, CommandError


def merge_replay(a, b):
    """Merge replay data b into a (mutating a), marking b's participations as ghosts.

    Both dicts are in build_contest_replay_data shape. b's problem ids are remapped
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
        if prob_id not in pmap:
            raise CommandError('Submission references problem id %s not in the "problems" list; '
                               'regenerate the replay data.' % prob_id)
        a['subs'].append([part_id + offset, pmap[prob_id], points, t])

    return a


class Command(BaseCommand):
    help = "patch contest A's replay data with contest B's participations shown as ghosts"

    def add_arguments(self, parser):
        parser.add_argument('contest', help="key of contest A (this server's contest) to patch")
        parser.add_argument('b_json', help='replay data whose participations become ghosts')

    def handle(self, *args, **options):
        from judge.models import Contest
        from judge.views.contests import build_contest_replay_data, write_contest_replay_data

        try:
            contest = Contest.objects.get(key=options['contest'])
        except Contest.DoesNotExist:
            raise CommandError('No contest with key "%s".' % options['contest'])

        # Regenerate A fresh from the DB so re-running is idempotent (no duplicate ghosts).
        a = build_contest_replay_data(contest)
        with open(options['b_json']) as f:
            b = json.load(f)

        if a.get('duration') != b.get('duration'):
            self.stderr.write(self.style.WARNING(
                'Warning: durations differ (%s vs %s); ghosts may not line up with the contest.'
                % (a.get('duration'), b.get('duration')),
            ))

        merge_replay(a, b)

        # Bump the version so the (immutable-cached) replay URL changes and clients refetch.
        contest.replay_version += 1
        filepath, _ = write_contest_replay_data(contest, a)  # path uses the new version

        contest.csv_ranking = Contest.HAS_GHOST_PARTICIPATION  # ranking page reads this to show the ghost toggle
        contest.save(update_fields=['csv_ranking', 'replay_version'])

        self.stdout.write(self.style.SUCCESS(
            'Merged %d ghost participations into %s.' % (len(b['participations']), filepath),
        ))
