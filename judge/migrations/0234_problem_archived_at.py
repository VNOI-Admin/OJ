from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0233_organization_notice'),
    ]

    operations = [
        migrations.AddField(
            model_name='problem',
            name='archived_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='archived at',
                                       help_text="When set, this problem's data has been moved to cold storage."),
        ),
        migrations.AddField(
            model_name='problemdata',
            name='archived_size',
            field=models.BigIntegerField(default=0, help_text='Size of the test data zip file in bytes when archived.', verbose_name='archived test data storage size'),
        ),
        migrations.AddIndex(
            model_name='problem',
            index=models.Index(fields=['organization', '-archived_at'], name='judge_probl_organiz_0d1c92_idx'),
        ),
    ]
