# Generated migration for storage_expiration field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0220_organization_quota_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='storage_expiration',
            field=models.DateField(
                blank=True, default=None,
                help_text='Expiry date of the paid storage plan. Leave blank for no expiration.',
                null=True, verbose_name='storage expiration date',
            ),
        ),
    ]
