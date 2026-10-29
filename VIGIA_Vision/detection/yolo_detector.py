"""
VIGIA_Vision.detection.yolo_detector
====================================
Detector vehicular basado en modelos Ultralytics YOLO (Etapa 2 - SPRINT-02).

Implementa la interfaz ``IVehicleDetector`` de forma desacoplada y con carga perezosa
(lazy loading). No importa PyTorch ni Ultralytics al nivel de módulo ni en ``__init__``,
garantizando que la importación de ``VIGIA_Vision`` permanezca ligera y libre de efectos
secundarios.

Clases vehiculares soportadas (COCO dataset):
  - 2: ``'car'`` -> Automóviles
  - 3: ``'motorcycle'`` -> Motocicletas
  - 5: ``'bus'`` -> Autobuses
  - 7: ``'truck'`` -> Camiones

Todas las demás clases (personas, animales, semáforos, etc.) son descartadas
automáticamente durante la inferencia o en el filtrado de defensa en profundidad.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence, Tuple, Union

import numpy as np

from VIGIA_Vision.detection.models import BoundingBox, RawVehicleDetection
from VIGIA_Vision.detection.roi_and_preprocess import validate_bgr_frame

logger = logging.getLogger(__name__)

# Clases vehiculares COCO oficiales y su mapeo a etiquetas crudas de dominio
COCO_VEHICLE_CLASSES: Dict[int, str] = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


class ModelLoadError(RuntimeError):
    """Fallo al cargar los pesos o instanciar el modelo YOLO."""


class InferenceError(RuntimeError):
    """Fallo inesperado durante la ejecución de inferencia predictiva."""


@dataclass(frozen=True)
class YoloDetectorConfig:
    """
    Configuración inmutable para el detector vehicular YOLO.

    Parámetros
    ----------
    model_path : Union[str, Path]
        Ruta al archivo de pesos (.pt) o identificador del modelo (por defecto 'yolo11n.pt').
    confidence_threshold : float
        Umbral mínimo de confianza para aceptar una detección (por defecto 0.25).
    device : str
        Dispositivo de cómputo para inferencia ('cpu', 'cuda', etc. Por defecto 'cpu').
    imgsz : int
        Tamaño de resolución para inferencia cuadrada (por defecto 640).
    iou_threshold : float
        Umbral de IoU para Non-Maximum Suppression (por defecto 0.45).
    classes : Tuple[int, ...]
        IDs numéricos de clases COCO a filtrar (por defecto (2, 3, 5, 7)).
    """

    model_path: Union[str, Path] = "yolo11n.pt"
    confidence_threshold: float = 0.25
    device: str = "cpu"
    imgsz: int = 640
    iou_threshold: float = 0.45
    classes: Tuple[int, ...] = (2, 3, 5, 7)

    def __post_init__(self) -> None:
        if isinstance(self.confidence_threshold, bool) or not isinstance(
            self.confidence_threshold, (int, float)
        ):
            raise ValueError("confidence_threshold debe ser un número en el rango [0.0, 1.0].")
        if not (0.0 <= float(self.confidence_threshold) <= 1.0):
            raise ValueError(
                f"confidence_threshold={self.confidence_threshold} fuera del rango [0.0, 1.0]."
            )

        if isinstance(self.iou_threshold, bool) or not isinstance(
            self.iou_threshold, (int, float)
        ):
            raise ValueError("iou_threshold debe ser un número en el rango [0.0, 1.0].")
        if not (0.0 <= float(self.iou_threshold) <= 1.0):
            raise ValueError(
                f"iou_threshold={self.iou_threshold} fuera del rango [0.0, 1.0]."
            )

        if isinstance(self.imgsz, bool) or not isinstance(self.imgsz, int) or self.imgsz <= 0:
            raise ValueError(f"imgsz={self.imgsz!r} debe ser un entero positivo.")

        if not isinstance(self.device, str) or not self.device.strip():
            raise ValueError("device debe ser una cadena no vacía (ej. 'cpu', 'cuda:0').")

        if not isinstance(self.model_path, (str, Path)) or not str(self.model_path).strip():
            raise ValueError("model_path debe ser una ruta válida (str o Path no vacío).")

        if not isinstance(self.classes, (tuple, list)) or len(self.classes) == 0:
            raise ValueError("classes debe ser una secuencia no vacía de IDs de clase enteros.")

        for cls_id in self.classes:
            if isinstance(cls_id, bool) or not isinstance(cls_id, int) or cls_id < 0:
                raise ValueError(f"ID de clase inválido en classes: {cls_id!r}.")

        object.__setattr__(self, "confidence_threshold", float(self.confidence_threshold))
        object.__setattr__(self, "iou_threshold", float(self.iou_threshold))
        object.__setattr__(self, "device", self.device.strip())
        object.__setattr__(self, "model_path", str(self.model_path).strip())
        object.__setattr__(self, "classes", tuple(self.classes))


class YoloVehicleDetector:
    """
    Detector vehicular basado en Ultralytics YOLO implementando el contrato ``IVehicleDetector``.

    Características:
    - Lazy loading: Ultralytics y PyTorch se importan e inicializan únicamente en la
      primera llamada a ``detect()`` o ``load_model()``.
    - Inyección de dependencias para testing: admite un ``model_factory`` para inyectar
      modelos simulados sin requerir pesos reales ni dependencias de GPU/disco en tests unitarios.
    - Thread-safe: inicialización del modelo protegida mediante un lock reentrante (``threading.RLock``).
    - Validación estricta: valida fotogramas con ``validate_bgr_frame()``.
    - Clamping de coordenadas: garantiza que todas las cajas delimiten regiones válidas
      dentro del fotograma.
    """

    def __init__(
        self,
        config: Optional[YoloDetectorConfig] = None,
        model_factory: Optional[Callable[[Union[str, Path]], Any]] = None,
    ) -> None:
        self._config = config or YoloDetectorConfig()
        self._model_factory = model_factory
        self._model: Optional[Any] = None
        self._lock = threading.RLock()

    @property
    def config(self) -> YoloDetectorConfig:
        return self._config

    @property
    def is_loaded(self) -> bool:
        """Indica si el modelo ya fue cargado en memoria."""
        with self._lock:
            return self._model is not None

    def load_model(self) -> Any:
        """
        Carga e inicializa el modelo YOLO de manera perezosa y segura para hilos.

        Lanza
        -----
        ModelLoadError
            Si no se pueden cargar los pesos o instanciar la clase de modelo.
        """
        with self._lock:
            if self._model is not None:
                return self._model

            if self._model_factory is not None:
                try:
                    self._model = self._model_factory(self._config.model_path)
                    return self._model
                except Exception as exc:
                    raise ModelLoadError(
                        f"Fallo al instanciar el modelo con model_factory inyectado: {exc}"
                    ) from exc

            try:
                from ultralytics import YOLO

                self._model = YOLO(str(self._config.model_path))
                return self._model
            except Exception as exc:
                raise ModelLoadError(
                    f"Error al cargar el modelo YOLO desde '{self._config.model_path}': {exc}"
                ) from exc

    def detect(self, frame: np.ndarray) -> Sequence[RawVehicleDetection]:
        """
        Ejecuta la inferencia sobre un fotograma BGR uint8 y extrae las detecciones de vehículos.

        Parámetros
        ----------
        frame : np.ndarray
            Fotograma BGR con forma (H, W, 3) y dtype uint8.

        Retorna
        -------
        Sequence[RawVehicleDetection]
            Secuencia inmutable (tupla) de detecciones vehiculares válidas.

        Lanza
        -----
        FrameValidationError
            Si el fotograma no cumple las especificaciones BGR uint8 3D.
        InferenceError
            Si ocurre un fallo en el motor de inferencia YOLO.
        ModelLoadError
            Si la carga perezosa del modelo falla.
        """
        frame_width, frame_height = validate_bgr_frame(frame)
        model = self.load_model()

        try:
            results = model.predict(
                source=frame,
                conf=self._config.confidence_threshold,
                iou=self._config.iou_threshold,
                device=self._config.device,
                imgsz=self._config.imgsz,
                classes=list(self._config.classes),
                verbose=False,
                save=False,
                show=False,
            )
        except Exception as exc:
            raise InferenceError(f"Error durante la inferencia YOLO: {exc}") from exc

        if not results or len(results) == 0:
            return ()

        raw_boxes = getattr(results[0], "boxes", None)
        if raw_boxes is None or len(raw_boxes) == 0:
            return ()

        detections = []
        for box in raw_boxes:
            try:
                coords = (
                    box.xyxy[0].tolist()
                    if hasattr(box.xyxy, "__getitem__")
                    else box.xyxy.tolist()
                )
                x1, y1, x2, y2 = (
                    float(coords[0]),
                    float(coords[1]),
                    float(coords[2]),
                    float(coords[3]),
                )

                conf = (
                    float(box.conf[0])
                    if hasattr(box.conf, "__getitem__")
                    else float(box.conf)
                )
                cls_id = (
                    int(box.cls[0])
                    if hasattr(box.cls, "__getitem__")
                    else int(box.cls)
                )
            except (AttributeError, IndexError, TypeError, ValueError) as exc:
                logger.warning("Estructura de caja inesperada en resultado YOLO: %s", exc)
                continue

            # Filtro de umbral de confianza
            if conf < self._config.confidence_threshold:
                continue

            # Filtro defensivo de clases configuradas y clases vehiculares COCO
            if cls_id not in self._config.classes or cls_id not in COCO_VEHICLE_CLASSES:
                continue

            raw_label = COCO_VEHICLE_CLASSES[cls_id]

            # Clamping estricto de coordenadas al tamaño del fotograma
            x_min = max(0, min(int(round(x1)), frame_width - 1))
            y_min = max(0, min(int(round(y1)), frame_height - 1))
            x_max = max(0, min(int(round(x2)), frame_width))
            y_max = max(0, min(int(round(y2)), frame_height))

            if x_max <= x_min or y_max <= y_min:
                # Caja degenerada tras clamping o nula
                continue

            try:
                bbox = BoundingBox(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max)
                detection = RawVehicleDetection(
                    bbox=bbox,
                    confidence=conf,
                    raw_label=raw_label,
                )
                detections.append(detection)
            except ValueError as val_err:
                logger.warning("Omitiendo detección con BoundingBox inválida: %s", val_err)
                continue

        return tuple(detections)
