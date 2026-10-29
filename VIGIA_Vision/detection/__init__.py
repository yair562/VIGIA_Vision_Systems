"""
VIGIA_Vision.detection
======================
Modelos de observación, validación de fotogramas y filtrado geométrico por ROI
del subsistema de visión de VIGÍA.
"""

from VIGIA_Vision.detection.models import (
    BoundingBox,
    CaptureReadResult,
    ObservationMetrics,
    RawVehicleDetection,
    VisionObservationEnvelope,
)
from VIGIA_Vision.detection.roi_and_preprocess import (
    FrameValidationError,
    PixelROI,
    filter_detections_by_roi,
    project_normalized_roi,
    validate_bgr_frame,
)

__all__ = [
    "BoundingBox",
    "CaptureReadResult",
    "FrameValidationError",
    "ObservationMetrics",
    "PixelROI",
    "RawVehicleDetection",
    "VisionObservationEnvelope",
    "filter_detections_by_roi",
    "project_normalized_roi",
    "validate_bgr_frame",
]
