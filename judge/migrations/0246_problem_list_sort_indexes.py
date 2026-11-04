from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0245_problem_points_range'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='problem',
            index=models.Index(fields=['is_public', 'is_organization_private', 'deleted_at', 'points'], name='judge_probl_is_publ_735a10_idx'),
        ),
        migrations.AddIndex(
            model_name='problem',
            index=models.Index(fields=['is_public', 'is_organization_private', 'deleted_at', 'user_count'], name='judge_probl_is_publ_7ded85_idx'),
        ),
    ]
