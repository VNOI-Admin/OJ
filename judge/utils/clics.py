"""Build a CLICS Contest API event feed (2023-06) for a contest.

The feed is consumed by the ICPC live overlay (https://github.com/icpc/live-v3) through its
`clics` plugin, and follows https://ccs-specs.icpc.io/2023-06/contest_api#event-feed.

The whole contest is dumped as a snapshot every time. Every object type that has ids is sent
as a *batch* event (`"id": null` and a list of objects), which replaces the client's whole
collection: objects missing from a later dump (e.g. a removed participant) are deleted, and
rejudges are picked up automatically. live-v3 reconnects about every 5 seconds once the
connection is closed, so this behaves like a full reload every 5 seconds.

Events never carry a `token`: live-v3 skips events whose token it has already seen, which would
make it ignore every dump but the first.
"""
from datetime import timedelta, timezone as dt_timezone
from typing import Dict, Iterator, List, Optional, Tuple

from django.utils import timezone

from judge.models import Contest, ContestParticipation, ContestSubmission, Language
from judge.models.submission import SUBMISSION_RESULT

# Results that do not count as a try in VNOJ's ICPC scoring (see judge/contest_format/icpc.py).
NO_PENALTY_RESULTS = {'CE', 'IE'}
SOLVED_RESULTS = {'AC'}


