from django.contrib import admin
from django.forms import ModelForm
from django.urls import reverse_lazy
from django.utils.html import format_html
from django.utils.translation import gettext, gettext_lazy as _, ngettext
from reversion.admin import VersionAdmin

from judge.models import Organization
from judge.widgets import AdminHeavySelect2MultipleWidget, AdminMartorWidget


class OrganizationForm(ModelForm):
    class Meta:
        widgets = {
            'admins': AdminHeavySelect2MultipleWidget(data_view='profile_select2'),
            'about': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('organization_preview')}),
        }


class OrganizationAdmin(VersionAdmin):
    readonly_fields = ('creation_date', 'current_consumed_credit')
    fields = ('name', 'slug', 'short_name', 'is_open', 'is_unlisted', 'available_credit', 'current_consumed_credit',
              'about', 'logo_override_image', 'slots', 'creation_date', 'admins')
    list_display = ('name', 'short_name', 'is_open', 'is_unlisted', 'slots', 'show_public')
    prepopulated_fields = {'slug': ('name',)}
    actions = ('recalculate_points',)
    actions_on_top = True
    actions_on_bottom = True
    form = OrganizationForm

    @admin.display(description='')
    def show_public(self, obj):
        return format_html('<a href="{0}" style="white-space:nowrap;">{1}</a>',
                           obj.get_absolute_url(), gettext('View on site'))

    def get_readonly_fields(self, request, obj=None):
        fields = self.readonly_fields
        if not request.user.has_perm('judge.organization_admin'):
            return fields + ('admins', 'is_open', 'slots')
        return fields

    def get_queryset(self, request):
        queryset = Organization.objects.all()
        if request.user.has_perm('judge.edit_all_organization'):
            return queryset
        else:
            return queryset.filter(admins=request.profile.id)

    def has_change_permission(self, request, obj=None):
        if not request.user.has_perm('judge.change_organization'):
            return False
        if request.user.has_perm('judge.edit_all_organization') or obj is None:
            return True
        return obj.is_admin(request.profile)

    @admin.display(description=_('Recalculate scores'))
    def recalculate_points(self, request, queryset):
        count = 0
        for org in queryset:
            org.calculate_points()
            count += 1
        self.message_user(request, ngettext('%d organization has scores recalculated.',
                                            '%d organizations have scores recalculated.',
                                            count) % count)


class OrganizationRequestAdmin(admin.ModelAdmin):
    list_display = ('username', 'organization', 'state', 'time')
    readonly_fields = ('user', 'organization')

    @admin.display(description=_('username'), ordering='user__user__username')
    def username(self, obj):
        return obj.user.user.username
