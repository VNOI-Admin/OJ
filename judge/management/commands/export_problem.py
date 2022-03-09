import json

from django.core.management.base import BaseCommand
from django.utils import timezone

from judge.models import Language, Problem, ProblemGroup, ProblemType, Profile


class Command(BaseCommand):
    help = 'create export/import problems'

    def add_arguments(self, parser):
        # parser.add_argument('code', help='problem code')
        # parser.add_argument('output', help='output file')
        parser.add_argument('input', help='input file')

    def handle(self, *args, **options):
        problems = json.load(open(options['input']))
        for p in problems:
            problem = Problem(**p)
            problem.group = ProblemGroup.objects.order_by('id').first()  # Uncategorized
            problem.date = timezone.now()
            problem.save()

            problem.allowed_languages.set(Language.objects.filter(include_in_problem=True))
            problem.types.set([ProblemType.objects.order_by('id').first()])  # Uncategorized
            problem.authors.set(Profile.objects.filter(user__username='admin'))
            problem.save()
        # problems = Problem.objects.get(code__startswith=options['code'])
        # result = []
        # for p in problems:
        #     data = {
        #         'code': p.code,
        #         'name': p.name,
        #         'pdf_url': 'https://oj.vnoi.info' + p.pdf_url,
        #         'time_limit': p.time_limit,
        #         'memory_limit': p.memory_limit,
        #         'points': p.points,
        #         'partial': p.partial,
        #     }
        #     result.append(data)
        # json.dump(result, open(options['output'], 'w'))
