from django.db import models
from django.db.models import CASCADE, Exists, OuterRef
from django.utils.translation import gettext_lazy as _

from judge.models.profile import Profile

ROLE_AUTHOR = 'A'
ROLE_CURATOR = 'C'
ROLE_TESTER = 'T'

ROLE_CHOICES = (
    (ROLE_AUTHOR, _('Author')),
    (ROLE_CURATOR, _('Curator')),
    (ROLE_TESTER, _('Tester')),
)


class RoleQuerySetAdapter:
    def __init__(self, queryset):
        self.queryset = queryset

    def all(self):
        return self.queryset.all()

    def filter(self, *args, **kwargs):
        return self.queryset.filter(*args, **kwargs)

    def exists(self):
        return self.queryset.exists()

    def first(self):
        return self.queryset.first()

    def values_list(self, *args, **kwargs):
        return self.queryset.values_list(*args, **kwargs)

    def __iter__(self):
        return iter(self.queryset)

    def __contains__(self, item):
        return self.queryset.filter(pk=getattr(item, 'pk', item)).exists()


class ContestRole(models.Model):
    contest = models.ForeignKey(
        'Contest', verbose_name=_('contest'), related_name='contest_roles', on_delete=CASCADE,
    )
    user = models.ForeignKey(
        Profile, verbose_name=_('user'), related_name='contest_roles', on_delete=CASCADE,
    )
    role = models.CharField(max_length=1, choices=ROLE_CHOICES, verbose_name=_('role'))

    class Meta:
        unique_together = ('contest', 'user', 'role')
        verbose_name = _('contest role')
        verbose_name_plural = _('contest roles')

    def __str__(self):
        return f'{self.user} - {self.get_role_display()} of {self.contest}'

    @staticmethod
    def exists_for(user, role=None, roles=None):
        filters = {'contest_id': OuterRef('pk'), 'user': user}
        if role:
            filters['role'] = role
        qs = ContestRole.objects.filter(**filters)
        if roles:
            qs = qs.filter(role__in=roles)
        return Exists(qs)


class ProblemRole(models.Model):
    problem = models.ForeignKey(
        'Problem', verbose_name=_('problem'), related_name='problem_roles', on_delete=CASCADE,
    )
    user = models.ForeignKey(
        Profile, verbose_name=_('user'), related_name='problem_roles', on_delete=CASCADE,
    )
    role = models.CharField(max_length=1, choices=ROLE_CHOICES, verbose_name=_('role'))

    class Meta:
        unique_together = ('problem', 'user', 'role')
        verbose_name = _('problem role')
        verbose_name_plural = _('problem roles')

    def __str__(self):
        return f'{self.user} - {self.get_role_display()} of {self.problem}'

    @staticmethod
    def exists_for(user, role=None, roles=None):
        filters = {'problem_id': OuterRef('pk'), 'user': user}
        if role:
            filters['role'] = role
        qs = ProblemRole.objects.filter(**filters)
        if roles:
            qs = qs.filter(role__in=roles)
        return Exists(qs)
