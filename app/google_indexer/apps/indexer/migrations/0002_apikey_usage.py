# Generated by Django 5.1.1 on 2024-10-06 12:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('indexer', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='apikey',
            name='usage',
            field=models.CharField(choices=[('APIKEY_USAGE_INDEXATION', '⚡Indexing'), ('APIKEY_USAGE_VERIFICATION', '✅Checking')], default='APIKEY_USAGE_INDEXATION', max_length=255),
        ),
    ]
