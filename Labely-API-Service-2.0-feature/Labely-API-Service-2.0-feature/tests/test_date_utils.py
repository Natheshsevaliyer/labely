"""Unit tests for app/utils/date_utils.py"""
import pytest
from datetime import datetime

from app.utils.date_utils import parse_date, format_date, get_date_range, get_month_range


class TestParseDate:
    def test_valid_date(self):
        result = parse_date("2024-01-15")
        assert result == datetime(2024, 1, 15)

    def test_invalid_date_returns_none(self):
        assert parse_date("not-a-date") is None
        assert parse_date("2024/01/15") is None
        assert parse_date("") is None

    def test_boundary_dates(self):
        assert parse_date("2024-02-29") == datetime(2024, 2, 29)  # leap year
        assert parse_date("2023-02-29") is None  # not a leap year


class TestFormatDate:
    def test_default_format(self):
        dt = datetime(2024, 3, 7)
        assert format_date(dt) == "2024-03-07"

    def test_custom_format(self):
        dt = datetime(2024, 12, 31)
        assert format_date(dt, "%d/%m/%Y") == "31/12/2024"

    def test_single_digit_padding(self):
        dt = datetime(2024, 1, 5)
        assert format_date(dt) == "2024-01-05"


class TestGetDateRange:
    def test_returns_two_strings(self):
        start, end = get_date_range(7)
        assert isinstance(start, str)
        assert isinstance(end, str)

    def test_start_before_end(self):
        start, end = get_date_range(30)
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        assert start_dt < end_dt

    def test_zero_days(self):
        start, end = get_date_range(0)
        # Same day
        assert start == end


class TestGetMonthRange:
    def test_regular_month(self):
        start, end = get_month_range(2024, 3)
        assert start == datetime(2024, 3, 1)
        assert end == datetime(2024, 4, 1)

    def test_december_wraps_to_january(self):
        start, end = get_month_range(2024, 12)
        assert start == datetime(2024, 12, 1)
        assert end == datetime(2025, 1, 1)

    def test_february_non_leap(self):
        start, end = get_month_range(2023, 2)
        assert start == datetime(2023, 2, 1)
        assert end == datetime(2023, 3, 1)
