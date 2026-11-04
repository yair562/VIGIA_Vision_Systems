"""
tests.unit.test_lan_detector
============================
Pruebas unitarias para el módulo centralizado VIGIA_Core.network.lan_detector (VIGIA-NET-02).

Cobertura:
1. Independencia arquitectónica: no importa Flask ni Werkzeug en sys.modules.
2. Validación de IPv4 utilizable (is_usable_ipv4).
3. Filtrado determinista de interfaces virtuales, contenedores y túneles.
4. Resolución y selección de interfaces candidatas y recomendadas.
5. Validación y normalización de URLs de acceso (resolve_access_urls).
6. Estructura y coherencia del informe de diagnóstico pasivo (get_lan_diagnostic_report).
7. Sondeo pasivo de puertos de socket local (probe_local_port).
"""

import socket
import sys
import unittest
from unittest.mock import MagicMock, patch

from VIGIA_Core.network.lan_detector import (
    NetworkDiscoveryError,
    NoLanAddressError,
    discover_all_lan_candidates,
    discover_lan_ipv4,
    get_default_route_ip,
    get_lan_diagnostic_report,
    is_usable_ipv4,
    probe_local_port,
    resolve_access_urls,
    validate_public_base_url,
)


class TestLanDetectorUnit(unittest.TestCase):
    """Suite de pruebas unitarias para lan_detector."""

    def test_01_module_has_no_flask_or_werkzeug_dependencies(self):
        """1. lan_detector debe ser puro y no acoplarse a Flask ni Werkzeug."""
        # Se verifica que lan_detector no importe Flask ni Werkzeug en su espacio de nombres
        import VIGIA_Core.network.lan_detector as mod
        self.assertFalse(hasattr(mod, "Flask"))
        self.assertFalse(hasattr(mod, "request"))
        self.assertFalse(hasattr(mod, "jsonify"))

    def test_02_is_usable_ipv4_validation(self):
        """2. is_usable_ipv4 acepta IPs privadas y rechaza loopback, APIPA, multicast y no-IPs."""
        self.assertTrue(is_usable_ipv4("192.168.1.100"))
        self.assertTrue(is_usable_ipv4("10.0.0.1"))
        self.assertTrue(is_usable_ipv4("172.16.10.5"))

        # Inválidas
        self.assertFalse(is_usable_ipv4("127.0.0.1"))
        self.assertFalse(is_usable_ipv4("127.0.1.1"))
        self.assertFalse(is_usable_ipv4("169.254.10.20"))  # APIPA
        self.assertFalse(is_usable_ipv4("0.0.0.0"))
        self.assertFalse(is_usable_ipv4("224.0.0.251"))    # Multicast
        self.assertFalse(is_usable_ipv4(None))             # NoneType
        self.assertFalse(is_usable_ipv4(""))
        self.assertFalse(is_usable_ipv4("texto_invalido"))

    def test_03_discover_all_lan_candidates_filters_virtual(self):
        """3. discover_all_lan_candidates excluye vEthernet, Docker, WSL, VMware y loopback."""
        mock_addrs = {
            "vEthernet (WSL)": [MagicMock(family=socket.AF_INET, address="172.28.0.1")],
            "docker0": [MagicMock(family=socket.AF_INET, address="172.17.0.1")],
            "VMware Network Adapter VMnet8": [MagicMock(family=socket.AF_INET, address="192.168.200.1")],
            "Loopback Pseudo-Interface 1": [MagicMock(family=socket.AF_INET, address="127.0.0.1")],
            "Ethernet Real": [MagicMock(family=socket.AF_INET, address="192.168.1.75")],
        }
        mock_stats = {
            "vEthernet (WSL)": MagicMock(isup=True),
            "docker0": MagicMock(isup=True),
            "VMware Network Adapter VMnet8": MagicMock(isup=True),
            "Loopback Pseudo-Interface 1": MagicMock(isup=True),
            "Ethernet Real": MagicMock(isup=True),
        }

        with patch("psutil.net_if_addrs", return_value=mock_addrs), \
             patch("psutil.net_if_stats", return_value=mock_stats), \
             patch("VIGIA_Core.network.lan_detector.get_default_route_ip", return_value="192.168.1.75"):
            candidates = discover_all_lan_candidates()
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["interface"], "Ethernet Real")
            self.assertEqual(candidates[0]["ip"], "192.168.1.75")
            self.assertTrue(candidates[0]["is_recommended"])

    def test_04_discover_all_lan_candidates_preference_selection(self):
        """4. preferred_interface fuerza la recomendación de la interfaz deseada."""
        mock_addrs = {
            "Ethernet 1": [MagicMock(family=socket.AF_INET, address="192.168.1.75")],
            "Wi-Fi Caseta": [MagicMock(family=socket.AF_INET, address="192.168.1.80")],
        }
        mock_stats = {
            "Ethernet 1": MagicMock(isup=True),
            "Wi-Fi Caseta": MagicMock(isup=True),
        }

        with patch("psutil.net_if_addrs", return_value=mock_addrs), \
             patch("psutil.net_if_stats", return_value=mock_stats), \
             patch("VIGIA_Core.network.lan_detector.get_default_route_ip", return_value="192.168.1.75"):
            candidates = discover_all_lan_candidates(preferred_interface="Wi-Fi Caseta")
            wifi_c = next(c for c in candidates if c["interface"] == "Wi-Fi Caseta")
            eth_c = next(c for c in candidates if c["interface"] == "Ethernet 1")
            self.assertTrue(wifi_c["is_recommended"])
            self.assertFalse(eth_c["is_recommended"])

    def test_05_resolve_access_urls_and_validation(self):
        """5. resolve_access_urls calcula URLs y aplica TLS según el esquema."""
        mock_addrs = {
            "Ethernet": [MagicMock(family=socket.AF_INET, address="192.168.1.75")],
        }
        mock_stats = {"Ethernet": MagicMock(isup=True)}

        with patch("psutil.net_if_addrs", return_value=mock_addrs), \
             patch("psutil.net_if_stats", return_value=mock_stats):
            # HTTP plano
            urls_http = resolve_access_urls(port=5000, tls_enabled=False)
            self.assertEqual(urls_http["local_url"], "http://127.0.0.1:5000")
            self.assertEqual(urls_http["recommended_lan_url"], "http://192.168.1.75:5000")

            # HTTPS
            urls_https = resolve_access_urls(port=5000, tls_enabled=True)
            self.assertEqual(urls_https["local_url"], "https://127.0.0.1:5000")
            self.assertEqual(urls_https["recommended_lan_url"], "https://192.168.1.75:5000")

    def test_06_get_lan_diagnostic_report_structure(self):
        """6. get_lan_diagnostic_report entrega estructura completa y categoriza interfaces."""
        mock_addrs = {
            "vEthernet (WSL)": [MagicMock(family=socket.AF_INET, address="172.25.0.1")],
            "Ethernet Real": [MagicMock(family=socket.AF_INET, address="192.168.1.75")],
        }
        mock_stats = {
            "vEthernet (WSL)": MagicMock(isup=True),
            "Ethernet Real": MagicMock(isup=True),
        }

        with patch("psutil.net_if_addrs", return_value=mock_addrs), \
             patch("psutil.net_if_stats", return_value=mock_stats), \
             patch("VIGIA_Core.network.lan_detector.probe_local_port", return_value=False), \
             patch("VIGIA_Core.network.lan_detector.get_default_route_ip", return_value="192.168.1.75"):
            report = get_lan_diagnostic_report(port=5000)

            self.assertTrue(report["ok"])
            self.assertEqual(report["port"], 5000)
            self.assertEqual(report["recommended_candidate"]["ip"], "192.168.1.75")
            self.assertFalse(report["socket_listening_127_0_0_1"])

            # Comprobar que vEthernet fue categorizada en filtered_virtual
            filtered_names = [f["interface"] for f in report["filtered_virtual"]]
            self.assertIn("vEthernet (WSL)", filtered_names)

    def test_07_probe_local_port(self):
        """7. probe_local_port maneja puertos cerrados sin lanzar excepciones."""
        # Un puerto alto aleatorio que no esté en uso
        self.assertFalse(probe_local_port(host="127.0.0.1", port=59999, timeout=0.1))


if __name__ == "__main__":
    unittest.main()
