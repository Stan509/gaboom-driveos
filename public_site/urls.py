from django.urls import path

from . import views
from clients import views_portal

app_name = "public_site"

urlpatterns = [
    # Agency public pages
    path("<slug:slug>/", views.agency_public_home, name="agency_public_home"),
    path("<slug:slug>/catalog/", views.agency_catalog, name="agency_catalog"),
    path("<slug:slug>/vehicle/<int:vehicle_id>/", views.vehicle_detail, name="vehicle_detail"),
    path("<slug:slug>/book/", views.vehicle_book, name="vehicle_book"),
    path("<slug:slug>/reserve/<int:vehicle_id>/", views.reserve_vehicle, name="reserve_vehicle"),
    path("<slug:slug>/reservation/<uuid:token>/", views.reservation_status, name="reservation_status"),
    path("<slug:slug>/reservation/<uuid:token>/poll/", views.reservation_poll, name="reservation_poll"),
    path("<slug:slug>/reservation/<uuid:token>/accept-counter/", views.reservation_accept_counter, name="reservation_accept_counter"),
    path("<slug:slug>/reservation/<uuid:token>/reject-counter/", views.reservation_reject_counter, name="reservation_reject_counter"),
    path("<slug:slug>/reservation/<uuid:token>/send-message/", views.reservation_send_message, name="reservation_send_message"),
    # CMS pages
    path("<slug:slug>/p/<slug:page_slug>/", views.page_detail, name="page_detail"),
    # Client portal — auth
    path("<slug:slug>/c/login/", views_portal.client_login, name="client_login"),
    path("<slug:slug>/c/signup/", views_portal.client_signup, name="client_signup"),
    path("<slug:slug>/c/logout/", views_portal.client_logout, name="client_logout"),
    # Client portal — pages
    path("<slug:slug>/c/", views_portal.client_dashboard, name="client_dashboard"),
    path("<slug:slug>/c/bookings/", views_portal.client_bookings, name="client_bookings"),
    path("<slug:slug>/c/profile/", views_portal.client_profile, name="client_profile"),
    path("<slug:slug>/c/notifications/", views_portal.client_notifications, name="client_notifications"),
    # Client portal — negotiation
    path("<slug:slug>/c/bookings/<int:pk>/accept-counter/", views_portal.client_accept_counter, name="client_accept_counter"),
    path("<slug:slug>/c/bookings/<int:pk>/refuse-counter/", views_portal.client_refuse_counter, name="client_refuse_counter"),
    # Client portal — contracts
    path("<slug:slug>/c/contracts/", views_portal.client_contracts, name="client_contracts"),
    path("<slug:slug>/c/contracts/<int:pk>/", views_portal.client_contract_detail, name="client_contract_detail"),
    path("<slug:slug>/c/contracts/<int:pk>/sign/", views_portal.client_contract_sign, name="client_contract_sign"),
    # Client portal — GPS tracking
    path("<slug:slug>/c/gps/", views_portal.client_gps_tracking, name="client_gps_tracking"),
    path("<slug:slug>/c/gps/consent/", views_portal.client_gps_consent, name="client_gps_consent"),
    path("<slug:slug>/c/gps/share/", views_portal.client_gps_share, name="client_gps_share"),
    path("<slug:slug>/c/gps/trail/", views_portal.client_vehicle_trail, name="client_gps_trail"),
]
