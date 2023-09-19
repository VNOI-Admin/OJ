import csv

from django.core.management.base import BaseCommand, CommandError

from judge.models import Contest, Submission, SubmissionTestCase
from judge.utils.raw_sql import use_straight_join
from judge.views.submission import submission_related


class Command(BaseCommand):
    help = 'export contest submissions details'

    def add_arguments(self, parser):
        parser.add_argument('key', help='contest key')
        parser.add_argument('output', help='output file')

    def handle(self, *args, **options):
        contest_key = options['key']

        contest = Contest.objects.filter(key=contest_key).first()
        if contest is None:
            raise CommandError('contest not found')

        queryset = Submission.objects.all()
        use_straight_join(queryset)
        queryset = submission_related(queryset.order_by('-id'))
        queryset = queryset.filter(contest_object=contest)

        self.export_queryset_to_output(queryset, options['output'])

    def export_queryset_to_output(self, queryset, output_file):
        fout = open(output_file, 'w', newline='')

        writer = csv.DictWriter(fout, fieldnames=['username', 'problem', 'submission', 'testcase',
                                                  'points', 'time', 'memory', 'feedback'])
        writer.writeheader()

        for submission in queryset:
            testcases = SubmissionTestCase.objects.filter(submission=submission)

            for testcase in testcases:
                case_id = f'case{testcase.case}'
                if submission.batch:
                    case_id += f'/batch{testcase.batch}'

                writer.writerow({
                    'username': submission.user.username,
                    'problem': submission.problem.code,
                    'submission': submission.id,
                    'testcase': case_id,
                    'points': testcase.points,
                    'time': testcase.time,
                    'memory': testcase.memory,
                    'feedback': testcase.extended_feedback,
                })

        fout.close()
