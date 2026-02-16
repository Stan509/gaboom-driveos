from django.urls import path

from . import views

app_name = "superadmin"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("agencies/", views.agencies_list, name="agencies"),
    path("agencies/<int:pk>/", views.agency_detail, name="agency_detail"),
    path("proofs/", views.proofs_list, name="proofs"),
    path("settings/", views.saas_settings, name="settings"),
    path("settings/payments/", views.payments_settings, name="payments_settings"),
    path("settings/payments/test-email/", views.payments_test_email, name="payments_test_email"),
    path("webhooks/", views.webhooks_log, name="webhooks_log"),
    path("audit/", views.audit_list, name="audit"),
    # Setup Wizard
    path("setup/", views.setup_wizard, name="setup_wizard"),
    path("setup/save-domain/", views.setup_save_domain, name="setup_save_domain"),
    path("setup/save-keys/", views.setup_save_keys, name="setup_save_keys"),
    path("setup/save-plans/", views.setup_save_plans, name="setup_save_plans"),
    path("setup/save-webhook/", views.setup_save_webhook, name="setup_save_webhook"),
    path("setup/validate-all/", views.setup_validate_all, name="setup_validate_all"),
    path("setup/paypal/test-token/", views.setup_test_token, name="setup_test_token"),
    path("setup/paypal/test-plan/", views.setup_test_plan, name="setup_test_plan"),
    path("setup/paypal/create-plan/", views.setup_create_plan, name="setup_create_plan"),
    path("setup/paypal/test-webhook/", views.setup_test_webhook, name="setup_test_webhook"),
    path("setup/paypal/simulate-webhook/", views.setup_simulate_webhook, name="setup_simulate_webhook"),
    path("setup/status/", views.setup_status, name="setup_status"),
    # Alerts
    path("alerts/", views.alerts_list, name="alerts"),
    path("alerts/<int:pk>/read/", views.alert_mark_read, name="alert_mark_read"),
    path("alerts/mark-all-read/", views.alerts_mark_all_read, name="alerts_mark_all_read"),
    # Actions
    path("access/<int:pk>/renew/", views.action_renew, name="action_renew"),
    path("access/<int:pk>/suspend/", views.action_suspend, name="action_suspend"),
    path("access/<int:pk>/bonus/", views.action_bonus, name="action_bonus"),
    path("access/<int:pk>/notes/", views.action_save_notes, name="action_save_notes"),
    path("proof/<int:proof_pk>/approve/", views.action_proof_approve, name="action_proof_approve"),
    path("proof/<int:proof_pk>/reject/", views.action_proof_reject, name="action_proof_reject"),
    path("access/<int:pk>/dismiss-alert/", views.action_dismiss_alert, name="action_dismiss_alert"),
]
