"""
VIGIA_Core.security.password_hasher
===================================
Funciones canónicas de derivación y verificación de contraseñas mediante Argon2id
para VIGÍA Vision Systems, cumpliendo estrictamente con la invariante de seguridad
especificada en el esquema DDL V1 (V001__baseline_schema.sql) y DOC-01.

Utiliza la implementación estándar Argon2id provista por PyNaCl / libsodium.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import nacl.exceptions
    import nacl.pwhash.argon2id
    _NACL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _NACL_AVAILABLE = False
    nacl = None  # type: ignore

# Hash sintético válido para comparación de tiempo constante ante usuarios inexistentes
DUMMY_ARGON2ID_HASH = (
    "$argon2id$v=19$m=65536,t=2,p=1$7sBWiBPwQuYfbe/sxxIqgg$8FHHXWg+FKSSuhjME/XwtgMnncs+cAbLRTZvHGNktzM"
)


class PasswordHashingError(RuntimeError):
    """Excepción técnica ante fallos de la biblioteca criptográfica Argon2id."""


def hash_password(password: str) -> str:
    """
    Deriva un hash criptográfico modular PHC utilizando Argon2id.

    Parámetros
    ----------
    password : str
        Contraseña en texto plano a derivar.

    Retorna
    -------
    str
        Cadena con formato PHC estándar Argon2id (ej. ``$argon2id$v=19$m=65536,t=2,p=1$...``).

    Lanza
    -----
    ValueError
        Si la contraseña es nula, vacía o no es una cadena de texto.
    PasswordHashingError
        Si la biblioteca criptográfica subyacente no está disponible.
    """
    if not isinstance(password, str) or not password:
        raise ValueError("La contraseña debe ser una cadena de texto no vacía.")

    if not _NACL_AVAILABLE:  # pragma: no cover
        raise PasswordHashingError(
            "La biblioteca PyNaCl (nacl.pwhash.argon2id) no está disponible en el entorno."
        )

    try:
        raw_hash: bytes = nacl.pwhash.argon2id.str(password.encode("utf-8"))
        return raw_hash.decode("utf-8")
    except Exception as exc:  # pragma: no cover
        logger.error("Error inesperado derivando hash Argon2id: %s", exc, exc_info=True)
        raise PasswordHashingError(f"Fallo al generar hash Argon2id: {exc}") from exc


def verify_password(hash_str: Optional[str], password: Optional[str]) -> bool:
    """
    Verifica una contraseña en texto plano contra un hash Argon2id en tiempo constante.

    Parámetros
    ----------
    hash_str : Optional[str]
        Hash PHC almacenado en la base de datos.
    password : Optional[str]
        Contraseña en texto plano provista por el usuario.

    Retorna
    -------
    bool
        ``True`` si la contraseña coincide exactamente con el hash, ``False`` en cualquier
        otro caso (incluyendo hash inválido, contraseña incorrecta o argumentos nulos).
    """
    if not hash_str or not password:
        return False

    if not isinstance(hash_str, str) or not isinstance(password, str):
        return False

    if not _NACL_AVAILABLE:  # pragma: no cover
        logger.error("No se puede verificar contraseña: PyNaCl no disponible.")
        return False

    try:
        return bool(
            nacl.pwhash.verify(
                hash_str.strip().encode("utf-8"),
                password.encode("utf-8"),
            )
        )
    except (
        nacl.exceptions.InvalidkeyError,
        nacl.exceptions.CryptoError,
        ValueError,
        TypeError,
    ):
        return False
    except Exception as exc:  # pragma: no cover
        logger.warning("Fallo inesperado durante verificación Argon2id: %s", exc)
        return False
