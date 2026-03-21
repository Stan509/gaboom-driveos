from django.urls import path

from . import views
from . import views_cms
from . import views_growth
from . import views_gps
from . import views_marketing

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    # Vehicles
    path("vehicles/", views.vehicle_hub, name="vehicle_hub"),
    path("vehicles/new/", views.vehicle_create, name="vehicle_create"),
    path("vehicles/<int:pk>/edit/", views.vehicle_edit, name="vehicle_edit"),
    path("vehicles/<int:pk>/delete/", views.vehicle_delete, name="vehicle_delete"),
    path("vehicles/<int:pk>/duplicate/", views.vehicle_duplicate, name="vehicle_duplicate"),
    path("vehicles/<int:pk>/toggle-negotiation/", views.vehicle_toggle_negotiation, name="vehicle_toggle_negotiation"),
    # Clients
    path("clients/", views.client_hub, name="client_hub"),
    path("clients/new/", views.client_create, name="client_create"),
    path("clients/<int:pk>/", views.client_detail, name="client_detail"),
    path("clients/<int:pk>/edit/", views.client_edit, name="client_edit"),
    path("clients/<int:pk>/delete/", views.client_delete, name="client_delete"),
    # Contracts
    path("contracts/", views.contract_hub, name="contract_hub"),
    path("contracts/new/", views.contract_create, name="contract_create"),
    path("contracts/<int:pk>/", views.contract_detail, name="contract_detail"),
    path("contracts/<int:pk>/sign-client/", views.contract_sign_client, name="contract_sign_client"),
    path("contracts/<int:pk>/print/", views.contract_print, name="contract_print"),
    path("contracts/<int:pk>/close/", views.contract_close, name="contract_close"),
    path("contracts/<int:pk>/cancel/", views.contract_cancel, name="contract_cancel"),
    path("contracts/<int:pk>/send-to-sign/", views.contract_send_to_sign, name="contract_send_to_sign"),
    path("contracts/<int:pk>/activate/", views.contract_activate, name="contract_activate"),
    path("contracts/<int:pk>/start-return/", views.contract_start_return, name="contract_start_return"),
    path("contracts/<int:pk>/inspection/", views.contract_inspection, name="contract_inspection"),
    path("contracts/<int:pk>/photos/upload/", views.contract_photo_upload, name="contract_photo_upload"),
    path("contracts/<int:pk>/photos/<int:photo_pk>/delete/", views.contract_photo_delete, name="contract_photo_delete"),
    path("contracts/from-reservation/<int:reservation_pk>/", views.contract_from_reservation, name="contract_from_reservation"),
    # Payments
    path("payments/", views.payment_list, name="payment_list"),
    path("payments/export/", views.payment_export, name="payment_export"),
    path("payments/<int:pk>/receipt/", views.payment_receipt, name="payment_receipt"),
    path("contracts/<int:contract_pk>/pay/", views.payment_create, name="payment_create"),
    # Maintenance
    path("maintenance/", views.maintenance_list, name="maintenance_list"),
    path("maintenance/<int:pk>/record/", views.maintenance_record, name="maintenance_record"),
    path("maintenance/<int:pk>/update-km/", views.maintenance_update_km, name="maintenance_update_km"),
    path("maintenance/<int:pk>/history/", views.maintenance_history, name="maintenance_history"),
    # Business settings
    path("business-settings/", views.business_settings, name="business_settings"),
    # Team
    path("team/", views.team_list, name="team"),
    path("team/new/", views.team_create, name="team_create"),
    path("team/<int:pk>/edit/", views.team_edit, name="team_edit"),
    path("team/<int:pk>/toggle/", views.team_toggle_active, name="team_toggle_active"),
    path("team/<int:pk>/delete/", views.team_delete, name="team_delete"),
    # Account
    path("account/", views.account, name="account"),
    # Reservations
    path("reservations/", views.reservation_list, name="reservation_list"),
    path("reservations/<int:pk>/", views.reservation_detail, name="reservation_detail"),
    path("reservations/<int:pk>/confirm/", views.reservation_confirm, name="reservation_confirm"),
    path("reservations/<int:pk>/reject/", views.reservation_reject, name="reservation_reject"),
    # Negotiation
    path("reservations/<int:pk>/accept-offer/", views.nego_accept_offer, name="nego_accept_offer"),
    path("reservations/<int:pk>/counter-offer/", views.nego_counter_offer, name="nego_counter_offer"),
    path("reservations/<int:pk>/refuse-offer/", views.nego_refuse, name="nego_refuse"),
    path("reservations/<int:pk>/send-message/", views.nego_send_message, name="nego_send_message"),
    # Subscription (agency)
    path("subscription/", views.subscription, name="subscription"),
    path("abonnement/", views.subscription, name="subscription_alias"),
    path("subscription/paypal/start/", views.start_paypal_subscription, name="start_paypal"),
    path("subscription/paypal/return/", views.paypal_return_success, name="paypal_return"),
    path("subscription/paypal/cancel/", views.paypal_cancel_return, name="paypal_cancel"),
    # Superadmin — agencies access
    path("admin/agencies-access/", views.admin_agencies_access, name="admin_agencies_access"),
    path("admin/agencies-access/<int:pk>/", views.admin_agency_access_detail, name="admin_agency_access_detail"),
    path("admin/access/<int:pk>/renew/", views.admin_access_renew, name="admin_access_renew"),
    path("admin/access/<int:pk>/suspend/", views.admin_access_suspend, name="admin_access_suspend"),
    path("admin/access/<int:pk>/bonus/", views.admin_access_bonus, name="admin_access_bonus"),
    path("admin/access/<int:pk>/notes/", views.admin_access_save_notes, name="admin_access_save_notes"),
    path("admin/proof/<int:proof_pk>/approve/", views.admin_proof_approve, name="admin_proof_approve"),
    path("admin/proof/<int:proof_pk>/reject/", views.admin_proof_reject, name="admin_proof_reject"),
    # Site public
    path("site-public/", views.site_public_settings, name="site_public_settings"),
    # CMS Pages
    path("site-public/pages/", views_cms.cms_page_list, name="cms_page_list"),
    path("site-public/pages/new/", views_cms.cms_page_create, name="cms_page_create"),
    path("site-public/pages/<int:pk>/edit/", views_cms.cms_page_edit, name="cms_page_edit"),
    path("site-public/pages/<int:pk>/delete/", views_cms.cms_page_delete, name="cms_page_delete"),
    # Growth — Themes
    path("themes/", views_growth.theme_settings, name="theme_settings"),
    # Growth — Marketing
    path("marketing/", views_growth.marketing_dashboard, name="marketing_dashboard"),
    # Growth — Promo codes
    path("promotions/", views_growth.promo_list, name="promo_list"),
    path("promotions/new/", views_growth.promo_create, name="promo_create"),
    path("promotions/<int:pk>/edit/", views_growth.promo_edit, name="promo_edit"),
    path("promotions/<int:pk>/delete/", views_growth.promo_delete, name="promo_delete"),
    # Growth — Banners
    path("banners/", views_growth.banner_list, name="banner_list"),
    path("banners/new/", views_growth.banner_create, name="banner_create"),
    path("banners/<int:pk>/edit/", views_growth.banner_edit, name="banner_edit"),
    path("banners/<int:pk>/delete/", views_growth.banner_delete, name="banner_delete"),
    # Growth — Campaigns
    path("campaigns/", views_growth.campaign_list, name="campaign_list"),
    path("campaigns/new/", views_growth.campaign_create, name="campaign_create"),
    path("campaigns/<int:pk>/edit/", views_growth.campaign_edit, name="campaign_edit"),
    path("campaigns/<int:pk>/send/", views_growth.campaign_send, name="campaign_send"),
    path("campaigns/<int:pk>/delete/", views_growth.campaign_delete, name="campaign_delete"),
    # ── Marketing Engine 2.0 ──
    path("mkt/campaigns/", views_marketing.campaign_list, name="mkt_campaign_list"),
    path("mkt/campaigns/new/", views_marketing.campaign_create, name="mkt_campaign_create"),
    path("mkt/campaigns/<int:pk>/edit/", views_marketing.campaign_edit, name="mkt_campaign_edit"),
    path("mkt/campaigns/<int:pk>/delete/", views_marketing.campaign_delete, name="mkt_campaign_delete"),
    path("mkt/campaigns/<int:pk>/send/", views_marketing.campaign_send, name="mkt_campaign_send"),
    path("mkt/settings/update/", views_marketing.marketing_settings_update, name="mkt_settings_update"),
    path("mkt/automations/", views_marketing.automation_list, name="mkt_automations"),
    path("mkt/automations/create/", views_marketing.automation_create, name="mkt_automation_create"),
    path("mkt/automations/<int:pk>/toggle/", views_marketing.automation_toggle, name="mkt_automation_toggle"),
    path("mkt/automations/<int:pk>/delete/", views_marketing.automation_delete, name="mkt_automation_delete"),
    path("mkt/automations/<int:pk>/update/", views_marketing.automation_update, name="mkt_automation_update"),
    path("mkt/automations/<int:pk>/dryrun/", views_marketing.automation_dryrun, name="mkt_automation_dryrun"),
    path("mkt/analytics/", views_marketing.analytics, name="mkt_analytics"),
    path("mkt/whatsapp/", views_marketing.wa_outbox, name="mkt_wa_outbox"),
    path("mkt/whatsapp/<int:pk>/sent/", views_marketing.wa_mark_sent, name="mkt_wa_mark_sent"),
    # ── GPS Tracking ──
    path("maps/", views_gps.maps_hub, name="maps_hub"),
    path("gps/", views_gps.gps_tracking, name="gps_tracking"),
    path("gps/zones/", views_gps.zone_list, name="gps_zone_list"),
    path("gps/zones/new/", views_gps.zone_create, name="gps_zone_create"),
    path("gps/zones/<int:pk>/edit/", views_gps.zone_edit, name="gps_zone_edit"),
    path("gps/zones/<int:pk>/delete/", views_gps.zone_delete, name="gps_zone_delete"),
    path("gps/alerts/", views_gps.alert_list, name="gps_alert_list"),
    path("gps/alerts/<int:pk>/resolve/", views_gps.alert_resolve, name="gps_alert_resolve"),
    path("gps/vehicles/<int:pk>/config/", views_gps.vehicle_gps_config, name="vehicle_gps_config"),
    path("gps/contracts/<int:pk>/config/", views_gps.contract_gps_config, name="contract_gps_config"),
    # API
    path("api/set-theme/", views.api_set_theme, name="api_set_theme"),
    path("api/ai-writer/", views_growth.api_ai_writer, name="api_ai_writer"),
    path("api/mkt-ai/", views_marketing.api_ai_writer, name="mkt_api_ai"),
    path("api/gps/update/", views_gps.api_gps_update, name="api_gps_update"),
    path("api/gps/devices/", views_gps.api_gps_device_create, name="api_gps_device_create"),
    path("api/gps/simulate/", views_gps.api_gps_simulate, name="api_gps_simulate"),
    path("api/gps/positions/", views_gps.api_gps_positions, name="api_gps_positions"),
    path("api/gps/trail/<int:pk>/", views_gps.api_vehicle_trail, name="api_gps_trail"),
    path("api/maps/ai-analyze/", views_gps.api_maps_ai_analyze, name="api_maps_ai_analyze"),
    path("api/maps/heatmap/", views_gps.api_maps_heatmap, name="api_maps_heatmap"),
]
