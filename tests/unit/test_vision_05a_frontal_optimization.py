"""
tests.unit.test_vision_05a_frontal_optimization
===============================================
Pruebas unitarias y de integración para VIGIA-VISION-05A:
- Deduplicación espacial intra-frame y consolidación de confianza en anclas partidas.
- Sonda auxiliar multiescala condicional para recuperación de automóviles y autobuses frontales.
- Configuración centralizada por entorno y preservación del modelo predeterminado (yolo11n.pt).
- Telemetría operativa (frontal_aux_triggers, frontal_aux_recoveries, duplicates_suppressed).
- Validación de integración real en GPU con YOLO26x sobre casos problemáticos frontales del corpus.
"""

from __future__ import annotations

import os
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from unittest.mock import patch
from uuid import uuid4

import cv2
import numpy as np

from VIGIA_Core.domain.vision_result import VisionStatus
from VIGIA_Vision.capture.sources import MobilePushFrameBuffer
from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.config.topology_validator import (
    AreaConfigDTO,
    CameraConfigDTO,
    TopologyValidator,
)
from VIGIA_Vision.detection.models import BoundingBox, CaptureReadResult, RawVehicleDetection
from VIGIA_Vision.detection.yolo_detector import (
    YoloDetectorConfig,
    YoloVehicleDetector,
    compute_bbox_iou,
    deduplicate_and_consolidate_detections,
    load_yolo_config_from_env,
    resolve_yolo_weights_path,
)
from VIGIA_Vision.runtime.coordinator import VisionEngineCoordinator


class _MockBox:
    def __init__(self, xyxy: Sequence[float], conf: float, cls: int) -> None:
        self.xyxy = np.array([xyxy], dtype=np.float32)
        self.conf = np.array([conf], dtype=np.float32)
        self.cls = np.array([cls], dtype=np.float32)


class _MockResult:
    def __init__(self, boxes: Optional[Sequence[_MockBox]] = None) -> None:
        self.boxes = list(boxes) if boxes is not None else []


class _MultiscaleMockModel:
    supports_multiscale_aux = True

    def __init__(
        self,
        by_imgsz: Dict[int, Sequence[_MockBox]],
        *,
        end2end: bool = True,
    ) -> None:
        self.by_imgsz = by_imgsz
        self.end2end = end2end
        self.calls: List[Dict[str, Any]] = []

    def predict(self, **kwargs: Any) -> List[_MockResult]:
        self.calls.append(kwargs)
        sz = int(kwargs.get("imgsz", 640))
        return [_MockResult(self.by_imgsz.get(sz, []))]


class _FakeTopologyRepo:
    def __init__(self) -> None:
        self.cam_sal_id = uuid4()
        self.cam_ent_id = uuid4()

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
                x_min=0.10,
                y_min=0.20,
                x_max=0.90,
                y_max=0.80,
                activa=True,
            ),
            AreaConfigDTO(
                id_area_vision=uuid4(),
                id_camara=self.cam_sal_id,
                codigo="ROI-SAL",
                nombre="ROI Salida",
                tipo_movimiento="SALIDA",
                x_min=0.10,
                y_min=0.20,
                x_max=0.90,
                y_max=0.80,
                activa=True,
            ),
        ]


