from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from judge.models import Organization, OrganizationMonthlyUsage
from judge.utils.celery import Progress
from judge.utils.organization import archived_problems_queryset
from judge.utils.problem_archive import restore_problem_from_archive


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def restore_organization_archived_problems(self, organization_id):
    organization = Organization.objects.get(pk=organization_id)

    problems = (
        archived_problems_queryset(organization)
        .select_related("data_files")
    )

    total = problems.count()

    if not total:
        return {
            "total": 0,
            "restored": 0,
            "failed": 0,
        }

    restored = 0
    failed = 0

    with Progress(self, total) as progress:
        for index, problem in enumerate(
            problems.iterator(chunk_size=100),
            start=1,
        ):
            try:
                if restore_problem_from_archive(problem):
                    restored += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

            # Update progress in batches to reduce overhead.
            if index % 5 == 0 or index == total:
                progress.done = index

    # Only clear notice after processing has finished.
    Organization.objects.filter(pk=organization.pk).update(
        notice=""
    )

    return {
        "total": total,
        "restored": restored,
        "failed": failed,
    }


@shared_task
def organization_monthly_reset():
    """
    Archive the previous month's usage and reset organization credits.

    Uses row-level locking + bulk operations to avoid:
    - N+1 INSERT/UPDATE queries
    - race conditions between concurrent Celery workers
    - unnecessary model.save() calls
    """

    now = timezone.now()

    # First day of current month -> first day of previous month.
    current_month_start = now.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    previous_month_start = (
        current_month_start - timedelta(days=1)
    ).replace(day=1)

    with transaction.atomic():
        organizations = list(
            Organization.objects
            .select_for_update()
            .filter(current_consumed_credit__gt=0)
        )

        if not organizations:
            return {
                "organizations": 0,
                "usage_records": 0,
            }

        # Snapshot previous usage in one bulk INSERT.
        usage_records = [
            OrganizationMonthlyUsage(
                organization=org,
                time=previous_month_start,
                consumed_credit=org.current_consumed_credit,
            )
            for org in organizations
        ]

        OrganizationMonthlyUsage.objects.bulk_create(
            usage_records,
            batch_size=1000,
        )

        # Reset all organizations in one bulk UPDATE.
        for org in organizations:
            org.free_credit = org.monthly_free_credit_limit
            org.current_consumed_credit = 0

        Organization.objects.bulk_update(
            organizations,
            fields=[
                "free_credit",
                "current_consumed_credit",
            ],
            batch_size=1000,
        )

    result = {
        "organizations": len(organizations),
        "usage_records": len(usage_records),
    }

    print(
        "Monthly organization credit reset completed: "
        f"{result['organizations']} organizations"
    )

    return result
