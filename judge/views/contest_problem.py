from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from django.utils.translation import gettext as _

from judge.models import Contest
from judge.utils.problems import contest_attempted_ids, contest_completed_ids
from judge.utils.views import generic_message
from judge.views.problem import ProblemDeleted, ProblemDetail, ProblemPdfView, ProblemRaw, ProblemSolution, \
    ProblemSubmit

__all__ = ['ContestProblemResolverMixin', 'ContestProblemDetail', 'ContestProblemSubmit', 'ContestProblemRaw',
           'ContestProblemPdfView', 'ContestProblemSolution']


class ContestProblemResolverMixin:
    """Resolves (contest key, order) -> ContestProblem -> Problem for /contest/<key>/<order>/... views.

    Replaces the current_contest-coupled access check of ProblemMixin with a
    contest-scoped one, and derives the participation a submission would be
    attributed to from the URL contest instead of the session. Must be first in
    the MRO so that `contest`, `contest_problem` and `submission_participation`
    shadow their session-based counterparts.
    """

    @cached_property
    def contest(self):
        return get_object_or_404(Contest, key=self.kwargs['contest'])

    @cached_property
    def contest_problem(self):
        # filter().first() instead of get(): tolerates duplicate orders on
        # deployments that have not run the normalization migration yet.
        contest_problem = (self.contest.contest_problems.select_related('problem')
                           .filter(order=self.kwargs['order']).order_by('id').first())
        if contest_problem is None:
            raise Http404()
        contest_problem.contest = self.contest
        return contest_problem

    @cached_property
    def url_participation(self):
        """The requester's participation in the URL contest, preferring an unended one."""
        if not self.request.user.is_authenticated:
            return None
        profile = self.request.profile
        current = profile.current_contest
        if current is not None and current.contest_id == self.contest.id:
            return current
        participations = list(self.contest.users.filter(user=profile).order_by('-virtual'))
        for participation in participations:
            if not participation.ended:
                return participation
        return participations[0] if participations else None

    @cached_property
    def submission_participation(self):
        participation = self.url_participation
        if participation is not None and not participation.ended:
            return participation
        return None

    def check_contest_problem_access(self, problem):
        user = self.request.user
        contest = self.contest
        if contest.is_editable_by(user):
            return
        if user.is_authenticated and self.request.profile.id in contest.tester_ids:
            return
        if not contest.is_accessible_by(user):
            raise Http404()
        if not contest.can_join:
            # Before the start, only editors and testers may see the problems.
            raise Http404()
        if self.url_participation is not None and not self.url_participation.ended:
            return
        # Archive mode (ended contest, ended participation, or non-participant
        # during the contest): fall back to the problem's own global visibility,
        # bypassing the current_contest branch so an unrelated active contest
        # can neither grant nor deny it.
        if problem.is_accessible_by(user, skip_contest_problem_check=True):
            return
        raise Http404()

    def get_object(self, queryset=None):
        problem = self.contest_problem.problem
        self.check_contest_problem_access(problem)
        if problem.is_deleted:
            raise ProblemDeleted(problem_name=problem.name)
        return problem

    def no_such_problem(self):
        return generic_message(self.request, _('No such problem'),
                               _('Could not find problem %(order)s in the contest "%(contest)s".') %
                               {'order': self.kwargs.get('order'), 'contest': self.kwargs.get('contest')},
                               status=404)

    def handle_submission_post(self, request):
        # Submitting through the contest namespace requires an active (unended)
        # participation while the contest runs; after the end it degrades to a
        # practice submission, so no guard is needed then.
        if self.submission_participation is None and not self.contest.ended:
            return generic_message(request, _('Not in contest'),
                                   _('You have to join the contest "%s" to submit to this problem.') %
                                   self.contest.name), None
        return super().handle_submission_post(request)

    def get_completed_problems(self):
        # Status icons reflect the participation while the user is in this
        # contest (live or virtual); spectators cannot submit, so they keep
        # their general solved status.
        participation = self.submission_participation
        if participation is not None and not participation.spectate:
            return contest_completed_ids(participation)
        return super().get_completed_problems()

    def get_attempted_problems(self):
        participation = self.submission_participation
        if participation is not None and not participation.spectate:
            return contest_attempted_ids(participation)
        return super().get_attempted_problems()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['contest'] = self.contest
        context['contest_problem'] = self.contest_problem
        context['problem_label'] = self.contest_problem.label
        return context

    def dispatch(self, request, *args, **kwargs):
        # The URL contest wins over the session participation for link generation.
        request.contest_scope = self.contest
        return super().dispatch(request, *args, **kwargs)


class ContestProblemDetail(ContestProblemResolverMixin, ProblemDetail):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if context.get('title'):
            context['title'] = '%s. %s' % (self.contest_problem.label, context['title'])
        return context


class ContestProblemSubmit(ContestProblemResolverMixin, ProblemSubmit):
    pass


class ContestProblemRaw(ContestProblemResolverMixin, ProblemRaw):
    pass


class ContestProblemPdfView(ContestProblemResolverMixin, ProblemPdfView):
    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        # Only the download filename is contest-scoped; the disk cache stays
        # keyed on the problem code (see ProblemPdfView).
        language = kwargs.get('language', request.LANGUAGE_CODE)
        response['Content-Disposition'] = 'inline; filename="%s-%s.%s.pdf"' % (
            self.contest.key, self.contest_problem.label, language)
        return response


class ContestProblemSolution(ContestProblemResolverMixin, ProblemSolution):
    def editorial_access_check(self, solution):
        if not solution.is_accessible_by(self.request.user):
            raise Http404()
        if self.contest.is_editable_by(self.request.user):
            return
        # Editorials of a contest problem are unavailable until the contest
        # ends, and stay hidden from users who are amid any other contest.
        if not self.contest.ended or self.request.in_contest:
            raise Http404()
