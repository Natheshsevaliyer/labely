"""Unit tests for app/services/helpers/pagination.py"""
import pytest

from app.services.helpers.pagination import build_page_response


class TestBuildPageResponse:
    def test_basic_structure(self):
        items = [{"id": 1}, {"id": 2}]
        result = build_page_response(items, total=10, page=1, limit=5)
        assert result["items"] == items
        assert result["total"] == 10
        assert result["page"] == 1
        assert result["limit"] == 5

    def test_pages_calculation(self):
        result = build_page_response([], total=23, page=1, limit=10)
        assert result["pages"] == 3

    def test_exact_division_pages(self):
        result = build_page_response([], total=20, page=1, limit=10)
        assert result["pages"] == 2

    def test_zero_total(self):
        result = build_page_response([], total=0, page=1, limit=10)
        assert result["pages"] == 0
        assert result["has_next"] is False
        assert result["has_previous"] is False

    def test_has_next_true(self):
        result = build_page_response([], total=20, page=1, limit=10)
        assert result["has_next"] is True

    def test_has_next_false_on_last_page(self):
        result = build_page_response([], total=20, page=2, limit=10)
        assert result["has_next"] is False

    def test_has_previous_false_on_first_page(self):
        result = build_page_response([], total=20, page=1, limit=10)
        assert result["has_previous"] is False

    def test_has_previous_true_on_second_page(self):
        result = build_page_response([], total=20, page=2, limit=10)
        assert result["has_previous"] is True

    def test_extra_fields_merged(self):
        result = build_page_response([], total=5, page=1, limit=5, extra={"carrier": "GLS"})
        assert result["carrier"] == "GLS"

    def test_single_item_single_page(self):
        result = build_page_response([{"id": 1}], total=1, page=1, limit=10)
        assert result["pages"] == 1
        assert result["has_next"] is False
        assert result["has_previous"] is False
