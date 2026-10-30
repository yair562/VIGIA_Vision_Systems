"""
VIGIA_API.security.auth_service
===============================
Servicio de autenticación para VIGÍA Vision Systems (ENR-02A).

Coordina la verificación criptográfica de contraseñas con Argon2id, la mitigación
de enumeración de usuarios por temporización y la creación de sesiones seguras.
"""

from __future__ import annotations

import logging
from typing import Optional

from VIGIA_API.security.session_manager import SessionManager, UserSession
from VIGIA_Core.domain.user import UserDTO
from VIGIA_Core.repository.user_repository import IUserRepository
from VIGIA_Core.security.password_hasher import DUMMY_ARGON2ID_HASH, verify_password

logger = logging.getLogger(__name__)


class AuthService:
    """
    Servicio de autenticación basado en repositorio de usuarios y gestor de sesiones.
    """

    def __init__(
        self,
        user_repository: IUserRepository,
        session_manager: SessionManager,
    ) -> None:
        self._user_repo = user_repository
        self._session_mgr = session_manager

    @property
    def user_repository(self) -> IUserRepository:
        return self._user_repo

    @property
    def session_manager(self) -> SessionManager:
        return self._session_mgr

    def authenticate(
        self,
        username: Optional[str],
        password: Optional[str],
        ttl_seconds: Optional[int] = None,
    ) -> Optional[UserSession]:
        """
        Autentica credenciales contra el repositorio y emite una sesión activa.

        Garantías:
        - Si el usuario no existe, ejecuta una verificación de costo idéntico contra
          un hash de relleno para evitar ataques de enumeración por temporización.
        - Si el usuario existe pero está inactivo, rechaza la autenticación sin revelar
          el estado interno.
        - Si las credenciales son válidas, emite y registra una ``UserSession``.
        """
        if not username or not password or not isinstance(username, str) or not isinstance(password, str):
            # Ejecutar verificación de relleno para mantener latencia similar
            verify_password(DUMMY_ARGON2ID_HASH, "dummy_fallback")
            return None

        clean_user = username.strip()
        user: Optional[UserDTO] = None
        try:
            user = self._user_repo.get_by_username(clean_user)
        except Exception as exc:
            logger.error("Error al consultar repositorio de usuarios: %s", exc)
            verify_password(DUMMY_ARGON2ID_HASH, password)
            return None

        if user is None:
            # Mitigación de timing attack ante usuarios inexistentes
            verify_password(DUMMY_ARGON2ID_HASH, password)
            return None

        # Si el usuario está deshabilitado administrativamente, rechazar
        if not user.activo:
            verify_password(user.contrasena_hash, password)
            logger.warning("Intento de login con usuario inactivo: '%s'", clean_user)
            return None

        # Verificación criptográfica real Argon2id
        is_valid = verify_password(user.contrasena_hash, password)
        if not is_valid:
            logger.warning("Contraseña incorrecta para el usuario: '%s'", clean_user)
            return None

        # Credenciales válidas: crear sesión
        session = self._session_mgr.create_session(user, ttl_seconds=ttl_seconds)
        logger.info(
            "Sesión iniciada exitosamente para '%s' con rol funcional '%s' (DB: '%s')",
            user.username,
            session.rol,
            session.db_rol,
        )
        return session
