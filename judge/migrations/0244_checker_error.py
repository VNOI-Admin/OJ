from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0243_contest_tag_name_unicode'),
    ]

    operations = [
        migrations.AlterField(
            model_name='submission',
            name='result',
            field=models.CharField(blank=True, choices=[('AC', 'Accepted'), ('PAC', 'Partially Accepted'), ('WA', 'Wrong Answer'), ('TLE', 'Time Limit Exceeded'), ('MLE', 'Memory Limit Exceeded'), ('OLE', 'Output Limit Exceeded'), ('IR', 'Invalid Return'), ('RTE', 'Runtime Error'), ('CE', 'Compile Error'), ('IE', 'Internal Error'), ('CKE', 'Checker Error'), ('SC', 'Short Circuited'), ('AB', 'Aborted')], default=None, max_length=3, null=True, verbose_name='result'),
        ),
        migrations.AlterField(
            model_name='submission',
            name='status',
            field=models.CharField(choices=[('QU', 'Queued'), ('P', 'Processing'), ('G', 'Grading'), ('D', 'Completed'), ('IE', 'Internal Error'), ('CKE', 'Checker Error'), ('CE', 'Compile Error'), ('AB', 'Aborted')], db_index=True, default='QU', max_length=3, verbose_name='status'),
        ),
        migrations.AlterField(
            model_name='submissiontestcase',
            name='status',
            field=models.CharField(choices=[('AC', 'Accepted'), ('PAC', 'Partially Accepted'), ('WA', 'Wrong Answer'), ('TLE', 'Time Limit Exceeded'), ('MLE', 'Memory Limit Exceeded'), ('OLE', 'Output Limit Exceeded'), ('IR', 'Invalid Return'), ('RTE', 'Runtime Error'), ('CE', 'Compile Error'), ('IE', 'Internal Error'), ('CKE', 'Checker Error'), ('SC', 'Short Circuited'), ('AB', 'Aborted')], max_length=3, verbose_name='status flag'),
        ),
    ]
