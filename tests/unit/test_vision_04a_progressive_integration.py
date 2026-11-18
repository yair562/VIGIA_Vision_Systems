"""
Pruebas de integración progresiva VIGIA-VISION-04A (YOLO26x en arquitectura operativa).
"""

from __future__ import annotations

import io
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import cv2
import numpy as np

from VIGIA_API.ingest_service import build_vision_engine_coordinator, create_ingest_app
from VIGIA_Core.domain.user import UserDTO
from VIGIA_Core.domain.vision_result import VisionStatus
from VIGIA_Core.repository.detection_repository import DetectionInsertDTO, IDetectionRepository
from VIGIA_Core.security.password_hasher import hash_password
from VIGIA_Vision.capture.sources import MobilePushFrameBuffer
from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.config.topology_validator import (
    AreaConfigDTO,
    CameraConfigDTO,
    OperationalTopologyDTO,
    TopologyValidator,
)
from VIGIA_Vision.detection.yolo_detector import (
    InferenceBackpressureError,
    InferenceError,
    ModelLoadError,
    YoloDetectorConfig,
    YoloVehicleDetector,
    load_yolo_config_from_env,
    resolve_yolo_weights_path,
)
from VIGIA_Vision.runtime.coordinator import VisionEngineCoordinator


class _DummyBox:
    def __init__(self, x1: float, y1: float, x2: float, y2: float, conf: float, cls_id: int) -> None:
        self.xyxy = [np.array([x1, y1, x2, y2], dtype=np.float32)]
        self.conf = [np.float32(conf)]
        self.cls = [np.float32(cls_id)]


class _DummyModel:
    def __init__(self, *, fp16: bool = True, end2end: bool = True, imgsz: int = 640, fail_cuda: bool = False) -> None:
        self.end2end = end2end
        self.fail_cuda = fail_cuda
        self.predictor = SimpleNamespace(
            args=SimpleNamespace(imgsz=imgsz),
            model=SimpleNamespace(fp16=fp16, end2end=end2end),
        )

    def predict(self, **kwargs):
        if self.fail_cuda:
            raise RuntimeError("CUDA out of memory simulated")
        return [SimpleNamespace(boxes=[_DummyBox(100, 100, 260, 220, 0.91, 2)])]


