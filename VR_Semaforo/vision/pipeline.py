"""
VR_Semaforo.vision.pipeline
===========================
Pipeline mínimo desacoplado de visión vehicular para VIGÍA Vision Systems (Fase 2B).

Adapta el procesamiento de detección vehicular existente al contrato canónico
VIGIA_Core.domain.vision_result.VisionResult, manteniendo compatibilidad con
VR_Semaforo/service.py y VR_Semaforo/app.py.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# Asegurar resolución de VIGIA_Core en cualquier entorno de ejecución
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from VIGIA_Core.domain.vision_result import VisionResult, VisionStatus


@dataclass
class VisionPipelineResult:
    """
    Adaptador de resultado que encapsula el contrato canónico VisionResult
    y expone los atributos requeridos por los consumidores actuales (app.py y service.py).
    """

    canonical: VisionResult
    vehicles: List[Dict[str, Any]]
    annotated_frame: Optional[Any] = None

    @property
    def vehicle_count(self) -> int:
        """Número de vehículos detectados."""
        return len(self.vehicles)

    @property
    def status(self) -> VisionStatus:
        return self.canonical.status

    @property
    def vehicle_detected(self) -> bool:
        return self.canonical.vehicle_detected

    @property
    def error(self) -> Optional[str]:
        return self.canonical.error_message

    def to_dict(self) -> Dict[str, Any]:
        """
        Representación serializable a JSON compatible con las respuestas HTTP
        de app.py y service.py, preservando la estructura de vehicles con vehicle_bbox.
        """
        return {
            "status": self.canonical.status.value,
            "vehicle_detected": self.canonical.vehicle_detected,
            "vehicle_count": self.vehicle_count,
            "vehicle_confidence": self.canonical.vehicle_confidence,
            "vehicle_type_pred": self.canonical.vehicle_type_pred,
            "plate_located": self.canonical.plate_located,
            "plate_text": self.canonical.plate_text,
            "plate_confidence": self.canonical.plate_confidence,
            "evidence_path": self.canonical.evidence_path,
            "error_message": self.canonical.error_message,
            "vehicles": self.vehicles,
        }


class VisionPipeline:
    """
    Pipeline de visión vehicular desacoplado.
    Permite inyectar detectores simulados para pruebas unitarias sin hardware ni GPU.
    """

    def __init__(self, detector: Optional[Callable[..., Any]] = None):
        self._detector = detector

    def _get_detector(self) -> Callable[..., Any]:
        if self._detector is not None:
            return self._detector
        # Importación perezosa para no cargar YOLO ni PyTorch al importar este módulo
        from vision.processor import contar_carritos
        return contar_carritos

    def process(
        self,
        frame: Optional[Any],
        draw: bool = False
    ) -> VisionPipelineResult:
        """
        Procesa un fotograma y retorna el resultado de visión adaptado.

        Parámetros
        ----------
        frame : Optional[np.ndarray]
            Fotograma de imagen en formato NumPy BGR, o None si la captura falló.
        draw : bool
            True si se requiere generar la imagen anotada y cajas para el frontend móvil.
        """
        # 1. Validación de entrada: fallo de captura o frame nulo
        if frame is None:
            canonical = VisionResult(
                status=VisionStatus.CAMERA_ERROR,
                vehicle_detected=False,
                error_message="Camera frame could not be captured or is None.",
            )
            return VisionPipelineResult(
                canonical=canonical,
                vehicles=[],
                annotated_frame=None,
            )

        # 2. Invocación segura del detector
        try:
            detector_fn = self._get_detector()
            detection_output = detector_fn(frame, dibujar=draw)
        except Exception as exc:
            canonical = VisionResult(
                status=VisionStatus.VISION_ERROR,
                vehicle_detected=False,
                error_message=f"Inference execution failed: {exc}",
            )
            return VisionPipelineResult(
                canonical=canonical,
                vehicles=[],
                annotated_frame=None,
            )

        # 3. Interpretación de la salida del detector
        annotated_frame = None
        vehicles_list: List[Dict[str, Any]] = []
        max_confidence: Optional[float] = None
        vehicle_type_pred: Optional[str] = None

        if isinstance(detection_output, tuple):
            if len(detection_output) == 3:
                cantidad, annotated_frame, lista_boxes = detection_output
                for item in lista_boxes:
                    if isinstance(item, (tuple, list)) and len(item) == 4:
                        x, y, w, h = item
                        vehicles_list.append({
                            "vehicle_bbox": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
                        })
                    elif isinstance(item, dict) and "vehicle_bbox" in item:
                        vehicles_list.append(item)
            elif len(detection_output) >= 2:
                cantidad = detection_output[0]
                annotated_frame = detection_output[1]
            else:
                cantidad = detection_output[0]
        elif isinstance(detection_output, dict):
            cantidad = detection_output.get("vehicle_count", 0)
            annotated_frame = detection_output.get("annotated_frame")
            vehicles_list = detection_output.get("vehicles", [])
            max_confidence = detection_output.get("vehicle_confidence")
            vehicle_type_pred = detection_output.get("vehicle_type_pred")
        elif isinstance(detection_output, (int, float)):
            cantidad = int(detection_output)
        else:
            cantidad = 0

        # Si el detector retornó cantidad numérica pero lista_boxes estaba vacía (ej. draw=False)
        if cantidad > 0 and not vehicles_list:
            vehicles_list = [
                {"vehicle_bbox": {"x": 0, "y": 0, "w": 0, "h": 0}}
                for _ in range(cantidad)
            ]

        vehicle_detected = cantidad > 0

        # 4. Construcción del VisionResult canónico de VIGIA_Core
        # En esta fase (sin OCR/LPR integrado), una detección exitosa se clasifica como VEHICLE_DETECTED_NO_PLATE
        status = (
            VisionStatus.VEHICLE_DETECTED_NO_PLATE
            if vehicle_detected
            else VisionStatus.NO_VEHICLE_DETECTED
        )

        canonical = VisionResult(
            status=status,
            vehicle_detected=vehicle_detected,
            vehicle_confidence=max_confidence,
            vehicle_type_pred=vehicle_type_pred,
            plate_located=False,
            plate_text=None,
            plate_confidence=None,
            evidence_path=None,
            error_message=None,
        )

        return VisionPipelineResult(
            canonical=canonical,
            vehicles=vehicles_list,
            annotated_frame=annotated_frame,
        )
