import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0227_add_submission_heatmap_index'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255, verbose_name='title')),
                ('body', models.TextField(blank=True, verbose_name='body')),
                ('url', models.CharField(blank=True, max_length=255, verbose_name='target link')),
                ('time', models.DateTimeField(auto_now_add=True, verbose_name='creation time')),
                ('read', models.BooleanField(default=False, verbose_name='is read?')),
                ('priority', models.IntegerField(default=0, verbose_name='priority')),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='judge.profile', verbose_name='recipient')),
            ],
            options={
                'verbose_name': 'notification',
                'verbose_name_plural': 'notifications',
                'ordering': ['-time'],
                'indexes': [models.Index(fields=['recipient', 'read', '-priority', '-time'], name='judge_notif_recip_i_0f60e0_idx')],
            },
        ),
    ]
