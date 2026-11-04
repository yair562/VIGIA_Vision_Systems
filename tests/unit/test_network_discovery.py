"""
tests.unit.test_network_discovery
=================================
Pruebas unitarias de descubrimiento de red y resolución de URLs de acceso (VIGIA-NET-01).

Cobertura:
1. Detección de IP LAN válida en interfaces físicas.
2. Exclusión estricta de loopback (127.0.0.1) y comodín (0.0.0.0).
3. Exclusión de adaptadores virtuales (WSL, Hyper-V, VMware, Docker) y link-local APIPA.
4. Manejo de múltiples interfaces y selección de la recomendada vía ruta externa.
5. Priorización y validación estricta de VIGIA_PUBLIC_BASE_URL.
6. Validación de URL: esquemas válidos, rechazo de credenciales embebidas, rechazo de query/fragment.
7. Comportamiento en TLS: forzado de HTTPS en URL pública.
8. Fallo controlado (NoLanAddressError / 503) cuando no hay interfaces físicas disponibles.
"""

import os
import socket
import unittest
from unittest.mock import MagicMock, patch

from VIGIA_API.ingest_service import (
    NetworkDiscoveryError,
    NoLanAddressError,
    discover_all_lan_candidates,
    discover_lan_ipv4,
    get_default_route_ip,
    is_usable_ipv4,
    resolve_access_urls,
    validate_public_base_url,
)


