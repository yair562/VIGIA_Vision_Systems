"""
VIGIA_Core.repository.user_repository
=====================================
Contrato de persistencia relacional y repositorio de usuarios para VIGÍA Vision Systems.

Implementa:
  - ``IUserRepository``: Protocolo canónico de acceso a datos de usuarios.
  - ``InMemoryUserRepository``: Implementación en memoria segura para pruebas unitarias.
  - ``PsycopgUserRepository``: Implementación concreta con ``psycopg2`` para PostgreSQL 16.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, List, Optional, Protocol, Sequence, runtime_checkable
from uuid import UUID

from VIGIA_Core.domain.user import UserDTO
from VIGIA_Core.repository.detection_repository import (
    DatabaseConnectionError,
    DatabasePersistenceError,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class IUserRepository(Protocol):
    """
    Protocolo de repositorio para la gestión y consulta de usuarios.
    """

    def get_by_username(self, username: str) -> Optional[UserDTO]:
        """Obtiene un usuario por su nombre de usuario (búsqueda sin distinción de mayúsculas)."""
        ...

    def get_by_id(self, user_id: UUID) -> Optional[UserDTO]:
        """Obtiene un usuario por su identificador primario UUID."""
        ...

    def create_user(self, user: UserDTO) -> UUID:
        """Persiste un nuevo usuario y retorna su id_usuario."""
        ...

    def list_users(self) -> Sequence[UserDTO]:
        """Retorna la lista de todos los usuarios registrados."""
        ...

    def deactivate_user(self, user_id: UUID) -> bool:
        """Desactiva un usuario (activo=False). Retorna True si existía."""
        ...


class InMemoryUserRepository:
    """
    Repositorio de usuarios en memoria, seguro para hilos, para pruebas y desarrollo.
    """

    def __init__(self, initial_users: Optional[Sequence[UserDTO]] = None) -> None:
        self._lock = threading.RLock()
        self._users_by_id: dict[UUID, UserDTO] = {}
        self._users_by_name: dict[str, UUID] = {}

        if initial_users:
            for u in initial_users:
                self.create_user(u)

    def get_by_username(self, username: str) -> Optional[UserDTO]:
        if not username:
            return None
        with self._lock:
            uid = self._users_by_name.get(username.strip().lower())
            if uid is None:
                return None
            return self._users_by_id.get(uid)

    def get_by_id(self, user_id: UUID) -> Optional[UserDTO]:
        if not isinstance(user_id, UUID):
            return None
        with self._lock:
            return self._users_by_id.get(user_id)

    def create_user(self, user: UserDTO) -> UUID:
        if not isinstance(user, UserDTO):
            raise TypeError("user debe ser una instancia de UserDTO.")
        with self._lock:
            lower_name = user.username.lower()
            if lower_name in self._users_by_name:
                raise DatabasePersistenceError(
                    f"El nombre de usuario '{user.username}' ya se encuentra registrado."
                )
            self._users_by_id[user.id_usuario] = user
            self._users_by_name[lower_name] = user.id_usuario
            return user.id_usuario

    def list_users(self) -> Sequence[UserDTO]:
        with self._lock:
            return list(self._users_by_id.values())

    def deactivate_user(self, user_id: UUID) -> bool:
        with self._lock:
            user = self._users_by_id.get(user_id)
            if user is None:
                return False
            updated = UserDTO(
                id_usuario=user.id_usuario,
                username=user.username,
                contrasena_hash=user.contrasena_hash,
                nombre_completo=user.nombre_completo,
                rol=user.rol,
                activo=False,
                creado_en=user.creado_en,
            )
            self._users_by_id[user_id] = updated
            return True


class PsycopgUserRepository:
    """
    Implementación concreta de ``IUserRepository`` sobre PostgreSQL utilizando ``psycopg2``.
    """

    _SELECT_FIELDS = (
        "id_usuario, username, contrasena_hash, nombre_completo, rol, activo, creado_en"
    )

    def __init__(self, dsn: str, connect_timeout: int = 5) -> None:
        self._dsn = dsn
        self._connect_timeout = connect_timeout
        try:
            import psycopg2  # noqa: F401
            import psycopg2.extras
            self._psycopg2 = psycopg2
            self._extras = psycopg2.extras
        except ImportError as exc:
            raise DatabaseConnectionError(
                "psycopg2 no está instalado en el entorno. "
                f"Error original: {exc}"
            ) from exc

    def _get_connection(self) -> Any:
        try:
            return self._psycopg2.connect(
                self._dsn,
                connect_timeout=self._connect_timeout,
            )
        except self._psycopg2.OperationalError as exc:
            raise DatabaseConnectionError(
                f"Fallo de conexión a PostgreSQL: {exc}"
            ) from exc

    def get_by_username(self, username: str) -> Optional[UserDTO]:
        if not username:
            return None
        sql = f"""
            SELECT {self._SELECT_FIELDS}
            FROM usuario
            WHERE LOWER(username) = LOWER(%(username)s)
            LIMIT 1;
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor(cursor_factory=self._extras.DictCursor) as cur:
                cur.execute(sql, {"username": username.strip()})
                row = cur.fetchone()
                if not row:
                    return None
                return self._row_to_dto(row)
        except self._psycopg2.OperationalError as exc:
            raise DatabaseConnectionError(f"Error relacional al consultar usuario: {exc}") from exc
        except Exception as exc:
            raise DatabasePersistenceError(f"Error al ejecutar consulta de usuario: {exc}") from exc
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def get_by_id(self, user_id: UUID) -> Optional[UserDTO]:
        if not isinstance(user_id, UUID):
            return None
        sql = f"""
            SELECT {self._SELECT_FIELDS}
            FROM usuario
            WHERE id_usuario = %(id_usuario)s
            LIMIT 1;
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor(cursor_factory=self._extras.DictCursor) as cur:
                cur.execute(sql, {"id_usuario": str(user_id)})
                row = cur.fetchone()
                if not row:
                    return None
                return self._row_to_dto(row)
        except self._psycopg2.OperationalError as exc:
            raise DatabaseConnectionError(f"Error relacional al consultar usuario por id: {exc}") from exc
        except Exception as exc:
            raise DatabasePersistenceError(f"Error al consultar usuario por id: {exc}") from exc
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def create_user(self, user: UserDTO) -> UUID:
        sql = """
            INSERT INTO usuario (
                id_usuario,
                username,
                contrasena_hash,
                nombre_completo,
                rol,
                activo
            ) VALUES (
                %(id_usuario)s,
                %(username)s,
                %(contrasena_hash)s,
                %(nombre_completo)s,
                %(rol)s,
                %(activo)s
            )
            RETURNING id_usuario;
        """
        params = {
            "id_usuario": str(user.id_usuario),
            "username": user.username,
            "contrasena_hash": user.contrasena_hash,
            "nombre_completo": user.nombre_completo,
            "rol": user.rol,
            "activo": user.activo,
        }
        conn = None
        try:
            conn = self._get_connection()
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    res = cur.fetchone()
                    return UUID(str(res[0]))
        except self._psycopg2.IntegrityError as exc:
            raise DatabasePersistenceError(f"Violación de integridad al crear usuario: {exc}") from exc
        except self._psycopg2.OperationalError as exc:
            raise DatabaseConnectionError(f"Error relacional al crear usuario: {exc}") from exc
        except Exception as exc:
            raise DatabasePersistenceError(f"Fallo al insertar usuario: {exc}") from exc
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def list_users(self) -> Sequence[UserDTO]:
        sql = f"""
            SELECT {self._SELECT_FIELDS}
            FROM usuario
            ORDER BY creado_en ASC;
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor(cursor_factory=self._extras.DictCursor) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
                return [self._row_to_dto(r) for r in rows]
        except self._psycopg2.OperationalError as exc:
            raise DatabaseConnectionError(f"Error relacional al listar usuarios: {exc}") from exc
        except Exception as exc:
            raise DatabasePersistenceError(f"Fallo al listar usuarios: {exc}") from exc
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def deactivate_user(self, user_id: UUID) -> bool:
        sql = """
            UPDATE usuario
            SET activo = FALSE
            WHERE id_usuario = %(id_usuario)s;
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql, {"id_usuario": str(user_id)})
                    return cur.rowcount > 0
        except self._psycopg2.OperationalError as exc:
            raise DatabaseConnectionError(f"Error relacional al desactivar usuario: {exc}") from exc
        except Exception as exc:
            raise DatabasePersistenceError(f"Fallo al desactivar usuario: {exc}") from exc
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _row_to_dto(self, row: Any) -> UserDTO:
        return UserDTO(
            id_usuario=UUID(str(row["id_usuario"])),
            username=row["username"],
            contrasena_hash=row["contrasena_hash"],
            nombre_completo=row["nombre_completo"],
            rol=row["rol"],
            activo=bool(row["activo"]),
            creado_en=row.get("creado_en"),
        )
