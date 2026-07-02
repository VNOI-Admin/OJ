from django.shortcuts import get_object_or_404
from django.urls import reverse

__all__ = ['contest_problem_order', 'problem_url', 'problem_label', 'resolve_contest_problem']

# Maps a logical problem view to its (contest-scoped, global) URL names. The
# contest-scoped route takes (contest.key, order, *extra); the global route
# takes (problem.code, *extra).
_VIEW_NAMES = {
    'detail': ('contest_problem_detail', 'problem_detail'),
    'submit': ('contest_problem_submit', 'problem_submit'),
    'raw': ('contest_problem_raw', 'problem_raw'),
    'pdf': ('contest_problem_pdf', 'problem_pdf'),
    'editorial': ('contest_problem_editorial', 'problem_editorial'),
    'rank': ('contest_problem_ranked_submissions', 'ranked_submissions'),
    'submissions': ('contest_problem_submissions', 'chronological_submissions'),
    'user_submissions': ('contest_problem_user_submissions', 'user_submissions'),
    'new_ticket': ('contest_new_problem_ticket', 'new_problem_ticket'),
}


def contest_problem_order(contest, problem):
    """Return the order of `problem` inside `contest`, or None if it is not in it.

    The problem_id -> order map is memoized on the contest instance so that
    rendering a page full of problem links costs a single query.
    """
    if contest is None or problem is None:
        return None
    cache = getattr(contest, '_cp_order_map', None)
    if cache is None:
        cache = contest._cp_order_map = dict(contest.contest_problems.values_list('problem_id', 'order'))
    return cache.get(problem.id)


def problem_url(problem, view='detail', contest=None, extra=()):
    """Reverse a problem-related URL, preferring the contest namespace.

    If `contest` is given and contains the problem, the contest-scoped route is
    returned; otherwise this falls back to the global route, so it is always
    safe to call for mixed lists.
    """
    contest_view, global_view = _VIEW_NAMES[view]
    if contest is not None:
        order = contest_problem_order(contest, problem)
        if order is not None:
            return reverse(contest_view, args=(contest.key, order, *extra))
    return reverse(global_view, args=(problem.code, *extra))


def problem_label(problem, contest=None):
    """The contest label ('A', '1', ...) of a problem, or its code outside a contest."""
    order = contest_problem_order(contest, problem)
    if order is not None:
        return contest.get_label_for_problem(order - 1)
    return problem.code


def resolve_contest_problem(contest, segment):
    """Resolve a URL segment that is either a ContestProblem.order or a Problem.code.

    Inside the contest namespace, an all-digit segment is interpreted as an
    order first; a problem whose code happens to be all digits is shadowed.
    """
    from judge.models import Problem

    if segment.isdigit():
        contest_problem = (contest.contest_problems.select_related('problem')
                           .filter(order=int(segment)).order_by('id').first())
        if contest_problem is not None:
            return contest_problem.problem
    return get_object_or_404(Problem, code=segment, contests__contest=contest)
