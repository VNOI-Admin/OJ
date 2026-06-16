import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0225_add_pac_result'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.CharField(choices=[('ticket', 'Ticket'), ('contest', 'Contest'), ('storage', 'Storage')], max_length=50, verbose_name='category')),
                ('title', models.CharField(max_length=255, verbose_name='title')),
                ('html', models.TextField(blank=True, verbose_name='body')),
                ('url', models.CharField(blank=True, max_length=255, verbose_name='target link')),
                ('time', models.DateTimeField(auto_now_add=True, verbose_name='creation time')),
                ('read', models.BooleanField(default=False, verbose_name='is read?')),
                ('popup', models.BooleanField(default=False, verbose_name='pop up on arrival?')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='judge.profile', verbose_name='owner')),
            ],
            options={
                'verbose_name': 'notification',
                'verbose_name_plural': 'notifications',
                'ordering': ['-time'],
                'indexes': [models.Index(fields=['owner', 'read', '-time'], name='judge_notif_owner_i_0f60e0_idx')],
            },
        ),
    ]
