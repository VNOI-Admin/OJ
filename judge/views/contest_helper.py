from datetime import timedelta

from django import forms
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import FormView

from judge.models import Contest, ContestParticipation, ContestProblem, Problem, Profile
from judge.utils.views import TitleMixin
from judge.views.select2 import Select2View
from judge.widgets import HeavySelect2Widget


# ---------------------------------------------------------------------------
# AJAX helpers
# ---------------------------------------------------------------------------

class ContestKeySelect2View(Select2View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Contest.objects.filter(
            Q(key__icontains=self.term) | Q(name__icontains=self.term)
        )

    def get(self, request, *args, **kwargs):
        self.request = request
        self.term = kwargs.get('term', request.GET.get('term', ''))
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        return JsonResponse({
            'results': [
                {'text': f'{obj.key} — {obj.name}', 'id': obj.key}
                for obj in context['object_list']
            ],
            'more': context['page_obj'].has_next(),
        })


class ProfilePrefixCountView(View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        prefix = request.GET.get('prefix', '').strip()
        if not prefix:
            return JsonResponse({'count': 0, 'prefix': prefix})
        count = Profile.objects.filter(user__username__startswith=prefix).count()
        return JsonResponse({'count': count, 'prefix': prefix})


class ProblemPrefixCountView(View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        prefix = request.GET.get('prefix', '').strip()
        if not prefix:
            return JsonResponse({'count': 0, 'prefix': prefix})
        count = Problem.objects.filter(code__startswith=prefix).count()
        return JsonResponse({'count': count, 'prefix': prefix})


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

def _contest_key_field():
    return forms.CharField(
        label=_('Contest'),
        widget=HeavySelect2Widget(
            data_view='contest_helper_contest_select2',
            attrs={'style': 'width: 100%'},
        ),
    )


class AddToContestForm(forms.Form):
    contest_key = _contest_key_field()
    profile_prefixes = forms.CharField(
        label=_('Profile prefixes'),
        widget=forms.Textarea(attrs={'rows': 6, 'style': 'width: 100%; font-family: monospace;'}),
        help_text=_('One username prefix per line, e.g. A_'),
    )
    private = forms.BooleanField(
        required=False,
        label=_('Add as private contestants'),
        help_text=_('Also adds users to private_contestants and sets the contest as private.'),
    )
    no_self_join = forms.BooleanField(
        required=False,
        initial=True,
        label=_('Disallow self-join'),
        help_text=_('Sets the registration window to 1 day before now, preventing users from joining themselves.'),
    )


class AddProblemToContestForm(forms.Form):
    contest_key = _contest_key_field()
    problem_prefix = forms.CharField(
        label=_('Problem code prefix'),
        max_length=100,
        widget=forms.TextInput(attrs={'style': 'width: 100%; font-family: monospace;'}),
        help_text=_('Problems whose code starts with this prefix will be added, ordered by code.'),
    )
    points = forms.IntegerField(
        label=_('Points per problem'),
        initial=100,
        min_value=0,
    )


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class ContestHelperIndexView(TitleMixin, View):
    template_name = 'contest_helper/index.html'
    title = _('Contest Helper')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        from django.shortcuts import render
        return render(request, self.template_name, {'title': self.title})


class AddProfileToContestView(TitleMixin, FormView):
    template_name = 'contest_helper/profile.html'
    form_class = AddToContestForm
    title = _('Add profiles to contest')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse('contest_helper_profile')

    def form_valid(self, form):
        contest_key = form.cleaned_data['contest_key']
        prefixes = [
            p.strip()
            for p in form.cleaned_data['profile_prefixes'].splitlines()
            if p.strip()
        ]
        private = form.cleaned_data['private']
        no_self_join = form.cleaned_data['no_self_join']

        try:
            contest = Contest.objects.get(key=contest_key)
        except Contest.DoesNotExist:
            form.add_error('contest_key', _('Contest with key "%s" does not exist.') % contest_key)
            return self.form_invalid(form)

        if no_self_join:
            past = timezone.now() - timedelta(days=1)
            contest.registration_start = past
            contest.registration_end = past
            contest.save(update_fields=['registration_start', 'registration_end'])

        profiles = []
        for prefix in prefixes:
            profiles.extend(Profile.objects.filter(user__username__startswith=prefix).select_related('user'))

        if private and profiles:
            contest.private_contestants.add(*profiles)
            contest.is_private = True
            contest.save(update_fields=['is_private'])

        added, skipped = [], []
        for profile in profiles:
            try:
                participation = ContestParticipation.objects.create(
                    contest=contest,
                    user=profile,
                    virtual=ContestParticipation.LIVE,
                    real_start=contest.start_time,
                )
                added.append(profile.user.username)
                profile.current_contest = participation
                profile.save()
            except Exception:
                skipped.append(profile.user.username)

        contest._updating_stats_only = True
        contest.update_user_count()

        return self.render_to_response(self.get_context_data(
            form=form,
            results={
                'contest_name': contest.name,
                'contest_key': contest.key,
                'added': added,
                'skipped': skipped,
                'total': len(profiles),
            },
        ))


class AddProblemToContestView(TitleMixin, FormView):
    template_name = 'contest_helper/problem.html'
    form_class = AddProblemToContestForm
    title = _('Add problems to contest')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse('contest_helper_problem')

    def form_valid(self, form):
        contest_key = form.cleaned_data['contest_key']
        problem_prefix = form.cleaned_data['problem_prefix'].strip()
        points = form.cleaned_data['points']

        try:
            contest = Contest.objects.get(key=contest_key)
        except Contest.DoesNotExist:
            form.add_error('contest_key', _('Contest with key "%s" does not exist.') % contest_key)
            return self.form_invalid(form)

        problems = list(Problem.objects.filter(code__startswith=problem_prefix).order_by('code'))

        ContestProblem.objects.filter(contest=contest).delete()
        added, skipped = [], []
        for idx, problem in enumerate(problems, start=1):
            try:
                ContestProblem.objects.create(
                    contest=contest,
                    problem=problem,
                    points=points,
                    order=idx,
                )
                added.append(problem.code)
            except Exception:
                skipped.append(problem.code)

        return self.render_to_response(self.get_context_data(
            form=form,
            results={
                'contest_name': contest.name,
                'contest_key': contest.key,
                'added': added,
                'skipped': skipped,
                'total': len(problems),
            },
        ))
