from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0245_problem_list_optimization'),
    ]

    operations = [
        migrations.AddField(
            model_name='language',
            name='is_disabled',
            field=models.BooleanField(default=False, help_text='If true, users cannot submit in this language and it is hidden from the supported language lists.', verbose_name='disabled'),
        ),
    ]
