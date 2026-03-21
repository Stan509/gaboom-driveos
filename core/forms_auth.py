from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from agencies.models import Agency


User = get_user_model()


class EmailOrUsernameAuthenticationForm(AuthenticationForm):
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request=request, *args, **kwargs)

        self.fields["username"].label = "Nom d'agence"
        self.fields["username"].widget = forms.TextInput(
            attrs={
                "autocomplete": "organization",
                "placeholder": "nom de l'agence",
            }
        )

    def clean_username(self):
        username = self.cleaned_data.get('username')
        
        # Si le username correspond à un nom d'agence, trouver l'utilisateur associé
        try:
            agency = Agency.objects.get(name__iexact=username)
            # Prendre le premier utilisateur de l'agence
            user = agency.users.first()
            if user:
                return user.username
        except Agency.DoesNotExist:
            pass
        except Exception:
            pass
        
        # Sinon, utiliser le username normal
        return username

    def clean(self):
        # Appeler la méthode parent avec le username potentiellement modifié
        return super().clean()
