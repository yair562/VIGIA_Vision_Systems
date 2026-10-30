"""
VIGIA_Core.domain.user
======================
Modelo de dominio canónico para usuarios del sistema VIGÍA Vision Systems.

Mapea fielmente contra las columnas y restricciones de integridad del esquema DDL V1
(tabla ``usuario`` en ``V001__baseline_schema.sql``):
  - ``id_usuario``: UUID (Primary Key)
  - ``username``: Cadena no vacía, sin espacios intermedios (máximo 50 caracteres)
  - ``contrasena_hash``: Hash Argon2id no vacío
  - ``nombre_completo``: Cadena no vacía (máximo 150 caracteres)
  - ``rol``: ``CHECK (rol IN ('ADMINISTRADOR', 'OPERADOR', 'AUDITOR'))``
  - ``activo``: Booleano (por omisión True)
  - ``creado_en``: Marca temporal TIMESTAMPTZ

Mapeo funcional (ENR-02A):
  - El rol relacional ``'OPERADOR'`` se mapea funcionalmente a ``'GUARDIA'``
    a través de la propiedad ``functional_role``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

_VALID_DB_ROLES = frozenset({"ADMINISTRADOR", "OPERADOR", "AUDITOR"})
_WHITESPACE_REGEX = re.compile(r"\s")


@dataclass(frozen=True)
class UserDTO:
    """
    DTO inmutable que representa a un usuario autenticable del sistema VIGÍA.
    """

    username: str
    contrasena_hash: str
    nombre_completo: str
    rol: str
    id_usuario: UUID = None  # type: ignore
    activo: bool = True
    creado_en: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.id_usuario is None:
            object.__setattr__(self, "id_usuario", uuid4())
        elif not isinstance(self.id_usuario, UUID):
            raise TypeError("id_usuario debe ser una instancia válida de uuid.UUID.")

        if not isinstance(self.username, str) or not self.username.strip():
            raise ValueError("username no puede ser nulo ni cadena vacía.")
        trimmed_user = self.username.strip()
        if _WHITESPACE_REGEX.search(trimmed_user):
            raise ValueError(f"username '{trimmed_user}' no debe contener espacios en blanco.")
        if len(trimmed_user) > 50:
            raise ValueError("username no puede exceder 50 caracteres.")
        object.__setattr__(self, "username", trimmed_user)

        if not isinstance(self.contrasena_hash, str) or not self.contrasena_hash.strip():
            raise ValueError("contrasena_hash no puede ser nulo ni cadena vacía.")
        object.__setattr__(self, "contrasena_hash", self.contrasena_hash.strip())

        if not isinstance(self.nombre_completo, str) or not self.nombre_completo.strip():
            raise ValueError("nombre_completo no puede ser nulo ni cadena vacía.")
        trimmed_nombre = self.nombre_completo.strip()
        if len(trimmed_nombre) > 150:
            raise ValueError("nombre_completo no puede exceder 150 caracteres.")
        object.__setattr__(self, "nombre_completo", trimmed_nombre)

        if not isinstance(self.rol, str):
            raise TypeError("rol debe ser una cadena de texto.")
        normalized_rol = self.rol.strip().upper()
        # Permitir que el constructor acepte 'GUARDIA' y lo normalice transparentemente a 'OPERADOR'
        if normalized_rol == "GUARDIA":
            normalized_rol = "OPERADOR"

        if normalized_rol not in _VALID_DB_ROLES:
            raise ValueError(
                f"rol '{normalized_rol}' inválido. Debe pertenecer a {_VALID_DB_ROLES}."
            )
        object.__setattr__(self, "rol", normalized_rol)

        if not isinstance(self.activo, bool):
            raise TypeError("activo debe ser un booleano.")

    @property
    def functional_role(self) -> str:
        """
        Retorna la denominación funcional del rol para el dominio VIGÍA:
        - ``'OPERADOR'`` -> ``'GUARDIA'``
        - ``'ADMINISTRADOR'`` -> ``'ADMINISTRADOR'``
        - ``'AUDITOR'`` -> ``'AUDITOR'``
        """
        if self.rol == "OPERADOR":
            return "GUARDIA"
        return self.rol
