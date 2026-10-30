"""
tests.unit.test_auth_rbac
=========================
Pruebas unitarias y de integración para la arquitectura de autenticación y autorización
RBAC de VIGÍA Vision Systems (ENR-02A).

Cobertura requerida:
- PU-AUTH-01: Derivación y verificación criptográfica de contraseñas con Argon2id.
- PU-AUTH-02: Rechazo de formatos inválidos o corruptos en Argon2id.
- PU-AUTH-03: Modelo UserDTO e invariantes de dominio (nombre, espacios, roles DDL).
- PU-AUTH-04: Mapeo funcional canónico: rol DDL 'OPERADOR' -> rol funcional 'GUARDIA'.
- PU-AUTH-05: Repositorio de usuarios en memoria (IUserRepository).
- PU-AUTH-06: Repositorio PsycopgUserRepository con driver simulado (mock).
- PU-AUTH-07: Ciclo de vida de sesiones (SessionManager): creación, expiración y purga.
- PU-AUTH-08: Revocación explícita de sesiones en servidor (logout).
- PU-AUTH-09: Login válido de ADMINISTRADOR (HTTP 200, emisión de token seguro).
- PU-AUTH-10: Login válido de GUARDIA (HTTP 200, rol funcional 'GUARDIA').
- PU-AUTH-11: Rechazo de contraseña incorrecta (HTTP 401, error genérico).
- PU-AUTH-12: Rechazo de usuario inexistente (HTTP 401, sin revelar existencia de cuenta).
- PU-AUTH-13: Rechazo de usuario inactivo (HTTP 401).
- PU-AUTH-14: Acceso a endpoints protegidos sin autenticación (HTTP 401).
- PU-AUTH-15: Acceso de supervisión con rol GUARDIA (HTTP 200).
- PU-AUTH-16: Acceso de supervisión con rol ADMINISTRADOR (HTTP 200).
- PU-AUTH-17: Rechazo de acceso administrativo para rol GUARDIA (HTTP 403 Forbidden).
- PU-AUTH-18: Prevención de manipulación del rol desde el cliente (tampering).
- PU-AUTH-19: Rechazo de token de sesión expirado (HTTP 401).
- PU-AUTH-20: Verificación de sesión revocada tras logout (HTTP 401).
- PU-AUTH-21: Restricción del rol AUDITOR ante operaciones administrativas (HTTP 403).
"""

from __future__ import annotations

import json
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

# Asegurar raíz del repositorio en sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from VIGIA_API.ingest_service import create_ingest_app
from VIGIA_API.security.auth_service import AuthService
from VIGIA_API.security.session_manager import SessionManager, UserSession
from VIGIA_Core.domain.user import UserDTO
from VIGIA_Core.repository.detection_repository import DatabaseConnectionError, DatabasePersistenceError
from VIGIA_Core.repository.user_repository import (
    IUserRepository,
    InMemoryUserRepository,
    PsycopgUserRepository,
)
from VIGIA_Core.security.password_hasher import (
    DUMMY_ARGON2ID_HASH,
    hash_password,
    verify_password,
)


class TestArgon2PasswordHasher(unittest.TestCase):
    """Pruebas para el derivador y validador de contraseñas Argon2id."""

    def test_pu_auth_01_hash_and_verify_valid(self):
        """PU-AUTH-01: Genera un hash PHC Argon2id válido y lo verifica exitosamente."""
        pwd = "AdminSecurePass2026!"
        h = hash_password(pwd)
        self.assertTrue(h.startswith("$argon2id$v=19$"))
        self.assertTrue(verify_password(h, pwd))

    def test_pu_auth_01b_verify_wrong_password(self):
        """PU-AUTH-01b: Falla de forma segura ante contraseña incorrecta."""
        pwd = "AdminSecurePass2026!"
        h = hash_password(pwd)
        self.assertFalse(verify_password(h, "WrongPassword2026!"))

    def test_pu_auth_02_invalid_inputs(self):
        """PU-AUTH-02: Rechaza entradas nulas, vacías o de tipo incorrecto sin excepciones no controladas."""
        with self.assertRaises(ValueError):
            hash_password("")
        with self.assertRaises(ValueError):
            hash_password(None)  # type: ignore

        self.assertFalse(verify_password(None, "pass"))
        self.assertFalse(verify_password("hash", None))
        self.assertFalse(verify_password("", ""))
        self.assertFalse(verify_password("corrupted$not$a$hash", "pwd"))


