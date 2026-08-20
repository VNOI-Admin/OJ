from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0232_organization_problem_tag'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='notice',
            field=models.TextField(blank=True, default='', verbose_name='organization notice',
                                   help_text='Warning banner shown at the top of every page of this '
                                             'organization. Leave blank to hide it.'),
        ),
    ]
