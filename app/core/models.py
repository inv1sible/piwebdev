from django.conf import settings
from django.contrib.auth.models import User
from django.db import models


class Project(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True)
    path = models.CharField(max_length=600, unique=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="projects")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProjectMemory(models.Model):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="memory")
    content = models.TextField(default="# General Memory\n\n# Todos\n\n# Ideas For Later\n")
    updated_at = models.DateTimeField(auto_now=True)


class UserPiSettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="pi_settings")
    provider = models.CharField(max_length=120, default=settings.DEFAULT_PI_PROVIDER)
    model = models.CharField(max_length=160, default=settings.DEFAULT_PI_MODEL)
    thinking_level = models.CharField(max_length=40, default=settings.DEFAULT_PI_THINKING)
    mindset = models.TextField(blank=True, default="")
    extra_args = models.CharField(max_length=500, blank=True, default="")


class ProjectPiSettings(models.Model):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="pi_settings")
    provider = models.CharField(max_length=120, blank=True, default="")
    model = models.CharField(max_length=160, blank=True, default="")
    thinking_level = models.CharField(max_length=40, blank=True, default="")
    mindset = models.TextField(blank=True, default="")
    inject_memory = models.BooleanField(default=True)
    extra_args = models.CharField(max_length=500, blank=True, default="")


class PiSession(models.Model):
    STATUS_CHOICES = [("idle", "Idle"), ("running", "Running"), ("stopped", "Stopped"), ("archived", "Archived")]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="sessions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pi_sessions")
    title = models.CharField(max_length=160, default="New session")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="idle")
    session_dir = models.CharField(max_length=800, blank=True, default="")
    provider = models.CharField(max_length=120, blank=True, default="")
    model = models.CharField(max_length=160, blank=True, default="")
    thinking_level = models.CharField(max_length=40, blank=True, default="")
    mindset = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_started_at = models.DateTimeField(null=True, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]


class ChatMessage(models.Model):
    ROLE_CHOICES = [("user", "User"), ("assistant", "Assistant"), ("tool", "Tool"), ("system", "System")]
    session = models.ForeignKey(PiSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField(blank=True, default="")
    raw_event = models.JSONField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:80]}"
