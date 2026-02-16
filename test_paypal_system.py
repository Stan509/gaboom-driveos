#!/usr/bin/env python
"""
Test script for PayPal subscription system.
Run with: python manage.py shell < test_paypal_system.py
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from agencies.models import Agency
from agencies.models_access import AgencyAccess
from core.models_platform import PlatformSettings
from core.models_paypal_event import PayPalEvent
from core.models_paypal_subscription import PayPalSubscription
from core.services_platform import get_paypal_config

User = get_user_model()

def test_paypal_system():
    print("🧪 TESTING PAYPAL SUBSCRIPTION SYSTEM")
    print("=" * 50)
    
    # 1. Test PlatformSettings configuration
    print("\n1️⃣ Testing PlatformSettings...")
    ps = PlatformSettings.get()
    print(f"   ✅ PlatformSettings loaded: {ps.public_base_url}")
    print(f"   ✅ PayPal mode: {ps.paypal_mode}")
    print(f"   ✅ Enable PayPal auto: {ps.enable_paypal_auto}")
    
    # 2. Test PayPal config
    print("\n2️⃣ Testing PayPal config...")
    cfg = get_paypal_config()
    print(f"   ✅ Base URL: {cfg.get('base_url')}")
    print(f"   ✅ Client ID exists: {bool(cfg.get('client_id'))}")
    print(f"   ✅ Secret exists: {bool(cfg.get('secret'))}")
    print(f"   ✅ Webhook URL: {cfg.get('webhook_url')}")
    
    # 3. Test plan IDs
    print("\n3️⃣ Testing plan IDs...")
    if ps.paypal_mode == "live":
        plans = {
            "starter": ps.paypal_plan_id_starter_live,
            "business": ps.paypal_plan_id_business_live,
            "enterprise": ps.paypal_plan_id_enterprise_live,
        }
    else:
        plans = {
            "starter": ps.paypal_plan_id_starter_sandbox,
            "business": ps.paypal_plan_id_business_sandbox,
            "enterprise": ps.paypal_plan_id_enterprise_sandbox,
        }
    
    for plan_code, plan_id in plans.items():
        status = "✅" if plan_id else "❌"
        print(f"   {status} {plan_code}: {plan_id or 'MISSING'}")
    
    # 4. Test webhook events
    print("\n4️⃣ Testing webhook events...")
    event_count = PayPalEvent.objects.count()
    latest_event = PayPalEvent.objects.order_by('-created_at').first()
    print(f"   ✅ Total events: {event_count}")
    if latest_event:
        print(f"   ✅ Latest event: {latest_event.event_type} at {latest_event.created_at}")
        print(f"   ✅ Latest verified: {latest_event.verified}")
    else:
        print("   ⚠️  No events found - use 'Simulate webhook' in admin")
    
    # 5. Test validation endpoint
    print("\n5️⃣ Testing validation endpoint...")
    client = Client()
    
    # Create superuser for testing
    if not User.objects.filter(is_superuser=True).exists():
        User.objects.create_superuser('testadmin', 'test@example.com', 'testpass123')
    
    # Login
    client.login(username='testadmin', password='testpass123')
    
    # Test validation
    response = client.post('/saas/setup/validate-all/')
    if response.status_code == 200:
        data = response.json()
        validation = data.get('validation', {})
        print("   ✅ Validation endpoint working:")
        print(f"      - Domain OK: {validation.get('domain_ok')}")
        print(f"      - Keys OK: {validation.get('keys_ok')}")
        print(f"      - Plans OK: {validation.get('plans_ok')}")
        print(f"      - Webhook OK: {validation.get('webhook_ok')}")
        print(f"      - Events OK: {validation.get('received_event_ok')}")
        print(f"      - Overall OK: {validation.get('overall_ok')}")
        print(f"      - Webhook URL: {validation.get('webhook_url')}")
    else:
        print(f"   ❌ Validation endpoint failed: {response.status_code}")
    
    # 6. Test subscription endpoint (if agency exists)
    print("\n6️⃣ Testing subscription endpoint...")
    try:
        # Get first agency access
        access = AgencyAccess.objects.select_related('agency').first()
        if access:
            print(f"   ✅ Found agency: {access.agency.name}")
            
            # Test subscription creation
            response = client.post('/billing/paypal/subscribe/', {
                'plan_code': 'starter',
                'agency_id': access.agency.id
            })
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    print(f"   ✅ Subscription endpoint working:")
                    print(f"      - Subscription ID: {data.get('paypal_subscription_id')}")
                    print(f"      - Approval URL: {data.get('approval_url')[:50]}...")
                else:
                    print(f"   ⚠️  Subscription endpoint returned error: {data.get('message')}")
            else:
                print(f"   ❌ Subscription endpoint failed: {response.status_code}")
                print(f"      Response: {response.content.decode()}")
        else:
            print("   ⚠️  No agency found - create an agency first")
    except Exception as e:
        print(f"   ❌ Subscription test error: {e}")
    
    print("\n" + "=" * 50)
    print("🎯 PAYPAL SYSTEM TEST COMPLETE")
    print("\nNext steps:")
    print("1. Configure PayPal plans in SuperAdmin → Setup → Step 3")
    print("2. Test webhook with 'Simulate webhook' button")
    print("3. Try creating a real subscription via /billing/paypal/subscribe/")

if __name__ == "__main__":
    test_paypal_system()
