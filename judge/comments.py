from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import FilteredRelation, Q
from django.db.models.expressions import F, Value
from django.db.models.functions import Coalesce
from django.forms import ModelForm
from django.http import HttpResponseBadRequest, HttpResponseForbidden, HttpResponseNotFound, HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.generic import View
from django.views.generic.base import TemplateResponseMixin
from django.views.generic.detail import SingleObjectMixin
from reversion import revisions
from reversion.models import Revision, Version

from judge.dblock import LockModel
from judge.models import Comment, CommentLock
from judge.widgets import MartorWidget


class CommentForm(ModelForm):
    class Meta:
        model = Comment
        fields = ['body', 'parent']
        widgets = {
            'parent': forms.HiddenInput(),
        }

        widgets['body'] = MartorWidget(attrs={'data-markdownfy-url': reverse_lazy('comment_preview')})

    def __init__(self, request, *args, **kwargs):
        self.request = request
        super(CommentForm, self).__init__(*args, **kwargs)
        self.fields['body'].widget.attrs.update({'placeholder': _('Comment body')})

    def clean(self):
        cleaned_data = super(CommentForm, self).clean()
        if self.request is not None and self.request.user.is_authenticated:
            profile = self.request.profile
            body = cleaned_data.get('body')

            # Mute
            if profile.mute:
                suffix_msg = '' if profile.ban_reason is None else _(' Reason: ') + profile.ban_reason
                raise ValidationError(_('Your part is silent, little toad.') + suffix_msg)

            # Solved problems count
            elif profile.is_new_user:
                raise ValidationError(_('You need to have solved at least %d problems '
                                        'before your voice can be heard.') % settings.VNOJ_INTERACT_MIN_PROBLEM_COUNT)

            # Contribution points
            min_contrib = getattr(settings, 'VNOJ_COMMENT_MIN_CONTRIBUTION', 0)
            if profile.contribution_points < min_contrib:
                raise ValidationError(_('You need at least %d contribution points to comment.') % min_contrib)

            # Checks that require body content
            if body:
                # Comment length
                min_len = getattr(settings, 'VNOJ_COMMENT_MIN_LENGTH', 10)
                max_len = getattr(settings, 'VNOJ_COMMENT_MAX_LENGTH', 10000)
                if len(body) < min_len:
                    raise ValidationError(_('Comment is too short (min %d chars).') % min_len)
                if len(body) > max_len:
                    raise ValidationError(_('Comment is too long (max %d chars).') % max_len)

                # Blacklist
                blacklist = getattr(settings, 'VNOJ_COMMENT_BLACKLIST_TERMS', [])
                if blacklist:
                    body_lower = body.lower()
                    for term in blacklist:
                        if term.lower() in body_lower:
                            raise ValidationError(_('Your comment contains forbidden content.'))

            # Rate limit
            limit_count = getattr(settings, 'VNOJ_COMMENT_RATE_LIMIT_COUNT', 5)
            limit_time = getattr(settings, 'VNOJ_COMMENT_RATE_LIMIT_TIME', 600)  # seconds
            if limit_count > 0:
                time_threshold = timezone.now() - timedelta(seconds=limit_time)
                recent_comments = Comment.objects.filter(
                    author=profile,
                    time__gte=time_threshold,
                ).count()
                if recent_comments >= limit_count:
                    raise ValidationError(_('You are commenting too fast. Chill out.'))

        return cleaned_data


class CommentedDetailView(TemplateResponseMixin, SingleObjectMixin, View):
    comment_page = None

    def get_comment_page(self):
        if self.comment_page is None:
            raise NotImplementedError()
        return self.comment_page

    def is_comment_locked(self):
        return (CommentLock.objects.filter(page=self.get_comment_page()).exists() and
                not self.request.user.has_perm('judge.override_comment_lock'))

    def get_comment_form(self, request):
        return CommentForm(request, initial={'page': self.get_comment_page(), 'parent': None})

    @method_decorator(login_required)
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        page = self.get_comment_page()

        if self.is_comment_locked():
            return HttpResponseForbidden()

        parent = request.POST.get('parent')
        if parent:
            if len(parent) > 10:
                return HttpResponseBadRequest()
            try:
                parent = int(parent)
            except ValueError:
                return HttpResponseBadRequest()
            try:
                parent_comment = Comment.objects.get(hidden=False, id=parent, page=page)
            except Comment.DoesNotExist:
                return HttpResponseNotFound()
            if not (self.request.user.has_perm('judge.change_comment') or
                    parent_comment.time > timezone.now() - settings.DMOJ_COMMENT_REPLY_TIMEFRAME):
                return HttpResponseForbidden()

        form = CommentForm(request, request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.author = request.profile
            comment.page = page
            with LockModel(write=(Comment, Revision, Version), read=(ContentType,)), revisions.create_revision():
                revisions.set_user(request.user)
                revisions.set_comment(_('Posted comment'))
                comment.save()
            return HttpResponseRedirect(request.path)

        context = self.get_context_data(object=self.object, comment_form=form)
        return self.render_to_response(context)

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self.render_to_response(self.get_context_data(
            object=self.object,
            comment_form=self.get_comment_form(request),
        ))

    def get_context_data(self, **kwargs):
        context = super(CommentedDetailView, self).get_context_data(**kwargs)
        queryset = Comment.objects.filter(hidden=False, page=self.get_comment_page())
        context['has_comments'] = queryset.exists()
        context['comment_lock'] = self.is_comment_locked()
        queryset = queryset.select_related('author__user', 'author__display_badge').defer('author__about')

        if self.request.user.is_authenticated:
            profile = self.request.profile
            queryset = queryset.annotate(
                my_vote=FilteredRelation('votes', condition=Q(votes__voter_id=profile.id)),
            ).annotate(vote_score=Coalesce(F('my_vote__score'), Value(0)))
            context['is_new_user'] = profile.is_new_user
            context['interact_min_problem_count_msg'] = \
                _('You need to have solved at least %d problems before your voice can be heard.') \
                % settings.VNOJ_INTERACT_MIN_PROBLEM_COUNT
        context['comment_list'] = queryset
        context['vote_hide_threshold'] = settings.DMOJ_COMMENT_VOTE_HIDE_THRESHOLD
        context['reply_cutoff'] = timezone.now() - settings.DMOJ_COMMENT_REPLY_TIMEFRAME

        return context
