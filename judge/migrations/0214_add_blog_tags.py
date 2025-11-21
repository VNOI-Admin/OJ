# Manual migration for blog tags
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0213_add_rate_disqualified'),
    ]

    operations = [
        migrations.CreateModel(
            name='BlogPostTag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=40, unique=True, verbose_name='name')),
                ('slug', models.SlugField(unique=True, verbose_name='slug')),
            ],
            options={
                'verbose_name': 'blog tag',
                'verbose_name_plural': 'blog tags',
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='blogpost',
            name='tags',
            field=models.ManyToManyField(blank=True, related_name='posts', to='judge.blogposttag', verbose_name='tags'),
        ),
    ]
