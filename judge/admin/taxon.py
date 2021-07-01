from django.contrib import admin


class ProblemGroupAdmin(admin.ModelAdmin):
    fields = ('name', 'full_name')


class ProblemTypeAdmin(admin.ModelAdmin):
    fields = ('name', 'full_name')
