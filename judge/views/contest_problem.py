"""
Contest-specific problem submission views.
Handles problem submissions within contest context.
"""
import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.html import format_html
from django.utils.translation import gettext as _

from judge.models import ContestSubmission, Submission, SubmissionSource
from judge.utils.views import SingleObjectFormView, generic_message
from judge.views.problem import ProblemSubmit
from judge.views.widgets import submission_uploader

user_submit_ip_logger = logging.getLogger('judge.user_submit_ip_logger')


class ContestProblemSubmit(ProblemSubmit):
    """Submit to problem via contest (by order). URL: /contest/{key}/problem/{order}"""

    def dispatch(self, request, *args, **kwargs):
        from judge.models import Contest, ContestProblem

        # Load old submission for resubmit
        submission_id = kwargs.get('submission')
        self.old_submission = (
            get_object_or_404(Submission.objects.select_related('source', 'language'), id=submission_id)
            if submission_id else None
        )
        if self.old_submission:
            if self.old_submission.language.file_only:
                raise Http404()
            if not request.user.has_perm('judge.resubmit_other') and self.old_submission.user != request.profile:
                raise PermissionDenied()

        # Load contest and problem by order
        self.contest = get_object_or_404(Contest, key=kwargs['contest'])
        try:
            self.contest_problem = ContestProblem.objects.select_related('problem').get(
                contest=self.contest, order=int(kwargs['problem']),
            )
            self.object = self.contest_problem.problem
        except (ContestProblem.DoesNotExist, ValueError):
            raise Http404()

        if not self.object.is_accessible_by(request.user):
            raise Http404()

        return SingleObjectFormView.dispatch(self, request, *args, **kwargs)

    def get_object(self, queryset=None):
        return self.object

    def get_participation(self):
        """Get contest participation for the current user."""
        from judge.models import ContestParticipation

        profile = self.request.profile
        if profile.current_contest and profile.current_contest.contest_id == self.contest.id:
            return profile.current_contest

        try:
            return ContestParticipation.objects.get(contest=self.contest, user=profile)
        except ContestParticipation.DoesNotExist:
            return None

    def form_valid(self, form):
        # Validate submission limits and permissions
        if (not self.request.user.has_perm('judge.spam_submission') and
                Submission.objects.filter(user=self.request.profile, rejudged_date__isnull=True)
                .exclude(status__in=['D', 'IE', 'CE', 'AB']).count() >= settings.DMOJ_SUBMISSION_LIMIT):
            return HttpResponse(format_html('<h1>{0}</h1>', _('You submitted too many submissions.')), status=429)

        if not self.object.allowed_languages.filter(id=form.cleaned_data['language'].id).exists():
            raise PermissionDenied()

        if not self.request.user.is_superuser and self.object.banned_users.filter(id=self.request.profile.id).exists():
            return generic_message(self.request, _('Banned from submitting'),
                                   _('You have been declared persona non grata for this problem. '
                                     'You are permanently barred from submitting to this problem.'))

        if self.remaining_submission_count == 0:
            return generic_message(self.request, _('Too many submissions'),
                                   _('You have exceeded the submission limit for this problem.'))

        # Validate participation
        participation = self.get_participation()
        if not participation:
            return generic_message(self.request, _('Not in contest'),
                                   _('You must join the contest before submitting.'))

        # Check organization credits
        if settings.VNOJ_ENABLE_ORGANIZATION_CREDIT_LIMITATION:
            orgs = (list(self.object.organizations.all()) if self.object.is_organization_private
                    else list(self.contest.organizations.all()) if self.contest.is_organization_private else [])
            for org in orgs:
                if not org.has_credit_left():
                    return generic_message(self.request, _('No credit'),
                                           _('The organization %s has no credit left to execute this submission. '
                                             'Ask the organization to buy more credit.') % org.name)

        # Save submission
        with transaction.atomic():
            self.new_submission = form.save(commit=False)
            self.new_submission.contest_object = self.contest
            if participation.live:
                self.new_submission.locked_after = self.contest.locked_after
            self.new_submission.save()

            ContestSubmission(submission=self.new_submission, problem=self.contest_problem,
                              participation=participation).save()

            submission_file = form.files.get('submission_file')
            source_url = submission_uploader(submission_file=submission_file,
                                             problem_code=self.object.code,
                                             user_id=self.request.profile.user.id) if submission_file else ''

            source = SubmissionSource(submission=self.new_submission,
                                      source=form.cleaned_data['source'] + source_url)
            source.save()

        self.new_submission.source = source
        self.new_submission.judge(force_judge=True, judge_id=form.cleaned_data['judge'])

        if settings.VNOJ_OFFICIAL_CONTEST_MODE:
            user_submit_ip_logger.info('%s,%s,%s', self.request.user.username,
                                       self.request.META['REMOTE_ADDR'], self.object.code)

        return SingleObjectFormView.form_valid(self, form)
