from operator import attrgetter

from django import forms
from django.contrib import admin
from django.db import transaction
from django.forms import ModelForm
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext, gettext_lazy as _, ngettext
from reversion.admin import VersionAdmin

from judge.models import LanguageLimit, Problem, ProblemClarification, ProblemTranslation, Profile, Solution
from judge.utils.views import NoBatchDeleteMixin
from judge.widgets import AdminHeavySelect2MultipleWidget, AdminHeavySelect2Widget, AdminMartorWidget, \
    AdminSelect2MultipleWidget, AdminSelect2Widget, CheckboxSelectMultipleWithSelectAll


class ProblemForm(ModelForm):
    change_message = forms.CharField(max_length=256, label='Edit reason', required=False)

    def __init__(self, *args, **kwargs):
        super(ProblemForm, self).__init__(*args, **kwargs)
        self.fields['authors'].widget.can_add_related = False
        self.fields['curators'].widget.can_add_related = False
        self.fields['suggester'].widget.can_add_related = False
        self.fields['testers'].widget.can_add_related = False
        self.fields['banned_users'].widget.can_add_related = False
        self.fields['change_message'].widget.attrs.update({
            'placeholder': gettext('Describe the changes you made (optional)'),
        })

    class Meta:
        widgets = {
            'authors': AdminHeavySelect2MultipleWidget(data_view='profile_select2'),
            'curators': AdminHeavySelect2MultipleWidget(data_view='profile_select2'),
            'suggester': AdminHeavySelect2Widget(data_view='profile_select2'),
            'testers': AdminHeavySelect2MultipleWidget(data_view='profile_select2'),
            'banned_users': AdminHeavySelect2MultipleWidget(data_view='profile_select2'),
            'organizations': AdminHeavySelect2MultipleWidget(data_view='organization_select2'),
            'types': AdminSelect2MultipleWidget,
            'group': AdminSelect2Widget,
            'description': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('problem_preview')}),
        }


class ProblemCreatorListFilter(admin.SimpleListFilter):
    title = parameter_name = 'creator'

    def lookups(self, request, model_admin):
        queryset = Profile.objects.exclude(authored_problems=None).values_list('user__username', flat=True)
        return [(name, name) for name in queryset]

    def queryset(self, request, queryset):
        if self.value() is None:
            return queryset
        return queryset.filter(authors__user__username=self.value())


class LanguageLimitInlineForm(ModelForm):
    class Meta:
        widgets = {'language': AdminSelect2Widget}


class LanguageLimitInline(admin.TabularInline):
    model = LanguageLimit
    fields = ('language', 'time_limit', 'memory_limit')
    form = LanguageLimitInlineForm


class ProblemClarificationForm(ModelForm):
    class Meta:
        widgets = {'description': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('comment_preview')})}


class ProblemClarificationInline(admin.StackedInline):
    model = ProblemClarification
    fields = ('description',)
    form = ProblemClarificationForm
    extra = 0


class ProblemSolutionForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(ProblemSolutionForm, self).__init__(*args, **kwargs)
        self.fields['authors'].widget.can_add_related = False

    class Meta:
        widgets = {
            'authors': AdminHeavySelect2MultipleWidget(data_view='profile_select2'),
            'content': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('solution_preview')}),
        }


class ProblemSolutionInline(admin.StackedInline):
    model = Solution
    fields = ('is_public', 'publish_on', 'authors', 'content')
    form = ProblemSolutionForm
    extra = 0


class ProblemTranslationForm(ModelForm):
    class Meta:
        widgets = {'description': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('problem_preview')})}


class ProblemTranslationInline(admin.StackedInline):
    model = ProblemTranslation
    fields = ('language', 'name', 'description')
    form = ProblemTranslationForm
    extra = 0

    def has_permission_full_markup(self, request, obj=None):
        if not obj:
            return True
        return request.user.has_perm('judge.problem_full_markup') or not obj.is_full_markup

    has_add_permission = has_change_permission = has_delete_permission = has_permission_full_markup


