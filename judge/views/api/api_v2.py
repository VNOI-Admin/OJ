import json
import time

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import F
from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.functional import cached_property
from django.views.generic import View
from django.views.generic.detail import BaseDetailView, SingleObjectMixin

from judge.models import Contest, ContestParticipation, Language, Problem, Submission
from judge.utils.clics import build_clics_events
from judge.views.problem import ProblemDeleted, ProblemMixin, ProblemSubmitMixin


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


class APIContestClicsEventFeed(APIContestSyncBase):
    """CLICS Contest API event feed (NDJSON), consumed by the ICPC live overlay (live-v3)."""

    # live-v3 only finishes its initial load after 1 second without new events. If the
    # end_of_updates state arrives before that, it treats the contest as final before replaying the
    # runs, and anything waiting for finalization (e.g. emulation) sees no results at all.
    FINALIZE_DELAY = 1.5

    @staticmethod
    def to_line(event):
        return json.dumps(event, ensure_ascii=False, separators=(',', ':')) + '\n'

    def render_to_response(self, context, **response_kwargs):
        # `?finalize=1`: mark a finished contest as final so live-v3 can replay it (emulation mode).
        finalize = self.request.GET.get('finalize') in ('1', 'true')
        events = list(build_clics_events(context['object'], now=self._now, finalize=finalize))
        content_type = 'application/x-ndjson; charset=utf-8'
        if not events[-1]['data'].get('end_of_updates'):
            return HttpResponse(''.join(map(self.to_line, events)), content_type=content_type)

        def stream():
            yield ''.join(map(self.to_line, events[:-1]))
            time.sleep(self.FINALIZE_DELAY)
            yield self.to_line(events[-1])

        return StreamingHttpResponse(stream(), content_type=content_type)


class APISubmit(APIMixin, ProblemMixin, ProblemSubmitMixin, SingleObjectMixin, View):
    """Submit `file` in `language` to a problem, with the same checks as the submit page."""

    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied()
        try:
            self.object = self.get_object()
        except ProblemDeleted:
            raise Http404()

        try:
            response, form = self.handle_submission_post(request)
        except ValidationError as e:
            return self.submission_rejected(None, e.message, 400)
        if form is not None:
            return self.submission_rejected(None, ' '.join(e for errors in form.errors.values() for e in errors), 400)
        return response

    def get_submit_data(self):
        language_id = self.request.POST.get('language')
        upload = self.request.FILES.get('file')
        try:
            language = Language.objects.filter(id=language_id).first()
        except (TypeError, ValueError):
            # Let the form's ModelChoiceField report the invalid choice.
            language = None
        data, files = {'language': language_id}, {}
        if upload is not None:
            if language is not None and not language.file_only:
                if upload.size > 65536 * 4:
                    raise ValidationError('File is too big (maximum 65536 characters).')
                content = upload.read()
                if b'\x00' in content:
                    raise ValidationError('File is not a text file.')
                try:
                    data['source'] = content.decode('utf-8-sig')
                except UnicodeDecodeError:
                    raise ValidationError('File is not valid UTF-8 text.')
            else:
                files['submission_file'] = upload
        return data, files

    def submission_rejected(self, title, message, status):
        return JsonResponse(self.get_base_response(error={'code': status, 'message': message}), status=status)

    def submission_accepted(self, submission):
        return JsonResponse(self.get_base_response(data={'id': submission.id}), status=201)


class APILanguageTable(APIMixin, View):
    """Languages `problem` accepts submissions in."""

    def get(self, request, *args, **kwargs):
        code = request.GET.get('problem')
        if not code:
            return JsonResponse(self.get_base_response(error={
                'code': 400,
                'message': 'problem is required',
            }), status=400)
        problem = get_object_or_404(Problem, code=code, deleted_at__isnull=True)
        if not problem.is_accessible_by(request.user):
            raise Http404()

        languages = list(problem.usable_languages.order_by('name', 'key').values(
            'id', 'key', 'name', 'extension', 'file_only', 'file_size_limit',
        ))
        language_ids = {language['id'] for language in languages}
        default_language_id = None
        if request.profile and request.profile.language_id in language_ids:
            default_language_id = request.profile.language_id

        return JsonResponse(self.get_base_response(data={
            'default_language_id': default_language_id,
            'languages': languages,
        }))
