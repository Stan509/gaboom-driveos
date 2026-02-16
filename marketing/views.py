from django.contrib.auth import login
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from core.views import _send_verification_email
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
            _send_verification_email(request, user)
            return redirect("verify_required")
    else:
        form = AgencySignupForm()

    plan_cards = [PLAN_CONFIGS["starter"], PLAN_CONFIGS["business"], PLAN_CONFIGS["enterprise"]]
    return render(request, "marketing/signup.html", {"form": form, "plan_cards": plan_cards})
