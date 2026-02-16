from django.urls import path

from . import views

app_name = "marketing"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("demo/", views.demo, name="demo"),
    path("signup/", views.signup, name="signup"),
]
