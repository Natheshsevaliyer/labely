"""Base Mirakl service."""
import logging
from typing import Any, Dict, Optional

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

class BaseMiraklService:
    """Base class for Mirakl API services."""

    def __init__(self):
        self.base_url = settings.MIRAKL_BASE_URL
        self.api_key = settings.MIRAKL_API_KEY
        self.shop_id = settings.MIRAKL_SHOP_ID
        self.headers = {
            "Authorization": self.api_key,
            "Accept": "application/json"
        }

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Make HTTP request to Mirakl API."""
        url = f"{self.base_url}{endpoint}"
        params = kwargs.get('params', {})
        params['shop_id'] = self.shop_id

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                params=params,
                json=kwargs.get('json'),
                timeout=kwargs.get('timeout', 30)
            )
            response.raise_for_status()
            return response.json() if response.content else None
        except Exception as e:
            logger.error(f"Mirakl API error: {e}")
            raise
