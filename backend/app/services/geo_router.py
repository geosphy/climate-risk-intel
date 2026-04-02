"""
Geographic region detection for routing to correct data services.
Determines whether an address is in the US, Europe, or elsewhere.
"""

# European country codes (ISO 3166-1 alpha-2)
EUROPEAN_COUNTRY_CODES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
    "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
    "PL", "PT", "RO", "SK", "SI", "ES", "SE",  # EU member states
    "GB", "CH", "NO", "IS", "AL", "BA", "ME", "MK", "RS", "XK",  # Non-EU Europe
    "MD", "UA", "BY", "GE", "AM", "AZ",  # Eastern Europe
    "TR",  # Turkey
}

US_COUNTRY_CODES = {"US", "USA"}


def is_european(country_code: str) -> bool:
    """Return True if the country code is a European country."""
    return country_code.upper() in EUROPEAN_COUNTRY_CODES


def is_us(country_code: str) -> bool:
    """Return True if the country code is the United States."""
    return country_code.upper() in US_COUNTRY_CODES


def get_region(country_code: str) -> str:
    """
    Return the region for a given country code.
    Returns: "US", "EUROPE", or "GLOBAL"
    """
    code = country_code.upper()
    if code in US_COUNTRY_CODES:
        return "US"
    elif code in EUROPEAN_COUNTRY_CODES:
        return "EUROPE"
    else:
        return "GLOBAL"


def get_data_sources_for_region(region: str) -> list[str]:
    """Return the list of data source names used for a given region."""
    if region == "US":
        return ["OpenStreetMap Nominatim", "FEMA National Flood Hazard Layer",
                "NOAA Climate Data Online", "World Bank Climate Change Knowledge Portal"]
    elif region == "EUROPE":
        return ["OpenStreetMap Nominatim", "JRC Global Surface Water",
                "Open-Meteo / Copernicus ERA5", "World Bank Climate Change Knowledge Portal"]
    else:
        return ["OpenStreetMap Nominatim", "World Bank Climate Change Knowledge Portal",
                "Open-Meteo Historical Weather"]
