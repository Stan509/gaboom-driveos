from django.contrib.auth import login
from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from core.views import _send_verification_email
from core.email import get_email_config
from agencies.services import PLAN_CONFIGS
from .forms import AgencySignupForm


def landing(request: HttpRequest) -> HttpResponse:
    return render(request, "marketing/landing.html")


def demo(request: HttpRequest) -> HttpResponse:
    return render(request, "marketing/demo.html")


def signup(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    if request.method == "POST":
        form = AgencySignupForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                _agency, user = form.save()
            login(request, user)
            cfg = get_email_config()
            if not cfg.email_verification_required:
                user.email_verified = True
                user.save(update_fields=["email_verified"])
                return redirect("dashboard:home")

            ok = _send_verification_email(request, user)
            if ok:
                return redirect("verify_required")

            if cfg.email_fail_open:
                request.session["_email_fail_open"] = True
                messages.warning(
                    request,
                    "Email provider unavailable, user created (verification pending).",
                )
                return redirect("dashboard:home")

            messages.error(request, "Impossible d'envoyer l'email de vérification.")
    else:
        form = AgencySignupForm()

    plan_cards = [PLAN_CONFIGS["starter"], PLAN_CONFIGS["business"], PLAN_CONFIGS["enterprise"]]
    return render(request, "marketing/signup.html", {"form": form, "plan_cards": plan_cards})
