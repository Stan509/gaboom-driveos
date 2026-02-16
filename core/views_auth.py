from django.contrib.auth.views import LoginView

from agencies.services import get_agency_access, sync_access


class RoleBasedLoginView(LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        user = self.request.user
        # D) Login intelligent
        if user.is_superuser:
            return "/saas/"
        agency = getattr(user, "agency", None)
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
