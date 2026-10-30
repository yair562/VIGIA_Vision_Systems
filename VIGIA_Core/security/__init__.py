"""
VIGIA_Core.security
===================
Módulo de seguridad criptográfica y gestión de contraseñas de VIGÍA Vision Systems.
"""

from VIGIA_Core.security.password_hasher import hash_password, verify_password

__all__ = ["hash_password", "verify_password"]
