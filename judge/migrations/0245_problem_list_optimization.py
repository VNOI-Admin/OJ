import django.core.validators
from django.db import migrations, models


def clamp_problem_points(apps, schema_editor):
    Problem = apps.get_model('judge', 'Problem')
    Problem.objects.filter(points__lt=0.01).update(points=0.01)
    Problem.objects.filter(points__gt=2).update(points=2)


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0244_remove_legacy_tag_project'),
    ]

    operations = [
        migrations.RunPython(clamp_problem_points, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='problem',
            name='points',
            field=models.FloatField(help_text="Points awarded for problem completion. Points are displayed with a 'p' suffix if partial.", validators=[django.core.validators.MinValueValidator(0.01), django.core.validators.MaxValueValidator(2)], verbose_name='points'),
        ),
        migrations.AddIndex(
            model_name='problem',
            index=models.Index(fields=['is_public', 'is_organization_private', 'deleted_at', 'points'], name='judge_probl_is_publ_735a10_idx'),
        ),
        migrations.AddIndex(
            model_name='problem',
            index=models.Index(fields=['is_public', 'is_organization_private', 'deleted_at', 'user_count'], name='judge_probl_is_publ_7ded85_idx'),
        ),
        # Add before removing, so the problem list always has a usable index.
        migrations.AddIndex(
            model_name='problem',
            index=models.Index(fields=['is_public', 'is_organization_private', 'date'], name='judge_probl_is_publ_f72cb6_idx'),
        ),
        migrations.RemoveIndex(
            model_name='problem',
            name='judge_probl_is_publ_b00d80_idx',
        ),
        migrations.AddIndex(
            model_name='problem',
            index=models.Index(fields=['organization', 'is_public', 'deleted_at', 'date'], name='judge_probl_organiz_f1caf4_idx'),
        ),
    ]
