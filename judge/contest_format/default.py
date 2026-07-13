from django.core.exceptions import ValidationError
from django.db.models import Max
from django.utils.translation import gettext as _, gettext_lazy

from judge.contest_format.base import BaseContestFormat
from judge.contest_format.registry import register_contest_format


@register_contest_format('default')
class DefaultContestFormat(BaseContestFormat):
    name = gettext_lazy('Default')

    @classmethod
    def validate(cls, config):
        if config is not None and (not isinstance(config, dict) or config):
            raise ValidationError('default contest expects no config or empty dict as config')

    def __init__(self, contest, config):
        super(DefaultContestFormat, self).__init__(contest, config)

    def update_participation(self, participation):
        cumtime = 0
        points = 0
        format_data = {}

        for result in participation.submissions.values('problem_id').annotate(
                time=Max('submission__date'), points=Max('points'),
        ):
            dt = (result['time'] - participation.start).total_seconds()
            if result['points']:
                cumtime += dt
            format_data[str(result['problem_id'])] = {'time': dt, 'points': result['points']}
            points += result['points']

        participation.cumtime = max(cumtime, 0)
        participation.score = round(points, self.contest.points_precision)
        participation.tiebreaker = 0
        participation.format_data = format_data
        participation.save()

    def get_problem_breakdown(self, participation, contest_problems):
        return [(participation.format_data or {}).get(str(contest_problem.id)) for contest_problem in contest_problems]

    def get_label_for_problem(self, index):
        return str(index + 1)

    def get_short_form_display(self):
        yield _('The maximum score submission for each problem will be used.')
        yield _('Ties will be broken by the sum of the last submission time on problems with '
                'a non-zero score.')
