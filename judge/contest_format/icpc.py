from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models import Max
from django.template.defaultfilters import floatformat, pluralize
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _, gettext_lazy, ngettext

from judge.contest_format.default import DefaultContestFormat
from judge.contest_format.registry import register_contest_format
from judge.timezone import from_database_time
from judge.utils.timedelta import nice_repr


@register_contest_format('icpc')
class ICPCContestFormat(DefaultContestFormat):
    name = gettext_lazy('ICPC')
    config_defaults = {'penalty': 20}
    config_validators = {'penalty': lambda x: x >= 0}
    """
        penalty: Number of penalty minutes each incorrect submission adds. Defaults to 20.
    """

    @classmethod
    def validate(cls, config):
        if config is None:
            return

        if not isinstance(config, dict):
            raise ValidationError('ICPC-styled contest expects no config or dict as config')

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

    def update_participation(self, participation):
        cumtime = 0
        last = 0
        penalty = 0
        score = 0

        frozen_cumtime = 0
        frozen_last = 0
        frozen_penalty = 0
        frozen_score = 0
        frozen_time = participation.contest.frozen_time

        format_data = {}

        with connection.cursor() as cursor:
            cursor.execute("""
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
            """, (participation.id, participation.id))

            for points, time, prob in cursor.fetchall():
                time = from_database_time(time)
                dt_second = (time - participation.start).total_seconds()
                dt = int(dt_second // 60)
                is_frozen_sub = (participation.is_frozen and time >= frozen_time)

                frozen_points = 0
                frozen_tries = 0
                # Compute penalty
                if self.config['penalty']:
                    # An IE can have a submission result of `None`
                    subs = participation.submissions.exclude(submission__result__isnull=True) \
                                                    .exclude(submission__result__in=['IE', 'CE']) \
                                                    .filter(problem_id=prob)
                    if points:
                        # Submissions after the first AC does not count toward number of tries
                        tries = subs.filter(submission__date__lte=time).count()
                        penalty += (tries - 1) * self.config['penalty']
                        if not is_frozen_sub:
                            # Because the sub have not frozen yet, we update the frozen_penalty just like
                            # the normal penalty
                            frozen_penalty += (tries - 1) * self.config['penalty']
                            frozen_tries = tries
                        else:
                            # For frozen sub, we should always display the number of tries
                            frozen_tries = subs.count()
                    else:
                        # We should always display the penalty, even if the user has a score of 0
                        tries = subs.count()
                        frozen_tries = tries
                        # the raw SQL query above returns the first submission with the
                        # largest points. However, for computing & showing frozen scoreboard,
                        # if the largest points is 0, we need to get the last submission.
                        time = subs.aggregate(time=Max('submission__date'))['time']
                        # time can be None if there all of submissions are CE or IE.
                        is_frozen_sub = (participation.is_frozen and time and time >= frozen_time)
                else:
                    tries = 0
                    # Don't need to set frozen_tries = 0 because we've initialized it with 0

                if points:
                    cumtime += dt
                    last = max(last, dt)
                    score += points

                    if not is_frozen_sub:
                        frozen_points = points
                        frozen_cumtime += dt
                        frozen_last = max(frozen_last, dt)
                        frozen_score += points

                format_data[str(prob)] = {
                    'time': dt_second,
                    'points': points,
                    'frozen_points': frozen_points,
                    'tries': tries,
                    'frozen_tries': frozen_tries,
                    'is_frozen': is_frozen_sub,
                }

        participation.cumtime = cumtime + penalty
        participation.score = round(score, self.contest.points_precision)
        participation.tiebreaker = last  # field is sorted from least to greatest

        participation.frozen_cumtime = frozen_cumtime + frozen_penalty
        participation.frozen_score = round(frozen_score, self.contest.points_precision)
        participation.frozen_tiebreaker = frozen_last

        participation.format_data = format_data
        participation.save()

    def get_first_solves_and_total_ac(self, problems, participations, frozen=False):
        first_solves = {}
        total_ac = {}

        prefix = 'frozen_' if frozen else ''
        for problem in problems:
            problem_id = str(problem.id)
            min_time = None
            first_solves[problem_id] = None
            total_ac[problem_id] = 0

            for participation in participations:
                format_data = (participation.format_data or {}).get(problem_id)
                if format_data:
                    points = format_data[prefix + 'points']
                    time = format_data['time']

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
            # This prefix is used to help get the correct data from the format_data dictionary
            prefix = 'frozen_' if frozen else ''
            submissions_count = format_data[prefix + 'tries']

            if submissions_count == 0:
                return mark_safe('<td></td>')

            tries = format_html(
                '{tries} {msg}',
                tries=submissions_count,
                msg=pluralize(submissions_count, 'try,tries'),
            )

            # The cell will have `pending` css class if there is a new score-changing submission after the frozen time
            state = (('pending ' if frozen and format_data['is_frozen'] else '') +
                     ('pretest-' if self.contest.run_pretests_only and contest_problem.is_pretested else '') +
                     ('first-solve ' if first_solves.get(str(contest_problem.id), None) == participation.id else '') +
                     self.best_solution_state(format_data[prefix + 'points'], contest_problem.points))
            url = reverse('contest_user_submissions',
                          args=[self.contest.key, participation.user.user.username, contest_problem.problem.code])

            if not format_data[prefix + 'points']:
                return format_html(
                    '<td class="{state}"><a href="{url}">{tries}</a></td>',
                    state=state,
                    url=url,
                    tries=tries,
                )

            return format_html(
                ('<td class="{state}">'
                 '<a href="{url}"><div class="solving-time-minute">{minute}</div>'
                 '<div class="solving-time">{time}</div>{tries}</a></td>'),
                state=state,
                url=url,
                tries=tries,
                minute=int(format_data['time'] // 60),
                time=nice_repr(timedelta(seconds=format_data['time']), 'noday'),
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
            ('<td class="user-points"><a href="{url}">{points}</a></td>'
             '<td class="user-penalty">{cumtime}</td>'),
            url=reverse('contest_all_user_submissions',
                        args=[self.contest.key, participation.user.user.username]),
            points=floatformat(points, -self.contest.points_precision),
            cumtime=floatformat(cumtime, 0),
        )

    def get_label_for_problem(self, index):
        index += 1
        ret = ''
        while index > 0:
            ret += chr((index - 1) % 26 + 65)
            index = (index - 1) // 26
        return ret[::-1]

    def get_short_form_display(self):
        yield _('The maximum score submission for each problem will be used.')

        penalty = self.config['penalty']
        if penalty:
            yield ngettext(
                'Each submission before the first maximum score submission will incur a **penalty of %d minute**.',
                'Each submission before the first maximum score submission will incur a **penalty of %d minutes**.',
                penalty,
            ) % penalty
            yield _('Ties will be broken by the sum of the last score altering submission time on problems with '
                    'a non-zero score (including penalty), followed by the time of the last score altering submission.')
        else:
            yield _('Ties will be broken by the sum of the last score altering submission time on problems with '
                    'a non-zero score, followed by the time of the last score altering submission.')

        if self.contest.frozen_last_minutes:
            yield ngettext(
                'The scoreboard will be frozen in the **last %d minute**.',
                'The scoreboard will be frozen in the **last %d minutes**.',
                self.contest.frozen_last_minutes,
            ) % self.contest.frozen_last_minutes
