from django.core.validators import RegexValidator
from django.db import models
from django.db.models import CASCADE
from django.utils.translation import gettext_lazy as _


class TagGroup(models.Model):
    code = models.CharField(max_length=30, verbose_name=_('Tag group ID'), unique=True)
    name = models.CharField(max_length=100, verbose_name=_('Tag group name'))

    def __str__(self):
        return self.name


class Tag(models.Model):
    code = models.CharField(max_length=30, verbose_name=_('Tag group ID'), unique=True)
    name = models.CharField(max_length=100, verbose_name=_('Tag group name'))
    group = models.OneToOneField(TagGroup, verbose_name=_('Parent tag group'), on_delete=CASCADE)

    def __str__(self):
        return self.name


class TagProblem(models.Model):
    code = models.CharField(max_length=32, verbose_name=_('problem code'), unique=True,
                            validators=[RegexValidator('^[a-zA-Z0-9_]+$', _('Problem code must be ^[a-zA-Z0-9_]+$'))])
    name = models.CharField(max_length=100, verbose_name=_('problem name'))
    link = models.URLField(max_length=200, verbose_name=_('Problem URL'))

    tag = models.ManyToManyField(Tag, verbose_name=_('Tag'))

    def get_absolute_url(self):
        return self.link
