from datetime import datetime, timedelta

import pytz
from celery import shared_task

from judge.models import Organization, OrganizationMonthlyUsage


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
