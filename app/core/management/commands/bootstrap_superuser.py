import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create/update initial superuser from environment"

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        if not username or not password:
            self.stdout.write("No superuser env configured.")
            return
        User = get_user_model()
        user, created = User.objects.get_or_create(username=username, defaults={"email": email, "is_staff": True, "is_superuser": True})
        changed = created
        if email and user.email != email:
            user.email = email
            changed = True
        if not user.is_staff or not user.is_superuser:
            user.is_staff = True
            user.is_superuser = True
            changed = True
        # Keep the bootstrap admin password in sync with .env. This is expected for this
        # local/admin-managed deployment and prevents confusion after regenerating .env.
        user.set_password(password)
        changed = True
        if changed:
            user.save()
        self.stdout.write(self.style.SUCCESS(f"Superuser ready: {username}"))