class TestVision05AFrontalOptimization(unittest.TestCase):
    def test_compute_bbox_iou_and_deduplication_consolidation(self) -> None:
        b1 = BoundingBox(100, 100, 300, 300)
        b2 = BoundingBox(102, 101, 301, 299)  # Casi idéntica (IoU > 0.95)
        b3 = BoundingBox(400, 100, 550, 250)  # Disjunta (IoU = 0.0)

        self.assertGreater(compute_bbox_iou(b1, b2), 0.95)
        self.assertEqual(compute_bbox_iou(b1, b3), 0.0)

        # Caso 1: Partición de confianza entre dos anclas de la misma clase (ej. EV-0657 auto frontal rosa)
        dets_same_cls = (
            RawVehicleDetection(bbox=b1, confidence=0.535, raw_label="car"),
            RawVehicleDetection(bbox=b2, confidence=0.508, raw_label="car"),
            RawVehicleDetection(bbox=b3, confidence=0.810, raw_label="bus"),
        )
        dedup, supp = deduplicate_and_consolidate_detections(
            dets_same_cls,
            iou_threshold=0.55,
            consolidate_split_confidence=True,
        )
        self.assertEqual(supp, 1)
        self.assertEqual(len(dedup), 2)
        # Preserva orden original: primero el auto consolidado en b1, luego el autobús en b3
        self.assertEqual(dedup[0].raw_label, "car")
        self.assertGreaterEqual(dedup[0].confidence, 0.68)
        self.assertEqual(dedup[1].raw_label, "bus")
        self.assertAlmostEqual(dedup[1].confidence, 0.810, places=3)

        # Caso 2: Partición inter-clase sobre autobús frontal (truck + bus con IoU >= 0.75)
        dets_bus_split = (
            RawVehicleDetection(bbox=b1, confidence=0.595, raw_label="truck"),
            RawVehicleDetection(bbox=b2, confidence=0.453, raw_label="bus"),
        )
        dedup_bus, supp_bus = deduplicate_and_consolidate_detections(
            dets_bus_split,
            iou_threshold=0.55,
            consolidate_split_confidence=True,
        )
        self.assertEqual(supp_bus, 1)
        self.assertEqual(len(dedup_bus), 1)
        self.assertEqual(dedup_bus[0].raw_label, "bus")
        self.assertGreaterEqual(dedup_bus[0].confidence, 0.75)

    def test_config_and_env_loading_for_vision_05a_settings(self) -> None:
        cfg_default = YoloDetectorConfig()
        self.assertEqual(cfg_default.deduplicate_iou_threshold, 0.55)
        self.assertTrue(cfg_default.consolidate_frontal_confidence)
        self.assertTrue(cfg_default.frontal_aux_enabled)
        self.assertEqual(cfg_default.frontal_aux_imgsz, 384)
        self.assertEqual(cfg_default.frontal_aux_trigger_confidence, 0.70)

        with self.assertRaises(ValueError):
            YoloDetectorConfig(deduplicate_iou_threshold=0.0)
        with self.assertRaises(ValueError):
            YoloDetectorConfig(deduplicate_iou_threshold=1.5)
        with self.assertRaises(ValueError):
            YoloDetectorConfig(frontal_aux_imgsz=0)
        with self.assertRaises(ValueError):
            YoloDetectorConfig(frontal_aux_trigger_confidence=0.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            empty_env = Path(tmpdir) / ".env.empty"
            empty_env.write_text("", encoding="utf-8")
            env = {
                "VIGIA_ENV_FILE": str(empty_env),
                "VIGIA_INFERENCE_DEVICE": "cpu",
                "VIGIA_YOLO_DEDUP_IOU": "0.60",
                "VIGIA_YOLO_CONSOLIDATE_CONFIDENCE": "false",
                "VIGIA_YOLO_FRONTAL_AUX_ENABLED": "true",
                "VIGIA_YOLO_FRONTAL_AUX_IMGSZ": "480",
                "VIGIA_YOLO_FRONTAL_AUX_TRIGGER_CONF": "0.75",
            }
            with patch.dict(os.environ, env, clear=True):
                loaded = load_yolo_config_from_env()
                self.assertEqual(Path(loaded.model_path).name, "yolo11n.pt")
                self.assertEqual(loaded.deduplicate_iou_threshold, 0.60)
                self.assertFalse(loaded.consolidate_frontal_confidence)
                self.assertTrue(loaded.frontal_aux_enabled)
                self.assertEqual(loaded.frontal_aux_imgsz, 480)
                self.assertEqual(loaded.frontal_aux_trigger_confidence, 0.75)

            env_disabled = {
                "VIGIA_ENV_FILE": str(empty_env),
                "VIGIA_INFERENCE_DEVICE": "cpu",
                "VIGIA_YOLO_DEDUP_IOU": "none",
                "VIGIA_YOLO_FRONTAL_AUX_IMGSZ": "none",
            }
            with patch.dict(os.environ, env_disabled, clear=True):
                loaded_dis = load_yolo_config_from_env()
                self.assertIsNone(loaded_dis.deduplicate_iou_threshold)
                self.assertIsNone(loaded_dis.frontal_aux_imgsz)

    def test_conditional_multiscale_frontal_recovery_and_telemetry(self) -> None:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Escenario A: en 640 no detecta nada (como EV-0625 auto frontal cian), pero en 384 detecta car 0.80
        mock_model = _MultiscaleMockModel(
            by_imgsz={
                640: [],
                384: [_MockBox([225, 103, 493, 342], 0.797, 2)],
            }
        )
        det = YoloVehicleDetector(
            config=YoloDetectorConfig(
                model_path="yolo26x.pt",
                device="cpu",
                imgsz=640,
                quantize=16,
                nms=False,
                frontal_aux_enabled=True,
                frontal_aux_imgsz=384,
                frontal_aux_trigger_confidence=0.70,
            ),
            model_factory=lambda _p: mock_model,
        )
        res = det.detect(frame, camera_code="CAM-SALIDA")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].raw_label, "car")
        self.assertAlmostEqual(res[0].confidence, 0.797, places=3)
        self.assertEqual(len(mock_model.calls), 2)
        self.assertEqual(mock_model.calls[0]["imgsz"], 640)
        self.assertEqual(mock_model.calls[1]["imgsz"], 384)

        status = det.get_runtime_status()
        self.assertEqual(status["inference_metrics"]["frontal_aux_triggers"], 1)
        self.assertEqual(status["inference_metrics"]["frontal_aux_recoveries"], 1)

        # Escenario B: cuando en 640 ya hay una detección sólida >= 0.70 y sin candidatos débiles, NO dispara sonda 384
        mock_strong = _MultiscaleMockModel(
            by_imgsz={
                640: [_MockBox([120, 100, 480, 260], 0.91, 5)],
                384: [_MockBox([120, 100, 480, 260], 0.85, 5)],
            }
        )
        det_strong = YoloVehicleDetector(
            config=YoloDetectorConfig(
                model_path="yolo26x.pt",
                device="cpu",
                imgsz=640,
                quantize=16,
                nms=False,
            ),
            model_factory=lambda _p: mock_strong,
        )
        res_strong = det_strong.detect(frame)
        self.assertEqual(len(res_strong), 1)
        self.assertEqual(len(mock_strong.calls), 1)
        self.assertEqual(det_strong.get_runtime_status()["inference_metrics"]["frontal_aux_triggers"], 0)

    def test_real_yolo26x_frontal_car_and_frontal_bus_recovery_in_coordinator(self) -> None:
        yolo26_path = resolve_yolo_weights_path("experiments/yolo26x/weights/yolo26x.pt")
        repo_root = Path(__file__).resolve().parents[2]
        ev_dir = repo_root / "evidencias_vigia"
        if not yolo26_path.is_file() or not ev_dir.is_dir():
            self.skipTest("Pesos yolo26x.pt o evidencias_vigia no disponibles")

        try:
            import torch

            if not torch.cuda.is_available():
                self.skipTest("CUDA no disponible")
        except Exception:
            self.skipTest("PyTorch CUDA no disponible")

        # Tres casos reales de fallo frontal en YOLO26x baseline:
        # 1. EV-0625: automóvil frontal cian (0.00 en baseline -> >=0.79 en 05A)
        # 2. EV-0657: automóvil frontal rosa con doble ancla partida (0.535+0.508 en baseline -> >=0.95 en 05A)
        # 3. EV-0581: autobús escolar frontal + auto frontal (0.67+0.59 en baseline -> ambos >=0.75 en 05A)
        cases = [
            ev_dir / "20261116/CAM-SALIDA/20261116T172015_568913Z_c43de572acc5_orig.jpg",
            ev_dir / "20261116/CAM-SALIDA/20261116T172113_418425Z_e8a735512bc2_orig.jpg",
            ev_dir / "20261114/CAM-SALIDA/20261114T010037_321148Z_29a0e74bbe1e_orig.jpg",
        ]
        for p in cases:
            if not p.is_file():
                self.skipTest(f"Evidencia no encontrada: {p}")

        det = YoloVehicleDetector(
            config=YoloDetectorConfig(
                model_path=str(yolo26_path),
                confidence_threshold=0.25,
                device="cuda:0",
                imgsz=640,
                quantize=16,
                nms=False,
                fallback_enabled=True,
            )
        )
        src_ent = MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=10.0)
        src_sal = MobilePushFrameBuffer("CAM-SALIDA", ttl_seconds=10.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            coord = VisionEngineCoordinator(
                topology_validator=TopologyValidator(repository=_FakeTopologyRepo()),
                settings=VisionEngineSettings(
                    vehicle_confidence_threshold=0.70,
                    evidence_directory=Path(tmpdir),
                ),
                detector=det,
                sources={"CAM-ENTRADA": src_ent, "CAM-SALIDA": src_sal},
            )
            coord.initialize(open_sources=True)
            try:
                for p in cases:
                    frame = cv2.imread(str(p))
                    self.assertIsNotNone(frame)
                    src_sal.push_frame(frame)
                    env = coord.process_camera_step("CAM-SALIDA")
                    self.assertIsNotNone(env)
                    self.assertEqual(
                        env.vision_result.status,
                        VisionStatus.VEHICLE_DETECTED_NO_PLATE,
                        msg=f"Falló recuperación frontal en {p.name}",
                    )
                    self.assertTrue(env.vision_result.vehicle_detected)
                    self.assertGreaterEqual(env.vision_result.vehicle_confidence or 0.0, 0.70)

                status = det.get_runtime_status()
                self.assertGreaterEqual(status["inference_metrics"]["frontal_aux_triggers"], 2)
                self.assertGreaterEqual(status["inference_metrics"]["frontal_aux_recoveries"], 2)
                self.assertGreaterEqual(status["inference_metrics"]["duplicates_suppressed"], 3)
            finally:
                coord.shutdown()

    def test_multi_vehicle_same_frame_adjacent_and_partially_overlapping_preserved(self) -> None:
        # 1. Dos automóviles en carriles contiguos (IoU = 0.25 < 0.55) -> ambos preservados
        car_left = BoundingBox(50, 200, 250, 400)
        car_right = BoundingBox(170, 200, 370, 400)
        self.assertLess(compute_bbox_iou(car_left, car_right), 0.55)

        # 2. Un automóvil parcialmente superpuesto delante de un autobús (0.55 <= IoU = 0.72 < 0.75) -> NO suprimir
        bus_back = BoundingBox(100, 100, 300, 300)
        car_front = BoundingBox(120, 140, 300, 300)
        iou_car_bus = compute_bbox_iou(bus_back, car_front)
        self.assertGreaterEqual(iou_car_bus, 0.55)
        self.assertLess(iou_car_bus, 0.75)

        # 3. Una motocicleta delante de un automóvil (0.75 <= IoU = 0.81 < 0.85) -> NO suprimir motocicleta
        car_host = BoundingBox(380, 100, 580, 300)
        moto_front = BoundingBox(395, 115, 575, 295)
        iou_moto_car = compute_bbox_iou(car_host, moto_front)
        self.assertGreaterEqual(iou_moto_car, 0.75)
        self.assertLess(iou_moto_car, 0.85)

        # 4. Duplicado real one2one del mismo automóvil car_left (IoU > 0.90) -> consolidado en 1 sola caja
        car_left_dup = BoundingBox(52, 202, 248, 398)
        self.assertGreater(compute_bbox_iou(car_left, car_left_dup), 0.90)

        detections = (
            RawVehicleDetection(bbox=bus_back, confidence=0.88, raw_label="bus"),
            RawVehicleDetection(bbox=car_front, confidence=0.82, raw_label="car"),
            RawVehicleDetection(bbox=car_host, confidence=0.90, raw_label="car"),
            RawVehicleDetection(bbox=moto_front, confidence=0.79, raw_label="motorcycle"),
            RawVehicleDetection(bbox=car_left, confidence=0.58, raw_label="car"),
            RawVehicleDetection(bbox=car_left_dup, confidence=0.52, raw_label="car"),
            RawVehicleDetection(bbox=car_right, confidence=0.85, raw_label="car"),
        )
        dedup, suppressed = deduplicate_and_consolidate_detections(
            detections,
            iou_threshold=0.55,
            consolidate_split_confidence=True,
        )
        # De 7 predicciones (6 vehículos reales + 1 duplicado), debe suprimir exactamente 1 y conservar 6 vehículos
        self.assertEqual(suppressed, 1)
        self.assertEqual(len(dedup), 6)
        labels = [d.raw_label for d in dedup]
        self.assertEqual(labels.count("bus"), 1)
        self.assertEqual(labels.count("motorcycle"), 1)
        self.assertEqual(labels.count("car"), 4)
        # El automóvil car_left consolidado superó el umbral de 0.70 (1 - (1-0.58)*(1-0.65*0.52) = 0.722)
        consolidated_car_left = [d for d in dedup if d.bbox == car_left][0]
        self.assertGreaterEqual(consolidated_car_left.confidence, 0.70)

    def test_multi_camera_concurrent_isolation_usb_and_mobile(self) -> None:
        class _FakeUsbPullSource:
            def __init__(self, frame_factory) -> None:
                self._frame_factory = frame_factory
                self._opened = False
                self._seq = 0

            def open(self) -> bool:
                self._opened = True
                return True

            def is_opened(self) -> bool:
                return self._opened

            def release(self) -> None:
                self._opened = False

            def close(self) -> None:
                self.release()

            def read_frame(self) -> CaptureReadResult:
                self._seq += 1
                return CaptureReadResult(
                    ok=True,
                    frame=self._frame_factory(self._seq),
                    captured_at=datetime.now(timezone.utc),
                    frame_sequence=self._seq,
                )

        # Codificamos la firma del frame en el canal azul: CAM-ENTRADA (movil)=10, CAM-SALIDA (usb)=20
        class _SignatureMultiscaleMock:
            supports_multiscale_aux = True

            def __init__(self) -> None:
                self.end2end = True

            def predict(self, **kwargs: Any) -> List[_MockResult]:
                frame = kwargs["source"]
                sig = int(frame[0, 0, 0])
                sz = int(kwargs.get("imgsz", 640))
                if sig == 10:  # Móvil PUSH (CAM-ENTRADA): autobús frontal claro en 640
                    return [_MockResult([_MockBox([200, 160, 420, 320], 0.91, 5)])]
                # USB Pull (CAM-SALIDA): automóvil frontal recuperado en 384 (fallo en 640)
                if sz == 384:
                    return [_MockResult([_MockBox([220, 150, 430, 330], 0.84, 2)])]
                return [_MockResult([])]

        class _DualTopologyRepo(_FakeTopologyRepo):
            def get_cameras(self):
                cams = super().get_cameras()
                cams[1] = CameraConfigDTO(
                    id_camara=self.cam_sal_id,
                    codigo="CAM-SALIDA",
                    nombre="Salida USB",
                    uri_stream="usb://0",
                    activa=True,
                )
                return cams

        src_mobile = MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=10.0)
        src_usb = _FakeUsbPullSource(lambda _seq: np.full((480, 640, 3), 20, dtype=np.uint8))

        det = YoloVehicleDetector(
            config=YoloDetectorConfig(
                model_path="yolo26x.pt",
                device="cpu",
                imgsz=640,
                quantize=16,
                nms=False,
                frontal_aux_enabled=True,
                frontal_aux_imgsz=384,
                frontal_aux_trigger_confidence=0.70,
            ),
            model_factory=lambda _p: _SignatureMultiscaleMock(),
        )

        results_ent = []
        results_sal = []
        errors = []

        with tempfile.TemporaryDirectory() as tmpdir:
            coord = VisionEngineCoordinator(
                topology_validator=TopologyValidator(repository=_DualTopologyRepo()),
                settings=VisionEngineSettings(
                    vehicle_confidence_threshold=0.70,
                    evidence_directory=Path(tmpdir),
                ),
                detector=det,
                sources={"CAM-ENTRADA": src_mobile, "CAM-SALIDA": src_usb},
            )
            coord.initialize(open_sources=True)
            try:
                frame_mobile = np.full((480, 640, 3), 10, dtype=np.uint8)

                def _worker_mobile() -> None:
                    try:
                        for _ in range(15):
                            src_mobile.push_frame(frame_mobile)
                            env = coord.process_camera_step("CAM-ENTRADA")
                            if env is not None:
                                results_ent.append(env)
                    except Exception as exc:
                        errors.append(exc)

                def _worker_usb() -> None:
                    try:
                        for _ in range(15):
                            env = coord.process_camera_step("CAM-SALIDA")
                            if env is not None:
                                results_sal.append(env)
                    except Exception as exc:
                        errors.append(exc)

                t1 = threading.Thread(target=_worker_mobile)
                t2 = threading.Thread(target=_worker_usb)
                t1.start()
                t2.start()
                t1.join(timeout=10.0)
                t2.join(timeout=10.0)

                self.assertEqual(errors, [])
                self.assertEqual(len(results_ent), 15)
                self.assertEqual(len(results_sal), 15)
                self.assertTrue(all(r.codigo_camara == "CAM-ENTRADA" and r.vision_result.vehicle_type_pred == "AUTOBUS" for r in results_ent))
                self.assertTrue(all(r.codigo_camara == "CAM-SALIDA" and r.vision_result.vehicle_type_pred == "AUTOMOVIL" for r in results_sal))

                status = det.get_runtime_status()
                self.assertEqual(status["inference_metrics"]["frontal_aux_triggers"], 15)
                self.assertEqual(status["inference_metrics"]["frontal_aux_recoveries"], 15)
            finally:
                coord.shutdown()

    def test_real_multi_vehicle_evidence_frames_gpu(self) -> None:
        yolo26_path = resolve_yolo_weights_path("experiments/yolo26x/weights/yolo26x.pt")
        repo_root = Path(__file__).resolve().parents[2]
        ev_dir = repo_root / "evidencias_vigia"
        if not yolo26_path.is_file() or not ev_dir.is_dir():
            self.skipTest("Pesos yolo26x.pt o evidencias_vigia no disponibles")
        try:
            import torch

            if not torch.cuda.is_available():
                self.skipTest("CUDA no disponible en este intérprete Python")
        except Exception:
            self.skipTest("PyTorch CUDA no disponible")

        multi_cases = [
            ev_dir / "20261114/CAM-SALIDA/20261114T010037_321148Z_29a0e74bbe1e_orig.jpg",  # EV-0581: bus + car
            ev_dir / "20261116/CAM-SALIDA/20261116T171957_156573Z_06fd6441d05f_orig.jpg",  # EV-0605: 2 carros frontales
            ev_dir / "20261116/CAM-SALIDA/20261116T172203_520604Z_e0c6c9b2989f_orig.jpg",  # EV-0671: bus frontal + car oblicuo
        ]
        for p in multi_cases:
            if not p.is_file():
                self.skipTest(f"Evidencia multi-vehículo no encontrada: {p}")

        det = YoloVehicleDetector(
            config=YoloDetectorConfig(
                model_path=str(yolo26_path),
                confidence_threshold=0.25,
                device="cuda:0",
                imgsz=640,
                quantize=16,
                nms=False,
                fallback_enabled=True,
            )
        )
        try:
            for p in multi_cases:
                frame = cv2.imread(str(p))
                self.assertIsNotNone(frame)
                dets = det.detect(frame, camera_code="CAM-MULTI-AUDIT")
                self.assertGreaterEqual(
                    len(dets),
                    2,
                    msg=f"Se esperaban >=2 vehículos en {p.name}, obtenidos: {dets}",
                )
                for i in range(len(dets)):
                    for j in range(i + 1, len(dets)):
                        iou_ij = compute_bbox_iou(dets[i].bbox, dets[j].bbox)
                        if dets[i].raw_label == dets[j].raw_label:
                            self.assertLess(iou_ij, 0.55)
                        else:
                            self.assertLess(iou_ij, 0.75)
        finally:
            det.close()


if __name__ == "__main__":
    unittest.main()
