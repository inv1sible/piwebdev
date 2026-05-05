from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User


class UsernameOrEmailAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label="Username or email")

    def clean(self):
        ident = self.cleaned_data.get("username")
        if ident and "@" in ident:
            try:
                self.cleaned_data["username"] = User.objects.get(email__iexact=ident).username
            except User.DoesNotExist:
                pass
        return super().clean()
