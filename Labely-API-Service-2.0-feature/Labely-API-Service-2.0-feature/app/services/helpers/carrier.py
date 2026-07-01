"""Carrier-detection helpers shared by order_service and mirakl order_service."""
from typing import Any, Dict

# French overseas territories → always Colissimo
FRENCH_OVERSEAS = frozenset([
    "GP", "MQ", "GF", "RE", "YT", "PF", "NC", "WF", "BL", "MF", "PM"
])

# GLS supported countries (ISO-2)
GLS_COUNTRIES = frozenset([
    "DE", "AT", "CH", "NL", "BE", "LU", "PL", "CZ", "SK", "HU",
    "SI", "HR", "RO", "BG", "EE", "LV", "LT", "DK", "SE", "FI",
    "IE", "GB", "PT", "ES", "IT",
])

# Country name → ISO-2
_COUNTRY_NAME_MAP: Dict[str, str] = {
    "FRANCE": "FR",
    "GERMANY": "DE",
    "ALLEMAGNE": "DE",
    "SPAIN": "ES",
    "ESPAGNE": "ES",
    "ITALY": "IT",
    "ITALIE": "IT",
    "UNITED STATES": "US",
    "USA": "US",
    "UNITED KINGDOM": "GB",
    "UK": "GB",
}

# ISO-3 → ISO-2 (MAIN FIX)
ISO3_TO_ISO2: Dict[str, str] = {
    "FRA": "FR",
    "ESP": "ES",
    "DEU": "DE",
    "ITA": "IT",
    "GBR": "GB",
    "PRT": "PT",
    "NLD": "NL",
    "BEL": "BE",
    "CHE": "CH",
    "AUT": "AT",
    "IRL": "IE",
    "DNK": "DK",
    "SWE": "SE",
    "FIN": "FI",
    "POL": "PL",
    "CZE": "CZ",
    "SVK": "SK",
    "HUN": "HU",
    "SVN": "SI",
    "HRV": "HR",
    "ROU": "RO",
    "BGR": "BG",
    "EST": "EE",
    "LVA": "LV",
    "LTU": "LT",
}

CARRIER_COLISSIMO = "Colissimo"
CARRIER_GLS = "GLS"


def resolve_country_code(address: Dict[str, Any]) -> str:
    """
    Return ISO-3166-1 alpha-2 country code.
    Handles both ISO-2 and ISO-3 inputs.
    """
    code = address.get("country_iso_code", "").upper()

    # Convert ISO-3 → ISO-2
    if len(code) == 3:
        code = ISO3_TO_ISO2.get(code, "")

    if code:
        return code

    # fallback using country name
    name = address.get("country", "").upper()
    return _COUNTRY_NAME_MAP.get(name, "")


def detect_carrier_from_address(address: Dict[str, Any]) -> str:
    """
    Determine carrier:
    - France → Colissimo
    - French overseas → Colissimo
    - Europe (GLS countries) → GLS
    - Others → Colissimo
    """
    code = resolve_country_code(address)

    # France itself
    if code == "FR":
        return CARRIER_COLISSIMO

    # French overseas
    if code in FRENCH_OVERSEAS:
        return CARRIER_COLISSIMO

    # GLS Europe
    if code in GLS_COUNTRIES:
        return CARRIER_GLS

    # Default
    return CARRIER_GLS
