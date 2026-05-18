from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_terminalsession"),
    ]

    operations = [
        migrations.AddField(
            model_name="userpisettings",
            name="use_context_files",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="projectpisettings",
            name="use_context_files",
            field=models.BooleanField(default=True),
        ),
    ]
