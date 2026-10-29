"""
VIGIA_Vision.detection.models
=============================
Objetos de valor inmutables para el transporte interno de capturas, cajas
delimitadoras, detecciones vehiculares, métricas de observación y el sobre
inmutable ``VisionObservationEnvelope`` de la Etapa 1.

Reglas de diseño:
- Todos los objetos de valor son inmutables (``@dataclass(frozen=True)``).
- ``VisionResult`` se transporta íntegro y sin modificaciones dentro de
  ``VisionObservationEnvelope``. No se duplica ni altera su validación.
- Dependencia de conteo documentada:
  * ``in_roi_now`` representa la ocupación instantánea de vehículos válidos
    dentro del ROI en el fotograma actual.
  * ``unique_vehicles_total`` permanece explícitamente en ``None`` en la
    Etapa 1. Su cálculo requiere el seguimiento temporal (tracking) y
    deduplicación reservados para la Etapa 3; nunca se inventa ni se rellena
    con un acumulado provisional no fiable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Tuple
from uuid import UUID

from VIGIA_Core.domain.vision_result import VisionResult


@dataclass(frozen=True)
class BoundingBox:
    """
    Caja delimitadora rectangular en coordenadas de píxeles de imagen.

    Invariantes
    -----------
    - ``x_min >= 0``, ``y_min >= 0``
    - ``x_max > x_min``, ``y_max > y_min``
    """

    x_min: int
    y_min: int
    x_max: int
    y_max: int

    def __post_init__(self) -> None:
        for name, val in (
            ("x_min", self.x_min),
            ("y_min", self.y_min),
            ("x_max", self.x_max),
            ("y_max", self.y_max),
        ):
            if isinstance(val, bool) or not isinstance(val, int):
                raise ValueError(f"{name}={val!r} debe ser un entero.")
        if self.x_min < 0 or self.y_min < 0:
            raise ValueError(
                f"Las coordenadas mínimas no pueden ser negativas: ({self.x_min}, {self.y_min})."
            )
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError(
                f"BoundingBox degenerada o invertida: ({self.x_min}, {self.y_min}, {self.x_max}, {self.y_max})."
            )

    @property
    def width(self) -> int:
        return self.x_max - self.x_min

    @property
    def height(self) -> int:
        return self.y_max - self.y_min

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def centroid(self) -> Tuple[float, float]:
        """Centro geométrico ``(cx, cy)`` en coordenadas de píxeles."""
        return (
            self.x_min + (self.width / 2.0),
            self.y_min + (self.height / 2.0),
        )

    def to_xywh_dict(self) -> dict[str, int]:
        """Representación serializable ``{'x', 'y', 'w', 'h'}`` para el monitor."""
        return {
            "x": self.x_min,
            "y": self.y_min,
            "w": self.width,
            "h": self.height,
        }


@dataclass(frozen=True)
class RawVehicleDetection:
    """
    Detección vehicular emitida por un detector inyectable antes o después del
    filtrado por ROI.

    Atributos
    ---------
    bbox : BoundingBox
        Caja delimitadora en píxeles.
    confidence : float
        Confianza del detector en el rango [0.0, 1.0].
    raw_label : str
        Etiqueta de clase emitida por el detector (ej. ``'car'``, ``'motorcycle'``,
        ``'truck'``, ``'bus'`` o el nombre ya normalizado en dominio).
    """

    bbox: BoundingBox
    confidence: float
    raw_label: str

    def __post_init__(self) -> None:
        if not isinstance(self.bbox, BoundingBox):
            raise ValueError("bbox debe ser una instancia de BoundingBox.")
        if (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
            or not (0.0 <= float(self.confidence) <= 1.0)
        ):
            raise ValueError(
                f"confidence={self.confidence!r} fuera del rango permitido [0.0, 1.0]."
            )
        if not isinstance(self.raw_label, str) or not self.raw_label.strip():
            raise ValueError("raw_label debe ser una cadena no vacía.")
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "raw_label", self.raw_label.strip())


@dataclass(frozen=True)
class CaptureReadResult:
    """
    Resultado estructurado e inmutable de una operación de lectura de fotograma.

    Distingue explícitamente entre:
    - ``ok=True`` con ``frame`` presente (lectura exitosa).
    - ``ok=False`` con ``error_reason`` (fallo de hardware, desconexión o TTL expirado).
    - ``ok=False`` con ``is_already_processed=True`` (en buffers push cuando no ha
      llegado un fotograma nuevo desde la última lectura; no constituye un fallo de cámara).
    """

    ok: bool
    frame: Optional[Any] = None
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    frame_sequence: Optional[int] = None
    error_reason: Optional[str] = None
    is_already_processed: bool = False

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at debe incluir zona horaria (UTC).")
        if self.ok and self.frame is None:
            raise ValueError("CaptureReadResult con ok=True requiere un frame no nulo.")
        if not self.ok and self.frame is not None:
            raise ValueError("CaptureReadResult con ok=False no puede transportar un frame.")


@dataclass(frozen=True)
class ObservationMetrics:
    """
    Métricas operativas de observación para una cámara y su área de visión.

    NOTA ARQUITECTÓNICA SOBRE EL CONTEO (Etapa 1 vs. Etapa 3):
    ----------------------------------------------------------
    - ``in_roi_now`` informa la ocupación instantánea (número de vehículos con
      confianza >= umbral cuyo centroide se encuentra dentro del ROI en el
      fotograma actual).
    - ``unique_vehicles_total`` permanece obligatoriamente en ``None`` durante
      la Etapa 1. El conteo acumulado de vehículos únicos requiere el módulo de
      seguimiento temporal (tracking IoU + deduplicación) de la Etapa 3 y jamás
      se rellena con un conteo por fotograma que induciría a error.
    """

    in_roi_now: int = 0
    total_detected_in_frame: int = 0
    excluded_outside_roi: int = 0
    unique_vehicles_total: Optional[int] = None

    def __post_init__(self) -> None:
        for name, val in (
            ("in_roi_now", self.in_roi_now),
            ("total_detected_in_frame", self.total_detected_in_frame),
            ("excluded_outside_roi", self.excluded_outside_roi),
        ):
            if isinstance(val, bool) or not isinstance(val, int) or val < 0:
                raise ValueError(f"{name}={val!r} debe ser un entero >= 0.")
        if self.unique_vehicles_total is not None:
            if (
                isinstance(self.unique_vehicles_total, bool)
                or not isinstance(self.unique_vehicles_total, int)
                or self.unique_vehicles_total < 0
            ):
                raise ValueError("unique_vehicles_total debe ser None o un entero >= 0.")


@dataclass(frozen=True)
class VisionObservationEnvelope:
    """
    Sobre inmutable de observación emitido por ``VisionEngineCoordinator``.

    Envuelve la instancia original e intacta de ``VisionResult`` junto con el
    contexto de topología (cámara y área), las cajas detectadas en el ROI, las
    rutas de evidencia original/anotada, el identificador de persistencia
    relacional cuando exista y las métricas operativas del cuadro.
    """

    vision_result: VisionResult
    id_camara: UUID
    codigo_camara: str
    id_area_vision: UUID
    codigo_area: str
    tipo_movimiento: str
    detections_in_roi: Tuple[RawVehicleDetection, ...] = ()
    metrics: ObservationMetrics = field(default_factory=ObservationMetrics)
    id_deteccion: Optional[UUID] = None
    frame_sequence: Optional[int] = None
    original_evidence_path: Optional[str] = None
    annotated_evidence_path: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.vision_result, VisionResult):
            raise ValueError("vision_result debe ser una instancia de VisionResult.")
        if not isinstance(self.id_camara, UUID):
            raise ValueError("id_camara debe ser un UUID válido.")
        if not isinstance(self.id_area_vision, UUID):
            raise ValueError("id_area_vision debe ser un UUID válido.")
        if not isinstance(self.codigo_camara, str) or not self.codigo_camara.strip():
            raise ValueError("codigo_camara no puede ser vacío.")
        if not isinstance(self.codigo_area, str) or not self.codigo_area.strip():
            raise ValueError("codigo_area no puede ser vacío.")
        if self.tipo_movimiento not in ("ENTRADA", "SALIDA"):
            raise ValueError(
                f"tipo_movimiento={self.tipo_movimiento!r} debe ser 'ENTRADA' o 'SALIDA'."
            )
        object.__setattr__(self, "detections_in_roi", tuple(self.detections_in_roi))
