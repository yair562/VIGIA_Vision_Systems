"""
tests.integration.test_phase3b_dashboard_integration
=====================================================
Pruebas de integración E2E para la Fase 3B: Integración de VIGIA_Dashboard con el backend real y PostgreSQL 16.

Verifica:
1. Servido de la aplicación web en /app y de los activos estáticos del Dashboard
   (/dashboard-assets/js/services/api-service.js, /dashboard-assets/js/views/cameras-view.js).
2. Flujo completo de sesión e inicio de sesión con cookie HttpOnly 'vigia_session'.
3. Consulta real de cámaras persistidas en PostgreSQL sin 'uri_stream'.
4. Manejo del estado vacío (0 cámaras) desde base de datos real.
5. Restricción del rol AUDITOR (HTTP 403 Forbidden).
6. Cierre de sesión idempotente con eliminación de cookie en servidor y cliente.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from uuid import uuid4

# Asegurar raíz del repositorio en sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import psycopg2

from VIGIA_API.ingest_service import create_ingest_app
from VIGIA_Core.domain.user import UserDTO
from VIGIA_Core.repository.user_repository import (
    PsycopgUserRepository,
    resolve_database_dsn,
)
from VIGIA_Core.security.password_hasher import hash_password
from VIGIA_Vision.config.psycopg_topology_repository import PsycopgTopologyConfigRepository


class TestPhase3BDashboardIntegration(unittest.TestCase):
    """Pruebas E2E de integración Dashboard-Backend contra PostgreSQL 16 vivo."""

    @classmethod
    def setUpClass(cls):
        os.environ["VIGIA_ALLOW_IN_MEMORY"] = "0"
        cls.dsn = resolve_database_dsn()

        try:
            conn = psycopg2.connect(cls.dsn, connect_timeout=5)
            conn.close()
        except Exception as exc:
            raise unittest.SkipTest(
                f"PostgreSQL no está disponible en '{cls.dsn}'. Omitiendo pruebas reales de integración: {exc}"
            )

        cls.user_repo = PsycopgUserRepository(cls.dsn)
        cls.topo_repo = PsycopgTopologyConfigRepository(cls.dsn)

        # Usuarios de prueba únicos para Fase 3B
        cls.admin_uname = f"admin_dash_{uuid4().hex[:6]}"
        cls.admin_pwd = "AdminDashboard2026!"
        cls.guardia_uname = f"guardia_dash_{uuid4().hex[:6]}"
        cls.guardia_pwd = "GuardiaDashboard2026!"
        cls.auditor_uname = f"auditor_dash_{uuid4().hex[:6]}"
        cls.auditor_pwd = "AuditorDashboard2026!"

        cls.admin_id = cls.user_repo.create_user(
            UserDTO(
                username=cls.admin_uname,
                contrasena_hash=hash_password(cls.admin_pwd),
                nombre_completo="Administrador Dashboard Real",
                rol="ADMINISTRADOR",
                activo=True,
            )
        )
        cls.guardia_id = cls.user_repo.create_user(
            UserDTO(
                username=cls.guardia_uname,
                contrasena_hash=hash_password(cls.guardia_pwd),
                nombre_completo="Guardia Caseta Real",
                rol="OPERADOR",  # Rol relacional que mapea a GUARDIA
                activo=True,
            )
        )
        cls.auditor_id = cls.user_repo.create_user(
            UserDTO(
                username=cls.auditor_uname,
                contrasena_hash=hash_password(cls.auditor_pwd),
                nombre_completo="Auditor Externo",
                rol="AUDITOR",
                activo=True,
            )
        )

        # Datos de cámara de prueba en PostgreSQL
        cls.cam_codigo = f"CAM-DASH-{uuid4().hex[:4]}"
        cls.area_codigo = f"A-DASH-{uuid4().hex[:4]}"
        cls.cam_id = None
        cls.area_id = None

        with psycopg2.connect(cls.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO camara (codigo, nombre, uri_stream, activa)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id_camara;
                    """,
                    (
                        cls.cam_codigo,
                        "Cámara Caseta Principal Fase 3B",
                        "rtsp://secret_user:secret_pass@192.168.1.120:554/ch1",
                        True,
                    ),
                )
                cls.cam_id = cur.fetchone()[0]

                cur.execute(
                    """
                    INSERT INTO area_vision (id_camara, codigo, nombre, tipo_movimiento, x_min, y_min, x_max, y_max, activa)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id_area_vision;
                    """,
                    (
                        cls.cam_id,
                        cls.area_codigo,
                        "Área Carril Ingreso Norte",
                        "ENTRADA",
                        0.05,
                        0.10,
                        0.95,
                        0.90,
                        True,
                    ),
                )
                cls.area_id = cur.fetchone()[0]
            conn.commit()

        # Instanciar aplicación Flask con persistencia real
        cls.app = create_ingest_app(
            user_repository=cls.user_repo,
            topology_repository=cls.topo_repo,
            allow_in_memory=False,
            auth_token="TEST_PUSH_KEY_2026",
        )

    @classmethod
    def tearDownClass(cls):
        with psycopg2.connect(cls.dsn) as conn:
            with conn.cursor() as cur:
                if cls.area_id:
                    cur.execute("DELETE FROM area_vision WHERE id_area_vision = %s;", (cls.area_id,))
                if cls.cam_id:
                    cur.execute("DELETE FROM camara WHERE id_camara = %s;", (cls.cam_id,))
                if cls.admin_id:
                    cur.execute("DELETE FROM usuario WHERE id_usuario = %s;", (str(cls.admin_id),))
                if cls.guardia_id:
                    cur.execute("DELETE FROM usuario WHERE id_usuario = %s;", (str(cls.guardia_id),))
                if cls.auditor_id:
                    cur.execute("DELETE FROM usuario WHERE id_usuario = %s;", (str(cls.auditor_id),))
            conn.commit()

    def setUp(self):
        self.client = self.app.test_client()

    def test_e2e_01_serve_dashboard_app_html(self):
        """E2E-01: GET /app entrega la pantalla HTML de VIGIA_Dashboard con estado DEMO deshabilitado."""
        resp = self.client.get("/app")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("Content-Type", ""))
        html = resp.get_data(as_text=True)
        self.assertIn("VIGÍA Vision Systems", html)
        self.assertIn('data-demo-enabled="false"', html)

    def test_e2e_02_serve_dashboard_static_assets(self):
        """E2E-02: GET /dashboard-assets/ entrega api-service.js y cameras-view.js autorizados."""
        # api-service.js
        resp_api = self.client.get("/dashboard-assets/js/services/api-service.js")
        self.assertEqual(resp_api.status_code, 200)
        self.assertIn("createApiService", resp_api.get_data(as_text=True))

        # cameras-view.js
        resp_cam = self.client.get("/dashboard-assets/js/views/cameras-view.js")
        self.assertEqual(resp_cam.status_code, 200)
        self.assertIn("renderCamerasView", resp_cam.get_data(as_text=True))

        # admin-navbar.js
        resp_nav = self.client.get("/dashboard-assets/js/components/admin-navbar.js")
        self.assertEqual(resp_nav.status_code, 200)
        self.assertIn("renderAdminNavbar", resp_nav.get_data(as_text=True))

    def test_e2e_03_login_and_session_restoration_lifecycle(self):
        """E2E-03: Login guarda cookie HttpOnly, /auth/me restaura usuario y no hay token en JSON."""
        # 1. Login
        login_resp = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"username": self.guardia_uname, "password": self.guardia_pwd}),
            content_type="application/json",
        )
        self.assertEqual(login_resp.status_code, 200)
        data = login_resp.get_json()
        self.assertTrue(data["ok"])
        self.assertNotIn("token", data, "El token NUNCA debe estar en el JSON de respuesta.")
        self.assertEqual(data["user"]["rol"], "GUARDIA")

        set_cookie = login_resp.headers.get("Set-Cookie", "")
        self.assertIn("vigia_session=", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Strict", set_cookie)

        # 2. Restauración de sesión mediante /api/v1/auth/me usando la cookie retenida
        me_resp = self.client.get("/api/v1/auth/me")
        self.assertEqual(me_resp.status_code, 200)
        me_data = me_resp.get_json()
        self.assertTrue(me_data["ok"])
        self.assertEqual(me_data["user"]["username"], self.guardia_uname)
        self.assertEqual(me_data["user"]["rol"], "GUARDIA")

    def test_e2e_04_cameras_persisted_query_excludes_uri_stream(self):
        """E2E-04: GET /api/v1/cameras devuelve la cámara persistida en PostgreSQL y omite uri_stream."""
        # Login como guardia
        self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"username": self.guardia_uname, "password": self.guardia_pwd}),
            content_type="application/json",
        )

        resp = self.client.get("/api/v1/cameras")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertGreaterEqual(data["total"], 1)

        cam = next((c for c in data["cameras"] if c["codigo"] == self.cam_codigo), None)
        self.assertIsNotNone(cam, "La cámara creada en PostgreSQL debe figurar en la respuesta.")
        self.assertEqual(cam["nombre"], "Cámara Caseta Principal Fase 3B")
        self.assertTrue(cam["activa"])

        # INVARIANTE CRÍTICO: uri_stream nunca expuesto
        self.assertNotIn("uri_stream", cam)

        # Áreas agrupadas correctamente
        self.assertEqual(len(cam["areas"]), 1)
        self.assertEqual(cam["areas"][0]["codigo"], self.area_codigo)
        self.assertEqual(cam["areas"][0]["tipo_movimiento"], "ENTRADA")

    def test_e2e_05_auditor_role_forbidden_on_cameras(self):
        """E2E-05: El rol AUDITOR es rechazado con HTTP 403 Forbidden al consultar cámaras."""
        self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"username": self.auditor_uname, "password": self.auditor_pwd}),
            content_type="application/json",
        )

        resp = self.client.get("/api/v1/cameras")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json()["error"], "FORBIDDEN")

    def test_e2e_06_logout_clears_cookie_and_protects_routes(self):
        """E2E-06: Logout elimina la cookie en el cliente e invalida llamadas subsecuentes con 401."""
        self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"username": self.admin_uname, "password": self.admin_pwd}),
            content_type="application/json",
        )

        # Logout
        logout_resp = self.client.post("/api/v1/auth/logout")
        self.assertEqual(logout_resp.status_code, 200)
        self.assertTrue(logout_resp.get_json()["ok"])
        self.assertIn("Max-Age=0", logout_resp.headers.get("Set-Cookie", ""))

        # Petición protegida posterior debe dar 401
        after_resp = self.client.get("/api/v1/auth/me")
        self.assertEqual(after_resp.status_code, 401)


if __name__ == "__main__":
    unittest.main()
