from django.core.exceptions import ValidationError
from django.db.models import Max
from django.utils.translation import gettext as _, gettext_lazy

from judge.contest_format.base import BaseContestFormat
from judge.contest_format.registry import register_contest_format


@register_contest_format('default')
class DefaultContestFormat(BaseContestFormat):
    name = gettext_lazy('Default')
    config_defaults = {'scale': False}
    config_validators = {'scale': lambda x: isinstance(x, bool)}
    """
        scale: Specify True to scale the scoreboard, so that on every problem the highest score achieved is worth
        the problem's full points. This only affects how the ranking is displayed; stored scores are unchanged.
        Defaults to False.
    """

    @classmethod
    def validate(cls, config):
        if config is None:
            return

        if not isinstance(config, dict):
            raise ValidationError('default contest expects no config or dict as config')

        for key, value in config.items():
            if key not in cls.config_defaults:
                raise ValidationError('unknown config key "%s"' % key)
            if not isinstance(value, type(cls.config_defaults[key])):
                raise ValidationError('invalid type for config key "%s"' % key)
            validator = cls.config_validators.get(key)
            if validator is not None and not validator(value):
                raise ValidationError('invalid value "%s" for config key "%s"' % (value, key))

    def __init__(self, contest, config):
        self.config = self.config_defaults.copy()
        self.config.update(config or {})
        self.contest = contest

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

    def get_scale_display(self):
        """Formats supporting the `scale` config key should chain this onto get_short_form_display()."""
        if self.config.get('scale'):
            yield _('Scores are scaled: on each problem, the highest score achieved is worth the '
                    "problem's full points.")

    def get_short_form_display(self):
        yield _('The maximum score submission for each problem will be used.')
        yield _('Ties will be broken by the sum of the last submission time on problems with '
                'a non-zero score.')
        yield from self.get_scale_display()
