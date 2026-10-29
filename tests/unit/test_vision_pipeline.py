"""
tests.unit.test_vision_pipeline
===============================
Pruebas unitarias e integración simulada para ``VisionEngineCoordinator`` y el
flujo completo de la Etapa 1 del motor propio ``VIGIA_Vision``.

Verifica sin GPU, sin cámaras físicas, sin PostgreSQL activo y sin ningún
import del prototipo experimental:
- Bloqueo fail-fast si la topología es inválida.
- Asociación inequívoca de cada observación con su cámara y área de visión.
- Exclusión de detecciones fuera del ROI (RF-03) y bajo el umbral 0.70.
- Mapeo de clases ('car' -> 'AUTOMOVIL', 'bus' -> 'AUTOBUS' en VisionResult y
  'OTRO' en DetectionInsertDTO).
- Construcción válida de VisionObservationEnvelope con VisionResult intacto.
- Almacenamiento de evidencia original y anotada, tolerancia a fallo de disco
  (ruta_evidencia_foto=None) y limpieza compensatoria ante fallo de PostgreSQL.
- Aislamiento de fallos entre CAM-ENTRADA y CAM-SALIDA.
- No persistencia de NO_VEHICLE_DETECTED, CAMERA_ERROR ni VISION_ERROR.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Sequence
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import numpy as np

# Asegurar raíz del repositorio en sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from VIGIA_Core.domain.vision_result import VisionResult, VisionStatus
from VIGIA_Core.repository.detection_repository import (
    DatabasePersistenceError,
    DetectionInsertDTO,
    IDetectionRepository,
)
from VIGIA_Vision.capture.sources import MobilePushFrameBuffer
from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.config.topology_validator import (
    AreaConfigDTO,
    CameraConfigDTO,
    ITopologyConfigRepository,
    TopologyValidator,
)
from VIGIA_Vision.detection.models import (
    BoundingBox,
    RawVehicleDetection,
    VisionObservationEnvelope,
)
from VIGIA_Vision.runtime.coordinator import (
    IObservationConsumer,
    IVehicleDetector,
    VisionEngineCoordinator,
)
from VIGIA_Vision.runtime.evidence_storage import (
    EvidenceSaveResult,
    IEvidenceStorageService,
    LocalDiskEvidenceStorage,
)


class SpyDetectionRepository(IDetectionRepository):
    """Doble de prueba que captura los DetectionInsertDTO recibidos."""

    def __init__(self, should_fail: bool = False) -> None:
        self.persisted_dtos: List[DetectionInsertDTO] = []
        self.should_fail = should_fail

    def persist_detection(self, data: DetectionInsertDTO) -> UUID:
        if self.should_fail:
            raise DatabasePersistenceError("Fallo simulado de inserción SQL en tabla deteccion.")
        self.persisted_dtos.append(data)
        return uuid4()


class SpyObservationConsumer(IObservationConsumer):
    """Doble de prueba que registra los sobres VisionObservationEnvelope recibidos."""

    def __init__(self) -> None:
        self.envelopes: List[VisionObservationEnvelope] = []

    def on_observation(self, envelope: VisionObservationEnvelope) -> None:
        self.envelopes.append(envelope)


class StubVehicleDetector(IVehicleDetector):
    """Detector vehicular simulado configurable sin dependencias de IA."""

    def __init__(
        self,
        detections: Sequence[RawVehicleDetection] = (),
        raise_error: bool = False,
    ) -> None:
        self._detections = tuple(detections)
        self._raise_error = raise_error

    def detect(self, frame: object) -> Sequence[RawVehicleDetection]:
        if self._raise_error:
            raise RuntimeError("CUDA simulated out of memory")
        return self._detections


class TestVisionEngineCoordinatorStage1(unittest.TestCase):
    """Pruebas del coordinador propio de VIGIA_Vision (Etapa 1)."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="vigia_test_evid_"))
        self.id_cam_ent = uuid4()
        self.id_cam_sal = uuid4()
        self.id_area_ent = uuid4()
        self.id_area_sal = uuid4()

        self.cam_entrada = CameraConfigDTO(
            id_camara=self.id_cam_ent,
            codigo="CAM-ENTRADA",
            nombre="Cámara Entrada",
            uri_stream="push://cam-entrada",
            activa=True,
        )
        self.cam_salida = CameraConfigDTO(
            id_camara=self.id_cam_sal,
            codigo="CAM-SALIDA",
            nombre="Cámara Salida",
            uri_stream="push://cam-salida",
            activa=True,
        )
        # ROI central: [0.20, 0.20, 0.80, 0.80] -> en un frame 200x100 (W=200, H=100)
        # corresponde a x en [40, 160] e y en [20, 80].
        self.area_entrada = AreaConfigDTO(
            id_area_vision=self.id_area_ent,
            id_camara=self.id_cam_ent,
            codigo="ROI-ENT",
            nombre="ROI Entrada",
            tipo_movimiento="ENTRADA",
            x_min=0.20,
            y_min=0.20,
            x_max=0.80,
            y_max=0.80,
            activa=True,
        )
        self.area_salida = AreaConfigDTO(
            id_area_vision=self.id_area_sal,
            id_camara=self.id_cam_sal,
            codigo="ROI-SAL",
            nombre="ROI Salida",
            tipo_movimiento="SALIDA",
            x_min=0.20,
            y_min=0.20,
            x_max=0.80,
            y_max=0.80,
            activa=True,
        )

        mock_top_repo = MagicMock(spec=ITopologyConfigRepository)
        mock_top_repo.get_cameras.return_value = [self.cam_entrada, self.cam_salida]
        mock_top_repo.get_areas.return_value = [self.area_entrada, self.area_salida]
        self.validator = TopologyValidator(repository=mock_top_repo)

        self.buf_entrada = MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=5.0)
        self.buf_salida = MobilePushFrameBuffer("CAM-SALIDA", ttl_seconds=5.0)

        self.valid_frame = np.zeros((100, 200, 3), dtype=np.uint8)
        self.storage = LocalDiskEvidenceStorage(
            base_directory=self.temp_dir,
            jpeg_quality=85,
            encoder=lambda _arr, _q: b"\xff\xd8\xff\xe0FAKE_JPEG_BYTES\xff\xd9",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_empty_buffer_produces_camera_error_and_does_not_persist(self) -> None:
        """Un buffer móvil vacío produce CAMERA_ERROR y no persiste nada en PostgreSQL."""
        spy_repo = SpyDetectionRepository()
        coord = VisionEngineCoordinator(
            topology_validator=self.validator,
            settings=VisionEngineSettings(evidence_directory=self.temp_dir),
            detection_repository=spy_repo,
            evidence_storage=self.storage,
            sources={"CAM-ENTRADA": self.buf_entrada, "CAM-SALIDA": self.buf_salida},
        )
        coord.initialize()

        env = coord.process_camera_step("CAM-ENTRADA", persist_as_new_event=True)
        self.assertIsNotNone(env)
        assert env is not None
        self.assertEqual(env.vision_result.status, VisionStatus.CAMERA_ERROR)
        self.assertFalse(env.vision_result.vehicle_detected)
        self.assertEqual(env.id_camara, self.id_cam_ent)
        self.assertEqual(env.id_area_vision, self.id_area_ent)
        self.assertEqual(len(spy_repo.persisted_dtos), 0)

    def test_detections_outside_roi_or_below_threshold_are_excluded(self) -> None:
        """
        Detecciones fuera del ROI o con confianza < 0.70 quedan excluidas,
        produciendo NO_VEHICLE_DETECTED y sin persistir en PostgreSQL.
        """
        # 1) Vehículo con alta confianza (0.92) pero centroide en (15, 15) -> FUERA del ROI [40..160, 20..80]
        outside_det = RawVehicleDetection(
            bbox=BoundingBox(x_min=5, y_min=5, x_max=25, y_max=25),
            confidence=0.92,
            raw_label="car",
        )
        # 2) Vehículo dentro del ROI (centroide en 100, 50) pero confianza 0.65 < umbral 0.70
        low_conf_det = RawVehicleDetection(
            bbox=BoundingBox(x_min=80, y_min=40, x_max=120, y_max=60),
            confidence=0.65,
            raw_label="car",
        )
        spy_repo = SpyDetectionRepository()
        coord = VisionEngineCoordinator(
            topology_validator=self.validator,
            settings=VisionEngineSettings(evidence_directory=self.temp_dir),
            detector=StubVehicleDetector([outside_det, low_conf_det]),
            detection_repository=spy_repo,
            evidence_storage=self.storage,
            sources={"CAM-ENTRADA": self.buf_entrada, "CAM-SALIDA": self.buf_salida},
        )
        coord.initialize()
        self.buf_entrada.push_frame(self.valid_frame)

        env = coord.process_camera_step("CAM-ENTRADA", persist_as_new_event=True)
        assert env is not None
        self.assertEqual(env.vision_result.status, VisionStatus.NO_VEHICLE_DETECTED)
        self.assertFalse(env.vision_result.vehicle_detected)
        self.assertEqual(env.metrics.in_roi_now, 0)
        self.assertEqual(env.metrics.total_detected_in_frame, 2)
        self.assertEqual(env.metrics.excluded_outside_roi, 1)
        self.assertIsNone(env.metrics.unique_vehicles_total)
        self.assertEqual(len(spy_repo.persisted_dtos), 0)

    def test_valid_detection_bus_maps_to_autobus_in_vision_result_and_otro_in_dto(self) -> None:
        """
        Una detección de 'bus' dentro del ROI con confianza >= 0.70:
        - Asigna 'AUTOBUS' en VisionResult.vehicle_type_pred.
        - Convierte 'AUTOBUS' -> 'OTRO' en DetectionInsertDTO.
        - Guarda evidencia original y anotada y retorna id_deteccion en el sobre.
        """
        inside_bus = RawVehicleDetection(
            bbox=BoundingBox(x_min=70, y_min=30, x_max=130, y_max=70),  # centroide (100, 50) dentro del ROI
            confidence=0.88,
            raw_label="bus",
        )
        spy_repo = SpyDetectionRepository()
        spy_consumer = SpyObservationConsumer()
        coord = VisionEngineCoordinator(
            topology_validator=self.validator,
            settings=VisionEngineSettings(evidence_directory=self.temp_dir),
            detector=StubVehicleDetector([inside_bus]),
            detection_repository=spy_repo,
            evidence_storage=self.storage,
            sources={"CAM-ENTRADA": self.buf_entrada, "CAM-SALIDA": self.buf_salida},
            consumers=[spy_consumer],
        )
        coord.initialize()
        self.buf_entrada.push_frame(self.valid_frame)

        env = coord.process_camera_step("CAM-ENTRADA", persist_as_new_event=True)
        assert env is not None

        # Verificar VisionResult intacto
        self.assertIsInstance(env.vision_result, VisionResult)
        self.assertEqual(env.vision_result.status, VisionStatus.VEHICLE_DETECTED_NO_PLATE)
        self.assertTrue(env.vision_result.vehicle_detected)
        self.assertAlmostEqual(env.vision_result.vehicle_confidence or 0.0, 0.88)
        self.assertEqual(env.vision_result.vehicle_type_pred, "AUTOBUS")
        self.assertIsNotNone(env.vision_result.evidence_path)

        # Verificar sobre y métricas (unique_vehicles_total es None en Etapa 1)
        self.assertEqual(env.codigo_camara, "CAM-ENTRADA")
        self.assertEqual(env.tipo_movimiento, "ENTRADA")
        self.assertEqual(env.metrics.in_roi_now, 1)
        self.assertIsNone(env.metrics.unique_vehicles_total)
        self.assertIsNotNone(env.id_deteccion)
        self.assertIsNotNone(env.original_evidence_path)
        self.assertIsNotNone(env.annotated_evidence_path)
        self.assertTrue((self.temp_dir / str(env.original_evidence_path)).is_file())
        self.assertTrue((self.temp_dir / str(env.annotated_evidence_path)).is_file())

        # Verificar DTO enviado al repositorio SQL
        self.assertEqual(len(spy_repo.persisted_dtos), 1)
        dto = spy_repo.persisted_dtos[0]
        self.assertEqual(dto.id_area_vision, self.id_area_ent)
        self.assertEqual(dto.tipo_vehiculo_pred, "OTRO")
        self.assertEqual(dto.ruta_evidencia_foto, env.original_evidence_path)
        self.assertEqual(len(spy_consumer.envelopes), 1)

    def test_storage_failure_continues_persistence_with_null_evidence_path(self) -> None:
        """Si falla el guardado de evidencia en disco, se persiste la detección con ruta_evidencia_foto=None."""
        failing_storage = MagicMock(spec=IEvidenceStorageService)
        failing_storage.save_evidence.return_value = EvidenceSaveResult(
            saved=False,
            original_rel_path=None,
            annotated_rel_path=None,
            created_files=(),
            error_message="Simulated disk full",
        )
        inside_car = RawVehicleDetection(
            bbox=BoundingBox(x_min=70, y_min=30, x_max=130, y_max=70),
            confidence=0.91,
            raw_label="car",
        )
        spy_repo = SpyDetectionRepository()
        coord = VisionEngineCoordinator(
            topology_validator=self.validator,
            settings=VisionEngineSettings(evidence_directory=self.temp_dir),
            detector=StubVehicleDetector([inside_car]),
            detection_repository=spy_repo,
            evidence_storage=failing_storage,
            sources={"CAM-ENTRADA": self.buf_entrada, "CAM-SALIDA": self.buf_salida},
        )
        coord.initialize()
        self.buf_entrada.push_frame(self.valid_frame)

        env = coord.process_camera_step("CAM-ENTRADA", persist_as_new_event=True)
        assert env is not None
        self.assertIsNone(env.vision_result.evidence_path)
        self.assertEqual(len(spy_repo.persisted_dtos), 1)
        self.assertIsNone(spy_repo.persisted_dtos[0].ruta_evidencia_foto)
        self.assertEqual(spy_repo.persisted_dtos[0].tipo_vehiculo_pred, "AUTOMOVIL")

    def test_sql_persistence_failure_rolls_back_only_created_evidence_files(self) -> None:
        """
        Si el INSERT en PostgreSQL falla después de escribir las evidencias,
        rollback_evidence borra exclusivamente los archivos creados por la
        operación fallida y conserva cualquier evidencia previa.
        """
        # Crear un archivo preexistente en el directorio de evidencias que NO debe borrarse
        preexisting = self.temp_dir / "preexisting_keep.jpg"
        preexisting.write_bytes(b"KEEP")

        inside_truck = RawVehicleDetection(
            bbox=BoundingBox(x_min=70, y_min=30, x_max=130, y_max=70),
            confidence=0.94,
            raw_label="truck",
        )
        failing_repo = SpyDetectionRepository(should_fail=True)
        coord = VisionEngineCoordinator(
            topology_validator=self.validator,
            settings=VisionEngineSettings(evidence_directory=self.temp_dir),
            detector=StubVehicleDetector([inside_truck]),
            detection_repository=failing_repo,
            evidence_storage=self.storage,
            sources={"CAM-ENTRADA": self.buf_entrada, "CAM-SALIDA": self.buf_salida},
        )
        coord.initialize()
        self.buf_entrada.push_frame(self.valid_frame)

        with self.assertRaises(DatabasePersistenceError):
            coord.process_camera_step("CAM-ENTRADA", persist_as_new_event=True)

        # El archivo preexistente sigue intacto, y no quedaron archivos *_orig.jpg ni *_annot.jpg huérfanos
        self.assertTrue(preexisting.is_file())
        jpg_files = list(self.temp_dir.rglob("*.jpg"))
        self.assertEqual(jpg_files, [preexisting])

    def test_evidence_storage_second_file_failure_cleans_partial(self) -> None:
        """
        Si falla la codificación o escritura de la segunda imagen (annotated_frame),
        save_evidence limpia el archivo original parcial recién creado y retorna saved=False.
        """
        calls = 0

        def failing_second_encoder(_arr: np.ndarray, _q: int) -> bytes:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("Disk full while writing annotated image")
            return b"\xff\xd8\xff\xe0JPEG\xff\xd9"

        storage = LocalDiskEvidenceStorage(
            base_directory=self.temp_dir,
            encoder=failing_second_encoder,
        )
        res = storage.save_evidence(
            original_frame=self.valid_frame,
            codigo_camara="CAM-ENTRADA",
            timestamp=datetime(2026, 10, 29, 12, 0, 0, tzinfo=timezone.utc),
            annotated_frame=self.valid_frame,
        )

        self.assertFalse(res.saved)
        self.assertIsNone(res.original_rel_path)
        self.assertIsNone(res.annotated_rel_path)
        # Verificar que no quedó ningún archivo huérfano en disco
        jpg_files = list(self.temp_dir.rglob("*.jpg"))
        self.assertEqual(jpg_files, [])

    def test_single_operation_does_not_duplicate_sql_writes(self) -> None:
        """Una sola invocación a process_camera_step ejecuta como máximo un único INSERT en el repositorio."""
        inside_car = RawVehicleDetection(
            bbox=BoundingBox(x_min=70, y_min=30, x_max=130, y_max=70),
            confidence=0.88,
            raw_label="car",
        )
        spy_repo = SpyDetectionRepository()
        coord = VisionEngineCoordinator(
            topology_validator=self.validator,
            settings=VisionEngineSettings(evidence_directory=self.temp_dir),
            detector=StubVehicleDetector([inside_car]),
            detection_repository=spy_repo,
            evidence_storage=self.storage,
            sources={"CAM-ENTRADA": self.buf_entrada, "CAM-SALIDA": self.buf_salida},
        )
        coord.initialize()
        self.buf_entrada.push_frame(self.valid_frame)

        env = coord.process_camera_step("CAM-ENTRADA", persist_as_new_event=True)
        self.assertIsNotNone(env)
        self.assertEqual(len(spy_repo.persisted_dtos), 1)

    def test_detector_exception_produces_vision_error_and_isolates_cameras(self) -> None:
        """
        Un error del detector produce VISION_ERROR sin persistir en BD, y en
        step_all_cameras() un fallo en CAM-ENTRADA no impide procesar CAM-SALIDA.
        """
        inside_moto = RawVehicleDetection(
            bbox=BoundingBox(x_min=70, y_min=30, x_max=130, y_max=70),
            confidence=0.85,
            raw_label="motorcycle",
        )
        spy_repo = SpyDetectionRepository()
        coord = VisionEngineCoordinator(
            topology_validator=self.validator,
            settings=VisionEngineSettings(evidence_directory=self.temp_dir),
            detector=StubVehicleDetector([inside_moto]),
            detection_repository=spy_repo,
            evidence_storage=self.storage,
            sources={"CAM-ENTRADA": self.buf_entrada, "CAM-SALIDA": self.buf_salida},
        )
        coord.initialize()

        # CAM-ENTRADA vacía (fallará con CAMERA_ERROR), CAM-SALIDA con fotograma válido
        self.buf_salida.push_frame(self.valid_frame)

        results = coord.step_all_cameras(persist_as_new_event=False)
        env_ent = results["CAM-ENTRADA"]
        env_sal = results["CAM-SALIDA"]
        assert env_ent is not None and env_sal is not None

        self.assertEqual(env_ent.vision_result.status, VisionStatus.CAMERA_ERROR)
        self.assertEqual(env_sal.vision_result.status, VisionStatus.VEHICLE_DETECTED_NO_PLATE)
        self.assertEqual(env_sal.vision_result.vehicle_type_pred, "MOTOCICLETA")
        # Como persist_as_new_event=False por omisión (sin tracking en Etapa 1), no se insertó fila por frame
        self.assertEqual(len(spy_repo.persisted_dtos), 0)


if __name__ == "__main__":
    unittest.main()
