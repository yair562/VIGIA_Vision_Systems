"""
VIGIA_Vision.async_persistence.worker_pool
==========================================
Pool de workers dedicados por ranura de cámara con procesamiento secuencial
estricto, reintentos con backoff exponencial acotado, compensación transaccional
y desvío determinista a Dead Letter Queue (DLQ) con desbloqueo de cámara.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from VIGIA_Core.repository.detection_repository import (
    DetectionInsertDTO,
    IDetectionRepository,
    map_tipo_vehiculo_ddl_v1,
)
from VIGIA_Vision.async_persistence.evidence_writer import (
    AtomicEvidenceWriter,
    EvidenceWriteError,
)
from VIGIA_Vision.async_persistence.metrics import PilotMetricsCollector
from VIGIA_Vision.async_persistence.models import (
    DLQRecord,
    DiscontinuityRecord,
    PersistenceTaskDTO,
    TaskStatus,
)
from VIGIA_Vision.async_persistence.queue_manager import (
    CameraPartitionSlot,
    PartitionedQueueManager,
)
from VIGIA_Vision.async_persistence.spool import BinarySpoolStorage

logger = logging.getLogger(__name__)


class PartitionedWorkerPool:
    """
    Gestiona un worker de un solo hilo por cámara, garantizando orden causal
    y resiliencia transaccional.
    """

    def __init__(
        self,
        queue_manager: PartitionedQueueManager,
        evidence_writer: AtomicEvidenceWriter,
        db_repo: IDetectionRepository,
        dlq_base_dir: Path,
        spool_storage: Optional[BinarySpoolStorage] = None,
        metrics_collector: Optional[PilotMetricsCollector] = None,
        max_retries: int = 3,
        backoff_intervals: Sequence[float] = (0.050, 0.150, 0.450),
    ) -> None:
        self._qm = queue_manager
        self._ew = evidence_writer
        self._db = db_repo
        self._dlq_dir = Path(dlq_base_dir).resolve()
        self._dlq_dir.mkdir(parents=True, exist_ok=True)
        self._spool = spool_storage
        self._metrics = metrics_collector or PilotMetricsCollector()
        self._max_retries = max_retries
        self._backoffs = backoff_intervals

        self._running = False
        self._threads: Dict[str, threading.Thread] = {}
        self._thread_locks: Dict[str, threading.Lock] = {}
        self._last_committed_seq: Dict[str, int] = {}

        # Ganchos de inyección de fallos para arnés de pruebas (Escenarios 4, 5, 6, 9)
        self.injected_fail_annotated: bool = False
        self.injected_fail_sql_countdown: int = 0
        self.injected_crash_post_commit: bool = False
        self.injected_fail_dlq_io: bool = False

    @property
    def dlq_dir(self) -> Path:
        return self._dlq_dir

    def start(self, camera_codes: Sequence[str]) -> None:
        """Inicia los hilos de workers dedicados para las cámaras provistas."""
        self._running = True
        for cam in camera_codes:
            if cam not in self._threads:
                slot = self._qm.get_or_create_slot(cam)
                t = threading.Thread(
                    target=self._worker_loop,
                    args=(slot,),
                    name=f"WorkerPool-{cam}",
                    daemon=True,
                )
                self._threads[cam] = t
                self._last_committed_seq[cam] = 0
                t.start()
        logger.info("PartitionedWorkerPool iniciado para cámaras: %s", list(camera_codes))

    def stop(self, drain_timeout: float = 5.0) -> bool:
        """Detiene los workers tras drenar las tareas en cola (Graceful Shutdown)."""
        logger.info("Deteniendo PartitionedWorkerPool con timeout de drenaje de %.1fs...", drain_timeout)
        start_mono = time.monotonic()
        
        # Esperar a que las colas se vacíen hasta agotar timeout
        while self._qm.get_total_depth() > 0:
            if (time.monotonic() - start_mono) > drain_timeout:
                logger.warning("Timeout de drenaje alcanzado con tareas pendientes.")
                break
            time.sleep(0.05)

        is_clean_drain = (self._qm.get_total_depth() == 0)

        self._running = False
        for cam, t in self._threads.items():
            t.join(timeout=1.0)
        self._threads.clear()
        logger.info("PartitionedWorkerPool detenido con éxito.")
        return is_clean_drain

    def _worker_loop(self, slot: CameraPartitionSlot) -> None:
        """Bucle secuencial estricto ejecutado por el worker de la ranura."""
        cam = slot.codigo_camara

        while self._running:
            t_wait_start = time.monotonic()
            try:
                task = slot.queue.get(block=True, timeout=0.100)
            except queue.Empty:
                continue

            wait_ms = (time.monotonic() - t_wait_start) * 1000.0
            self._metrics.record_worker_wait(wait_ms)

            # Procesar tarea con control transaccional
            self._process_task_with_retries(slot, task)

    def _process_task_with_retries(
        self,
        slot: CameraPartitionSlot,
        task: PersistenceTaskDTO,
    ) -> None:
        """Ejecuta la persistencia física y SQL con política acotada de reintentos."""
        cam = slot.codigo_camara
        current_task = task
        created_files: Tuple[Path, Optional[Path]] = ()

        # Comprobar si existe una discontinuidad respecto a la última secuencia comprometida
        last_seq = self._last_committed_seq.get(cam, 0)
        if last_seq > 0 and current_task.camera_sequence > (last_seq + 1):
            logger.warning(
                "Discontinuidad detectada en cam=%s: previa=%d, actual=%d",
                cam,
                last_seq,
                current_task.camera_sequence,
            )
            self._metrics.record_discontinuity()

        attempt = 0
        while attempt <= self._max_retries:
            attempt += 1
            t_persist_start = time.monotonic()

            try:
                # 1. Escritura de evidencias físicas atómicas
                fail_annot = self.injected_fail_annotated
                created_files = self._ew.write_evidence(
                    current_task, force_fail_annotated=fail_annot
                )
                persist_ms = (time.monotonic() - t_persist_start) * 1000.0
                self._metrics.record_persistence_time(persist_ms)

                # Ruta relativa del fotograma original para PostgreSQL
                orig_rel = created_files[0].relative_to(self._ew.base_dir).as_posix()

                # 2. Inserción transaccional en PostgreSQL
                t_sql_start = time.monotonic()

                # Comprobación de fallo SQL inyectado (Escenario 5)
                if self.injected_fail_sql_countdown > 0:
                    self.injected_fail_sql_countdown -= 1
                    raise Exception("Inyección de fallo SQL simulada (timeout de base de datos).")

                mapped_tipo = map_tipo_vehiculo_ddl_v1(current_task.tipo_vehiculo_pred)
                dto = DetectionInsertDTO(
                    id_area_vision=current_task.id_area_vision,
                    fecha_hora=current_task.timestamp_captura,
                    placa_detectada=current_task.placa_detectada,
                    confianza_placa=current_task.confianza_placa,
                    confianza_vehiculo=current_task.confianza_vehiculo,
                    tipo_vehiculo_pred=mapped_tipo,
                    ruta_evidencia_foto=orig_rel,
                )

                id_deteccion = self._db.persist_detection(dto)
                sql_ms = (time.monotonic() - t_sql_start) * 1000.0
                self._metrics.record_sql_commit(sql_ms)

                # Simulación de crash post-commit antes de purgar spool (Escenario 6)
                if self.injected_crash_post_commit:
                    self.injected_crash_post_commit = False
                    logger.warning("Simulación de crash post-commit activada: spool conservado.")
                    slot.queue.task_done()
                    return

                # 3. Purgar archivo .spool si existe
                if self._spool:
                    spool_name = f"{current_task.camera_sequence:012d}_{current_task.task_id.hex}.spool"
                    spool_path = self._spool.base_dir / cam / spool_name
                    self._spool.purge_spool(spool_path)

                # Actualizar última secuencia exitosa
                self._last_committed_seq[cam] = current_task.camera_sequence
                slot.queue.task_done()
                return

            except Exception as exc:
                self._metrics.record_retry()
                # Compensación inmediata: purgar archivos físicos creados antes de reintentar
                if created_files:
                    files_to_clean = [f for f in created_files if f is not None]
                    self._ew.rollback_evidence(files_to_clean)
                    created_files = ()

                if attempt <= self._max_retries:
                    backoff_sec = (
                        self._backoffs[attempt - 1]
                        if (attempt - 1) < len(self._backoffs)
                        else 0.450
                    )
                    logger.warning(
                        "Reintento %d/%d para tarea %s en cam=%s tras error: %s. Esperando %.3fs...",
                        attempt,
                        self._max_retries,
                        current_task.task_id,
                        cam,
                        exc,
                        backoff_sec,
                    )
                    time.sleep(backoff_sec)
                    current_task = current_task.with_retry_incremented()
                else:
                    # Agotamiento de reintentos: desvío a Dead Letter Queue
                    logger.error(
                        "Reintentos agotados para tarea %s en cam=%s. Desviando a DLQ...",
                        current_task.task_id,
                        cam,
                    )
                    self._quarantine_to_dlq(slot, current_task, exc)
                    slot.queue.task_done()
                    return

    def _quarantine_to_dlq(
        self,
        slot: CameraPartitionSlot,
        task: PersistenceTaskDTO,
        exc: Exception,
    ) -> None:
        """Desvía la tarea a la DLQ, registra discontinuidad y desbloquea la ranura."""
        cam = slot.codigo_camara
        tb_str = traceback.format_exc()
        ts_now = datetime.now(timezone.utc)

        disc = DiscontinuityRecord(
            codigo_camara=cam,
            missing_sequence=task.camera_sequence,
            resumed_sequence=task.camera_sequence + 1,
            reason=f"RETRY_EXHAUSTED: {exc}",
            timestamp=ts_now,
        )
        self._metrics.record_discontinuity()
        self._metrics.record_dlq()

        dlq_rec = DLQRecord(
            task_id=task.task_id,
            capture_id=task.capture_id,
            camera_sequence=task.camera_sequence,
            codigo_camara=cam,
            timestamp_failure=ts_now,
            retry_count=task.retry_count,
            last_error=str(exc),
            error_trace=tb_str,
            discontinuity=disc,
        )

        date_str = ts_now.strftime("%Y%m%d")
        cam_dlq_dir = self._dlq_dir / date_str / cam
        cam_dlq_dir.mkdir(parents=True, exist_ok=True)
        dlq_file = cam_dlq_dir / f"{task.camera_sequence:012d}_{task.task_id.hex}.dlq"

        # Simulación de fallo en cascada de disco durante DLQ (Escenario 9)
        if self.injected_fail_dlq_io:
            self.injected_fail_dlq_io = False
            logger.critical("Fallo de E/S inyectado al escribir archivo DLQ (disco lleno).")
            # El worker no colapsa el proceso, registra error y avanza para no paralizar la cámara
            return

        try:
            with open(dlq_file, "w", encoding="utf-8") as fh:
                fh.write(dlq_rec.to_json())
            logger.info("Tarea en cuarentena consolidada en DLQ: %s", dlq_file)
        except OSError as dlq_exc:
            logger.critical("Fallo catastrófico al escribir DLQ: %s", dlq_exc)

        # Actualizar secuencia para permitir que el siguiente fotograma continúe (No-Bloqueo de Cámara)
        self._last_committed_seq[cam] = task.camera_sequence
