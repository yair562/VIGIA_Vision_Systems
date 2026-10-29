"""
tests.unit.test_vision_stage1_components
========================================
Pruebas unitarias exhaustivas para los módulos de la Etapa 1 de ``VIGIA_Vision``:
- ``VisionEngineSettings`` (umbral por omisión 0.70, validaciones e inmutabilidad).
- ``PsycopgTopologyConfigRepository`` (consultas parametrizadas/solo lectura sobre
  ``camara`` y ``area_vision``, cierre garantizado de cursores/conexiones y
  traducción de errores a ``DatabaseConnectionError``).
- ``roi_and_preprocess`` (validación de matriz BGR, proyección de ROI normalizado
  a píxeles y criterio determinista de inclusión del centroide en los bordes).
- ``evidence_storage`` (prevención de path traversal, no sobrescritura y limpieza
  compensatoria).
- Verificación estática de que ningún módulo de ``VIGIA_Vision`` ni sus pruebas
  unitarias importan el prototipo experimental.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from VIGIA_Core.domain.vision_result import VisionResult, VisionStatus
from VIGIA_Core.repository.detection_repository import (
    DatabaseConnectionError,
    DetectionInsertDTO,
    IDetectionRepository,
)
from VIGIA_Vision.capture.sources import MobilePushFrameBuffer
from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.config.psycopg_topology_repository import PsycopgTopologyConfigRepository
from VIGIA_Vision.config.topology_validator import (
    AreaConfigDTO,
    CameraConfigDTO,
    OperationalTopologyDTO,
    TopologyValidationResult,
    TopologyValidator,
)
from VIGIA_Vision.detection.models import BoundingBox, RawVehicleDetection
from VIGIA_Vision.detection.roi_and_preprocess import (
    FrameValidationError,
    filter_detections_by_roi,
    project_normalized_roi,
    validate_bgr_frame,
)
from VIGIA_Vision.runtime.coordinator import (
    IVehicleDetector,
    VisionEngineCoordinator,
    map_raw_label_to_domain_vehicle_type,
)
from VIGIA_Vision.runtime.evidence_storage import (
    LocalDiskEvidenceStorage,
    derive_annotated_evidence_path,
    derive_original_evidence_path,
    render_annotated_frame,
)


class TestVisionEngineSettings(unittest.TestCase):
    """Pruebas de validación e inmutabilidad de VisionEngineSettings."""

    def test_default_vehicle_confidence_threshold_is_070(self) -> None:
        """El umbral inicial de confianza vehicular por omisión es 0.70."""
        settings = VisionEngineSettings()
        self.assertAlmostEqual(settings.vehicle_confidence_threshold, 0.70)
        self.assertGreater(settings.mobile_frame_ttl_seconds, 0.0)
        self.assertIsInstance(settings.evidence_directory, Path)

    def test_settings_immutability(self) -> None:
        settings = VisionEngineSettings()
        with self.assertRaises(FrozenInstanceError):
            settings.vehicle_confidence_threshold = 0.50  # type: ignore[misc]

    def test_invalid_thresholds_and_parameters_rejected(self) -> None:
        with self.assertRaises(ValueError):
            VisionEngineSettings(vehicle_confidence_threshold=0.0)
        with self.assertRaises(ValueError):
            VisionEngineSettings(vehicle_confidence_threshold=1.05)
        with self.assertRaises(ValueError):
            VisionEngineSettings(mobile_frame_ttl_seconds=0.0)
        with self.assertRaises(ValueError):
            VisionEngineSettings(mobile_frame_ttl_seconds=-1.0)
        with self.assertRaises(ValueError):
            VisionEngineSettings(jpeg_quality=0)
        with self.assertRaises(ValueError):
            VisionEngineSettings(jpeg_quality=101)
        with self.assertRaises(ValueError):
            VisionEngineSettings(evidence_directory="   ")


class TestPsycopgTopologyConfigRepository(unittest.TestCase):
    """Pruebas unitarias con dobles de conexión y cursor para PsycopgTopologyConfigRepository."""

    def test_get_cameras_and_areas_maps_dtos_and_closes_resources(self) -> None:
        cam_id = uuid4()
        area_id = uuid4()

        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        # 1. Lectura de cámaras
        mock_cursor.fetchall.return_value = [
            (str(cam_id), "CAM-ENTRADA", "Cámara Entrada", "rtsp://127.0.0.1/in", True),
        ]
        repo = PsycopgTopologyConfigRepository(
            dsn="postgresql://user:pass@localhost:5433/vigia_db",
            connect_timeout=3,
            connection_factory=lambda _dsn, connect_timeout=3: mock_conn,
        )
        cameras = repo.get_cameras()

        self.assertEqual(len(cameras), 1)
        self.assertIsInstance(cameras[0], CameraConfigDTO)
        self.assertEqual(cameras[0].id_camara, cam_id)
        self.assertEqual(cameras[0].codigo, "CAM-ENTRADA")
        self.assertTrue(cameras[0].activa)
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

        # 2. Lectura de áreas con NUMERIC(4,3) (Decimal)
        mock_cursor.reset_mock()
        mock_conn.reset_mock()
        mock_cursor.fetchall.return_value = [
            (
                area_id,
                cam_id,
                "ROI-ENT",
                "Área Entrada",
                "ENTRADA",
                Decimal("0.100"),
                Decimal("0.150"),
                Decimal("0.900"),
                Decimal("0.850"),
                True,
            ),
        ]
        areas = repo.get_areas()

        self.assertEqual(len(areas), 1)
        self.assertIsInstance(areas[0], AreaConfigDTO)
        self.assertEqual(areas[0].id_area_vision, area_id)
        self.assertEqual(areas[0].id_camara, cam_id)
        self.assertAlmostEqual(areas[0].x_min, 0.100)
        self.assertAlmostEqual(areas[0].y_max, 0.850)
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_connection_failure_raises_database_connection_error_without_leaking_dsn(self) -> None:
        secret_dsn = "postgresql://admin:SUPER_SECRET_PASS@localhost:5433/vigia_db"

        def broken_factory(_dsn: str, connect_timeout: int = 5):
            raise RuntimeError("socket timeout")

        repo = PsycopgTopologyConfigRepository(
            dsn=secret_dsn,
            connection_factory=broken_factory,
        )
        with self.assertRaises(DatabaseConnectionError) as ctx:
            repo.get_cameras()

        self.assertNotIn("SUPER_SECRET_PASS", str(ctx.exception))
        self.assertNotIn("SUPER_SECRET_PASS", repr(repo))

    def test_cursor_error_closes_connection_in_finally(self) -> None:
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = RuntimeError("relation camara does not exist")
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        repo = PsycopgTopologyConfigRepository(
            dsn="postgresql://localhost:5433/vigia_db",
            connection_factory=lambda _dsn, connect_timeout=5: mock_conn,
        )
        with self.assertRaises(DatabaseConnectionError):
            repo.get_cameras()

        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()


class TestROIAndPreprocess(unittest.TestCase):
    """Pruebas de validación de fotograma BGR, proyección de ROI y pertenencia en bordes."""

    def setUp(self) -> None:
        self.area = AreaConfigDTO(
            id_area_vision=uuid4(),
            id_camara=uuid4(),
            codigo="ROI-01",
            nombre="Zona Prueba",
            tipo_movimiento="ENTRADA",
            x_min=0.25,
            y_min=0.20,
            x_max=0.75,
            y_max=0.80,
            activa=True,
        )

    def test_validate_bgr_frame_accepts_valid_and_rejects_invalid(self) -> None:
        valid = np.zeros((100, 200, 3), dtype=np.uint8)
        self.assertEqual(validate_bgr_frame(valid), (200, 100))

        with self.assertRaises(FrameValidationError):
            validate_bgr_frame(None)
        with self.assertRaises(FrameValidationError):
            validate_bgr_frame(np.zeros((100, 200), dtype=np.uint8))  # 2D grayscale
        with self.assertRaises(FrameValidationError):
            validate_bgr_frame(np.zeros((100, 200, 4), dtype=np.uint8))  # BGRA 4 canales
        with self.assertRaises(FrameValidationError):
            validate_bgr_frame(np.zeros((100, 200, 3), dtype=np.float32))  # float32

    def test_project_normalized_roi_and_boundary_inclusion(self) -> None:
        # En un frame 200x100, ROI [0.25, 0.20, 0.75, 0.80] -> x en [50.0, 150.0], y en [20.0, 80.0]
        roi = project_normalized_roi(self.area, frame_width=200, frame_height=100)
        self.assertAlmostEqual(roi.x_min, 50.0)
        self.assertAlmostEqual(roi.x_max, 150.0)
        self.assertAlmostEqual(roi.y_min, 20.0)
        self.assertAlmostEqual(roi.y_max, 80.0)

        # Caja cuyo centroide cae exactamente en el borde izquierdo (cx=50.0, cy=50.0) -> INCLUIDA
        border_box = BoundingBox(x_min=40, y_min=40, x_max=60, y_max=60)
        self.assertTrue(roi.contains_bbox_centroid(border_box))

        # Caja cuyo centroide cae en (49.0, 50.0) -> EXCLUIDA
        outside_box = BoundingBox(x_min=39, y_min=40, x_max=59, y_max=60)
        self.assertFalse(roi.contains_bbox_centroid(outside_box))

    def test_vehicle_type_mapping(self) -> None:
        self.assertEqual(map_raw_label_to_domain_vehicle_type("car"), "AUTOMOVIL")
        self.assertEqual(map_raw_label_to_domain_vehicle_type("motorcycle"), "MOTOCICLETA")
        self.assertEqual(map_raw_label_to_domain_vehicle_type("truck"), "CAMION")
        self.assertEqual(map_raw_label_to_domain_vehicle_type("bus"), "AUTOBUS")
        self.assertIsNone(map_raw_label_to_domain_vehicle_type("bicycle"))


class TestEvidenceStorageSafety(unittest.TestCase):
    """Pruebas de seguridad de rutas y renderizado de evidencia anotada."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="vigia_evid_safety_"))
        self.storage = LocalDiskEvidenceStorage(
            base_directory=self.temp_dir,
            encoder=lambda _arr, _q: b"\xff\xd8\xff\xe0JPEG\xff\xd9",
        )
        self.frame = np.zeros((80, 120, 3), dtype=np.uint8)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_rejects_path_traversal_in_camera_code(self) -> None:
        ts = datetime(2026, 10, 29, 12, 0, 0, tzinfo=timezone.utc)
        res = self.storage.save_evidence(
            original_frame=self.frame,
            codigo_camara="../escape",
            timestamp=ts,
        )
        self.assertFalse(res.saved)
        self.assertIsNone(res.original_rel_path)

    def test_render_annotated_frame_does_not_mutate_original(self) -> None:
        det = RawVehicleDetection(
            bbox=BoundingBox(x_min=10, y_min=10, x_max=50, y_max=50),
            confidence=0.90,
            raw_label="car",
        )
        annotated = render_annotated_frame(self.frame, [det])
        self.assertEqual(int(self.frame.sum()), 0)
        self.assertGreater(int(annotated.sum()), 0)

    def test_derive_annotated_and_original_paths(self) -> None:
        """Verifica la derivación determinista bidireccional de rutas de evidencia."""
        orig = "20261029/CAM-ENTRADA/20261029T120000_000000Z_abcdef123456_orig.jpg"
        expected_annot = "20261029/CAM-ENTRADA/20261029T120000_000000Z_abcdef123456_annot.jpg"
        self.assertEqual(derive_annotated_evidence_path(orig), expected_annot)
        self.assertEqual(derive_original_evidence_path(expected_annot), orig)

        with self.assertRaises(ValueError):
            derive_annotated_evidence_path("")
        with self.assertRaises(ValueError):
            derive_annotated_evidence_path("invalid/path/file.jpg")
        with self.assertRaises(ValueError):
            derive_original_evidence_path("invalid/path/file.jpg")

    def test_resolve_files_from_storage(self) -> None:
        """Verifica la resolución segura de archivos originales y anotados en disco."""
        ts = datetime(2026, 10, 29, 12, 0, 0, tzinfo=timezone.utc)
        save_res = self.storage.save_evidence(
            original_frame=self.frame,
            codigo_camara="CAM-ENTRADA",
            timestamp=ts,
            annotated_frame=self.frame,
        )
        self.assertTrue(save_res.saved)
        assert save_res.original_rel_path is not None

        orig_file = self.storage.resolve_original_file(save_res.original_rel_path)
        annot_file = self.storage.resolve_annotated_file(save_res.original_rel_path)
        self.assertIsNotNone(orig_file)
        self.assertIsNotNone(annot_file)
        assert orig_file is not None and annot_file is not None
        self.assertTrue(orig_file.is_file())
        self.assertTrue(annot_file.is_file())

        # Archivo inexistente retorna None sin excepción
        self.assertIsNone(self.storage.resolve_annotated_file("20261029/CAM-ENTRADA/no_existe_orig.jpg"))


