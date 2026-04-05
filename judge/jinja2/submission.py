from judge.models import SubmissionSourceAccess
from judge.models.role import ContestRole, ROLE_AUTHOR, ROLE_CURATOR
from . import registry


def get_editor_ids(contest):
    return set(ContestRole.objects.filter(
        contest=contest, role__in=[ROLE_AUTHOR, ROLE_CURATOR],
    ).values_list('user_id', flat=True))


@registry.function
def submission_layout(submission, profile_id, user, completed_problem_ids, editable_problem_ids, tester_problem_ids):
    if not user.is_authenticated:
        return False, False

    problem_id = submission.problem_id
    submission_source_visibility = submission.problem.submission_source_visibility
    can_view = False
    can_edit = False

    if (user.has_perm('judge.edit_all_problem') or
            (user.has_perm('judge.edit_public_problem') and submission.problem.is_public) or
            # We try to avoid evaluating this as much as possible to keep it lazy.
            problem_id in editable_problem_ids):
        can_view = True
        can_edit = True
    elif user.has_perm('judge.view_all_submission'):
        can_view = True
    elif profile_id == submission.user_id:
        can_view = True
    elif not submission.problem.is_public and user.has_perm('judge.suggest_new_problem') and \
            submission.problem.is_suggesting:
        can_view = True
    elif submission_source_visibility == SubmissionSourceAccess.ALWAYS:
        can_view = True
    elif submission.contest_object is not None and profile_id in get_editor_ids(submission.contest_object):
        can_view = True
    elif submission.problem_id in completed_problem_ids:
        can_view = submission.problem_id in tester_problem_ids
        if submission_source_visibility == SubmissionSourceAccess.SOLVED:
            can_view = can_view or submission.problem.is_public

    return can_view, can_edit
