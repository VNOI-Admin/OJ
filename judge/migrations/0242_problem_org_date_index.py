from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0241_add_submission_contest_user_index'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='problem',
            index=models.Index(fields=['organization', 'date'], name='judge_probl_organiz_61d146_idx'),
        ),
    ]
