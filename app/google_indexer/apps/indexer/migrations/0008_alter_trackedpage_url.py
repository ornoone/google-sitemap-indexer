from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("indexer", "0007_callerror"),
    ]

    operations = [
        migrations.AlterField(
            model_name="trackedpage",
            name="url",
            field=models.URLField(max_length=1000),
        ),
    ]
