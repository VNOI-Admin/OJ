from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import ExpressionWrapper, FloatField, Sum
from django.utils import timezone

from judge.models import Organization, Submission


class Command(BaseCommand):
    help = 'backfill current credit usage for all organizations'

    def backfill_current_credit(self, org: Organization, month_start):
        credit_problem = (
            Submission.objects.filter(
                problem__organizations=org,
                contest_object__isnull=True,
                date__gte=month_start,
            )
            .annotate(
                credit=ExpressionWrapper(
                    Sum('test_cases__time'), output_field=FloatField(),
                ),
            )
            .aggregate(Sum('credit'))['credit__sum'] or 0
        )

        credit_contest = (
            Submission.objects.filter(
                contest_object__organizations=org,
                date__gte=month_start,
            )
            .annotate(
                credit=ExpressionWrapper(
                    Sum('test_cases__time'), output_field=FloatField(),
                ),
            )
            .aggregate(Sum('credit'))['credit__sum'] or 0
        )

        org.monthly_credit = settings.VNOJ_MONTHLY_FREE_CREDIT

        org.consume_credit(credit_problem + credit_contest)

    def handle(self, *args, **options):
        # get current month
        start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        print('Processing', start, 'at time', timezone.now())

        for org in Organization.objects.all():
            self.backfill_current_credit(org, start)
