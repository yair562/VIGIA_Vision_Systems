"""
VIGIA_Core.domain.access_decision
===================================
Modelos canónicos para la decisión de acceso y los estados de la interfaz del guardia.

Reglas de diseño:
- Inmutable (frozen dataclass).
- Separa explícitamente la decisión lógica de la acción física.
- No asume que la orden de hardware se ejecutó.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID


class AccessResult(str, Enum):
    """Decisión de acceso tomada por VIGIA_Core."""
    PERMITIDO = "PERMITIDO"
    DENEGADO  = "DENEGADO"


class TipoMovimiento(str, Enum):
    ENTRADA = "ENTRADA"
    SALIDA  = "SALIDA"


class TipoAcceso(str, Enum):
    AUTOMATICO         = "AUTOMATICO"
    MANUAL_SUPERVISADO = "MANUAL_SUPERVISADO"


class MotivoDecision(str, Enum):
    """
    Justificaciones compatibles con el CHECK constraint del DDL V1.

    NOTA: SIN_ASOCIACION_AUTORIZADA y PERSONA_INACTIVA no están en el DDL V1.
    En V1 ambos se mapean a VEHICULO_INACTIVO con observaciones explicativas.
    Están incluidos aquí para documentar la intención semántica y facilitar
    la migración cuando el esquema se amplíe.
    """
    # DDL V1 — disponibles sin migración
    VEHICULO_AUTORIZADO  = "VEHICULO_AUTORIZADO"
    VISITA_JUSTIFICADA   = "VISITA_JUSTIFICADA"
    PLACA_NO_REGISTRADA  = "PLACA_NO_REGISTRADA"
    VEHICULO_INACTIVO    = "VEHICULO_INACTIVO"
    APERTURA_EMERGENCIA  = "APERTURA_EMERGENCIA"
    PLACA_ILEGIBLE_MANUAL = "PLACA_ILEGIBLE_MANUAL"
    TIMEOUT_PASO         = "TIMEOUT_PASO"
    OBSTACULO_SENSOR     = "OBSTACULO_SENSOR"

    # Pendientes de migración DDL (documentados, no persisten en V1)
    SIN_ASOCIACION_AUTORIZADA = "SIN_ASOCIACION_AUTORIZADA"  # → VEHICULO_INACTIVO en V1
    PERSONA_INACTIVA          = "PERSONA_INACTIVA"           # → VEHICULO_INACTIVO en V1

    def ddl_v1_safe(self) -> "MotivoDecision":
        """
        Retorna el motivo equivalente compatible con el CHECK del DDL V1.
        Usa esto antes de persistir en evento_acceso.
        """
        _map = {
            MotivoDecision.SIN_ASOCIACION_AUTORIZADA: MotivoDecision.VEHICULO_INACTIVO,
            MotivoDecision.PERSONA_INACTIVA:          MotivoDecision.VEHICULO_INACTIVO,
        }
        return _map.get(self, self)


class AccessState(str, Enum):
    """
    Estado operativo para la interfaz del guardia.
    Un estado por cada situación distinguible según el flujo de 8 pasos.
    """
    PROCESANDO              = "PROCESANDO"
    VEHICULO_NO_DETECTADO   = "VEHICULO_NO_DETECTADO"
    PLACA_LEGIBLE           = "PLACA_LEGIBLE"
    PLACA_ILEGIBLE          = "PLACA_ILEGIBLE"
    PLACA_NO_REGISTRADA     = "PLACA_NO_REGISTRADA"
    VEHICULO_INACTIVO       = "VEHICULO_INACTIVO"
    SIN_AUTORIZACION        = "SIN_AUTORIZACION"
    ACCESO_PERMITIDO        = "ACCESO_PERMITIDO"
    ACCESO_DENEGADO         = "ACCESO_DENEGADO"
    ERROR_CAMARA            = "ERROR_CAMARA"
    ERROR_VISION            = "ERROR_VISION"
    ERROR_BASE_DATOS        = "ERROR_BASE_DATOS"
    ERROR_HARDWARE          = "ERROR_HARDWARE"
    REVISION_MANUAL         = "REVISION_MANUAL"

    def mensaje_guardia(self) -> str:
        """Texto descriptivo para mostrar en la interfaz del guardia."""
        _messages = {
            AccessState.PROCESANDO:            "Procesando imagen…",
            AccessState.VEHICULO_NO_DETECTADO: "No se detectó ningún vehículo.",
            AccessState.PLACA_LEGIBLE:         "Matrícula detectada. Consultando registro…",
            AccessState.PLACA_ILEGIBLE:        "Matrícula ilegible o no localizada. Revisión del guardia requerida.",
            AccessState.PLACA_NO_REGISTRADA:   "Matrícula no registrada en el sistema.",
            AccessState.VEHICULO_INACTIVO:     "Vehículo registrado pero sin autorización activa.",
            AccessState.SIN_AUTORIZACION:      "Vehículo sin asociación autorizada vigente.",
            AccessState.ACCESO_PERMITIDO:      "Acceso permitido. Orden de apertura enviada al semáforo.",
            AccessState.ACCESO_DENEGADO:       "Acceso denegado.",
            AccessState.ERROR_CAMARA:           "Error técnico: cámara no disponible.",
            AccessState.ERROR_VISION:          "Error técnico: fallo en el módulo de visión.",
            AccessState.ERROR_BASE_DATOS:      "Error técnico: no se pudo consultar la base de datos.",
            AccessState.ERROR_HARDWARE:        "Error técnico: sin respuesta del hardware.",
            AccessState.REVISION_MANUAL:       "Revisión manual pendiente. Esperando al guardia.",
        }
        return _messages.get(self, self.value)


@dataclass(frozen=True)
class AccessDecision:
    """
    Decisión de acceso producida por VIGIA_Core.

    Separa explícitamente:
    - La decisión lógica (result, motivo).
    - El estado para la interfaz (ui_state).
    - Los identificadores de BD para persistencia (no inventados).
    - La orden de hardware (hardware_command — solo presente si es PERMITIDO).

    Nunca afirma que el hardware ejecutó la orden.
    """

    result: AccessResult
    motivo: MotivoDecision
    tipo_movimiento: TipoMovimiento
    tipo_acceso: TipoAcceso
    ui_state: AccessState
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Referencias de BD — None si no aplica
    id_vehiculo: Optional[UUID] = None
    id_deteccion: Optional[UUID] = None
    id_usuario_operador: Optional[UUID] = None
    placa_efectiva: Optional[str] = None
    observaciones: Optional[str] = None

    # Orden de hardware — solo 'ABRE' o None
    hardware_command: Optional[str] = None

    def __post_init__(self) -> None:
        if self.result == AccessResult.PERMITIDO and self.hardware_command is None:
            # Advertencia de diseño: si se permite acceso, debe haber una orden
            # No se lanza excepción porque puede omitirse en revisión manual sin hardware
            pass

        if (
            self.tipo_acceso == TipoAcceso.MANUAL_SUPERVISADO
            and self.id_usuario_operador is None
            and self.result == AccessResult.PERMITIDO
        ):
            raise ValueError(
                "MANUAL_SUPERVISADO con PERMITIDO requiere id_usuario_operador"
            )

    @property
    def motivo_ddl_v1(self) -> str:
        """Motivo seguro para insertar en el CHECK constraint del DDL V1."""
        return self.motivo.ddl_v1_safe().value
