from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("indexer", "__latest__"),
    ]

    operations = [
        migrations.AlterField(
            model_name="trackedpage",
            name="url",
            field=models.URLField(max_length=1000),
        ),
    ]
