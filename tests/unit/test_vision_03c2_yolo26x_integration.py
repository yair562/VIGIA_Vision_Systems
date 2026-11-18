"""
tests.unit.test_vision_03c2_yolo26x_integration
===============================================
Suite de pruebas unitarias, integración, fallback, concurrencia y validación GPU
para la fase VIGIA-VISION-03C.2 (Integración experimental controlada de YOLO26x).

Cobertura:
- Grupo A: Configuración centralizada, variables de entorno, validaciones y rutas deterministas.
- Grupo B: Fallback automático seguro en inicialización y runtime (sin bucles infinitos).
- Grupo C: Preservación de contratos (RawVehicleDetection, ROI, VisionEngineCoordinator, FSM temporal).
- Grupo D: Concurrencia multi-cámara (CAM-ENTRADA / CAM-SALIDA) y validación real YOLO26x en GPU CUDA.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from unittest.mock import patch
from uuid import uuid4

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from VIGIA_API.ingest_service import build_vision_engine_coordinator
from VIGIA_Core.domain.vision_result import VisionStatus
from VIGIA_Core.repository.detection_repository import IDetectionRepository
from VIGIA_Vision.capture.sources import MobilePushFrameBuffer
from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.config.topology_validator import (
    AreaConfigDTO,
    CameraConfigDTO,
    ITopologyConfigRepository,
    TopologyValidator,
)
from VIGIA_Vision.detection.models import BoundingBox, RawVehicleDetection
from VIGIA_Vision.detection.yolo_detector import (
    InferenceError,
    ModelLoadError,
    YoloDetectorConfig,
    YoloVehicleDetector,
    load_yolo_config_from_env,
    resolve_yolo_weights_path,
)
from VIGIA_Vision.runtime.coordinator import VisionEngineCoordinator
from VIGIA_Vision.runtime.evidence_storage import LocalDiskEvidenceStorage
from VIGIA_Vision.runtime.temporal_state import (
    CameraTemporalStateTracker,
    TemporalDetectionStatus,
    TemporalStateConfig,
)


class _MockBox:
    def __init__(self, xyxy: Sequence[float], conf: float, cls: int) -> None:
        self.xyxy = np.array([xyxy], dtype=np.float32)
        self.conf = np.array([conf], dtype=np.float32)
        self.cls = np.array([cls], dtype=np.float32)


class _MockResult:
    def __init__(self, boxes: Optional[Sequence[_MockBox]] = None) -> None:
        self.boxes = list(boxes) if boxes is not None else []


class _MockAutoBackend:
    def __init__(self, end2end: bool = True, has_one2one: bool = True, cv2_released: bool = True) -> None:
        self.end2end = end2end
        head = type("_MockHead", (), {})()
        head.one2one_cv2 = object() if has_one2one else None
        head.cv2 = None if cv2_released else object()
        inner = type("_MockInner", (), {"model": [head]})()
        self.model = inner


class _MockPredictor:
    def __init__(self, autobackend: _MockAutoBackend) -> None:
        self.model = autobackend


class _MockYOLOModel:
    def __init__(
        self,
        results_to_return: Optional[Sequence[Any]] = None,
        should_raise: bool = False,
        raise_on_call: Optional[int] = None,
        end2end: Optional[bool] = None,
        predictor: Optional[_MockPredictor] = None,
    ) -> None:
        self.results_to_return = list(results_to_return) if results_to_return is not None else []
        self.should_raise = should_raise
        self.raise_on_call = raise_on_call
        if end2end is not None:
            self.end2end = end2end
        if predictor is not None:
            self.predictor = predictor
        self.predict_calls: List[Dict[str, Any]] = []
        self._call_count = 0

    def predict(self, **kwargs: Any) -> List[Any]:
        self._call_count += 1
        self.predict_calls.append(kwargs)
        if self.should_raise:
            raise RuntimeError("CUDA out of memory simulated")
        if self.raise_on_call is not None and self._call_count == self.raise_on_call:
            raise RuntimeError("Transient CUDA inference failure simulated")
        return self.results_to_return


class _FakeTopoRepo(ITopologyConfigRepository):
    def __init__(self) -> None:
        self.cam_ent_id = uuid4()
        self.cam_sal_id = uuid4()
        self.cameras = [
            CameraConfigDTO(
                id_camara=self.cam_ent_id,
                codigo="CAM-ENTRADA",
                nombre="Cámara Entrada",
                uri_stream="push://cam-entrada",
                activa=True,
            ),
            CameraConfigDTO(
                id_camara=self.cam_sal_id,
                codigo="CAM-SALIDA",
                nombre="Cámara Salida",
                uri_stream="push://cam-salida",
                activa=True,
            ),
        ]
        self.areas = [
            AreaConfigDTO(
                id_area_vision=uuid4(),
                id_camara=self.cam_ent_id,
                codigo="ROI-ENT",
                nombre="ROI Entrada",
                tipo_movimiento="ENTRADA",
                x_min=0.05,
                y_min=0.05,
                x_max=0.95,
                y_max=0.95,
                activa=True,
            ),
            AreaConfigDTO(
                id_area_vision=uuid4(),
                id_camara=self.cam_sal_id,
                codigo="ROI-SAL",
                nombre="ROI Salida",
                tipo_movimiento="SALIDA",
                x_min=0.05,
                y_min=0.05,
                x_max=0.95,
                y_max=0.95,
                activa=True,
            ),
        ]

    def get_cameras(self) -> List[CameraConfigDTO]:
        return self.cameras

    def get_areas(self) -> List[AreaConfigDTO]:
        return self.areas


class _InMemoryDetectionRepo(IDetectionRepository):
    def __init__(self) -> None:
        self.saved_records: List[Any] = []

    def save_detection(self, record: Any) -> Any:
        self.saved_records.append(record)
        return record.id_deteccion


def _clean_yolo_env(empty_env_file: Path) -> Dict[str, str]:
    """Prepara un entorno limpio aislado de variables VIGIA_YOLO_* previas."""
    keys = (
        "VIGIA_YOLO_MODEL",
        "VIGIA_YOLO_WEIGHTS",
        "VIGIA_YOLO_IMGSZ",
        "VIGIA_YOLO_QUANTIZE",
        "VIGIA_YOLO_NMS",
        "VIGIA_YOLO_DEVICE",
        "VIGIA_INFERENCE_DEVICE",
        "VIGIA_YOLO_FALLBACK_ENABLED",
        "VIGIA_YOLO_FALLBACK_MODEL",
    )
    env = {k: v for k, v in os.environ.items() if k not in keys}
    env["VIGIA_ENV_FILE"] = str(empty_env_file)
    return env


class TestVision03C2Config(unittest.TestCase):
    """Grupo A — Configuración centralizada, validaciones y resolución de rutas."""

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="vigia_03c2_cfg_"))
        self.empty_env = self.tmp_dir / ".env.empty"
        self.empty_env.write_text("# empty test env\n", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_default_env_keeps_yolo11n_production_baseline(self) -> None:
        """Sin variables experimentales, el modelo predeterminado es estrictamente yolo11n.pt."""
        env = _clean_yolo_env(self.empty_env)
        env["VIGIA_INFERENCE_DEVICE"] = "cpu"
        with patch.dict(os.environ, env, clear=True):
            cfg = load_yolo_config_from_env()
        self.assertEqual(Path(cfg.model_path).name, "yolo11n.pt")
        self.assertNotIn("yolo26x", str(cfg.model_path).lower())
        self.assertEqual(cfg.imgsz, 640)
        self.assertIsNone(cfg.quantize)
        self.assertIsNone(cfg.nms)
        self.assertFalse(cfg.augment)
        self.assertTrue(cfg.fallback_enabled)
        self.assertEqual(Path(cfg.fallback_model_path).name, "yolo11n.pt")
        self.assertEqual(cfg.device, "cpu")

    def test_explicit_yolo26x_env_profile_loaded_cleanly(self) -> None:
        """Perfil experimental YOLO26x por variables de entorno se carga con precisión."""
        env = _clean_yolo_env(self.empty_env)
        env.update(
            {
                "VIGIA_YOLO_MODEL": "yolo26x.pt",
                "VIGIA_YOLO_IMGSZ": "640",
                "VIGIA_YOLO_QUANTIZE": "16",
                "VIGIA_YOLO_NMS": "false",
                "VIGIA_YOLO_DEVICE": "cpu",
                "VIGIA_YOLO_FALLBACK_ENABLED": "true",
                "VIGIA_YOLO_FALLBACK_MODEL": "yolo11n.pt",
            }
        )
        with patch.dict(os.environ, env, clear=True):
            cfg = load_yolo_config_from_env(confidence_threshold=0.25)

        self.assertEqual(Path(cfg.model_path).name, "yolo26x.pt")
        self.assertEqual(cfg.imgsz, 640)
        self.assertEqual(cfg.quantize, 16)
        self.assertIs(cfg.nms, False)
        self.assertEqual(cfg.device, "cpu")
        self.assertIs(cfg.fallback_enabled, True)
        self.assertEqual(Path(cfg.fallback_model_path).name, "yolo11n.pt")

    def test_quantize_and_nms_distinction_propagated_to_predict(self) -> None:
        """nms=None/True/False y quantize=None/16/32 se pasan exactamente sin inferir por nombre."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Caso 1: modelo yolo26x.pt con nms=None y quantize=None -> NO se envían ni se infieren
        m_none = _MockYOLOModel([])
        d_none = YoloVehicleDetector(
            config=YoloDetectorConfig(model_path="yolo26x.pt", nms=None, quantize=None),
            model_factory=lambda _: m_none,
        )
        d_none.detect(frame)
        self.assertNotIn("nms", m_none.predict_calls[0])
        self.assertNotIn("quantize", m_none.predict_calls[0])
        self.assertNotIn("augment", m_none.predict_calls[0])

        # Caso 2: nms=True y quantize=32
        m_true = _MockYOLOModel([])
        d_true = YoloVehicleDetector(
            config=YoloDetectorConfig(model_path="yolo26x.pt", nms=True, quantize=32),
            model_factory=lambda _: m_true,
        )
        d_true.detect(frame)
        self.assertIs(m_true.predict_calls[0]["nms"], True)
        self.assertEqual(m_true.predict_calls[0]["quantize"], 32)

        # Caso 3: nms=False y quantize=16
        m_false = _MockYOLOModel([])
        d_false = YoloVehicleDetector(
            config=YoloDetectorConfig(model_path="yolo26x.pt", nms=False, quantize=16),
            model_factory=lambda _: m_false,
        )
        d_false.detect(frame)
        self.assertIs(m_false.predict_calls[0]["nms"], False)
        self.assertEqual(m_false.predict_calls[0]["quantize"], 16)

    def test_invalid_configs_and_env_values_raise_value_error(self) -> None:
        """Valores inválidos de quantize, imgsz, nms o combinación augment+nms=False son rechazados."""
        with self.assertRaises(ValueError):
            YoloDetectorConfig(quantize=8)
        with self.assertRaises(ValueError):
            YoloDetectorConfig(quantize=True)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            YoloDetectorConfig(imgsz=0)
        with self.assertRaises(ValueError):
            YoloDetectorConfig(imgsz=True)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            YoloDetectorConfig(nms="false")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            YoloDetectorConfig(augment=True, nms=False)

        invalid_cases = [
            {"VIGIA_YOLO_QUANTIZE": "8"},
            {"VIGIA_YOLO_QUANTIZE": "invalid"},
            {"VIGIA_YOLO_IMGSZ": "0"},
            {"VIGIA_YOLO_IMGSZ": "-640"},
            {"VIGIA_YOLO_IMGSZ": "abc"},
            {"VIGIA_YOLO_NMS": "maybe"},
            {"VIGIA_YOLO_FALLBACK_ENABLED": "sometimes"},
        ]
        for overrides in invalid_cases:
            env = _clean_yolo_env(self.empty_env)
            env["VIGIA_INFERENCE_DEVICE"] = "cpu"
            env.update(overrides)
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaises(ValueError, msg=f"Debió fallar con {overrides}"):
                    load_yolo_config_from_env()

    def test_weights_resolution_is_cwd_independent(self) -> None:
        """resolve_yolo_weights_path localiza yolo11n.pt y yolo26x.pt desde cualquier CWD."""
        yolo26x_expected = _REPO_ROOT / "experiments" / "yolo26x" / "weights" / "yolo26x.pt"
        yolo11n_expected = _REPO_ROOT / "yolo11n.pt"
        if not yolo26x_expected.is_file() or not yolo11n_expected.is_file():
            self.skipTest("Pesos reales yolo11n.pt o yolo26x.pt no presentes en disco.")

        prev_cwd = os.getcwd()
        try:
            os.chdir(self.tmp_dir)
            resolved_11 = resolve_yolo_weights_path("yolo11n.pt")
            resolved_26 = resolve_yolo_weights_path("yolo26x.pt")
            self.assertEqual(resolved_11, yolo11n_expected.resolve())
            self.assertEqual(resolved_26, yolo26x_expected.resolve())
            self.assertTrue(resolved_11.is_file())
            self.assertTrue(resolved_26.is_file())
        finally:
            os.chdir(prev_cwd)


