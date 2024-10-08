# Generated by Django 5.1.1 on 2024-10-08 17:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('indexer', '0004_trackedsite_next_verification'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='trackedpage',
            name='last_verification',
        ),
        migrations.RemoveField(
            model_name='trackedpage',
            name='next_verification',
        ),
        migrations.AlterField(
            model_name='trackedpage',
            name='status',
            field=models.CharField(choices=[('2_NEED_INDEXATION', 'need indexation'), ('3_PENDING_INDEXATION_CALL', 'pending indexation call'), ('5_INDEXED', 'indexed')], default='2_NEED_INDEXATION', max_length=255),
        ),
        migrations.AlterField(
            model_name='trackedsite',
            name='status',
            field=models.CharField(choices=[('CREATED', 'created'), ('PENDING', 'pending'), ('HOLD', 'hold'), ('OK', 'up to date')], default='CREATED', max_length=255),
        ),
    ]