class _FakeTopologyRepo:
    def __init__(self) -> None:
        self.cam_ent_id = uuid4()
        self.cam_sal_id = uuid4()

    def get_cameras(self):
        return [
            CameraConfigDTO(
                id_camara=self.cam_ent_id,
                codigo="CAM-ENTRADA",
                nombre="Entrada",
                uri_stream="push://cam-entrada",
                activa=True,
            ),
            CameraConfigDTO(
                id_camara=self.cam_sal_id,
                codigo="CAM-SALIDA",
                nombre="Salida",
                uri_stream="push://cam-salida",
                activa=True,
            ),
        ]

    def get_areas(self):
        return [
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


class _InMemoryDetRepo(IDetectionRepository):
    def __init__(self) -> None:
        self.records: list[DetectionInsertDTO] = []

    def persist_detection(self, data: DetectionInsertDTO):
        self.records.append(data)
        return uuid4()


class _InMemoryUserRepo:
    def __init__(self) -> None:
        self._users = {
            "admin_test": UserDTO(
                id_usuario=uuid4(),
                username="admin_test",
                contrasena_hash=hash_password("VigiaTest#2026"),
                nombre_completo="Admin Test",
                rol="ADMINISTRADOR",
                activo=True,
            )
        }

    def get_by_username(self, username: str):
        return self._users.get(username)

    def get_by_id(self, user_id):
        for u in self._users.values():
            if u.id_usuario == user_id:
                return u
        return None


class _InMemoryCredRepo:
    def get_by_token_hash(self, token_hash: str):
        return None


class TestVision04AProgressiveIntegration(unittest.TestCase):
    def test_detector_observability_runtime_verification_and_unload(self) -> None:
        cfg = YoloDetectorConfig(
            model_path="yolo26x.pt",
            device="cpu",
            imgsz=640,
            quantize=16,
            nms=False,
            augment=False,
            fallback_enabled=True,
        )
        det = YoloVehicleDetector(
            config=cfg,
            model_factory=lambda _p: _DummyModel(fp16=True, end2end=True, imgsz=640),
        )
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections = det.detect(frame, camera_code="CAM-ENTRADA")
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].raw_label, "car")

        status = det.get_runtime_status()
        self.assertEqual(status["effective_model"], "yolo26x.pt")
        self.assertTrue(status["effective_fp16"])
        self.assertEqual(status["effective_imgsz"], 640)
        self.assertTrue(status["end2end_verified"])
        metrics = status["inference_metrics"]
        self.assertEqual(metrics["total_inferences"], 1)
        self.assertEqual(metrics["last_camera_code"], "CAM-ENTRADA")
        self.assertIsNotNone(metrics["latency_mean_ms"])
        self.assertIsNotNone(metrics["inference_fps"])

        det.unload()
        self.assertFalse(det.is_loaded)
        det.close()

    def test_cuda_failure_telemetry_and_fallback_recovery(self) -> None:
        def factory(path):
            if "yolo26x" in str(path):
                return _DummyModel(fp16=True, end2end=True, fail_cuda=True)
            return _DummyModel(fp16=False, end2end=False, fail_cuda=False)

        cfg = YoloDetectorConfig(
            model_path="yolo26x.pt",
            device="cpu",
            imgsz=640,
            quantize=16,
            nms=False,
            fallback_enabled=True,
            fallback_model_path="yolo11n.pt",
        )
        det = YoloVehicleDetector(config=cfg, model_factory=factory)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections = det.detect(frame, camera_code="CAM-SALIDA")
        self.assertEqual(len(detections), 1)

        status = det.get_runtime_status()
        self.assertTrue(status["using_fallback"])
        self.assertEqual(status["effective_model"], "yolo11n.pt")
        metrics = status["inference_metrics"]
        self.assertEqual(metrics["cuda_errors"], 1)
        self.assertEqual(metrics["inference_errors"], 1)
        self.assertEqual(metrics["fallback_count"], 1)
        self.assertIsNotNone(metrics["last_recovery_ms"])

    def test_coordinator_backpressure_and_stale_frame_metrics(self) -> None:
        det = YoloVehicleDetector(
            config=YoloDetectorConfig(model_path="yolo26x.pt", device="cpu", imgsz=640, quantize=16, nms=False),
            model_factory=lambda _p: _DummyModel(),
        )
        src_ent = MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=10.0)
        src_sal = MobilePushFrameBuffer("CAM-SALIDA", ttl_seconds=0.01)

        with tempfile.TemporaryDirectory() as tmpdir:
            coord = VisionEngineCoordinator(
                topology_validator=TopologyValidator(repository=_FakeTopologyRepo()),
                settings=VisionEngineSettings(evidence_directory=Path(tmpdir)),
                detector=det,
                sources={"CAM-ENTRADA": src_ent, "CAM-SALIDA": src_sal},
                max_inference_wait_ms=15.0,
            )
            coord.initialize(open_sources=True)
            try:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                src_ent.push_frame(frame)

                # Simular contención GPU manteniendo el lock desde otro hilo
                held = threading.Event()
                release = threading.Event()

                def _hold():
                    with det._lock:
                        held.set()
                        release.wait(timeout=2.0)

                t = threading.Thread(target=_hold, daemon=True)
                t.start()
                self.assertTrue(held.wait(timeout=1.0))
                try:
                    env = coord.process_camera_step("CAM-ENTRADA")
                    self.assertIsNotNone(env)
                    self.assertEqual(env.vision_result.status, VisionStatus.VISION_ERROR)
                finally:
                    release.set()
                    t.join(timeout=1.0)

                # Simular frame obsoleto por TTL en CAM-SALIDA
                src_sal.push_frame(frame)
                time.sleep(0.03)
                env_stale = coord.process_camera_step("CAM-SALIDA")
                self.assertIsNotNone(env_stale)
                self.assertEqual(env_stale.vision_result.status, VisionStatus.CAMERA_ERROR)

                op = coord.get_operational_metrics()
                self.assertFalse(op["temporal_fsm_integrated"])
                self.assertEqual(op["cameras"]["CAM-ENTRADA"]["dropped_frames"], 1)
                self.assertEqual(op["cameras"]["CAM-ENTRADA"]["drop_reasons"]["GPU_BACKPRESSURE_TIMEOUT"], 1)
                self.assertEqual(op["cameras"]["CAM-ENTRADA"]["last_drop_policy"], "DROP_ON_GPU_BACKPRESSURE")
                self.assertEqual(op["cameras"]["CAM-SALIDA"]["dropped_frames"], 1)
                self.assertEqual(op["cameras"]["CAM-SALIDA"]["drop_reasons"]["STALE_FRAME_TTL"], 1)
            finally:
                coord.shutdown()

    def test_backpressure_never_activates_fallback_and_recovers_next_frame(self) -> None:
        det = YoloVehicleDetector(
            config=YoloDetectorConfig(
                model_path="yolo26x.pt",
                device="cpu",
                imgsz=640,
                quantize=16,
                nms=False,
                fallback_enabled=True,
                fallback_model_path="yolo11n.pt",
            ),
            model_factory=lambda _p: _DummyModel(fp16=True, end2end=True, imgsz=640),
        )
        src_ent = MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=10.0)
        src_sal = MobilePushFrameBuffer("CAM-SALIDA", ttl_seconds=10.0)
        with tempfile.TemporaryDirectory() as tmpdir:
            coord = VisionEngineCoordinator(
                topology_validator=TopologyValidator(repository=_FakeTopologyRepo()),
                settings=VisionEngineSettings(evidence_directory=Path(tmpdir)),
                detector=det,
                sources={"CAM-ENTRADA": src_ent, "CAM-SALIDA": src_sal},
                max_inference_wait_ms=15.0,
            )
            coord.initialize(open_sources=True)
            try:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                src_ent.push_frame(frame)
                held = threading.Event()
                release = threading.Event()

                def _hold():
                    with det._lock:
                        held.set()
                        release.wait(timeout=2.0)

                t = threading.Thread(target=_hold, daemon=True)
                t.start()
                self.assertTrue(held.wait(timeout=1.0))
                try:
                    env_drop = coord.process_camera_step("CAM-ENTRADA")
                    self.assertIsNotNone(env_drop)
                    self.assertEqual(env_drop.vision_result.status, VisionStatus.VISION_ERROR)
                    self.assertFalse(det.using_fallback)
                    self.assertEqual(det.get_runtime_status()["effective_model"], "yolo26x.pt")
                finally:
                    release.set()
                    t.join(timeout=1.0)

                src_ent.push_frame(frame)
                env_ok = coord.process_camera_step("CAM-ENTRADA")
                self.assertIsNotNone(env_ok)
                self.assertEqual(env_ok.vision_result.status, VisionStatus.VEHICLE_DETECTED_NO_PLATE)
                self.assertFalse(det.using_fallback)
                self.assertEqual(det.get_runtime_status()["effective_model"], "yolo26x.pt")
            finally:
                coord.shutdown()

    def test_shutdown_idempotence_close_blocks_new_inferences_and_exception_resilience(self) -> None:
        det = YoloVehicleDetector(
            config=YoloDetectorConfig(model_path="yolo26x.pt", device="cpu", imgsz=640, quantize=16, nms=False),
            model_factory=lambda _p: _DummyModel(),
        )
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.assertEqual(len(det.detect(frame)), 1)
        det.close()
        det.close()
        self.assertFalse(det.is_loaded)
        with self.assertRaises(ModelLoadError):
            det.load_model()
        with self.assertRaises(InferenceError):
            det.detect(frame)

        det2 = YoloVehicleDetector(
            config=YoloDetectorConfig(model_path="yolo26x.pt", device="cpu", imgsz=640, quantize=16, nms=False),
            model_factory=lambda _p: _DummyModel(),
        )
        src_ent = MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=10.0)
        src_sal = MobilePushFrameBuffer("CAM-SALIDA", ttl_seconds=10.0)
        with tempfile.TemporaryDirectory() as tmpdir:
            coord = VisionEngineCoordinator(
                topology_validator=TopologyValidator(repository=_FakeTopologyRepo()),
                settings=VisionEngineSettings(evidence_directory=Path(tmpdir)),
                detector=det2,
                sources={"CAM-ENTRADA": src_ent, "CAM-SALIDA": src_sal},
            )
            coord.initialize(open_sources=True)
            det2.detect(frame)
            self.assertTrue(det2.is_loaded)
            with patch.object(coord.registry, "release_all", side_effect=RuntimeError("Simulated release failure")):
                coord.shutdown()
            self.assertFalse(coord.is_initialized)
            self.assertFalse(det2.is_loaded)

    def test_real_yolo26x_supervision_status_and_ingest_pipeline(self) -> None:
        yolo26_path = resolve_yolo_weights_path("experiments/yolo26x/weights/yolo26x.pt")
        if not yolo26_path.is_file():
            self.skipTest("Pesos yolo26x.pt no disponibles")

        try:
            import torch
            if not torch.cuda.is_available():
                self.skipTest("CUDA no disponible")
        except Exception:
            self.skipTest("PyTorch CUDA no disponible")

        env_overrides = {
            "VIGIA_YOLO_MODEL": str(yolo26_path),
            "VIGIA_YOLO_DEVICE": "cuda:0",
            "VIGIA_YOLO_IMGSZ": "640",
            "VIGIA_YOLO_QUANTIZE": "16",
            "VIGIA_YOLO_NMS": "false",
            "VIGIA_YOLO_AUGMENT": "false",
            "VIGIA_YOLO_FALLBACK_ENABLED": "true",
        }
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(os.environ, env_overrides, clear=False):
            det_repo = _InMemoryDetRepo()
            coord = build_vision_engine_coordinator(
                settings=VisionEngineSettings(evidence_directory=Path(tmpdir)),
                topology_repository=_FakeTopologyRepo(),
                detection_repository=det_repo,
                open_sources=False,
            )
            try:
                app = create_ingest_app(
                    coordinator=coord,
                    auth_token="test-token-04a",
                    topology_repository=_FakeTopologyRepo(),
                    user_repository=_InMemoryUserRepo(),
                    allow_in_memory=True,
                )
                client = app.test_client()
                login_res = client.post(
                    "/api/v1/auth/login",
                    json={"username": "admin_test", "password": "VigiaTest#2026"},
                )
                self.assertEqual(login_res.status_code, 200)

                sample_img = Path(__file__).resolve().parents[2] / "benchmarks" / "vigia_bench_v1" / "images"
                jpg_files = sorted(sample_img.glob("*.jpg"))
                if jpg_files:
                    img_bytes = jpg_files[0].read_bytes()
                else:
                    blank = np.zeros((480, 640, 3), dtype=np.uint8)
                    ok, enc = cv2.imencode(".jpg", blank)
                    self.assertTrue(ok)
                    img_bytes = enc.tobytes()

                push_res = client.post(
                    "/api/v1/cameras/CAM-ENTRADA/push",
                    headers={"Authorization": "Bearer test-token-04a"},
                    data={"image": (io.BytesIO(img_bytes), "probe.jpg")},
                    content_type="multipart/form-data",
                )
                self.assertEqual(push_res.status_code, 200)

                sup_res = client.get("/api/v1/supervision/status")
                self.assertEqual(sup_res.status_code, 200)
                payload = sup_res.get_json()
                self.assertTrue(payload["ok"])
                vm = payload["vision_metrics"]
                self.assertIsNotNone(vm)
                self.assertFalse(vm["temporal_fsm_integrated"])
                self.assertEqual(vm["detector"]["effective_model"], "yolo26x.pt")
                self.assertTrue(vm["detector"]["end2end"])
                self.assertTrue(vm["detector"]["effective_fp16"])
                self.assertNotIn("weights_path", vm["detector"])
                self.assertNotIn("requested_weights_path", vm["detector"])
                self.assertGreaterEqual(vm["detector"]["inference_metrics"]["total_inferences"], 1)
                self.assertGreaterEqual(vm["cameras"]["CAM-ENTRADA"]["processed_count"], 1)
            finally:
                coord.shutdown()


if __name__ == "__main__":
    unittest.main()
