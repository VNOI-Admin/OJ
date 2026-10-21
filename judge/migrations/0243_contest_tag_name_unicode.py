from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0242_problem_org_date_index'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contesttag',
            name='name',
            field=models.CharField(max_length=50, unique=True, verbose_name='tag name'),
        ),
    ]
