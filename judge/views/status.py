import datetime
import json
from collections import defaultdict
from functools import partial

from django.conf import settings
from django.db.models import F, Q
from django.db.models.aggregates import Count
from django.db.models.fields import DateField
from django.db.models.functions import Cast
from django.http import HttpResponseBadRequest
from django.shortcuts import render
from django.utils import six
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from packaging import version

from judge.models import Judge, Language, RuntimeVersion, Submission
from judge.utils.stats import get_pie_chart

__all__ = ['status_all', 'status_table']


def get_judges(request):
    if request.user.is_superuser or request.user.is_staff:
        return True, Judge.objects.order_by('-online', 'name')
    else:
        return False, Judge.objects.filter(online=True)


def status_all(request):
    see_all, judges = get_judges(request)
    return render(request, 'status/judge-status.html', {
        'title': _('Status'),
        'judges': judges,
        'runtime_version_data': Judge.runtime_versions(),
        'see_all_judges': see_all,
    })


def status_oj(request):
    if not request.user.is_superuser or not request.user.is_staff:
        return HttpResponseBadRequest(_("You must be admin to view this content."), content_type='text/plain')

    queryset = Submission.objects.filter(date__gt=datetime.datetime.today() - datetime.timedelta(days=30))

    context = {'title': _('OJ Status')}

    submissions = (
        queryset.annotate(date_only=Cast(F('date'), DateField())).order_by('date').values('date_only', 'result')
        .annotate(count=Count('result')).values_list('date_only', 'result', 'count')
    )

    labels = list(set(item[0].isoformat() for item in submissions.values_list('date_only')))
    labels.sort()
    num_date = len(labels)
    result_order = ["AC", "WA", "TLE", "CE", "ERR"]
    result_data = defaultdict(partial(list, [0] * num_date))

    for date, result, count in submissions:
        result_data[result if result in result_order else "ERR"][labels.index(date.isoformat())] += count

    submissions_count = {
        'labels': labels,
        'datasets': [
            {
                'label': name,
                'backgroundColor': settings.DMOJ_STATS_SUBMISSION_RESULT_COLORS.get(name, "ERR"),
                'data': result_data[name],
            }
            for name in result_order
        ],
    }

    stats = {
        'language_count': get_pie_chart(
            queryset.values('language__name').annotate(count=Count('language__name'))
            .filter(count__gt=0).order_by('-count').values_list('language__name', 'count'),
        ),
        'submission_count': submissions_count,
        'ac_rate': get_pie_chart(
            queryset.values('result').annotate(count=Count('result'))
            .order_by('-count').values_list('result', 'count').filter(~Q(result__in=["IR", "AB", "MLE", "OLE", "IE"])),
        ),
    }
    context['stats'] = mark_safe(json.dumps(stats))

    return render(request, 'status/oj-status.html', context)


def status_table(request):
    see_all, judges = get_judges(request)
    return render(request, 'status/judge-status-table.html', {
        'judges': judges,
        'runtime_version_data': Judge.runtime_versions(),
        'see_all_judges': see_all,
    })


class LatestList(list):
    __slots__ = ('versions', 'is_latest')


def compare_version_list(x, y):
    if sorted(x.keys()) != sorted(y.keys()):
        return False
    for k in x.keys():
        if len(x[k]) != len(y[k]):
            return False
        for a, b in zip(x[k], y[k]):
            if a.name != b.name:
                return False
            if a.version != b.version:
                return False
    return True


def version_matrix(request):
    matrix = defaultdict(partial(defaultdict, LatestList))
    latest = defaultdict(list)
    groups = defaultdict(list)

    judges = {judge.id: judge.name for judge in Judge.objects.filter(online=True)}
    languages = Language.objects.filter(judges__online=True).distinct()

    for runtime in RuntimeVersion.objects.filter(judge__online=True).order_by('priority'):
        matrix[runtime.judge_id][runtime.language_id].append(runtime)

    for judge, data in six.iteritems(matrix):
        name_tuple = judges[judge].rpartition('.')
        groups[name_tuple[0] or name_tuple[-1]].append((judges[judge], data))

    matrix = {}
    for group, data in six.iteritems(groups):
        if len(data) == 1:
            judge, data = data[0]
            matrix[judge] = data
            continue

        ds = list(range(len(data)))
        size = [1] * len(data)
        for i, (p, x) in enumerate(data):
            if ds[i] != i:
                continue
            for j, (q, y) in enumerate(data):
                if i != j and compare_version_list(x, y):
                    ds[j] = i
                    size[i] += 1
                    size[j] = 0

        rep = max(range(len(data)), key=size.__getitem__)
        matrix[group] = data[rep][1]
        for i, (j, x) in enumerate(data):
            if ds[i] != rep:
                matrix[j] = x

    for data in six.itervalues(matrix):
        for language, versions in six.iteritems(data):
            versions.versions = [version.parse(runtime.version) for runtime in versions]
            if versions.versions > latest[language]:
                latest[language] = versions.versions

    for data in six.itervalues(matrix):
        for language, versions in six.iteritems(data):
            versions.is_latest = versions.versions == latest[language]

    languages = sorted(languages, key=lambda lang: version.parse(lang.name))
    return render(request, 'status/versions.html', {
        'title': _('Version matrix'),
        'judges': sorted(matrix.keys()),
        'languages': languages,
        'matrix': matrix,
    })
