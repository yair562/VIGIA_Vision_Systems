"""
VIGIA_API
=========
Capa de Servicios de Comunicación Externa, Interfaces REST y WebSockets
de VIGÍA Vision Systems.

Provee el servicio de ingesta HTTP móvil (VO-03 / VO-03B) conectado al motor de
visión artificial VIGIA_Vision.
"""

from VIGIA_API.ingest_service import (
    create_ingest_app,
    generate_vigia_tls_certificate,
    run_ingest_server,
)

__all__ = [
    "create_ingest_app",
    "generate_vigia_tls_certificate",
    "run_ingest_server",
]
