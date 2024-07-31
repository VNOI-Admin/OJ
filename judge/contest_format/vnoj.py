from collections import namedtuple
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import connection
from django.template.defaultfilters import floatformat
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _, gettext_lazy, ngettext

from judge.contest_format.default import DefaultContestFormat
from judge.contest_format.registry import register_contest_format
from judge.timezone import from_database_time, to_database_time
from judge.utils.timedelta import nice_repr

ParticipationInfo = namedtuple('ParticipationInfo', 'cumtime score tiebreaker format_data')

DEFAULT_RANKING_SQL = """
SELECT MAX(cs.points) as `points`, (
    SELECT MIN(csub.date)
        FROM judge_contestsubmission ccs LEFT OUTER JOIN
                judge_submission csub ON (csub.id = ccs.submission_id)
        WHERE ccs.problem_id = cp.id AND ccs.participation_id = %s AND ccs.points = MAX(cs.points)
) AS `time`, cp.id AS `prob`
FROM judge_contestproblem cp INNER JOIN
        judge_contestsubmission cs ON (cs.problem_id = cp.id AND cs.participation_id = %s) LEFT OUTER JOIN
        judge_submission sub ON (sub.id = cs.submission_id)
GROUP BY cp.id
"""

FROZEN_RANKING_SQL = """
SELECT MAX(cs.points) as `points`, (
    SELECT MIN(csub.date)
        FROM judge_contestsubmission ccs LEFT OUTER JOIN
                judge_submission csub ON (csub.id = ccs.submission_id)
        WHERE ccs.problem_id = cp.id AND ccs.participation_id = %s AND ccs.points = MAX(cs.points) AND csub.date < %s
) AS `time`, cp.id AS `prob`
FROM judge_contestproblem cp INNER JOIN
        judge_contestsubmission cs ON (cs.problem_id = cp.id AND cs.participation_id = %s) LEFT OUTER JOIN
        judge_submission sub ON (sub.id = cs.submission_id)
WHERE sub.date < %s
GROUP BY cp.id
"""


