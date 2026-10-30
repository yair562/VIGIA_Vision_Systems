"""
VIGIA_API.security.session_manager
==================================
Gestor de sesiones seguras en memoria para VIGÍA Vision Systems (ENR-02A).

Garantías de seguridad:
  - Generación de tokens opacos y criptográficamente aleatorios (256 bits de entropía).
  - Almacenamiento seguro del estado de sesión en el servidor (el cliente no puede alterar
    su rol ni falsificar privilegios).
  - Expiración temporal automática y revocación inmediata de sesiones (logout).
  - Operaciones atómicas y seguras para hilos concurrentes.
"""

from __future__ import annotations

import logging
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from uuid import UUID

from VIGIA_Core.domain.user import UserDTO

logger = logging.getLogger(__name__)

DEFAULT_SESSION_TTL_SECONDS = 8 * 60 * 60  # 8 horas


@dataclass(frozen=True)
class UserSession:
    """
    Representa una sesión autenticada activa en el servidor.
    """

    token: str
    user_id: UUID
    username: str
    nombre_completo: str
    rol: str       # Rol funcional ('ADMINISTRADOR', 'GUARDIA', 'AUDITOR')
    db_rol: str    # Rol DDL ('ADMINISTRADOR', 'OPERADOR', 'AUDITOR')
    created_at: datetime
    expires_at: datetime

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """Determina si la sesión ha superado su tiempo de vida."""
        current_time = now or datetime.now(timezone.utc)
        return current_time >= self.expires_at


class SessionManager:
    """
    Registro y administrador de sesiones en el lado del servidor.
    """

    def __init__(self, default_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS) -> None:
        if default_ttl_seconds <= 0:
            raise ValueError("default_ttl_seconds debe ser mayor a 0.")
        self._default_ttl = int(default_ttl_seconds)
        self._lock = threading.RLock()
        self._sessions: Dict[str, UserSession] = {}

    @property
    def default_ttl_seconds(self) -> int:
        return self._default_ttl

    def create_session(
        self,
        user: UserDTO,
        ttl_seconds: Optional[int] = None,
    ) -> UserSession:
        """
        Crea y registra una nueva sesión para el usuario indicado.
        """
        if not isinstance(user, UserDTO):
            raise TypeError("user debe ser una instancia de UserDTO.")

        ttl = int(ttl_seconds) if ttl_seconds is not None else self._default_ttl
        if ttl <= 0:
            raise ValueError("ttl debe ser mayor a 0.")

        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl)

        session = UserSession(
            token=token,
            user_id=user.id_usuario,
            username=user.username,
            nombre_completo=user.nombre_completo,
            rol=user.functional_role,
            db_rol=user.rol,
            created_at=now,
            expires_at=expires_at,
        )

        with self._lock:
            self._sessions[token] = session

        return session

    def get_session(self, token: Optional[str]) -> Optional[UserSession]:
        """
        Obtiene y valida una sesión activa por su token.
        Si la sesión expiró, la elimina del registro y retorna None.
        """
        if not token or not isinstance(token, str):
            return None

        clean_token = token.strip()
        with self._lock:
            session = self._sessions.get(clean_token)
            if session is None:
                return None

            if session.is_expired():
                # Purga inmediata de sesión expirada
                self._sessions.pop(clean_token, None)
                return None

            return session

    def revoke_session(self, token: Optional[str]) -> bool:
        """
        Revoca inmediatamente una sesión activa (logout).
        """
        if not token or not isinstance(token, str):
            return False

        clean_token = token.strip()
        with self._lock:
            return self._sessions.pop(clean_token, None) is not None

    def revoke_user_sessions(self, user_id: UUID) -> int:
        """
        Revoca todas las sesiones asociadas a un identificador de usuario.
        """
        if not isinstance(user_id, UUID):
            return 0

        revoked_count = 0
        with self._lock:
            tokens_to_remove = [
                tok for tok, sess in self._sessions.items() if sess.user_id == user_id
            ]
            for tok in tokens_to_remove:
                self._sessions.pop(tok, None)
                revoked_count += 1

        return revoked_count

    def clean_expired(self) -> int:
        """
        Limpia todas las sesiones vencidas registradas en memoria.
        """
        now = datetime.now(timezone.utc)
        removed_count = 0
        with self._lock:
            expired_tokens = [
                tok for tok, sess in self._sessions.items() if sess.is_expired(now)
            ]
            for tok in expired_tokens:
                self._sessions.pop(tok, None)
                removed_count += 1
        return removed_count

    def active_sessions_count(self) -> int:
        """Retorna el total de sesiones registradas (incluidas las que podrían no haberse purgado)."""
        with self._lock:
            return len(self._sessions)
