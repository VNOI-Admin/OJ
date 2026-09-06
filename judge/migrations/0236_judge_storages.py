from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0235_problem_storage'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='judge',
            name='problems',
        ),
        migrations.AddField(
            model_name='judge',
            name='storages',
            field=models.JSONField(blank=True, default=list, verbose_name='storage backends'),
        ),
    ]
