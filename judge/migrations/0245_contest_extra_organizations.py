from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0244_remove_legacy_tag_project'),
    ]

    operations = [
        migrations.AddField(
            model_name='contest',
            name='extra_organizations',
            field=models.ManyToManyField(blank=True, help_text='If private, members of these organizations may also see the contest', related_name='+', to='judge.organization', verbose_name='extra organizations'),
        ),
    ]
