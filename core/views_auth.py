from django.contrib.auth.views import LoginView

from agencies.services import get_agency_access, sync_access
from core.forms_auth import EmailOrUsernameAuthenticationForm


class RoleBasedLoginView(LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True
    authentication_form = EmailOrUsernameAuthenticationForm

    def get_success_url(self):
        user = self.request.user
        # D) Login intelligent
        if user.is_superuser:
            return "/saas/"
        try:
            agency = getattr(user, "agency", None)
        except Exception:
            agency = None
        if agency:
            try:
                access = get_agency_access(agency)
                sync_access(access)
                is_paypal_active = (
                    access.billing_mode == "paypal"
                    and access.paypal_status == "active"
                )
                if not is_paypal_active and (
                    access.status == "suspended" or access.should_block_now
                ):
                    return "/dashboard/subscription/"
            except Exception:
                pass
            return "/dashboard/"
        return "/"
