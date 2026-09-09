from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0234_problem_archived_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='problem',
            name='storage',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Storage backend identifier from config. Leave blank to use the default.',
                max_length=100,
                verbose_name='storage backend',
            ),
        ),
    ]
