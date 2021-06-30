import bisect
from collections import defaultdict
from functools import partial
from itertools import chain, repeat
from operator import itemgetter

from django.conf import settings
from django.db.models import Case, Count, DateField, F, FloatField, IntegerField, Q, Value, When
from django.db.models.expressions import CombinedExpression, ExpressionWrapper
from django.db.models.functions import Cast
from django.http import HttpResponseForbidden, JsonResponse
from django.http.response import HttpResponseBadRequest
from django.shortcuts import render
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _

from judge.models import Language, Submission
from judge.utils.stats import chart_colors, get_bar_chart, get_pie_chart, highlight_colors


ac_count = Count(Case(When(submission__result='AC', then=Value(1)), output_field=IntegerField()))


def repeat_chain(iterable):
    return chain.from_iterable(repeat(iterable))


def language_data(request, language_count=Language.objects.annotate(count=Count('submission'))):
    languages = language_count.filter(count__gt=0).values('key', 'name', 'count').order_by('-count')
    num_languages = min(len(languages), settings.DMOJ_STATS_LANGUAGE_THRESHOLD)
    other_count = sum(map(itemgetter('count'), languages[num_languages:]))

    return JsonResponse({
        'labels': list(map(itemgetter('name'), languages[:num_languages])) + ['Other'],
        'datasets': [
            {
                'backgroundColor': chart_colors[:num_languages] + ['#FDB45C'],
                'highlightBackgroundColor': highlight_colors[:num_languages] + ['#FFC870'],
                'data': list(map(itemgetter('count'), languages[:num_languages])) + [other_count],
            },
        ],
    }, safe=False)


def ac_language_data(request):
    return language_data(request, Language.objects.annotate(count=ac_count))


def status_data(request, statuses=None):
    if not statuses:
        statuses = (Submission.objects.values('result').annotate(count=Count('result'))
                    .values('result', 'count').order_by('-count'))
    data = []
    for status in statuses:
        res = status['result']
        if not res:
            continue
        count = status['count']
        data.append((str(Submission.USER_DISPLAY_CODES[res]), count))

    return JsonResponse(get_pie_chart(data), safe=False)


def ac_rate(request):
    rate = CombinedExpression(ac_count / Count('submission'), '*', Value(100.0), output_field=FloatField())
    data = Language.objects.annotate(total=Count('submission'), ac_rate=rate).filter(total__gt=0) \
        .order_by('total').values_list('name', 'ac_rate')
    return JsonResponse(get_bar_chart(list(data)))


def oj_data(request):
    if request.method != 'POST' or not request.user.is_superuser or not request.user.is_staff:
        return HttpResponseForbidden()

    start_date = request.POST.get('start_date')
    end_date = request.POST.get('end_date')
    if not start_date or not end_date:
        return HttpResponseBadRequest()

    start_date = parse_datetime(start_date)
    end_date = parse_datetime(end_date)
    if not start_date or not end_date:
        return HttpResponseBadRequest()

    queryset = Submission.objects.filter(date__gte=start_date, date__lte=end_date)

    submissions = (
        queryset.annotate(date_only=Cast(F('date'), DateField())).order_by('date').values('date_only', 'result')
        .annotate(count=Count('result')).values_list('date_only', 'result', 'count')
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


def language(request):
    return render(request, 'stats/language.html', {
        'title': _('Language statistics'), 'tab': 'language',
    })
