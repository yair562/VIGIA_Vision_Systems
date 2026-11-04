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
    ensure_crl_is_valid,
    generate_vigia_crl,
    generate_vigia_local_ca_bundle,
    generate_vigia_tls_certificate,
    revoke_certificate,
    run_ingest_server,
    start_crl_http_server,
)

__all__ = [
    "create_ingest_app",
    "ensure_crl_is_valid",
    "generate_vigia_crl",
    "generate_vigia_local_ca_bundle",
    "generate_vigia_tls_certificate",
    "revoke_certificate",
    "run_ingest_server",
    "start_crl_http_server",
]
