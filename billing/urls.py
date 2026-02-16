from django.urls import path

from . import views_paypal

app_name = "billing"

urlpatterns = [
    # PayPal subscription endpoints
    path("paypal/subscribe/", views_paypal.subscribe_paypal, name="paypal_subscribe"),
    path("paypal/success/", views_paypal.paypal_success, name="paypal_success"),
    path("paypal/cancel/", views_paypal.paypal_cancel, name="paypal_cancel"),
]
