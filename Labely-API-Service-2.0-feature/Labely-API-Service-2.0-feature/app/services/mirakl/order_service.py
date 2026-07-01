"""Mirakl Order API client – fetching, filtering, and extracting order data."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

from app.core.config import settings
from app.services.helpers.carrier import detect_carrier_from_address

logger = logging.getLogger(__name__)

# Carrier field codes accepted from Mirakl additional fields
_CARRIER_FIELD_CODES = {"carrier-manager", "carrier_manager", "carriermanager", "shipping-carrier", "shipping_carrier"}


class MiraklOrderService:
    """HTTP client for Mirakl Order endpoints."""

    def __init__(self) -> None:
        self.base_url = settings.MIRAKL_BASE_URL
        self.headers = {
            "Authorization": settings.MIRAKL_API_KEY,
            "Accept": "application/json",
        }
        self.shop_id = settings.MIRAKL_SHOP_ID
        
        # Validate configuration
        if not self.base_url:
            raise ValueError("MIRAKL_BASE_URL is not configured. Please set the environment variable.")
        if not self.headers.get("Authorization"):
            raise ValueError("MIRAKL_API_KEY is not configured. Please set the environment variable.")
        if not self.shop_id:
            raise ValueError("MIRAKL_SHOP_ID is not configured. Please set the environment variable.")

    # ------------------------------------------------------------------
    # Fetch helpers
    # ------------------------------------------------------------------

    def fetch_orders(
        self,
        start_date: str,
        end_date: str,
        state: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch orders within a date range from Mirakl."""
        params: Dict[str, Any] = {
            "shop_id": self.shop_id,
            "start_date": start_date,
            "end_date": end_date,
            "orders": "SRP",  # Only fetch orders with SRP (carrier manager) field
            "order_state_codes": "SHIPPING",  # Only fetch orders in SHIPPING state
            "max": 100,
        }
        if state:
            params["order_state_codes"] = state

        logger.info("Fetching Mirakl orders [%s → %s]%s", start_date, end_date,
                    f" state={state}" if state else "")
        return self._get_orders(params)

    def fetch_orders_with_filters(
        self,
        carrier_manager: Optional[str] = None,
        order_state: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max: int = 100,
    ) -> List[Dict[str, Any]]:
        """Fetch orders with direct Mirakl API filters."""
        params: Dict[str, Any] = {"shop_id": self.shop_id, "max": max}
        if carrier_manager:
            params["carrier_manager"] = carrier_manager
        if order_state:
            params["order_state_codes"] = order_state
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        logger.info(
            "Fetching Mirakl orders with filters: carrier=%s state=%s",
            carrier_manager, order_state,
        )
        return self._get_orders(params)

    def fetch_single_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single order by ID."""
        params = {"shop_id": self.shop_id, "order_ids": order_id, "max": 1}
        logger.info("Fetching single order %s", order_id)
        orders = self._get_orders(params)
        if orders:
            return orders[0]
        logger.warning("Order %s not found in Mirakl", order_id)
        return None

    def _get_orders(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/orders"
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                logger.error("Mirakl returned non-dict response: %s", type(data))
                return []
            orders = data.get("orders", [])
            logger.info("Mirakl returned %d orders", len(orders))
            return orders
        except requests.HTTPError as exc:
            logger.error("Mirakl HTTP error %s: %s", exc.response.status_code, exc.response.text)
            raise
        except Exception as exc:
            logger.error("Mirakl fetch error: %s", exc, exc_info=True)
            raise

    # ------------------------------------------------------------------
    # Data extraction
    # ------------------------------------------------------------------

    def extract_order_info(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten a raw Mirakl order into a standardised dict."""
        customer = order.get("customer", {})
        shipping_address = customer.get("shipping_address", {})
        
        # Extract carrier manager
        carrier_manager = self.extract_carrier_manager(order)
        
        # Extract order state
        order_state = order.get("order_state", "")
        
        formatted_address = {
            "civility": shipping_address.get("civility", ""),
            "firstname": shipping_address.get("firstname", ""),
            "lastname": shipping_address.get("lastname", ""),
            "company": shipping_address.get("company", ""),
            "company_2": shipping_address.get("company_2", ""),
            "street_1": shipping_address.get("street_1", ""),
            "street_2": shipping_address.get("street_2", ""),
            "zip_code": shipping_address.get("zip_code", ""),
            "city": shipping_address.get("city", ""),
            "state": shipping_address.get("state", ""),
            "country": shipping_address.get("country", ""),
             "country_iso_code": shipping_address.get("country_iso_code", ""),
            "phone": shipping_address.get("phone", ""),
            "additional_info": shipping_address.get("additional_info", "")
        }
        
        result = {
            "order_id": order.get("order_id", ""),
            "order_date": order.get("created_date", ""),
            "carrier_manager": self.extract_carrier_manager(order),
            "customer_email": self._extract_field(order, "customer-email"),
            "order_state": order.get("order_state", ""),
            "shipping_address": self._format_address(shipping_address),
            "commercial_id": order.get("commercial_id", ""),
            "can_shop_ship": order.get("can_shop_ship", False),
            "order_lines": self.extract_order_lines(order),
        }

    def extract_carrier_manager(self, order: Dict[str, Any]) -> str:
        """Extract carrier manager value from order additional fields."""
        for field in order.get("order_additional_fields", []):
            code = field.get("code", "").lower().replace("-", "_")
            value = field.get("value", "")
            if code in _CARRIER_FIELD_CODES and value:
                return value
            # Fallback: any field that contains 'carrier'
            if "carrier" in code and value:
                return value
        return ""

    def extract_order_lines(self, order: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract and normalise order line items."""
        raw_lines = order.get("order_lines") or order.get("commercial_order_lines") or []
        return [
            {
                "sku": line.get("product_sku", ""),
                "product_id": line.get("product_id", ""),
                "product_title": line.get("product_title", ""),
                "quantity": line.get("quantity", 1),
                "description": line.get("description", ""),
                "price": self._extract_price(line.get("price", 0)),
                "total_price": self._extract_price(line.get("total_price", 0)),
                "ean_code": self._extract_line_field(line, "product-ean-code"),
                "campaign_number": self._extract_line_field(line, "campaign-number"),
                "made_in": self._extract_line_field(line, "made-in"),
            }
            for line in raw_lines
        ]

    # ------------------------------------------------------------------
    # Carrier detection (delegates to shared helper)
    # ------------------------------------------------------------------

    def detect_carrier_by_destination(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """Return carrier metadata dict for the order's shipping destination."""
        address = (
            order.get("shipping_address")
            if isinstance(order.get("shipping_address"), dict)
            else self.extract_order_info(order).get("shipping_address", {})
        )
        carrier_name = detect_carrier_from_address(address)

        if carrier_name == "GLS":
            return {
                "name": "GLS", "code": "GLS",
                "url": "https://gls-group.com/",
                "tracking_url_template": "https://gls-group.com/GR/EN/tracking?match={tracking_number}",
            }
        return {
            "name": "Colissimo", "code": "COLISSIMO",
            "url": "https://www.laposte.fr/particulier/outils/suivre-vos-envois",
            "tracking_url_template": "https://www.laposte.fr/particulier/outils/suivre-vos-envois?code={tracking_number}",
        }

    def get_carrier_for_order(self, order_id: str) -> Dict[str, Any]:
        order = self.fetch_single_order(order_id)
        if not order:
            return {
                "name": "Colissimo", "code": "COLISSIMO",
                "url": "https://www.laposte.fr/particulier/outils/suivre-vos-envois",
                "tracking_url_template": "https://www.laposte.fr/particulier/outils/suivre-vos-envois?code={tracking_number}",
            }
        return self.detect_carrier_by_destination(order)

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    async def get_available_srps(self, days_back: int = 7) -> List[str]:
        """Collect unique SRP values from recent orders."""
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        orders = self.fetch_orders(start_date, end_date)
        srps = sorted({self.extract_carrier_manager(o) for o in orders if self.extract_carrier_manager(o)})
        logger.info("Available SRPs: %s", ", ".join(srps) or "none")
        return srps

    # ------------------------------------------------------------------
    # Private static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_address(addr: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "civility": addr.get("civility", ""),
            "firstname": addr.get("firstname", ""),
            "lastname": addr.get("lastname", ""),
            "company": addr.get("company", ""),
            "company_2": addr.get("company_2", ""),
            "street_1": addr.get("street_1", ""),
            "street_2": addr.get("street_2", ""),
            "zip_code": addr.get("zip_code", ""),
            "city": addr.get("city", ""),
            "state": addr.get("state", ""),
            "country": addr.get("country", ""),
            "country_iso_code": addr.get("country_iso_code", ""),
            "phone": addr.get("phone", ""),
            "additional_info": addr.get("additional_info", ""),
        }

    @staticmethod
    def _extract_field(order: Dict, code: str) -> str:
        for field in order.get("order_additional_fields", []):
            if field.get("code") == code:
                return field.get("value", "")
        return ""

    @staticmethod
    def _extract_line_field(line: Dict, code: str) -> str:
        for field in line.get("order_line_additional_fields", []):
            if field.get("code") == code:
                return field.get("value", "")
        return ""

    @staticmethod
    def _extract_price(price_data: Any) -> float:
        if isinstance(price_data, dict):
            return float(price_data.get("amount", 0))
        return float(price_data) if price_data else 0.0


mirakl_order_service = MiraklOrderService()
