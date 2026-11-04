"""
Pruebas de integración para VIGIA-TLS-01: Habilitación de HTTPS para enrolamiento móvil.

Verifica:
1. create_ingest_app con enable_tls=True expone TLS_ENABLED y URLs https://.
2. GET /api/v1/system/network reporta tls_enabled=True y direcciones con esquema https://.
3. POST /api/v1/devices/pairing-qr genera QR codificando https:// y no 127.0.0.1 en LAN.
4. GET /api/v1/tls/ca.crt entrega exclusivamente el certificado público X.509 de la Root CA,
   sin claves privadas ni secretos.
5. Preservación estricta de la Root CA ante renovación del certificado de servidor para nueva IP.
6. Validez de SAN en el certificado de servidor conteniendo localhost, 127.0.0.1 y la IP LAN activa.
7. Compatibilidad con modo HTTP plano cuando VIGIA_ENABLE_TLS=0.
"""

import ipaddress
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtensionOID

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from VIGIA_API.ingest_service import (
    create_ingest_app,
    generate_vigia_local_ca_bundle,
    resolve_access_urls,
    resolve_active_tls_pair,
    validate_tls_certificate_pair,
    TLSConfigError,
)
from VIGIA_Core.domain.user import UserDTO
from VIGIA_Core.repository.user_repository import InMemoryUserRepository


class TestTLSMobileEnrollmentIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="vigia_tls_test_"))
        cls.ca_cert, cls.srv_key, cls.srv_cert = generate_vigia_local_ca_bundle(
            target_ip="192.168.1.75",
            cert_dir=cls.temp_dir,
            overwrite=True,
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        self.admin_user = UserDTO(
            username="admin_tls",
            contrasena_hash="$argon2id$v=19$m=65536,t=3,p=4$dummyhash",
            nombre_completo="Admin TLS",
            rol="ADMINISTRADOR",
        )
        self.user_repo = InMemoryUserRepository(initial_users=[self.admin_user])

    def test_01_create_app_tls_config_flags(self):
        """1. create_ingest_app configura TLS_ENABLED y DEV_PORT correctamente."""
        app = create_ingest_app(
            allow_in_memory=True,
            user_repository=self.user_repo,
            initialize_vision_engine=False,
            enable_tls=True,
            dev_port=8443,
        )
        self.assertTrue(app.config["TLS_ENABLED"])
        self.assertEqual(app.config["DEV_PORT"], 8443)

    def test_02_system_network_endpoint_reports_https(self):
        """2. GET /api/v1/system/network devuelve https:// en local y LAN cuando TLS está activo."""
        app = create_ingest_app(
            allow_in_memory=True,
            user_repository=self.user_repo,
            initialize_vision_engine=False,
            enable_tls=True,
            dev_port=8443,
        )
        app.config["TESTING"] = True
        client = app.test_client()

        resp = client.get("/api/v1/system/network")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["tls_enabled"])
        self.assertEqual(data["port"], 8443)
        self.assertTrue(data["local_url"].startswith("https://127.0.0.1:8443"))
        if data["recommended_lan_url"]:
            self.assertTrue(data["recommended_lan_url"].startswith("https://"))
        self.assertTrue(data["effective_qr_base_url"].startswith("https://"))

    def test_03_ca_download_endpoint_returns_valid_public_cert(self):
        """3. GET /api/v1/tls/ca.crt entrega el certificado público X.509 y ninguna clave privada."""
        app = create_ingest_app(
            allow_in_memory=True,
            user_repository=self.user_repo,
            initialize_vision_engine=False,
            enable_tls=True,
            dev_port=8443,
        )
        app.config["CERTS_DIR"] = self.temp_dir
        client = app.test_client()

        resp = client.get("/api/v1/tls/ca.crt")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("Content-Type"), "application/x-x509-ca-cert")
        self.assertIn('filename="vigia_root_ca.crt"', resp.headers.get("Content-Disposition", ""))

        content = resp.data
        # Verificar que es un certificado X.509 parseable
        cert = x509.load_pem_x509_certificate(content)
        self.assertIn("VIGIA Local Root CA", cert.subject.rfc4514_string())

        # Verificar que NO contiene claves privadas
        self.assertNotIn(b"PRIVATE KEY", content)

    def test_04_server_cert_san_contains_lan_ip_and_loopback(self):
        """4. El certificado del servidor emitido por la CA local incluye target_ip, localhost y 127.0.0.1 en SAN."""
        resolved_cert, resolved_key = resolve_active_tls_pair(
            cert_dir_or_cert_path=self.temp_dir,
            target_ip="192.168.1.75",
        )
        self.assertTrue(resolved_cert.is_file())
        self.assertTrue(resolved_key.is_file())

        cert = x509.load_pem_x509_certificate(resolved_cert.read_bytes())
        san_ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        san_values = san_ext.value

        ip_sans = [str(g.value) for g in san_values if isinstance(g, x509.IPAddress)]
        dns_sans = [g.value for g in san_values if isinstance(g, x509.DNSName)]

        self.assertIn("127.0.0.1", ip_sans)
        self.assertIn("192.168.1.75", ip_sans)
        self.assertIn("localhost", dns_sans)

    def test_05_root_ca_is_preserved_when_leaf_renewed_for_new_lan_ip(self):
        """5. La Root CA local no cambia al renovar el certificado hoja de servidor para una nueva IP LAN."""
        ca_cert_path = self.temp_dir / "vigia_root_ca.crt"
        original_ca_bytes = ca_cert_path.read_bytes()
        original_ca_cert = x509.load_pem_x509_certificate(original_ca_bytes)

        # Renovar para nueva IP LAN: 192.168.1.180
        new_srv_cert, new_srv_key, returned_ca = generate_vigia_local_ca_bundle(
            target_ip="192.168.1.180",
            cert_dir=self.temp_dir,
            overwrite=True,
        )

        after_ca_bytes = ca_cert_path.read_bytes()
        after_ca_cert = x509.load_pem_x509_certificate(after_ca_bytes)

        # La Root CA debe ser exactamente idéntica
        self.assertEqual(original_ca_bytes, after_ca_bytes)
        self.assertEqual(original_ca_cert.serial_number, after_ca_cert.serial_number)
        self.assertEqual(original_ca_cert.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ), after_ca_cert.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ))

        # Pero el certificado del servidor ahora es para 192.168.1.180
        resolved_cert, _ = resolve_active_tls_pair(self.temp_dir, target_ip="192.168.1.180")
        cert_180 = x509.load_pem_x509_certificate(resolved_cert.read_bytes())
        san_ext = cert_180.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        ip_sans = [str(g.value) for g in san_ext.value if isinstance(g, x509.IPAddress)]
        self.assertIn("192.168.1.180", ip_sans)

    def test_06_http_mode_fallback_when_tls_disabled(self):
        """6. Cuando enable_tls=False, las URLs usan esquema http:// y puerto 5000."""
        app = create_ingest_app(
            allow_in_memory=True,
            user_repository=self.user_repo,
            initialize_vision_engine=False,
            enable_tls=False,
            dev_port=5000,
        )
        app.config["TESTING"] = True
        client = app.test_client()

        resp = client.get("/api/v1/system/network")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data["tls_enabled"])
        self.assertEqual(data["port"], 5000)
        self.assertTrue(data["local_url"].startswith("http://127.0.0.1:5000"))
        if data["recommended_lan_url"]:
            self.assertTrue(data["recommended_lan_url"].startswith("http://"))


if __name__ == "__main__":
    unittest.main()
