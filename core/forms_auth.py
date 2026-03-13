from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm


User = get_user_model()


class EmailOrUsernameAuthenticationForm(AuthenticationForm):
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request=request, *args, **kwargs)

        self.fields["username"].label = "Email de l'agence"
        self.fields["username"].widget = forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "placeholder": "email@agence.com",
            }
        )

    def clean(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if username and "@" in username:
            try:
                user = User.objects.get(email__iexact=username)
                self.cleaned_data["username"] = user.get_username()
            except User.DoesNotExist:
                pass
        return super().clean()
