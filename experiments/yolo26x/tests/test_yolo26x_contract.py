"""
Pruebas unitarias aisladas del contrato de inferencia YOLO26x (VISION-03C.1).

Verifica sin modificar codigo de produccion:
1. Carga CUDA de weights/yolo26x.pt y activacion explicita de end2end=True via nms=False.
2. Comportamiento de poda de ramas en Detect.fuse() segun nms=False vs nms=True / default.
3. Inferencia FP32 y FP16 (quantize=16) con clases COCO vehiculares {2, 3, 5, 7}.
4. Compatibilidad end-to-end con YoloVehicleDetector, filter_detections_by_roi,
   map_raw_label_to_domain_vehicle_type, VisionResult y CameraTemporalStateTracker.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2
import torch
from ultralytics import YOLO

EXP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = EXP_ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from VIGIA_Core.domain.vision_result import VisionResult, VisionStatus
from VIGIA_Vision.config.topology_validator import AreaConfigDTO
from VIGIA_Vision.detection.models import BoundingBox, RawVehicleDetection
from VIGIA_Vision.detection.roi_and_preprocess import (
    filter_detections_by_roi,
    project_normalized_roi,
    validate_bgr_frame,
)
from VIGIA_Vision.detection.yolo_detector import (
    COCO_VEHICLE_CLASSES,
    YoloDetectorConfig,
    YoloVehicleDetector,
)
from VIGIA_Vision.runtime.coordinator import map_raw_label_to_domain_vehicle_type
from VIGIA_Vision.runtime.temporal_state import (
    CameraTemporalStateTracker,
    TemporalDetectionStatus,
    TemporalStateConfig,
)


class TestYolo26xContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.weights_path = EXP_ROOT / "weights" / "yolo26x.pt"
        if not cls.weights_path.is_file():
            raise unittest.SkipTest(f"Peso experimental ausente: {cls.weights_path}")
        if not torch.cuda.is_available():
            raise unittest.SkipTest("CUDA no disponible para pruebas GPU.")

        ev_dir = REPO_ROOT / "evidencias_vigia" / "20261114"
        cls.sample_640_path = sorted((ev_dir / "CAM-SALIDA").glob("*_orig.jpg"))[-1]
        cls.sample_720_path = sorted((ev_dir / "CAM-ENTRADA").glob("*_orig.jpg"))[-1]
        cls.img_640 = cv2.imread(str(cls.sample_640_path))
        cls.img_720 = cv2.imread(str(cls.sample_720_path))
        if cls.img_640 is None or cls.img_720 is None:
            raise unittest.SkipTest("No se pudieron cargar imagenes de muestra reales.")

    def test_nms_false_enables_true_end2end_one2one_head(self) -> None:
        model_e2e = YOLO(str(self.weights_path))
        res = model_e2e.predict(
            self.img_640,
            conf=0.25,
            classes=list(COCO_VEHICLE_CLASSES.keys()),
            imgsz=640,
            device="cuda:0",
            quantize=16,
            nms=False,
            verbose=False,
        )[0]
        ab = model_e2e.predictor.model
        head = ab.model.model[-1]
        self.assertTrue(bool(ab.end2end))
        self.assertTrue(bool(ab.fp16))
        self.assertIsNone(head.cv2)
        self.assertIsNotNone(head.one2one_cv2)
        self.assertGreaterEqual(len(res.boxes), 1)
        for box in res.boxes:
            cls_id = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            self.assertIn(cls_id, COCO_VEHICLE_CLASSES)
            self.assertGreaterEqual(conf, 0.25)
            self.assertLessEqual(conf, 1.0)

    def test_default_predict_without_nms_false_prunes_one2one_head(self) -> None:
        model_default = YOLO(str(self.weights_path))
        model_default.predict(
            self.img_640,
            conf=0.25,
            classes=list(COCO_VEHICLE_CLASSES.keys()),
            imgsz=640,
            device="cuda:0",
            verbose=False,
        )
        ab = model_default.predictor.model
        head = ab.model.model[-1]
        self.assertFalse(bool(ab.end2end))
        self.assertIsNotNone(head.cv2)
        self.assertIsNone(head.one2one_cv2)

    def test_fp32_and_fp16_inference_across_vigia_resolutions(self) -> None:
        model_fp32 = YOLO(str(self.weights_path))
        model_fp16 = YOLO(str(self.weights_path))
        for frame in (self.img_640, self.img_720):
            r32 = model_fp32.predict(
                frame,
                conf=0.25,
                classes=list(COCO_VEHICLE_CLASSES.keys()),
                imgsz=640,
                device="cuda:0",
                nms=False,
                verbose=False,
            )[0]
            r16 = model_fp16.predict(
                frame,
                conf=0.25,
                classes=list(COCO_VEHICLE_CLASSES.keys()),
                imgsz=640,
                device="cuda:0",
                quantize=16,
                nms=False,
                verbose=False,
            )[0]
            self.assertEqual(r32.orig_shape, frame.shape[:2])
            self.assertEqual(r16.orig_shape, frame.shape[:2])
            for box in r16.boxes:
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
                self.assertLess(x1, x2)
                self.assertLess(y1, y2)

    def test_vigia_production_pipeline_contracts_without_code_changes(self) -> None:
        detector = YoloVehicleDetector(
            config=YoloDetectorConfig(
                model_path=str(self.weights_path),
                confidence_threshold=0.25,
                device="cuda:0",
                imgsz=640,
                iou_threshold=0.45,
                classes=tuple(COCO_VEHICLE_CLASSES.keys()),
            )
        )
        fw, fh = validate_bgr_frame(self.img_640)
        raw_dets = detector.detect(self.img_640)
        self.assertGreaterEqual(len(raw_dets), 1)
        for det in raw_dets:
            self.assertIsInstance(det, RawVehicleDetection)
            self.assertIsInstance(det.bbox, BoundingBox)
            self.assertIn(det.raw_label, ("car", "motorcycle", "bus", "truck"))

        area = AreaConfigDTO(
            id_area_vision=uuid4(),
            id_camara=uuid4(),
            codigo="AREA-SALIDA",
            nombre="Area Experimental Salida",
            tipo_movimiento="SALIDA",
            x_min=0.05,
            y_min=0.05,
            x_max=0.95,
            y_max=0.95,
            activa=True,
        )
        roi = project_normalized_roi(area, fw, fh)
        in_roi, excluded = filter_detections_by_roi(raw_dets, roi, min_confidence=0.25)
        self.assertGreaterEqual(len(in_roi) + excluded, 1)

        primary = in_roi[0] if in_roi else raw_dets[0]
        domain_type = map_raw_label_to_domain_vehicle_type(primary.raw_label)
        self.assertIn(domain_type, ("AUTOMOVIL", "MOTOCICLETA", "AUTOBUS", "CAMION"))

        res = VisionResult(
            status=VisionStatus.VEHICLE_DETECTED_NO_PLATE,
            timestamp=datetime.now(timezone.utc),
            vehicle_detected=True,
            vehicle_confidence=primary.confidence,
            vehicle_type_pred=domain_type,
        )
        self.assertTrue(res.vehicle_detected)

        tracker = CameraTemporalStateTracker(
            config=TemporalStateConfig(min_confirm_frames=2, max_missed_frames=3),
        )
        s1 = tracker.update(
            camera_id="CAM-SALIDA",
            roi_vehicle_detected=True,
            raw_vehicle_detected=True,
            frame_sequence=1,
            vehicle_type=domain_type,
            vehicle_confidence=primary.confidence,
            now_monotonic=10.0,
        )
        s2 = tracker.update(
            camera_id="CAM-SALIDA",
            roi_vehicle_detected=True,
            raw_vehicle_detected=True,
            frame_sequence=2,
            vehicle_type=domain_type,
            vehicle_confidence=primary.confidence,
            now_monotonic=10.1,
        )
        self.assertEqual(s1.detection_status, TemporalDetectionStatus.VEHICLE_CANDIDATE)
        self.assertEqual(s2.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)


if __name__ == "__main__":
    unittest.main()
