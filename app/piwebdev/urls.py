from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", views.PiLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("projects/new/", views.project_create, name="project_create"),
    path("projects/<int:pk>/", views.project_detail, name="project_detail"),
    path("projects/<int:pk>/rename/", views.project_rename, name="project_rename"),
    path("projects/<int:pk>/memory/", views.project_memory, name="project_memory"),
    path("projects/<int:pk>/settings/", views.project_settings, name="project_settings"),
    path("sessions/<int:pk>/clear/", views.session_clear, name="session_clear"),
    path("api/projects/<int:pk>/files/", views.file_tree, name="file_tree"),
    path("api/projects/<int:pk>/file/", views.file_read, name="file_read"),
    path("api/projects/<int:pk>/file/save/", views.file_save, name="file_save"),
    path("api/projects/<int:pk>/file/rename/", views.file_rename, name="file_rename"),
    path("api/projects/<int:pk>/file/new/", views.file_new, name="file_new"),
    path("api/projects/<int:pk>/file/delete/", views.file_delete, name="file_delete"),
    path("api/projects/<int:pk>/upload/", views.file_upload, name="file_upload"),
    path("api/projects/<int:pk>/task/done/", views.task_mark_done, name="task_mark_done"),
    path("api/projects/<int:pk>/memory/", views.api_memory, name="api_memory"),
    path("api/projects/<int:pk>/git/diff/", views.git_diff, name="git_diff"),
    path("api/projects/<int:pk>/git/commit/", views.git_commit, name="git_commit"),
    path("api/projects/<int:pk>/git/push/", views.git_push, name="git_push"),
    path("api/projects/<int:pk>/git/init/", views.git_init, name="git_init"),
    path("terminal/", views.terminal_page, name="terminal"),
    path("manifest.json", views.manifest, name="manifest"),
    path("offline/", views.offline, name="offline"),
    path("service-worker.js", views.service_worker, name="service_worker"),
]
