#!/usr/bin/env python
"""
Test simple healthcheck endpoint.
Run with: python test_health_simple.py
"""

import requests
import json
import sys

def test_healthcheck(base_url="http://localhost:8000"):
    """Test the basic healthcheck endpoint."""
    
    url = f"{base_url}/health/"
    
    print("🧪 Testing Simple Healthcheck Endpoint")
    print("=" * 40)
    print(f"URL: {url}")
    
    try:
        response = requests.get(url, timeout=5)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response JSON: {json.dumps(data, indent=2)}")
            
            if data.get("status") == "ok":
                print("✅ Healthcheck passed!")
                return 0
            else:
                print("❌ Invalid response status")
                return 1
        else:
            print(f"❌ Expected status 200, got {response.status_code}")
            print(f"Response: {response.text}")
            return 1
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return 1
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON response: {e}")
        print(f"Response: {response.text}")
        return 1

if __name__ == "__main__":
    # Allow custom base URL as argument
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    exit(test_healthcheck(base_url))
