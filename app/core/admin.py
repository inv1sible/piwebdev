from django.contrib import admin
from .models import Project, ProjectMemory, UserPiSettings, ProjectPiSettings, PiSession, ChatMessage

admin.site.register(Project)
admin.site.register(ProjectMemory)
admin.site.register(UserPiSettings)
admin.site.register(ProjectPiSettings)
admin.site.register(PiSession)
admin.site.register(ChatMessage)
