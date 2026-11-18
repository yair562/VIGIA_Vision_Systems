"""
Pruebas unitarias y de telemetría para VIGIA-VISION-06 (Promoción de YOLO26x a Producción).
"""

from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import numpy as np

from VIGIA_Core.domain.vision_result import VisionStatus
from VIGIA_Vision.capture.sources import MobilePushFrameBuffer
from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.config.topology_validator import (
    AreaConfigDTO,
    CameraConfigDTO,
    TopologyValidator,
)
from VIGIA_Vision.detection.yolo_detector import (
    YoloDetectorConfig,
    YoloVehicleDetector,
    load_yolo_config_from_env,
)
from VIGIA_Vision.runtime.coordinator import VisionEngineCoordinator


class _MockBox:
    def __init__(self, x1: float, y1: float, x2: float, y2: float, conf: float, cls_id: int) -> None:
        self.xyxy = [np.array([x1, y1, x2, y2], dtype=np.float32)]
        self.conf = [np.float32(conf)]
        self.cls = [np.float32(cls_id)]


class _MockModel:
    def __init__(
        self,
        *,
        fp16: bool = True,
        end2end: bool = True,
        fail_after: int = 0,
        fail_exc: BaseException | None = None,
    ) -> None:
        self.end2end = end2end
        self.fail_after = fail_after
        self.fail_exc = fail_exc or RuntimeError("CUDA out of memory simulated")
        self.calls = 0
        self.predictor = SimpleNamespace(
            args=SimpleNamespace(imgsz=640),
            model=SimpleNamespace(fp16=fp16, end2end=end2end),
        )

    def predict(self, **kwargs):
        self.calls += 1
        if self.fail_after > 0 and self.calls >= self.fail_after:
            raise self.fail_exc
        return [SimpleNamespace(boxes=[_MockBox(120, 120, 320, 300, 0.92, 2)])]


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


