import json
import logging

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from agencies.models_access import AgencyAccess
from core.models_paypal_subscription import PayPalSubscription
from core.services_paypal_api import create_paypal_subscription
from core.services_platform import get_paypal_config

logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
@csrf_exempt
def subscribe_paypal(request: HttpRequest) -> JsonResponse:
    """
    Create a PayPal subscription for an agency.
    POST /billing/paypal/subscribe/
    
    Input:
    - plan_code: "starter" | "business" | "enterprise"
    - agency_id: (optional) if user has multiple agencies
    
    Output:
    - approval_url: URL to redirect user for PayPal approval
    - paypal_subscription_id: PayPal subscription ID
    """
    try:
        # Parse request data
        if request.content_type == "application/json":
            data = json.loads(request.body)
        else:
            data = request.POST
        
        plan_code = data.get("plan_code")
        if not plan_code or plan_code not in ["starter", "business", "enterprise"]:
            return JsonResponse({
                "ok": False,
                "message": "plan_code requis (starter/business/enterprise)"
            }, status=400)
        
        # Get agency (for now, assume user has one agency)
        try:
            if request.user.is_authenticated:
                agency_access = AgencyAccess.objects.select_related("agency").get(
                    agency__users=request.user
                )
            else:
                return JsonResponse({
                    "ok": False,
                    "message": "Utilisateur non authentifié"
                }, status=401)
        except AgencyAccess.DoesNotExist:
            return JsonResponse({
                "ok": False,
                "message": "Aucune agence trouvée pour cet utilisateur"
            }, status=404)
        except AgencyAccess.MultipleObjectsReturned:
            # If user has multiple agencies, require agency_id
            agency_id = data.get("agency_id")
            if not agency_id:
                return JsonResponse({
                    "ok": False,
                    "message": "agency_id requis (utilisateur a plusieurs agences)"
                }, status=400)
            agency_access = AgencyAccess.objects.select_related("agency").get(
                agency_id=agency_id, agency__users=request.user
            )
        
        # Get PayPal configuration
        config = get_paypal_config()
        if not config["client_id"] or not config["secret"]:
            return JsonResponse({
                "ok": False,
                "message": "Configuration PayPal incomplète"
            }, status=500)
        
        # Get plan ID based on plan_code and mode (sandbox/live)
        if config["mode"] == "live":
            plan_id_map = {
                "starter": config.get("plan_id_starter_live"),
                "business": config.get("plan_id_business_live"),
                "enterprise": config.get("plan_id_enterprise_live"),
            }
        else:
            plan_id_map = {
                "starter": config.get("plan_id_starter_sandbox"),
                "business": config.get("plan_id_business_sandbox"),
                "enterprise": config.get("plan_id_enterprise_sandbox"),
            }
        
        plan_id = plan_id_map.get(plan_code)
        if not plan_id:
            return JsonResponse({
                "ok": False,
                "message": f"Plan ID non configuré pour {plan_code} en mode {config['mode']}"
            }, status=500)
        
        # Create PayPal subscription
        try:
            subscription_result = create_paypal_subscription(
                plan_id=plan_id,
                return_url=f"{config['base_url']}/billing/paypal/success/",
                cancel_url=f"{config['base_url']}/billing/paypal/cancel/",
            )
        except Exception as e:
            logger.error(f"PayPal subscription creation failed: {e}")
            return JsonResponse({
                "ok": False,
                "message": f"Erreur PayPal: {str(e)}"
            }, status=500)
        
        if not subscription_result.get("approval_url"):
            return JsonResponse({
                "ok": False,
                "message": "PayPal n'a pas retourné d'approval_url"
            }, status=500)
        
        paypal_subscription_id = subscription_result.get("subscription_id")
        approval_url = subscription_result.get("approval_url")
        
        # Update AgencyAccess with PayPal subscription ID
        agency_access.paypal_subscription_id = paypal_subscription_id
        agency_access.paypal_status = "approval_pending"
        agency_access.save(update_fields=["paypal_subscription_id", "paypal_status"])
        
        # Create/update PayPalSubscription record
        paypal_sub, created = PayPalSubscription.objects.update_or_create(
            access=agency_access,
            defaults={
                "paypal_subscription_id": paypal_subscription_id,
                "status": "APPROVAL_PENDING",
                "plan_id": plan_id,
                "product_id": subscription_result.get("product_id", ""),
            }
        )
        
        logger.info(f"PayPal subscription created: {paypal_subscription_id} for agency {agency_access.agency.name}")
        
        return JsonResponse({
            "ok": True,
            "approval_url": approval_url,
            "paypal_subscription_id": paypal_subscription_id,
            "message": "Abonnement PayPal créé. Redirigez l'utilisateur vers l'URL d'approbation."
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "ok": False,
            "message": "JSON invalide"
        }, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in subscribe_paypal: {e}")
        return JsonResponse({
            "ok": False,
            "message": f"Erreur serveur: {str(e)}"
        }, status=500)


@require_http_methods(["GET"])
def paypal_success(request: HttpRequest) -> JsonResponse:
    """
    Handle successful PayPal subscription approval.
    GET /billing/paypal/success/?subscription_id=I-XXXXX&token=XXXXX
    """
    subscription_id = request.GET.get("subscription_id")
    if not subscription_id:
        return JsonResponse({
            "ok": False,
            "message": "subscription_id manquant"
        }, status=400)
    
    try:
        # Find the subscription
        paypal_sub = PayPalSubscription.objects.select_related("access__agency").get(
            paypal_subscription_id=subscription_id
        )
        
        # Update status (will be finalized by webhook)
        paypal_sub.status = "APPROVED"
        paypal_sub.save(update_fields=["status"])
        
        return JsonResponse({
            "ok": True,
            "message": "Abonnement approuvé. En attente de finalisation...",
            "agency_name": paypal_sub.access.agency.name
        })
        
    except PayPalSubscription.DoesNotExist:
        return JsonResponse({
            "ok": False,
            "message": "Abonnement non trouvé"
        }, status=404)


@require_http_methods(["GET"])
def paypal_cancel(request: HttpRequest) -> JsonResponse:
    """
    Handle cancelled PayPal subscription.
    GET /billing/paypal/cancel/
    """
    return JsonResponse({
        "ok": False,
        "message": "Abonnement annulé par l'utilisateur"
    })
