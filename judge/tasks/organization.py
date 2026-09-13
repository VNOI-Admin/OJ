from datetime import datetime, timedelta

import pytz
from celery import shared_task

from judge.models import Organization, OrganizationMonthlyUsage
from judge.utils.celery import Progress
from judge.utils.organization import archived_problems_queryset
from judge.utils.problem_archive import restore_problem_from_archive


@shared_task(bind=True)
def restore_organization_archived_problems(self, organization_id):
    organization = Organization.objects.get(id=organization_id)
    problems = archived_problems_queryset(organization).select_related('data_files')
    total = problems.count()
    if total == 0:
        return {'total': 0, 'restored': 0, 'failed': 0}

    restored, failed = 0, 0
    with Progress(self, total) as p:
        for i, problem in enumerate(problems.iterator(), 1):
            if restore_problem_from_archive(problem):
                restored += 1
            else:
                failed += 1
            if i % 5 == 0:
                p.done = i

    organization.notice = ''
    organization.save(update_fields=['notice'])
    return {'total': total, 'restored': restored, 'failed': failed}


@shared_task
def organization_monthly_reset():
    # Get first day of last month
    current_time = datetime.now(pytz.utc)
    month_start = (current_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0) -
                   timedelta(days=1)).replace(day=1)

    organizations = Organization.objects.filter(current_consumed_credit__gt=0)

    for org in organizations:
        usage = OrganizationMonthlyUsage(
            organization=org,
            time=month_start,
            consumed_credit=org.current_consumed_credit,
        )
        usage.save()
        org.free_credit = org.monthly_free_credit_limit
        org.current_consumed_credit = 0
        org.save()

    print('Reset monthly credit for all organizations')
