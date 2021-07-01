import bisect
import datetime
from collections import defaultdict
from functools import partial

from django.conf import settings
from django.db.models import Count, DateField, F, FloatField
from django.db.models.expressions import ExpressionWrapper
from django.db.models.functions import Cast
from django.http import HttpResponseForbidden, JsonResponse
from django.http.response import HttpResponseBadRequest
from django.utils.dateparse import parse_datetime

from judge.models import Submission
from judge.utils.stats import get_bar_chart, get_pie_chart


def oj_data(request):
    if request.method != 'POST' or not request.user.is_superuser:
        return HttpResponseForbidden()

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

    queryset = Submission.objects.filter(date__gte=start_date, date__lte=end_date)

    submissions = (
        queryset.annotate(date_only=Cast(F('date') + utc_offset, DateField())).order_by('date')
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
        .annotate(queue_time=ExpressionWrapper((F('judged_date') - F('date')) / 1000000, output_field=FloatField()))
        .order_by('queue_time').values_list('queue_time', flat=True)
    )

    days_labels = list(set(item[0].isoformat() for item in submissions.values_list('date_only')))
    days_labels.sort()
    num_days = len(days_labels)
    result_order = ["AC", "WA", "TLE", "CE", "ERR"]
    result_data = defaultdict(partial(list, [0] * num_days))

    for date, result, count in submissions:
        result_data[result if result in result_order else "ERR"][days_labels.index(date.isoformat())] += count

    submissions_by_day = {
        'labels': days_labels,
        'datasets': [
            {
                'label': name,
                'backgroundColor': settings.DMOJ_STATS_SUBMISSION_RESULT_COLORS.get(name, "ERR"),
                'data': result_data[name],
            }
            for name in result_order
        ],
    }

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

    return JsonResponse({
        'by_day': submissions_by_day,
        'by_language': get_pie_chart(languages),
        'result': get_pie_chart(results),
        'queue_time': get_bar_chart(queue_time_data),
    })
