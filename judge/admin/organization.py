from django.contrib import admin
from django.forms import DecimalField, ModelForm
from django.urls import reverse_lazy
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, gettext_lazy as _, ngettext
from reversion.admin import VersionAdmin

from judge.models import Organization, OrganizationQuota, OrganizationRegistrationForm
from judge.utils.organization import approve_organization_registration, reject_organization_registration
from judge.widgets import AdminHeavySelect2MultipleWidget, AdminMartorWidget

_GB = 1024 ** 3


class OrganizationForm(ModelForm):
    class Meta:
        widgets = {
            'admins': AdminHeavySelect2MultipleWidget(data_view='profile_select2'),
            'about': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('organization_preview')}),
            'notice': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('organization_preview')}),
        }


class OrganizationQuotaForm(ModelForm):
    added_storage_gb = DecimalField(
        min_value=0,
        required=False,
        label=_('Additional storage (GB)'),
        help_text=_('Decimal values allowed, e.g. 1.5. Leave blank for no additional storage.'),
    )

    class Meta:
        model = OrganizationQuota
        fields = ('start_date', 'end_date', 'added_problems', 'added_storage_gb')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial['added_storage_gb'] = round(self.instance.added_storage / _GB, 10)

    def clean(self):
        cleaned_data = super().clean()
        gb = cleaned_data.get('added_storage_gb') or 0
        cleaned_data['added_storage'] = round(float(gb) * _GB)
        return cleaned_data

    def save(self, commit=True):
        self.instance.added_storage = self.cleaned_data['added_storage']
        return super().save(commit=commit)


class OrganizationQuotaInline(admin.TabularInline):
    model = OrganizationQuota
    form = OrganizationQuotaForm
    fields = ('start_date', 'end_date', 'added_problems', 'added_storage_gb')
    extra = 0
    verbose_name = _('Quota Grant')
    verbose_name_plural = _('Quota Grants')


class OrganizationAdmin(VersionAdmin):
    readonly_fields = ('creation_date', 'current_consumed_credit')
    fields = ('name', 'slug', 'short_name', 'is_open', 'is_unlisted', 'paid_credit', 'current_consumed_credit',
              'about', 'notice', 'logo_override_image', 'slots', 'creation_date', 'admins')
    list_display = ('name', 'short_name', 'is_open', 'is_unlisted', 'slots', 'show_public')
    prepopulated_fields = {'slug': ('name',)}
    actions = ('recalculate_points',)
    actions_on_top = True
    actions_on_bottom = True
    form = OrganizationForm
    inlines = (OrganizationQuotaInline,)

    @admin.display(description='')
    def show_public(self, obj):
        return format_html('<a href="{0}" style="white-space:nowrap;">{1}</a>',
                           obj.get_absolute_url(), gettext('View on site'))

    def get_readonly_fields(self, request, obj=None):
        fields = self.readonly_fields
        if not request.user.has_perm('judge.organization_admin'):
            return fields + ('admins', 'is_open', 'slots', 'notice')
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
    readonly_fields = ('user', 'organization', 'state')

    @admin.display(description=_('username'), ordering='user__user__username')
    def username(self, obj):
        return obj.user.user.username


class OrganizationRegistrationReviewForm(ModelForm):
    class Meta:
        model = OrganizationRegistrationForm
        fields = ('state', 'review_note')

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('state') == OrganizationRegistrationForm.State.REJECTED and \
                not cleaned_data.get('review_note', '').strip():
            self.add_error('review_note', _('Tell the applicant why their form was rejected.'))
        return cleaned_data


class OrganizationRegistrationFormAdmin(admin.ModelAdmin):
    list_display = ('username', 'requested_organization', 'state', 'time', 'proof_count')
    list_filter = ('state',)
    search_fields = ('user__user__username', 'name', 'slug', 'applicant_name', 'facebook', 'email', 'phone')
    form = OrganizationRegistrationReviewForm
    readonly_fields = ('user', 'organization', 'name', 'slug', 'short_name', 'about', 'applicant_name',
                       'facebook', 'email', 'phone', 'reason', 'proof', 'time', 'reviewer', 'review_time')
    fields = ('user', 'organization', 'state', 'name', 'slug', 'short_name', 'about', 'applicant_name', 'facebook',
              'email', 'phone', 'reason', 'proof', 'time', 'reviewer', 'review_time', 'review_note')
    actions = ('approve_registrations', 'reject_registrations')

    def get_readonly_fields(self, request, obj=None):
        # A reviewed form keeps its state: flipping it later would leave the organization it created behind.
        if obj is not None and obj.state != OrganizationRegistrationForm.State.PENDING:
            return self.readonly_fields + ('state', 'review_note')
        return self.readonly_fields

    def save_model(self, request, obj, form, change):
        reviewed = OrganizationRegistrationForm.objects.filter(
            pk=obj.pk, state=OrganizationRegistrationForm.State.PENDING,
        ).first() if change else None

        if reviewed is None or obj.state == OrganizationRegistrationForm.State.PENDING:
            super().save_model(request, obj, form, change)
            return

        # Let the shared helpers own the transition: they create the organization and notify the applicant.
        reviewed.review_note = obj.review_note
        if obj.state == OrganizationRegistrationForm.State.APPROVED:
            approve_organization_registration(reviewed, request.profile)
        else:
            reject_organization_registration(reviewed, request.profile, obj.review_note)

    @admin.display(description=_('username'), ordering='user__user__username')
    def username(self, obj):
        return obj.user.user.username

    @admin.display(description=_('organization'))
    def requested_organization(self, obj):
        if obj.is_new_organization:
            return obj.name
        return format_html('<a href="{0}">{1}</a>', obj.organization.get_absolute_url(), obj.organization.name)

    @admin.display(description=_('proof'))
    def proof_count(self, obj):
        return len(obj.proof_files)

    @admin.display(description=_('proof'))
    def proof(self, obj):
        return format_html_join(mark_safe('<br>'), '<a href="{0}">{0}</a>', ((url,) for url in obj.proof_files))

    @admin.display(description=_('Approve selected registration forms'))
    def approve_registrations(self, request, queryset):
        count = 0
        for registration in queryset:
            if registration.state == registration.State.PENDING:
                approve_organization_registration(registration, request.profile)
                count += 1
        self.message_user(request, ngettext('%d registration form was approved.',
                                            '%d registration forms were approved.',
                                            count) % count)

    @admin.display(description=_('Reject selected registration forms'))
    def reject_registrations(self, request, queryset):
        count = 0
        for registration in queryset:
            if registration.state == registration.State.PENDING:
                reject_organization_registration(registration, request.profile, registration.review_note)
                count += 1
        self.message_user(request, ngettext('%d registration form was rejected.',
                                            '%d registration forms were rejected.',
                                            count) % count)
