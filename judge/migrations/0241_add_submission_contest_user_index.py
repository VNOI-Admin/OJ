from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0240_add_submission_index'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='submission',
            index=models.Index(fields=['contest_object', 'user', '-id'], name='judge_submi_contest_fb7afc_idx'),
        ),
    ]
