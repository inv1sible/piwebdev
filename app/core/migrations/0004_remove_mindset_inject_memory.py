from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_context_files"),
    ]

    operations = [
        migrations.RemoveField(model_name="userpisettings", name="mindset"),
        migrations.RemoveField(model_name="projectpisettings", name="mindset"),
        migrations.RemoveField(model_name="projectpisettings", name="inject_memory"),
        migrations.RemoveField(model_name="pisession", name="mindset"),
    ]
