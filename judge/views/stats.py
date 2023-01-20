import bisect
import datetime

from django.conf import settings
from django.db.models import Count, DateField, F, FloatField, Q
from django.db.models.functions import Cast
from django.http import HttpResponseForbidden, JsonResponse
from django.http.response import HttpResponseBadRequest
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _

from judge.models import Problem, Submission
from judge.utils.stats import get_bar_chart, get_pie_chart, get_stacked_bar_chart


def generate_day_labels(start_date, end_date, utc_offset):
    start_date += utc_offset
    end_date += utc_offset
    delta = end_date - start_date

    return [(start_date + datetime.timedelta(days=i)).date().isoformat() for i in range(delta.days + 1)]


def submission_data(start_date, end_date, utc_offset):
    queryset = Submission.objects.filter(date__gte=start_date, date__lte=end_date)

    submissions = (
        queryset.annotate(date_only=Cast(F('date') + utc_offset, DateField()))
        .values('date_only', 'result').annotate(count=Count('result')).values_list('date_only', 'result', 'count')
    )

    languages = (
        queryset.values('language__name').annotate(count=Count('language__name'))
        .filter(count__gt=0).order_by('-count').values_list('language__name', 'count')
    )

    results = (
        queryset.values('result').annotate(count=Count('result'))
        .filter(count__gt=0).order_by('-count').values_list('result', 'count')
    )
    results = [(str(Submission.USER_DISPLAY_CODES[res]), count) for (res, count) in results]

    queue_time = (
        # Divide by 1000000 to convert microseconds to seconds
        queryset.filter(judged_date__isnull=False, rejudged_date__isnull=True)
        .annotate(queue_time=Cast(F('judged_date') - F('date'), FloatField()) / 1000000.0)
        .order_by('queue_time').values_list('queue_time', flat=True)
    )

    days_labels = generate_day_labels(start_date, end_date, utc_offset)
    num_days = len(days_labels)
    result_order = ['AC', 'WA', 'TLE', 'CE', 'ERR']
    result_data = {result: [0] * num_days for result in result_order}

    for date, result, count in submissions:
        result_data[result if result in result_order else 'ERR'][days_labels.index(date.isoformat())] += count

    queue_time_ranges = [0, 1, 2, 5, 10, 30, 60, 120, 300, 600]
    queue_time_labels = [
        '',
        '0s - 1s',
        '1s - 2s',
        '2s - 5s',
        '5s - 10s',
        '10s - 30s',
        '30s - 1min',
        '1min - 2min',
        '2min - 5min',
        '5min - 10min',
        '> 10min',
    ]

    def binning(x):
        return bisect.bisect_left(queue_time_ranges, x, lo=0, hi=len(queue_time_ranges))

    queue_time_count = [0] * len(queue_time_labels)
    for group in map(binning, list(queue_time)):
        queue_time_count[group] += 1

    queue_time_data = [(queue_time_labels[i], queue_time_count[i]) for i in range(1, len(queue_time_labels))]

    return {
        'by_day': get_stacked_bar_chart(days_labels, result_data, settings.DMOJ_STATS_SUBMISSION_RESULT_COLORS),
        'by_language': get_pie_chart(languages),
        'result': get_pie_chart(results),
        'queue_time': get_bar_chart(queue_time_data),
    }


def organization_data(start_date, end_date, utc_offset):
    submissions = (
        Submission.objects.filter(date__gte=start_date, date__lte=end_date)
        .filter(Q(problem__is_organization_private=True) | Q(contest_object__is_organization_private=True))
        .annotate(date_only=Cast(F('date') + utc_offset, DateField()))
        .values('date_only', 'result').annotate(count=Count('result')).values_list('date_only', 'result', 'count')
    )

    days_labels = generate_day_labels(start_date, end_date, utc_offset)
    num_days = len(days_labels)
    result_order = ['AC', 'WA', 'TLE', 'CE', 'ERR']
    result_data = {result: [0] * num_days for result in result_order}

    for date, result, count in submissions:
        result_data[result if result in result_order else 'ERR'][days_labels.index(date.isoformat())] += count

    org_data = get_stacked_bar_chart(days_labels, result_data, settings.DMOJ_STATS_SUBMISSION_RESULT_COLORS)

    problems = (
        Problem.objects.filter(date__gte=start_date, date__lte=end_date, is_organization_private=True)
        .annotate(date_only=Cast(F('date') + utc_offset, DateField()))
        .values('date_only').annotate(count=Count('date_only')).values_list('date_only', 'count')
    )

    problems_dataset = {
        'label': _('New Problems'),
        'type': 'line',
        'fill': False,
        'data': [0] * num_days,
        'backgroundColor': '#023e8a',
        'borderColor': '#03045e',
        'yAxisID': 'yRightAxis',
    }

    for date_only, count in problems:
        problems_dataset['data'][days_labels.index(date_only.isoformat())] += count

    org_data['datasets'].insert(0, problems_dataset)

    return {
        'org_by_day': org_data,
    }


def all_data(request):
    if request.method != 'POST' or not request.user.is_superuser:
        return HttpResponseForbidden()

    # start_date and end_date are in UTC timezone
    # utc_offset is required for properly converting the dates to user's local timezone
    start_date = request.POST.get('start_date')
    end_date = request.POST.get('end_date')
    utc_offset = request.POST.get('utc_offset')
    if not start_date or not end_date or not utc_offset:
        return HttpResponseBadRequest()

    start_date = parse_datetime(start_date)
    end_date = parse_datetime(end_date)
    if not start_date or not end_date:
        return HttpResponseBadRequest()

    try:
        utc_offset = datetime.timedelta(minutes=int(utc_offset))
    except Exception:
        return HttpResponseBadRequest()

    return JsonResponse({
        **submission_data(start_date, end_date, utc_offset),
        **organization_data(start_date, end_date, utc_offset),
    })