class TestUserDTO(unittest.TestCase):
    """Pruebas del modelo UserDTO y mapeo funcional de roles."""

    def test_pu_auth_03_valid_admin_user(self):
        """PU-AUTH-03: Creación de UserDTO para ADMINISTRADOR."""
        uid = uuid4()
        user = UserDTO(
            id_usuario=uid,
            username="admin_user",
            contrasena_hash=DUMMY_ARGON2ID_HASH,
            nombre_completo="Administrador de Caseta",
            rol="ADMINISTRADOR",
            activo=True,
        )
        self.assertEqual(user.id_usuario, uid)
        self.assertEqual(user.username, "admin_user")
        self.assertEqual(user.rol, "ADMINISTRADOR")
        self.assertEqual(user.functional_role, "ADMINISTRADOR")
        self.assertTrue(user.activo)

    def test_pu_auth_04_mapping_operador_to_guardia(self):
        """PU-AUTH-04: Mapeo funcional de 'OPERADOR' relacional a 'GUARDIA'."""
        user = UserDTO(
            username="guardia1",
            contrasena_hash=DUMMY_ARGON2ID_HASH,
            nombre_completo="Guardia Vigilante",
            rol="OPERADOR",
        )
        self.assertEqual(user.rol, "OPERADOR")  # Respeto estricto del DDL
        self.assertEqual(user.functional_role, "GUARDIA")  # Dominio funcional

    def test_pu_auth_04b_constructor_accepts_guardia_alias(self):
        """PU-AUTH-04b: El constructor acepta 'GUARDIA' y lo normaliza a 'OPERADOR'."""
        user = UserDTO(
            username="guardia2",
            contrasena_hash=DUMMY_ARGON2ID_HASH,
            nombre_completo="Segundo Guardia",
            rol="GUARDIA",
        )
        self.assertEqual(user.rol, "OPERADOR")
        self.assertEqual(user.functional_role, "GUARDIA")

    def test_pu_auth_03b_invalid_invariants(self):
        """PU-AUTH-03b: Invariantes de nombre con espacios, cadena vacía y rol no permitido."""
        with self.assertRaises(ValueError):
            UserDTO(username="user name", contrasena_hash="h", nombre_completo="N", rol="ADMINISTRADOR")
        with self.assertRaises(ValueError):
            UserDTO(username="", contrasena_hash="h", nombre_completo="N", rol="ADMINISTRADOR")
        with self.assertRaises(ValueError):
            UserDTO(username="valid", contrasena_hash="h", nombre_completo="N", rol="SUPERUSER")


class TestUserRepository(unittest.TestCase):
    """Pruebas del repositorio de usuarios en memoria y con mock de base de datos."""

    def test_pu_auth_05_in_memory_repository_crud(self):
        """PU-AUTH-05: Operaciones básicas sobre InMemoryUserRepository."""
        repo = InMemoryUserRepository()
        user = UserDTO(
            username="test_user",
            contrasena_hash=DUMMY_ARGON2ID_HASH,
            nombre_completo="Usuario de Prueba",
            rol="OPERADOR",
        )
        uid = repo.create_user(user)
        self.assertEqual(uid, user.id_usuario)

        # Búsqueda case-insensitive
        by_name = repo.get_by_username("TEST_USER")
        self.assertIsNotNone(by_name)
        self.assertEqual(by_name.username, "test_user")

        # Búsqueda por id
        by_id = repo.get_by_id(uid)
        self.assertIsNotNone(by_id)

        # Desactivación
        deact_ok = repo.deactivate_user(uid)
        self.assertTrue(deact_ok)
        updated = repo.get_by_id(uid)
        self.assertFalse(updated.activo)

        # Intento de duplicado
        with self.assertRaises(DatabasePersistenceError):
            repo.create_user(user)

    def test_pu_auth_06_psycopg_user_repository_mock(self):
        """PU-AUTH-06: Verificación de PsycopgUserRepository usando conexión simulada."""
        mock_psycopg2 = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        mock_psycopg2.connect.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        uid = uuid4()
        mock_cursor.fetchone.return_value = {
            "id_usuario": uid,
            "username": "sql_admin",
            "contrasena_hash": DUMMY_ARGON2ID_HASH,
            "nombre_completo": "Admin SQL",
            "rol": "ADMINISTRADOR",
            "activo": True,
            "creado_en": datetime.now(timezone.utc),
        }

        with patch.dict("sys.modules", {"psycopg2": mock_psycopg2, "psycopg2.extras": MagicMock()}):
            repo = PsycopgUserRepository(dsn="mock_dsn")
            user = repo.get_by_username("sql_admin")
            self.assertIsNotNone(user)
            self.assertEqual(user.username, "sql_admin")
            self.assertEqual(user.rol, "ADMINISTRADOR")


