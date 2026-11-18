"""
VIGIA_Vision.classification.config
==================================
Configuración centralizada y parámetros ajustables para la clasificación
de color vehicular (Fase VISION-05B).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VehicleColorConfig:
    """
    Parámetros configurables del módulo de clasificación cromática.

    Invariantes y valores predeterminados conservadores para evitar clasificaciones
    forzadas o alucinaciones fotométricas.
    """

    # 1. Restricciones de geometría mínima de la caja delimitadora
    min_bbox_width: int = 45
    min_bbox_height: int = 35
    min_bbox_area: int = 2000

    # 2. Umbral mínimo de confianza de la detección vehicular original
    min_detection_confidence: float = 0.50

    # 3. Ratios de muestreo anatómico de carrocería (exclusión de parabrisas y neumáticos)
    # y_min = 30% (descarta techo, parabrisas delantero/trasero y cielo)
    # y_max = 78% (descarta ruedas, neumáticos, asfalto y sombras inferiores)
    # x_margin = 12% (descarta fondo adyacente a los costados)
    anatomical_crop_y_min_ratio: float = 0.30
    anatomical_crop_y_max_ratio: float = 0.78
    anatomical_crop_x_margin_ratio: float = 0.12

    # 4. Umbrales de descarte de artefactos fotométricos (OpenCV 0..255)
    shadow_v_min: int = 28
    shadow_l_min: int = 20
    glare_v_max: int = 248
    glare_s_max: int = 25

    # 5. Discriminación acromática vs cromática (HSV Saturation + CIELAB Chroma)
    achromatic_s_max: float = 40.0
    achromatic_chroma_max: float = 16.0
    high_chroma_boost_thresh: float = 26.0

    # 6. Umbrales de calidad y rechazo fail-safe
    min_usable_pixel_ratio: float = 0.15
    min_mean_luminance: float = 20.0
    severe_glare_ratio: float = 0.65
    min_confidence_for_decision: float = 0.35
    min_margin_over_second: float = 0.05

    def __post_init__(self) -> None:
        if self.min_bbox_width <= 0 or self.min_bbox_height <= 0 or self.min_bbox_area <= 0:
            raise ValueError("Las dimensiones mínimas del BBox deben ser mayores a 0.")
        if not (0.0 <= self.min_detection_confidence <= 1.0):
            raise ValueError("min_detection_confidence debe estar en [0.0, 1.0].")
        if not (0.0 <= self.anatomical_crop_y_min_ratio < self.anatomical_crop_y_max_ratio <= 1.0):
            raise ValueError("Ratios anatómicos verticales inválidos.")
        if not (0.0 <= self.anatomical_crop_x_margin_ratio < 0.40):
            raise ValueError("anatomical_crop_x_margin_ratio debe estar en [0.0, 0.40).")
        if not (0.0 <= self.min_usable_pixel_ratio <= 1.0):
            raise ValueError("min_usable_pixel_ratio debe estar en [0.0, 1.0].")
        if not (0.0 <= self.min_confidence_for_decision <= 1.0):
            raise ValueError("min_confidence_for_decision debe estar en [0.0, 1.0].")
