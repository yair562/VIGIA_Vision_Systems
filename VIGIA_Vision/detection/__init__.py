"""
VIGIA_Vision.detection
======================
Modelos de observación, validación de fotogramas, filtrado geométrico por ROI
y detector vehicular YOLO (SPRINT-02) del subsistema de visión de VIGÍA.
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
from VIGIA_Vision.detection.yolo_detector import (
    COCO_VEHICLE_CLASSES,
    InferenceError,
    ModelLoadError,
    YoloDetectorConfig,
    YoloVehicleDetector,
)

__all__ = [
    "BoundingBox",
    "CaptureReadResult",
    "COCO_VEHICLE_CLASSES",
    "FrameValidationError",
    "InferenceError",
    "ModelLoadError",
    "ObservationMetrics",
    "PixelROI",
    "RawVehicleDetection",
    "VisionObservationEnvelope",
    "YoloDetectorConfig",
    "YoloVehicleDetector",
    "filter_detections_by_roi",
    "project_normalized_roi",
    "validate_bgr_frame",
]
