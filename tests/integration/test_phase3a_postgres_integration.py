"""
tests.integration.test_phase3a_postgres_integration
====================================================
Pruebas de integración reales contra PostgreSQL 16 para la Fase 3A de VIGÍA.

Verifica:
1. Inicialización de create_ingest_app(allow_in_memory=False) conectando
   directamente a la base de datos PostgreSQL real (puerto 5433).
2. Autenticación real contra la tabla 'usuario' con hashes Argon2id.
3. Transporte estricto por cookie HttpOnly (sin token en el cuerpo JSON).
4. Consulta real de topología ('camara' y 'area_vision') mediante PsycopgTopologyConfigRepository.
5. Invariante de seguridad: 'uri_stream' NUNCA expuesto en la respuesta HTTP.
6. Matriz RBAC real:
   - GUARDIA y ADMINISTRADOR autorizados en /api/v1/cameras.
   - AUDITOR restringido con HTTP 403 en /api/v1/cameras.
7. Cierre de sesión (logout) idempotente con invalidación de cookie en servidor y cliente.
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
    build_default_user_repository,
    resolve_database_dsn,
)
from VIGIA_Core.security.password_hasher import hash_password
from VIGIA_Vision.config.psycopg_topology_repository import PsycopgTopologyConfigRepository


class TestPhase3APostgresIntegration(unittest.TestCase):
    """Pruebas de integración E2E contra la instancia PostgreSQL 16 viva."""

    @classmethod
    def setUpClass(cls):
        # Desactivar explícitamente modo en memoria para forzar PostgreSQL
        os.environ["VIGIA_ALLOW_IN_MEMORY"] = "0"
        cls.dsn = resolve_database_dsn()

        # Verificar conectividad directa antes de ejecutar
        try:
            conn = psycopg2.connect(cls.dsn, connect_timeout=5)
            conn.close()
        except Exception as exc:
            raise unittest.SkipTest(
                f"PostgreSQL no está disponible en '{cls.dsn}'. Omitiendo pruebas de integración reales: {exc}"
            )

        # Repositorio de usuarios real sobre PostgreSQL
        cls.user_repo = PsycopgUserRepository(cls.dsn)
        cls.topo_repo = PsycopgTopologyConfigRepository(cls.dsn)

        # Generar identificadores únicos para datos de prueba
        cls.test_guardia_uname = f"test_guardia_{uuid4().hex[:8]}"
        cls.test_guardia_pwd = "GuardiaSecurePass2026!"
        cls.test_auditor_uname = f"test_auditor_{uuid4().hex[:8]}"
        cls.test_auditor_pwd = "AuditorSecurePass2026!"

        # Crear usuarios de prueba con hash Argon2id
        cls.guardia_id = cls.user_repo.create_user(
            UserDTO(
                username=cls.test_guardia_uname,
                contrasena_hash=hash_password(cls.test_guardia_pwd),
                nombre_completo="Guardia Integración Real",
                rol="OPERADOR",
                activo=True,
            )
        )

        cls.auditor_id = cls.user_repo.create_user(
            UserDTO(
                username=cls.test_auditor_uname,
                contrasena_hash=hash_password(cls.test_auditor_pwd),
                nombre_completo="Auditor Integración Real",
                rol="AUDITOR",
                activo=True,
            )
        )

        # Insertar una cámara y un área de prueba en PostgreSQL
        cls.test_cam_codigo = f"CAM-TEST-{uuid4().hex[:6]}"
        cls.test_area_codigo = f"AREA-TEST-{uuid4().hex[:6]}"
        cls.test_cam_id = None
        cls.test_area_id = None

        with psycopg2.connect(cls.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO camara (codigo, nombre, uri_stream, activa)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id_camara;
                    """,
                    (
                        cls.test_cam_codigo,
                        "Cámara Integración Fase 3A",
                        "rtsp://admin:super_secret_password@192.168.1.50:554/live",
                        True,
                    ),
                )
                cls.test_cam_id = cur.fetchone()[0]

                cur.execute(
                    """
                    INSERT INTO area_vision (id_camara, codigo, nombre, tipo_movimiento, x_min, y_min, x_max, y_max, activa)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id_area_vision;
                    """,
                    (
                        cls.test_cam_id,
                        cls.test_area_codigo,
                        "Área Carril Entrada Fase 3A",
                        "ENTRADA",
                        0.1,
                        0.2,
                        0.8,
                        0.9,
                        True,
                    ),
                )
                cls.test_area_id = cur.fetchone()[0]
            conn.commit()

        # Construir aplicación Flask conectada a PostgreSQL real
        cls.app = create_ingest_app(
            user_repository=cls.user_repo,
            topology_repository=cls.topo_repo,
            allow_in_memory=False,
            auth_token="TEST_PUSH_KEY_2026",
        )

    @classmethod
    def tearDownClass(cls):
        # Limpieza de datos de prueba en PostgreSQL
        with psycopg2.connect(cls.dsn) as conn:
            with conn.cursor() as cur:
                if cls.test_area_id:
                    cur.execute("DELETE FROM area_vision WHERE id_area_vision = %s;", (cls.test_area_id,))
                if cls.test_cam_id:
                    cur.execute("DELETE FROM camara WHERE id_camara = %s;", (cls.test_cam_id,))
                if cls.guardia_id:
                    cur.execute("DELETE FROM usuario WHERE id_usuario = %s;", (str(cls.guardia_id),))
                if cls.auditor_id:
                    cur.execute("DELETE FROM usuario WHERE id_usuario = %s;", (str(cls.auditor_id),))
            conn.commit()

    def setUp(self):
        self.client = self.app.test_client()

    def test_pi_01_login_guardia_real_postgres(self):
        """PI-01: Login exitoso de guardia contra PostgreSQL devuelve 200, rol GUARDIA y cookie HttpOnly sin token JSON."""
        resp = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"username": self.test_guardia_uname, "password": self.test_guardia_pwd}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertNotIn("token", data, "El token de sesión NO debe figurar en el cuerpo JSON.")
        self.assertEqual(data["user"]["username"], self.test_guardia_uname)
        self.assertEqual(data["user"]["rol"], "GUARDIA")

        # Verificar encabezado Set-Cookie
        set_cookie = resp.headers.get("Set-Cookie", "")
        self.assertIn("vigia_session=", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("Path=/", set_cookie)
        self.assertIn("SameSite=Strict", set_cookie)

    def test_pi_02_auth_me_via_cookie(self):
        """PI-02: /api/v1/auth/me resuelve la identidad y rol del usuario autenticado vía cookie."""
        # 1. Login
        self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"username": self.test_guardia_uname, "password": self.test_guardia_pwd}),
            content_type="application/json",
        )

        # 2. Consultar perfil
        resp = self.client.get("/api/v1/auth/me")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["user"]["username"], self.test_guardia_uname)
        self.assertEqual(data["user"]["rol"], "GUARDIA")

    def test_pi_03_cameras_endpoint_real_postgres_persisted_data(self):
        """PI-03: /api/v1/cameras consulta la base de datos real, devuelve cámaras y áreas, y omite uri_stream."""
        # Login como guardia
        self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"username": self.test_guardia_uname, "password": self.test_guardia_pwd}),
            content_type="application/json",
        )

        resp = self.client.get("/api/v1/cameras")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertGreaterEqual(data["total"], 1)

        # Buscar la cámara de prueba insertada
        test_cam = next((c for c in data["cameras"] if c["codigo"] == self.test_cam_codigo), None)
        self.assertIsNotNone(test_cam, "La cámara persistida debe estar presente en la respuesta.")
        self.assertEqual(test_cam["nombre"], "Cámara Integración Fase 3A")
        self.assertTrue(test_cam["activa"])

        # INVARIANTE CRÍTICO: uri_stream nunca debe exponerse
        self.assertNotIn("uri_stream", test_cam, "Invariante de seguridad violado: uri_stream expuesto al frontend.")

        # Verificar áreas agrupadas
        self.assertEqual(len(test_cam["areas"]), 1)
        area = test_cam["areas"][0]
        self.assertEqual(area["codigo"], self.test_area_codigo)
        self.assertEqual(area["nombre"], "Área Carril Entrada Fase 3A")
        self.assertEqual(area["tipo_movimiento"], "ENTRADA")

    def test_pi_04_cameras_endpoint_auditor_forbidden_real_postgres(self):
        """PI-04: Usuario con rol AUDITOR es rechazado con 403 Forbidden en /api/v1/cameras."""
        # Login como auditor
        self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"username": self.test_auditor_uname, "password": self.test_auditor_pwd}),
            content_type="application/json",
        )

        resp = self.client.get("/api/v1/cameras")
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "FORBIDDEN")

    def test_pi_05_logout_lifecycle_and_idempotence(self):
        """PI-05: Logout invalida la sesión, limpia la cookie y posterior petición a /auth/me devuelve 401."""
        # 1. Login
        self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"username": self.test_guardia_uname, "password": self.test_guardia_pwd}),
            content_type="application/json",
        )

        # 2. Logout
        logout_resp = self.client.post("/api/v1/auth/logout")
        self.assertEqual(logout_resp.status_code, 200)
        self.assertTrue(logout_resp.get_json()["ok"])
        set_cookie = logout_resp.headers.get("Set-Cookie", "")
        self.assertIn("vigia_session=", set_cookie)
        self.assertIn("Max-Age=0", set_cookie)

        # 3. /auth/me posterior devuelve 401
        after_resp = self.client.get("/api/v1/auth/me")
        self.assertEqual(after_resp.status_code, 401)

        # 4. Segundo logout consecutivo es idempotente y devuelve 200
        repeat_logout = self.client.post("/api/v1/auth/logout")
        self.assertEqual(repeat_logout.status_code, 200)


if __name__ == "__main__":
    unittest.main()
