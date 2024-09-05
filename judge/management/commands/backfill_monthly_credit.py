import datetime

import dateutil.relativedelta
from django.core.management.base import BaseCommand
from django.db.models import ExpressionWrapper, FloatField, Sum
from django.utils import timezone

from judge.models import Organization, OrganizationMonthlyUsage, Submission


class Command(BaseCommand):
    help = 'backfill monthly credit usage for all organizations'

    def backfill_credit(self, org, month_start, next_month_start):
        credit_problem = (
            Submission.objects.filter(
                problem__organizations=org,
                contest_object__isnull=True,
                date__gte=month_start,
                date__lt=next_month_start,
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
                date__lt=next_month_start,
            )
            .annotate(
                credit=ExpressionWrapper(
                    Sum('test_cases__time'), output_field=FloatField(),
                ),
            )
            .aggregate(Sum('credit'))['credit__sum'] or 0
        )

        usage, created = OrganizationMonthlyUsage.objects.get_or_create(
            organization=org,
            time=month_start,
        )

        usage.consumed_credit = credit_problem + credit_contest
        usage.save()

    def handle(self, *args, **options):
        start = datetime.datetime(2023, 6, 1, tzinfo=timezone.utc)
        while True:
            print('Processing', start, 'at time', timezone.now())
            next_month = start + dateutil.relativedelta.relativedelta(months=+1)
            if next_month > timezone.now():
                break

            for org in Organization.objects.all():
                self.backfill_credit(org, start, next_month)

            start = next_month
