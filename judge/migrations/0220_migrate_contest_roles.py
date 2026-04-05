"""Single migration: create ContestRole, copy contest authors/curators/testers data, remove old M2M fields."""
import django.db.models.deletion
from django.db import migrations, models

ROLE_AUTHOR = 'A'
ROLE_CURATOR = 'C'
ROLE_TESTER = 'T'


def forwards(apps, schema_editor):
    Contest = apps.get_model('judge', 'Contest')
    ContestRole = apps.get_model('judge', 'ContestRole')

    contest_roles = []
    for contest in Contest.objects.prefetch_related('authors', 'curators', 'testers').iterator():
        for author in contest.authors.all():
            contest_roles.append(ContestRole(contest=contest, user=author, role=ROLE_AUTHOR))
        for curator in contest.curators.all():
            contest_roles.append(ContestRole(contest=contest, user=curator, role=ROLE_CURATOR))
        for tester in contest.testers.all():
            contest_roles.append(ContestRole(contest=contest, user=tester, role=ROLE_TESTER))
    ContestRole.objects.bulk_create(contest_roles, ignore_conflicts=True)


def backwards(apps, schema_editor):
    Contest = apps.get_model('judge', 'Contest')
    ContestRole = apps.get_model('judge', 'ContestRole')

    for contest in Contest.objects.all().iterator():
        roles = ContestRole.objects.filter(contest=contest)
        contest.authors.set(roles.filter(role=ROLE_AUTHOR).values_list('user', flat=True))
        contest.curators.set(roles.filter(role=ROLE_CURATOR).values_list('user', flat=True))
        contest.testers.set(roles.filter(role=ROLE_TESTER).values_list('user', flat=True))


class Migration(migrations.Migration):
    dependencies = [
        ('judge', '0219_problemdata_zipfile_size_alter_contest_authors_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContestRole',
            fields=[
                (
                    'id',
                    models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
                ),
                (
                    'role',
                    models.CharField(
                        choices=[('A', 'Author'), ('C', 'Curator'), ('T', 'Tester')],
                        max_length=1,
                        verbose_name='role',
                    ),
                ),
                (
                    'contest',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='contest_roles',
                        to='judge.contest',
                        verbose_name='contest',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='contest_roles',
                        to='judge.profile',
                        verbose_name='user',
                    ),
                ),
            ],
            options={
                'verbose_name': 'contest role',
                'verbose_name_plural': 'contest roles',
                'unique_together': {('contest', 'user', 'role')},
            },
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name='contest',
            name='authors',
        ),
        migrations.RemoveField(
            model_name='contest',
            name='curators',
        ),
        migrations.RemoveField(
            model_name='contest',
            name='testers',
        ),
    ]