class ProblemAdmin(NoBatchDeleteMixin, VersionAdmin):
    fieldsets = (
        (None, {
            'fields': (
                'code', 'name', 'suggester', 'is_public', 'is_manually_managed', 'date', 'authors',
                'curators', 'testers', 'is_organization_private', 'organizations', 'submission_source_visibility_mode',
                'testcase_visibility_mode', 'testcase_result_visibility_mode', 'allow_view_feedback',
                'is_full_markup', 'pdf_url', 'source', 'description', 'license',
            ),
        }),
        (_('Social Media'), {'classes': ('collapse',), 'fields': ('og_image', 'summary')}),
        (_('Taxonomy'), {'fields': ('types', 'group')}),
        (_('Points'), {'fields': (('points', 'partial'), 'short_circuit')}),
        (_('Limits'), {'fields': ('time_limit', 'memory_limit')}),
        (_('Language'), {'fields': ('allowed_languages',)}),
        (_('Justice'), {'fields': ('banned_users',)}),
        (_('History'), {'fields': ('change_message',)}),
    )
    list_display = ['code', 'name', 'show_authors', 'points', 'is_public', 'show_public']
    ordering = ['code']
    search_fields = ('code', 'name', 'authors__user__username', 'curators__user__username')
    inlines = [LanguageLimitInline, ProblemClarificationInline, ProblemSolutionInline, ProblemTranslationInline]
    list_max_show_all = 1000
    actions_on_top = True
    actions_on_bottom = True
    list_filter = ('is_public', ProblemCreatorListFilter)
    form = ProblemForm
    date_hierarchy = 'date'

    def get_actions(self, request):
        actions = super(ProblemAdmin, self).get_actions(request)

        if request.user.has_perm('judge.change_public_visibility'):
            func, name, desc = self.get_action('make_public_and_update_publish_date')
            actions[name] = (func, name, desc)

            func, name, desc = self.get_action('make_private')
            actions[name] = (func, name, desc)

        return actions

    def get_readonly_fields(self, request, obj=None):
        fields = self.readonly_fields
        if not request.user.has_perm('judge.change_public_visibility'):
            fields += ('is_public',)
        if not request.user.has_perm('judge.change_manually_managed'):
            fields += ('is_manually_managed',)
        if not request.user.has_perm('judge.problem_full_markup'):
            fields += ('is_full_markup',)
            if obj and obj.is_full_markup:
                fields += ('description',)
        return fields

    @admin.display(description=_('authors'))
    def show_authors(self, obj):
        return ', '.join(map(attrgetter('user.username'), obj.authors.all()))

    @admin.display(description='')
    def show_public(self, obj):
        return format_html('<a href="{1}">{0}</a>', gettext('View on site'), obj.get_absolute_url())

    def _rescore(self, request, problem_id, publicy_changed=False):
        from judge.tasks import rescore_problem
        transaction.on_commit(rescore_problem.s(problem_id, publicy_changed).delay)

    @admin.display(description=_('Mark problems as public and set publish date to now'))
    def make_public_and_update_publish_date(self, request, queryset):
        count = queryset.update(is_public=True, date=timezone.now())
        for problem_id in queryset.values_list('id', flat=True):
            self._rescore(request, problem_id, True)

        self.message_user(request, ngettext('%d problem successfully marked as public.',
                                            '%d problems successfully marked as public.',
                                            count) % count)

    @admin.display(description=_('Mark problems as private'))
    def make_private(self, request, queryset):
        count = queryset.update(is_public=False)
        for problem_id in queryset.values_list('id', flat=True):
            self._rescore(request, problem_id, True)
        self.message_user(request, ngettext('%d problem successfully marked as private.',
                                            '%d problems successfully marked as private.',
                                            count) % count)

    def get_queryset(self, request):
        return Problem.get_editable_problems(request.user).prefetch_related('authors__user').distinct()

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return request.user.has_perm('judge.edit_own_problem')
        return obj.is_editable_by(request.user)

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        if db_field.name == 'allowed_languages':
            kwargs['widget'] = CheckboxSelectMultipleWithSelectAll()
        return super(ProblemAdmin, self).formfield_for_manytomany(db_field, request, **kwargs)

    def get_form(self, *args, **kwargs):
        form = super(ProblemAdmin, self).get_form(*args, **kwargs)
        form.base_fields['authors'].queryset = Profile.objects.all()
        return form

    def save_model(self, request, obj, form, change):
        super(ProblemAdmin, self).save_model(request, obj, form, change)
        if (
            form.changed_data and
            any(f in form.changed_data for f in ('is_public', 'is_organization_private', 'partial'))
        ):
            self._rescore(request, obj.id, 'is_public' in form.changed_data)

    def construct_change_message(self, request, form, *args, **kwargs):
        if form.cleaned_data.get('change_message'):
            return form.cleaned_data['change_message']
        return super(ProblemAdmin, self).construct_change_message(request, form, *args, **kwargs)
