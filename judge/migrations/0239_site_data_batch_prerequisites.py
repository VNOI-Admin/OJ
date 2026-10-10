from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0238_contest_balloons_permission'),
    ]

    operations = [
        migrations.AddField(
            model_name='problemtestcase',
            name='batch_dependencies',
            field=models.TextField(blank=True, help_text='batch dependencies as a comma-separated list of integers', verbose_name='batch dependencies'),
        ),
    ]
