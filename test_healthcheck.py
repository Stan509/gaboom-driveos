#!/usr/bin/env python
"""
Test script for healthcheck endpoints.
Run with: python test_healthcheck.py
"""

import requests
import json
import sys

def test_healthcheck(base_url="http://localhost:8000"):
    """Test all healthcheck endpoints."""
    
    endpoints = [
        ("/health/", "Basic healthcheck"),
        ("/health/ready/", "Readiness probe"),
        ("/health/live/", "Liveness probe"),
    ]
    
    print("🧪 Testing Healthcheck Endpoints")
    print("=" * 50)
    
    all_passed = True
    
    for endpoint, description in endpoints:
        url = f"{base_url}{endpoint}"
        print(f"\n📍 Testing {description}: {url}")
        
        try:
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Status: {response.status_code}")
                print(f"   ✅ Response: {json.dumps(data, indent=6)}")
            else:
                print(f"   ❌ Status: {response.status_code}")
                print(f"   ❌ Response: {response.text}")
                all_passed = False
                
        except requests.exceptions.RequestException as e:
            print(f"   ❌ Error: {e}")
            all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 All healthcheck endpoints passed!")
        return 0
    else:
        print("❌ Some healthcheck endpoints failed!")
        return 1

if __name__ == "__main__":
    # Allow custom base URL as argument
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    exit(test_healthcheck(base_url))
