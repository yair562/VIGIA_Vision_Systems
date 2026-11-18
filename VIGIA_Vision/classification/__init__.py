"""
VIGIA_Vision.classification
===========================
Módulo modular e independiente de clasificación de color vehicular (Fase VISION-05B).
"""

from __future__ import annotations

from VIGIA_Vision.classification.config import VehicleColorConfig
from VIGIA_Vision.classification.models import (
    ColorClassificationStatus,
    ColorQualityMetrics,
    VehicleColor,
    VehicleColorResult,
)
from VIGIA_Vision.classification.normalizer import NormalizedBodyCrop, VehicleColorNormalizer
from VIGIA_Vision.classification.color_classifier import VehicleColorClassifier

__all__ = [
    "VehicleColor",
    "ColorClassificationStatus",
    "ColorQualityMetrics",
    "VehicleColorResult",
    "VehicleColorConfig",
    "NormalizedBodyCrop",
    "VehicleColorNormalizer",
    "VehicleColorClassifier",
]
