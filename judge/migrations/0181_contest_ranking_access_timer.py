# Generated by Django 2.2.28 on 2022-12-06 14:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0180_auto_20221206_1334'),
    ]

    operations = [
        migrations.AddField(
            model_name='contest',
            name='ranking_access_timer',
            field=models.IntegerField(default=0, help_text='Set the time (in minutes) before the contest ends to disable the contest ranking.', verbose_name='ranking access timer'),
        ),
    ]