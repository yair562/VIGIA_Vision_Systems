"""
VIGIA_Vision.async_persistence.models
=====================================
Contratos inmutables, enumeraciones y estructuras de datos para el piloto
aislado de persistencia asíncrona de VIGÍA Vision Systems.

Conforme a las especificaciones normativas de OPT-05 (R1, R2 y R3):
- Cuádruple separación de identidades: task_id, capture_id, content_hash e id_deteccion.
- Secuencia causal monótona por cámara (camera_sequence).
- Modelado formal de estados FSM y registros de discontinuidad causal.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID, uuid4

from VIGIA_Vision.detection.models import BoundingBox, RawVehicleDetection
from VIGIA_Vision.detection.roi_and_preprocess import PixelROI


class TaskStatus(str, Enum):
    """Estados del ciclo de vida formal de una tarea de persistencia asíncrona."""
    CREATED = "CREATED"
    SPOOLED = "SPOOLED"
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    EVIDENCES_STAGED = "EVIDENCES_STAGED"
    EVIDENCES_COMMITTED = "EVIDENCES_COMMITTED"
    DATABASE_COMMITTED = "DATABASE_COMMITTED"
    COMPLETED = "COMPLETED"
    COMPENSATING_ROLLBACK = "COMPENSATING_ROLLBACK"
    FAILED_DLQ = "FAILED_DLQ"
    CORRUPTED = "CORRUPTED"


@dataclass(frozen=True)
class DiscontinuityRecord:
    """Registro explícito de discontinuidad en la secuencia causal de una cámara."""
    codigo_camara: str
    missing_sequence: int
    resumed_sequence: int
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "codigo_camara": self.codigo_camara,
            "missing_sequence": self.missing_sequence,
            "resumed_sequence": self.resumed_sequence,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DiscontinuityRecord:
        ts = datetime.fromisoformat(data["timestamp"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return cls(
            codigo_camara=data["codigo_camara"],
            missing_sequence=int(data["missing_sequence"]),
            resumed_sequence=int(data["resumed_sequence"]),
            reason=data["reason"],
            timestamp=ts,
        )


@dataclass(frozen=True)
class DLQRecord:
    """Contenido y diagnóstico forense preservado en cuarentena Dead Letter Queue."""
    task_id: UUID
    capture_id: UUID
    camera_sequence: int
    codigo_camara: str
    timestamp_failure: datetime
    retry_count: int
    last_error: str
    error_trace: str
    discontinuity: Optional[DiscontinuityRecord] = None
    created_at_mono: float = field(default_factory=time.monotonic)

    def to_json(self) -> str:
        data = {
            "task_id": str(self.task_id),
            "capture_id": str(self.capture_id),
            "camera_sequence": self.camera_sequence,
            "codigo_camara": self.codigo_camara,
            "timestamp_failure": self.timestamp_failure.isoformat(),
            "retry_count": self.retry_count,
            "last_error": self.last_error,
            "error_trace": self.error_trace,
            "discontinuity": self.discontinuity.to_dict() if self.discontinuity else None,
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> DLQRecord:
        data = json.loads(raw)
        ts = datetime.fromisoformat(data["timestamp_failure"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        disc = DiscontinuityRecord.from_dict(data["discontinuity"]) if data.get("discontinuity") else None
        return cls(
            task_id=UUID(data["task_id"]),
            capture_id=UUID(data["capture_id"]),
            camera_sequence=int(data["camera_sequence"]),
            codigo_camara=data["codigo_camara"],
            timestamp_failure=ts,
            retry_count=int(data["retry_count"]),
            last_error=data["last_error"],
            error_trace=data["error_trace"],
            discontinuity=disc,
        )


def compute_content_hash(raw_bytes: bytes) -> str:
    """Calcula el hash criptográfico SHA-256 de una secuencia binaria."""
    if not isinstance(raw_bytes, (bytes, bytearray)):
        raise TypeError("raw_bytes debe ser una secuencia de bytes.")
    return hashlib.sha256(raw_bytes).hexdigest()


@dataclass(frozen=True)
class PersistenceTaskDTO:
    """
    Contrato inmutable de trabajo para el subsistema de persistencia asíncrona.
    
    Invariantes formales:
    - task_id, capture_id, id_camara, id_area_vision son instancias válidas de UUID.
    - camera_sequence es un entero >= 1.
    - timestamp_captura incluye tzinfo UTC.
    - content_hash coincide estrictamente con SHA256(raw_jpeg_bytes).
    """
    task_id: UUID
    capture_id: UUID
    camera_sequence: int
    codigo_camara: str
    id_camara: UUID
    id_area_vision: UUID
    timestamp_captura: datetime
    content_hash: str
    raw_jpeg_bytes: bytes
    detections: Tuple[RawVehicleDetection, ...]
    pixel_roi: Optional[PixelROI] = None
    tipo_vehiculo_pred: Optional[str] = None
    confianza_vehiculo: Optional[float] = None
    placa_detectada: Optional[str] = None
    confianza_placa: Optional[float] = None
    retry_count: int = 0
    created_at_mono: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, UUID):
            raise TypeError("task_id debe ser UUID.")
        if not isinstance(self.capture_id, UUID):
            raise TypeError("capture_id debe ser UUID.")
        if not isinstance(self.camera_sequence, int) or self.camera_sequence < 1:
            raise ValueError("camera_sequence debe ser un entero >= 1.")
        if not isinstance(self.codigo_camara, str) or not self.codigo_camara.strip():
            raise ValueError("codigo_camara no puede ser vacío.")
        if not isinstance(self.id_camara, UUID):
            raise TypeError("id_camara debe ser UUID.")
        if not isinstance(self.id_area_vision, UUID):
            raise TypeError("id_area_vision debe ser UUID.")
        if not isinstance(self.timestamp_captura, datetime) or self.timestamp_captura.tzinfo is None:
            raise ValueError("timestamp_captura debe ser un datetime con timezone.")
        if not isinstance(self.raw_jpeg_bytes, (bytes, bytearray)) or len(self.raw_jpeg_bytes) == 0:
            raise ValueError("raw_jpeg_bytes no puede estar vacío.")
        
        # Validar consistencia criptográfica
        actual_hash = compute_content_hash(self.raw_jpeg_bytes)
        if self.content_hash != actual_hash:
            raise ValueError(
                f"content_hash inconsistente: declarado={self.content_hash}, real={actual_hash}"
            )
        
        # Normalizar tupla de detecciones si se pasó lista
        if not isinstance(self.detections, tuple):
            object.__setattr__(self, "detections", tuple(self.detections))

    def with_retry_incremented(self) -> PersistenceTaskDTO:
        """Retorna una copia inmutable con retry_count incrementado."""
        return PersistenceTaskDTO(
            task_id=self.task_id,
            capture_id=self.capture_id,
            camera_sequence=self.camera_sequence,
            codigo_camara=self.codigo_camara,
            id_camara=self.id_camara,
            id_area_vision=self.id_area_vision,
            timestamp_captura=self.timestamp_captura,
            content_hash=self.content_hash,
            raw_jpeg_bytes=self.raw_jpeg_bytes,
            detections=self.detections,
            pixel_roi=self.pixel_roi,
            tipo_vehiculo_pred=self.tipo_vehiculo_pred,
            confianza_vehiculo=self.confianza_vehiculo,
            placa_detectada=self.placa_detectada,
            confianza_placa=self.confianza_placa,
            retry_count=self.retry_count + 1,
            created_at_mono=self.created_at_mono,
        )

    def to_metadata_dict(self) -> Dict[str, Any]:
        """Serializa los metadatos de la tarea a un diccionario JSON serializable (sin los bytes JPEG)."""
        dets_json = []
        for det in self.detections:
            dets_json.append({
                "bbox": [det.bbox.x_min, det.bbox.y_min, det.bbox.x_max, det.bbox.y_max],
                "confidence": det.confidence,
                "raw_label": det.raw_label,
            })

        roi_json = None
        if self.pixel_roi is not None:
            roi_json = {
                "x_min": self.pixel_roi.x_min,
                "y_min": self.pixel_roi.y_min,
                "x_max": self.pixel_roi.x_max,
                "y_max": self.pixel_roi.y_max,
                "frame_width": self.pixel_roi.frame_width,
                "frame_height": self.pixel_roi.frame_height,
            }

        return {
            "task_id": str(self.task_id),
            "capture_id": str(self.capture_id),
            "camera_sequence": self.camera_sequence,
            "codigo_camara": self.codigo_camara,
            "id_camara": str(self.id_camara),
            "id_area_vision": str(self.id_area_vision),
            "timestamp_captura": self.timestamp_captura.isoformat(),
            "content_hash": self.content_hash,
            "tipo_vehiculo_pred": self.tipo_vehiculo_pred,
            "confianza_vehiculo": self.confianza_vehiculo,
            "placa_detectada": self.placa_detectada,
            "confianza_placa": self.confianza_placa,
            "retry_count": self.retry_count,
            "detections": dets_json,
            "pixel_roi": roi_json,
        }

    @classmethod
    def from_metadata_dict(cls, data: Dict[str, Any], raw_jpeg_bytes: bytes) -> PersistenceTaskDTO:
        """Reconstruye una instancia inmutable a partir de metadatos deserializados y bytes JPEG."""
        dets = []
        for d in data.get("detections", []):
            bbox_coords = d["bbox"]
            bbox = BoundingBox(
                x_min=int(bbox_coords[0]),
                y_min=int(bbox_coords[1]),
                x_max=int(bbox_coords[2]),
                y_max=int(bbox_coords[3]),
            )
            dets.append(
                RawVehicleDetection(
                    bbox=bbox,
                    confidence=float(d["confidence"]),
                    raw_label=str(d.get("raw_label", d.get("class_name", "car"))),
                )
            )

        pixel_roi = None
        if data.get("pixel_roi"):
            r = data["pixel_roi"]
            pixel_roi = PixelROI(
                x_min=float(r["x_min"]),
                y_min=float(r["y_min"]),
                x_max=float(r["x_max"]),
                y_max=float(r["y_max"]),
                frame_width=int(r.get("frame_width", 640)),
                frame_height=int(r.get("frame_height", 640)),
            )

        ts = datetime.fromisoformat(data["timestamp_captura"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        return cls(
            task_id=UUID(data["task_id"]),
            capture_id=UUID(data["capture_id"]),
            camera_sequence=int(data["camera_sequence"]),
            codigo_camara=str(data["codigo_camara"]),
            id_camara=UUID(data["id_camara"]),
            id_area_vision=UUID(data["id_area_vision"]),
            timestamp_captura=ts,
            content_hash=str(data["content_hash"]),
            raw_jpeg_bytes=raw_jpeg_bytes,
            detections=tuple(dets),
            pixel_roi=pixel_roi,
            tipo_vehiculo_pred=data.get("tipo_vehiculo_pred"),
            confianza_vehiculo=data.get("confianza_vehiculo"),
            placa_detectada=data.get("placa_detectada"),
            confianza_placa=data.get("confianza_placa"),
            retry_count=int(data.get("retry_count", 0)),
        )
