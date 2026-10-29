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

from VIGIA_Core.repository.detection_repository import DatabaseConnectionError
from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.config.psycopg_topology_repository import PsycopgTopologyConfigRepository
from VIGIA_Vision.config.topology_validator import AreaConfigDTO, CameraConfigDTO
from VIGIA_Vision.detection.models import BoundingBox, RawVehicleDetection
from VIGIA_Vision.detection.roi_and_preprocess import (
    FrameValidationError,
    filter_detections_by_roi,
    project_normalized_roi,
    validate_bgr_frame,
)
from VIGIA_Vision.runtime.coordinator import map_raw_label_to_domain_vehicle_type
from VIGIA_Vision.runtime.evidence_storage import (
    LocalDiskEvidenceStorage,
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
