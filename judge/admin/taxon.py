from django.contrib import admin


class ProblemGroupAdmin(admin.ModelAdmin):
    fields = ('name', 'full_name')


class ProblemTypeAdmin(admin.ModelAdmin):
    fields = ('name', 'full_name')


class OrganizationProblemTagAdmin(admin.ModelAdmin):
    fields = ('name', 'organization')
    list_display = ('name', 'organization')
    search_fields = ('name', 'organization__name')
