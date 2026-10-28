"""
VIGIA_Core.domain.vision_result
================================
Contrato canónico de salida del subsistema VIGIA_Vision.

Reglas de diseño:
- Inmutable (frozen dataclass).
- Nunca contiene lógica de negocio ni decisiones de acceso.
- Distingue explícitamente: sin vehículo / sin placa / placa ilegible / error técnico.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class VisionStatus(str, Enum):
    """Estado del resultado de visión artificial."""

    # Ciclo completado con normalidad
    VEHICLE_DETECTED_PLATE_READ = "VEHICLE_DETECTED_PLATE_READ"
    """Vehículo detectado y matrícula leída con confianza suficiente."""

    VEHICLE_DETECTED_PLATE_UNREADABLE = "VEHICLE_DETECTED_PLATE_UNREADABLE"
    """Vehículo detectado pero la matrícula no se pudo leer (baja confianza o sin ROI)."""

    VEHICLE_DETECTED_NO_PLATE = "VEHICLE_DETECTED_NO_PLATE"
    """Vehículo detectado pero no se localizó región de matrícula."""

    NO_VEHICLE_DETECTED = "NO_VEHICLE_DETECTED"
    """El frame se procesó correctamente pero no hay ningún vehículo."""

    # Fallos técnicos — no deben interpretarse como ausencia de vehículo
    CAMERA_ERROR = "CAMERA_ERROR"
    """No se pudo capturar el frame (cámara desconectada o fallo de lectura)."""

    VISION_ERROR = "VISION_ERROR"
    """El modelo de visión lanzó una excepción durante la inferencia."""


@dataclass(frozen=True)
class VisionResult:
    """
    Resultado estructurado e inmutable producido por VIGIA_Vision.

    Atributos
    ---------
    status : VisionStatus
        Estado semántico del ciclo de visión. Determina el camino de procesamiento
        en VIGIA_Core sin necesidad de inspeccionar los demás campos.

    timestamp : datetime
        Momento de la inferencia (UTC). Siempre con timezone.

    vehicle_detected : bool
        True si YOLO detectó al menos un vehículo con confianza >= umbral.

    vehicle_confidence : Optional[float]
        Confianza máxima de detección vehicular [0.0, 1.0]. None si sin vehículo.

    vehicle_type_pred : Optional[str]
        Tipo de vehículo predicho por el clasificador visual.
        Valores esperados: 'AUTOMOVIL', 'CAMIONETA', 'MOTOCICLETA', 'AUTOBUS', 'CAMION'.

    plate_located : bool
        True si se localizó una región de matrícula en el frame.

    plate_text : Optional[str]
        Caracteres extraídos por OCR. None si no se leyó o no se localizó placa.
        NUNCA se rellena artificialmente ni se completa con caracteres inventados.

    plate_confidence : Optional[float]
        Confianza de la lectura OCR [0.0, 1.0]. None si plate_text is None.

    evidence_path : Optional[str]
        Ruta relativa al fotograma guardado como evidencia. None si no se guardó.

    error_message : Optional[str]
        Descripción técnica del fallo. Solo presente cuando status es CAMERA_ERROR
        o VISION_ERROR. No debe mostrarse directamente al guardia.
    """

    status: VisionStatus
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    vehicle_detected: bool = False
    vehicle_confidence: Optional[float] = None
    vehicle_type_pred: Optional[str] = None

    plate_located: bool = False
    plate_text: Optional[str] = None
    plate_confidence: Optional[float] = None

    evidence_path: Optional[str] = None
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        """Valida invariantes semánticas del contrato."""
        # Un resultado técnico no puede tener datos de detección
        if self.status in (VisionStatus.CAMERA_ERROR, VisionStatus.VISION_ERROR):
            if self.vehicle_detected:
                raise ValueError(
                    f"status={self.status} no puede tener vehicle_detected=True"
                )

        # Si se leyó la placa debe existir confianza
        if self.plate_text is not None and self.plate_confidence is None:
            raise ValueError(
                "plate_text presente pero plate_confidence es None"
            )

        # La confianza debe estar en rango válido
        for label, value in (
            ("vehicle_confidence", self.vehicle_confidence),
            ("plate_confidence", self.plate_confidence),
        ):
            if value is not None and not (0.0 <= value <= 1.0):
                raise ValueError(
                    f"{label}={value} fuera del rango [0.0, 1.0]"
                )

    # ------------------------------------------------------------------
    # Helpers de inspección (no modifican estado)
    # ------------------------------------------------------------------

    @property
    def is_technical_error(self) -> bool:
        """True cuando el fallo es técnico, no funcional."""
        return self.status in (VisionStatus.CAMERA_ERROR, VisionStatus.VISION_ERROR)

    @property
    def has_readable_plate(self) -> bool:
        """True si existe una matrícula legible."""
        return self.plate_text is not None and self.plate_text.strip() != ""

    @property
    def requires_guard_review(self) -> bool:
        """True cuando el estado exige intervención humana."""
        return self.status in (
            VisionStatus.VEHICLE_DETECTED_PLATE_UNREADABLE,
            VisionStatus.VEHICLE_DETECTED_NO_PLATE,
        )
