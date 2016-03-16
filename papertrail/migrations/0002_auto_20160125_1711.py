# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('papertrail', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='entry',
            options={'ordering': ['-timestamp'], 'get_latest_by': 'timestamp', 'verbose_name_plural': 'entries'},
        ),
    ]
