# app/services/srp/async_srp_service.py
import asyncio
import base64
import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class AsyncSRPService:
    """Async SRP Label Generation Service.

    Key design decisions
    --------------------
    * A **single token** is fetched once at the start of every batch.
      It is reused for every label request – no per-batch or per-order
      token calls.
    * All orders are dispatched **concurrently** (bounded by a semaphore)
      in a single pass – there is no outer batch loop.
    * ``generate_labels_stream`` is an async-generator that yields each
      result as soon as it arrives so the caller can stream SSE progress
      updates without waiting for the whole set to finish.
    """

    def __init__(
        self,
        max_concurrent: int = 100,
        request_timeout: int = 60,
        max_retries: int = 2,
    ):
        self.base_url = settings.SRP_ENDPOINT_URI
        self.username = settings.SRP_USERNAME
        self.client_id = settings.SRP_CLIENT_ID
        self.password = settings.SRP_PASSWORD
        self.max_concurrent = max_concurrent
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.token_url = f"{self.base_url}{settings.SRP_GETTOKEN_URI}"
        self.label_url = f"{self.base_url}{settings.SRP_CREATELABEL_URI}"

    # ------------------------------------------------------------------
    # Token (called ONCE per batch)
    # ------------------------------------------------------------------

    async def generate_token(self, client: httpx.AsyncClient) -> str:
        """Fetch a fresh access token.  Called exactly once per batch."""
        payload = {
            "grant_type": "password",
            "client_id": self.client_id,
            "username": self.username,
            "password": self.password,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        try:
            logger.info("Fetching SRP token (once for this batch)")
            response = await client.post(
                self.token_url, headers=headers, data=payload, timeout=15
            )
            response.raise_for_status()
            token_data = response.json()
            logger.info("SRP token obtained successfully")
            return token_data["access_token"]
        except httpx.TimeoutException:
            logger.error("SRP token request timed out")
            raise Exception("SRP token generation timeout")
        except Exception as exc:
            logger.error("SRP token generation failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Single label (uses the shared token, no token call inside)
    # ------------------------------------------------------------------

    async def _generate_label_with_retry(
        self,
        client: httpx.AsyncClient,
        order_number: str,
        token: str,
        reference_source: str = "SRP",
    ) -> Dict[str, Any]:
        """Generate one label using the provided token.  Retries on
        transient errors but never re-fetches the token."""

        for attempt in range(self.max_retries + 1):
            try:
                reference_id = "".join(filter(str.isdigit, order_number))
                payload = {
                    "referenceId": reference_id,
                    "referenceSource": reference_source,
                    "mode": "Shipping",
                }
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }

                response = await client.post(
                    self.label_url,
                    headers=headers,
                    json=payload,
                    timeout=self.request_timeout,
                )
                response.raise_for_status()

                data = response.json()
                label_data = data.get("data", {})
                label_string = label_data.get("label")
                tracking_number = label_data.get("trackingNumber")

                if not label_string or not tracking_number:
                    logger.warning(
                        "SRP incomplete data for %s – label=%s tracking=%s",
                        order_number,
                        bool(label_string),
                        bool(tracking_number),
                    )
                    return {
                        "success": False,
                        "order_number": order_number,
                        "error": (
                            f"SRP returned incomplete data – "
                            f"label: {'present' if label_string else 'MISSING'}, "
                            f"tracking: {'present' if tracking_number else 'MISSING'}"
                        ),
                        "tracking_number": None,
                        "label": None,
                        "attempt": attempt + 1,
                    }

                return {
                    "success": True,
                    "order_number": order_number,
                    "tracking_number": tracking_number,
                    "label": label_string,
                    "reference_id": label_data.get("referenceId"),
                    "attempt": attempt + 1,
                }

            except httpx.TimeoutException:
                if attempt < self.max_retries:
                    wait = (attempt + 1) * 2
                    logger.warning(
                        "Timeout for %s – retry %d/%d in %ds",
                        order_number, attempt + 1, self.max_retries, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "Timeout for %s after %d attempts",
                        order_number, self.max_retries + 1,
                    )
                    return {
                        "success": False,
                        "order_number": order_number,
                        "error": f"Request timeout after {self.max_retries + 1} attempts",
                        "tracking_number": None,
                        "label": None,
                        "attempt": attempt + 1,
                    }

            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    if attempt < self.max_retries:
                        wait = (attempt + 1) * 5
                        logger.warning(
                            "Rate-limited for %s – retry in %ds", order_number, wait
                        )
                        await asyncio.sleep(wait)
                    else:
                        return {
                            "success": False,
                            "order_number": order_number,
                            "error": f"Rate-limited after {self.max_retries + 1} attempts",
                            "tracking_number": None,
                            "label": None,
                        }
                else:
                    logger.error(
                        "HTTP %d for %s", exc.response.status_code, order_number
                    )
                    return {
                        "success": False,
                        "order_number": order_number,
                        "error": f"HTTP {exc.response.status_code}",
                        "tracking_number": None,
                        "label": None,
                    }

            except Exception as exc:
                if attempt < self.max_retries:
                    wait = (attempt + 1) * 2
                    logger.warning(
                        "Error for %s: %s – retry %d/%d in %ds",
                        order_number, exc, attempt + 1, self.max_retries, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "Failed for %s after %d attempts: %s",
                        order_number, self.max_retries + 1, exc,
                    )
                    return {
                        "success": False,
                        "order_number": order_number,
                        "error": str(exc),
                        "tracking_number": None,
                        "label": None,
                    }

    # ------------------------------------------------------------------
    # Streaming generator – yields results as they arrive
    # ------------------------------------------------------------------

    async def generate_labels_stream(
        self,
        order_numbers: List[str],
        reference_source: str = "SRP",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Async generator: fetch ONE token, dispatch ALL orders concurrently,
        yield each result as soon as it completes.

        Usage::

            async for result in srp_service.generate_labels_stream(order_ids):
                # stream progress to the client immediately
                await handle_result(result)
        """
        if not order_numbers:
            return

        total = len(order_numbers)
        logger.info(
            "generate_labels_stream: %d orders | max_concurrent=%d | timeout=%ds | retries=%d",
            total, self.max_concurrent, self.request_timeout, self.max_retries,
        )

        semaphore = asyncio.Semaphore(self.max_concurrent)
        limits = httpx.Limits(
            max_keepalive_connections=self.max_concurrent,
            max_connections=self.max_concurrent + 20,
            keepalive_expiry=60,
        )
        timeout = httpx.Timeout(
            connect=10.0,
            read=self.request_timeout,
            write=self.request_timeout,
            pool=60.0,
        )

        # Queue that tasks drop results into as they finish
        result_queue: asyncio.Queue = asyncio.Queue()

        async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
            # ── Single token fetch ──────────────────────────────────────
            try:
                token = await self.generate_token(client)
            except Exception as exc:
                # If we cannot even get a token, yield failure for every order
                logger.error("Cannot obtain SRP token: %s", exc)
                for oid in order_numbers:
                    yield {
                        "success": False,
                        "order_number": oid,
                        "error": f"Token generation failed: {exc}",
                        "tracking_number": None,
                        "label": None,
                    }
                return

            # ── Dispatch all orders concurrently ────────────────────────
            async def _worker(order_id: str) -> None:
                async with semaphore:
                    result = await self._generate_label_with_retry(
                        client, order_id, token, reference_source
                    )
                await result_queue.put(result)

            # Fire all tasks at once (semaphore limits true concurrency)
            tasks = [asyncio.create_task(_worker(oid)) for oid in order_numbers]

            # ── Yield results as they land ──────────────────────────────
            completed = 0
            while completed < total:
                result = await result_queue.get()
                completed += 1
                yield result

            # Ensure all tasks are fully done (they should be by now)
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("generate_labels_stream: finished %d orders", total)

    # ------------------------------------------------------------------
    # Convenience batch method (collects stream into a list)
    # ------------------------------------------------------------------

    async def generate_labels_batch(
        self,
        order_numbers: List[str],
        reference_source: str = "SRP",
    ) -> List[Dict[str, Any]]:
        """Collect all streaming results into a list.

        Use ``generate_labels_stream`` directly when you need per-result
        streaming; use this when you only need the final list.
        """
        results: List[Dict[str, Any]] = []
        async for result in self.generate_labels_stream(order_numbers, reference_source):
            results.append(result)

        success_count = sum(1 for r in results if r.get("success"))
        logger.info(
            "generate_labels_batch: %d/%d succeeded", success_count, len(order_numbers)
        )
        return results

    # ------------------------------------------------------------------
    # File helpers (unchanged)
    # ------------------------------------------------------------------

    async def save_label_to_file(
        self,
        order_number: str,
        label_data: str,
        process_id: int = None,
        output_dir: str = None,
    ) -> Optional[str]:
        """Save a base64-encoded label to a PDF file (async wrapper)."""
        if output_dir is None:
            output_dir = settings.OUTPUT_FOLDER

        os.makedirs(output_dir, exist_ok=True)
        loop = asyncio.get_event_loop()

        def _save():
            try:
                pdf_bytes = base64.b64decode(label_data)
                pdf_filename = (
                    f"{order_number}_{process_id}.pdf" if process_id else f"{order_number}.pdf"
                )
                pdf_path = os.path.join(output_dir, pdf_filename)
                with open(pdf_path, "wb") as fh:
                    fh.write(pdf_bytes)
                logger.debug("Saved label to %s", pdf_path)
                return pdf_path
            except Exception as exc:
                logger.error("Failed to save label for %s: %s", order_number, exc)
                return None

        return await loop.run_in_executor(None, _save)

    async def save_labels_batch(
        self, results: List[Dict[str, Any]], process_id: int
    ) -> Dict[str, str]:
        """Save multiple labels concurrently; returns order_id → file path."""
        logger.info("Saving %d labels to files", len(results))

        successful = [r for r in results if r.get("success") and r.get("label")]
        save_tasks = [
            self.save_label_to_file(r["order_number"], r["label"], process_id)
            for r in successful
        ]

        if not save_tasks:
            return {}

        saved_paths = await asyncio.gather(*save_tasks)
        path_map = {
            r["order_number"]: path
            for r, path in zip(successful, saved_paths)
            if path
        }
        logger.info("Saved %d labels", len(path_map))
        return path_map


# Global instance
async_srp_service = AsyncSRPService(
    max_concurrent=settings.SRP_MAX_CONCURRENT,
    request_timeout=settings.SRP_REQUEST_TIMEOUT,
    max_retries=settings.SRP_MAX_RETRIES,
)