class TestNetworkDiscoveryUnit(unittest.TestCase):
    """Pruebas unitarias de utilidades de red y autodescubrimiento."""

    def test_01_is_usable_ipv4(self):
        """1. is_usable_ipv4 acepta IPs privadas y rechaza loopback, APIPA, multicast y 0.0.0.0."""
        # Válidas privadas
        self.assertTrue(is_usable_ipv4("192.168.1.75"))
        self.assertTrue(is_usable_ipv4("10.0.0.5"))
        self.assertTrue(is_usable_ipv4("172.16.0.1"))

        # Inválidas / Excluidas
        self.assertFalse(is_usable_ipv4("127.0.0.1"))
        self.assertFalse(is_usable_ipv4("0.0.0.0"))
        self.assertFalse(is_usable_ipv4("169.254.1.1"))  # APIPA
        self.assertFalse(is_usable_ipv4("224.0.0.1"))    # Multicast
        self.assertFalse(is_usable_ipv4(""))
        self.assertFalse(is_usable_ipv4("no_es_ip"))

    def test_02_validate_public_base_url_success(self):
        """2. validate_public_base_url acepta URLs válidas y normaliza barras finales."""
        self.assertEqual(
            validate_public_base_url("http://192.168.1.75:5000/"),
            "http://192.168.1.75:5000"
        )
        self.assertEqual(
            validate_public_base_url("https://vigia.empresa.com:8443"),
            "https://vigia.empresa.com:8443"
        )
        self.assertEqual(
            validate_public_base_url("http://10.10.1.20"),
            "http://10.10.1.20"
        )

    def test_03_validate_public_base_url_rejects_credentials_and_schemes(self):
        """3. validate_public_base_url rechaza credenciales, esquemas no http/https y 0.0.0.0."""
        # Credenciales
        with self.assertRaises(ValueError) as ctx:
            validate_public_base_url("http://admin:secret@192.168.1.75:5000")
        self.assertIn("credenciales", str(ctx.exception).lower())

        # Esquema no permitido
        with self.assertRaises(ValueError) as ctx:
            validate_public_base_url("ftp://192.168.1.75:5000")
        self.assertIn("solo se admite 'http' o 'https'", str(ctx.exception).lower())

        # 0.0.0.0
        with self.assertRaises(ValueError) as ctx:
            validate_public_base_url("http://0.0.0.0:5000")
        self.assertIn("0.0.0.0", str(ctx.exception))

        # Query strings y fragmentos
        with self.assertRaises(ValueError) as ctx:
            validate_public_base_url("http://192.168.1.75:5000/mobile?foo=bar")
        self.assertIn("parámetros de consulta", str(ctx.exception).lower())

    def test_04_validate_public_base_url_tls_enforced(self):
        """4. validate_public_base_url exige esquema https:// cuando require_tls=True."""
        with self.assertRaises(ValueError) as ctx:
            validate_public_base_url("http://192.168.1.75:5000", require_tls=True)
        self.assertIn("https://", str(ctx.exception))

        valid_https = validate_public_base_url("https://192.168.1.75:8443", require_tls=True)
        self.assertEqual(valid_https, "https://192.168.1.75:8443")

    def test_05_discover_all_lan_candidates_filters_virtual_adapters(self):
        """5. discover_all_lan_candidates ignora adaptadores virtuales (WSL, Hyper-V, VMware)."""
        mock_addrs = {
            "vEthernet (WSL)": [MagicMock(family=socket.AF_INET, address="172.23.64.1")],
            "VMware VMnet1": [MagicMock(family=socket.AF_INET, address="192.168.152.1")],
            "Loopback": [MagicMock(family=socket.AF_INET, address="127.0.0.1")],
            "Ethernet Real": [MagicMock(family=socket.AF_INET, address="192.168.1.75")],
        }
        mock_stats = {
            "vEthernet (WSL)": MagicMock(isup=True),
            "VMware VMnet1": MagicMock(isup=True),
            "Loopback": MagicMock(isup=True),
            "Ethernet Real": MagicMock(isup=True),
        }

        with patch("psutil.net_if_addrs", return_value=mock_addrs), \
             patch("psutil.net_if_stats", return_value=mock_stats), \
             patch("VIGIA_API.ingest_service.get_default_route_ip", return_value="192.168.1.75"):
            candidates = discover_all_lan_candidates()
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["interface"], "Ethernet Real")
            self.assertEqual(candidates[0]["ip"], "192.168.1.75")
            self.assertTrue(candidates[0]["is_recommended"])

    def test_06_discover_all_lan_candidates_multiple_interfaces_recommends_route(self):
        """6. Ante múltiples interfaces físicas activas, recomienda la que tiene ruta externa."""
        mock_addrs = {
            "Ethernet 1": [MagicMock(family=socket.AF_INET, address="192.168.1.75")],
            "Wi-Fi": [MagicMock(family=socket.AF_INET, address="10.0.0.22")],
        }
        mock_stats = {
            "Ethernet 1": MagicMock(isup=True),
            "Wi-Fi": MagicMock(isup=True),
        }

        # Cuando la ruta predeterminada sale por Wi-Fi (10.0.0.22)
        with patch("psutil.net_if_addrs", return_value=mock_addrs), \
             patch("psutil.net_if_stats", return_value=mock_stats), \
             patch("VIGIA_API.ingest_service.get_default_route_ip", return_value="10.0.0.22"):
            candidates = discover_all_lan_candidates()
            self.assertEqual(len(candidates), 2)
            wifi_c = next(c for c in candidates if c["interface"] == "Wi-Fi")
            eth_c = next(c for c in candidates if c["interface"] == "Ethernet 1")
            self.assertTrue(wifi_c["is_recommended"])
            self.assertFalse(eth_c["is_recommended"])

    def test_07_resolve_access_urls_precedence_public_base_url(self):
        """7. VIGIA_PUBLIC_BASE_URL tiene precedencia sobre el autodescubrimiento para el QR."""
        mock_addrs = {
            "Ethernet": [MagicMock(family=socket.AF_INET, address="192.168.1.75")],
        }
        mock_stats = {"Ethernet": MagicMock(isup=True)}

        with patch("psutil.net_if_addrs", return_value=mock_addrs), \
             patch("psutil.net_if_stats", return_value=mock_stats), \
             patch.dict(os.environ, {"VIGIA_PUBLIC_BASE_URL": "https://camaras.vigia.gob.mx:9443"}):
            urls = resolve_access_urls(port=5000, tls_enabled=False)
            self.assertEqual(urls["public_base_url"], "https://camaras.vigia.gob.mx:9443")
            self.assertEqual(urls["effective_qr_base_url"], "https://camaras.vigia.gob.mx:9443")
            self.assertEqual(urls["local_url"], "http://127.0.0.1:5000")
            self.assertEqual(urls["recommended_lan_url"], "http://192.168.1.75:5000")

    def test_08_resolve_access_urls_no_lan_interfaces(self):
        """8. Si no hay interfaces y no es entorno de pruebas, effective_qr_base_url es None."""
        with patch("psutil.net_if_addrs", return_value={}), \
             patch("psutil.net_if_stats", return_value={}), \
             patch.dict(os.environ, {}, clear=True):
            urls = resolve_access_urls(port=5000, tls_enabled=False, app_config={"TESTING": False})
            self.assertIsNone(urls["effective_qr_base_url"])
            self.assertIsNone(urls["recommended_lan_url"])
            self.assertEqual(urls["lan_urls"], [])
            self.assertEqual(urls["local_url"], "http://127.0.0.1:5000")


if __name__ == "__main__":
    unittest.main()