class TestVision03C2Fallback(unittest.TestCase):
    """Grupo B — Fallback automático ante fallos de inicialización y runtime."""

    def setUp(self) -> None:
        self.frame = np.zeros((480, 640, 3), dtype=np.uint8)

    def test_init_failure_triggers_automatic_fallback_and_logs_warning(self) -> None:
        """Si los pesos primarios fallan al cargar, conmuta automáticamente a yolo11n.pt."""
        car_box = _MockBox(xyxy=[100, 120, 300, 260], conf=0.89, cls=2)
        fallback_model = _MockYOLOModel([_MockResult([car_box])])
        calls: List[str] = []

        def factory(path: Any) -> Any:
            calls.append(str(path))
            if "yolo26x" in str(path) or "missing" in str(path):
                raise FileNotFoundError(f"Missing weights: {path}")
            return fallback_model

        detector = YoloVehicleDetector(
            config=YoloDetectorConfig(
                model_path="missing_yolo26x.pt",
                device="cpu",
                imgsz=640,
                quantize=16,
                nms=False,
                fallback_enabled=True,
                fallback_model_path="yolo11n.pt",
            ),
            model_factory=factory,
        )

        with self.assertLogs("VIGIA_Vision.detection.yolo_detector", level="WARNING") as cm:
            detections = detector.detect(self.frame)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].raw_label, "car")
        self.assertTrue(detector.using_fallback)
        self.assertEqual(Path(detector.effective_model_path).name, "yolo11n.pt")
        self.assertIn("[model_init]", detector.fallback_reason or "")
        self.assertEqual(calls, ["missing_yolo26x.pt", "yolo11n.pt"])
        # En detect(frame) + 1 probe en model_init
        self.assertEqual(len(fallback_model.predict_calls), 2)
        self.assertNotIn("quantize", fallback_model.predict_calls[-1])
        self.assertNotIn("nms", fallback_model.predict_calls[-1])
        self.assertTrue(any("FALLBACK YOLO ACTIVADO" in msg for msg in cm.output))

    def test_init_failure_when_non_e2e_model_requested_with_nms_false(self) -> None:
        """Un modelo sin soporte end2end con nms=False activa fallback a modelo estándar."""
        non_e2e_model = _MockYOLOModel([], end2end=False)
        fallback_model = _MockYOLOModel([_MockResult([_MockBox([80, 90, 220, 210], 0.85, 2)])])

        def factory(path: Any) -> Any:
            if "bad_e2e" in str(path):
                return non_e2e_model
            return fallback_model

        detector = YoloVehicleDetector(
            config=YoloDetectorConfig(
                model_path="bad_e2e.pt",
                nms=False,
                fallback_enabled=True,
                fallback_model_path="yolo11n.pt",
            ),
            model_factory=factory,
        )
        detections = detector.detect(self.frame)
        self.assertTrue(detector.using_fallback)
        self.assertEqual(len(detections), 1)

    def test_runtime_inference_failure_switches_to_fallback_and_retries_frame_once(self) -> None:
        """Fallo runtime de yolo26x activa fallback a yolo11n.pt y reintenta el frame actual una vez."""
        failing_primary = _MockYOLOModel(raise_on_call=1)
        fallback_box = _MockBox(xyxy=[150, 140, 350, 280], conf=0.91, cls=7)
        healthy_fallback = _MockYOLOModel([_MockResult([fallback_box])])
        loaded_paths: List[str] = []

        def factory(path: Any) -> Any:
            loaded_paths.append(str(path))
            if "yolo26x" in str(path):
                return failing_primary
            return healthy_fallback

        detector = YoloVehicleDetector(
            config=YoloDetectorConfig(
                model_path="yolo26x.pt",
                imgsz=640,
                quantize=16,
                nms=False,
                fallback_enabled=True,
                fallback_model_path="yolo11n.pt",
            ),
            model_factory=factory,
        )

        # Frame 1: primario falla en predict(), fallback se activa y reintenta el mismo frame con éxito
        dets1 = detector.detect(self.frame)
        self.assertEqual(len(dets1), 1)
        self.assertEqual(dets1[0].raw_label, "truck")
        self.assertTrue(detector.using_fallback)
        self.assertIn("[runtime_inference]", detector.fallback_reason or "")
        self.assertEqual(loaded_paths, ["yolo26x.pt", "yolo11n.pt"])
        self.assertEqual(len(failing_primary.predict_calls), 1)
        self.assertEqual(len(healthy_fallback.predict_calls), 1)

        # Frame 2: va directo al fallback ya activo sin tocar el primario fallido
        dets2 = detector.detect(self.frame)
        self.assertEqual(len(dets2), 1)
        self.assertEqual(len(failing_primary.predict_calls), 1)
        self.assertEqual(len(healthy_fallback.predict_calls), 2)

    def test_nan_output_in_primary_triggers_runtime_fallback_and_recovers(self) -> None:
        """Coordenadas o confianza NaN en el modelo primario disparan fallback seguro."""
        nan_primary = _MockYOLOModel([_MockResult([_MockBox([float("nan"), 10, 100, 100], 0.90, 2)])])
        healthy_fallback = _MockYOLOModel([_MockResult([_MockBox([100, 100, 250, 220], 0.87, 5)])])

        detector = YoloVehicleDetector(
            config=YoloDetectorConfig(
                model_path="yolo26x.pt",
                quantize=16,
                nms=False,
                fallback_enabled=True,
                fallback_model_path="yolo11n.pt",
            ),
            model_factory=lambda p: nan_primary if "yolo26x" in str(p) else healthy_fallback,
        )
        dets = detector.detect(self.frame)
        self.assertTrue(detector.using_fallback)
        self.assertEqual(len(dets), 1)
        self.assertEqual(dets[0].raw_label, "bus")

    def test_no_infinite_loop_when_primary_and_fallback_both_fail(self) -> None:
        """Si primario y fallback fallan, aborta limpiamente sin recursión ni bucles infinitos."""
        factory_calls: List[str] = []

        def double_failing_factory(path: Any) -> Any:
            factory_calls.append(str(path))
            return _MockYOLOModel(should_raise=True)

        detector = YoloVehicleDetector(
            config=YoloDetectorConfig(
                model_path="yolo26x.pt",
                quantize=16,
                nms=False,
                fallback_enabled=True,
                fallback_model_path="yolo11n.pt",
            ),
            model_factory=double_failing_factory,
        )
        with self.assertRaises(InferenceError):
            detector.detect(self.frame)
        # Solo debe cargar yolo26x.pt una vez y yolo11n.pt una vez
        self.assertEqual(factory_calls, ["yolo26x.pt", "yolo11n.pt"])

        # En una nueva llamada posterior tras fallback ya agotado, NO vuelve a cargar ni loopear
        with self.assertRaises(InferenceError):
            detector.detect(self.frame)
        self.assertEqual(factory_calls, ["yolo26x.pt", "yolo11n.pt"])

    def test_fallback_disabled_raises_immediately(self) -> None:
        """Con fallback_enabled=False, un fallo del modelo primario falla explícitamente sin respaldo."""
        loaded: List[str] = []

        def factory(path: Any) -> Any:
            loaded.append(str(path))
            if "yolo26x" in str(path):
                raise RuntimeError("Weight load failure")
            return _MockYOLOModel([])

        detector = YoloVehicleDetector(
            config=YoloDetectorConfig(
                model_path="yolo26x.pt",
                fallback_enabled=False,
                fallback_model_path="yolo11n.pt",
            ),
            model_factory=factory,
        )
        with self.assertRaises(ModelLoadError):
            detector.load_model()
        self.assertEqual(loaded, ["yolo26x.pt"])
        self.assertFalse(detector.using_fallback)

    def test_build_vision_engine_coordinator_wiring_from_env(self) -> None:
        """build_vision_engine_coordinator usa load_yolo_config_from_env manteniendo yolo11n default."""
        tmp_dir = Path(tempfile.mkdtemp(prefix="vigia_03c2_coord_"))
        try:
            empty_env = tmp_dir / ".env.empty"
            empty_env.write_text("", encoding="utf-8")
            ev_dir = tmp_dir / "ev"
            topo_repo = _FakeTopoRepo()
            det_repo = _InMemoryDetectionRepo()
            storage = LocalDiskEvidenceStorage(base_directory=ev_dir)
            settings = VisionEngineSettings(evidence_directory=ev_dir)

            # 1. Default -> yolo11n.pt
            env = _clean_yolo_env(empty_env)
            env["VIGIA_INFERENCE_DEVICE"] = "cpu"
            with patch.dict(os.environ, env, clear=True):
                coord_default = build_vision_engine_coordinator(
                    topology_repository=topo_repo,
                    detection_repository=det_repo,
                    evidence_storage=storage,
                    settings=settings,
                    open_sources=False,
                )
            try:
                det_status = coord_default._detector.get_runtime_status()  # type: ignore[attr-defined]
                self.assertEqual(det_status["requested_model"], "yolo11n.pt")
                self.assertEqual(det_status["imgsz"], 640)
                self.assertIsNone(det_status["quantize"])
                self.assertIsNone(det_status["nms"])
            finally:
                coord_default.shutdown()

            # 2. Experimental YOLO26x cuando se configuran env vars explícitamente
            yolo26x_weights = _REPO_ROOT / "experiments" / "yolo26x" / "weights" / "yolo26x.pt"
            if yolo26x_weights.is_file():
                env_exp = _clean_yolo_env(empty_env)
                env_exp.update(
                    {
                        "VIGIA_YOLO_MODEL": "yolo26x.pt",
                        "VIGIA_YOLO_IMGSZ": "640",
                        "VIGIA_YOLO_QUANTIZE": "16",
                        "VIGIA_YOLO_NMS": "false",
                        "VIGIA_YOLO_DEVICE": "cpu",
                    }
                )
                with patch.dict(os.environ, env_exp, clear=True):
                    coord_exp = build_vision_engine_coordinator(
                        topology_repository=topo_repo,
                        detection_repository=det_repo,
                        evidence_storage=storage,
                        settings=settings,
                        open_sources=False,
                    )
                try:
                    det_status = coord_exp._detector.get_runtime_status()  # type: ignore[attr-defined]
                    self.assertEqual(det_status["requested_model"], "yolo26x.pt")
                    self.assertEqual(det_status["quantize"], 16)
                    self.assertIs(det_status["nms"], False)
                finally:
                    coord_exp.shutdown()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestVision03C2ContractsAndCoordinator(unittest.TestCase):
    """Grupo C — Integración de contratos con VisionEngineCoordinator y FSM temporal."""

    def test_coordinator_and_temporal_fsm_survive_live_fallback_seamlessly(self) -> None:
        """
        Coordina 2 pasos consecutivos donde el paso 1 usa yolo26x y el paso 2 dispara
        fallback runtime hacia yolo11n.pt sin romper el contrato VisionResult ni la FSM.
        """
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        car_box = _MockBox(xyxy=[180, 140, 380, 300], conf=0.88, cls=2)
        # Paso 1 OK; paso 2 falla para provocar transición en caliente a yolo11n.pt
        primary_model = _MockYOLOModel([_MockResult([car_box])], raise_on_call=2)
        fallback_model = _MockYOLOModel([_MockResult([car_box])])

        detector = YoloVehicleDetector(
            config=YoloDetectorConfig(
                model_path="yolo26x.pt",
                imgsz=640,
                quantize=16,
                nms=False,
                fallback_enabled=True,
                fallback_model_path="yolo11n.pt",
            ),
            model_factory=lambda p: primary_model if "yolo26x" in str(p) else fallback_model,
        )

        topo_repo = _FakeTopoRepo()
        validator = TopologyValidator(repository=topo_repo)
        buf_ent = MobilePushFrameBuffer("CAM-ENTRADA")
        buf_sal = MobilePushFrameBuffer("CAM-SALIDA")
        buf_ent.open()
        buf_sal.open()

        coordinator = VisionEngineCoordinator(
            topology_validator=validator,
            detector=detector,
            sources={"CAM-ENTRADA": buf_ent, "CAM-SALIDA": buf_sal},
        )
        coordinator.initialize()

        now = [100.0]
        fsm = CameraTemporalStateTracker(
            config=TemporalStateConfig(),
            clock_fn=lambda: now[0],
        )

        # Paso 1 (modelo primario yolo26x)
        seq1 = buf_ent.push_frame(frame)
        env1 = coordinator.process_camera_step("CAM-ENTRADA")
        self.assertIsNotNone(env1)
        self.assertEqual(env1.vision_result.status, VisionStatus.VEHICLE_DETECTED_NO_PLATE)
        self.assertFalse(detector.using_fallback)
        snap1 = fsm.update(
            "CAM-ENTRADA",
            True,
            raw_vehicle_detected=env1.vision_result.vehicle_detected,
            frame_sequence=seq1,
            vehicle_type=env1.vision_result.vehicle_type_pred,
            vehicle_confidence=env1.vision_result.vehicle_confidence,
        )
        self.assertEqual(snap1.detection_status, TemporalDetectionStatus.VEHICLE_CANDIDATE)

        # Paso 2 (primario falla runtime -> fallback en caliente -> mismo frame se procesa con yolo11n)
        now[0] += 0.1
        seq2 = buf_ent.push_frame(frame)
        env2 = coordinator.process_camera_step("CAM-ENTRADA")
        self.assertIsNotNone(env2)
        self.assertTrue(detector.using_fallback)
        self.assertEqual(env2.vision_result.status, VisionStatus.VEHICLE_DETECTED_NO_PLATE)
        self.assertIsInstance(env2.detections_in_roi[0], RawVehicleDetection)
        self.assertIsInstance(env2.detections_in_roi[0].bbox, BoundingBox)

        snap2 = fsm.update(
            "CAM-ENTRADA",
            True,
            raw_vehicle_detected=env2.vision_result.vehicle_detected,
            frame_sequence=seq2,
            vehicle_type=env2.vision_result.vehicle_type_pred,
            vehicle_confidence=env2.vision_result.vehicle_confidence,
        )
        self.assertEqual(snap2.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)


