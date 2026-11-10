"""
tests.unit.test_async_persistence_pilot
=======================================
Suite exhaustiva de pruebas unitarias y de integración en aislamiento
para el piloto de persistencia asíncrona de VIGÍA Vision Systems (IMP-01).

Valida:
- Contratos inmutables, DTOs y separación de 4 identidades.
- Serialización binaria VGSP y verificación de integridad SHA-256.
- Escritura atómica de evidencias y compensación (rollback).
- Colas particionadas por ranura y política de backpressure HTTP 429.
- Los 9 modos de fallo críticos formalizados en OPT-05 (Secc. 20.3).
- Criterios de aceptación (recuperación < 3s, causalidad, DLQ, memoria).
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import cv2
import numpy as np

from VIGIA_Core.repository.detection_repository import (
    DatabaseConnectionError,
    DatabasePersistenceError,
    DetectionInsertDTO,
    IDetectionRepository,
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
    compute_content_hash,
)
from VIGIA_Vision.async_persistence.queue_manager import (
    CameraPartitionSlot,
    PartitionedQueueManager,
)
from VIGIA_Vision.async_persistence.reconciler import (
    DLQReconciler,
    SpoolReconciler,
)
from VIGIA_Vision.async_persistence.spool import (
    BinarySpoolStorage,
    SpoolCorruptionError,
)
from VIGIA_Vision.async_persistence.worker_pool import PartitionedWorkerPool
from VIGIA_Vision.detection.models import BoundingBox, RawVehicleDetection
from VIGIA_Vision.detection.roi_and_preprocess import PixelROI


# ==============================================================================
# Dobles de Prueba (Mocks Aislados sin Dependencia Externa)
# ==============================================================================

class MockDetectionRepository(IDetectionRepository):
    """Repositorio en memoria para pruebas de aislamiento sin PostgreSQL real."""

    def __init__(self) -> None:
        self.records: List[DetectionInsertDTO] = []
        self.records_by_key: Dict[Tuple[UUID, datetime], UUID] = {}
        self.fail_all_sql: bool = False
        self.fail_countdown: int = 0
        self.connection_error: bool = False

    def persist_detection(self, data: DetectionInsertDTO) -> UUID:
        if self.connection_error:
            raise DatabaseConnectionError("Fallo de conexión simulado con PostgreSQL.")
        if self.fail_countdown > 0:
            self.fail_countdown -= 1
            raise DatabaseConnectionError("Fallo de conexión transitorio.")
        if self.fail_all_sql:
            raise DatabasePersistenceError("Fallo de inserción SQL simulado.")

        new_id = uuid4()
        self.records.append(data)
        key = (data.id_area_vision, data.fecha_hora)
        self.records_by_key[key] = new_id
        return new_id

    def has_detection(self, id_area_vision: UUID, fecha_hora: datetime) -> bool:
        """Verifica existencia previa para pruebas de idempotencia."""
        return (id_area_vision, fecha_hora) in self.records_by_key


# ==============================================================================
# Generadores de Datos Sintéticos para el Arnés
# ==============================================================================

def create_synthetic_jpeg(width: int = 1280, height: int = 720, color: Tuple[int, int, int] = (120, 120, 120)) -> bytes:
    """Genera una imagen JPEG sintética válida con OpenCV."""
    canvas = np.full((height, width, 3), color, dtype=np.uint8)
    cv2.rectangle(canvas, (100, 100), (400, 400), (0, 255, 0), -1)
    ok, buf = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        raise RuntimeError("No se pudo codificar imagen sintética.")
    return buf.tobytes()


def create_synthetic_task(
    codigo_camara: str = "CAM-ENTRADA",
    camera_sequence: int = 1,
    capture_id: Optional[UUID] = None,
    task_id: Optional[UUID] = None,
    raw_jpeg: Optional[bytes] = None,
    timestamp: Optional[datetime] = None,
) -> PersistenceTaskDTO:
    """Genera una instancia válida y reproducible de PersistenceTaskDTO."""
    jpeg_bytes = raw_jpeg or create_synthetic_jpeg()
    c_hash = compute_content_hash(jpeg_bytes)
    ts = timestamp or datetime.now(timezone.utc)

    bbox = BoundingBox(x_min=150, y_min=150, x_max=350, y_max=350)
    det = RawVehicleDetection(bbox=bbox, confidence=0.88, raw_label="car")
    roi = PixelROI(x_min=50.0, y_min=50.0, x_max=600.0, y_max=600.0, frame_width=640, frame_height=640)

    return PersistenceTaskDTO(
        task_id=task_id or uuid4(),
        capture_id=capture_id or uuid4(),
        camera_sequence=camera_sequence,
        codigo_camara=codigo_camara,
        id_camara=uuid4(),
        id_area_vision=uuid4(),
        timestamp_captura=ts,
        content_hash=c_hash,
        raw_jpeg_bytes=jpeg_bytes,
        detections=(det,),
        pixel_roi=roi,
        tipo_vehiculo_pred="AUTOMOVIL",
        confianza_vehiculo=0.88,
        placa_detectada=None,
        confianza_placa=None,
    )


# ==============================================================================
# Suite de Pruebas Automatizadas
# ==============================================================================

class TestAsyncPersistencePilot(unittest.TestCase):
    """Suite principal del arnés de persistencia asíncrona (IMP-01)."""

    def setUp(self) -> None:
        self.test_dir = Path(tempfile.mkdtemp(prefix="vigia_pilot_test_"))
        self.spool_dir = self.test_dir / "spool"
        self.evidence_dir = self.test_dir / "evidencias"
        self.dlq_dir = self.test_dir / "dlq"

        self.spool_storage = BinarySpoolStorage(self.spool_dir)
        self.evidence_writer = AtomicEvidenceWriter(self.evidence_dir, jpeg_quality=90)
        self.db_repo = MockDetectionRepository()
        self.metrics = PilotMetricsCollector()
        self.queue_manager = PartitionedQueueManager(max_depth_per_camera=64, dedup_window_seconds=60.0)

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # 1. Contratos, Identidades y Serialización
    # --------------------------------------------------------------------------

    def test_01_persistence_task_dto_invariants(self) -> None:
        """Valida que PersistenceTaskDTO aplique invariantes y rechace datos corruptos."""
        task = create_synthetic_task()
        self.assertIsInstance(task.task_id, UUID)
        self.assertIsInstance(task.capture_id, UUID)
        self.assertEqual(task.content_hash, compute_content_hash(task.raw_jpeg_bytes))

        # Rechazo de content_hash falso
        with self.assertRaises(ValueError):
            PersistenceTaskDTO(
                task_id=uuid4(),
                capture_id=uuid4(),
                camera_sequence=1,
                codigo_camara="CAM-ENTRADA",
                id_camara=uuid4(),
                id_area_vision=uuid4(),
                timestamp_captura=datetime.now(timezone.utc),
                content_hash="bad_hash",
                raw_jpeg_bytes=task.raw_jpeg_bytes,
                detections=(),
            )

    def test_02_four_level_identity_separation(self) -> None:
        """
        Demuestra la separación entre capture_id y content_hash:
        Dos capturas consecutivas con imagen idéntica (escena estática) son admitidas
        como eventos distintos gracias a tener distinto capture_id.
        """
        shared_jpeg = create_synthetic_jpeg()
        cap_id_1 = uuid4()
        cap_id_2 = uuid4()

        # Captura 1
        task_1 = create_synthetic_task(camera_sequence=1, capture_id=cap_id_1, raw_jpeg=shared_jpeg)
        ok1, st1 = self.queue_manager.enqueue_task(task_1)
        self.assertTrue(ok1)
        self.assertEqual(st1, "ENQUEUED")

        # Reintento idéntico de Captura 1 (mismo capture_id, mismo content_hash)
        task_1_retry = create_synthetic_task(camera_sequence=1, capture_id=cap_id_1, raw_jpeg=shared_jpeg)
        ok_ret, st_ret = self.queue_manager.enqueue_task(task_1_retry)
        self.assertTrue(ok_ret)
        self.assertEqual(st_ret, "DUPLICATE_RETRY_ACK")
        self.assertEqual(self.queue_manager.get_queue_depth("CAM-ENTRADA"), 1)  # No duplicado en cola

        # Captura 2 legítima de escena estática (nuevo capture_id, mismo content_hash)
        task_2 = create_synthetic_task(camera_sequence=2, capture_id=cap_id_2, raw_jpeg=shared_jpeg)
        ok2, st2 = self.queue_manager.enqueue_task(task_2)
        self.assertTrue(ok2)
        self.assertEqual(st2, "ENQUEUED")
        self.assertEqual(self.queue_manager.get_queue_depth("CAM-ENTRADA"), 2)  # Admitida legítimamente

    def test_03_binary_spool_serialization_and_recovery(self) -> None:
        """Valida que BinarySpoolStorage serialice, almacene con fsync y recupere el DTO intacto."""
        task = create_synthetic_task(camera_sequence=1042)
        spool_path = self.spool_storage.write_spool(task)
        self.assertTrue(spool_path.is_file())
        self.assertTrue(spool_path.name.endswith(".spool"))

        recovered_task = self.spool_storage.read_spool(spool_path)
        self.assertEqual(recovered_task.task_id, task.task_id)
        self.assertEqual(recovered_task.capture_id, task.capture_id)
        self.assertEqual(recovered_task.camera_sequence, 1042)
        self.assertEqual(recovered_task.content_hash, task.content_hash)
        self.assertEqual(recovered_task.raw_jpeg_bytes, task.raw_jpeg_bytes)
        self.assertEqual(len(recovered_task.detections), 1)

    # --------------------------------------------------------------------------
    # 2. Los Nueve Escenarios de Fallo Formalizados en OPT-05 (Secc. 20.3)
    # --------------------------------------------------------------------------

    def test_04_scenario_1_partially_written_spool(self) -> None:
        """
        Escenario 1: Corte de energía durante la escritura del archivo .spool.
        El reconciliador detecta fallo de Trailer SHA-256 y aisla el archivo en .corrupt.
        """
        task = create_synthetic_task()
        valid_bytes = self.spool_storage.serialize_task(task)
        truncated_bytes = valid_bytes[: len(valid_bytes) // 2]  # Truncado a la mitad

        cam_dir = self.spool_storage._get_camera_dir(task.codigo_camara)
        corrupt_path = cam_dir / "000000000001_corrupt_trunc.spool"
        with open(corrupt_path, "wb") as fh:
            fh.write(truncated_bytes)

        reconciler = SpoolReconciler(self.spool_storage, self.evidence_writer, self.db_repo)
        res = reconciler.reconcile_cold_start()

        self.assertEqual(res.spools_corrupt, 1)
        self.assertEqual(res.spools_recovered, 0)
        self.assertFalse(corrupt_path.exists())  # Removido de la cola activa
        corrupt_files = list(self.spool_storage.corrupt_dir.glob("*.spool.*"))
        self.assertEqual(len(corrupt_files), 1)  # Confinado en .corrupt

    def test_05_scenario_2_spool_durable_ack_not_sent(self) -> None:
        """
        Escenario 2: El archivo .spool se sincronizó en disco pero el socket HTTP colapsó.
        Al arrancar, SpoolReconciler recupera y persiste la tarea en PostgreSQL sin pérdida.
        """
        task = create_synthetic_task(camera_sequence=5)
        self.spool_storage.write_spool(task)

        reconciler = SpoolReconciler(self.spool_storage, self.evidence_writer, self.db_repo)
        res = reconciler.reconcile_cold_start()

        self.assertEqual(res.spools_recovered, 1)
        self.assertEqual(len(self.db_repo.records), 1)
        self.assertEqual(self.db_repo.records[0].id_area_vision, task.id_area_vision)

    def test_06_scenario_3_volatile_ram_crash_vs_nvme_spool(self) -> None:
        """
        Escenario 3: Comparativa de durabilidad.
        Demuestra formalmente que una tarea exclusivamente en RAM se pierde ante crash,
        mientras que en NVME_SPOOL se recupera íntegramente.
        """
        task_ram = create_synthetic_task(camera_sequence=10)
        self.queue_manager.enqueue_task(task_ram)

        # Simular crash del proceso: se reinicializa la cola (RAM perdida)
        new_queue_manager = PartitionedQueueManager()
        self.assertEqual(new_queue_manager.get_total_depth(), 0)  # Perdido en RAM

        # Con NVMe Spool: se persiste a disco antes del crash
        task_spool = create_synthetic_task(camera_sequence=11)
        self.spool_storage.write_spool(task_spool)

        reconciler = SpoolReconciler(self.spool_storage, self.evidence_writer, self.db_repo)
        res = reconciler.reconcile_cold_start()
        self.assertEqual(res.spools_recovered, 1)  # Preservado y recuperado

    def test_07_scenario_4_annotated_evidence_failure_zero_orphans(self) -> None:
        """
        Escenario 4: Fallo al escribir la evidencia anotada (*_annot.jpg).
        Garantiza limpieza atómica inmediata y cero archivos huérfanos.
        """
        task = create_synthetic_task()
        with self.assertRaises(EvidenceWriteError):
            self.evidence_writer.write_evidence(task, force_fail_annotated=True)

        # Comprobar que no quedó ningún archivo huérfano en evidencias
        created = list(self.evidence_dir.rglob("*.jpg"))
        self.assertEqual(len(created), 0)

    def test_08_scenario_5_evidences_written_sql_failed_routes_to_dlq(self) -> None:
        """
        Escenario 5: Evidencias escritas en disco pero PostgreSQL falla repetidamente.
        Worker ejecuta rollback_evidence (elimina JPEGs), reintenta 3 veces y desvía a DLQ.
        """
        pool = PartitionedWorkerPool(
            queue_manager=self.queue_manager,
            evidence_writer=self.evidence_writer,
            db_repo=self.db_repo,
            dlq_base_dir=self.dlq_dir,
            spool_storage=self.spool_storage,
            metrics_collector=self.metrics,
            max_retries=3,
            backoff_intervals=(0.005, 0.010, 0.015),
        )
        pool.injected_fail_sql_countdown = 10  # Fallarán todos los reintentos
        pool.start(["CAM-ENTRADA"])

        task = create_synthetic_task(codigo_camara="CAM-ENTRADA", camera_sequence=1)
        self.queue_manager.enqueue_task(task)

        # Esperar a que el worker agote reintentos y desvíe a DLQ
        time.sleep(0.15)
        pool.stop(drain_timeout=1.0)

        # Evidencias físicas eliminadas (compensación)
        jpg_files = list(self.evidence_dir.rglob("*.jpg"))
        self.assertEqual(len(jpg_files), 0)

        # Archivo DLQ generado con diagnóstico
        dlq_files = list(self.dlq_dir.rglob("*.dlq"))
        self.assertEqual(len(dlq_files), 1)

        dlq_rec = DLQRecord.from_json(dlq_files[0].read_text(encoding="utf-8"))
        self.assertEqual(dlq_rec.camera_sequence, 1)
        self.assertIn("Inyección de fallo SQL", dlq_rec.last_error)

    def test_09_scenario_6_post_commit_crash_before_spool_purge(self) -> None:
        """
        Escenario 6: PostgreSQL confirmó el commit pero el proceso colapsó antes de borrar el .spool.
        Al arrancar, SpoolReconciler detecta que ya fue insertado y purga el spool sin duplicar filas.
        """
        task = create_synthetic_task(camera_sequence=20)
        spool_path = self.spool_storage.write_spool(task)

        # Simular que la fila ya existe en base de datos
        mapped_dto = DetectionInsertDTO(
            id_area_vision=task.id_area_vision,
            fecha_hora=task.timestamp_captura,
            placa_detectada=None,
            confianza_placa=None,
            confianza_vehiculo=task.confianza_vehiculo,
            tipo_vehiculo_pred=task.tipo_vehiculo_pred,
            ruta_evidencia_foto="test_path_orig.jpg",
        )
        self.db_repo.persist_detection(mapped_dto)
        self.assertEqual(len(self.db_repo.records), 1)

        reconciler = SpoolReconciler(self.spool_storage, self.evidence_writer, self.db_repo)
        res = reconciler.reconcile_cold_start()

        self.assertEqual(res.spools_already_committed, 1)
        self.assertEqual(res.spools_recovered, 0)
        self.assertEqual(len(self.db_repo.records), 1)  # Cero filas duplicadas
        self.assertFalse(spool_path.exists())  # Spool purgado limpiamente

    def test_10_scenario_7_and_8_interrupted_and_repeated_reconciliation(self) -> None:
        """
        Escenarios 7 y 8: Reconciliación interrumpida y ejecutada múltiples veces.
        Demuestra la estricta idempotencia del reconciliador.
        """
        task = create_synthetic_task(camera_sequence=30)
        self.spool_storage.write_spool(task)

        reconciler = SpoolReconciler(self.spool_storage, self.evidence_writer, self.db_repo)

        # 1ra ejecución de reconciliación
        res1 = reconciler.reconcile_cold_start()
        self.assertEqual(res1.spools_recovered, 1)
        self.assertEqual(len(self.db_repo.records), 1)

        # 2da ejecución idéntica de reconciliación
        res2 = reconciler.reconcile_cold_start()
        self.assertEqual(res2.spools_scanned, 0)
        self.assertEqual(len(self.db_repo.records), 1)  # Cero duplicados

    def test_11_scenario_9_storage_failure_during_dlq_handled_gracefully(self) -> None:
        """
        Escenario 9: Fallo en cascada (PostgreSQL inaccesible y disco lleno durante DLQ).
        El worker no colapsa el proceso y avanza de forma segura.
        """
        pool = PartitionedWorkerPool(
            queue_manager=self.queue_manager,
            evidence_writer=self.evidence_writer,
            db_repo=self.db_repo,
            dlq_base_dir=self.dlq_dir,
            max_retries=1,
            backoff_intervals=(0.005,),
        )
        pool.injected_fail_sql_countdown = 5
        pool.injected_fail_dlq_io = True  # Simular disco lleno al escribir DLQ
        pool.start(["CAM-ENTRADA"])

        task = create_synthetic_task(codigo_camara="CAM-ENTRADA", camera_sequence=99)
        self.queue_manager.enqueue_task(task)

        time.sleep(0.08)
        pool.stop(drain_timeout=0.5)

        # El worker debió terminar sin abortar el proceso Python
        self.assertFalse(pool._running)

    # --------------------------------------------------------------------------
    # 3. Criterios de Aceptación Cuantitativos (Latencia, Concurrencia y Memoria)
    # --------------------------------------------------------------------------

    def test_12_backpressure_saturation_returns_429(self) -> None:
        """Valida que una ranura saturada con 64 tareas active backpressure HTTP 429."""
        qm = PartitionedQueueManager(max_depth_per_camera=5)  # Capacidad acotada a 5 para el test
        cam = "CAM-ENTRADA"

        # Llenar las 5 ranuras
        for i in range(1, 6):
            t = create_synthetic_task(codigo_camara=cam, camera_sequence=i)
            ok, status = qm.enqueue_task(t, timeout=0.05)
            self.assertTrue(ok)
            self.assertEqual(status, "ENQUEUED")

        # La 6ta tarea debe ser rechazada con HTTP 429 tras timeout
        t_overflow = create_synthetic_task(codigo_camara=cam, camera_sequence=6)
        ok_over, status_over = qm.enqueue_task(t_overflow, timeout=0.05)
        self.assertFalse(ok_over)
        self.assertEqual(status_over, "QUEUE_SATURATED_429")

    def test_13_cold_reconciliation_speed_under_3_seconds(self) -> None:
        """
        Criterio 8: La reconciliación en frío de 50 archivos .spool
        debe completarse en menos de 3.0 segundos.
        """
        task_template = create_synthetic_task()
        base_ts = datetime.now(timezone.utc)
        # Pre-generar 50 spools válidos en disco con timestamps monotonicamente crecientes
        for i in range(1, 51):
            t = PersistenceTaskDTO(
                task_id=uuid4(),
                capture_id=uuid4(),
                camera_sequence=i,
                codigo_camara="CAM-ENTRADA",
                id_camara=task_template.id_camara,
                id_area_vision=task_template.id_area_vision,
                timestamp_captura=base_ts + timedelta(milliseconds=i * 20),
                content_hash=task_template.content_hash,
                raw_jpeg_bytes=task_template.raw_jpeg_bytes,
                detections=task_template.detections,
            )
            self.spool_storage.write_spool(t)

        reconciler = SpoolReconciler(self.spool_storage, self.evidence_writer, self.db_repo)
        res = reconciler.reconcile_cold_start()

        self.assertEqual(res.spools_recovered, 50)
        self.assertTrue(res.passed_benchmark_latency)
        self.assertLess(res.elapsed_seconds, 3.0)

    def test_14_dlq_reconciliation_protocol(self) -> None:
        """Criterio 5: Reprocesamiento de tareas en DLQ hasta confirmar PostgreSQL."""
        task = create_synthetic_task(camera_sequence=77)
        disc = DiscontinuityRecord("CAM-ENTRADA", 77, 78, "DB_OFFLINE")
        dlq_rec = DLQRecord(
            task_id=task.task_id,
            capture_id=task.capture_id,
            camera_sequence=77,
            codigo_camara="CAM-ENTRADA",
            timestamp_failure=datetime.now(timezone.utc),
            retry_count=3,
            last_error="Connection refused",
            error_trace="Traceback...",
            discontinuity=disc,
        )

        dlq_file = self.dlq_dir / "20261104" / "CAM-ENTRADA" / "000000000077_test.dlq"
        dlq_file.parent.mkdir(parents=True, exist_ok=True)
        dlq_file.write_text(dlq_rec.to_json(), encoding="utf-8")

        # Reprocesador DLQ conectado al repositorio
        reconciler = DLQReconciler(self.dlq_dir, self.evidence_writer, self.db_repo)
        res = reconciler.reprocess_all(payload_resolver=lambda tid: task)

        self.assertEqual(res.dlq_scanned, 1)
        self.assertEqual(res.dlq_reprocessed, 1)
        self.assertEqual(len(self.db_repo.records), 1)

        # Archivo renombrado a .reconciled
        reconciled_file = dlq_file.with_suffix(".dlq.reconciled")
        self.assertTrue(reconciled_file.exists())
        self.assertFalse(dlq_file.exists())


if __name__ == "__main__":
    unittest.main()