class TestStage1EndToEndReproduciblePipeline(unittest.TestCase):
    """
    Validación de integración reproducible de extremo a extremo (E2E) para
    el flujo completo de la Etapa 1 sin requerir hardware físico ni GPU:
    1. Recepción de fotograma (fuente push móvil o sintética).
    2. Validación y preparación del fotograma (BGR uint8).
    3. Proyección de ROI y evaluación geométrica inclusiva.
    4. Invocación del detector vehicular inyectable.
    5. Construcción de observación (VisionObservationEnvelope con VisionResult).
    6. Almacenamiento seguro de evidencia original y anotada en disco.
    7. Persistencia relacional (DetectionInsertDTO con ruta_evidencia_foto).
    8. Recuperación determinista de la imagen anotada a partir de la ruta en BD.
    9. Limpieza compensatoria ante fallos de persistencia.
    """

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="vigia_e2e_reproducible_"))
        self.id_cam = uuid4()
        self.id_area = uuid4()
        id_cam_sal = uuid4()
        self.cam_config = CameraConfigDTO(
            id_camara=self.id_cam,
            codigo="CAM-ENTRADA",
            nombre="Cámara Entrada Principal",
            uri_stream="push://cam-entrada",
            activa=True,
        )
        self.area_config = AreaConfigDTO(
            id_area_vision=self.id_area,
            id_camara=self.id_cam,
            codigo="ROI-ENT",
            nombre="Zona de Control",
            tipo_movimiento="ENTRADA",
            x_min=0.1,
            y_min=0.1,
            x_max=0.9,
            y_max=0.9,
            activa=True,
        )
        self.topology = OperationalTopologyDTO(
            cam_entrada=self.cam_config,
            area_entrada=self.area_config,
            cam_salida=CameraConfigDTO(
                id_camara=id_cam_sal,
                codigo="CAM-SALIDA",
                nombre="Cámara Salida",
                uri_stream="push://cam-salida",
                activa=True,
            ),
            area_salida=AreaConfigDTO(
                id_area_vision=uuid4(),
                id_camara=id_cam_sal,
                codigo="ROI-SAL",
                nombre="Zona Salida",
                tipo_movimiento="SALIDA",
                x_min=0.1,
                y_min=0.1,
                x_max=0.9,
                y_max=0.9,
                activa=True,
            ),
        )
        self.buffer = MobilePushFrameBuffer("CAM-ENTRADA")
        self.storage = LocalDiskEvidenceStorage(
            base_directory=self.temp_dir,
            encoder=lambda _arr, _q: b"\xff\xd8\xff\xe0JPEG\xff\xd9",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_reproducible_e2e_flow_and_ca01_08_resolution(self) -> None:
        persisted_dtos: list[DetectionInsertDTO] = []

        class MockRepo(IDetectionRepository):
            def persist_detection(self, dto: DetectionInsertDTO) -> UUID:
                persisted_dtos.append(dto)
                return uuid4()

        class MockDetector(IVehicleDetector):
            def detect(self, frame: object) -> Sequence[RawVehicleDetection]:
                # Detección centrada en (100, 50) dentro del frame 200x100 y ROI [20..180, 10..90]
                return [
                    RawVehicleDetection(
                        bbox=BoundingBox(x_min=70, y_min=30, x_max=130, y_max=70),
                        confidence=0.88,
                        raw_label="car",
                    )
                ]

        validator = MagicMock(spec=TopologyValidator)
        validator.validate.return_value = TopologyValidationResult(
            is_valid=True,
            topology=self.topology,
        )

        coordinator = VisionEngineCoordinator(
            topology_validator=validator,
            settings=VisionEngineSettings(evidence_directory=self.temp_dir),
            detector=MockDetector(),
            detection_repository=MockRepo(),
            evidence_storage=self.storage,
            sources={
                "CAM-ENTRADA": self.buffer,
                "CAM-SALIDA": MobilePushFrameBuffer("CAM-SALIDA"),
            },
        )
        coordinator.initialize()

        # 1. Recepción: depositar fotograma BGR sintético (200x100x3)
        synthetic_frame = np.full((100, 200, 3), 128, dtype=np.uint8)
        self.buffer.push_frame(synthetic_frame)

        # 2 a 7. Ejecutar paso con persistencia como nuevo evento
        envelope = coordinator.process_camera_step("CAM-ENTRADA", persist_as_new_event=True)
        self.assertIsNotNone(envelope)
        assert envelope is not None

        # 5. Construcción de observación con VisionResult intacto
        self.assertEqual(envelope.vision_result.status, VisionStatus.VEHICLE_DETECTED_NO_PLATE)
        self.assertTrue(envelope.vision_result.vehicle_detected)
        self.assertEqual(envelope.vision_result.vehicle_type_pred, "AUTOMOVIL")
        self.assertAlmostEqual(envelope.vision_result.vehicle_confidence or 0.0, 0.88)

        # 6. Almacenamiento en disco de ambas imágenes
        self.assertIsNotNone(envelope.original_evidence_path)
        self.assertIsNotNone(envelope.annotated_evidence_path)
        assert envelope.original_evidence_path is not None
        assert envelope.annotated_evidence_path is not None

        orig_file = self.temp_dir / envelope.original_evidence_path
        annot_file = self.temp_dir / envelope.annotated_evidence_path
        self.assertTrue(orig_file.is_file())
        self.assertTrue(annot_file.is_file())

        # 7. Persistencia relacional: DTO solo persiste original_rel_path en ruta_evidencia_foto
        self.assertEqual(len(persisted_dtos), 1)
        dto = persisted_dtos[0]
        self.assertEqual(dto.ruta_evidencia_foto, envelope.original_evidence_path)
        self.assertEqual(dto.tipo_vehiculo_pred, "AUTOMOVIL")

        # 8. Resolución de CA01-08: la imagen anotada se recupera determinísticamente
        recovered_annot_path = derive_annotated_evidence_path(dto.ruta_evidencia_foto or "")
        self.assertEqual(recovered_annot_path, envelope.annotated_evidence_path)
        self.assertTrue((self.temp_dir / recovered_annot_path).is_file())

        # Reversibilidad bidireccional
        self.assertEqual(derive_original_evidence_path(recovered_annot_path), dto.ruta_evidencia_foto)


class TestNoVRSemaforoDependency(unittest.TestCase):
    """Verificación estática y de importación en limpio de VIGIA_Vision y tests/unit."""

    def test_no_vr_semaforo_imports_in_vigia_vision_or_unit_tests(self) -> None:
        legacy_pkg = "VR_" + "Semaforo"
        legacy_from = "from " + "vision."
        legacy_import = "import " + "vision."
        forbidden_tokens = (legacy_pkg, legacy_from, legacy_import)
        scan_dirs = [
            _REPO_ROOT / "VIGIA_Vision",
            _REPO_ROOT / "tests" / "unit",
        ]
        offending: list[str] = []

        for folder in scan_dirs:
            for py_file in folder.rglob("*.py"):
                content = py_file.read_text(encoding="utf-8")
                for token in forbidden_tokens:
                    if token in content:
                        offending.append(f"{py_file.relative_to(_REPO_ROOT)}: contiene '{token}'")

        self.assertEqual(offending, [], f"Dependencias prohibidas detectadas: {offending}")

    def test_clean_import_without_side_effects(self) -> None:
        """Importar VIGIA_Vision y todos sus submódulos no carga ultralytics/torch ni abre hardware."""
        import VIGIA_Vision
        import VIGIA_Vision.capture
        import VIGIA_Vision.config
        import VIGIA_Vision.detection
        import VIGIA_Vision.runtime

        self.assertTrue(hasattr(VIGIA_Vision, "VisionEngineCoordinator"))
        self.assertNotIn("ultralytics", sys.modules)
        self.assertNotIn("vision.camera", sys.modules)
        self.assertNotIn("vision.service", sys.modules)
        self.assertNotIn("vision.pipeline", sys.modules)


if __name__ == "__main__":
    unittest.main()
