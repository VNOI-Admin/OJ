from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.contrib.flatpages.models import FlatPage
from django.utils.html import format_html
from django.db.models import Q

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
    ContestTag, FileUsage, Judge, Language, License, MiscConfig, NavigationBar, Organization, \
    OrganizationRequest, Problem, ProblemGroup, ProblemType, Profile, Submission, Tag, \
    TagGroup, TagProblem, Ticket, UserFile


class UserFileAdmin(admin.ModelAdmin):
    """Admin configuration for user files."""
    list_display = ('filename', 'user', 'file_type', 'is_public', 'uploaded_at')
    list_filter = ('file_type', 'is_public', 'uploaded_at')
    search_fields = ('filename', 'user__user__username')

    def get_readonly_fields(self, request, obj=None):
        """Return different readonly fields for add vs change."""
        self._request = request
        if obj is None:
            return ()
        return (
            'uuid',
            'filename',
            'size',
            'uploaded_at',
            'last_accessed',
            'access_count',
            'access_url',
            'download_link',
        )

    def get_fields(self, request, obj=None):
        """Show different fields for add vs change."""
        self._request = request
        if obj is None:
            return ('user', 'file', 'file_type', 'description', 'is_public')
        return ('uuid', 'user', 'filename', 'file_type', 'size', 'description', 'is_public',
                'uploaded_at', 'last_accessed', 'access_count', 'access_url', 'download_link')

    def access_url(self, obj):
        """Show shareable URL for public files only."""
        if not obj or not obj.pk or not obj.file:
            return '-'

        if not getattr(obj, 'is_public', False):
            return '-'

        access_path = obj.get_access_url()
        request = getattr(self, '_request', None)
        full_url = request.build_absolute_uri(access_path) if request else access_path

        return format_html(
            '<input type="text" value="{}" readonly onclick="this.select();" />'
            '<br><small>Click to select and copy URL</small>',
            full_url
        )

    access_url.short_description = 'Shareable URL (Public Only)'

    def download_link(self, obj):
        """Show download link."""
        if not obj or not obj.pk:
            return '-'

        return format_html(
            '<a href="{}" target="_blank">Download File</a>',
            obj.get_download_url()
        )

    download_link.short_description = 'Download'

    def get_queryset(self, request):
        """Filter queryset based on permissions - apply same rules as views."""
        queryset = super().get_queryset(request)

        if request.user.is_superuser:
            return queryset

        if not request.user.is_authenticated:
            return queryset.none()

        user_profile = request.user.profile
        queryset = queryset.filter(
            Q(is_public=True) | Q(user=user_profile)
        )
        return queryset


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
admin.site.register(UserFile, UserFileAdmin)
admin.site.register(FileUsage)
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