class TestSessionManager(unittest.TestCase):
    """Pruebas del ciclo de vida de sesiones de usuario en el servidor."""

    def setUp(self):
        self.mgr = SessionManager(default_ttl_seconds=3600)
        self.user = UserDTO(
            username="operador_casetas",
            contrasena_hash=DUMMY_ARGON2ID_HASH,
            nombre_completo="Operador 1",
            rol="OPERADOR",
        )

    def test_pu_auth_07_session_creation_and_expiration(self):
        """PU-AUTH-07: Creación de sesión, verificación de vigencia y purga al expirar."""
        # Sesión de 1 segundo
        session = self.mgr.create_session(self.user, ttl_seconds=1)
        self.assertIsNotNone(session.token)
        self.assertEqual(session.rol, "GUARDIA")
        self.assertEqual(session.db_rol, "OPERADOR")

        # Inmediatamente válida
        retrieved = self.mgr.get_session(session.token)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.username, "operador_casetas")

        # Simular expiración forzando el timestamp
        expired_time = datetime.now(timezone.utc) + timedelta(seconds=5)
        self.assertTrue(session.is_expired(now=expired_time))

        # Al esperar más de 1 segundo real, get_session debe purgarla
        time.sleep(1.1)
        self.assertIsNone(self.mgr.get_session(session.token))

    def test_pu_auth_08_explicit_revocation(self):
        """PU-AUTH-08: Revocación explícita (logout)."""
        session = self.mgr.create_session(self.user)
        self.assertIsNotNone(self.mgr.get_session(session.token))

        revoked = self.mgr.revoke_session(session.token)
        self.assertTrue(revoked)
        self.assertIsNone(self.mgr.get_session(session.token))


