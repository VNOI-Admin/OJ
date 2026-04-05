"""Single migration: create ProblemRole, copy problem authors/curators/testers data, remove old M2M fields."""
import django.db.models.deletion
from django.db import migrations, models

ROLE_AUTHOR = 'A'
ROLE_CURATOR = 'C'
ROLE_TESTER = 'T'


def forwards(apps, schema_editor):
    Problem = apps.get_model('judge', 'Problem')
    ProblemRole = apps.get_model('judge', 'ProblemRole')

    problem_roles = []
    for problem in Problem.objects.prefetch_related('authors', 'curators', 'testers').iterator():
        for author in problem.authors.all():
            problem_roles.append(ProblemRole(problem=problem, user=author, role=ROLE_AUTHOR))
        for curator in problem.curators.all():
            problem_roles.append(ProblemRole(problem=problem, user=curator, role=ROLE_CURATOR))
        for tester in problem.testers.all():
            problem_roles.append(ProblemRole(problem=problem, user=tester, role=ROLE_TESTER))
    ProblemRole.objects.bulk_create(problem_roles, ignore_conflicts=True)


def backwards(apps, schema_editor):
    Problem = apps.get_model('judge', 'Problem')
    ProblemRole = apps.get_model('judge', 'ProblemRole')

    for problem in Problem.objects.all().iterator():
        roles = ProblemRole.objects.filter(problem=problem)
        problem.authors.set(roles.filter(role=ROLE_AUTHOR).values_list('user', flat=True))
        problem.curators.set(roles.filter(role=ROLE_CURATOR).values_list('user', flat=True))
        problem.testers.set(roles.filter(role=ROLE_TESTER).values_list('user', flat=True))


class Migration(migrations.Migration):
    dependencies = [
        ('judge', '0220_migrate_contest_roles'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProblemRole',
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
                    'problem',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='problem_roles',
                        to='judge.problem',
                        verbose_name='problem',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='problem_roles',
                        to='judge.profile',
                        verbose_name='user',
                    ),
                ),
            ],
            options={
                'verbose_name': 'problem role',
                'verbose_name_plural': 'problem roles',
                'unique_together': {('problem', 'user', 'role')},
            },
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name='problem',
            name='authors',
        ),
        migrations.RemoveField(
            model_name='problem',
            name='curators',
        ),
        migrations.RemoveField(
            model_name='problem',
            name='testers',
        ),
    ]
