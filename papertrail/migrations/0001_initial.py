# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import papertrail.fields


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Entry',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('timestamp', models.DateTimeField(db_index=True)),
                ('type', models.CharField(max_length=50, db_index=True)),
                ('message', models.CharField(max_length=512)),
                ('data', papertrail.fields.JSONField(null=True)),
                ('external_key', models.CharField(max_length=255, null=True, db_index=True)),
            ],
            options={
                'ordering': ['-timestamp'],
                'get_latest_by': 'timestamp',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='EntryRelatedObject',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('relation_name', models.CharField(max_length=100, db_index=True)),
                ('related_id', models.PositiveIntegerField(db_index=True)),
                ('entry', models.ForeignKey(related_name='targets', to='papertrail.Entry')),
                ('related_content_type', models.ForeignKey(to='contenttypes.ContentType')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
    ]
