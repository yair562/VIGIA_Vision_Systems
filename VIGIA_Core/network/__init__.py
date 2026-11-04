"""
VIGIA_Core.network
==================
Módulo de diagnóstico y autodescubrimiento de red local (LAN/Wi-Fi/Ethernet)
para VIGÍA Vision Systems.

Independiente de frameworks web (sin dependencias de Flask ni Werkzeug).
"""

from .lan_detector import (
    NetworkDiscoveryError,
    NoLanAddressError,
    discover_all_lan_candidates,
    discover_lan_ipv4,
    discover_wifi_ipv4,
    get_default_route_ip,
    get_lan_diagnostic_report,
    get_local_ipv4_addresses,
    get_windows_wlan_interfaces,
    is_usable_ipv4,
    resolve_access_urls,
    validate_public_base_url,
)

__all__ = [
    "NetworkDiscoveryError",
    "NoLanAddressError",
    "discover_all_lan_candidates",
    "discover_lan_ipv4",
    "discover_wifi_ipv4",
    "get_default_route_ip",
    "get_lan_diagnostic_report",
    "get_local_ipv4_addresses",
    "get_windows_wlan_interfaces",
    "is_usable_ipv4",
    "resolve_access_urls",
    "validate_public_base_url",
]
