import csv
import re

from django.core.management.base import BaseCommand, CommandError

from judge.models import Contest, ContestSubmission, SubmissionTestCase
from judge.utils.raw_sql import use_straight_join

# https://stackoverflow.com/a/14693789/16224359
# Error messages may sometimes be formatted with
# ANSI sequences representing text colors and text weight,
# which may display dirty text in raw text files.
# The following regex is to filter such sequences.
ansi_escape = re.compile(r"""
    \x1B  # ESC
    (?:   # 7-bit C1 Fe (except CSI)
        [@-Z\\-_]
    |     # or [ for CSI, followed by a control sequence
        \[
        [0-?]*  # Parameter bytes
        [ -/]*  # Intermediate bytes
        [@-~]   # Final byte
    )
""", re.VERBOSE)


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

        queryset = ContestSubmission.objects.all()
        use_straight_join(queryset)
        queryset = queryset.filter(submission__contest_object=contest,
                                   participation__virtual=0) \
                           .order_by('-id')

        self.export_queryset_to_output(queryset, options['output'])

    def export_queryset_to_output(self, queryset, output_file):
        fout = open(output_file, 'w', newline='')

        writer = csv.DictWriter(fout, fieldnames=['username', 'problem', 'submission', 'testcase',
                                                  'result', 'points', 'time', 'memory', 'feedback'])
        writer.writeheader()

        for contest_submission in queryset:
            submission = contest_submission.submission

            # Submission row
            escaped_error = ansi_escape.sub('', submission.error)

            writer.writerow({
                'username': submission.user.username,
                'problem': submission.problem.code,
                'submission': submission.id,
                'result': submission.result,
                'points': submission.case_points,
                'time': submission.time,
                'memory': submission.memory,
                'feedback': escaped_error,
            })

            testcases = SubmissionTestCase.objects.filter(submission=submission)

            for testcase in testcases:
                case_id = f'case{testcase.case}'
                if submission.batch:
                    case_id += f'/batch{testcase.batch}'

                # Testcase rows
                writer.writerow({
                    'username': submission.user.username,
                    'problem': submission.problem.code,
                    'submission': submission.id,
                    'testcase': case_id,
                    'result': testcase.status,
                    'points': testcase.points,
                    'time': testcase.time,
                    'memory': testcase.memory,
                    'feedback': testcase.extended_feedback,
                })

        fout.close()
