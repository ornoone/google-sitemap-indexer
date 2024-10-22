# Generated by Django 5.1.1 on 2024-10-22 16:42

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('indexer', '0006_trackedsite_admin_url_alter_apikey_status_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='CallError',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('error', models.TextField(blank=True, default='', null=True)),
                ('date', models.DateTimeField(auto_now=True)),
                ('api_key', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='call_errors', to='indexer.apikey')),
                ('page', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='call_errors', to='indexer.trackedpage')),
                ('site', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='call_errors', to='indexer.trackedsite')),
            ],
        ),
    ]
