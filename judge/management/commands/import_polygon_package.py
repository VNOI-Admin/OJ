from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse
from django.utils import translation

from judge.models import Profile
from judge.utils.codeforces_polygon import ImportPolygonError, PolygonImporter


class Command(BaseCommand):
    help = 'import Codeforces Polygon full package'

    def add_arguments(self, parser):
        parser.add_argument('package', help='path to package in zip format')
        parser.add_argument('code', help='problem code')
        parser.add_argument('--update', help='update the problem if it exists', action='store_true')
        parser.add_argument('--authors', help='username of problem author', nargs='*')
        parser.add_argument('--curators', help='username of problem curator', nargs='*')

    def handle(self, *args, **options):
        # Force using English
        translation.activate('en')

        problem_authors_args = options['authors'] or []
        problem_authors = []
        for username in problem_authors_args:
            try:
                profile = Profile.objects.get(user__username=username)
            except Profile.DoesNotExist:
                raise CommandError(f'user {username} does not exist')

            problem_authors.append(profile)

        problem_curators_args = options['curators'] or []
        problem_curators = []
        for username in problem_curators_args:
            try:
                profile = Profile.objects.get(user__username=username)
            except Profile.DoesNotExist:
                raise CommandError(f'user {username} does not exist')

            problem_curators.append(profile)

        try:
            importer = PolygonImporter(
                package=options['package'],
                code=options['code'],
                authors=problem_authors,
                curators=problem_curators,
                do_update=options['update'],
                interactive=True,
            )
            importer.run()
        except ImportPolygonError as e:
            raise CommandError(e)

        problem_url = 'https://' + Site.objects.first().domain + reverse('problem_detail', args=[options['code']])
        print(f'Imported successfully. View problem at {problem_url}')
