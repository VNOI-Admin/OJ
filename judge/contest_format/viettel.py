from datetime import timedelta

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Count, Max
from django.template.defaultfilters import floatformat, pluralize
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from judge.contest_format.base import BaseContestFormat
from judge.contest_format.registry import register_contest_format


@register_contest_format('viettel')
class ViettelContestFormat(BaseContestFormat):
    name = _('Viettel')

    @classmethod
    def validate(cls, config):
        if config is not None and (not isinstance(config, dict) or config):
            raise ValidationError('viettel contest expects no config or empty dict as config')

    def __init__(self, contest, config):
        super(ViettelContestFormat, self).__init__(contest, config)

    def get_max_scores(self, use_cache=True):
        """
        Get max scores for all problems, using cache if available.
        Returns tuple: (global_maxes, problem_points)
        """
        cache_key = f'viettel_max_scores:{self.contest.id}'

        if use_cache:
            cached = cache.get(cache_key)
            if cached:
                return cached

        # Calculate from database
        global_maxes = {}
        problem_points = {}
        for cp in self.contest.contest_problems.all():
            global_maxes[cp.id] = cp.submissions.aggregate(m=Max('points'))['m'] or 0
            problem_points[cp.id] = cp.points

        result = (global_maxes, problem_points)
        cache.set(cache_key, result, 86400)
        return result

    def compute_score(self, participation):
        cumtime = 0
        raw_data = {}

        for result in participation.submissions.exclude(submission__result__in=['IE', 'CE']).values('problem_id').annotate(
                time=Max('submission__date'), points=Max('points'), tries=Count('id')
        ):
            dt = (result['time'] - participation.start).total_seconds()
            if result['points']:
                cumtime += dt
            raw_data[result['problem_id']] = {
                'time': dt, 'points': result['points'], 'tries': result['tries']
            }

        return raw_data, max(cumtime, 0)

    def update_participation(self, participation):
        raw_data, cumtime = self.compute_score(participation)

        global_maxes, problem_points = self.get_max_scores()

        for problem_id, data in raw_data.items():
            if data['points'] > global_maxes.get(problem_id, 0):
                # new max score -> trigger full rescore
                from judge.tasks.contest import rescore_contest
                rescore_contest.delay(self.contest.key)
                return

        # Recalculate score for current participation only
        self.recalculate_score(participation, global_maxes, problem_points, raw_data, cumtime)

    def recalculate_score(self, participation, global_maxes, problem_points, raw_data, cumtime):
        score = 0
        format_data = {}

        for pid, data in raw_data.items():
            max_p = global_maxes.get(pid, 0)
            p_points = problem_points.get(pid, 0)
            scaled_points = 0
            if max_p > 0:
                scaled_points = (data['points'] / max_p) * p_points

            score += scaled_points
            data['scaled_points'] = scaled_points
            data['max_points'] = max_p
            format_data[str(pid)] = data

        participation.score = round(score, self.contest.points_precision)
        participation.cumtime = cumtime
        participation.tiebreaker = 0
        participation.format_data = format_data
        participation.save()

    def get_first_solves_and_total_ac(self, problems, participations, frozen=False):
        first_solves = {}
        total_ac = {}

        for problem in problems:
            problem_id = str(problem.id)
            total_ac[problem_id] = 0

            max_points = 0
            min_time = None
            first_solver = None

            for participation in participations:
                format_data = (participation.format_data or {}).get(problem_id)
                if format_data:
                    points = format_data['points']
                    time = format_data['time']

                    if points == problem.points:
                        total_ac[problem_id] += 1

                    if participation.virtual == 0:
                        if points > max_points:
                            max_points = points
                            min_time = time
                            first_solver = participation.id
                        elif points == max_points and points > 0:
                            if min_time is None or time < min_time:
                                min_time = time
                                first_solver = participation.id

            first_solves[problem_id] = first_solver

        return first_solves, total_ac

    def display_user_problem(self, participation, contest_problem, first_solves, frozen=False):
        format_data = (participation.format_data or {}).get(str(contest_problem.id))

        if format_data:
            tries = format_data.get('tries', 0)
            return format_html(
                '<td class="{state}"><a href="{url}">{points}<div class="tries">{tries}</div></a></td>',
                state=(('pretest-' if self.contest.run_pretests_only and contest_problem.is_pretested else '') +
                       ('first-solve ' if first_solves.get(str(contest_problem.id), None) == participation.id else '') +
                       self.best_solution_state(format_data['points'], format_data.get('max_points', contest_problem.points))),
                url=reverse('contest_user_submissions',
                            args=[self.contest.key, participation.user.user.username, contest_problem.problem.code]),
                points=floatformat(format_data['points'], -self.contest.points_precision),
                tries=format_html('{tries} {msg}', tries=tries, msg=pluralize(tries, _('try,tries'))),
            )
        else:
            return mark_safe('<td></td>')

    def display_participation_result(self, participation, frozen=False):
        return format_html(
            '<td class="user-points"><a href="{url}">{points}</a></td>',
            url=reverse('contest_all_user_submissions',
                        args=[self.contest.key, participation.user.user.username]),
            points=floatformat(participation.score, -self.contest.points_precision),
        )

    def get_problem_breakdown(self, participation, contest_problems):
        return [(participation.format_data or {}).get(str(contest_problem.id)) for contest_problem in contest_problems]

    def get_label_for_problem(self, index):
        return str(index + 1)

    def get_short_form_display(self):
        yield _('The maximum score submission for each problem will be used.')
        yield _('The score is normalized against the highest score obtained by any participant.')
