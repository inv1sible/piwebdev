import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="userpisettings",
            name="terminal_access",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="TerminalSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("idle", "Idle"), ("running", "Running")], default="idle", max_length=20)),
                ("last_cols", models.SmallIntegerField(default=80)),
                ("last_rows", models.SmallIntegerField(default=24)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_connected_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="terminal_sessions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-last_connected_at"]},
        ),
    ]
