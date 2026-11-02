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
    ]
