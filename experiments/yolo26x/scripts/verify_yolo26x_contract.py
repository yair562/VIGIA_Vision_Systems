"""
Paso 3 (VISION-03C.1): Verificacion exhaustiva de inferencia de YOLO26x y
compatibilidad estricta con el contrato productivo de VIGIA Vision Systems.

Comprueba sobre ``yolo26x.pt`` (sin modificar codigo productivo):
1. Inicializacion del modelo y verificacion de ``end2end=True`` (NMS-Free).
2. Inferencia sobre imagenes JPEG reales (640x480 y 720x1280) y tensores
   sinteticos multiresolucion (1280x720, 1920x1080).
3. Ejecucion en CUDA con FP32 (``half=False``) y FP16 (``half=True``).
4. Emision de ``xyxy``, ``cls`` y ``conf``, y verificacion de las 4 clases COCO
   (``car=2``, ``motorcycle=3``, ``bus=5``, ``truck=7``).
5. Compatibilidad integral con ``YoloVehicleDetector``, ``filter_detections_by_roi``,
   ``map_raw_label_to_domain_vehicle_type``, ``VisionResult`` y ``CameraTemporalStateTracker``.
6. Comparativa entre ``end2end=True`` (cabezal one2one NMS-Free) vs ``end2end=False``
   (cabezal one2many + NMS tradicional IoU=0.45) y entre FP32 vs FP16.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

import cv2
import numpy as np
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
from VIGIA_Vision.runtime.temporal_state import CameraTemporalStateTracker, TemporalStateConfig


def _summarize_boxes(res: Any) -> List[Dict[str, Any]]:
    out = []
    boxes = getattr(res, "boxes", None)
    if boxes is None:
        return out
    for b in boxes:
        cid = int(b.cls[0].item())
        conf = float(b.conf[0].item())
        x1, y1, x2, y2 = [round(float(v), 2) for v in b.xyxy[0].tolist()]
        out.append(
            {
                "cls_id": cid,
                "label": COCO_VEHICLE_CLASSES.get(cid, str(res.names.get(cid, cid))),
                "conf": round(conf, 4),
                "xyxy": [x1, y1, x2, y2],
            }
        )
    return out


def main() -> None:
    weights_path = EXP_ROOT / "weights" / "yolo26x.pt"
    if not weights_path.is_file():
        raise FileNotFoundError(f"Falta {weights_path}. Ejecute prepare_weights.py primero.")

    # Seleccionar imagenes JPEG reales de las dos resoluciones disponibles (720x1280 y 640x480)
    ev_20261114 = REPO_ROOT / "evidencias_vigia" / "20261114"
    sample_720 = sorted((ev_20261114 / "CAM-ENTRADA").glob("*_orig.jpg"))[-1]
    sample_640 = sorted((ev_20261114 / "CAM-SALIDA").glob("*_orig.jpg"))[-1]

    img_720 = cv2.imread(str(sample_720))
    img_640 = cv2.imread(str(sample_640))
    if img_720 is None or img_640 is None:
        raise RuntimeError("No se pudieron leer imagenes JPEG reales de muestra.")

    # 1. Prueba directa Ultralytics CUDA: comportamiento real de end2end / nms en Ultralytics 8.4.171
    model_raw = YOLO(str(weights_path))
    head_raw = model_raw.model.model[-1]
    unfused_load_state = {
        "ckpt_yaml_end2end": bool(getattr(model_raw.model, "yaml", {}).get("end2end", False)),
        "head_end2end_on_load": bool(getattr(head_raw, "end2end", False)),
        "head_reg_max": int(getattr(head_raw, "reg_max", -1)),
        "head_has_one2one": getattr(head_raw, "one2one_cv2", None) is not None,
    }

    # Con nms=False -> AutoBackend fusiona conservando exclusivamente la rama one2one (NMS-Free real)
    model_e2e_fp32 = YOLO(str(weights_path))
    model_e2e_fp16 = YOLO(str(weights_path))

    resolution_checks = []
    inputs = [
        ("real_jpeg_640x480", img_640),
        ("real_jpeg_720x1280", img_720),
        ("synthetic_1280x720", cv2.resize(img_640, (1280, 720))),
        ("synthetic_1920x1080", cv2.resize(img_640, (1920, 1080))),
    ]
    for label, frame in inputs:
        h, w = frame.shape[:2]
        r_fp32 = model_e2e_fp32.predict(
            frame, conf=0.25, iou=0.45, classes=[2, 3, 5, 7], imgsz=640, device="cuda:0", nms=False, verbose=False
        )[0]
        r_fp16 = model_e2e_fp16.predict(
            frame, conf=0.25, iou=0.45, classes=[2, 3, 5, 7], imgsz=640, device="cuda:0", quantize=16, nms=False, verbose=False
        )[0]
        resolution_checks.append(
            {
                "input_name": label,
                "shape_hw": [h, w],
                "fp32_end2end_active": bool(model_e2e_fp32.predictor.model.end2end),
                "fp16_end2end_active": bool(model_e2e_fp16.predictor.model.end2end),
                "fp16_param_dtype": str(next(model_e2e_fp16.predictor.model.model.parameters()).dtype),
                "fp32_boxes": _summarize_boxes(r_fp32),
                "fp16_boxes": _summarize_boxes(r_fp16),
            }
        )

    # Comparativa limpia (instancias aisladas): nms=False (one2one NMS-Free) vs nms=True (one2many + NMS)
    model_nms_fp32 = YOLO(str(weights_path))
    model_default_fp32 = YOLO(str(weights_path))
    _ = model_default_fp32.predict(img_640, conf=0.25, classes=[2, 3, 5, 7], imgsz=640, device="cuda:0", verbose=False)
    default_predict_end2end_active = bool(model_default_fp32.predictor.model.end2end)

    sample_batch_paths = (
        sorted((ev_20261114 / "CAM-ENTRADA").glob("*_orig.jpg"))[:5]
        + sorted((ev_20261114 / "CAM-SALIDA").glob("*_orig.jpg"))[-10:]
    )
    e2e_diffs = []
    for sp in sample_batch_paths:
        fr = cv2.imread(str(sp))
        b_e2e = _summarize_boxes(
            model_e2e_fp32.predict(
                fr, conf=0.25, classes=[2, 3, 5, 7], imgsz=640, device="cuda:0", nms=False, verbose=False
            )[0]
        )
        b_nms = _summarize_boxes(
            model_nms_fp32.predict(
                fr, conf=0.25, iou=0.45, classes=[2, 3, 5, 7], imgsz=640, device="cuda:0", nms=True, verbose=False
            )[0]
        )
        e2e_diffs.append(
            {
                "file": sp.name,
                "end2end_count": len(b_e2e),
                "nms_count": len(b_nms),
                "end2end_boxes": b_e2e,
                "nms_boxes": b_nms,
            }
        )

    ab_e2e_head = model_e2e_fp32.predictor.model.model.model[-1]
    ab_nms_head = model_nms_fp32.predictor.model.model.model[-1]
    ab_def_head = model_default_fp32.predictor.model.model.model[-1]
    predictor_branch_audit = {
        "nms_false_mode": {
            "autobackend_end2end": bool(model_e2e_fp32.predictor.model.end2end),
            "cv2_pruned_is_none": ab_e2e_head.cv2 is None,
            "one2one_cv2_present": ab_e2e_head.one2one_cv2 is not None,
        },
        "nms_true_mode": {
            "autobackend_end2end": bool(model_nms_fp32.predictor.model.end2end),
            "cv2_present": ab_nms_head.cv2 is not None,
            "one2one_pruned_is_none": ab_nms_head.one2one_cv2 is None,
        },
        "default_nms_none_mode": {
            "autobackend_end2end": default_predict_end2end_active,
            "cv2_present": ab_def_head.cv2 is not None,
            "one2one_pruned_is_none": ab_def_head.one2one_cv2 is None,
        },
    }

    # 2. Verificacion directa del contrato VIGIA actual sin modificar produccion
    detector = YoloVehicleDetector(
        config=YoloDetectorConfig(
            model_path=str(weights_path),
            confidence_threshold=0.25,
            device="cuda:0",
            imgsz=640,
            iou_threshold=0.45,
            classes=(2, 3, 5, 7),
        )
    )
    fw, fh = validate_bgr_frame(img_640)
    raw_dets = detector.detect(img_640)
    area = AreaConfigDTO(
        id_area_vision=uuid4(),
        id_camara=uuid4(),
        codigo="AREA-SALIDA",
        nombre="Area Experimental Salida",
        tipo_movimiento="SALIDA",
        x_min=0.10,
        y_min=0.15,
        x_max=0.90,
        y_max=0.95,
        activa=True,
    )
    pixel_roi = project_normalized_roi(area, fw, fh)
    in_roi, excluded = filter_detections_by_roi(raw_dets, pixel_roi, min_confidence=0.70)

    primary = in_roi[0] if in_roi else (raw_dets[0] if raw_dets else None)
    domain_type = map_raw_label_to_domain_vehicle_type(primary.raw_label) if primary else None
    vision_res = VisionResult(
        status=VisionStatus.VEHICLE_DETECTED_NO_PLATE if primary else VisionStatus.NO_VEHICLE_DETECTED,
        timestamp=datetime.now(timezone.utc),
        vehicle_detected=bool(primary),
        vehicle_confidence=primary.confidence if primary else None,
        vehicle_type_pred=domain_type,
    )

    tracker = CameraTemporalStateTracker(
        config=TemporalStateConfig(min_confirm_frames=2, max_missed_frames=3),
    )
    fsm_snap = tracker.update(
        camera_id="CAM-SALIDA",
        roi_vehicle_detected=bool(in_roi),
        raw_vehicle_detected=bool(raw_dets),
        frame_sequence=1,
        vehicle_type=domain_type,
        vehicle_confidence=primary.confidence if primary else None,
    )

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "cuda_available": torch.cuda.is_available(),
        "device_name": torch.cuda.get_device_name(0),
        "unfused_load_state": unfused_load_state,
        "predictor_branch_audit": predictor_branch_audit,
        "coco_vehicle_classes_in_weights": {k: model_raw.names.get(k) for k in COCO_VEHICLE_CLASSES},
        "multiresolution_fp32_vs_fp16": resolution_checks,
        "end2end_vs_traditional_nms_sample": e2e_diffs,
        "vigia_contract_integration_smoke": {
            "raw_detections_count": len(raw_dets),
            "in_roi_count": len(in_roi),
            "excluded_outside_roi": excluded,
            "all_raw_are_RawVehicleDetection": all(isinstance(d, RawVehicleDetection) for d in raw_dets),
            "all_bboxes_are_BoundingBox": all(isinstance(d.bbox, BoundingBox) for d in raw_dets),
            "mapped_domain_type": domain_type,
            "vision_result_status": vision_res.status.value,
            "fsm_state_after_1_frame": fsm_snap.detection_status.value,
            "yolo_detector_default_end2end_active": bool(
                getattr(getattr(getattr(detector._model, "predictor", None), "model", None), "end2end", False)
            ),
        },
    }

    out_path = EXP_ROOT / "results" / "contract_verification.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["vigia_contract_integration_smoke"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
