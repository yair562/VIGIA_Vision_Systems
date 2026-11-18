"""
Esquema canonico de anotacion manual para el sandbox VIGIA-ML (Actividad B).

Caracteristicas de diseño:
1. Totalmente independiente del codigo de produccion (``VIGIA_Core``, ``VIGIA_Vision``).
2. Exige taxonomias cerradas para clases vehiculares, colores y condiciones visuales.
3. Separa estrictamente la prediccion auxiliar de YOLO (``yolo_aux_reference``,
   nunca Ground Truth) de la etiqueta humana aprobada.
4. Incluye registro formal de desacuerdos entre anotadores y estado de revision.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

VEHICLE_CLASSES: Tuple[str, ...] = (
    "CAR",
    "MOTORCYCLE",
    "BUS",
    "TRUCK",
    "OTHER",
    "IGNORE",
)

COLOR_CLASSES: Tuple[str, ...] = (
    "WHITE",
    "BLACK",
    "GRAY",
    "SILVER",
    "RED",
    "BLUE",
    "GREEN",
    "YELLOW",
    "BROWN",
    "ORANGE",
    "OTHER",
    "INDETERMINATE",
)

VISIBILITY_LEVELS: Tuple[str, ...] = ("FULL", "PARTIAL", "EDGE_TRUNCATED", "LOW")
OCCLUSION_LEVELS: Tuple[str, ...] = ("NONE", "PARTIAL", "HEAVY")
LIGHTING_CONDITIONS: Tuple[str, ...] = ("NORMAL", "LOW_LIGHT", "GLARE", "COLOR_CAST", "BACKLIT")
BLUR_LEVELS: Tuple[str, ...] = ("SHARP", "MODERATE", "SEVERE")
REVIEW_STATES: Tuple[str, ...] = ("DRAFT", "PENDING_REVIEW", "APPROVED", "DISPUTED", "REJECTED")


@dataclass(frozen=True)
class YoloAuxReference:
    """Referencia auxiliar no autoritativa; jamas equivale a Ground Truth."""

    model_name: str
    bbox_xyxy: Tuple[int, int, int, int]
    raw_class: str
    confidence: float
    is_ground_truth: bool = False

    def __post_init__(self) -> None:
        if self.is_ground_truth:
            raise ValueError(
                "Una prediccion de YOLO nunca puede marcarse automaticamente como Ground Truth."
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence debe estar en [0.0, 1.0].")


@dataclass
class VehicleAnnotation:
    """Anotacion humana de una instancia vehicular dentro de una imagen."""

    annotation_id: str
    bbox_xyxy: Tuple[int, int, int, int]
    vehicle_class: str
    observed_color: str
    visibility: str
    occlusion: str
    lighting_condition: str
    blur_level: str
    annotator_id: str
    review_status: str = "PENDING_REVIEW"
    reviewer_id: Optional[str] = None
    annotator_notes: str = ""
    yolo_aux_reference: Optional[YoloAuxReference] = None

    def __post_init__(self) -> None:
        x1, y1, x2, y2 = self.bbox_xyxy
        if x1 < 0 or y1 < 0 or x2 <= x1 or y2 <= y1:
            raise ValueError(f"Bounding box invalida (xyxy): {self.bbox_xyxy}")
        if self.vehicle_class not in VEHICLE_CLASSES:
            raise ValueError(f"Clase vehicular invalida: {self.vehicle_class}")
        if self.observed_color not in COLOR_CLASSES:
            raise ValueError(f"Color observado invalido: {self.observed_color}")
        if self.visibility not in VISIBILITY_LEVELS:
            raise ValueError(f"Visibilidad invalida: {self.visibility}")
        if self.occlusion not in OCCLUSION_LEVELS:
            raise ValueError(f"Oclusion invalida: {self.occlusion}")
        if self.lighting_condition not in LIGHTING_CONDITIONS:
            raise ValueError(f"Condicion de iluminacion invalida: {self.lighting_condition}")
        if self.blur_level not in BLUR_LEVELS:
            raise ValueError(f"Nivel de desenfoque invalido: {self.blur_level}")
        if self.review_status not in REVIEW_STATES:
            raise ValueError(f"Estado de revision invalido: {self.review_status}")
        if not self.annotator_id.strip():
            raise ValueError("annotator_id es obligatorio para trazabilidad humana.")


@dataclass(frozen=True)
class AnnotatorDisagreement:
    """Registro de desacuerdo entre dos anotadores para auditoria y consenso."""

    disagreement_id: str
    sample_id: str
    annotation_id: str
    annotator_a_id: str
    annotator_b_id: str
    field_name: str
    value_a: str
    value_b: str
    resolution_status: str = "OPEN"
    resolved_value: Optional[str] = None
    adjudicator_id: Optional[str] = None
    recorded_at_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )


@dataclass
class ImageAnnotationRecord:
    """Contenedor de anotaciones humanas verificadas por imagen."""

    sample_id: str
    image_path: str
    sha256: str
    source_domain: str
    session_id: str
    duplicate_group: str
    objects: List[VehicleAnnotation] = field(default_factory=list)
    disagreements: List[AnnotatorDisagreement] = field(default_factory=list)
    ground_truth_status: str = "PENDING_HUMAN_REVIEW"


@dataclass
class AnnotationDataset:
    """Coleccion versionada de anotaciones manuales y bitacora de revision."""

    schema_version: str = "1.0.0"
    created_at_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    records: List[ImageAnnotationRecord] = field(default_factory=list)

    def compare_double_annotation(
        self,
        sample_id: str,
        ann_a: VehicleAnnotation,
        ann_b: VehicleAnnotation,
    ) -> List[AnnotatorDisagreement]:
        """
        Compara anotaciones independientes de dos revisores sobre el mismo objeto
        y registra cualquier desacuerdo en clase o color, marcando ``DISPUTED``.
        """
        if ann_a.annotator_id == ann_b.annotator_id:
            raise ValueError("La doble revision requiere dos anotadores distintos.")

        diffs: List[AnnotatorDisagreement] = []
        for field_name in ("vehicle_class", "observed_color"):
            va = getattr(ann_a, field_name)
            vb = getattr(ann_b, field_name)
            if va != vb:
                diffs.append(
                    AnnotatorDisagreement(
                        disagreement_id=f"DIS_{sample_id}_{ann_a.annotation_id}_{field_name}",
                        sample_id=sample_id,
                        annotation_id=ann_a.annotation_id,
                        annotator_a_id=ann_a.annotator_id,
                        annotator_b_id=ann_b.annotator_id,
                        field_name=field_name,
                        value_a=str(va),
                        value_b=str(vb),
                    )
                )

        if diffs:
            ann_a.review_status = "DISPUTED"
            ann_b.review_status = "DISPUTED"
        else:
            ann_a.review_status = "APPROVED"
            ann_b.review_status = "APPROVED"

        for rec in self.records:
            if rec.sample_id == sample_id:
                rec.disagreements.extend(diffs)
                rec.ground_truth_status = "DISPUTED" if diffs else "HUMAN_VERIFIED"
                break

        return diffs

    def summary(self) -> Dict[str, int]:
        total_objs = sum(len(r.objects) for r in self.records)
        approved = sum(
            1 for r in self.records for o in r.objects if o.review_status == "APPROVED"
        )
        disputed = sum(len(r.disagreements) for r in self.records)
        return {
            "images": len(self.records),
            "objects": total_objs,
            "approved_objects": approved,
            "open_disagreements": disputed,
        }

    def save_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