class TestAuthRBACIntegration(unittest.TestCase):
    """Pruebas de integración HTTP de autenticación y autorización RBAC sobre VIGIA_API."""

    @classmethod
    def setUpClass(cls):
        # Hashes reales derivados con Argon2id para pruebas de autenticación
        cls.pwd_admin = "AdminPass2026!"
        cls.pwd_guardia = "GuardiaPass2026!"
        cls.pwd_auditor = "AuditorPass2026!"

        cls.hash_admin = hash_password(cls.pwd_admin)
        cls.hash_guardia = hash_password(cls.pwd_guardia)
        cls.hash_auditor = hash_password(cls.pwd_auditor)

    def setUp(self):
        self.user_repo = InMemoryUserRepository()
        self.session_mgr = SessionManager(default_ttl_seconds=3600)
        self.auth_svc = AuthService(user_repository=self.user_repo, session_manager=self.session_mgr)

        # Usuarios iniciales
        self.admin_user = UserDTO(
            username="admin",
            contrasena_hash=self.hash_admin,
            nombre_completo="Administrador Principal",
            rol="ADMINISTRADOR",
            activo=True,
        )
        self.guardia_user = UserDTO(
            username="guardia1",
            contrasena_hash=self.hash_guardia,
            nombre_completo="Guardia Caseta Norte",
            rol="OPERADOR",
            activo=True,
        )
        self.auditor_user = UserDTO(
            username="auditor1",
            contrasena_hash=self.hash_auditor,
            nombre_completo="Auditor Institucional",
            rol="AUDITOR",
            activo=True,
        )
        self.inactive_user = UserDTO(
            username="inactivo",
            contrasena_hash=self.hash_guardia,
            nombre_completo="Guardia Baja Temporal",
            rol="OPERADOR",
            activo=False,
        )

        self.user_repo.create_user(self.admin_user)
        self.user_repo.create_user(self.guardia_user)
        self.user_repo.create_user(self.auditor_user)
        self.user_repo.create_user(self.inactive_user)

        self.app = create_ingest_app(
            user_repository=self.user_repo,
            session_manager=self.session_mgr,
            auth_service=self.auth_svc,
            auth_token="LEGACY_TEST_KEY_123",
        )
        self.client = self.app.test_client()

    def _login(self, username: str, password: str):
        return self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"username": username, "password": password}),
            content_type="application/json",
        )

    # -------------------------------------------------------------------------
    # Pruebas de Login
    # -------------------------------------------------------------------------

    def test_pu_auth_09_login_admin_success(self):
        """PU-AUTH-09: Login válido de administrador entrega HTTP 200 y rol ADMINISTRADOR."""
        resp = self._login("admin", self.pwd_admin)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("token", data)
        self.assertEqual(data["user"]["username"], "admin")
        self.assertEqual(data["user"]["rol"], "ADMINISTRADOR")

    def test_pu_auth_10_login_guardia_success(self):
        """PU-AUTH-10: Login válido de guardia entrega HTTP 200 y rol funcional GUARDIA."""
        resp = self._login("guardia1", self.pwd_guardia)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("token", data)
        self.assertEqual(data["user"]["username"], "guardia1")
        self.assertEqual(data["user"]["rol"], "GUARDIA")

    def test_pu_auth_11_wrong_password(self):
        """PU-AUTH-11: Contraseña incorrecta devuelve HTTP 401 con mensaje genérico."""
        resp = self._login("admin", "IncorrectPassword!")
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "INVALID_CREDENTIALS")

    def test_pu_auth_12_nonexistent_user(self):
        """PU-AUTH-12: Usuario inexistente devuelve HTTP 401 sin revelar existencia."""
        resp = self._login("usuario_no_registrado", "CualquierPass123!")
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "INVALID_CREDENTIALS")

    def test_pu_auth_13_inactive_user(self):
        """PU-AUTH-13: Usuario inactivo administrativamente es rechazado con HTTP 401."""
        resp = self._login("inactivo", self.pwd_guardia)
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "INVALID_CREDENTIALS")

    # -------------------------------------------------------------------------
    # Pruebas de Autorización y Matriz RBAC
    # -------------------------------------------------------------------------

    def test_pu_auth_14_unauthenticated_access(self):
        """PU-AUTH-14: Intento de acceso a endpoints protegidos sin sesión entrega HTTP 401."""
        # /auth/me
        resp = self.client.get("/api/v1/auth/me")
        self.assertEqual(resp.status_code, 401)

        # /supervision/status
        resp = self.client.get("/api/v1/supervision/status")
        self.assertEqual(resp.status_code, 401)

        # /admin/users
        resp = self.client.get("/api/v1/admin/users")
        self.assertEqual(resp.status_code, 401)

    def test_pu_auth_15_supervision_access_guardia(self):
        """PU-AUTH-15: Acceso a supervisión operativo con rol GUARDIA entrega HTTP 200."""
        login_res = self._login("guardia1", self.pwd_guardia).get_json()
        token = login_res["token"]

        resp = self.client.get(
            "/api/v1/supervision/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["role"], "GUARDIA")

    def test_pu_auth_16_supervision_access_admin(self):
        """PU-AUTH-16: Acceso a supervisión operativo con rol ADMINISTRADOR entrega HTTP 200."""
        login_res = self._login("admin", self.pwd_admin).get_json()
        token = login_res["token"]

        resp = self.client.get(
            "/api/v1/supervision/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["role"], "ADMINISTRADOR")

    def test_pu_auth_17_admin_access_denied_for_guardia(self):
        """PU-AUTH-17: Guardia intentando acceder a endpoints administrativos recibe HTTP 403 Forbidden."""
        login_res = self._login("guardia1", self.pwd_guardia).get_json()
        token = login_res["token"]

        # 1. Intentar listar usuarios
        resp = self.client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json()["error"], "FORBIDDEN")

        # 2. Intentar crear un usuario
        resp_post = self.client.post(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            data=json.dumps({
                "username": "hacker_user",
                "password": "Password123!",
                "nombre_completo": "Intento Ilegal",
                "rol": "ADMINISTRADOR",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp_post.status_code, 403)

    def test_pu_auth_18_client_role_tampering_prevented(self):
        """PU-AUTH-18: Manipulación de rol desde el cliente es ignorada (servidor manda)."""
        login_res = self._login("guardia1", self.pwd_guardia).get_json()
        token = login_res["token"]

        # El cliente envía headers o parámetros pretendiendo ser ADMINISTRADOR
        resp = self.client.get(
            "/api/v1/admin/users?role=ADMINISTRADOR",
            headers={
                "Authorization": f"Bearer {token}",
                "X-User-Role": "ADMINISTRADOR",
                "X-Role": "ADMINISTRADOR",
            },
        )
        # El servidor consulta su SessionManager interno, detecta que es GUARDIA y responde 403
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json()["error"], "FORBIDDEN")

    def test_pu_auth_19_session_expired(self):
        """PU-AUTH-19: Sesión con tiempo vencido es rechazada con HTTP 401."""
        # Creamos una sesión con TTL de 1 segundo
        sess = self.session_mgr.create_session(self.admin_user, ttl_seconds=1)
        token = sess.token

        time.sleep(1.1)

        resp = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.get_json()["error"], "UNAUTHORIZED")

    def test_pu_auth_20_session_revocation_logout(self):
        """PU-AUTH-20: Cierre de sesión (logout) invalida el token para peticiones posteriores."""
        login_res = self._login("admin", self.pwd_admin).get_json()
        token = login_res["token"]

        # Validar que inicialmente funciona
        me_resp = self.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_resp.status_code, 200)

        # Ejecutar logout
        logout_resp = self.client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(logout_resp.status_code, 200)

        # Intento posterior debe ser 401
        after_resp = self.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(after_resp.status_code, 401)

    def test_pu_auth_21_auditor_role_restrictions(self):
        """PU-AUTH-21: Rol AUDITOR no obtiene permisos de escritura administrativa por defecto."""
        login_res = self._login("auditor1", self.pwd_auditor).get_json()
        token = login_res["token"]

        # Intentar crear usuario
        resp = self.client.post(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            data=json.dumps({
                "username": "nuevo_usuario",
                "password": "Password123!",
                "nombre_completo": "Nuevo",
                "rol": "OPERADOR",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
