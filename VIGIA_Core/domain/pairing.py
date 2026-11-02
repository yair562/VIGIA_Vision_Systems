"""
VIGIA_Core.domain.pairing
=========================
Modelos de dominio inmutables para el flujo de enrolamiento QR
y credenciales de dispositivos móviles (MOB-QR-01 / ENR-02B-D).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID


class PairingRequestState(str, Enum):
    CREADA = "CREADA"
    PENDIENTE = "PENDIENTE"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"
    EXPIRADA = "EXPIRADA"
    CANCELADA = "CANCELADA"
    CONSUMIDA = "CONSUMIDA"


@dataclass(frozen=True)
class PairingRequestDTO:
    id_solicitud: UUID
    id_camara: UUID
    token_claim_hash: str
    token_poll_hash: Optional[str]
    estado: PairingRequestState
    dispositivo_info: Optional[Dict[str, Any]]
    creado_por: UUID
    resuelto_por: Optional[UUID]
    motivo_rechazo: Optional[str]
    creado_en: datetime
    expira_en: datetime
    reclamado_en: Optional[datetime]
    resuelto_en: Optional[datetime]
    consumido_en: Optional[datetime]
    cancelado_en: Optional[datetime]


@dataclass(frozen=True)
class CameraCredentialDTO:
    id_credencial: UUID
    id_camara: UUID
    id_solicitud: UUID
    token_transmision_hash: str
    clave_cifrado_id: str
    credencial_cifrada: Optional[str]
    intentos_entrega: int
    entregado_en: Optional[datetime]
    activa: bool
    revocado_por: Optional[UUID]
    motivo_revocacion: Optional[str]
    creado_en: datetime
    activado_en: datetime
    revocado_en: Optional[datetime]


@dataclass(frozen=True)
class ActiveDeviceDTO:
    """Proyección de dispositivo físico activo para el Dashboard."""
    id_credencial: UUID
    id_camara: UUID
    codigo_camara: str
    nombre_camara: str
    nombre_dispositivo: str
    dispositivo_info: Optional[Dict[str, Any]]
    activado_en: datetime
    activa: bool
    ultima_actividad: Optional[datetime] = None
