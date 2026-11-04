from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0246_problem_list_sort_indexes'),
    ]

    operations = [
        # Add before removing, so the problem list always has a usable index.
        migrations.AddIndex(
            model_name='problem',
            index=models.Index(fields=['is_public', 'is_organization_private', 'date'], name='judge_probl_is_publ_f72cb6_idx'),
        ),
        migrations.RemoveIndex(
            model_name='problem',
            name='judge_probl_is_publ_b00d80_idx',
        ),
        migrations.AddIndex(
            model_name='problem',
            index=models.Index(fields=['organization', 'is_public', 'deleted_at', 'date'], name='judge_probl_organiz_f1caf4_idx'),
        ),
    ]
