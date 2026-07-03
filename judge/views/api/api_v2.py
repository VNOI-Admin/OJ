from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import F
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.functional import cached_property
from django.views.generic.detail import BaseDetailView

from judge.models import Contest, ContestParticipation, Submission


class APIKeyRequiredException(Exception):
    pass


class APIKeyRequiredMixin:
    def setup_api(self, request, *args, **kwargs):
        global_api_key = getattr(settings, 'GLOBAL_API_KEY', None)
        provided_key = request.headers.get('X-Global-API-Key') or request.GET.get('global_api_key')
        if not (global_api_key and provided_key == global_api_key):
            raise APIKeyRequiredException()
        super().setup_api(request, *args, **kwargs)


class APIMixin:
    @cached_property
    def _now(self):
        return timezone.now()

    def get_object_data(self, obj):
        raise NotImplementedError()

    def get_api_data(self, context):
        raise NotImplementedError()

    def get_base_response(self, **kwargs):
        resp = {
            'api_version': '2.0',
            'method': self.request.method.lower(),
            'fetched': self._now.isoformat(),
        }
        resp.update(kwargs)
        return resp

    def get_data(self, context):
        return self.get_base_response(data=self.get_api_data(context))

    def get_error(self, exception):
        caught_exceptions = {
            ValueError: (400, 'invalid filter value type'),
            ValidationError: (400, 'invalid filter value type'),
            PermissionDenied: (403, 'permission denied'),
            APIKeyRequiredException: (403, 'api key required'),
            Http404: (404, 'page/object not found'),
        }
        exception_type = type(exception)
        if exception_type in caught_exceptions:
            status_code, message = caught_exceptions[exception_type]
            return JsonResponse(
                self.get_base_response(error={
                    'code': status_code,
                    'message': message,
                }),
                status=status_code,
            )
        else:
            raise exception

    def render_to_response(self, context, **response_kwargs):
        return JsonResponse(
            self.get_data(context),
            **response_kwargs,
        )

    def setup_api(self, request, *args, **kwargs):
        pass

    def dispatch(self, request, *args, **kwargs):
        try:
            self.setup_api(request, *args, **kwargs)
            return super().dispatch(request, *args, **kwargs)
        except Exception as e:
            return self.get_error(e)


class APIContestSyncBase(APIKeyRequiredMixin, APIMixin, BaseDetailView):
    model = Contest
    slug_field = 'key'
    slug_url_kwarg = 'contest_code'

    def get_data(self, context):
        return self.get_api_data(context)

    def render_to_response(self, context, **response_kwargs):
        data = self.get_data(context)
        if not isinstance(data, dict):
            response_kwargs.setdefault('safe', False)
        return JsonResponse(data, **response_kwargs)


class APIContestSyncDetail(APIContestSyncBase):
    def get_api_data(self, context):
        contest = context['object']
        frozen_at = None
        if contest.frozen_last_minutes:
            frozen_at = contest.frozen_time.isoformat()
        return {
            'code': contest.key,
            'start_time': contest.start_time.isoformat(),
            'end_time': contest.end_time.isoformat(),
            'frozen_at': frozen_at,
        }


class APIContestSyncProblems(APIContestSyncBase):
    def get_api_data(self, context):
        contest = context['object']
        problems = contest.contest_problems.select_related('problem').order_by('order')
        return [
            {
                'code': contest_problem.problem.code,
                'contest': contest.key,
            }
            for contest_problem in problems
        ]


class APIContestSyncParticipants(APIContestSyncBase):
    def get_api_data(self, context):
        contest = context['object']
        score_field = 'frozen_score' if contest.is_frozen else 'score'
        cumtime_field = 'frozen_cumtime' if contest.is_frozen else 'cumtime'
        tiebreaker_field = 'frozen_tiebreaker' if contest.is_frozen else 'tiebreaker'
        participations = (
            contest.users
            .filter(virtual=ContestParticipation.LIVE, is_disqualified=False)
            .annotate(username=F('user__user__username'))
            .order_by(F(score_field).desc(), cumtime_field, tiebreaker_field, 'id')
            .values('username', score_field, cumtime_field, tiebreaker_field)
        )
        results = []
        last_scores = None
        current_rank = 0
        for index, participation in enumerate(participations, start=1):
            score_tuple = (
                participation[score_field],
                participation[cumtime_field],
                participation[tiebreaker_field],
            )
            if score_tuple != last_scores:
                current_rank = index
                last_scores = score_tuple
            results.append({
                'user': participation['username'],
                'contest': contest.key,
                'rank': current_rank,
            })
        return results


class APIContestSyncSubmissions(APIContestSyncBase):
    def get_api_data(self, context):
        contest = context['object']
        from_timestamp = self.request.GET.get('from_timestamp')
        if not from_timestamp:
            raise ValidationError('from_timestamp is required')

        parsed = parse_datetime(from_timestamp)
        if parsed is None:
            raise ValidationError('from_timestamp must be ISO 8601')
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone=timezone.utc)

        limit_param = self.request.GET.get('limit')
        if limit_param is None:
            limit = 2000
        else:
            try:
                limit = int(limit_param)
            except (TypeError, ValueError):
                raise ValidationError('limit must be an integer')
            if limit < 1:
                raise ValidationError('limit must be positive')
            limit = min(limit, 2000)

        status = self.request.GET.get('status', 'final')
        if status not in ('final', 'all'):
            raise ValidationError('status must be "final" or "all"')

        submissions = (
            Submission.objects
            .filter(contest_object=contest, judged_date__gte=parsed)
            .select_related('user__user', 'problem', 'contest_object')
            .order_by('judged_date', 'id')
        )
        if status == 'final':
            submissions = submissions.exclude(status__in=Submission.IN_PROGRESS_GRADING_STATUS)
        submissions = submissions[:limit]

        return [
            {
                'id': str(submission.id),
                'submittedAt': submission.date.isoformat(),
                'judgedAt': submission.judged_date.isoformat() if submission.judged_date else None,
                'author': submission.user.user.username,
                'submissionStatus': submission.result or submission.status,
                'contest_code': contest.key,
                'problem_code': submission.problem.code,
            }
            for submission in submissions
        ]