class TestVision03C2ConcurrencyAndRealGPU(unittest.TestCase):
    """Grupo D — Concurrencia multi-cámara y validación real con YOLO26x en GPU CUDA."""

    def test_concurrent_multi_camera_steps_and_thread_safe_fallback(self) -> None:
        """
        Dos hilos (CAM-ENTRADA y CAM-SALIDA) operan simultáneamente sobre una única instancia
        compartida de YoloVehicleDetector sufriendo un fallo runtime concurrente sin race conditions.
        """
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        car_box = _MockBox(xyxy=[180, 140, 360, 290], conf=0.88, cls=2)
        # Falla en la llamada #5 para disparar fallback exactamente en medio de la contención
        primary_model = _MockYOLOModel([_MockResult([car_box])], raise_on_call=5)
        fallback_model = _MockYOLOModel([_MockResult([car_box])])

        factory_lock = threading.Lock()
        factory_loads: List[str] = []

        def thread_counting_factory(path: Any) -> Any:
            with factory_lock:
                factory_loads.append(str(path))
            return primary_model if "yolo26x" in str(path) else fallback_model

        detector = YoloVehicleDetector(
            config=YoloDetectorConfig(
                model_path="yolo26x.pt",
                imgsz=640,
                quantize=16,
                nms=False,
                fallback_enabled=True,
                fallback_model_path="yolo11n.pt",
            ),
            model_factory=thread_counting_factory,
        )
        topo_repo = _FakeTopoRepo()
        validator = TopologyValidator(repository=topo_repo)
        buf_ent = MobilePushFrameBuffer("CAM-ENTRADA")
        buf_sal = MobilePushFrameBuffer("CAM-SALIDA")
        buf_ent.open()
        buf_sal.open()

        coordinator = VisionEngineCoordinator(
            topology_validator=validator,
            detector=detector,
            sources={"CAM-ENTRADA": buf_ent, "CAM-SALIDA": buf_sal},
        )
        coordinator.initialize()

        errors: List[BaseException] = []
        results_by_cam: Dict[str, List[VisionStatus]] = {"CAM-ENTRADA": [], "CAM-SALIDA": []}
        res_lock = threading.Lock()

        def worker(cam_code: str, buf: MobilePushFrameBuffer, iterations: int) -> None:
            try:
                for _ in range(iterations):
                    buf.push_frame(frame)
                    env = coordinator.process_camera_step(cam_code)
                    assert env is not None
                    with res_lock:
                        results_by_cam[cam_code].append(env.vision_result.status)
            except BaseException as exc:
                with res_lock:
                    errors.append(exc)

        t1 = threading.Thread(target=worker, args=("CAM-ENTRADA", buf_ent, 25))
        t2 = threading.Thread(target=worker, args=("CAM-SALIDA", buf_sal, 25))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results_by_cam["CAM-ENTRADA"]), 25)
        self.assertEqual(len(results_by_cam["CAM-SALIDA"]), 25)
        self.assertTrue(all(s == VisionStatus.VEHICLE_DETECTED_NO_PLATE for s in results_by_cam["CAM-ENTRADA"]))
        self.assertTrue(all(s == VisionStatus.VEHICLE_DETECTED_NO_PLATE for s in results_by_cam["CAM-SALIDA"]))
        self.assertTrue(detector.using_fallback)
        # El fallback se activó exactamente una sola vez en todo el burst concurrente
        self.assertEqual(factory_loads, ["yolo26x.pt", "yolo11n.pt"])

    def test_real_yolo26x_cuda_nms_free_and_fallback_probe(self) -> None:
        """
        Validación real en GPU CUDA de yolo26x.pt (imgsz=640, quantize=16, nms=False, end2end=True)
        y validación real de fallback desde archivo .pt corrupto hacia yolo11n.pt.
        """
        try:
            import cv2
            import torch
            import ultralytics
        except ImportError as exc:
            self.skipTest(f"Dependencia faltante para prueba real GPU: {exc}")

        if not torch.cuda.is_available():
            self.skipTest("CUDA no disponible.")

        yolo26x_weights = _REPO_ROOT / "experiments" / "yolo26x" / "weights" / "yolo26x.pt"
        yolo11n_weights = _REPO_ROOT / "yolo11n.pt"
        if not yolo26x_weights.is_file() or not yolo11n_weights.is_file():
            self.skipTest("Pesos reales yolo26x.pt o yolo11n.pt no disponibles.")

        bus_img_path = Path(ultralytics.__file__).parent / "assets" / "bus.jpg"
        if not bus_img_path.is_file():
            self.skipTest("Imagen bus.jpg no encontrada en ultralytics/assets.")

        frame = cv2.imread(str(bus_img_path))
        self.assertIsNotNone(frame)

        # 1. Prueba real YOLO26x FP16 NMS-Free en GPU CUDA
        cfg_26x = YoloDetectorConfig(
            model_path=str(yolo26x_weights),
            confidence_threshold=0.25,
            device="cuda:0",
            imgsz=640,
            quantize=16,
            nms=False,
            fallback_enabled=True,
            fallback_model_path=str(yolo11n_weights),
        )
        detector_26x = YoloVehicleDetector(config=cfg_26x)
        detections = detector_26x.detect(frame)

        self.assertFalse(detector_26x.using_fallback)
        self.assertEqual(detector_26x.effective_device, "cuda:0")
        self.assertTrue(detector_26x.effective_end2end)
        status = detector_26x.get_runtime_status()
        self.assertEqual(status["effective_model"], "yolo26x.pt")
        self.assertTrue(status["end2end_verified"])
        self.assertIn("bus", [d.raw_label for d in detections])
        self.assertNotIn("person", [d.raw_label for d in detections])

        head = detector_26x._model.predictor.model.model.model[-1]
        self.assertIsNotNone(getattr(head, "one2one_cv2", None))
        self.assertIsNone(getattr(head, "cv2", None))

        # 2. Prueba real de fallback desde archivo .pt corrupto hacia yolo11n.pt real
        tmp_dir = Path(tempfile.mkdtemp(prefix="vigia_03c2_corrupt_"))
        try:
            corrupt_pt = tmp_dir / "corrupt_yolo26x.pt"
            corrupt_pt.write_bytes(b"NOT_A_VALID_PYTORCH_CHECKPOINT")
            cfg_corrupt = YoloDetectorConfig(
                model_path=str(corrupt_pt),
                confidence_threshold=0.25,
                device="cuda:0",
                imgsz=640,
                quantize=16,
                nms=False,
                fallback_enabled=True,
                fallback_model_path="yolo11n.pt",
            )
            det_fb = YoloVehicleDetector(config=cfg_corrupt)
            dets_fb = det_fb.detect(frame)
            self.assertTrue(det_fb.using_fallback)
            self.assertEqual(Path(det_fb.effective_model_path).name, "yolo11n.pt")
            self.assertIn("bus", [d.raw_label for d in dets_fb])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        # 3. Prueba real de rechazo NMS-Free cuando se configura yolo11n.pt con nms=False -> fallback estándar
        cfg_incompatible_e2e = YoloDetectorConfig(
            model_path=str(yolo11n_weights),
            confidence_threshold=0.25,
            device="cuda:0",
            imgsz=640,
            nms=False,
            fallback_enabled=True,
            fallback_model_path="yolo11n.pt",
        )
        det_incomp = YoloVehicleDetector(config=cfg_incompatible_e2e)
        dets_incomp = det_incomp.detect(frame)
        self.assertTrue(det_incomp.using_fallback)
        self.assertIsNone(det_incomp.config.nms)
        self.assertIn("bus", [d.raw_label for d in dets_incomp])


if __name__ == "__main__":
    unittest.main()
