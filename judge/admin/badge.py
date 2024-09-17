from django.contrib import admin
from django.utils.translation import gettext_lazy as _


class BadgeRequestAdmin(admin.ModelAdmin):
    list_display = ("username", "badge", "state", "time")
    readonly_fields = ("user", "cert", "desc")

    @admin.display(description=_("username"), ordering="user__user__username")
    def username(self, obj):
        return obj.user.user.username
