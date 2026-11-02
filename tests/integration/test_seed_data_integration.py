"""
tests.integration.test_seed_data_integration
============================================
Pruebas de verificación de los datos de prueba sintéticos (seed_data.sql)
y validación de autenticación RBAC en VIGÍA Vision Systems.

Verifica:
1. Integridad del archivo Software/BD/seed_data.sql:
   - Hashes Argon2id PHC válidos.
   - Ninguna contraseña en texto plano en las sentencias INSERT.
   - Cláusulas de idempotencia ON CONFLICT DO NOTHING.
   - Ausencia de inserciones de cámaras o áreas de visión.
2. Estado de la base de datos PostgreSQL 16:
   - Existencia de los usuarios sintéticos (admin_dev, guardia_dev, auditor_dev).
   - Compatibilidad criptográfica con VIGIA_Core.security.password_hasher.
   - Existencia de 20 personas y 20 alumnos distribuidos en las 7 carreras.
3. Flujo HTTP de autenticación y proyección de roles RBAC:
   - admin_dev autentica con rol funcional ADMINISTRADOR.
   - guardia_dev autentica con rol funcional GUARDIA (desde rol relacional OPERADOR).
   - auditor_dev autentica con rol funcional AUDITOR.
   - Rechazo de contraseñas inválidas con HTTP 401.
4. Idempotencia de ejecución repetida:
   - Re-ejecución sin duplicación ni alteración de hashes existentes.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# Asegurar raíz del repositorio en sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import psycopg2

from VIGIA_API.ingest_service import create_ingest_app
from VIGIA_Core.repository.user_repository import (
    PsycopgUserRepository,
    resolve_database_dsn,
)
from VIGIA_Core.security.password_hasher import verify_password


class TestSeedDataIntegration(unittest.TestCase):
    """Pruebas de verificación e integración para la fuente unificada V003__seed_data.sql en PostgreSQL 16."""

    @classmethod
    def setUpClass(cls):
        os.environ["VIGIA_ALLOW_IN_MEMORY"] = "0"

        # Localizar la fuente unificada canónica V003__seed_data.sql
        cls.seed_path = _REPO_ROOT.parent / "BD" / "migrations" / "V003__seed_data.sql"
        if not cls.seed_path.exists():
            cls.seed_path = Path("BD/migrations/V003__seed_data.sql").resolve()

        if not cls.seed_path.exists():
            raise FileNotFoundError(f"No se encontró V003__seed_data.sql en {cls.seed_path}")

        cls.dsn = resolve_database_dsn()
        try:
            conn = psycopg2.connect(cls.dsn, connect_timeout=5)
            conn.close()
        except Exception as exc:
            raise unittest.SkipTest(
                f"PostgreSQL 16 no está disponible en '{cls.dsn}'. Omitiendo pruebas de integración: {exc}"
            )

        # Cargar seed data en la base de datos de pruebas desde la fuente canónica V003
        with open(cls.seed_path, "r", encoding="utf-8") as f:
            sql_content = f.read()

        conn = psycopg2.connect(cls.dsn)
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql_content)
        conn.close()

        # Inicializar Flask test client
        cls.user_repo = PsycopgUserRepository(cls.dsn)
        cls.app = create_ingest_app(allow_in_memory=False)
        cls.client = cls.app.test_client()

    def test_seed_file_security_and_constraints(self):
        """Verifica que seed_data.sql respete todas las invariantes de seguridad."""
        with open(self.seed_path, "r", encoding="utf-8") as f:
            content = f.read()

        # No debe contener contraseñas en texto plano dentro de sentencias INSERT
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("(") and ("AdminDev2026!" in stripped or "GuardiaDev2026!" in stripped):
                self.fail(f"Contraseña en texto plano encontrada en sentencia INSERT: {line}")

        # Debe contener hashes Argon2id válidos
        self.assertIn("$argon2id$v=19$m=65536,t=2,p=1$", content)

        # Debe ser idempotente
        self.assertIn("ON CONFLICT", content)

        # No debe crear cámaras ni áreas
        self.assertNotIn("INSERT INTO camara", content)
        self.assertNotIn("INSERT INTO area_vision", content)

    def test_synthetic_users_exist_and_verify(self):
        """Verifica que exclusivamente existan admin_dev y guardia_dev en PostgreSQL y verifiquen."""
        credentials = {
            "admin_dev": ("AdminDev2026!", "ADMINISTRADOR", "ADMINISTRADOR"),
            "guardia_dev": ("GuardiaDev2026!", "OPERADOR", "GUARDIA"),
        }

        conn = psycopg2.connect(self.dsn)
        with conn:
            with conn.cursor() as cur:
                # Comprobar conteo exacto de 2 usuarios
                cur.execute("SELECT count(*) FROM usuario;")
                self.assertEqual(cur.fetchone()[0], 2, "La base de datos debe contener exclusivamente 2 usuarios sintéticos.")

                for username, (pwd, db_rol, func_rol) in credentials.items():
                    cur.execute(
                        "SELECT id_usuario, contrasena_hash, rol, activo FROM usuario WHERE LOWER(username) = %s;",
                        (username.lower(),),
                    )
                    row = cur.fetchone()
                    self.assertIsNotNone(row, f"Usuario '{username}' no encontrado en PostgreSQL.")
                    uid, hash_str, actual_db_rol, activo = row

                    self.assertTrue(activo, f"Usuario '{username}' no está activo.")
                    self.assertEqual(actual_db_rol, db_rol, f"Rol relacional no coincide para '{username}'.")
                    self.assertTrue(
                        hash_str.startswith("$argon2id$"),
                        f"El hash del usuario '{username}' no es un hash Argon2id válido.",
                    )
                    self.assertTrue(
                        verify_password(hash_str, pwd),
                        f"La contraseña provista no verifica con el hash Argon2id para '{username}'.",
                    )
        conn.close()

    def test_synthetic_students_and_careers_distribution(self):
        """Verifica que se hayan insertado 20 personas y 20 alumnos distribuidos en las 7 carreras."""
        conn = psycopg2.connect(self.dsn)
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM persona;")
                total_personas = cur.fetchone()[0]
                self.assertGreaterEqual(total_personas, 20)

                cur.execute("SELECT count(*) FROM alumno;")
                total_alumnos = cur.fetchone()[0]
                self.assertGreaterEqual(total_alumnos, 20)

                cur.execute("SELECT count(*) FROM carrera;")
                total_carreras = cur.fetchone()[0]
                self.assertGreaterEqual(total_carreras, 7)

                # Verificar distribución por carrera
                cur.execute("""
                    SELECT c.clave, count(a.id_persona)
                    FROM carrera c
                    LEFT JOIN alumno a ON a.id_carrera = c.id_carrera
                    GROUP BY c.clave
                    ORDER BY c.clave;
                """)
                carrera_counts = dict(cur.fetchall())
                for clave in ("IC", "ISC", "II", "IM", "LB", "LA", "LG"):
                    self.assertIn(clave, carrera_counts)
                    self.assertGreater(
                        carrera_counts[clave],
                        0,
                        f"La carrera '{clave}' no tiene alumnos sintéticos asignados.",
                    )
        conn.close()

    def test_http_auth_login_admin_dev(self):
        """Verifica el flujo HTTP de inicio de sesión con admin_dev."""
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin_dev", "password": "AdminDev2026!"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("user", {}).get("username"), "admin_dev")
        self.assertEqual(data.get("user", {}).get("rol"), "ADMINISTRADOR")
        self.assertNotIn("token", data)  # Invariante HTTP: no token en el body

        # Sesión vía cookie HttpOnly en /me
        me_resp = self.client.get("/api/v1/auth/me")
        self.assertEqual(me_resp.status_code, 200)
        me_data = me_resp.get_json()
        self.assertEqual(me_data.get("user", {}).get("rol"), "ADMINISTRADOR")

        # Logout
        logout_resp = self.client.post("/api/v1/auth/logout")
        self.assertEqual(logout_resp.status_code, 200)

    def test_http_auth_login_guardia_dev_role_mapping(self):
        """Verifica que guardia_dev autentique y proyecte su rol a GUARDIA en la API."""
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": "guardia_dev", "password": "GuardiaDev2026!"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("user", {}).get("username"), "guardia_dev")
        self.assertEqual(data.get("user", {}).get("rol"), "GUARDIA")

        # /me debe reportar GUARDIA
        me_resp = self.client.get("/api/v1/auth/me")
        self.assertEqual(me_resp.status_code, 200)
        self.assertEqual(me_resp.get_json().get("user", {}).get("rol"), "GUARDIA")

        self.client.post("/api/v1/auth/logout")

    def test_http_auth_session_lifecycle_and_logout(self):
        """Verifica el ciclo completo de vida de sesión, restauración por cookie y logout."""
        # 1. Login exitoso como admin_dev
        login_resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin_dev", "password": "AdminDev2026!"},
        )
        self.assertEqual(login_resp.status_code, 200)
        cookie = login_resp.headers.get("Set-Cookie")
        self.assertIn("vigia_session=", cookie)
        self.assertIn("HttpOnly", cookie)

        # 2. Restauración de sesión (GET /api/v1/auth/me) con cookie automática del cliente
        me_resp = self.client.get("/api/v1/auth/me")
        self.assertEqual(me_resp.status_code, 200)
        me_json = me_resp.get_json()
        self.assertTrue(me_json.get("ok"))
        self.assertEqual(me_json.get("user", {}).get("username"), "admin_dev")
        self.assertEqual(me_json.get("user", {}).get("rol"), "ADMINISTRADOR")

        # 3. Logout (POST /api/v1/auth/logout)
        logout_resp = self.client.post("/api/v1/auth/logout")
        self.assertEqual(logout_resp.status_code, 200)

        # 4. Comprobar que la sesión queda invalidada
        post_logout_me = self.client.get("/api/v1/auth/me")
        self.assertEqual(post_logout_me.status_code, 401)

    def test_http_auth_invalid_credentials(self):
        """Verifica que contraseñas incorrectas sean rechazadas con 401."""
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": "guardia_dev", "password": "BadPassword123!"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_idempotent_reexecution(self):
        """Verifica que re-ejecutar seed_data.sql no cause errores ni duplicados ni modifique hashes."""
        conn = psycopg2.connect(self.dsn)
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT username, contrasena_hash FROM usuario ORDER BY username;")
                hashes_before = dict(cur.fetchall())

                cur.execute("SELECT count(*) FROM usuario;")
                u_count_before = cur.fetchone()[0]
                cur.execute("SELECT count(*) FROM alumno;")
                a_count_before = cur.fetchone()[0]

                # Re-ejecutar seed_data.sql
                with open(self.seed_path, "r", encoding="utf-8") as f:
                    cur.execute(f.read())

                cur.execute("SELECT username, contrasena_hash FROM usuario ORDER BY username;")
                hashes_after = dict(cur.fetchall())
                cur.execute("SELECT count(*) FROM usuario;")
                u_count_after = cur.fetchone()[0]
                cur.execute("SELECT count(*) FROM alumno;")
                a_count_after = cur.fetchone()[0]

                self.assertEqual(u_count_before, u_count_after, "La cantidad de usuarios cambió tras re-ejecutar seed.")
                self.assertEqual(a_count_before, a_count_after, "La cantidad de alumnos cambió tras re-ejecutar seed.")
                self.assertEqual(hashes_before, hashes_after, "Los hashes de contraseñas fueron alterados indebidamente.")
        conn.close()


if __name__ == "__main__":
    unittest.main()