@register_contest_format('vnoj')
class VNOJContestFormat(DefaultContestFormat):
    name = gettext_lazy('VNOJ')
    config_defaults = {'penalty': 5, 'LSO': False}
    config_validators = {'penalty': lambda x: x >= 0, 'LSO': lambda x: isinstance(x, bool)}
    """
        penalty: Number of penalty minutes each incorrect submission adds. Defaults to 5.
        LSO: Last submission only. If true, cumtime will used the last submission time, not the total time of
        all submissions.
    """

    @classmethod
    def validate(cls, config):
        if config is None:
            return

        if not isinstance(config, dict):
            raise ValidationError('VNOJ-styled contest expects no config or dict as config')

        for key, value in config.items():
            if key not in cls.config_defaults:
                raise ValidationError('unknown config key "%s"' % key)
            if not isinstance(value, type(cls.config_defaults[key])):
                raise ValidationError('invalid type for config key "%s"' % key)
            if not cls.config_validators[key](value):
                raise ValidationError('invalid value "%s" for config key "%s"' % (value, key))

    def __init__(self, contest, config):
        self.config = self.config_defaults.copy()
        self.config.update(config or {})
        self.contest = contest

    def calculate_participation_info(self, participation, frozen=False) -> ParticipationInfo:
        cumtime = 0
        last = 0
        penalty = 0
        score = 0
        format_data = {}

        frozen_time = participation.contest.frozen_time

        with connection.cursor() as cursor:
            if not frozen:
                cursor.execute(DEFAULT_RANKING_SQL, (participation.id, participation.id))
            else:
                db_time = to_database_time(frozen_time)
                cursor.execute(FROZEN_RANKING_SQL, (participation.id, db_time,
                                                    participation.id, db_time))

            for points, time, prob in cursor.fetchall():
                time = from_database_time(time)
                dt = (time - participation.start).total_seconds()
                # An IE can have a submission result of `None`
                problem_subs = participation.submissions.exclude(submission__result__isnull=True) \
                                            .exclude(submission__result__in=['IE', 'CE']) \
                                            .filter(problem_id=prob)

                # Compute penalty
                if self.config['penalty']:
                    subs = problem_subs
                    if frozen:
                        subs = subs.filter(submission__date__lt=frozen_time)

                    if points:
                        prev = subs.filter(submission__date__lte=time).count() - 1
                        penalty += prev * self.config['penalty'] * 60
                    else:
                        # We should always display the penalty, even if the user has a score of 0
                        prev = subs.count()
                else:
                    prev = 0

                if points:
                    cumtime += dt
                    last = max(last, dt)

                format_data[str(prob)] = {'time': dt, 'points': points, 'penalty': prev}

                if not frozen and participation.contest.frozen_last_minutes != 0:
                    format_data[str(prob)]['pending'] = problem_subs \
                        .filter(submission__date__gte=frozen_time) \
                        .count()

                score += points

        return ParticipationInfo(
            cumtime=max((last if self.config['LSO'] else cumtime) + penalty, 0),
            score=round(score, self.contest.points_precision),
            tiebreaker=last,
            format_data=format_data,
        )

    def update_participation(self, participation):
        actual_info = self.calculate_participation_info(participation)

        participation.cumtime = actual_info.cumtime
        participation.score = actual_info.score
        participation.tiebreaker = actual_info.tiebreaker
        format_data = actual_info.format_data

        if participation.contest.frozen_last_minutes != 0:
            frozen_info = self.calculate_participation_info(participation, frozen=True)
            participation.frozen_cumtime = frozen_info.cumtime
            participation.frozen_score = frozen_info.score
            participation.frozen_tiebreaker = frozen_info.tiebreaker

            # merge format_data
            for prob, data in format_data.items():
                frozen_data = frozen_info.format_data.get(prob, {})
                new_prob_data = {**data}
                for key in data.keys():
                    if key != 'pending':
                        new_prob_data['frozen_' + key] = frozen_data.get(key, 0)

                format_data[prob] = new_prob_data

        participation.format_data = format_data
        participation.save()

    def get_first_solves_and_total_ac(self, problems, participations, frozen=False):
        first_solves = {}
        total_ac = {}

        for problem in problems:
            problem_id = str(problem.id)
            min_time = None
            first_solves[problem_id] = None
            total_ac[problem_id] = 0

            for participation in participations:
                format_data = (participation.format_data or {}).get(problem_id)
                if format_data:
                    has_pending = bool(format_data.get('pending', 0))
                    prefix = 'frozen_' if frozen and has_pending else ''
                    points = format_data[prefix + 'points']
                    time = format_data[prefix + 'time']

                    if points == problem.points:
                        total_ac[problem_id] += 1

                        # Only acknowledge first solves for live participations
                        if participation.virtual == 0 and (min_time is None or min_time > time):
                            min_time = time
                            first_solves[problem_id] = participation.id

        return first_solves, total_ac

    def display_user_problem(self, participation, contest_problem, first_solves, frozen=False):
        format_data = (participation.format_data or {}).get(str(contest_problem.id))

        if format_data:
            first_solved = first_solves.get(str(contest_problem.id), None) == participation.id
            url = reverse('contest_user_submissions',
                          args=[self.contest.key, participation.user.user.username, contest_problem.problem.code])

            if not frozen:
                # Fast path for non-frozen contests
                penalty = format_html(
                    '<small style="color:red"> ({penalty})</small>',
                    penalty=floatformat(format_data['penalty']),
                ) if format_data['penalty'] else ''

                state = (('pretest-' if self.contest.run_pretests_only and contest_problem.is_pretested else '') +
                         ('first-solve ' if first_solved else '') +
                         self.best_solution_state(format_data['points'], contest_problem.points))

                points = floatformat(format_data['points'], -self.contest.points_precision)
                time = nice_repr(timedelta(seconds=format_data['time']), 'noday')

                return format_html(
                    '<td class="{state}"><a href="{url}"><div>{points}{penalty}</div>'
                    '<div class="solving-time">{time}</div></a></td>',
                    state=state,
                    url=url,
                    points=points,
                    penalty=penalty,
                    time=time,
                )

            # This prefix is used to help get the correct data from the format_data dictionary
            has_pending = bool(format_data.get('pending', 0))
            prefix = 'frozen_' if has_pending else ''

            # AC before frozen_time
            if has_pending and format_data[prefix + 'points'] == contest_problem.points:
                has_pending = False
                prefix = ''

            penalty = format_html(
                '<small style="color:red"> ({penalty})</small>',
                penalty=floatformat(format_data[prefix + 'penalty']),
            ) if format_data[prefix + 'penalty'] else ''

            state = (('pending ' if has_pending else '') +
                     ('pretest-' if self.contest.run_pretests_only and contest_problem.is_pretested else '') +
                     ('first-solve ' if first_solved else '') +
                     self.best_solution_state(format_data[prefix + 'points'], contest_problem.points))

            points = floatformat(format_data[prefix + 'points'], -self.contest.points_precision)
            time = nice_repr(timedelta(seconds=format_data[prefix + 'time']), 'noday')
            pending = format_html(' <small style="color:black;">[{pending}]</small>',
                                  pending=floatformat(format_data['pending'])) if has_pending else ''

            if has_pending:
                time = '?'
                # hide penalty if there are pending submissions
                penalty = ''

                # if user have no submission before the frozen time, we display points as '?'
                if format_data.get('frozen_points', 0) == 0 and format_data.get('frozen_penalty', 0) == 0:
                    points = '?'
                else:
                    # if user have submissions before the frozen time, we display points as points + '?'
                    points = points + '?'

            return format_html(
                '<td class="{state}"><a href="{url}"><div>{points}{penalty}{pending}</div>'
                '<div class="solving-time">{time}</div></a></td>',
                state=state,
                url=url,
                points=points,
                penalty=penalty,
                time=time,
                pending=pending,
            )
        else:
            return mark_safe('<td></td>')

    def display_participation_result(self, participation, frozen=False):
        if frozen:
            points = participation.frozen_score
            cumtime = participation.frozen_cumtime
        else:
            points = participation.score
            cumtime = participation.cumtime
        return format_html(
            '<td class="user-points"><a href="{url}">{points}<div class="solving-time">{cumtime}</div></a></td>',
            url=reverse('contest_all_user_submissions',
                        args=[self.contest.key, participation.user.user.username]),
            points=floatformat(points, -self.contest.points_precision),
            cumtime=nice_repr(timedelta(seconds=cumtime), 'noday'),
        )

    def get_short_form_display(self):
        yield _('The maximum score submission for each problem will be used.')

        penalty = self.config['penalty']
        if penalty:
            yield ngettext(
                'Each submission before the first maximum score submission will incur a **penalty of %d minute**.',
                'Each submission before the first maximum score submission will incur a **penalty of %d minutes**.',
                penalty,
            ) % penalty
            if self.config['LSO']:
                yield _('Ties will be broken by the time of the last score altering submission (including penalty).')
            else:
                yield _('Ties will be broken by the sum of the last score altering submission time on problems with '
                        'a non-zero score (including penalty), followed by the time of the last score altering '
                        'submission.')
        else:
            if self.config['LSO']:
                yield _('Ties will be broken by the time of the last score altering submission.')
            else:
                yield _('Ties will be broken by the sum of the last score altering submission time on problems with '
                        'a non-zero score, followed by the time of the last score altering submission.')

        if self.contest.frozen_last_minutes:
            yield ngettext(
                'The scoreboard will be frozen in the **last %d minute**.',
                'The scoreboard will be frozen in the **last %d minutes**.',
                self.contest.frozen_last_minutes,
            ) % self.contest.frozen_last_minutes
