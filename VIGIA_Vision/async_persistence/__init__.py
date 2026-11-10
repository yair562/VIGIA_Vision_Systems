"""
VIGIA_Vision.async_persistence
==============================
Módulo del piloto aislado de persistencia asíncrona para VIGÍA Vision Systems.
"""

from VIGIA_Vision.async_persistence.evidence_writer import (
    AtomicEvidenceWriter,
    EvidenceWriteError,
    safe_replace_ntfs,
)
from VIGIA_Vision.async_persistence.metrics import PilotMetricsCollector
from VIGIA_Vision.async_persistence.models import (
    DLQRecord,
    DiscontinuityRecord,
    PersistenceTaskDTO,
    TaskStatus,
    compute_content_hash,
)
from VIGIA_Vision.async_persistence.queue_manager import (
    CameraPartitionSlot,
    PartitionedQueueManager,
)
from VIGIA_Vision.async_persistence.reconciler import (
    DLQReconciler,
    DLQReprocessResult,
    ReconciliationResult,
    SpoolReconciler,
)
from VIGIA_Vision.async_persistence.spool import (
    BinarySpoolStorage,
    SpoolCorruptionError,
    SpoolIOError,
)
from VIGIA_Vision.async_persistence.worker_pool import PartitionedWorkerPool

__all__ = [
    "PersistenceTaskDTO",
    "TaskStatus",
    "DiscontinuityRecord",
    "DLQRecord",
    "compute_content_hash",
    "BinarySpoolStorage",
    "SpoolCorruptionError",
    "SpoolIOError",
    "AtomicEvidenceWriter",
    "EvidenceWriteError",
    "safe_replace_ntfs",
    "PartitionedQueueManager",
    "CameraPartitionSlot",
    "PartitionedWorkerPool",
    "SpoolReconciler",
    "DLQReconciler",
    "ReconciliationResult",
    "DLQReprocessResult",
    "PilotMetricsCollector",
]