class TestVision06ProductionPromotion(unittest.TestCase):
    def test_per_inference_telemetry_never_misattributes_fallback_as_yolo26x(self) -> None:
        """
        Verifica que al transicionar de yolo26x.pt a yolo11n.pt por fallo runtime,
        last_inference_model y inferences_by_model registren exactamente cada modelo.
        """
        primary = _MockModel(fp16=True, end2end=True, fail_after=3)
        fallback = _MockModel(fp16=False, end2end=False)

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
            model_factory=lambda p: primary if "yolo26x" in str(p) else fallback,
        )
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Inferencias 1 y 2 exitosas bajo yolo26x.pt
        det.detect(frame, camera_code="CAM-ENTRADA")
        det.detect(frame, camera_code="CAM-SALIDA")
        st_pre = det.get_runtime_status()
        self.assertEqual(st_pre["effective_model"], "yolo26x.pt")
        self.assertEqual(st_pre["last_inference_model"], "yolo26x.pt")
        self.assertEqual(st_pre["inference_metrics"]["inferences_by_model"], {"yolo26x.pt": 2})
        self.assertFalse(st_pre["using_fallback"])

        # Inferencia 3 falla por OOM simulado -> fallback a yolo11n.pt y reintento único
        det.detect(frame, camera_code="CAM-ENTRADA")
        st_post = det.get_runtime_status()
        self.assertTrue(st_post["using_fallback"])
        self.assertEqual(st_post["requested_model"], "yolo26x.pt")
        self.assertEqual(st_post["effective_model"], "yolo11n.pt")
        self.assertEqual(st_post["last_inference_model"], "yolo11n.pt")
        self.assertIsNotNone(st_post["fallback_reason"])
        self.assertIsNotNone(st_post["fallback_timestamp"])
        self.assertEqual(
            st_post["inference_metrics"]["inferences_by_model"],
            {"yolo26x.pt": 2, "yolo11n.pt": 1},
        )
        self.assertEqual(st_post["inference_metrics"]["cuda_errors"], 1)
        self.assertEqual(st_post["inference_metrics"]["fallback_count"], 1)
        self.assertIsNotNone(st_post["inference_metrics"]["last_recovery_ms"])
        self.assertIs(st_post["effective_fp16"], False)
        self.assertIs(st_post["end2end"], False)

    def test_oom_fallback_releases_primary_model_before_loading_backup(self) -> None:
        """Ante OOM, libera la referencia previa al modelo primario antes de instanciar fallback."""
        events: list[str] = []
        primary = _MockModel(fp16=True, end2end=True, fail_after=2)
        fallback = _MockModel(fp16=False, end2end=False)

        det: YoloVehicleDetector

        def factory(path):
            events.append(f"load:{Path(str(path)).name}:prev_model_is_none={det._model is None}")
            return primary if "yolo26x" in str(path) else fallback

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
            model_factory=factory,
        )
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        det.detect(frame)
        self.assertIsNotNone(det._model)
        det.detect(frame)
        self.assertEqual(
            events,
            [
                "load:yolo26x.pt:prev_model_is_none=True",
                "load:yolo11n.pt:prev_model_is_none=True",
            ],
        )

    def test_concurrent_cameras_record_per_camera_inference_model(self) -> None:
        """El coordinador registra el modelo exacto por cámara bajo contención multihilo."""
        primary = _MockModel(fp16=True, end2end=True, fail_after=6)
        fallback = _MockModel(fp16=False, end2end=False)

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
            model_factory=lambda p: primary if "yolo26x" in str(p) else fallback,
        )
        src_ent = MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=10.0)
        src_sal = MobilePushFrameBuffer("CAM-SALIDA", ttl_seconds=10.0)
        with tempfile.TemporaryDirectory() as tmpdir:
            coord = VisionEngineCoordinator(
                topology_validator=TopologyValidator(repository=_FakeTopologyRepo()),
                settings=VisionEngineSettings(evidence_directory=Path(tmpdir)),
                detector=det,
                sources={"CAM-ENTRADA": src_ent, "CAM-SALIDA": src_sal},
            )
            coord.initialize(open_sources=True)
            try:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                errors: list[BaseException] = []

                def worker(code: str, buf: MobilePushFrameBuffer) -> None:
                    try:
                        for _ in range(10):
                            buf.push_frame(frame)
                            env = coord.process_camera_step(code)
                            assert env is not None
                            assert env.vision_result.status == VisionStatus.VEHICLE_DETECTED_NO_PLATE
                    except BaseException as exc:
                        errors.append(exc)

                t1 = threading.Thread(target=worker, args=("CAM-ENTRADA", src_ent))
                t2 = threading.Thread(target=worker, args=("CAM-SALIDA", src_sal))
                t1.start()
                t2.start()
                t1.join()
                t2.join()

                self.assertEqual(errors, [])
                metrics = coord.get_operational_metrics()
                self.assertEqual(metrics["detector"]["inference_metrics"]["total_inferences"], 20)
                by_model = metrics["detector"]["inference_metrics"]["inferences_by_model"]
                self.assertEqual(sum(by_model.values()), 20)
                self.assertEqual(metrics["cameras"]["CAM-ENTRADA"]["last_inference_model"], "yolo11n.pt")
                self.assertEqual(metrics["cameras"]["CAM-SALIDA"]["last_inference_model"], "yolo11n.pt")
            finally:
                coord.shutdown()

    def test_production_and_rollback_env_profiles_parse_cleanly(self) -> None:
        """Valida carga determinista del perfil de producción YOLO26x y rollback a YOLO11n."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prod_env = Path(tmpdir) / ".env.prod"
            prod_env.write_text(
                "\n".join(
                    [
                        "VIGIA_YOLO_MODEL=experiments/yolo26x/weights/yolo26x.pt",
                        "VIGIA_YOLO_DEVICE=cpu",
                        "VIGIA_YOLO_IMGSZ=640",
                        "VIGIA_YOLO_QUANTIZE=16",
                        "VIGIA_YOLO_NMS=false",
                        "VIGIA_YOLO_FALLBACK_ENABLED=true",
                        "VIGIA_YOLO_FALLBACK_MODEL=yolo11n.pt",
                        "VIGIA_YOLO_DEDUP_IOU=0.55",
                        "VIGIA_YOLO_CONSOLIDATE_CONFIDENCE=true",
                        "VIGIA_YOLO_FRONTAL_AUX_ENABLED=true",
                        "VIGIA_YOLO_FRONTAL_AUX_IMGSZ=384",
                        "VIGIA_YOLO_FRONTAL_AUX_TRIGGER_CONF=0.70",
                    ]
                ),
                encoding="utf-8",
            )
            rb_env = Path(tmpdir) / ".env.rollback"
            rb_env.write_text(
                "\n".join(
                    [
                        "VIGIA_INFERENCE_DEVICE=cpu",
                        "VIGIA_YOLO_MODEL=yolo11n.pt",
                        "VIGIA_YOLO_IMGSZ=640",
                        "VIGIA_YOLO_FALLBACK_ENABLED=true",
                        "VIGIA_YOLO_FALLBACK_MODEL=yolo11n.pt",
                    ]
                ),
                encoding="utf-8",
            )

            keys = (
                "VIGIA_YOLO_MODEL",
                "VIGIA_YOLO_WEIGHTS",
                "VIGIA_YOLO_DEVICE",
                "VIGIA_INFERENCE_DEVICE",
                "VIGIA_YOLO_IMGSZ",
                "VIGIA_YOLO_QUANTIZE",
                "VIGIA_YOLO_NMS",
                "VIGIA_YOLO_FALLBACK_ENABLED",
                "VIGIA_YOLO_FALLBACK_MODEL",
                "VIGIA_YOLO_DEDUP_IOU",
                "VIGIA_YOLO_CONSOLIDATE_CONFIDENCE",
                "VIGIA_YOLO_FRONTAL_AUX_ENABLED",
                "VIGIA_YOLO_FRONTAL_AUX_IMGSZ",
                "VIGIA_YOLO_FRONTAL_AUX_TRIGGER_CONF",
            )
            base = {k: v for k, v in os.environ.items() if k not in keys}

            with patch.dict(os.environ, {**base, "VIGIA_ENV_FILE": str(prod_env)}, clear=True):
                cfg_prod = load_yolo_config_from_env()
                self.assertEqual(Path(cfg_prod.model_path).name, "yolo26x.pt")
                self.assertEqual(cfg_prod.quantize, 16)
                self.assertIs(cfg_prod.nms, False)
                self.assertTrue(cfg_prod.frontal_aux_enabled)
                self.assertEqual(cfg_prod.frontal_aux_imgsz, 384)
                self.assertEqual(cfg_prod.deduplicate_iou_threshold, 0.55)
                self.assertTrue(cfg_prod.consolidate_frontal_confidence)
                self.assertTrue(cfg_prod.fallback_enabled)
                self.assertEqual(Path(cfg_prod.fallback_model_path).name, "yolo11n.pt")

            with patch.dict(os.environ, {**base, "VIGIA_ENV_FILE": str(rb_env)}, clear=True):
                cfg_rb = load_yolo_config_from_env()
                self.assertEqual(Path(cfg_rb.model_path).name, "yolo11n.pt")
                self.assertIsNone(cfg_rb.quantize)
                self.assertIsNone(cfg_rb.nms)


if __name__ == "__main__":
    unittest.main()
