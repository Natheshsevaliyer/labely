import base64
import json
import logging
import os
from time import time
from typing import Any, Dict

import requests

from app.core.config import settings
from app.core.exceptions import SRPServiceException
from app.core.http_client import sync_http_client

logger = logging.getLogger(__name__)

class SRPService:
    """SRP Label Generation Service"""

    def __init__(self):
        self.base_url = settings.SRP_ENDPOINT_URI
        self.username = settings.SRP_USERNAME
        self.client_id = settings.SRP_CLIENT_ID
        self.password = settings.SRP_PASSWORD
        self.token = None
        self.token_expiry = None

    def is_alive(self) -> bool:
        """Check if SRP service is alive"""
        url = f"{self.base_url}{settings.SRP_ISALIVE_URI}"
        try:
            response = sync_http_client.get(url)
            response.raise_for_status()
            return response.text.strip().lower() == "true"
        except Exception as e:
            logger.error(f"SRP service check failed: {e}")
            return False

    def generate_token(self) -> str:
        """Generate access token for SRP API"""
        url = f"{self.base_url}{settings.SRP_GETTOKEN_URI}"

        payload = (
            f"grant_type=password"
            f"&client_id={self.client_id}"
            f"&username={self.username}"
            f"&password={self.password}"
        )

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }

        try:
            response = requests.post(url, headers=headers, data=payload, timeout=15)
            response.raise_for_status()
            token_data = response.json()
            self.token = token_data["access_token"]
            return self.token
        except requests.exceptions.ConnectionError as e:
            logger.error(f"SRP connection failed: {e}")
            raise SRPServiceException("Cannot connect to SRP service", details=str(e))
        except requests.exceptions.Timeout as e:
            logger.error(f"SRP timeout: {e}")
            raise SRPServiceException("SRP service timeout", details=str(e))
        except Exception as e:
            logger.error(f"Token generation failed: {e}")
            raise SRPServiceException("Failed to generate SRP token", details=str(e))

    def generate_label(self, order_number: str, reference_source: str = "SRP") -> Dict[str, Any]:
        """Generate label for an order with retry logic"""
        max_retries = 3
        retry_delay = 1

        token = self.generate_token()
        url = f"{self.base_url}{settings.SRP_CREATELABEL_URI}"

        reference_id = ''.join(filter(str.isdigit, order_number))

        payload = {
            "referenceId": reference_id,
            "referenceSource": reference_source,
            "mode": "Shipping"
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        for attempt in range(max_retries):
            try:
                logger.info(f"Generating label for order: {order_number} (attempt {attempt+1})")
                response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=20)
                response.raise_for_status()

                data = response.json()
                label_data = data.get("data", {})

                return {
                    "success": True,
                    "order_number": order_number,
                    "tracking_number": label_data.get("trackingNumber"),
                    "label": label_data.get("label"),
                    "reference_id": label_data.get("referenceId")
                }
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                return {
                    "success": False,
                    "order_number": order_number,
                    "error": "Timeout after multiple retries"
                }
            except Exception as e:
                if attempt < max_retries - 1 and "connection" in str(e).lower():
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                logger.error(f"Label generation failed for {order_number}: {e}")
                return {
                    "success": False,
                    "order_number": order_number,
                    "error": str(e)
                }

        return {
            "success": False,
            "order_number": order_number,
            "error": "Max retries exceeded"
        }

    def save_label_to_file(self, order_number: str, label_data: str, process_id: int = None,
                          output_dir: str = None) -> str:
        """Save base64 encoded label to PDF file"""
        if output_dir is None:
            output_dir = settings.OUTPUT_FOLDER

        os.makedirs(output_dir, exist_ok=True)

        try:
            pdf_bytes = base64.b64decode(label_data)

            if process_id:
                pdf_filename = f"{order_number}_{process_id}.pdf"
            else:
                pdf_filename = f"{order_number}.pdf"

            pdf_path = os.path.join(output_dir, pdf_filename)

            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)

            logger.info(f"Saved label to {pdf_path}")
            return pdf_path
        except Exception as e:
            logger.error(f"Failed to save label: {e}")
            raise

srp_service = SRPService()
