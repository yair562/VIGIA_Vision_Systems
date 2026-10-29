"""
VIGIA_Vision
============
Subsistema propio de Percepción e Interpretación Visual de VIGÍA Vision Systems.

Importación libre de efectos secundarios: importar este paquete no abre
descriptores de cámara, no conecta a PostgreSQL y no carga modelos de IA.
"""

from VIGIA_Vision.capture import (
    BoundCameraSlot,
    CameraSourceRegistry,
    IFrameCaptureSource,
    MobilePushFrameBuffer,
    OpenCVCaptureSource,
    UnregisteredCameraError,
)
from VIGIA_Vision.config import (
    AreaConfigDTO,
    CameraConfigDTO,
    ITopologyConfigRepository,
    OperationalTopologyDTO,
    PsycopgTopologyConfigRepository,
    TopologyErrorCode,
    TopologyValidationError,
    TopologyValidationResult,
    TopologyValidator,
    VisionEngineSettings,
)
from VIGIA_Vision.detection import (
    BoundingBox,
    CaptureReadResult,
    FrameValidationError,
    InferenceError,
    ModelLoadError,
    ObservationMetrics,
    PixelROI,
    RawVehicleDetection,
    VisionObservationEnvelope,
    YoloDetectorConfig,
    YoloVehicleDetector,
    filter_detections_by_roi,
    project_normalized_roi,
    validate_bgr_frame,
)
from VIGIA_Vision.runtime import (
    EvidenceSaveResult,
    IEvidenceStorageService,
    IObservationConsumer,
    IVehicleDetector,
    LocalDiskEvidenceStorage,
    NullVehicleDetector,
    StorageWriteError,
    VisionEngineCoordinator,
    derive_annotated_evidence_path,
    derive_original_evidence_path,
    map_raw_label_to_domain_vehicle_type,
    render_annotated_frame,
)

__all__ = [
    "AreaConfigDTO",
    "BoundCameraSlot",
    "BoundingBox",
    "CameraConfigDTO",
    "CameraSourceRegistry",
    "CaptureReadResult",
    "EvidenceSaveResult",
    "FrameValidationError",
    "IEvidenceStorageService",
    "IFrameCaptureSource",
    "IObservationConsumer",
    "ITopologyConfigRepository",
    "IVehicleDetector",
    "InferenceError",
    "LocalDiskEvidenceStorage",
    "MobilePushFrameBuffer",
    "ModelLoadError",
    "NullVehicleDetector",
    "ObservationMetrics",
    "OpenCVCaptureSource",
    "OperationalTopologyDTO",
    "PixelROI",
    "PsycopgTopologyConfigRepository",
    "RawVehicleDetection",
    "StorageWriteError",
    "TopologyErrorCode",
    "TopologyValidationError",
    "TopologyValidationResult",
    "TopologyValidator",
    "UnregisteredCameraError",
    "VisionEngineCoordinator",
    "VisionEngineSettings",
    "VisionObservationEnvelope",
    "YoloDetectorConfig",
    "YoloVehicleDetector",
    "derive_annotated_evidence_path",
    "derive_original_evidence_path",
    "filter_detections_by_roi",
    "map_raw_label_to_domain_vehicle_type",
    "project_normalized_roi",
    "render_annotated_frame",
    "validate_bgr_frame",
]
