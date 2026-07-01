# app/services/mirakl/tracking_service.py

import logging
from typing import Any, Dict

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

class MiraklTrackingService:
    """Mirakl Tracking Update operations"""

    def __init__(self):
        self.base_url = settings.MIRAKL_BASE_URL
        self.api_key = settings.MIRAKL_API_KEY
        self.shop_id = settings.MIRAKL_SHOP_ID
        self.headers = {
            "Authorization": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def update_order_tracking_auto(self, order_id: str, tracking_number: str, db_session=None) -> Dict[str, Any]:
        """Auto-detect carrier and update tracking (NO URL)"""
        from app.services.mirakl.order_service import mirakl_order_service

        try:
            carrier_info = mirakl_order_service.get_carrier_for_order(order_id, db_session)
            carrier_code = carrier_info.get("code", "COLISSIMO")

            # No URL generation needed anymore
            logger.info(f"Auto-detected carrier: {carrier_info['name']}")

            return self.update_order_tracking_with_carrier(
                order_id, tracking_number, carrier_code
            )
        except Exception as e:
            logger.error(f"Error in auto carrier detection: {e}")
            return self.update_order_tracking_with_carrier(
                order_id, tracking_number, "COLISSIMO"
            )

    def update_order_tracking_with_carrier(self, order_id: str, tracking_number: str,
                                          carrier_code: str = "COLISSIMO") -> Dict[str, Any]:
        """
        Update tracking with specified carrier - ONLY carrier name and tracking number.
        Does NOT send tracking URL to Mirakl.
        """
        carrier_configs = {
            "COLISSIMO": {
                "name": "Colissimo",
                "carrier_name": "Colissimo",
            },
            "GLS": {
                "name": "GLS",
                "carrier_name": "GLS",
            }
        }

        carrier = carrier_configs.get(carrier_code, carrier_configs["COLISSIMO"])

        url = f"{self.base_url}/api/orders/{order_id}/tracking"
        params = {"shop_id": self.shop_id}

        # IMPORTANT: Only send carrier_name and tracking_number, NO carrier_url
        payload = {
            "carrier_name": carrier["carrier_name"],
            "tracking_number": tracking_number
            # carrier_url is intentionally omitted
        }

        try:
            logger.info(f"Updating tracking for {order_id} (carrier: {carrier['name']}, no URL)")
            response = requests.put(url, headers=self.headers, params=params,
                                    json=payload, timeout=30)

            if response.status_code == 204:
                return {
                    "success": True,
                    "order_id": order_id,
                    "tracking_number": tracking_number,
                    "carrier": carrier["name"],
                    "message": "Tracking updated successfully (no URL)"
                }
            else:
                error_msg = response.text if response.text else f"HTTP {response.status_code}"
                if response.status_code in [404, 410] and "already" in error_msg.lower():
                    return {
                        "success": False,
                        "order_id": order_id,
                        "tracking_number": tracking_number,
                        "carrier": carrier["name"],
                        "error": error_msg,
                        "already_updated": True
                    }
                return {
                    "success": False,
                    "order_id": order_id,
                    "tracking_number": tracking_number,
                    "carrier": carrier["name"],
                    "error": error_msg
                }
        except Exception as e:
            logger.error(f"Request failed for {order_id}: {e}")
            return {
                "success": False,
                "order_id": order_id,
                "tracking_number": tracking_number,
                "carrier": carrier["name"],
                "error": str(e)
            }

mirakl_tracking_service = MiraklTrackingService()
