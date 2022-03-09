from django.core.management.base import BaseCommand

from judge.models import Contest, ContestParticipation, Profile


class Command(BaseCommand):
    help = 'Create ContestParticipation before the contest'

    def add_arguments(self, parser):
        parser.add_argument('key', help='contest key')

    def handle(self, *args, **options):
        profiles = Profile.objects.filter(user__username__startswith='team')
        contest = Contest.objects.filter(key=options['key']).first()

        for profile in profiles:
            participation = ContestParticipation.objects.create(
                contest=contest, user=profile, virtual=ContestParticipation.LIVE,
                real_start=contest.start_time,
            )
            profile.current_contest = participation
            profile.save()

        contest._updating_stats_only = True
        contest.update_user_count()