def format_time(value) -> str:
    """CLICS absolute TIME, e.g. `2026-11-06T08:00:00.000+00:00`."""
    value = value.astimezone(dt_timezone.utc)
    return value.strftime('%Y-%m-%dT%H:%M:%S.') + '%03d+00:00' % (value.microsecond // 1000)


def format_reltime(value: timedelta) -> str:
    """CLICS RELTIME, e.g. `1:23:45.678` (may be negative)."""
    sign = '-' if value < timedelta(0) else ''
    total_ms = abs(value) // timedelta(milliseconds=1)
    seconds, ms = divmod(total_ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return '%s%d:%02d:%02d.%03d' % (sign, hours, minutes, seconds, ms)


def problem_label(index: int) -> str:
    """1 -> A, 26 -> Z, 27 -> AA."""
    label = ''
    while index > 0:
        index, rem = divmod(index - 1, 26)
        label = chr(65 + rem) + label
    return label


def _event(type_: str, data, id_: Optional[str] = None) -> dict:
    # `id` is null both for batch events and for the contest/state singletons.
    return {'type': type_, 'id': id_, 'data': data}


def contest_duration(contest: Contest) -> timedelta:
    return contest.time_limit or contest.contest_window_length


def freeze_duration(contest: Contest) -> Optional[timedelta]:
    if contest.frozen_last_minutes and contest.format.supports_frozen:
        return timedelta(minutes=contest.frozen_last_minutes)
    return None


def build_contest(contest: Contest) -> dict:
    data = {
        'id': contest.key,
        'name': contest.name,
        'formal_name': contest.name,
        'start_time': format_time(contest.start_time),
        'duration': format_reltime(contest_duration(contest)),
        'scoreboard_type': 'pass-fail',
        # 2023-06 sends penalty_time as an integer number of minutes.
        'penalty_time': int(contest.format.config.get('penalty', 0) if contest.format.config else 0),
    }
    freeze = freeze_duration(contest)
    if freeze is not None:
        data['scoreboard_freeze_duration'] = format_reltime(freeze)
    return data


def build_state(contest: Contest, now, finalize: bool = False, has_pending: bool = False) -> dict:
    state = {
        'started': None,
        'frozen': None,
        'ended': None,
        'thawed': None,
        'finalized': None,
        # live-v3 stops reading the feed for good once it sees end_of_updates, so it is only sent
        # when explicitly asked for (`finalize`), e.g. to replay a finished contest in emulation mode.
        'end_of_updates': None,
    }
    if now >= contest.start_time:
        state['started'] = format_time(contest.start_time)
    if freeze_duration(contest) is not None and now >= contest.frozen_time:
        state['frozen'] = format_time(contest.frozen_time)
    if now >= contest.end_time:
        state['ended'] = format_time(contest.end_time)
        if finalize and not has_pending:
            state['finalized'] = state['end_of_updates'] = format_time(contest.end_time)
    return state


def build_judgement_types() -> List[dict]:
    return [
        {
            'id': code,
            'name': str(name),
            'solved': code in SOLVED_RESULTS,
            'penalty': code not in SOLVED_RESULTS and code not in NO_PENALTY_RESULTS,
        }
        for code, name in SUBMISSION_RESULT
    ]


def build_languages() -> List[dict]:
    return [
        {'id': key, 'name': name, 'extensions': [extension] if extension else []}
        for key, name, extension in Language.objects.order_by('key').values_list('key', 'name', 'extension')
    ]


def build_problems(contest: Contest) -> List[dict]:
    problems = []
    contest_problems = contest.contest_problems.select_related('problem').order_by('order', 'id')
    for ordinal, contest_problem in enumerate(contest_problems):
        problem = contest_problem.problem
        problems.append({
            'id': problem.code,
            'label': problem_label(ordinal + 1),
            'name': problem.name,
            'ordinal': ordinal,
            'time_limit': problem.time_limit,
        })
    return problems


def live_participations(contest: Contest):
    return (
        contest.users.filter(virtual=ContestParticipation.LIVE)
        .select_related('user__user')
        .prefetch_related('user__organizations')
        .order_by('id')
    )


def build_teams_and_organizations(participations) -> Tuple[List[dict], List[dict]]:
    teams = []
    organizations: Dict[str, dict] = {}
    for participation in participations:
        profile = participation.user
        user = profile.user
        name = user.first_name or profile.display_name
        team = {
            'id': user.username,
            'label': user.username,
            'name': name,
            'display_name': name,
            'group_ids': [],
            'hidden': participation.is_disqualified,
        }
        org = profile.organization
        if org is not None:
            org_id = str(org.id)
            team['organization_id'] = org_id
            organizations.setdefault(org_id, {
                'id': org_id,
                'name': org.short_name or org.name,
                'formal_name': org.name,
            })
        teams.append(team)
    return teams, list(organizations.values())


def build_submissions_and_judgements(contest: Contest, participations) -> Tuple[List[dict], List[dict]]:
    starts = {participation.id: participation.start for participation in participations}

    contest_submissions = (
        ContestSubmission.objects
        .filter(participation__contest=contest, participation__virtual=ContestParticipation.LIVE)
        .select_related('submission__user__user', 'submission__problem', 'submission__language')
        .order_by('submission__date', 'submission_id')
    )

    submissions = []
    judgements = []
    for contest_submission in contest_submissions.iterator():
        sub = contest_submission.submission
        start = starts.get(contest_submission.participation_id)
        if start is None:
            continue
        submission_id = str(sub.id)
        contest_time = format_reltime(sub.date - start)
        submissions.append({
            'id': submission_id,
            'language_id': sub.language.key,
            'problem_id': sub.problem.code,
            'team_id': sub.user.user.username,
            'time': format_time(sub.date),
            'contest_time': contest_time,
        })

        # A submission still being (re)judged has no judgement: live-v3 shows it as pending.
        if sub.status in sub.IN_PROGRESS_GRADING_STATUS or not sub.result:
            continue
        judged_at = sub.judged_date or sub.date
        judgements.append({
            # One judgement per submission; a rejudge updates it in place.
            'id': submission_id,
            'submission_id': submission_id,
            'judgement_type_id': sub.result,
            'start_time': format_time(sub.date),
            'start_contest_time': contest_time,
            'end_time': format_time(judged_at),
            'end_contest_time': format_reltime(judged_at - start),
        })
    return submissions, judgements


def build_clics_events(contest: Contest, now=None, finalize: bool = False) -> Iterator[dict]:
    """Yield the feed events. With `finalize`, a finished contest whose submissions are all judged is
    marked as finalized (`end_of_updates`), which live-v3 needs before it can replay it."""
    now = now or timezone.now()
    participations = list(live_participations(contest))
    teams, organizations = build_teams_and_organizations(participations)
    submissions, judgements = build_submissions_and_judgements(contest, participations)

    yield _event('contest', build_contest(contest))
    yield _event('judgement-types', build_judgement_types())
    yield _event('languages', build_languages())
    yield _event('problems', build_problems(contest))
    yield _event('organizations', organizations)
    yield _event('teams', teams)
    yield _event('submissions', submissions)
    yield _event('judgements', judgements)
    has_pending = len(judgements) < len(submissions)
    yield _event('state', build_state(contest, now, finalize=finalize, has_pending=has_pending))
