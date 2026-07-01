#!/usr/bin/env python
"""Test carrier detection."""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.mirakl.order_service import mirakl_order_service
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_test_order(country_code, country_name):
    """Create a test order with given country details."""
    return {
        "order_id": f"TEST-{country_code}",
        "customer": {
            "shipping_address": {
                "country": country_name,
                "country_iso_code": country_code,
                "city": "Test City",
                "zip_code": "12345",
                "firstname": "Test",
                "lastname": "User"
            }
        },
        "order_additional_fields": [],
        "order_lines": []
    }

def test_carrier_detection():
    """Test carrier detection for different countries."""
    print("=" * 50)
    print("CARRIER DETECTION TEST")
    print("=" * 50)
    
    test_cases = [
        ("FR", "France", "Colissimo"),
        ("DE", "Germany", "GLS"),
        ("ES", "Spain", "GLS"),
        ("IT", "Italy", "GLS"),
        ("GB", "United Kingdom", "GLS"),
        ("US", "United States", "Colissimo"),
        ("CA", "Canada", "Colissimo"),
        ("PL", "Poland", "GLS"),
        ("MQ", "Martinique", "Colissimo"),
    ]
    
    for code, name, expected in test_cases:
        order = create_test_order(code, name)
        carrier = mirakl_order_service.detect_carrier_by_destination(order)
        result = "✓" if carrier["name"] == expected else "✗"
        print(f"{result} {code} ({name}) → {carrier['name']} (expected: {expected})")
    
    print("=" * 50)

if __name__ == "__main__":
    test_carrier_detection()