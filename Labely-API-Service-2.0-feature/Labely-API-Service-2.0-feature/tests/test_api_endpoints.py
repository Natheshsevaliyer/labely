"""Integration tests for /api/v1/orders/*, /api/v1/tracking/*, /api/v1/shipment/* endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Orders ────────────────────────────────────────────────────────────────────

class TestGenerateLabelsEndpoint:
    def test_generate_by_quantity(self, authed_client):
        with patch("app.services.order_service.OrderService.generate_labels", new_callable=AsyncMock) as m:
            m.return_value = {
                "success": True,
                "message": "Processing",
                "process_id": 1,
                "download_url": None,
                "total_orders": 5,
                "successful": 0,
                "failed": 0,
                "request_method": "quantity",
                "requested_srp": "SRP",
                "requested_quantity": 5,
                "requested_start_date": None,
                "requested_end_date": None,
            }
            resp = authed_client.post("/api/v1/orders/generate-labels", json={"srp": "SRP", "quantity": 5})
            assert resp.status_code == 200
            assert resp.json()["data"]["process_id"] == 1

    def test_generate_by_date_range(self, authed_client):
        with patch("app.services.order_service.OrderService.generate_labels", new_callable=AsyncMock) as m:
            m.return_value = {
                "success": True,
                "message": "ok",
                "process_id": 2,
                "download_url": None,
                "total_orders": 3,
                "successful": 0,
                "failed": 0,
                "request_method": "date_range",
                "requested_srp": "SRP",
                "requested_quantity": None,
                "requested_start_date": "2024-01-01",
                "requested_end_date": "2024-01-31",
            }
            resp = authed_client.post(
                "/api/v1/orders/generate-labels",
                json={"srp": "SRP", "start_date": "2024-01-01", "end_date": "2024-01-31"},
            )
            assert resp.status_code == 200

    def test_generate_requires_auth(self, client):
        resp = client.post("/api/v1/orders/generate-labels", json={"srp": "SRP", "quantity": 5})
        assert resp.status_code == 401

    def test_generate_missing_srp(self, authed_client):
        resp = authed_client.post("/api/v1/orders/generate-labels", json={"quantity": 5})
        assert resp.status_code == 422

    def test_generate_no_method_422(self, authed_client):
        resp = authed_client.post("/api/v1/orders/generate-labels", json={"srp": "SRP"})
        assert resp.status_code == 422


class TestProcessStatusEndpoint:
    def test_get_status_success(self, authed_client):
        with patch("app.services.order_service.OrderService.get_process_status", new_callable=AsyncMock) as m:
            m.return_value = {
                "process_id": 1,
                "status": "Completed",
                "total": 5,
                "successful": 5,
                "failed": 0,
                "download_url": None,
                "labels_only_url": None,
                "report_url": None,
                "created_at": None,
                "completed_at": None,
                "srp": "SRP",
                "request_method": "quantity",
                "requested_quantity": 5,
                "requested_start_date": None,
                "requested_end_date": None,
            }
            resp = authed_client.get("/api/v1/orders/process/1/status")
            assert resp.status_code == 200
            assert resp.json()["data"]["status"] == "Completed"

    def test_get_status_requires_auth(self, client):
        resp = client.get("/api/v1/orders/process/1/status")
        assert resp.status_code == 401


class TestAvailableSRPs:
    def test_get_srps(self, authed_client):
        with patch(
            "app.services.mirakl.order_service.mirakl_order_service.get_available_srps",
            new_callable=AsyncMock,
        ) as m:
            m.return_value = ["SRP", "SRP_COLISSIMO"]
            resp = authed_client.get("/api/v1/orders/available-srps")
            assert resp.status_code == 200
            assert "srps" in resp.json()["data"]


class TestMiraklOrdersStatus:
    def test_missing_srp_param(self, authed_client):
        resp = authed_client.get("/api/v1/orders/mirakl-orders-status")
        assert resp.status_code == 422

    def test_with_srp_param(self, authed_client):
        with patch("app.services.order_service.OrderService.get_mirakl_orders_with_status", new_callable=AsyncMock) as m:
            m.return_value = {"items": [], "total": 0, "page": 1, "limit": 50, "pages": 0}
            resp = authed_client.get("/api/v1/orders/mirakl-orders-status?srp=SRP")
            assert resp.status_code == 200


# ── Tracking ─────────────────────────────────────────────────────────────────

class TestTrackingEndpoints:
    def test_get_ready_orders(self, authed_client):
        with patch("app.services.tracking_service.TrackingService.get_ready_orders", new_callable=AsyncMock) as m:
            m.return_value = {"items": [], "total": 0, "page": 1, "limit": 50}
            resp = authed_client.get("/api/v1/tracking/ready-orders")
            assert resp.status_code == 200

    def test_ready_orders_requires_auth(self, client):
        resp = client.get("/api/v1/tracking/ready-orders")
        assert resp.status_code == 401

    def test_bulk_update(self, authed_client):
        with patch("app.services.tracking_service.TrackingService.bulk_update", new_callable=AsyncMock) as m:
            m.return_value = {"message": "Done", "total_processed": 2, "successful": 2, "failed": 0}
            resp = authed_client.post(
                "/api/v1/tracking/bulk-update",
                json={"order_ids": ["ORD-001", "ORD-002"], "force_update": False},
            )
            assert resp.status_code == 200

    def test_get_batches(self, authed_client):
        with patch("app.api.v1.endpoints.tracking.TrackingService") as MockSvc:
            MockSvc.return_value.get_batches.return_value = {"items": [], "total": 0}
            resp = authed_client.get("/api/v1/tracking/batches")
            assert resp.status_code == 200

    def test_batch_not_found(self, authed_client):
        with patch("app.api.v1.endpoints.tracking.TrackingService") as MockSvc:
            MockSvc.return_value.get_batch_status.return_value = None
            resp = authed_client.get("/api/v1/tracking/batch/nonexistent-id/status")
            assert resp.status_code == 404


# ── Shipment ─────────────────────────────────────────────────────────────────

class TestShipmentEndpoints:
    def test_get_ready_shipments(self, authed_client):
        with patch("app.services.shipment_service.ShipmentService.get_ready_shipments", new_callable=AsyncMock) as m:
            m.return_value = {"items": [], "total": 0, "page": 1, "limit": 50}
            resp = authed_client.get("/api/v1/shipment/ready-orders")
            assert resp.status_code == 200

    def test_confirm_shipments(self, authed_client):
        with patch("app.services.shipment_service.ShipmentService.confirm_shipments", new_callable=AsyncMock) as m:
            m.return_value = {"confirmed": 2, "failed": 0, "total": 2}
            resp = authed_client.post(
                "/api/v1/shipment/confirm",
                json={"order_ids": ["ORD-001"], "validate_only": False, "force_confirm": False},
            )
            assert resp.status_code == 200

    def test_validate_shipments(self, authed_client):
        with patch("app.api.v1.endpoints.shipment.ShipmentService") as MockSvc:
            MockSvc.return_value._validate_orders = AsyncMock(return_value={"items": []})
            MockSvc.return_value.validate_shipments = AsyncMock(return_value={"items": []})
            resp = authed_client.post(
                "/api/v1/shipment/validate",
                json={"order_ids": ["ORD-001"], "force_confirm": False},
            )
            assert resp.status_code == 200

    def test_batch_not_found(self, authed_client):
        with patch("app.services.shipment_service.ShipmentService.get_batch_status") as m:
            m.return_value = None
            resp = authed_client.get("/api/v1/shipment/batch/bad-id/status")
            assert resp.status_code == 404

    def test_shipment_history(self, authed_client):
        with patch("app.services.shipment_service.ShipmentService.get_history") as m:
            m.return_value = {"items": [], "total": 0}
            resp = authed_client.get("/api/v1/shipment/history")
            assert resp.status_code == 200

    def test_ready_shipments_requires_auth(self, client):
        resp = client.get("/api/v1/shipment/ready-orders")
        assert resp.status_code == 401
