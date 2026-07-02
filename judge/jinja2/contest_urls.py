from jinja2 import pass_context

from judge.utils import contest_problems
from . import registry


def _ambient_contest(context, contest):
    if contest is not None:
        return contest
    request = context.get('request')
    return getattr(request, 'contest_scope', None)


@registry.function
@pass_context
def problem_url(context, problem, view='detail', contest=None, *extra):
    return contest_problems.problem_url(problem, view, _ambient_contest(context, contest), extra)


@registry.function
@pass_context
def problem_label(context, problem, contest=None):
    return contest_problems.problem_label(problem, _ambient_contest(context, contest))
