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

import gc
import logging
import math
import os
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Optional, Sequence, Tuple, Union

import numpy as np

from VIGIA_Vision.detection.models import BoundingBox, RawVehicleDetection
from VIGIA_Vision.detection.roi_and_preprocess import validate_bgr_frame

logger = logging.getLogger(__name__)

# Raíz del repositorio VIGIA_Vision_Systems para resolución determinista de pesos
_REPO_ROOT = Path(__file__).resolve().parents[2]

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


class InferenceBackpressureError(InferenceError):
    """Saturación de cola/lock GPU al superar el tiempo máximo de espera."""


def resolve_yolo_weights_path(model_spec: Union[str, Path]) -> Path:
    """
    Resuelve de forma determinista la ruta de un archivo de pesos YOLO (.pt)
    sin depender del directorio de trabajo actual (cwd).

    Orden de búsqueda para rutas relativas:
    1. ``<repo_root>/<model_spec>``
    2. ``<repo_root>/models/<model_spec>``
    3. ``<repo_root>/experiments/yolo26x/weights/<filename>``
    4. ``<repo_root.parent>/<model_spec>``
    5. Ruta relativa directa si existe en disco; en su defecto ``(<repo_root>/<model_spec>).resolve()``.
    """
    if not isinstance(model_spec, (str, Path)):
        raise ValueError(f"model_spec inválido ({type(model_spec).__name__}): se esperaba str o Path.")
    raw_str = str(model_spec).strip()
    if not raw_str:
        raise ValueError("model_spec no puede ser una cadena vacía.")

    raw_path = Path(raw_str)
    if raw_path.is_absolute():
        return raw_path.resolve()

    candidates = (
        _REPO_ROOT / raw_path,
        _REPO_ROOT / "models" / raw_path,
        _REPO_ROOT / "experiments" / "yolo26x" / "weights" / raw_path.name,
        _REPO_ROOT.parent / raw_path,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    if raw_path.is_file():
        return raw_path.resolve()

    return (_REPO_ROOT / raw_path).resolve()


def resolve_inference_device(device_setting: Optional[str] = None) -> str:
    """
    Resuelve y valida el dispositivo de cómputo para inferencia YOLO.

    Soporta:
    - 'auto': Evalúa disponibilidad funcional de CUDA (PyTorch + hardware). Si
      está operativa, selecciona 'cuda:0'; ante cualquier fallo o ausencia,
      realiza un fallback controlado a 'cpu' registrando una advertencia.
    - 'cuda' o 'cuda:N': Requiere explícitamente GPU CUDA. Valida disponibilidad
      y funcionalidad. Si no está disponible, lanza RuntimeError (fail-fast).
    - 'cpu': Selecciona cómputo en procesador central (modo estándar de respaldo).

    Parámetros
    ----------
    device_setting : Optional[str]
        Cadena de configuración ('auto', 'cuda', 'cuda:N', 'cpu') o None para
        resolver desde la variable de entorno 'VIGIA_INFERENCE_DEVICE'.

    Retorna
    -------
    str
        Cadena normalizada del dispositivo ('cuda:0', 'cuda:N' o 'cpu').

    Lanza
    -----
    ValueError
        Si el valor proporcionado no es reconocido o es inválido.
    RuntimeError
        Si se solicitó explícitamente 'cuda' pero la GPU o PyTorch CUDA no están operativos.
    """
    raw_setting = device_setting
    if raw_setting is None or str(raw_setting).strip() == "":
        try:
            from VIGIA_Core.config.env_loader import get_setting

            raw_setting = get_setting("VIGIA_INFERENCE_DEVICE", "auto")
        except Exception:
            raw_setting = os.environ.get("VIGIA_INFERENCE_DEVICE", "auto")

    dev_str = str(raw_setting).strip().lower()

    if dev_str == "cpu":
        logger.info("Dispositivo de inferencia seleccionado: 'cpu'.")
        return "cpu"

    if dev_str == "auto":
        try:
            import torch

            if torch.cuda.is_available():
                test_tensor = torch.zeros((1,), device="cuda:0")
                del test_tensor
                gpu_name = torch.cuda.get_device_name(0)
                props = torch.cuda.get_device_properties(0)
                vram_mb = props.total_memory / (1024.0 * 1024.0)
                logger.info(
                    "Modo 'auto': GPU NVIDIA CUDA detectada y validada: %s (%.0f MB VRAM). Seleccionando 'cuda:0'.",
                    gpu_name,
                    vram_mb,
                )
                return "cuda:0"
            else:
                logger.info("Modo 'auto': CUDA no disponible en este entorno PyTorch. Seleccionando 'cpu'.")
                return "cpu"
        except Exception as exc:
            logger.warning(
                "Modo 'auto': Error al validar GPU CUDA (%s). Fallback controlado a 'cpu'.",
                exc,
            )
            return "cpu"

    if dev_str == "cuda" or dev_str.startswith("cuda:"):
        target_dev = "cuda:0" if dev_str == "cuda" else dev_str
        try:
            import torch

            if not torch.cuda.is_available():
                raise RuntimeError(
                    f"Se solicitó dispositivo explícito '{raw_setting}', pero "
                    "torch.cuda.is_available() retornó False. Verifique la instalación de PyTorch con soporte CUDA."
                )
            test_tensor = torch.zeros((1,), device=target_dev)
            del test_tensor
            gpu_name = torch.cuda.get_device_name(target_dev)
            props = torch.cuda.get_device_properties(target_dev)
            vram_mb = props.total_memory / (1024.0 * 1024.0)
            logger.info(
                "Dispositivo CUDA explícito validado: %s en %s (%.0f MB VRAM).",
                gpu_name,
                target_dev,
                vram_mb,
            )
            return target_dev
        except Exception as exc:
            if isinstance(exc, RuntimeError) and "Se solicitó dispositivo explícito" in str(exc):
                raise
            raise RuntimeError(
                f"Fallo al validar dispositivo CUDA explícito '{raw_setting}': {exc}"
            ) from exc

    raise ValueError(
        f"Dispositivo de inferencia no soportado: '{raw_setting}'. Valores permitidos: 'auto', 'cuda', 'cuda:N', 'cpu'."
    )


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
    quantize : Optional[int]
        Precisión numérica de inferencia: ``None`` (predeterminado), ``16`` (FP16) o ``32`` (FP32).
    nms : Optional[bool]
        Control explícito de NMS: ``None`` (predeterminado), ``True`` (NMS clásico) o ``False`` (NMS-Free end2end).
    augment : bool
        Habilita Test-Time Augmentation (incompatible con ``nms=False``).
    fallback_enabled : bool
        Habilita el fallback automático a ``fallback_model_path`` ante fallo del modelo principal.
    fallback_model_path : Union[str, Path]
        Ruta o identificador del modelo de respaldo funcional (por defecto 'yolo11n.pt').
    """

    model_path: Union[str, Path] = "yolo11n.pt"
    confidence_threshold: float = 0.25
    device: str = "cpu"
    imgsz: int = 640
    iou_threshold: float = 0.45
    classes: Tuple[int, ...] = (2, 3, 5, 7)
    quantize: Optional[int] = None
    nms: Optional[bool] = None
    augment: bool = False
    fallback_enabled: bool = True
    fallback_model_path: Union[str, Path] = "yolo11n.pt"
    deduplicate_iou_threshold: Optional[float] = 0.55
    consolidate_frontal_confidence: bool = True
    frontal_aux_enabled: bool = True
    frontal_aux_imgsz: Optional[int] = 384
    frontal_aux_trigger_confidence: float = 0.70

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

        if self.quantize is not None:
            if isinstance(self.quantize, bool) or not isinstance(self.quantize, int) or self.quantize not in (16, 32):
                raise ValueError(
                    f"quantize={self.quantize!r} inválido. Valores permitidos: None, 16 (FP16) o 32 (FP32)."
                )

        if self.nms is not None and not isinstance(self.nms, bool):
            raise ValueError(
                f"nms={self.nms!r} inválido. Valores permitidos: None, True o False."
            )

        if not isinstance(self.augment, bool):
            raise ValueError(f"augment={self.augment!r} debe ser booleano.")

        if self.augment and self.nms is False:
            raise ValueError(
                "Configuración incompatible: augment=True (TTA) no es compatible con nms=False (modo NMS-Free)."
            )

        if not isinstance(self.fallback_enabled, bool):
            raise ValueError(f"fallback_enabled={self.fallback_enabled!r} debe ser booleano.")

        if not isinstance(self.fallback_model_path, (str, Path)) or not str(self.fallback_model_path).strip():
            raise ValueError("fallback_model_path debe ser una ruta válida (str o Path no vacío).")

        if self.deduplicate_iou_threshold is not None:
            if (
                isinstance(self.deduplicate_iou_threshold, bool)
                or not isinstance(self.deduplicate_iou_threshold, (int, float))
                or not (0.0 < float(self.deduplicate_iou_threshold) <= 1.0)
            ):
                raise ValueError(
                    f"deduplicate_iou_threshold={self.deduplicate_iou_threshold!r} debe ser None o un número en (0.0, 1.0]."
                )
            object.__setattr__(self, "deduplicate_iou_threshold", float(self.deduplicate_iou_threshold))

        if not isinstance(self.consolidate_frontal_confidence, bool):
            raise ValueError(
                f"consolidate_frontal_confidence={self.consolidate_frontal_confidence!r} debe ser booleano."
            )

        if not isinstance(self.frontal_aux_enabled, bool):
            raise ValueError(f"frontal_aux_enabled={self.frontal_aux_enabled!r} debe ser booleano.")

        if self.frontal_aux_imgsz is not None:
            if (
                isinstance(self.frontal_aux_imgsz, bool)
                or not isinstance(self.frontal_aux_imgsz, int)
                or self.frontal_aux_imgsz <= 0
            ):
                raise ValueError(
                    f"frontal_aux_imgsz={self.frontal_aux_imgsz!r} debe ser None o un entero positivo."
                )

        if (
            isinstance(self.frontal_aux_trigger_confidence, bool)
            or not isinstance(self.frontal_aux_trigger_confidence, (int, float))
            or not (0.0 < float(self.frontal_aux_trigger_confidence) <= 1.0)
        ):
            raise ValueError(
                f"frontal_aux_trigger_confidence={self.frontal_aux_trigger_confidence!r} debe estar en (0.0, 1.0]."
            )

        object.__setattr__(self, "confidence_threshold", float(self.confidence_threshold))
        object.__setattr__(self, "iou_threshold", float(self.iou_threshold))
        object.__setattr__(self, "device", self.device.strip())
        object.__setattr__(self, "model_path", str(self.model_path).strip())
        object.__setattr__(self, "classes", tuple(self.classes))
        object.__setattr__(self, "fallback_model_path", str(self.fallback_model_path).strip())
        object.__setattr__(self, "frontal_aux_trigger_confidence", float(self.frontal_aux_trigger_confidence))


def _parse_positive_int(raw: Optional[str], var_name: str, default: int) -> int:
    """Parsea un entero estrictamente positivo desde texto de entorno."""
    if raw is None or not str(raw).strip():
        return default
    text = str(raw).strip()
    if text.lower() in ("true", "false"):
        raise ValueError(f"{var_name}={raw!r} debe ser un entero positivo.")
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError(f"{var_name}={raw!r} debe ser un entero positivo.") from exc
    if value <= 0:
        raise ValueError(f"{var_name}={raw!r} debe ser mayor a 0.")
    return value


def _parse_quantize(raw: Optional[str], var_name: str = "VIGIA_YOLO_QUANTIZE") -> Optional[int]:
    """Parsea VIGIA_YOLO_QUANTIZE aceptando None/vacío/'none', 16/'fp16', o 32/'fp32'."""
    if raw is None:
        return None
    normalized = str(raw).strip().lower()
    if normalized in ("", "none", "null"):
        return None
    if normalized in ("16", "fp16"):
        return 16
    if normalized in ("32", "fp32"):
        return 32
    raise ValueError(
        f"{var_name}={raw!r} inválido. Valores permitidos: vacío/'none', '16'/'fp16', '32'/'fp32'."
    )


def _parse_optional_bool(raw: Optional[str], var_name: str) -> Optional[bool]:
    """Parsea una bandera booleana opcional distinguiendo estrictamente None, True y False."""
    if raw is None:
        return None
    normalized = str(raw).strip().lower()
    if normalized in ("", "none", "null"):
        return None
    if normalized in ("true", "1", "yes"):
        return True
    if normalized in ("false", "0", "no"):
        return False
    raise ValueError(
        f"{var_name}={raw!r} inválido. Valores permitidos: vacío/'none', 'true'/'1'/'yes', 'false'/'0'/'no'."
    )


def _parse_bool_with_default(raw: Optional[str], var_name: str, default: bool) -> bool:
    """Parsea una bandera booleana con valor predeterminado explícito."""
    parsed = _parse_optional_bool(raw, var_name)
    return default if parsed is None else parsed


def _parse_optional_positive_float(
    raw: Optional[str],
    var_name: str,
    default: Optional[float],
    *,
    allow_none: bool = True,
) -> Optional[float]:
    """Parsea un flotante en (0.0, 1.0] o None si se indica 'none'/'false'/'0'."""
    if raw is None or not str(raw).strip():
        return default
    norm = str(raw).strip().lower()
    if allow_none and norm in ("none", "null", "false", "0", "off"):
        return None
    if norm in ("true", "yes", "on"):
        raise ValueError(f"{var_name}={raw!r} debe ser un número en (0.0, 1.0].")
    try:
        val = float(norm)
    except ValueError as exc:
        raise ValueError(f"{var_name}={raw!r} debe ser un número en (0.0, 1.0].") from exc
    if not math.isfinite(val) or not (0.0 < val <= 1.0):
        raise ValueError(f"{var_name}={raw!r} fuera de rango (0.0, 1.0].")
    return val


def _parse_optional_positive_int(
    raw: Optional[str],
    var_name: str,
    default: Optional[int],
) -> Optional[int]:
    """Parsea un entero positivo o None si se indica 'none'/'false'/'0'."""
    if raw is None or not str(raw).strip():
        return default
    norm = str(raw).strip().lower()
    if norm in ("none", "null", "false", "0", "off"):
        return None
    if norm in ("true", "yes", "on"):
        raise ValueError(f"{var_name}={raw!r} debe ser un entero positivo o 'none'.")
    try:
        val = int(norm)
    except ValueError as exc:
        raise ValueError(f"{var_name}={raw!r} debe ser un entero positivo o 'none'.") from exc
    if val <= 0:
        raise ValueError(f"{var_name}={raw!r} debe ser mayor a 0.")
    return val


def compute_bbox_iou(box_a: BoundingBox, box_b: BoundingBox) -> float:
    """Calcula la Intersección sobre Unión (IoU) entre dos BoundingBox en [0.0, 1.0]."""
    x1 = max(box_a.x_min, box_b.x_min)
    y1 = max(box_a.y_min, box_b.y_min)
    x2 = min(box_a.x_max, box_b.x_max)
    y2 = min(box_a.y_max, box_b.y_max)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter <= 0:
        return 0.0
    union = box_a.area + box_b.area - inter
    if union <= 0:
        return 0.0
    return float(inter) / float(union)


def deduplicate_and_consolidate_detections(
    detections: Sequence[RawVehicleDetection],
    *,
    iou_threshold: Optional[float] = 0.55,
    consolidate_split_confidence: bool = True,
) -> Tuple[Tuple[RawVehicleDetection, ...], int]:
    """
    Suprime detecciones duplicadas intra-frame diferenciando coincidencia exacta de clase
    frente a superposición inter-clase de vehículos próximos:
    - Misma clase (``cand.raw_label == k_det.raw_label``): suprime duplicados desde
      ``IoU >= iou_threshold`` (por defecto 0.55) y consolida confianza si ``IoU >= 0.75``.
    - Distinta clase entre vehículos de 4+ ruedas (``car``, ``bus``, ``truck``): exige
      ``IoU >= max(iou_threshold, 0.75)`` para no suprimir vehículos distintos parcialmente
      superpuestos en la misma escena (ej. automóvil delante de autobús con ``0.55 <= IoU < 0.75``).
    - Distinta clase involucrando ``motorcycle``: exige ``IoU >= max(iou_threshold, 0.85)``
      para evitar fusionar motocicletas próximas con vehículos mayores.

    Preserva el orden relativo original de las detecciones sobrevivientes.
    Retorna ``(detecciones_consolidadas, conteo_suprimidas)``.
    """
    if not detections or iou_threshold is None or len(detections) <= 1:
        return tuple(detections), 0

    # Ordenar índices por confianza y área descendente para elegir el representante primario
    indexed = list(enumerate(detections))
    indexed.sort(key=lambda item: (item[1].confidence, item[1].bbox.area), reverse=True)

    kept_entries: list[Tuple[int, RawVehicleDetection]] = []
    suppressed = 0

    for orig_idx, cand in indexed:
        merged_into = -1
        for k_pos, (k_orig_idx, k_det) in enumerate(kept_entries):
            iou_val = compute_bbox_iou(cand.bbox, k_det.bbox)
            if cand.raw_label == k_det.raw_label:
                eff_threshold = float(iou_threshold)
            elif "motorcycle" in (cand.raw_label, k_det.raw_label):
                eff_threshold = max(float(iou_threshold), 0.85)
            else:
                eff_threshold = max(float(iou_threshold), 0.75)

            if iou_val >= eff_threshold:
                merged_into = k_pos
                suppressed += 1
                if consolidate_split_confidence and iou_val >= 0.75:
                    p1 = k_det.confidence
                    p2 = cand.confidence
                    new_label = k_det.raw_label
                    if cand.raw_label != k_det.raw_label:
                        combined = min(0.99, 1.0 - (1.0 - p1) * (1.0 - p2))
                        if cand.raw_label == "bus" and p2 >= 0.60 * p1:
                            new_label = "bus"
                    else:
                        combined = min(0.99, 1.0 - (1.0 - p1) * (1.0 - 0.65 * p2))
                    kept_entries[k_pos] = (
                        min(k_orig_idx, orig_idx),
                        RawVehicleDetection(
                            bbox=k_det.bbox,
                            confidence=round(float(combined), 4),
                            raw_label=new_label,
                        ),
                    )
                break
        if merged_into < 0:
            kept_entries.append((orig_idx, cand))

    kept_entries.sort(key=lambda item: item[0])
    return tuple(det for _, det in kept_entries), suppressed


def _get_env_setting(name: str, default: Optional[str] = None) -> Optional[str]:
    """Lee una configuración usando el cargador centralizado VIGIA_Core.config.env_loader."""
    try:
        from VIGIA_Core.config.env_loader import get_setting

        return get_setting(name, default)
    except Exception:
        return os.environ.get(name, default)


def load_yolo_config_from_env(
    yolo_weights_override: Optional[Union[str, Path]] = None,
    confidence_threshold: float = 0.25,
) -> YoloDetectorConfig:
    """
    Construye un ``YoloDetectorConfig`` desde el entorno centralizado de VIGÍA
    manteniendo ``yolo11n.pt`` como modelo predeterminado de producción.

    Variables soportadas:
    - ``VIGIA_YOLO_MODEL`` (default ``'yolo11n.pt'``; respaldo compatible: ``VIGIA_YOLO_WEIGHTS``)
    - ``VIGIA_YOLO_IMGSZ`` (default ``640``)
    - ``VIGIA_YOLO_QUANTIZE`` (default ``None``; soporta ``16``/``fp16`` o ``32``/``fp32``)
    - ``VIGIA_YOLO_NMS`` (default ``None``; ``true`` o ``false``)
    - ``VIGIA_YOLO_DEVICE`` (default fallback a ``VIGIA_INFERENCE_DEVICE`` -> ``'auto'``)
    - ``VIGIA_YOLO_FALLBACK_ENABLED`` (default ``True``)
    - ``VIGIA_YOLO_FALLBACK_MODEL`` (default ``'yolo11n.pt'``)
    - ``VIGIA_YOLO_DEDUP_IOU`` (default ``0.55``; ``'none'`` para desactivar)
    - ``VIGIA_YOLO_CONSOLIDATE_CONFIDENCE`` (default ``True``)
    - ``VIGIA_YOLO_FRONTAL_AUX_ENABLED`` (default ``True``)
    - ``VIGIA_YOLO_FRONTAL_AUX_IMGSZ`` (default ``384``; ``'none'`` para desactivar)
    - ``VIGIA_YOLO_FRONTAL_AUX_TRIGGER_CONF`` (default ``0.70``)
    """
    override_str = str(yolo_weights_override).strip() if yolo_weights_override is not None else ""
    if override_str:
        model_spec = override_str
    else:
        raw_model = _get_env_setting("VIGIA_YOLO_MODEL", None)
        if raw_model is not None and str(raw_model).strip():
            model_spec = str(raw_model).strip()
        else:
            legacy_weights = _get_env_setting("VIGIA_YOLO_WEIGHTS", None)
            if legacy_weights is not None and str(legacy_weights).strip():
                model_spec = str(legacy_weights).strip()
            else:
                model_spec = "yolo11n.pt"

    resolved_model_path = resolve_yolo_weights_path(model_spec)
    imgsz = _parse_positive_int(_get_env_setting("VIGIA_YOLO_IMGSZ", None), "VIGIA_YOLO_IMGSZ", 640)
    quantize = _parse_quantize(_get_env_setting("VIGIA_YOLO_QUANTIZE", None), "VIGIA_YOLO_QUANTIZE")
    nms = _parse_optional_bool(_get_env_setting("VIGIA_YOLO_NMS", None), "VIGIA_YOLO_NMS")

    raw_yolo_device = _get_env_setting("VIGIA_YOLO_DEVICE", None)
    device_spec = (
        str(raw_yolo_device).strip()
        if raw_yolo_device is not None and str(raw_yolo_device).strip()
        else None
    )
    resolved_device = resolve_inference_device(device_spec)

    fallback_enabled = _parse_bool_with_default(
        _get_env_setting("VIGIA_YOLO_FALLBACK_ENABLED", None),
        "VIGIA_YOLO_FALLBACK_ENABLED",
        default=True,
    )
    raw_fallback_model = _get_env_setting("VIGIA_YOLO_FALLBACK_MODEL", None)
    fallback_spec = (
        str(raw_fallback_model).strip()
        if raw_fallback_model is not None and str(raw_fallback_model).strip()
        else "yolo11n.pt"
    )
    resolved_fallback_path = resolve_yolo_weights_path(fallback_spec)

    dedup_iou = _parse_optional_positive_float(
        _get_env_setting("VIGIA_YOLO_DEDUP_IOU", None),
        "VIGIA_YOLO_DEDUP_IOU",
        default=0.55,
        allow_none=True,
    )
    consolidate_conf = _parse_bool_with_default(
        _get_env_setting("VIGIA_YOLO_CONSOLIDATE_CONFIDENCE", None),
        "VIGIA_YOLO_CONSOLIDATE_CONFIDENCE",
        default=True,
    )
    frontal_aux_enabled = _parse_bool_with_default(
        _get_env_setting("VIGIA_YOLO_FRONTAL_AUX_ENABLED", None),
        "VIGIA_YOLO_FRONTAL_AUX_ENABLED",
        default=True,
    )
    frontal_aux_imgsz = _parse_optional_positive_int(
        _get_env_setting("VIGIA_YOLO_FRONTAL_AUX_IMGSZ", None),
        "VIGIA_YOLO_FRONTAL_AUX_IMGSZ",
        default=384,
    )
    frontal_aux_trigger_conf = _parse_optional_positive_float(
        _get_env_setting("VIGIA_YOLO_FRONTAL_AUX_TRIGGER_CONF", None),
        "VIGIA_YOLO_FRONTAL_AUX_TRIGGER_CONF",
        default=0.70,
        allow_none=False,
    )
    assert frontal_aux_trigger_conf is not None

    return YoloDetectorConfig(
        model_path=str(resolved_model_path),
        confidence_threshold=confidence_threshold,
        device=resolved_device,
        imgsz=imgsz,
        quantize=quantize,
        nms=nms,
        fallback_enabled=fallback_enabled,
        fallback_model_path=str(resolved_fallback_path),
        deduplicate_iou_threshold=dedup_iou,
        consolidate_frontal_confidence=consolidate_conf,
        frontal_aux_enabled=frontal_aux_enabled,
        frontal_aux_imgsz=frontal_aux_imgsz,
        frontal_aux_trigger_confidence=frontal_aux_trigger_conf,
    )


def _get_ultralytics_version() -> Optional[str]:
    """Obtiene la versión de Ultralytics si ya está instalada o importable."""
    try:
        import ultralytics

        return getattr(ultralytics, "__version__", None)
    except Exception:
        return None


class YoloVehicleDetector:
    """
    Detector vehicular basado en Ultralytics YOLO implementando el contrato ``IVehicleDetector``.

    Características:
    - Lazy loading: Ultralytics y PyTorch se importan e inicializan únicamente en la
      primera llamada a ``detect()`` o ``load_model()``.
    - Inyección de dependencias para testing: admite un ``model_factory`` para inyectar
      modelos simulados sin requerir pesos reales ni dependencias de GPU/disco en tests unitarios.
    - Thread-safe: inicialización y ejecución de inferencia protegidas mediante ``threading.RLock``.
    - Soporte experimental controlado: ``quantize``, ``nms`` (NMS-Free end2end), ``imgsz`` y
      fallback automático seguro hacia ``yolo11n.pt`` ante fallos de inicialización o inferencia.
    - Validación estricta: valida fotogramas con ``validate_bgr_frame()``.
    - Clamping de coordenadas: garantiza que todas las cajas delimiten regiones válidas
      dentro del fotograma.
    """

    def __init__(
        self,
        config: Optional[YoloDetectorConfig] = None,
        model_factory: Optional[Callable[[Union[str, Path]], Any]] = None,
    ) -> None:
        raw_config = config or YoloDetectorConfig()
        dev_normalized = raw_config.device.strip().lower()
        if dev_normalized in ("auto", "cuda") or dev_normalized.startswith("cuda:"):
            effective_dev = resolve_inference_device(raw_config.device)
            if effective_dev != raw_config.device:
                resolved_config = replace(raw_config, device=effective_dev)
            else:
                resolved_config = raw_config
        else:
            resolved_config = raw_config

        self._requested_config: YoloDetectorConfig = resolved_config
        self._config: YoloDetectorConfig = resolved_config
        self._model_factory = model_factory
        self._model: Optional[Any] = None
        self._lock = threading.RLock()
        self._closed: bool = False
        self._using_fallback: bool = False
        self._fallback_reason: Optional[str] = None
        self._fallback_timestamp: Optional[str] = None
        self._end2end_verified: bool = False
        self._effective_end2end: Optional[bool] = None
        self._effective_fp16: Optional[bool] = None
        self._effective_imgsz: Optional[int] = None
        self._latencies_ms: Deque[float] = deque(maxlen=512)
        self._queue_waits_ms: Deque[float] = deque(maxlen=512)
        self._total_inferences: int = 0
        self._inference_errors: int = 0
        self._cuda_errors: int = 0
        self._init_errors: int = 0
        self._fallback_count: int = 0
        self._last_recovery_ms: Optional[float] = None
        self._last_queue_wait_ms: Optional[float] = None
        self._last_camera_code: Optional[str] = None
        self._last_inference_at: Optional[str] = None
        self._frontal_aux_triggers: int = 0
        self._frontal_aux_recoveries: int = 0
        self._duplicates_suppressed: int = 0
        self._last_inference_model: Optional[str] = None
        self._inferences_by_model: Dict[str, int] = {}

    @property
    def config(self) -> YoloDetectorConfig:
        with self._lock:
            return self._config

    @property
    def requested_config(self) -> YoloDetectorConfig:
        return self._requested_config

    @property
    def effective_device(self) -> str:
        """Dispositivo efectivo resuelto para inferencia predictiva."""
        with self._lock:
            return self._config.device

    @property
    def is_loaded(self) -> bool:
        """Indica si el modelo ya fue cargado en memoria."""
        with self._lock:
            return self._model is not None

    @property
    def using_fallback(self) -> bool:
        """Indica si el detector operó un fallback hacia el modelo de respaldo."""
        with self._lock:
            return self._using_fallback

    @property
    def fallback_reason(self) -> Optional[str]:
        """Descripción estructurada de la causa del último fallback activado."""
        with self._lock:
            return self._fallback_reason

    @property
    def effective_model_path(self) -> str:
        """Ruta efectiva del archivo de pesos actualmente activo."""
        with self._lock:
            return str(self._config.model_path)

    @property
    def requested_model_path(self) -> str:
        """Ruta o especificador del modelo originalmente solicitado."""
        return str(self._requested_config.model_path)

    @property
    def effective_end2end(self) -> Optional[bool]:
        """Estado verificado de operación end2end (NMS-Free) si aplica."""
        with self._lock:
            return self._effective_end2end

    @property
    def last_inference_model(self) -> Optional[str]:
        """Nombre del modelo efectivo que completó la inferencia más reciente."""
        with self._lock:
            return self._last_inference_model

    @staticmethod
    def _summarize_window(samples: Deque[float]) -> Dict[str, Optional[float]]:
        if not samples:
            return {"mean_ms": None, "p50_ms": None, "p95_ms": None, "p99_ms": None}
        ordered = sorted(samples)
        n = len(ordered)
        mean_val = round(sum(ordered) / n, 3)

        def _pct(p: float) -> float:
            idx = min(n - 1, max(0, int(math.ceil((p / 100.0) * n)) - 1))
            return round(ordered[idx], 3)

        return {
            "mean_ms": mean_val,
            "p50_ms": _pct(50.0),
            "p95_ms": _pct(95.0),
            "p99_ms": _pct(99.0),
        }

    @staticmethod
    def _sample_gpu_memory_snapshot() -> Dict[str, Optional[float]]:
        torch_mod = sys.modules.get("torch")
        if torch_mod is None:
            return {"vram_allocated_mb": None, "vram_reserved_mb": None}
        try:
            if not torch_mod.cuda.is_available():
                return {"vram_allocated_mb": None, "vram_reserved_mb": None}
            mib = 1024.0 * 1024.0
            return {
                "vram_allocated_mb": round(float(torch_mod.cuda.memory_allocated()) / mib, 2),
                "vram_reserved_mb": round(float(torch_mod.cuda.memory_reserved()) / mib, 2),
            }
        except Exception:
            return {"vram_allocated_mb": None, "vram_reserved_mb": None}

    @staticmethod
    def _is_cuda_exception(exc: BaseException) -> bool:
        msg = f"{type(exc).__name__}: {exc}".lower()
        return any(tok in msg for tok in ("cuda", "out of memory", "cudnn", "cublas", "nvml"))

    def unload(self) -> None:
        """Libera de forma idempotente la instancia del modelo y limpia caché CUDA si aplica."""
        with self._lock:
            self._model = None
            self._end2end_verified = False
            self._effective_end2end = None
            self._effective_fp16 = None
            self._effective_imgsz = None
            torch_mod = sys.modules.get("torch")
            if torch_mod is not None:
                try:
                    if torch_mod.cuda.is_available():
                        torch_mod.cuda.empty_cache()
                except Exception:
                    pass

    def close(self) -> None:
        """Cierra de forma permanente e idempotente el detector, impidiendo inferencias posteriores."""
        with self._lock:
            self._closed = True
            self.unload()

    def get_runtime_status(self) -> Dict[str, Any]:
        """Retorna una instantánea observable e inmutable del estado operativo del detector."""
        with self._lock:
            lat = self._summarize_window(self._latencies_ms)
            qwait = self._summarize_window(self._queue_waits_ms)
            mean_ms = lat["mean_ms"]
            inf_fps = round(1000.0 / mean_ms, 2) if mean_ms and mean_ms > 0.0 else None
            return {
                "requested_model": Path(str(self._requested_config.model_path)).name,
                "requested_weights_path": str(self._requested_config.model_path),
                "effective_model": Path(str(self._config.model_path)).name,
                "last_inference_model": self._last_inference_model,
                "weights_path": str(self._config.model_path),
                "device": self._config.device,
                "imgsz": self._config.imgsz,
                "effective_imgsz": self._effective_imgsz,
                "quantize": self._config.quantize,
                "effective_fp16": self._effective_fp16,
                "nms": self._config.nms,
                "augment": self._config.augment,
                "end2end": self._effective_end2end,
                "end2end_verified": self._end2end_verified,
                "deduplicate_iou_threshold": self._config.deduplicate_iou_threshold,
                "consolidate_frontal_confidence": self._config.consolidate_frontal_confidence,
                "frontal_aux_enabled": self._config.frontal_aux_enabled,
                "frontal_aux_imgsz": self._config.frontal_aux_imgsz if self._config.frontal_aux_enabled else None,
                "frontal_aux_trigger_confidence": self._config.frontal_aux_trigger_confidence,
                "fallback_enabled": self._config.fallback_enabled or self._using_fallback,
                "using_fallback": self._using_fallback,
                "fallback_reason": self._fallback_reason,
                "fallback_timestamp": self._fallback_timestamp,
                "is_loaded": self._model is not None,
                "ultralytics_version": _get_ultralytics_version(),
                "inference_metrics": {
                    "total_inferences": self._total_inferences,
                    "last_inference_model": self._last_inference_model,
                    "inferences_by_model": dict(self._inferences_by_model),
                    "inference_errors": self._inference_errors,
                    "cuda_errors": self._cuda_errors,
                    "init_errors": self._init_errors,
                    "fallback_count": self._fallback_count,
                    "last_recovery_ms": self._last_recovery_ms,
                    "frontal_aux_triggers": self._frontal_aux_triggers,
                    "frontal_aux_recoveries": self._frontal_aux_recoveries,
                    "duplicates_suppressed": self._duplicates_suppressed,
                    "latency_mean_ms": lat["mean_ms"],
                    "latency_p50_ms": lat["p50_ms"],
                    "latency_p95_ms": lat["p95_ms"],
                    "latency_p99_ms": lat["p99_ms"],
                    "inference_fps": inf_fps,
                    "queue_wait_mean_ms": qwait["mean_ms"],
                    "last_queue_wait_ms": self._last_queue_wait_ms,
                    "last_camera_code": self._last_camera_code,
                    "last_inference_at": self._last_inference_at,
                },
                "gpu_memory": self._sample_gpu_memory_snapshot(),
            }

    def _build_predict_kwargs(
        self, frame: np.ndarray, cfg: YoloDetectorConfig
    ) -> Dict[str, Any]:
        """Construye los argumentos de ``model.predict`` preservando valores explícitos."""
        kwargs: Dict[str, Any] = {
            "source": frame,
            "conf": cfg.confidence_threshold,
            "iou": cfg.iou_threshold,
            "device": cfg.device,
            "imgsz": cfg.imgsz,
            "classes": list(cfg.classes),
            "verbose": False,
            "save": False,
            "show": False,
        }
        allow_fp16 = self._model_factory is not None or cfg.device.strip().lower() != "cpu"
        if cfg.quantize is not None:
            if cfg.quantize == 16 and not allow_fp16:
                logger.warning(
                    "FP16 solicitado (quantize=16) en dispositivo '%s' sin CUDA activo; "
                    "usando precisión estándar compatible en CPU.",
                    cfg.device,
                )
            else:
                kwargs["quantize"] = cfg.quantize
        if cfg.nms is not None:
            kwargs["nms"] = cfg.nms
        if cfg.augment:
            kwargs["augment"] = True
        return kwargs

    def _instantiate_raw_model(self, cfg: YoloDetectorConfig) -> Any:
        """Instancia un modelo YOLO crudo (mock inyectado o Ultralytics real)."""
        if self._model_factory is not None:
            return self._model_factory(cfg.model_path)

        resolved_path = resolve_yolo_weights_path(cfg.model_path)
        if not resolved_path.is_file():
            raise FileNotFoundError(
                f"Archivo de pesos YOLO no encontrado en '{resolved_path}' (solicitado: '{cfg.model_path}')."
            )

        from ultralytics import YOLO

        model = YOLO(str(resolved_path))
        if cfg.device != "cpu":
            model.to(cfg.device)
        return model

    @staticmethod
    def _verify_nms_free_pre_predict(model: Any, cfg: YoloDetectorConfig) -> None:
        """
        Verifica antes de inferir si el modelo soporta modo NMS-Free nativo cuando ``nms=False``.
        """
        if cfg.nms is not False:
            return

        inner_model = getattr(model, "model", None)
        if inner_model is None:
            # Doble de prueba ligero sin .model interno
            explicit_e2e = getattr(model, "end2end", None)
            if explicit_e2e is False:
                raise ModelLoadError(
                    f"El modelo '{cfg.model_path}' reporta end2end=False y no soporta nms=False."
                )
            return

        layers = getattr(inner_model, "model", None)
        if layers is None or not hasattr(layers, "__getitem__"):
            return

        try:
            head = layers[-1]
        except Exception:
            return

        head_has_one2one = getattr(head, "one2one_cv2", None) is not None
        head_e2e = bool(getattr(head, "end2end", False))
        yaml_cfg = getattr(inner_model, "yaml", None)
        yaml_e2e = bool(yaml_cfg.get("end2end", False)) if isinstance(yaml_cfg, dict) else False

        if not (head_has_one2one and (head_e2e or yaml_e2e)):
            raise ModelLoadError(
                f"El modelo '{cfg.model_path}' no posee arquitectura NMS-Free / rama one2one "
                f"(yaml.end2end={yaml_e2e}, head.end2end={head_e2e}, has_one2one={head_has_one2one}) "
                f"requerida para nms=False."
            )

    def _verify_nms_free_post_predict(self, model: Any, cfg: YoloDetectorConfig) -> None:
        """
        Verifica sobre ``AutoBackend`` tras la primera inferencia que la ruta end2end
        permaneció activa cuando ``nms=False`` (y registra estado real).
        """
        predictor = getattr(model, "predictor", None)
        ab = getattr(predictor, "model", None) if predictor is not None else None
        if predictor is not None:
            pred_args = getattr(predictor, "args", None)
            pred_imgsz = getattr(pred_args, "imgsz", None) if pred_args is not None else None
            if isinstance(pred_imgsz, (list, tuple)) and pred_imgsz:
                self._effective_imgsz = int(pred_imgsz[0])
            elif isinstance(pred_imgsz, int):
                self._effective_imgsz = pred_imgsz
        if ab is not None and hasattr(ab, "fp16"):
            self._effective_fp16 = bool(getattr(ab, "fp16", False))

        if ab is not None and hasattr(ab, "end2end"):
            ab_e2e = bool(getattr(ab, "end2end", False))
            self._effective_end2end = ab_e2e

            one2one_active = None
            one2many_released = None
            ab_inner = getattr(ab, "model", None)
            ab_layers = getattr(ab_inner, "model", None) if ab_inner is not None else None
            if ab_layers is not None:
                try:
                    head = ab_layers[-1]
                    one2one_active = getattr(head, "one2one_cv2", None) is not None
                    one2many_released = getattr(head, "cv2", None) is None
                except Exception:
                    pass

            if cfg.nms is False:
                if not ab_e2e or one2one_active is False:
                    raise InferenceError(
                        f"Verificación NMS-Free fallida en '{cfg.model_path}': "
                        f"AutoBackend.end2end={ab_e2e}, one2one_cv2={one2one_active}."
                    )
            self._end2end_verified = True
            logger.info(
                "Estado AutoBackend verificado: modelo='%s', end2end=%s, one2one_cv2=%s, one2many_cv2_liberada=%s.",
                Path(str(cfg.model_path)).name,
                ab_e2e,
                one2one_active,
                one2many_released,
            )
            return

        explicit_e2e = getattr(model, "end2end", None)
        if cfg.nms is False and explicit_e2e is False:
            raise InferenceError(
                f"Verificación NMS-Free fallida en '{cfg.model_path}': end2end=False."
            )
        if explicit_e2e is not None:
            self._effective_end2end = bool(explicit_e2e)
        elif cfg.nms is False:
            self._effective_end2end = True
        self._end2end_verified = True

    def _can_attempt_fallback_locked(self) -> bool:
        """Determina si es seguro y no redundante conmutar al modelo de respaldo."""
        if not self._config.fallback_enabled or self._using_fallback:
            return False

        primary_spec = str(self._config.model_path).strip()
        fallback_spec = str(self._config.fallback_model_path).strip()
        experimental_overrides = (
            self._config.quantize is not None
            or self._config.nms is not None
            or self._config.augment
        )
        if experimental_overrides:
            return True

        if self._model_factory is not None:
            return Path(primary_spec).name.lower() != Path(fallback_spec).name.lower()

        try:
            return resolve_yolo_weights_path(primary_spec) != resolve_yolo_weights_path(fallback_spec)
        except Exception:
            return primary_spec != fallback_spec

    def _build_fallback_config(self) -> YoloDetectorConfig:
        """Construye la configuración estándar de respaldo para ``yolo11n.pt``."""
        target_path: Union[str, Path]
        if self._model_factory is not None:
            target_path = self._requested_config.fallback_model_path
        else:
            target_path = str(resolve_yolo_weights_path(self._requested_config.fallback_model_path))

        return YoloDetectorConfig(
            model_path=target_path,
            confidence_threshold=self._requested_config.confidence_threshold,
            device=self._requested_config.device,
            imgsz=640,
            iou_threshold=self._requested_config.iou_threshold,
            classes=self._requested_config.classes,
            quantize=None,
            nms=None,
            augment=False,
            fallback_enabled=False,
            fallback_model_path=self._requested_config.fallback_model_path,
            deduplicate_iou_threshold=self._requested_config.deduplicate_iou_threshold,
            consolidate_frontal_confidence=False,
            frontal_aux_enabled=False,
            frontal_aux_imgsz=None,
            frontal_aux_trigger_confidence=self._requested_config.frontal_aux_trigger_confidence,
        )

    def _activate_fallback_locked(self, exc: Exception, stage: str) -> Any:
        """
        Conmuta de forma atómica al modelo de respaldo, libera VRAM previa si hubo
        fallo CUDA/OOM, valida con un fotograma sintético de prueba y actualiza
        la telemetría interna del detector.
        """
        t_rec0 = time.perf_counter()
        fallback_cfg = self._build_fallback_config()
        reason_text = f"[{stage}] {type(exc).__name__}: {exc}"
        timestamp_utc = datetime.now(timezone.utc).isoformat()

        # Liberar referencia del modelo primario antes de instanciar fallback (crítico en OOM)
        self._model = None
        if self._is_cuda_exception(exc):
            gc.collect()
        torch_mod = sys.modules.get("torch")
        if torch_mod is not None:
            try:
                if torch_mod.cuda.is_available():
                    torch_mod.cuda.empty_cache()
            except Exception:
                pass

        fb_model = self._instantiate_raw_model(fallback_cfg)
        self._effective_end2end = None
        self._effective_fp16 = None
        self._end2end_verified = False
        self._effective_imgsz = fallback_cfg.imgsz
        if stage == "model_init":
            probe_frame = np.zeros((64, 64, 3), dtype=np.uint8)
            fb_model.predict(**self._build_predict_kwargs(probe_frame, fallback_cfg))
            self._verify_nms_free_post_predict(fb_model, fallback_cfg)

        self._model = fb_model
        self._config = fallback_cfg
        self._using_fallback = True
        self._fallback_reason = reason_text
        self._fallback_timestamp = timestamp_utc
        self._fallback_count += 1
        self._last_recovery_ms = round((time.perf_counter() - t_rec0) * 1000.0, 3)

        logger.warning(
            "FALLBACK YOLO ACTIVADO (%s): modelo_solicitado='%s' -> modelo_respaldo='%s' | "
            "device='%s' | motivo='%s' | timestamp_utc='%s'.",
            stage,
            self._requested_config.model_path,
            fallback_cfg.model_path,
            fallback_cfg.device,
            reason_text,
            timestamp_utc,
        )
        return self._model

    def load_model(self) -> Any:
        """
        Carga e inicializa el modelo YOLO de manera perezosa y segura para hilos.
        Si la inicialización falla y el fallback está habilitado, conmuta automáticamente
        al modelo de respaldo (``yolo11n.pt``).

        Lanza
        -----
        ModelLoadError
            Si no se pueden cargar los pesos ni activar un fallback funcional.
        """
        with self._lock:
            if self._closed:
                raise ModelLoadError("El detector YOLO ya fue cerrado mediante close().")
            if self._model is not None:
                return self._model

            try:
                model = self._instantiate_raw_model(self._config)
                self._verify_nms_free_pre_predict(model, self._config)
                self._model = model
                logger.info(
                    "Detector YOLO inicializado: modelo_solicitado='%s', modelo_efectivo='%s', "
                    "weights_path='%s', device='%s', imgsz=%d, quantize=%r, nms=%r, "
                    "fallback_enabled=%s, ultralytics='%s'.",
                    Path(str(self._requested_config.model_path)).name,
                    Path(str(self._config.model_path)).name,
                    self._config.model_path,
                    self._config.device,
                    self._config.imgsz,
                    self._config.quantize,
                    self._config.nms,
                    self._config.fallback_enabled,
                    _get_ultralytics_version(),
                )
                return self._model
            except Exception as primary_exc:
                self._init_errors += 1
                if self._is_cuda_exception(primary_exc):
                    self._cuda_errors += 1
                if self._can_attempt_fallback_locked():
                    logger.warning(
                        "Fallo inicializando modelo YOLO primario '%s' (%s: %s). Intentando fallback a '%s'.",
                        self._config.model_path,
                        type(primary_exc).__name__,
                        primary_exc,
                        self._config.fallback_model_path,
                    )
                    try:
                        return self._activate_fallback_locked(primary_exc, stage="model_init")
                    except Exception as fb_exc:
                        logger.error(
                            "Fallo crítico también al activar modelo de respaldo '%s': %s",
                            self._config.fallback_model_path,
                            fb_exc,
                        )
                        if self._model_factory is not None:
                            raise ModelLoadError(
                                f"Fallo al instanciar el modelo con model_factory inyectado "
                                f"(y fallo en fallback '{self._config.fallback_model_path}'): "
                                f"primario={primary_exc}; fallback={fb_exc}"
                            ) from fb_exc
                        raise ModelLoadError(
                            f"Error al cargar el modelo YOLO desde '{self._config.model_path}' "
                            f"y su respaldo '{self._config.fallback_model_path}': "
                            f"primario={primary_exc}; fallback={fb_exc}"
                        ) from fb_exc

                if self._model_factory is not None:
                    raise ModelLoadError(
                        f"Fallo al instanciar el modelo con model_factory inyectado: {primary_exc}"
                    ) from primary_exc
                if isinstance(primary_exc, ModelLoadError):
                    raise
                raise ModelLoadError(
                    f"Error al cargar el modelo YOLO desde '{self._config.model_path}': {primary_exc}"
                ) from primary_exc

    @staticmethod
    def _parse_prediction_results(
        results: Any,
        frame_width: int,
        frame_height: int,
        cfg: YoloDetectorConfig,
        *,
        min_confidence_override: Optional[float] = None,
    ) -> Sequence[RawVehicleDetection]:
        """Extrae, valida y recorta detecciones vehiculares desde la salida de Ultralytics."""
        if not results or len(results) == 0:
            return ()

        raw_boxes = getattr(results[0], "boxes", None)
        if raw_boxes is None or len(raw_boxes) == 0:
            return ()

        eff_min_conf = (
            float(min_confidence_override)
            if min_confidence_override is not None
            else cfg.confidence_threshold
        )

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

            if not (
                math.isfinite(x1)
                and math.isfinite(y1)
                and math.isfinite(x2)
                and math.isfinite(y2)
                and math.isfinite(conf)
            ):
                raise InferenceError(
                    f"Salida no finita (NaN/Inf) detectada en predicción YOLO: "
                    f"xyxy=({x1}, {y1}, {x2}, {y2}), conf={conf}."
                )

            # Filtro de umbral de confianza
            if conf < eff_min_conf:
                continue

            # Filtro defensivo de clases configuradas y clases vehiculares COCO
            if cls_id not in cfg.classes or cls_id not in COCO_VEHICLE_CLASSES:
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

    def _run_inference_with_frontal_refinement(
        self,
        model: Any,
        frame: np.ndarray,
        frame_width: int,
        frame_height: int,
        cfg: YoloDetectorConfig,
    ) -> Sequence[RawVehicleDetection]:
        """
        Ejecuta el pase primario de inferencia y, cuando está habilitado el modo
        de afinación frontal (``nms=False`` / ``frontal_aux_enabled`` sobre modelo real
        o mock con ``supports_multiscale_aux=True``), consolida anclas partidas y
        ejecuta una sonda auxiliar condicional a ``frontal_aux_imgsz`` ante ausencias
        o candidatos frontales débiles.
        """
        use_advanced_frontal = bool(
            cfg.nms is False
            and (
                self._model_factory is None
                or getattr(model, "supports_multiscale_aux", False)
            )
        )

        primary_kwargs = self._build_predict_kwargs(frame, cfg)
        candidate_floor = cfg.confidence_threshold
        if use_advanced_frontal and cfg.consolidate_frontal_confidence:
            candidate_floor = min(0.10, cfg.confidence_threshold)
            primary_kwargs["conf"] = candidate_floor

        results = model.predict(**primary_kwargs)
        if not self._end2end_verified:
            self._verify_nms_free_post_predict(model, cfg)

        raw_primary = self._parse_prediction_results(
            results,
            frame_width,
            frame_height,
            cfg,
            min_confidence_override=candidate_floor,
        )

        if cfg.deduplicate_iou_threshold is not None:
            primary_dedup, supp_p = deduplicate_and_consolidate_detections(
                raw_primary,
                iou_threshold=cfg.deduplicate_iou_threshold,
                consolidate_split_confidence=cfg.consolidate_frontal_confidence,
            )
            self._duplicates_suppressed += supp_p
        else:
            primary_dedup = tuple(raw_primary)

        final_candidates = primary_dedup

        # Sonda auxiliar multiescala condicional para recuperación de vehículos frontales
        if (
            use_advanced_frontal
            and cfg.frontal_aux_enabled
            and cfg.frontal_aux_imgsz is not None
            and cfg.frontal_aux_imgsz != cfg.imgsz
        ):
            trigger_conf = cfg.frontal_aux_trigger_confidence
            has_strong = any(d.confidence >= trigger_conf for d in primary_dedup)
            has_weak = any(candidate_floor <= d.confidence < trigger_conf for d in primary_dedup)
            if not has_strong or has_weak:
                self._frontal_aux_triggers += 1
                aux_cfg = replace(cfg, imgsz=cfg.frontal_aux_imgsz)
                aux_kwargs = self._build_predict_kwargs(frame, aux_cfg)
                aux_kwargs["conf"] = candidate_floor
                aux_results = model.predict(**aux_kwargs)
                raw_aux = self._parse_prediction_results(
                    aux_results,
                    frame_width,
                    frame_height,
                    aux_cfg,
                    min_confidence_override=candidate_floor,
                )
                if cfg.deduplicate_iou_threshold is not None:
                    aux_dedup, supp_a = deduplicate_and_consolidate_detections(
                        raw_aux,
                        iou_threshold=cfg.deduplicate_iou_threshold,
                        consolidate_split_confidence=cfg.consolidate_frontal_confidence,
                    )
                    self._duplicates_suppressed += supp_a
                else:
                    aux_dedup = tuple(raw_aux)

                if aux_dedup:
                    merged, supp_m = deduplicate_and_consolidate_detections(
                        tuple(primary_dedup) + tuple(aux_dedup),
                        iou_threshold=cfg.deduplicate_iou_threshold or 0.55,
                        consolidate_split_confidence=cfg.consolidate_frontal_confidence,
                    )
                    self._duplicates_suppressed += supp_m
                    prev_strong = sum(1 for d in primary_dedup if d.confidence >= trigger_conf)
                    new_strong = sum(1 for d in merged if d.confidence >= trigger_conf)
                    prev_valid = sum(1 for d in primary_dedup if d.confidence >= cfg.confidence_threshold)
                    new_valid = sum(1 for d in merged if d.confidence >= cfg.confidence_threshold)
                    if new_strong > prev_strong or new_valid > prev_valid:
                        self._frontal_aux_recoveries += 1
                    final_candidates = merged

        # Garantizar estrictamente el contrato de umbral mínimo de confianza de salida
        return tuple(d for d in final_candidates if d.confidence >= cfg.confidence_threshold)

    def _record_inference_success_locked(self, t_start: float) -> None:
        """Registra latencia y modelo efectivo exacto de una inferencia completada."""
        elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 3)
        model_name = Path(str(self._config.model_path)).name
        self._latencies_ms.append(elapsed_ms)
        self._total_inferences += 1
        self._last_inference_at = datetime.now(timezone.utc).isoformat()
        self._last_inference_model = model_name
        self._inferences_by_model[model_name] = self._inferences_by_model.get(model_name, 0) + 1

    def detect(
        self,
        frame: np.ndarray,
        *,
        camera_code: Optional[str] = None,
        max_wait_ms: Optional[float] = None,
    ) -> Sequence[RawVehicleDetection]:
        """
        Ejecuta la inferencia sobre un fotograma BGR uint8 y extrae las detecciones de vehículos.

        Si el modelo principal falla durante la inferencia (incluyendo incompatibilidad
        runtime, error CUDA o salida numérica inválida) y el fallback está habilitado,
        conmuta al modelo de respaldo (``yolo11n.pt``) y reintenta el fotograma actual
        una sola vez antes de fallar.

        Parámetros
        ----------
        frame : np.ndarray
            Fotograma BGR con forma (H, W, 3) y dtype uint8.
        camera_code : Optional[str]
            Código de cámara solicitante para trazabilidad y observabilidad.
        max_wait_ms : Optional[float]
            Tiempo máximo de espera (ms) por el lock GPU antes de aplicar backpressure.

        Retorna
        -------
        Sequence[RawVehicleDetection]
            Secuencia inmutable (tupla) de detecciones vehiculares válidas.

        Lanza
        -----
        FrameValidationError
            Si el fotograma no cumple las especificaciones BGR uint8 3D.
        InferenceBackpressureError
            Si el lock GPU supera ``max_wait_ms`` bajo contención.
        InferenceError
            Si ocurre un fallo irrecuperable en el motor de inferencia YOLO.
        ModelLoadError
            Si la carga perezosa del modelo falla sin respaldo operativo.
        """
        frame_width, frame_height = validate_bgr_frame(frame)
        t_wait0 = time.perf_counter()
        if max_wait_ms is not None and max_wait_ms > 0.0:
            acquired = self._lock.acquire(timeout=max_wait_ms / 1000.0)
            if not acquired:
                raise InferenceBackpressureError(
                    f"Backpressure GPU: espera superó {max_wait_ms:.1f} ms para cámara '{camera_code or 'UNKNOWN'}'."
                )
        else:
            self._lock.acquire()

        queue_wait_ms = round((time.perf_counter() - t_wait0) * 1000.0, 3)
        try:
            if self._closed:
                raise InferenceError("El detector YOLO ya fue cerrado mediante close().")
            self._last_queue_wait_ms = queue_wait_ms
            self._queue_waits_ms.append(queue_wait_ms)
            if camera_code is not None:
                self._last_camera_code = camera_code

            model = self.load_model()
            t_inf0 = time.perf_counter()
            try:
                parsed = self._run_inference_with_frontal_refinement(
                    model,
                    frame,
                    frame_width,
                    frame_height,
                    self._config,
                )
                self._record_inference_success_locked(t_inf0)
                return parsed
            except Exception as primary_exc:
                self._inference_errors += 1
                if self._is_cuda_exception(primary_exc):
                    self._cuda_errors += 1
                if self._can_attempt_fallback_locked():
                    logger.warning(
                        "Fallo durante inferencia runtime con '%s' (%s: %s). Conmutando a respaldo '%s' "
                        "y reintentando fotograma actual una vez.",
                        self._config.model_path,
                        type(primary_exc).__name__,
                        primary_exc,
                        self._config.fallback_model_path,
                    )
                    try:
                        fb_model = self._activate_fallback_locked(
                            primary_exc, stage="runtime_inference"
                        )
                        t_fb0 = time.perf_counter()
                        fb_results = fb_model.predict(
                            **self._build_predict_kwargs(frame, self._config)
                        )
                        self._verify_nms_free_post_predict(fb_model, self._config)
                        parsed_fb = self._parse_prediction_results(
                            fb_results, frame_width, frame_height, self._config
                        )
                        self._record_inference_success_locked(t_fb0)
                        return parsed_fb
                    except Exception as fb_exc:
                        self._inference_errors += 1
                        if self._is_cuda_exception(fb_exc):
                            self._cuda_errors += 1
                        logger.error(
                            "Fallo irrecuperable tras fallback runtime a '%s': %s",
                            self._config.model_path,
                            fb_exc,
                        )
                        raise InferenceError(
                            f"Error durante la inferencia YOLO en {self._config.device} "
                            f"incluso tras fallback a '{self._config.model_path}': {fb_exc}"
                        ) from fb_exc

                if isinstance(primary_exc, InferenceError):
                    raise
                raise InferenceError(
                    f"Error durante la inferencia YOLO en {self._config.device}: {primary_exc}"
                ) from primary_exc
        finally:
            self._lock.release()
