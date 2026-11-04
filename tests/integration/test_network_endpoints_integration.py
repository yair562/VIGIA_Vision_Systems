"""
tests.integration.test_network_endpoints_integration
====================================================
Pruebas de integración para los endpoints de red y enrolamiento QR (VIGIA-NET-01).

Valida:
1. GET /api/v1/system/network devuelve el contrato requerido (local_url, lan_urls, etc.).
2. POST /api/v1/devices/pairing-qr utiliza la dirección LAN o pública configurada en el QR.
3. El código QR nunca contiene 127.0.0.1, localhost ni 0.0.0.0 en producción.
4. Rechazo con 400 cuando VIGIA_PUBLIC_BASE_URL es loopback.
5. Control de acceso RBAC estricto (401 sin sesión, 403 rol GUARDIA).
6. Preservación del token de reclamación, TTL y formato base64 de la imagen PNG.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import psycopg2

from VIGIA_API.ingest_service import (
    build_vision_engine_coordinator,
    create_ingest_app,
)
from VIGIA_Core.domain.user import UserDTO
from VIGIA_Core.repository.detection_repository import PsycopgDetectionRepository
from VIGIA_Core.repository.pairing_repository import PsycopgPairingRepository
from VIGIA_Core.repository.user_repository import PsycopgUserRepository, resolve_database_dsn
from VIGIA_Core.security.password_hasher import hash_password
from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.config.psycopg_topology_repository import PsycopgTopologyConfigRepository
from VIGIA_Vision.runtime.evidence_storage import LocalDiskEvidenceStorage


class TestNetworkEndpointsIntegration(unittest.TestCase):
    """Pruebas de integración de endpoints de red y enrolamiento QR."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.dsn = resolve_database_dsn()
        try:
            conn = psycopg2.connect(cls.dsn, connect_timeout=5)
            conn.close()
        except Exception as exc:
            raise unittest.SkipTest(f"PostgreSQL no disponible en '{cls.dsn}': {exc}")

        cls.user_repo = PsycopgUserRepository(cls.dsn)
        cls.topo_repo = PsycopgTopologyConfigRepository(cls.dsn)
        cls.det_repo = PsycopgDetectionRepository(cls.dsn)
        cls.pairing_repo = PsycopgPairingRepository(cls.dsn)

        # Crear administrador y guardia
        cls.admin_uname = f"admin_net_{uuid4().hex[:6]}"
        cls.admin_pwd = "PasswordAdminNet123!"
        cls.admin_id = cls.user_repo.create_user(
            UserDTO(
                username=cls.admin_uname,
                contrasena_hash=hash_password(cls.admin_pwd),
                nombre_completo="Admin Pruebas Red",
                rol="ADMINISTRADOR",
                activo=True,
            )
        )

        cls.guardia_uname = f"guardia_net_{uuid4().hex[:6]}"
        cls.guardia_pwd = "PasswordGuardiaNet123!"
        cls.guardia_id = cls.user_repo.create_user(
            UserDTO(
                username=cls.guardia_uname,
                contrasena_hash=hash_password(cls.guardia_pwd),
                nombre_completo="Guardia Pruebas Red",
                rol="OPERADOR",
                activo=True,
            )
        )

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            with psycopg2.connect(cls.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        DELETE FROM camara_credencial
                        WHERE id_solicitud IN (
                            SELECT id_solicitud FROM camera_pairing_request WHERE creado_por IN (%s, %s)
                        );
                        DELETE FROM camera_pairing_request WHERE creado_por IN (%s, %s);
                        DELETE FROM usuario WHERE id_usuario IN (%s, %s);
                        """,
                        (
                            str(cls.admin_id),
                            str(cls.guardia_id),
                            str(cls.admin_id),
                            str(cls.guardia_id),
                            str(cls.admin_id),
                            str(cls.guardia_id),
                        ),
                    )
                conn.commit()
        except Exception as exc:
            print(f"Error en tearDownClass: {exc}")

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="vigia_net_test_"))
        self.settings = VisionEngineSettings(
            vehicle_confidence_threshold=0.70,
            mobile_frame_ttl_seconds=3.0,
        )
        self.evidence_storage = LocalDiskEvidenceStorage(base_directory=self.temp_dir)
        self.coordinator = build_vision_engine_coordinator(
            dsn=self.dsn,
            evidence_storage=self.evidence_storage,
            settings=self.settings,
        )
        self.app = create_ingest_app(
            coordinator=self.coordinator,
            auth_token="TEST_PUSH_SECRET_NET_2026",
            user_repository=self.user_repo,
            topology_repository=self.topo_repo,
            pairing_repository=self.pairing_repo,
            allow_in_memory=False,
        )
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _login(self, client, username, password) -> None:
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        self.assertEqual(resp.status_code, 200)

    # -------------------------------------------------------------------------
    # 1. Endpoint GET /api/v1/system/network
    # -------------------------------------------------------------------------
    def test_01_get_system_network_contract(self):
        """1. GET /api/v1/system/network entrega el contrato exacto sin exponer secretos."""
        resp = self.client.get("/api/v1/system/network")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        self.assertTrue(data["ok"])
        self.assertIn("local_url", data)
        self.assertTrue(data["local_url"].startswith("http://127.0.0.1:"))
        self.assertIn("lan_urls", data)
        self.assertIsInstance(data["lan_urls"], list)
        self.assertIn("recommended_lan_url", data)
        self.assertIn("port", data)
        self.assertIn("tls_enabled", data)
        self.assertFalse(data["tls_enabled"])

        # Verificar que no existen secretos ni credenciales en la respuesta
        text = resp.get_data(as_text=True)
        self.assertNotIn("password", text.lower())
        self.assertNotIn("secret", text.lower())
        self.assertNotIn("hash", text.lower())

    # -------------------------------------------------------------------------
    # 2. Generación de QR con URL LAN
    # -------------------------------------------------------------------------
    def test_02_qr_generation_uses_lan_address(self):
        """2. POST /api/v1/devices/pairing-qr genera un QR con URL accesible en LAN (no 127.0.0.1)."""
        self._login(self.client, self.admin_uname, self.admin_pwd)

        with patch.dict(os.environ, {"VIGIA_PUBLIC_BASE_URL": "http://192.168.1.150:5000"}):
            resp = self.client.post(
                "/api/v1/devices/pairing-qr",
                json={"codigo_camara": "CAM-ENTRADA", "ttl_minutes": 10},
            )
            self.assertEqual(resp.status_code, 201)
            data = resp.get_json()

            self.assertTrue(data["ok"])
            self.assertIn("192.168.1.150:5000", data["pairing_url"])
            self.assertIn("192.168.1.150:5000", data["enrollment_url"])
            self.assertIn("192.168.1.150:5000", data["lan_url"])
            self.assertIn("127.0.0.1:5000", data["local_url"])
            self.assertIn("claim_token", data)
            self.assertTrue(data["qr_base64_data_url"].startswith("data:image/png;base64,"))

    # -------------------------------------------------------------------------
    # 3. Rechazo de loopback explícito en VIGIA_PUBLIC_BASE_URL
    # -------------------------------------------------------------------------
    def test_03_reject_loopback_in_public_base_url(self):
        """3. Rechaza la generación de QR si VIGIA_PUBLIC_BASE_URL apunta a loopback (127.0.0.1)."""
        self._login(self.client, self.admin_uname, self.admin_pwd)

        # Forzar TESTING=False en app.config temporalmente para verificar regla de producción
        original_testing = self.app.config.get("TESTING")
        self.app.config["TESTING"] = False
        try:
            with patch.dict(os.environ, {"VIGIA_PUBLIC_BASE_URL": "http://127.0.0.1:5000"}):
                resp = self.client.post(
                    "/api/v1/devices/pairing-qr",
                    json={"codigo_camara": "CAM-ENTRADA"},
                )
                self.assertEqual(resp.status_code, 400)
                data = resp.get_json()
                self.assertFalse(data["ok"])
                self.assertEqual(data["error"], "INVALID_QR_BASE_URL")
                self.assertIn("no es accesible desde un teléfono móvil", data["message"])
        finally:
            self.app.config["TESTING"] = original_testing

    # -------------------------------------------------------------------------
    # 4. Control de Acceso RBAC en pairing-qr
    # -------------------------------------------------------------------------
    def test_04_rbac_controls_on_pairing_qr(self):
        """4. pairing-qr exige rol ADMINISTRADOR (401 no auth, 403 rol GUARDIA)."""
        # Sin login -> 401
        unauth_resp = self.client.post(
            "/api/v1/devices/pairing-qr",
            json={"codigo_camara": "CAM-ENTRADA"},
        )
        self.assertEqual(unauth_resp.status_code, 401)

        # Con login de guardia -> 403
        self._login(self.client, self.guardia_uname, self.guardia_pwd)
        guardia_resp = self.client.post(
            "/api/v1/devices/pairing-qr",
            json={"codigo_camara": "CAM-ENTRADA"},
        )
        self.assertEqual(guardia_resp.status_code, 403)

    # -------------------------------------------------------------------------
    # 5. Generación de QR con TLS Habilitado (HTTPS)
    # -------------------------------------------------------------------------
    def test_05_qr_generation_with_tls_enabled(self):
        """5. pairing-qr codifica URLs con esquema https:// cuando TLS_ENABLED=True."""
        self._login(self.client, self.admin_uname, self.admin_pwd)
        self.app.config["TLS_ENABLED"] = True
        self.app.config["DEV_PORT"] = 8443
        try:
            with patch.dict(os.environ, {"VIGIA_PUBLIC_BASE_URL": "https://192.168.1.150:8443"}):
                resp = self.client.post(
                    "/api/v1/devices/pairing-qr",
                    json={"codigo_camara": "CAM-ENTRADA", "ttl_minutes": 10},
                )
                self.assertEqual(resp.status_code, 201)
                data = resp.get_json()
                self.assertTrue(data["ok"])
                self.assertTrue(data["pairing_url"].startswith("https://192.168.1.150:8443"))
                self.assertTrue(data["lan_url"].startswith("https://192.168.1.150:8443"))
                self.assertTrue(data["local_url"].startswith("https://127.0.0.1:8443"))

            # Validar que si VIGIA_PUBLIC_BASE_URL usa http:// en modo TLS, se rechaza con 400
            with patch.dict(os.environ, {"VIGIA_PUBLIC_BASE_URL": "http://192.168.1.150:8443"}):
                resp_err = self.client.post(
                    "/api/v1/devices/pairing-qr",
                    json={"codigo_camara": "CAM-ENTRADA"},
                )
                self.assertEqual(resp_err.status_code, 400)
                data_err = resp_err.get_json()
                self.assertFalse(data_err["ok"])
                self.assertEqual(data_err["error"], "INVALID_CONFIGURATION")
        finally:
            self.app.config["TLS_ENABLED"] = False
            self.app.config["DEV_PORT"] = 5000


if __name__ == "__main__":
    unittest.main()
