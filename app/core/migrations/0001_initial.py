# Generated manually for PiWebDev
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name='Project',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('slug', models.SlugField(max_length=120, unique=True)),
                ('path', models.CharField(max_length=600, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='projects', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='PiSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(default='New session', max_length=160)),
                ('status', models.CharField(choices=[('idle', 'Idle'), ('running', 'Running'), ('stopped', 'Stopped'), ('archived', 'Archived')], default='idle', max_length=20)),
                ('session_dir', models.CharField(blank=True, default='', max_length=800)),
                ('provider', models.CharField(blank=True, default='', max_length=120)),
                ('model', models.CharField(blank=True, default='', max_length=160)),
                ('thinking_level', models.CharField(blank=True, default='', max_length=40)),
                ('mindset', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('last_started_at', models.DateTimeField(blank=True, null=True)),
                ('last_message_at', models.DateTimeField(blank=True, null=True)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sessions', to='core.project')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pi_sessions', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-updated_at']},
        ),
        migrations.CreateModel(
            name='ChatMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('user', 'User'), ('assistant', 'Assistant'), ('tool', 'Tool'), ('system', 'System')], max_length=20)),
                ('content', models.TextField(blank=True, default='')),
                ('raw_event', models.JSONField(blank=True, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='core.pisession')),
            ],
            options={'ordering': ['created_at']},
        ),
        migrations.CreateModel(
            name='ProjectMemory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField(default='# General Memory\n\n# Todos\n\n# Ideas For Later\n')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('project', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='memory', to='core.project')),
            ],
        ),
        migrations.CreateModel(
            name='ProjectPiSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.CharField(blank=True, default='', max_length=120)),
                ('model', models.CharField(blank=True, default='', max_length=160)),
                ('thinking_level', models.CharField(blank=True, default='', max_length=40)),
                ('mindset', models.TextField(blank=True, default='')),
                ('inject_memory', models.BooleanField(default=True)),
                ('extra_args', models.CharField(blank=True, default='', max_length=500)),
                ('project', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='pi_settings', to='core.project')),
            ],
        ),
        migrations.CreateModel(
            name='UserPiSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.CharField(default='openai-codex', max_length=120)),
                ('model', models.CharField(default='gpt-5.5', max_length=160)),
                ('thinking_level', models.CharField(default='minimal', max_length=40)),
                ('mindset', models.TextField(blank=True, default='')),
                ('extra_args', models.CharField(blank=True, default='', max_length=500)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='pi_settings', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
