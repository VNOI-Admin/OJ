from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from urlshortener.models import URLShortener


@admin.register(URLShortener)
class URLShortenerAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'suffix',
        'truncated_url',
        'created_user_link',
        'access_count',
        'is_active',
        'created_time',
    )
    list_display_links = ('id', 'suffix')
    list_filter = ('is_active', 'created_time')
    search_fields = ('suffix', 'original_url', 'created_user__user__username')
    readonly_fields = ('created_time', 'last_edited_time', 'last_access_time', 'access_count')
    ordering = ('-created_time',)
    date_hierarchy = 'created_time'

    fieldsets = (
        (None, {
            'fields': ('original_url', 'suffix'),
        }),
        (_('Ownership'), {
            'fields': ('created_user',),
        }),
        (_('Status'), {
            'fields': ('is_active',),
        }),
        (_('Statistics'), {
            'fields': ('access_count', 'last_access_time'),
            'classes': ('collapse',),
        }),
        (_('Timestamps'), {
            'fields': ('created_time', 'last_edited_time'),
            'classes': ('collapse',),
        }),
    )

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return request.user.has_perm('urlshortener.change_urlshortener')
        return obj.is_editable_by(request.user)

    def has_delete_permission(self, request, obj=None):
        if obj is None:
            return request.user.has_perm('urlshortener.delete_urlshortener')
        return obj.is_editable_by(request.user)

    @admin.display(description=_('Original URL'))
    def truncated_url(self, obj):
        url = obj.original_url
        if len(url) > 50:
            return format_html('<span title="{}">{}&hellip;</span>', url, url[:50])
        return url

    @admin.display(description=_('Created by'))
    def created_user_link(self, obj):
        user = obj.created_user.user
        return format_html(
            '<a href="/admin/auth/user/{}/change/">{}</a>',
            user.id,
            user.username,
        )
