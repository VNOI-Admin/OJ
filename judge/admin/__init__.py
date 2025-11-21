from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.contrib.flatpages.models import FlatPage
from django.urls import reverse
from django.utils.html import format_html
from reversion.admin import VersionAdmin

from judge.admin.comments import CommentAdmin
from judge.admin.contest import ContestAdmin, ContestParticipationAdmin, ContestTagAdmin
from judge.admin.interface import BlogPostAdmin, BlogPostTagAdmin, FlatPageAdmin, LicenseAdmin, LogEntryAdmin, \
    NavigationBarAdmin
from judge.admin.organization import OrganizationAdmin, OrganizationRequestAdmin
from judge.admin.problem import ProblemAdmin
from judge.admin.profile import ProfileAdmin, UserAdmin
from judge.admin.runtime import JudgeAdmin, LanguageAdmin
from judge.admin.submission import SubmissionAdmin
from judge.admin.tag import TagAdmin, TagGroupAdmin, TagProblemAdmin
from judge.admin.taxon import ProblemGroupAdmin, ProblemTypeAdmin
from judge.admin.ticket import TicketAdmin
from judge.models import Badge, BlogPost, BlogPostTag, Comment, CommentLock, Contest, ContestParticipation, \
    ContestTag, Judge, Language, License, MiscConfig, NavigationBar, Organization, \
    OrganizationRequest, Problem, ProblemGroup, ProblemType, Profile, Submission, Tag, \
    TagGroup, TagProblem, Ticket, URLShortener

admin.site.register(BlogPost, BlogPostAdmin)
admin.site.register(BlogPostTag, BlogPostTagAdmin)
admin.site.register(Comment, CommentAdmin)
admin.site.register(CommentLock)
admin.site.register(Contest, ContestAdmin)
admin.site.register(ContestParticipation, ContestParticipationAdmin)
admin.site.register(ContestTag, ContestTagAdmin)
admin.site.unregister(FlatPage)
admin.site.register(FlatPage, FlatPageAdmin)
admin.site.register(Judge, JudgeAdmin)
admin.site.register(Language, LanguageAdmin)
admin.site.register(License, LicenseAdmin)
admin.site.register(LogEntry, LogEntryAdmin)
admin.site.register(MiscConfig)
admin.site.register(Badge)
admin.site.register(NavigationBar, NavigationBarAdmin)
admin.site.register(Organization, OrganizationAdmin)
admin.site.register(OrganizationRequest, OrganizationRequestAdmin)
admin.site.register(Problem, ProblemAdmin)
admin.site.register(ProblemGroup, ProblemGroupAdmin)
admin.site.register(ProblemType, ProblemTypeAdmin)
admin.site.register(Profile, ProfileAdmin)
admin.site.register(Submission, SubmissionAdmin)
admin.site.register(Ticket, TicketAdmin)
admin.site.register(Tag, TagAdmin)
admin.site.register(TagGroup, TagGroupAdmin)
admin.site.register(TagProblem, TagProblemAdmin)
admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(URLShortener)
class URLShortenerAdmin(VersionAdmin):
    list_display = ('short_code', 'long_url_truncated', 'creator_link', 'click_count', 'created_at', 'is_active')
    list_filter = ('is_active', 'created_at')
    search_fields = ('short_code', 'long_url', 'creator__user__username', 'description')
    readonly_fields = ('click_count', 'created_at', 'updated_at', 'last_accessed')
    ordering = ('-created_at',)

    fieldsets = (
        ('Thông tin URL', {
            'fields': ('short_code', 'long_url', 'description'),
        }),
        ('Quyền sở hữu', {
            'fields': ('creator', 'organization'),
        }),
        ('Thống kê', {
            'fields': ('click_count', 'last_accessed', 'is_active'),
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def long_url_truncated(self, obj):
        return f'{obj.long_url[:60]}...' if len(obj.long_url) > 60 else obj.long_url
    long_url_truncated.short_description = 'URL đích'

    def creator_link(self, obj):
        return format_html(
            '<a href="{}">{}</a>',
            reverse('admin:judge_profile_change', args=[obj.creator.id]),
            obj.creator.user.username,
        )
    creator_link.short_description = 'Người tạo'
    creator_link.admin_order_field = 'creator__user__username'
