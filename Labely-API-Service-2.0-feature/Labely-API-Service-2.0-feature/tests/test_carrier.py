"""Unit tests for app/services/helpers/carrier.py"""
import pytest

from app.services.helpers.carrier import (
    resolve_country_code,
    detect_carrier_from_address,
    CARRIER_COLISSIMO,
    CARRIER_GLS,
    FRENCH_OVERSEAS,
    GLS_COUNTRIES,
)


class TestResolveCountryCode:
    def test_iso_code_takes_priority(self):
        addr = {"country_iso_code": "fr", "country": "FRANCE"}
        assert resolve_country_code(addr) == "FR"

    def test_country_name_fallback(self):
        addr = {"country": "GERMANY"}
        assert resolve_country_code(addr) == "DE"

    def test_alias_uk(self):
        addr = {"country": "UNITED KINGDOM"}
        assert resolve_country_code(addr) == "GB"

    def test_alias_usa(self):
        addr = {"country": "USA"}
        assert resolve_country_code(addr) == "US"

    def test_unknown_country_returns_empty(self):
        addr = {"country": "NARNIA"}
        assert resolve_country_code(addr) == ""

    def test_empty_address(self):
        assert resolve_country_code({}) == ""

    def test_iso_code_uppercased(self):
        addr = {"country_iso_code": "de"}
        assert resolve_country_code(addr) == "DE"


class TestDetectCarrier:
    @pytest.mark.parametrize("country_code", list(GLS_COUNTRIES))
    def test_gls_countries_return_gls(self, country_code):
        addr = {"country_iso_code": country_code}
        assert detect_carrier_from_address(addr) == CARRIER_GLS

    @pytest.mark.parametrize("country_code", list(FRENCH_OVERSEAS))
    def test_french_overseas_returns_colissimo(self, country_code):
        addr = {"country_iso_code": country_code}
        assert detect_carrier_from_address(addr) == CARRIER_COLISSIMO

    def test_unknown_country_defaults_to_colissimo(self):
        addr = {"country_iso_code": "XX"}
        assert detect_carrier_from_address(addr) == CARRIER_COLISSIMO

    def test_france_mainland_uses_colissimo(self):
        """FR is not in GLS_COUNTRIES, so Colissimo applies."""
        addr = {"country_iso_code": "FR"}
        assert detect_carrier_from_address(addr) == CARRIER_COLISSIMO

    def test_reunion_island_colissimo(self):
        """Réunion (RE) is a French overseas territory → Colissimo."""
        addr = {"country_iso_code": "RE"}
        assert detect_carrier_from_address(addr) == CARRIER_COLISSIMO

    def test_germany_gls(self):
        addr = {"country_iso_code": "DE"}
        assert detect_carrier_from_address(addr) == CARRIER_GLS

    def test_empty_address_defaults_to_colissimo(self):
        assert detect_carrier_from_address({}) == CARRIER_COLISSIMO
