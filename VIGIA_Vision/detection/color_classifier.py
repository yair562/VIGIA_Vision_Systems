"""
VIGIA_Vision.detection.color_classifier
=======================================
Módulo independiente y desacoplado de clasificación de color vehicular para
VIGÍA Vision Systems (VIGÍA-VISION-05B).

Características de diseño:
- Desacoplado del detector YOLO (funciona con ``YOLO26x``, ``YOLO11n`` o cualquier
  detector que emita ``BoundingBox``).
- Sin modelos pesados de aprendizaje profundo: opera mediante procesamiento
  vectorizado en CPU sobre el recorte ROI del fotograma BGR original en
  espacios ``HSV`` y perceptual ``CIELAB`` (< 1.5 ms, 0 MB VRAM adicional).
- No muta el fotograma de entrada ni las estructuras ``BoundingBox`` o
  ``RawVehicleDetection``.
- Criterios conservadores orientados a trazabilidad operativa: cuando la región
  útil es insuficiente, existe deslumbramiento severo, subexposición crítica o
  empate cromático, emite ``VehicleColor.UNKNOWN`` registrando el motivo y las
  limitaciones de calidad de la región analizada.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Protocol, Tuple, Union, runtime_checkable

import cv2
import numpy as np

from VIGIA_Core.config.env_loader import get_setting
from VIGIA_Vision.detection.models import BoundingBox


class VehicleColor(str, Enum):
    """Catálogo taxonómico canónico de colores vehiculares en VIGÍA."""

    WHITE = "WHITE"
    BLACK = "BLACK"
    GRAY = "GRAY"
    SILVER = "SILVER"
    RED = "RED"
    BLUE = "BLUE"
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    BROWN = "BROWN"
    ORANGE = "ORANGE"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class ColorClassificationStatus(str, Enum):
    """Estado estructurado de la clasificación cromática vehicular."""

    CLASSIFIED = "CLASSIFIED"
    LOW_CONFIDENCE_UNKNOWN = "LOW_CONFIDENCE_UNKNOWN"
    INSUFFICIENT_REGION = "INSUFFICIENT_REGION"
    LOW_ILLUMINATION = "LOW_ILLUMINATION"
    OVEREXPOSED_GLARE = "OVEREXPOSED_GLARE"
    AMBIGUOUS_COLOR = "AMBIGUOUS_COLOR"
    INVALID_DETECTION = "INVALID_DETECTION"
    CLASSIFIER_ERROR = "CLASSIFIER_ERROR"


@dataclass(frozen=True)
class ColorRegionQuality:
    """Indicadores de calidad geométrica, fotométrica y muestral de la carrocería."""

    bbox_area_px: int
    usable_body_pixels: int
    usable_pixel_ratio: float
    mean_luminance_l: float
    std_luminance_l: float
    mean_saturation_s: float
    mean_chroma_ab: float
    shadow_ratio: float
    glare_ratio: float
    background_excluded_ratio: float
    sharpness_laplacian: float
    is_sufficient: bool
    limitations: Tuple[str, ...] = ()


@dataclass(frozen=True)
class VehicleColorResult:
    """
    Resultado estructurado e inmutable de clasificación de color vehicular.

    Nota sobre ``confidence``: representa un índice heurístico acotado en
    ``[0.0, 1.0]`` derivado de pureza espectral/acromática, margen frente al
    segundo candidato y calidad muestral. No constituye una probabilidad
    estadística calibrada ni sustituye validación sobre Ground Truth externo.
    """

    predominant_color: VehicleColor
    confidence: float
    status: ColorClassificationStatus
    quality: ColorRegionQuality
    secondary_color: Optional[VehicleColor] = None
    runner_up_margin: float = 0.0
    category_scores: Mapping[str, float] = field(default_factory=dict)
    dominant_lab: Optional[Tuple[float, float, float]] = None
    dominant_hsv: Optional[Tuple[float, float, float]] = None
    vehicle_class: Optional[str] = None
    detection_confidence: Optional[float] = None
    processing_time_ms: float = 0.0

    def __post_init__(self) -> None:
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError(f"confidence={self.confidence!r} fuera del rango [0.0, 1.0].")
        object.__setattr__(self, "confidence", round(float(self.confidence), 4))
        object.__setattr__(self, "runner_up_margin", round(float(self.runner_up_margin), 4))
        object.__setattr__(self, "processing_time_ms", round(float(self.processing_time_ms), 3))
        if isinstance(self.predominant_color, str) and not isinstance(self.predominant_color, VehicleColor):
            object.__setattr__(self, "predominant_color", VehicleColor(self.predominant_color))

    @property
    def color(self) -> VehicleColor:
        """Alias compatible con VehicleColorResult de classification."""
        return self.predominant_color

    @property
    def quality_metrics(self) -> ColorRegionQuality:
        """Alias compatible con ColorQualityMetrics."""
        return self.quality

    @property
    def is_reliable(self) -> bool:
        """True si fue clasificado con margen y confianza suficiente."""
        return self.status == ColorClassificationStatus.CLASSIFIED and self.confidence >= 0.40

    @property
    def reason(self) -> str:
        """Justificación interpretable del dictamen (o motivo de rechazo a UNKNOWN)."""
        if self.quality and self.quality.limitations:
            return f"{self.status.value}: {', '.join(self.quality.limitations)}"
        return f"{self.status.value}: OK"

    @property
    def dominant_rgb(self) -> Optional[Tuple[int, int, int]]:
        """Color RGB representativo estimado a partir de dominant_hsv."""
        if self.dominant_hsv is not None:
            h, s, v = self.dominant_hsv
            hsv_pix = np.uint8([[[int(round(h)), int(round(s)), int(round(v))]]])
            rgb = cv2.cvtColor(hsv_pix, cv2.COLOR_HSV2RGB)[0, 0]
            return (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        return None

    @property
    def hsv_stats(self) -> Dict[str, float]:
        """Estadísticas descriptivas HSV."""
        if self.dominant_hsv is not None:
            return {
                "mean_h": float(self.dominant_hsv[0]),
                "mean_s": float(self.dominant_hsv[1]),
                "mean_v": float(self.dominant_hsv[2]),
            }
        return {"mean_h": 0.0, "mean_s": 0.0, "mean_v": 0.0}

    @classmethod
    def unknown(
        cls,
        reason: str,
        status: ColorClassificationStatus = ColorClassificationStatus.LOW_CONFIDENCE_UNKNOWN,
        quality: Optional[ColorRegionQuality] = None,
        confidence: float = 0.0,
    ) -> VehicleColorResult:
        """Constructor auxiliar fail-safe para resultado UNKNOWN."""
        q = quality or ColorRegionQuality(
            bbox_area_px=0,
            usable_body_pixels=0,
            usable_pixel_ratio=0.0,
            mean_luminance_l=0.0,
            std_luminance_l=0.0,
            mean_saturation_s=0.0,
            mean_chroma_ab=0.0,
            shadow_ratio=0.0,
            glare_ratio=0.0,
            background_excluded_ratio=0.0,
            sharpness_laplacian=0.0,
            is_sufficient=False,
            limitations=(reason,),
        )
        return cls(
            predominant_color=VehicleColor.UNKNOWN,
            confidence=max(0.0, min(1.0, float(confidence))),
            status=status,
            quality=q,
        )


@dataclass(frozen=True)
class VehicleColorConfig:
    """Parámetros centralizados y configurables de ``VehicleColorClassifier``."""

    enabled: bool = True
    min_detection_confidence: float = 0.25
    min_bbox_width: int = 28
    min_bbox_height: int = 28
    min_bbox_area_px: int = 900
    min_usable_pixels: int = 80
    min_usable_ratio: float = 0.12
    min_luminance_v: float = 26.0
    max_glare_ratio: float = 0.65
    glare_penalty_threshold: float = 0.22
    min_confidence_threshold: float = 0.40
    min_margin_over_runner_up: float = 0.10
    apply_illuminant_normalization: bool = True
    max_working_dim: int = 160

    def __post_init__(self) -> None:
        if not (0.0 <= self.min_detection_confidence <= 1.0):
            raise ValueError("min_detection_confidence debe estar en [0.0, 1.0].")
        if self.min_bbox_width < 8 or self.min_bbox_height < 8 or self.min_bbox_area_px < 64:
            raise ValueError("Dimensiones mínimas de ROI inválidas.")
        if self.min_usable_pixels < 10 or not (0.0 < self.min_usable_ratio <= 1.0):
            raise ValueError("Umbrales de región útil inválidos.")
        if not (0.0 <= self.min_confidence_threshold <= 1.0):
            raise ValueError("min_confidence_threshold debe estar en [0.0, 1.0].")
        if not (0.0 <= self.min_margin_over_runner_up <= 1.0):
            raise ValueError("min_margin_over_runner_up debe estar en [0.0, 1.0].")


def _parse_bool_setting(raw: Optional[str], default: bool) -> bool:
    if raw is None or not str(raw).strip():
        return default
    norm = str(raw).strip().lower()
    if norm in ("1", "true", "yes", "on", "si", "sí"):
        return True
    if norm in ("0", "false", "no", "off"):
        return False
    return default


def _parse_float_setting(raw: Optional[str], default: float) -> float:
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(str(raw).strip())
    except ValueError:
        return default


def _parse_int_setting(raw: Optional[str], default: int) -> int:
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(float(str(raw).strip()))
    except ValueError:
        return default


def load_color_config_from_env() -> VehicleColorConfig:
    """Carga ``VehicleColorConfig`` desde configuración centralizada ``VIGIA_COLOR_*``."""
    return VehicleColorConfig(
        enabled=_parse_bool_setting(get_setting("VIGIA_COLOR_ENABLED"), True),
        min_detection_confidence=_parse_float_setting(get_setting("VIGIA_COLOR_MIN_DETECTION_CONF"), 0.25),
        min_bbox_width=_parse_int_setting(get_setting("VIGIA_COLOR_MIN_BBOX_WIDTH"), 28),
        min_bbox_height=_parse_int_setting(get_setting("VIGIA_COLOR_MIN_BBOX_HEIGHT"), 28),
        min_bbox_area_px=_parse_int_setting(get_setting("VIGIA_COLOR_MIN_BBOX_AREA"), 900),
        min_usable_pixels=_parse_int_setting(get_setting("VIGIA_COLOR_MIN_USABLE_PIXELS"), 80),
        min_usable_ratio=_parse_float_setting(get_setting("VIGIA_COLOR_MIN_USABLE_RATIO"), 0.12),
        min_luminance_v=_parse_float_setting(get_setting("VIGIA_COLOR_MIN_LUMINANCE_V"), 26.0),
        max_glare_ratio=_parse_float_setting(get_setting("VIGIA_COLOR_MAX_GLARE_RATIO"), 0.65),
        glare_penalty_threshold=_parse_float_setting(get_setting("VIGIA_COLOR_GLARE_PENALTY_THRESHOLD"), 0.22),
        min_confidence_threshold=_parse_float_setting(get_setting("VIGIA_COLOR_MIN_CONFIDENCE"), 0.40),
        min_margin_over_runner_up=_parse_float_setting(get_setting("VIGIA_COLOR_MIN_MARGIN"), 0.10),
        apply_illuminant_normalization=_parse_bool_setting(
            get_setting("VIGIA_COLOR_NORMALIZE_ILLUMINANT"), True
        ),
        max_working_dim=_parse_int_setting(get_setting("VIGIA_COLOR_MAX_WORKING_DIM"), 160),
    )


@runtime_checkable
class IVehicleColorClassifier(Protocol):
    """Contrato inyectable para el clasificador modular de color vehicular."""

    def classify(
        self,
        frame: np.ndarray,
        bbox: BoundingBox,
        vehicle_class: Optional[str] = None,
        detection_confidence: Optional[float] = None,
    ) -> VehicleColorResult:
        """Clasifica el color predominante de la carrocería sin mutar las entradas."""
        ...  # pragma: no cover


_COLOR_ALIASES: Dict[str, VehicleColor] = {
    "WHITE": VehicleColor.WHITE,
    "BLANCO": VehicleColor.WHITE,
    "BLANCA": VehicleColor.WHITE,
    "BLACK": VehicleColor.BLACK,
    "NEGRO": VehicleColor.BLACK,
    "NEGRA": VehicleColor.BLACK,
    "GRAY": VehicleColor.GRAY,
    "GREY": VehicleColor.GRAY,
    "GRIS": VehicleColor.GRAY,
    "SILVER": VehicleColor.SILVER,
    "PLATEADO": VehicleColor.SILVER,
    "PLATA": VehicleColor.SILVER,
    "RED": VehicleColor.RED,
    "ROJO": VehicleColor.RED,
    "ROJA": VehicleColor.RED,
    "BLUE": VehicleColor.BLUE,
    "AZUL": VehicleColor.BLUE,
    "CYAN": VehicleColor.BLUE,
    "CELESTE": VehicleColor.BLUE,
    "GREEN": VehicleColor.GREEN,
    "VERDE": VehicleColor.GREEN,
    "YELLOW": VehicleColor.YELLOW,
    "AMARILLO": VehicleColor.YELLOW,
    "AMARILLA": VehicleColor.YELLOW,
    "BROWN": VehicleColor.BROWN,
    "CAFE": VehicleColor.BROWN,
    "MARRON": VehicleColor.BROWN,
    "ORANGE": VehicleColor.ORANGE,
    "NARANJA": VehicleColor.ORANGE,
    "ANARANJADO": VehicleColor.ORANGE,
    "OTHER": VehicleColor.OTHER,
    "OTRO": VehicleColor.OTHER,
    "PINK": VehicleColor.OTHER,
    "MAGENTA": VehicleColor.OTHER,
    "PURPLE": VehicleColor.OTHER,
    "UNKNOWN": VehicleColor.UNKNOWN,
    "INDETERMINATE": VehicleColor.UNKNOWN,
    "DESCONOCIDO": VehicleColor.UNKNOWN,
}


class VehicleColorNormalizer:
    """
    Normalizador cromático e idiomático para recortes vehiculares.

    Realiza dos funciones desacopladas:
    1. Compensación fotométrica acotada en espacio ``CIELAB`` sobre píxeles de
       referencia casi neutros (evitando el sesgo de Gray-World global sobre
       carrocerías monocromáticas saturadas).
    2. Normalización canónica de etiquetas al catálogo ``VehicleColor``.
    """

    @staticmethod
    def normalize_label(raw_color: Union[str, VehicleColor, None]) -> VehicleColor:
        """Mapea alias bilingües o variantes textuales hacia ``VehicleColor``."""
        if raw_color is None:
            return VehicleColor.UNKNOWN
        if isinstance(raw_color, VehicleColor):
            return raw_color
        cleaned = str(raw_color).strip().upper()
        if not cleaned:
            return VehicleColor.UNKNOWN
        return _COLOR_ALIASES.get(cleaned, VehicleColor.UNKNOWN)

    @staticmethod
    def normalize_crop_bgr(
        crop_bgr: np.ndarray,
        *,
        apply_illuminant: bool = True,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Tuple[str, ...]]:
        """
        Convierte el recorte BGR a ``HSV`` y ``CIELAB`` aplicando compensación
        acotada de iluminante cuando se habilita.
        """
        limitations = []
        hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
        lab = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2LAB)

        if not apply_illuminant:
            return crop_bgr, hsv, lab, ()

        # Estimación acotada de desvío de iluminante únicamente con referencias casi neutras
        # de luminosidad media-alta (parabrisas claro, matrícula, cemento o reflejos no saturados),
        # evitando que una carrocería roja o amarilla sesgue la corrección.
        l_f = lab[:, :, 0].astype(np.float32)
        a_f = lab[:, :, 1].astype(np.float32) - 128.0
        b_f = lab[:, :, 2].astype(np.float32) - 128.0
        chroma = np.hypot(a_f, b_f)

        neutral_refs = (chroma < 16.0) & (l_f >= 72.0) & (l_f <= 236.0)
        if int(neutral_refs.sum()) >= 36:
            shift_a = float(np.median(a_f[neutral_refs])) * 0.45
            shift_b = float(np.median(b_f[neutral_refs])) * 0.45
            # Acotar estrictamente el desplazamiento para preservar colores pastel reales
            shift_a = float(np.clip(shift_a, -5.0, 5.0))
            shift_b = float(np.clip(shift_b, -5.0, 5.0))
            if abs(shift_a) >= 0.8 or abs(shift_b) >= 0.8:
                lab_corr = lab.copy()
                lab_corr[:, :, 1] = np.clip(lab[:, :, 1].astype(np.float32) - shift_a, 0, 255).astype(np.uint8)
                lab_corr[:, :, 2] = np.clip(lab[:, :, 2].astype(np.float32) - shift_b, 0, 255).astype(np.uint8)
                norm_bgr = cv2.cvtColor(lab_corr, cv2.COLOR_LAB2BGR)
                norm_hsv = cv2.cvtColor(norm_bgr, cv2.COLOR_BGR2HSV)
                limitations.append("ILLUMINANT_COMPENSATED")
                return norm_bgr, norm_hsv, lab_corr, tuple(limitations)

        return crop_bgr, hsv, lab, ()


class VehicleColorClassifier:
    """
    Clasificador modular de color predominante de carrocería vehicular.

    Estrategia híbrida HSV + CIELAB con muestreo anatómico conservador:
    - Excluye el borde perimetral compatible con el fondo.
    - Excluye la banda inferior (neumáticos y sombra de rodadura) y la banda
      superior de cristales oscuros/reflejos de cielo.
    - Separa píxeles cromáticos puros de neutros acromáticos, distinguiendo
      ``SILVER`` vs ``GRAY`` por luminancia perceptual y contraste especular.
    """

    def __init__(
        self,
        config: Optional[VehicleColorConfig] = None,
        normalizer: Optional[VehicleColorNormalizer] = None,
    ) -> None:
        self._config = config or VehicleColorConfig()
        self._normalizer = normalizer or VehicleColorNormalizer()

    @property
    def config(self) -> VehicleColorConfig:
        return self._config

    @staticmethod
    def _empty_quality(bbox_area: int, limitations: Tuple[str, ...]) -> ColorRegionQuality:
        return ColorRegionQuality(
            bbox_area_px=bbox_area,
            usable_body_pixels=0,
            usable_pixel_ratio=0.0,
            mean_luminance_l=0.0,
            std_luminance_l=0.0,
            mean_saturation_s=0.0,
            mean_chroma_ab=0.0,
            shadow_ratio=0.0,
            glare_ratio=0.0,
            background_excluded_ratio=0.0,
            sharpness_laplacian=0.0,
            is_sufficient=False,
            limitations=limitations,
        )

    def _invalid_result(
        self,
        *,
        status: ColorClassificationStatus,
        bbox_area: int,
        limitations: Tuple[str, ...],
        vehicle_class: Optional[str],
        detection_confidence: Optional[float],
        t0: float,
    ) -> VehicleColorResult:
        return VehicleColorResult(
            predominant_color=VehicleColor.UNKNOWN,
            confidence=0.0,
            status=status,
            quality=self._empty_quality(bbox_area, limitations),
            category_scores={VehicleColor.UNKNOWN.value: 1.0},
            vehicle_class=vehicle_class,
            detection_confidence=detection_confidence,
            processing_time_ms=(time.perf_counter() - t0) * 1000.0,
        )

    @staticmethod
    def _build_anatomical_body_mask(
        h: int,
        w: int,
        hsv: np.ndarray,
        lab: np.ndarray,
        vehicle_class: Optional[str],
    ) -> Tuple[np.ndarray, float]:
        """
        Construye máscara booleana y mapa de pesos priorizando paneles de
        carrocería y excluyendo fondo perimetral, cristales oscuros y neumáticos.
        """
        v_ch = hsv[:, :, 2]
        s_ch = hsv[:, :, 1]
        l_f = lab[:, :, 0].astype(np.float32)
        a_f = lab[:, :, 1].astype(np.float32) - 128.0
        b_f = lab[:, :, 2].astype(np.float32) - 128.0

        yy, xx = np.ogrid[:h, :w]
        yn = yy / max(1, h - 1)
        xn = xx / max(1, w - 1)

        cls_norm = (vehicle_class or "").strip().upper()
        is_heavy = cls_norm in ("AUTOBUS", "BUS", "CAMION", "TRUCK")
        is_moto = cls_norm in ("MOTOCICLETA", "MOTORCYCLE")

        if is_heavy:
            # Autobús/camión: paneles pintados altos y laterales; excluir ruedas inferiores y márgenes estrechos
            anat_mask = (yn >= 0.16) & (yn <= 0.80) & (xn >= 0.10) & (xn <= 0.90)
            window_band = (yn >= 0.18) & (yn <= 0.50) & (xn >= 0.16) & (xn <= 0.84)
        elif is_moto:
            anat_mask = (yn >= 0.22) & (yn <= 0.72) & (xn >= 0.18) & (xn <= 0.82)
            window_band = np.zeros((h, w), dtype=bool)
        else:
            # Automóvil / camioneta: capó, puertas, laterales; excluir techo/cielo superior y ruedas inferiores
            anat_mask = (yn >= 0.26) & (yn <= 0.82) & (xn >= 0.10) & (xn <= 0.90)
            window_band = (yn >= 0.24) & (yn <= 0.44) & (xn >= 0.20) & (xn <= 0.80)

        # Exclusión de cristales oscuros / reflejo azulado muy pálido en banda de parabrisas
        glass_pixels = window_band & (
            ((v_ch < 75) & (s_ch < 52))
            | ((v_ch >= 220) & (s_ch < 22))
        )
        anat_mask = anat_mask & (~glass_pixels)

        # Exclusión adaptativa de fondo perimetral cuando el anillo exterior difiere claramente del núcleo
        bg_excluded_ratio = 0.0
        border_px = max(2, min(4, min(h, w) // 16))
        border_mask = np.zeros((h, w), dtype=bool)
        border_mask[:border_px, :] = True
        border_mask[:, :border_px] = True
        border_mask[:, -border_px:] = True

        core_mask = (yn >= 0.46) & (yn <= 0.74) & (xn >= 0.28) & (xn <= 0.72)
        if border_mask.any() and core_mask.any():
            bg_l = float(np.median(l_f[border_mask]))
            bg_a = float(np.median(a_f[border_mask]))
            bg_b = float(np.median(b_f[border_mask]))

            core_l = float(np.median(l_f[core_mask]))
            core_a = float(np.median(a_f[core_mask]))
            core_b = float(np.median(b_f[core_mask]))
            delta_core_bg = float(np.sqrt((core_l - bg_l) ** 2 + (core_a - bg_a) ** 2 + (core_b - bg_b) ** 2))

            # Solo excluir periferia coincidente con el fondo si el núcleo interior es cromática/luminosamente distinto
            if delta_core_bg > 15.0:
                periphery_zone = anat_mask & ((yn < 0.36) | (yn > 0.76) | (xn < 0.22) | (xn > 0.78))
                delta_pix_bg = np.sqrt((l_f - bg_l) ** 2 + (a_f - bg_a) ** 2 + (b_f - bg_b) ** 2)
                bg_like = periphery_zone & (delta_pix_bg < 9.5)
                if anat_mask.any():
                    bg_excluded_ratio = float(bg_like.sum()) / float(max(1, int(anat_mask.sum())))
                anat_mask = anat_mask & (~bg_like)

        return anat_mask, bg_excluded_ratio

    def classify(
        self,
        frame: np.ndarray,
        bbox: Any,
        vehicle_class: Optional[str] = None,
        detection_confidence: Optional[float] = None,
        detected_class: Optional[str] = None,
        **kwargs: Any,
    ) -> VehicleColorResult:
        """Clasifica el color vehicular predominante en el cuadro original sin alterarlo."""
        t0 = time.perf_counter()
        cfg = self._config

        if vehicle_class is None and detected_class is not None:
            vehicle_class = detected_class

        if not cfg.enabled:
            return self._invalid_result(
                status=ColorClassificationStatus.LOW_CONFIDENCE_UNKNOWN,
                bbox_area=0,
                limitations=("COLOR_CLASSIFIER_DISABLED",),
                vehicle_class=vehicle_class,
                detection_confidence=detection_confidence,
                t0=t0,
            )

        if frame is None or not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
            return self._invalid_result(
                status=ColorClassificationStatus.INVALID_DETECTION,
                bbox_area=0,
                limitations=("INVALID_BGR_FRAME",),
                vehicle_class=vehicle_class,
                detection_confidence=detection_confidence,
                t0=t0,
            )

        if not isinstance(bbox, BoundingBox):
            if isinstance(bbox, (tuple, list)) and len(bbox) == 4:
                try:
                    bbox = BoundingBox(
                        x_min=int(round(bbox[0])),
                        y_min=int(round(bbox[1])),
                        x_max=int(round(bbox[2])),
                        y_max=int(round(bbox[3])),
                    )
                except Exception:
                    pass
            elif hasattr(bbox, "x_min") and hasattr(bbox, "y_min") and hasattr(bbox, "x_max") and hasattr(bbox, "y_max"):
                try:
                    bbox = BoundingBox(
                        x_min=int(round(bbox.x_min)),
                        y_min=int(round(bbox.y_min)),
                        x_max=int(round(bbox.x_max)),
                        y_max=int(round(bbox.y_max)),
                    )
                except Exception:
                    pass

        if not isinstance(bbox, BoundingBox):
            return self._invalid_result(
                status=ColorClassificationStatus.INVALID_DETECTION,
                bbox_area=0,
                limitations=("INVALID_BOUNDING_BOX",),
                vehicle_class=vehicle_class,
                detection_confidence=detection_confidence,
                t0=t0,
            )

        if detection_confidence is not None and float(detection_confidence) < cfg.min_detection_confidence:
            return self._invalid_result(
                status=ColorClassificationStatus.INVALID_DETECTION,
                bbox_area=bbox.area,
                limitations=("DETECTION_CONFIDENCE_TOO_LOW",),
                vehicle_class=vehicle_class,
                detection_confidence=detection_confidence,
                t0=t0,
            )

        fh, fw = frame.shape[:2]
        x1 = max(0, min(bbox.x_min, fw - 1))
        y1 = max(0, min(bbox.y_min, fh - 1))
        x2 = max(0, min(bbox.x_max, fw))
        y2 = max(0, min(bbox.y_max, fh))
        cw = x2 - x1
        ch = y2 - y1
        bbox_area = max(0, cw * ch)

        if cw < cfg.min_bbox_width or ch < cfg.min_bbox_height or bbox_area < cfg.min_bbox_area_px:
            return self._invalid_result(
                status=ColorClassificationStatus.INSUFFICIENT_REGION,
                bbox_area=bbox_area,
                limitations=("BBOX_TOO_SMALL",),
                vehicle_class=vehicle_class,
                detection_confidence=detection_confidence,
                t0=t0,
            )

        # Vista de solo lectura y reducción controlada si la caja es muy grande
        crop_view = frame[y1:y2, x1:x2]
        max_dim = max(cw, ch)
        if max_dim > cfg.max_working_dim:
            scale = cfg.max_working_dim / float(max_dim)
            work_w = max(cfg.min_bbox_width, int(round(cw * scale)))
            work_h = max(cfg.min_bbox_height, int(round(ch * scale)))
            work_bgr = cv2.resize(crop_view, (work_w, work_h), interpolation=cv2.INTER_AREA)
        else:
            work_bgr = crop_view

        wh, ww = work_bgr.shape[:2]
        gray_work = cv2.cvtColor(work_bgr, cv2.COLOR_BGR2GRAY)
        sharpness = float(cv2.Laplacian(gray_work, cv2.CV_32F).var())

        norm_bgr, hsv, lab, norm_notes = self._normalizer.normalize_crop_bgr(
            work_bgr,
            apply_illuminant=cfg.apply_illuminant_normalization,
        )

        limitations = list(norm_notes)
        if max(cw, ch) < 56:
            limitations.append("LOW_RESOLUTION_CROP")
        if sharpness < 35.0:
            limitations.append("MOTION_OR_DEFOCUS_BLUR")

        anat_mask, bg_excluded_ratio = self._build_anatomical_body_mask(wh, ww, hsv, lab, vehicle_class)
        anat_pixels = int(anat_mask.sum())
        if anat_pixels < cfg.min_usable_pixels:
            return VehicleColorResult(
                predominant_color=VehicleColor.UNKNOWN,
                confidence=0.0,
                status=ColorClassificationStatus.INSUFFICIENT_REGION,
                quality=self._empty_quality(bbox_area, tuple(limitations + ["INSUFFICIENT_ANATOMICAL_AREA"])),
                category_scores={VehicleColor.UNKNOWN.value: 1.0},
                vehicle_class=vehicle_class,
                detection_confidence=detection_confidence,
                processing_time_ms=(time.perf_counter() - t0) * 1000.0,
            )

        h_ch = hsv[:, :, 0]
        s_ch = hsv[:, :, 1]
        v_ch = hsv[:, :, 2]
        l_ch = lab[:, :, 0]
        a_f = lab[:, :, 1].astype(np.float32) - 128.0
        b_f = lab[:, :, 2].astype(np.float32) - 128.0
        chroma_ab = np.hypot(a_f, b_f)

        # Evaluación global fotométrica dentro de la zona anatómica
        anat_v = v_ch[anat_mask]
        anat_l = l_ch[anat_mask].astype(np.float32)
        v_p75 = float(np.percentile(anat_v, 75))
        v_mean_anat = float(anat_v.mean())

        if v_p75 < cfg.min_luminance_v and v_mean_anat < (cfg.min_luminance_v - 2.0):
            limitations.append("LOW_AMBIENT_ILLUMINATION")
            quality = ColorRegionQuality(
                bbox_area_px=bbox_area,
                usable_body_pixels=0,
                usable_pixel_ratio=0.0,
                mean_luminance_l=round(float(anat_l.mean()), 2),
                std_luminance_l=round(float(anat_l.std()), 2),
                mean_saturation_s=round(float(s_ch[anat_mask].mean()), 2),
                mean_chroma_ab=round(float(chroma_ab[anat_mask].mean()), 2),
                shadow_ratio=1.0,
                glare_ratio=0.0,
                background_excluded_ratio=round(bg_excluded_ratio, 4),
                sharpness_laplacian=round(sharpness, 2),
                is_sufficient=False,
                limitations=tuple(limitations),
            )
            return VehicleColorResult(
                predominant_color=VehicleColor.UNKNOWN,
                confidence=0.0,
                status=ColorClassificationStatus.LOW_ILLUMINATION,
                quality=quality,
                category_scores={VehicleColor.UNKNOWN.value: 1.0},
                vehicle_class=vehicle_class,
                detection_confidence=detection_confidence,
                processing_time_ms=(time.perf_counter() - t0) * 1000.0,
            )

        # Detección de artefactos: reflejo especular saturado (clipping) vs sombras profundas
        min_bgr = np.min(norm_bgr, axis=2)
        specular_glare = anat_mask & (v_ch >= 250) & (s_ch <= 16) & (min_bgr >= 245)
        deep_shadow = anat_mask & (v_ch < 24) & (l_ch < 22)

        glare_ratio = float(specular_glare.sum()) / float(anat_pixels)
        shadow_ratio = float(deep_shadow.sum()) / float(anat_pixels)

        # En escenas con carrocería muy oscura de pintura negra real (V ~ 26..75), conservar V >= 24;
        # en escenas luminosas (P75(V) > 105), descartar recovecos/parrilla negra muy oscuros (V < 42, S < 45)
        # si ocupan una fracción minoritaria de la carrocería para no contaminar pintura viva con rejillas.
        minor_dark_grille = np.zeros_like(anat_mask)
        if v_p75 > 105.0:
            cand_grille = anat_mask & (v_ch < 44) & (s_ch < 45) & (chroma_ab < 11.0)
            if float(cand_grille.sum()) / float(anat_pixels) < 0.25:
                minor_dark_grille = cand_grille

        usable_mask = anat_mask & (~specular_glare) & (~deep_shadow) & (~minor_dark_grille)
        usable_px = int(usable_mask.sum())
        usable_ratio_total = float(usable_px) / float(max(1, wh * ww))
        usable_ratio_anat = float(usable_px) / float(anat_pixels)

        u_l = l_ch[usable_mask].astype(np.float32) if usable_px > 0 else anat_l
        u_s = s_ch[usable_mask].astype(np.float32) if usable_px > 0 else s_ch[anat_mask].astype(np.float32)
        u_c = chroma_ab[usable_mask] if usable_px > 0 else chroma_ab[anat_mask]
        mean_l = float(u_l.mean())
        std_l = float(u_l.std())
        mean_s = float(u_s.mean())
        mean_c = float(u_c.mean())

        if glare_ratio > cfg.max_glare_ratio:
            limitations.append("EXCESSIVE_SPECULAR_GLARE")
            quality = ColorRegionQuality(
                bbox_area_px=bbox_area,
                usable_body_pixels=usable_px,
                usable_pixel_ratio=round(usable_ratio_total, 4),
                mean_luminance_l=round(mean_l, 2),
                std_luminance_l=round(std_l, 2),
                mean_saturation_s=round(mean_s, 2),
                mean_chroma_ab=round(mean_c, 2),
                shadow_ratio=round(shadow_ratio, 4),
                glare_ratio=round(glare_ratio, 4),
                background_excluded_ratio=round(bg_excluded_ratio, 4),
                sharpness_laplacian=round(sharpness, 2),
                is_sufficient=False,
                limitations=tuple(limitations),
            )
            return VehicleColorResult(
                predominant_color=VehicleColor.UNKNOWN,
                confidence=0.0,
                status=ColorClassificationStatus.OVEREXPOSED_GLARE,
                quality=quality,
                category_scores={VehicleColor.UNKNOWN.value: 1.0},
                vehicle_class=vehicle_class,
                detection_confidence=detection_confidence,
                processing_time_ms=(time.perf_counter() - t0) * 1000.0,
            )

        if usable_px < cfg.min_usable_pixels or usable_ratio_total < cfg.min_usable_ratio:
            limitations.append("INSUFFICIENT_USABLE_BODY_REGION")
            quality = ColorRegionQuality(
                bbox_area_px=bbox_area,
                usable_body_pixels=usable_px,
                usable_pixel_ratio=round(usable_ratio_total, 4),
                mean_luminance_l=round(mean_l, 2),
                std_luminance_l=round(std_l, 2),
                mean_saturation_s=round(mean_s, 2),
                mean_chroma_ab=round(mean_c, 2),
                shadow_ratio=round(shadow_ratio, 4),
                glare_ratio=round(glare_ratio, 4),
                background_excluded_ratio=round(bg_excluded_ratio, 4),
                sharpness_laplacian=round(sharpness, 2),
                is_sufficient=False,
                limitations=tuple(limitations),
            )
            return VehicleColorResult(
                predominant_color=VehicleColor.UNKNOWN,
                confidence=0.0,
                status=ColorClassificationStatus.INSUFFICIENT_REGION,
                quality=quality,
                category_scores={VehicleColor.UNKNOWN.value: 1.0},
                vehicle_class=vehicle_class,
                detection_confidence=detection_confidence,
                processing_time_ms=(time.perf_counter() - t0) * 1000.0,
            )

        if glare_ratio > cfg.glare_penalty_threshold:
            limitations.append("MODERATE_SPECULAR_GLARE")
        if shadow_ratio > 0.25:
            limitations.append("PARTIAL_SHADOW_OCCLUSION")

        # Vectores 1D sobre píxeles útiles de carrocería
        uh = h_ch[usable_mask]
        us = s_ch[usable_mask]
        uv = v_ch[usable_mask]
        ul = l_ch[usable_mask].astype(np.float32)
        ua = a_f[usable_mask]
        ub = b_f[usable_mask]
        uc = chroma_ab[usable_mask]

        # Separación cromático vs acromático combinando S (HSV) y C*_ab (CIELAB)
        chromatic = (
            ((us >= 46) & (uv >= 34) & (uc >= 11.0))
            | ((us >= 34) & (uc >= 15.5) & (uv >= 45))
            | ((us >= 55) & (uv >= 26) & (uc >= 9.5))
        )

        # Máscaras cromáticas vectorizadas (OpenCV Hue in [0..179])
        yellow_mask = chromatic & (uh >= 18) & (uh <= 36) & (uv >= 82) & (ub >= 17.0) & (
            (uh >= 22) | (ub >= 1.40 * np.maximum(1.0, ua))
        )
        orange_mask = (
            chromatic
            & (~yellow_mask)
            & (uh >= 7)
            & (uh <= 20)
            & (uv >= 120)
            & (us >= 82)
            & (ua >= 8.0)
            & (ub >= 20.0)
            & (ul >= 125.0)
        )
        brown_mask = (
            chromatic
            & (~yellow_mask)
            & (~orange_mask)
            & (uh >= 7)
            & (uh <= 23)
            & (uv < 142)
            & (ul < 126.0)
            & (us >= 42)
            & (ua >= 2.0)
            & (ub >= 6.0)
            & (ua < 44.0)
        )
        other_mask = (
            chromatic
            & (
                ((uh >= 135) & (uh <= 165) & (us >= 40) & (uc >= 12.5))
                | ((uh >= 166) & (uh <= 171) & (ul >= 152.0) & (ub < 12.0) & (uc >= 14.0))
            )
        )
        red_mask = (
            chromatic
            & (~orange_mask)
            & (~brown_mask)
            & (~other_mask)
            & ((uh <= 8) | (uh >= 166))
            & (ua >= 9.0)
        )
        green_mask = chromatic & (uh >= 37) & (uh <= 84) & (ua <= 4.0)
        blue_mask = chromatic & (uh >= 85) & (uh <= 134) & (ub <= 6.0)

        # Píxeles acromáticos (pintura blanca, plateada, gris, negra)
        achrom = ~chromatic
        white_mask = achrom & (ul >= 208.0) & (uv >= 205) & (us < 36)
        silver_mask = achrom & (~white_mask) & (ul >= 156.0) & (ul < 208.0)
        gray_mask = achrom & (~white_mask) & (~silver_mask) & (ul >= 78.0) & (ul < 156.0)
        black_mask = achrom & (ul < 78.0)

        # Desambiguación fina SILVER vs GRAY usando dispersión metálica en [142..165]
        if achrom.any() and (std_l >= 14.0):
            metallic_transfer = achrom & (ul >= 144.0) & (ul < 156.0)
            silver_mask = silver_mask | metallic_transfer
            gray_mask = gray_mask & (~metallic_transfer)

        # Ponderación por pureza cromática para las clases cromáticas, y refuerzo si la
        # carrocería posee pintura cromática clara aunque parte tenga reflejos acromáticos
        chrom_weights = np.clip(uc / 26.0, 0.55, 1.50)
        chromatic_ratio = float(chromatic.mean())
        achrom_scale = 0.68 if chromatic_ratio >= 0.30 else 1.0

        raw_scores: Dict[VehicleColor, float] = {
            VehicleColor.RED: float(np.where(red_mask, chrom_weights, 0.0).sum()),
            VehicleColor.ORANGE: float(np.where(orange_mask, chrom_weights, 0.0).sum()),
            VehicleColor.BROWN: float(np.where(brown_mask, chrom_weights, 0.0).sum()),
            VehicleColor.YELLOW: float(np.where(yellow_mask, chrom_weights, 0.0).sum()),
            VehicleColor.GREEN: float(np.where(green_mask, chrom_weights, 0.0).sum()),
            VehicleColor.BLUE: float(np.where(blue_mask, chrom_weights, 0.0).sum()),
            VehicleColor.OTHER: float(np.where(other_mask, chrom_weights, 0.0).sum()),
            VehicleColor.WHITE: float(white_mask.sum()) * achrom_scale,
            VehicleColor.SILVER: float(silver_mask.sum()) * achrom_scale,
            VehicleColor.GRAY: float(gray_mask.sum()) * achrom_scale,
            VehicleColor.BLACK: float(black_mask.sum()) * achrom_scale,
        }

        total_score = sum(raw_scores.values())
        if total_score <= 1e-6:
            limitations.append("NO_DOMINANT_COLOR_SIGNAL")
            quality = ColorRegionQuality(
                bbox_area_px=bbox_area,
                usable_body_pixels=usable_px,
                usable_pixel_ratio=round(usable_ratio_total, 4),
                mean_luminance_l=round(mean_l, 2),
                std_luminance_l=round(std_l, 2),
                mean_saturation_s=round(mean_s, 2),
                mean_chroma_ab=round(mean_c, 2),
                shadow_ratio=round(shadow_ratio, 4),
                glare_ratio=round(glare_ratio, 4),
                background_excluded_ratio=round(bg_excluded_ratio, 4),
                sharpness_laplacian=round(sharpness, 2),
                is_sufficient=False,
                limitations=tuple(limitations),
            )
            return VehicleColorResult(
                predominant_color=VehicleColor.UNKNOWN,
                confidence=0.0,
                status=ColorClassificationStatus.LOW_CONFIDENCE_UNKNOWN,
                quality=quality,
                category_scores={VehicleColor.UNKNOWN.value: 1.0},
                vehicle_class=vehicle_class,
                detection_confidence=detection_confidence,
                processing_time_ms=(time.perf_counter() - t0) * 1000.0,
            )

        norm_scores: Dict[str, float] = {
            c.value: round(raw_scores[c] / total_score, 4) for c in raw_scores
        }
        ranked = sorted(raw_scores.items(), key=lambda kv: kv[1], reverse=True)
        top1_color, top1_raw = ranked[0]
        top2_color, top2_raw = ranked[1]
        top1_share = top1_raw / total_score
        top2_share = top2_raw / total_score
        margin = top1_share - top2_share

        # Confianza heurística conservadora acotada [0.0, 0.98]
        purity_factor = float(np.clip(top1_share, 0.0, 1.0))
        margin_factor = float(np.clip(margin / 0.30, 0.30, 1.0))
        region_factor = float(np.clip(usable_ratio_anat / 0.45, 0.55, 1.0))
        glare_penalty = (
            0.0
            if glare_ratio <= cfg.glare_penalty_threshold
            else 0.45 * ((glare_ratio - cfg.glare_penalty_threshold) / max(1e-6, 1.0 - cfg.glare_penalty_threshold))
        )
        blur_penalty = 0.08 if sharpness < 35.0 else 0.0
        confidence = float(
            np.clip(
                (0.65 * purity_factor + 0.35 * margin_factor)
                * region_factor
                * (1.0 - glare_penalty)
                * (1.0 - blur_penalty),
                0.0,
                0.98,
            )
        )

        # Mediana cromática representativa
        dom_lab = (
            round(float(np.median(ul) * (100.0 / 255.0)), 2),
            round(float(np.median(ua)), 2),
            round(float(np.median(ub)), 2),
        )
        dom_hsv = (
            round(float(np.median(uh)), 1),
            round(float(np.median(us)), 1),
            round(float(np.median(uv)), 1),
        )

        # Criterios conservadores de rechazo -> UNKNOWN
        final_color = top1_color
        status = ColorClassificationStatus.CLASSIFIED
        if margin < cfg.min_margin_over_runner_up:
            final_color = VehicleColor.UNKNOWN
            status = ColorClassificationStatus.AMBIGUOUS_COLOR
            limitations.append("AMBIGUOUS_TOP2_COLORS")
        elif confidence < cfg.min_confidence_threshold:
            final_color = VehicleColor.UNKNOWN
            status = ColorClassificationStatus.LOW_CONFIDENCE_UNKNOWN
            limitations.append("BELOW_MIN_CONFIDENCE_THRESHOLD")

        quality = ColorRegionQuality(
            bbox_area_px=bbox_area,
            usable_body_pixels=usable_px,
            usable_pixel_ratio=round(usable_ratio_total, 4),
            mean_luminance_l=round(mean_l, 2),
            std_luminance_l=round(std_l, 2),
            mean_saturation_s=round(mean_s, 2),
            mean_chroma_ab=round(mean_c, 2),
            shadow_ratio=round(shadow_ratio, 4),
            glare_ratio=round(glare_ratio, 4),
            background_excluded_ratio=round(bg_excluded_ratio, 4),
            sharpness_laplacian=round(sharpness, 2),
            is_sufficient=(final_color != VehicleColor.UNKNOWN),
            limitations=tuple(dict.fromkeys(limitations)),
        )

        return VehicleColorResult(
            predominant_color=final_color,
            confidence=confidence,
            status=status,
            quality=quality,
            secondary_color=top2_color if top2_share > 0.05 else None,
            runner_up_margin=margin,
            category_scores=norm_scores,
            dominant_lab=dom_lab,
            dominant_hsv=dom_hsv,
            vehicle_class=vehicle_class,
            detection_confidence=detection_confidence,
            processing_time_ms=(time.perf_counter() - t0) * 1000.0,
        )
