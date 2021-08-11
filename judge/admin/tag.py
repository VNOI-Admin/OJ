from django import forms
from django.contrib import admin
from django.forms import ModelForm
from django.utils.translation import gettext_lazy as _
from reversion.admin import VersionAdmin

from judge.models import Tag, TagGroup, TagProblem
from judge.utils.views import NoBatchDeleteMixin
from judge.widgets import AdminHeavySelect2Widget


class TagForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(TagForm, self).__init__(*args, **kwargs)
        self.fields['group'].widget.can_add_related = False

    class Meta:
        widgets = {
            'group': AdminHeavySelect2Widget(data_view='taggroup_select2', attrs={'style': 'width: 100%'}),
        }


class TagGroupForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(TagGroupForm, self).__init__(*args, **kwargs)


class TagProblemForm(ModelForm):
    change_message = forms.CharField(max_length=256, label='Edit reason', required=False)


class TagDataInlineForm(ModelForm):
    class Meta:
        widgets = {
            'assigner': AdminHeavySelect2Widget(data_view='profile_select2', attrs={'style': 'width: 100%;'}),
            'tag': AdminHeavySelect2Widget(data_view='tag_select2', attrs={'style': 'width: 100%;'}),
        }


class TagAdmin(NoBatchDeleteMixin, VersionAdmin):
    fieldsets = (
        (None, {
            'fields': (
                'code', 'name', 'group',
            ),
        }),
    )
    list_display = ['code', 'name', 'group']
    ordering = ['code']
    search_fields = ('code', 'name', 'group__code', 'group__name')
    list_max_show_all = 1000
    actions_on_top = True
    action_on_bottom = True
    form = TagForm

    def get_queryset(self, request):
        return Tag.objects.all().distinct()


class TagGroupAdmin(NoBatchDeleteMixin, VersionAdmin):
    fieldsets = (
        (None, {
            'fields': (
                'code', 'name',
            ),
        }),
    )
    list_display = ['code', 'name']
    ordering = ['code']
    search_fields = ('code', 'name')
    list_max_show_all = 1000
    actions_on_top = True
    actions_on_bottom = True
    form = TagGroupForm

    def get_queryset(self, request):
        return TagGroup.objects.all().distinct()


class TagDataInline(admin.TabularInline):
    model = TagProblem.tag.through
    verbose_name = _('Tag Data')
    verbose_name_plural = _('Tag Data')
    form = TagDataInlineForm


class TagProblemAdmin(NoBatchDeleteMixin, VersionAdmin):
    fieldsets = (
        (None, {
            'fields': (
                'code', 'name', 'link', 'judge',
            ),
        }),
    )
    inlines = [
        TagDataInline,
    ]
    list_display = ['code', 'name']
    ordering = ['code']
    search_fields = ('code', 'name')
    list_max_show_all = 1000
    actions_on_top = True
    actions_on_bottom = True
    form = TagProblemForm

    def get_queryset(self, request):
        return TagProblem.objects.all().distinct()

    def construct_change_message(self, request, form, *args, **kwargs):
        if form.cleaned_data.get('change_message'):
            return form.cleaned_data['change_message']
        return super(TagProblemAdmin, self).construct_change_message(request, form, *args, **kwargs)
