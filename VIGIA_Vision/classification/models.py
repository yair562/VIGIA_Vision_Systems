"""
VIGIA_Vision.classification.models
==================================
Modelos de datos inmutables y taxonomías de clasificación de color vehicular
para VIGÍA Vision Systems (Fase VISION-05B).

Reglas de diseño:
- Todos los objetos de valor son inmutables (``@dataclass(frozen=True)``).
- Taxonomía estricta de 12 clases: 11 colores físicos evaluables + UNKNOWN fail-safe.
- Distinción explícita de estados de clasificación (éxito, ambigüedad, baja calidad,
  detección no confiable, error técnico).
- Métricas cuantitativas de calidad fotométrica y área útil analizada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Tuple


class VehicleColor(str, Enum):
    """
    Taxonomía canónica de colores vehiculares en VIGÍA Vision Systems.
    Contiene 11 categorías cromáticas/acromáticas físicas y UNKNOWN para
    rechazo o calidad insuficiente.
    """

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

    @classmethod
    def evaluable_colors(cls) -> Tuple[VehicleColor, ...]:
        """Colores físicos evaluables (excluye UNKNOWN)."""
        return (
            cls.WHITE,
            cls.BLACK,
            cls.GRAY,
            cls.SILVER,
            cls.RED,
            cls.BLUE,
            cls.GREEN,
            cls.YELLOW,
            cls.BROWN,
            cls.ORANGE,
            cls.OTHER,
        )


class ColorClassificationStatus(str, Enum):
    """Estado operativo de la clasificación de color."""

    SUCCESS = "SUCCESS"
    """Clasificación cromática exitosa con confianza y margen suficiente."""

    AMBIGUOUS = "AMBIGUOUS"
    """Múltiples colores presentan puntuaciones similares; margen insuficiente."""

    LOW_QUALITY = "LOW_QUALITY"
    """Recorte pequeño, subexpuesto, deslumbrado o con señal útil insuficiente."""

    UNRELIABLE_DETECTION = "UNRELIABLE_DETECTION"
    """La confianza de la detección vehicular original es inferior al umbral mínimo."""

    INVALID_INPUT = "INVALID_INPUT"
    """Entrada BGR o BoundingBox nula, vacía, degenerada o fuera de dimensiones."""

    PROCESSING_ERROR = "PROCESSING_ERROR"
    """Excepción controlada capturada durante la ejecución del pipeline cromático."""


@dataclass(frozen=True)
class ColorQualityMetrics:
    """
    Indicadores cuantitativos de calidad de la región analizada en el vehículo.
    Permite auditar por qué un vehículo fue clasificado o rechazado como UNKNOWN.
    """

    bbox_area: int = 0
    sampled_area: int = 0
    usable_pixel_ratio: float = 0.0
    shadow_ratio: float = 0.0
    glare_ratio: float = 0.0
    mean_luminance: float = 0.0
    mean_saturation: float = 0.0
    mean_lab_chroma: float = 0.0
    sharpness_laplacian: float = 0.0
    quality_flag: str = "OK"

    def __post_init__(self) -> None:
        for name, val in (
            ("bbox_area", self.bbox_area),
            ("sampled_area", self.sampled_area),
        ):
            if isinstance(val, bool) or not isinstance(val, int) or val < 0:
                raise ValueError(f"{name}={val!r} debe ser un entero >= 0.")
        for name, val in (
            ("usable_pixel_ratio", self.usable_pixel_ratio),
            ("shadow_ratio", self.shadow_ratio),
            ("glare_ratio", self.glare_ratio),
        ):
            if not isinstance(val, (int, float)) or not (0.0 <= float(val) <= 1.0):
                raise ValueError(f"{name}={val!r} debe estar en el rango [0.0, 1.0].")
            object.__setattr__(self, name, float(val))


@dataclass(frozen=True)
class VehicleColorResult:
    """
    Resultado estructurado e inmutable de la clasificación de color vehicular.

    Atributos
    ---------
    color : VehicleColor
        Color predominante estimado o UNKNOWN si no es confiable.
    confidence : float
        Nivel de confianza en [0.0, 1.0].
    status : ColorClassificationStatus
        Estado semántico de la decisión.
    is_reliable : bool
        True si status == SUCCESS y confidence >= umbral de decisión.
    category_scores : Dict[str, float]
        Puntuaciones normalizadas para todas las categorías evaluables.
    quality_metrics : ColorQualityMetrics
        Indicadores fotométricos y geométricos de la región corporal muestreada.
    reason : str
        Justificación interpretable del dictamen (o motivo de rechazo a UNKNOWN).
    dominant_rgb : Optional[Tuple[int, int, int]]
        Color RGB representativo (mediana de píxeles válidos) para visualización.
    hsv_stats : Dict[str, float]
        Estadísticas descriptivas (mean_h, mean_s, mean_v).
    """

    color: VehicleColor
    confidence: float
    status: ColorClassificationStatus
    is_reliable: bool
    category_scores: Dict[str, float]
    quality_metrics: ColorQualityMetrics
    reason: str
    dominant_rgb: Optional[Tuple[int, int, int]] = None
    hsv_stats: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.color, VehicleColor):
            raise ValueError(f"color={self.color!r} debe ser una instancia de VehicleColor.")
        if not isinstance(self.status, ColorClassificationStatus):
            raise ValueError(f"status={self.status!r} debe ser ColorClassificationStatus.")
        if not isinstance(self.confidence, (int, float)) or not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError(f"confidence={self.confidence!r} debe estar en [0.0, 1.0].")
        if not isinstance(self.quality_metrics, ColorQualityMetrics):
            raise ValueError("quality_metrics debe ser una instancia de ColorQualityMetrics.")
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "is_reliable", bool(self.is_reliable))

    @property
    def predominant_color(self) -> VehicleColor:
        """Alias compatible con VehicleColorResult de detección."""
        return self.color

    @property
    def quality(self) -> ColorQualityMetrics:
        """Alias compatible con calidad fotométrica."""
        return self.quality_metrics

    @classmethod
    def unknown(
        cls,
        reason: str,
        status: ColorClassificationStatus = ColorClassificationStatus.LOW_QUALITY,
        quality_metrics: Optional[ColorQualityMetrics] = None,
        confidence: float = 0.0,
    ) -> VehicleColorResult:
        """Constructor helper para emitir UNKNOWN de forma segura y consistente."""
        metrics = quality_metrics or ColorQualityMetrics(quality_flag=status.value)
        empty_scores = {c.value: (1.0 if c == VehicleColor.UNKNOWN else 0.0) for c in VehicleColor}
        return cls(
            color=VehicleColor.UNKNOWN,
            confidence=max(0.0, min(1.0, float(confidence))),
            status=status,
            is_reliable=False,
            category_scores=empty_scores,
            quality_metrics=metrics,
            reason=reason,
            dominant_rgb=None,
            hsv_stats={},
        )
