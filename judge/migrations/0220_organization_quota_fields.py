from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0219_problemdata_zipfile_size_alter_contest_authors_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='max_problems',
            field=models.IntegerField(
                blank=True,
                default=None,
                help_text='Maximum number of problems this org can create. Leave blank to use default from settings.',
                null=True,
                verbose_name='maximum problems',
            ),
        ),
        migrations.AddField(
            model_name='organization',
            name='max_storage',
            field=models.BigIntegerField(
                blank=True,
                default=None,
                help_text='Maximum storage for test data in bytes. Leave blank to use default from settings.',
                null=True,
                verbose_name='maximum storage (bytes)',
            ),
        ),
    ]
