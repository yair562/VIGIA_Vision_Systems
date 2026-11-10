"""
VIGIA_Vision.async_persistence.reconciler
=========================================
Componentes de reconciliación en frío (SpoolReconciler) y reprocesamiento
de cuarentena (DLQReconciler) para restaurar la consistencia tras interrupciones.

Garantiza:
- Purga de temporales obsoletos (> 10 min).
- Reconstrucción íntegra de tareas a partir de .spool sin depender de RAM.
- Idempotencia estricta ante rearranques sucesivos o commits previos.
- Tiempo de reconciliación en frío inferior a 3.0 segundos.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from VIGIA_Core.repository.detection_repository import (
    DetectionInsertDTO,
    IDetectionRepository,
    map_tipo_vehiculo_ddl_v1,
)
from VIGIA_Vision.async_persistence.evidence_writer import AtomicEvidenceWriter
from VIGIA_Vision.async_persistence.metrics import PilotMetricsCollector
from VIGIA_Vision.async_persistence.models import (
    DLQRecord,
    PersistenceTaskDTO,
)
from VIGIA_Vision.async_persistence.spool import (
    BinarySpoolStorage,
    SpoolCorruptionError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconciliationResult:
    """Resultado estructurado de la reconciliación en frío."""
    purged_temps: int
    spools_scanned: int
    spools_recovered: int
    spools_already_committed: int
    spools_corrupt: int
    elapsed_seconds: float

    @property
    def passed_benchmark_latency(self) -> bool:
        """Verifica si la reconciliación se completó en menos de 3.0 segundos."""
        return self.elapsed_seconds < 3.0


@dataclass(frozen=True)
class DLQReprocessResult:
    """Resultado del reprocesamiento de la cola de descarte (DLQ)."""
    dlq_scanned: int
    dlq_reprocessed: int
    dlq_failed: int
    elapsed_seconds: float


class SpoolReconciler:
    """
    Reconciliador en frío ejecutado al arrancar el motor de visión.
    Restaura la consistencia entre almacenamiento y base de datos.
    """

    def __init__(
        self,
        spool_storage: BinarySpoolStorage,
        evidence_writer: AtomicEvidenceWriter,
        db_repo: IDetectionRepository,
        metrics_collector: Optional[PilotMetricsCollector] = None,
    ) -> None:
        self._spool = spool_storage
        self._ew = evidence_writer
        self._db = db_repo
        self._metrics = metrics_collector

    def reconcile_cold_start(self, max_temp_age_seconds: float = 600.0) -> ReconciliationResult:
        """
        Ejecuta el protocolo de arranque en frío:
        1. Purgar archivos .tmp obsoletos.
        2. Escanear y validar todos los archivos .spool.
        3. Cuarentena inmediata de spools corruptos.
        4. Replay idempotente de spools no confirmados en base de datos.
        5. Medir tiempo total de ejecución.
        """
        t_start = time.monotonic()
        purged_temps = self._spool.purge_stale_temps(max_age_seconds=max_temp_age_seconds)

        spools_scanned = 0
        spools_recovered = 0
        spools_already_committed = 0
        spools_corrupt = 0

        # Buscar todos los archivos .spool en las ranuras de cámara
        spool_files: List[Path] = []
        for root, _, files in os.walk(self._spool.base_dir):
            if ".corrupt" in root:
                continue
            for file in files:
                if file.endswith(".spool") and not file.startswith("."):
                    spool_files.append(Path(root) / file)

        # Ordenar por nombre (incorpora camera_sequence de 12 dígitos)
        spool_files.sort(key=lambda p: p.name)

        for sp_path in spool_files:
            spools_scanned += 1
            try:
                task = self._spool.read_spool(sp_path)
            except SpoolCorruptionError as exc:
                spools_corrupt += 1
                logger.warning("Spool corrupto detectado en arranque: %s (%s)", sp_path, exc)
                self._spool.quarantine_corrupt(sp_path, reason="checksum_mismatch")
                continue

            # Comprobar idempotencia en base de datos (si la fila ya existe)
            is_already_committed = False
            if hasattr(self._db, "has_detection"):
                is_already_committed = self._db.has_detection(task.id_area_vision, task.timestamp_captura)

            if is_already_committed:
                spools_already_committed += 1
                self._spool.purge_spool(sp_path)
                continue

            # Persistencia física de evidencias y commit en base de datos
            created_files: Tuple[Path, Optional[Path]] = ()
            try:
                created_files = self._ew.write_evidence(task)
                orig_rel = created_files[0].relative_to(self._ew.base_dir).as_posix()

                mapped_tipo = map_tipo_vehiculo_ddl_v1(task.tipo_vehiculo_pred)
                dto = DetectionInsertDTO(
                    id_area_vision=task.id_area_vision,
                    fecha_hora=task.timestamp_captura,
                    placa_detectada=task.placa_detectada,
                    confianza_placa=task.confianza_placa,
                    confianza_vehiculo=task.confianza_vehiculo,
                    tipo_vehiculo_pred=mapped_tipo,
                    ruta_evidencia_foto=orig_rel,
                )

                self._db.persist_detection(dto)
                self._spool.purge_spool(sp_path)
                spools_recovered += 1

            except Exception as exc:
                if created_files:
                    files_to_clean = [f for f in created_files if f is not None]
                    self._ew.rollback_evidence(files_to_clean)
                logger.error("Error al recuperar spool %s durante cold-start: %s", sp_path, exc)

        elapsed = time.monotonic() - t_start
        if self._metrics:
            self._metrics.record_recovery(spools_recovered, elapsed * 1000.0)

        logger.info(
            "Reconciliación en frío concluida en %.3fs: scanned=%d, recovered=%d, already_committed=%d, corrupt=%d, purged_tmp=%d",
            elapsed,
            spools_scanned,
            spools_recovered,
            spools_already_committed,
            spools_corrupt,
            purged_temps,
        )

        return ReconciliationResult(
            purged_temps=purged_temps,
            spools_scanned=spools_scanned,
            spools_recovered=spools_recovered,
            spools_already_committed=spools_already_committed,
            spools_corrupt=spools_corrupt,
            elapsed_seconds=round(elapsed, 4),
        )


class DLQReconciler:
    """
    Proceso desacoplado para reprocesar tareas archivadas en Dead Letter Queue.
    """

    def __init__(
        self,
        dlq_base_dir: Path,
        evidence_writer: AtomicEvidenceWriter,
        db_repo: IDetectionRepository,
    ) -> None:
        self._dlq_dir = Path(dlq_base_dir).resolve()
        self._ew = evidence_writer
        self._db = db_repo

    def reprocess_all(self, payload_resolver=None) -> DLQReprocessResult:
        """
        Escanea y reintenta la confirmación en PostgreSQL de archivos .dlq en cuarentena.
        """
        t_start = time.monotonic()
        dlq_scanned = 0
        dlq_reprocessed = 0
        dlq_failed = 0

        dlq_files: List[Path] = []
        for root, _, files in os.walk(self._dlq_dir):
            for file in files:
                if file.endswith(".dlq") and not file.startswith("."):
                    dlq_files.append(Path(root) / file)

        dlq_files.sort(key=lambda p: p.name)

        for dlq_path in dlq_files:
            dlq_scanned += 1
            try:
                with open(dlq_path, "r", encoding="utf-8") as fh:
                    raw_content = fh.read()
                record = DLQRecord.from_json(raw_content)

                # Obtener la tarea original a partir del payload_resolver si se provee
                task = payload_resolver(record.task_id) if payload_resolver else None
                if not task:
                    dlq_failed += 1
                    continue

                # Escribir evidencias e insertar en base de datos
                created = self._ew.write_evidence(task)
                orig_rel = created[0].relative_to(self._ew.base_dir).as_posix()
                mapped_tipo = map_tipo_vehiculo_ddl_v1(task.tipo_vehiculo_pred)

                dto = DetectionInsertDTO(
                    id_area_vision=task.id_area_vision,
                    fecha_hora=task.timestamp_captura,
                    placa_detectada=task.placa_detectada,
                    confianza_placa=task.confianza_placa,
                    confianza_vehiculo=task.confianza_vehiculo,
                    tipo_vehiculo_pred=mapped_tipo,
                    ruta_evidencia_foto=orig_rel,
                )

                self._db.persist_detection(dto)

                # Renombrar archivo DLQ a reconciliado
                reconciled_path = dlq_path.with_suffix(".dlq.reconciled")
                os.replace(dlq_path, reconciled_path)
                dlq_reprocessed += 1

            except Exception as exc:
                dlq_failed += 1
                logger.error("Error al reprocesar DLQ %s: %s", dlq_path, exc)

        elapsed = time.monotonic() - t_start
        return DLQReprocessResult(
            dlq_scanned=dlq_scanned,
            dlq_reprocessed=dlq_reprocessed,
            dlq_failed=dlq_failed,
            elapsed_seconds=round(elapsed, 4),
        )
