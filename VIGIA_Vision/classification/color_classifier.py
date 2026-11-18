"""
VIGIA_Vision.classification.color_classifier
============================================
Punto de entrada unificado y compatible del clasificador de color vehicular.
(Fase VISION-07B.1 - Unificación Arquitectónica).

Redirige canónicamente a ``VIGIA_Vision.detection.color_classifier.VehicleColorClassifier``
para garantizar paridad estricta entre producción, benchmarks y herramientas de evaluación.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np

from VIGIA_Vision.detection.color_classifier import (
    VehicleColorClassifier as CanonicalVehicleColorClassifier,
    VehicleColorConfig as CanonicalVehicleColorConfig,
    VehicleColorResult as CanonicalVehicleColorResult,
    VehicleColor,
    ColorClassificationStatus,
    ColorRegionQuality,
)
from VIGIA_Vision.classification.config import VehicleColorConfig

logger = logging.getLogger(__name__)


class VehicleColorClassifier:
    """
    Clasificador cromático unificado para vehículos detectados.
    Delega directamente en el clasificador oficial de producción
    (``VIGIA_Vision.detection.color_classifier.VehicleColorClassifier``).
    """

    def __init__(self, config: Optional[Any] = None) -> None:
        if isinstance(config, CanonicalVehicleColorConfig):
            self._canonical_cfg = config
        else:
            self._canonical_cfg = CanonicalVehicleColorConfig()
        self._delegate = CanonicalVehicleColorClassifier(config=self._canonical_cfg)
        self.config = config or VehicleColorConfig()

    def classify(
        self,
        frame: np.ndarray,
        bbox: Any,
        detected_class: Optional[str] = None,
        detection_confidence: Optional[float] = None,
        vehicle_class: Optional[str] = None,
        **kwargs: Any,
    ) -> CanonicalVehicleColorResult:
        """
        Clasifica el color vehicular utilizando el motor oficial canónico.
        """
        cls_name = vehicle_class or detected_class
        return self._delegate.classify(
            frame=frame,
            bbox=bbox,
            vehicle_class=cls_name,
            detection_confidence=detection_confidence,
            **kwargs,
        )
