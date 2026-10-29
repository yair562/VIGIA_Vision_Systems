"""
VIGIA_Vision.runtime
====================
Almacenamiento seguro de evidencias fotográficas y coordinador síncrono del
motor propio de visión artificial de VIGÍA.
"""

from VIGIA_Vision.runtime.coordinator import (
    IObservationConsumer,
    IVehicleDetector,
    NullVehicleDetector,
    VisionEngineCoordinator,
    map_raw_label_to_domain_vehicle_type,
)
from VIGIA_Vision.runtime.evidence_storage import (
    EvidenceSaveResult,
    IEvidenceStorageService,
    LocalDiskEvidenceStorage,
    StorageWriteError,
    derive_annotated_evidence_path,
    derive_original_evidence_path,
    render_annotated_frame,
)

__all__ = [
    "EvidenceSaveResult",
    "IEvidenceStorageService",
    "IObservationConsumer",
    "IVehicleDetector",
    "LocalDiskEvidenceStorage",
    "NullVehicleDetector",
    "StorageWriteError",
    "VisionEngineCoordinator",
    "derive_annotated_evidence_path",
    "derive_original_evidence_path",
    "map_raw_label_to_domain_vehicle_type",
    "render_annotated_frame",
]
