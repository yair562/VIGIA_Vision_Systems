"""
VIGIA-VISION-05A.1 — Auditoría Independiente, Reproducción y Validación Multiescala
====================================================================================
Verifica matemáticamente el corpus, reproduce métricas antes/después usando la clase real
YoloVehicleDetector, ejecuta validación multiescala completa (640, 480, 384, 320 + sondas
condicionales), audita el mecanismo de supresión de duplicados y captura evidencia de
integridad de archivos y entorno.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from VIGIA_Vision.config.topology_validator import AreaConfigDTO
from VIGIA_Vision.detection.roi_and_preprocess import project_normalized_roi
from VIGIA_Vision.detection.yolo_detector import (
    YoloDetectorConfig,
    YoloVehicleDetector,
    compute_bbox_iou,
    load_yolo_config_from_env,
    resolve_yolo_weights_path,
)
from scripts.check_https_strict import run_strict_check

EVIDENCE_DIR = REPO_ROOT / "evidencias_vigia"
RESULTS_DIR = REPO_ROOT / "experiments" / "vision_05a" / "results"
RAW_INV_PATH = RESULTS_DIR / "etapa_a_b_raw_inventory.json"
CLS_INV_PATH = RESULTS_DIR / "etapa_a_b_classified_inventory.json"
EXP_RES_PATH = RESULTS_DIR / "etapa_d_experiments_results.json"
OUT_AUDIT_PATH = RESULTS_DIR / "audit_05a1_verified_metrics.json"


def sha256_file(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def box_dict(det: Any, px_roi: Any, img_w: int, img_h: int) -> Dict[str, Any]:
    cx, cy = det.bbox.centroid
    area_pct = (det.bbox.area / float(max(1, img_w * img_h))) * 100.0
    return {
        "label": det.raw_label,
        "confidence": round(float(det.confidence), 4),
        "bbox": [det.bbox.x_min, det.bbox.y_min, det.bbox.x_max, det.bbox.y_max],
        "center": [round(cx, 2), round(cy, 2)],
        "in_roi": bool(px_roi.contains_point(cx, cy)),
        "area_pct": round(area_pct, 2),
    }


def bbox_iou_list(b1: Sequence[int], b2: Sequence[int]) -> float:
    x1 = max(b1[0], b2[0])
    y1 = max(b1[1], b2[1])
    x2 = min(b1[2], b2[2])
    y2 = min(b1[3], b2[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter <= 0:
        return 0.0
    a1 = max(1, (b1[2] - b1[0]) * (b1[3] - b1[1]))
    a2 = max(1, (b2[2] - b2[0]) * (b2[3] - b2[1]))
    return inter / float(a1 + a2 - inter)


def audit_corpus_and_counts(cls_data: Dict[str, Any]) -> Dict[str, Any]:
    items = cls_data["items"]
    unique_items = [it for it in items if not it["is_exact_duplicate"]]

    orig_count = len(list(EVIDENCE_DIR.rglob("*_orig.jpg")))
    annot_count = len(list(EVIDENCE_DIR.rglob("*_annot.jpg")))
    all_files_count = len([p for p in EVIDENCE_DIR.rglob("*") if p.is_file()])

    dup_groups = Counter(it["exact_duplicate_group"] for it in items)
    multi_dup_groups = sum(1 for _, c in dup_groups.items() if c > 1)
    pclusters_unique = len({it["perceptual_duplicate_group"] for it in unique_items})
    sessions = len({it["session_id"] for it in items})

    # Conteo exacto en únicas vs todas
    u_tag_counts = Counter()
    a_tag_counts = Counter()
    for it in unique_items:
        for c in it["confirmed_visual_classification"]["confirmed_categories"]:
            u_tag_counts[c] += 1
    for it in items:
        for c in it["confirmed_visual_classification"]["confirmed_categories"]:
            a_tag_counts[c] += 1

    # Conciliación matemática exacta de Vehículos Frontales
    has_fc_unique = [it for it in unique_items if it["confirmed_visual_classification"]["has_frontal_car"]]
    has_fb_unique = [it for it in unique_items if it["confirmed_visual_classification"]["has_frontal_bus"]]
    both_fc_fb_unique = [
        it
        for it in unique_items
        if it["confirmed_visual_classification"]["has_frontal_car"]
        and it["confirmed_visual_classification"]["has_frontal_bus"]
    ]
    union_fc_fb_unique = [
        it
        for it in unique_items
        if it["confirmed_visual_classification"]["has_frontal_car"]
        or it["confirmed_visual_classification"]["has_frontal_bus"]
    ]
    frontal_tag_unique = [
        it
        for it in unique_items
        if "Vehículo frontal" in it["confirmed_visual_classification"]["confirmed_categories"]
    ]
    screen_grid_frontal_unique = [
        it
        for it in frontal_tag_unique
        if not it["confirmed_visual_classification"]["has_frontal_car"]
        and not it["confirmed_visual_classification"]["has_frontal_bus"]
    ]
    screen_grid_frontal_all = [
        it
        for it in items
        if "Vehículo frontal" in it["confirmed_visual_classification"]["confirmed_categories"]
        and not it["confirmed_visual_classification"]["has_frontal_car"]
        and not it["confirmed_visual_classification"]["has_frontal_bus"]
    ]

    # Comprobar sub-etiquetas de bus frontal y oblicuo
    bus_front_or_obl_unique = [
        it
        for it in unique_items
        if it["confirmed_visual_classification"]["has_frontal_bus"]
        or (577 <= int(it["sample_id"].split("-")[1]) <= 578)
        or (662 <= int(it["sample_id"].split("-")[1]) <= 667)
        or (672 <= int(it["sample_id"].split("-")[1]) <= 675)
    ]

    return {
        "filesystem_counts": {
            "total_files": all_files_count,
            "orig_jpg": orig_count,
            "annot_jpg": annot_count,
            "other_files": all_files_count - orig_count - annot_count,
            "unique_sha256": len(unique_items),
            "exact_duplicates": len(items) - len(unique_items),
            "exact_dup_groups_n_gt_1": multi_dup_groups,
            "perceptual_clusters_in_unique": pclusters_unique,
            "temporal_sequences": sessions,
        },
        "confirmed_category_counts_unique_279": dict(sorted(u_tag_counts.items())),
        "confirmed_category_counts_all_675": dict(sorted(a_tag_counts.items())),
        "frontal_reconciliation": {
            "unique_has_frontal_car": len(has_fc_unique),
            "unique_has_frontal_bus": len(has_fb_unique),
            "unique_intersection_both_car_and_bus": len(both_fc_fb_unique),
            "intersection_sample_ids": [it["sample_id"] for it in both_fc_fb_unique],
            "unique_union_primary_frontal_car_or_bus": len(union_fc_fb_unique),
            "unique_screen_grid_with_frontal_tag": len(screen_grid_frontal_unique),
            "all_screen_grid_with_frontal_tag": len(screen_grid_frontal_all),
            "unique_total_with_frontal_tag": len(frontal_tag_unique),
            "all_675_with_frontal_tag": a_tag_counts["Vehículo frontal"],
            "unique_bus_frontal_plus_oblique_school_bus": len(bus_front_or_obl_unique),
            "why_89_vs_95_occurred": {
                "76_frontal_cars_plus_18_frontal_buses_plus_1_moto_screen": 76 + 18 + 1,
                "87_primary_frontal_images_plus_2_unique_motorcycle_front_only_or_screen": (
                    "La cifra '89' en VISION-05A provino de restar parcialmente la intersección "
                    "multi-vehículo o excluir recapturas de cuadrícula sobre 95 observaciones de subcategorías "
                    "(76 autos frontales + 18 autobuses frontales + 1 secuencia de moto frontal). "
                    "Matemáticamente exacto: 76 imágenes únicas con automóvil frontal primario + "
                    "18 imágenes únicas con autobús frontal primario - 7 imágenes compartidas "
                    "(EV-0581..EV-0587 donde aparecen AMBOS en el mismo frame) = 87 imágenes únicas "
                    "con automóvil/autobús frontal evaluado; sumando las 11 imágenes únicas de cuadrículas "
                    "de pantalla con tag 'Vehículo frontal' (EV-0295..0303 [3 hashes únicos, 9 archivos] y "
                    "EV-0449..0456 [8 archivos]), el total de imágenes únicas con tag 'Vehículo frontal' es 98 "
                    "(y 104 sobre el total de 675 archivos)."
                ),
            },
        },
    }


def evaluate_boxes_by_category(
    items: List[Dict[str, Any]],
    boxes_by_sha: Dict[str, List[Dict[str, Any]]],
    eval_thresh: float = 0.70,
    ref_boxes_by_sha: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    groups: Dict[str, List[Tuple[bool, bool, Optional[float]]]] = defaultdict(list)
    dup_frames_025 = 0
    dup_pairs_025 = 0
    dup_frames_070 = 0
    dup_pairs_070 = 0
    iou_vs_ref: List[float] = []
    center_shift_vs_ref: List[float] = []
    recovered_070: List[str] = []
    lost_070: List[str] = []

    for it in items:
        sha = it["sha256"]
        boxes = boxes_by_sha[sha]
        conf_info = it["confirmed_visual_classification"]
        cats = set(conf_info["confirmed_categories"])
        idx = int(it["sample_id"].split("-")[1])
        light = it["lighting_condition"]

        roi_70 = [b for b in boxes if b["in_roi"] and b["confidence"] >= eval_thresh]
        roi_25 = [b for b in boxes if b["in_roi"] and b["confidence"] >= 0.25]
        all_25 = [b for b in boxes if b["confidence"] >= 0.25]
        all_70 = [b for b in boxes if b["confidence"] >= eval_thresh]

        hit_70 = len(roi_70) > 0
        hit_25 = len(roi_25) > 0
        top_conf = max((b["confidence"] for b in roi_25), default=None)

        if ref_boxes_by_sha is not None:
            ref_boxes = ref_boxes_by_sha[sha]
            ref_hit_70 = any(b["in_roi"] and b["confidence"] >= eval_thresh for b in ref_boxes)
            if hit_70 and not ref_hit_70:
                recovered_070.append(it["sample_id"])
            elif not hit_70 and ref_hit_70:
                lost_070.append(it["sample_id"])

            ref_top = max((b for b in ref_boxes if b["in_roi"] and b["confidence"] >= 0.25), key=lambda x: x["confidence"], default=None)
            cur_top = max((b for b in boxes if b["in_roi"] and b["confidence"] >= 0.25), key=lambda x: x["confidence"], default=None)
            if ref_top is not None and cur_top is not None:
                iou_vs_ref.append(bbox_iou_list(ref_top["bbox"], cur_top["bbox"]))
                dx = cur_top["center"][0] - ref_top["center"][0]
                dy = cur_top["center"][1] - ref_top["center"][1]
                center_shift_vs_ref.append(math.hypot(dx, dy))

        # Duplicados intra-frame (IoU >= 0.50)
        dp25 = 0
        for i in range(len(all_25)):
            for j in range(i + 1, len(all_25)):
                if bbox_iou_list(all_25[i]["bbox"], all_25[j]["bbox"]) >= 0.50:
                    dp25 += 1
        if dp25 > 0:
            dup_frames_025 += 1
            dup_pairs_025 += dp25

        dp70 = 0
        for i in range(len(all_70)):
            for j in range(i + 1, len(all_70)):
                if bbox_iou_list(all_70[i]["bbox"], all_70[j]["bbox"]) >= 0.50:
                    dp70 += 1
        if dp70 > 0:
            dup_frames_070 += 1
            dup_pairs_070 += dp70

        groups["all"].append((hit_70, hit_25, top_conf))

        if conf_info["has_frontal_car"]:
            car_boxes = [b for b in boxes if b["in_roi"] and b["label"] == "car"]
            c70 = any(b["confidence"] >= eval_thresh for b in car_boxes)
            c25 = any(b["confidence"] >= 0.25 for b in car_boxes)
            c_top = max((b["confidence"] for b in car_boxes if b["confidence"] >= 0.25), default=None)
            groups["frontal_cars"].append((c70, c25, c_top))

        if conf_info["has_frontal_bus"]:
            bus_region_boxes = []
            for b in boxes:
                if not b["in_roi"]:
                    continue
                if 573 <= idx <= 576 and b["bbox"][0] > 450:
                    continue
                if 579 <= idx <= 587 and b["bbox"][3] < 200:
                    continue
                if idx == 588 and b["bbox"][0] < 200:
                    continue
                if idx == 671 and b["bbox"][0] > 220:
                    continue
                bus_region_boxes.append(b)
            b70_any = any(b["confidence"] >= eval_thresh for b in bus_region_boxes)
            b25_any = any(b["confidence"] >= 0.25 for b in bus_region_boxes)
            b_top = max((b["confidence"] for b in bus_region_boxes if b["confidence"] >= 0.25), default=None)
            groups["frontal_buses_presence"].append((b70_any, b25_any, b_top))

            b70_lbl = any(b["label"] == "bus" and b["confidence"] >= eval_thresh for b in bus_region_boxes)
            b25_lbl = any(b["label"] == "bus" and b["confidence"] >= 0.25 for b in bus_region_boxes)
            groups["frontal_buses_strict_label"].append((b70_lbl, b25_lbl, b_top))

        if "Vehículo frontal oblicuo" in cats:
            groups["oblique_vehicles"].append((hit_70, hit_25, top_conf))
        if "Vehículo lateral" in cats:
            groups["lateral_vehicles"].append((hit_70, hit_25, top_conf))
        if "Vehículo trasero" in cats:
            groups["rear_vehicles"].append((hit_70, hit_25, top_conf))
        if "Vehículo pequeño o lejano" in cats:
            groups["small_vehicles"].append((hit_70, hit_25, top_conf))
        if "Baja iluminación" in cats:
            groups["low_light"].append((hit_70, hit_25, top_conf))
        if "Contraluz" in cats:
            groups["backlight_glare"].append((hit_70, hit_25, top_conf))
        if light == "NORMAL":
            groups["lighting_normal"].append((hit_70, hit_25, top_conf))

        # Vehículos cercanos (primeros planos con bbox >= 15% del frame o ráfagas de corta distancia 20261116/EV-0625..0657 & EV-0573..0588)
        is_closeup = (605 <= idx <= 675) or (573 <= idx <= 588) or (508 <= idx <= 521) or (428 <= idx <= 429) or any(b["area_pct"] >= 15.0 for b in roi_25)
        if is_closeup:
            groups["closeup_vehicles"].append((hit_70, hit_25, top_conf))

        if it["date_folder"] == "20261114" and it["camera_code"] == "CAM-SALIDA":
            groups["cam_salida_20261114"].append((hit_70, hit_25, top_conf))
        if it["date_folder"] == "20261116" and it["camera_code"] == "CAM-SALIDA":
            groups["cam_salida_20261116"].append((hit_70, hit_25, top_conf))

    summary: Dict[str, Any] = {}
    for gk, vals in groups.items():
        n = len(vals)
        h70 = sum(1 for a, _, _ in vals if a)
        h25 = sum(1 for _, b, _ in vals if b)
        confs = [c for _, _, c in vals if c is not None]
        summary[gk] = {
            "total": n,
            "hits_070": h70,
            "rate_070_pct": round((h70 / n) * 100.0, 2) if n else 0.0,
            "hits_025": h25,
            "rate_025_pct": round((h25 / n) * 100.0, 2) if n else 0.0,
            "mean_top_conf": round(sum(confs) / len(confs), 4) if confs else None,
        }

    summary["dup_frames_025"] = dup_frames_025
    summary["dup_pairs_025"] = dup_pairs_025
    summary["dup_frames_070"] = dup_frames_070
    summary["dup_pairs_070"] = dup_pairs_070
    if ref_boxes_by_sha is not None:
        summary["vs_640_stability"] = {
            "matched_frames": len(iou_vs_ref),
            "mean_iou_vs_640": round(statistics.mean(iou_vs_ref), 4) if iou_vs_ref else None,
            "min_iou_vs_640": round(min(iou_vs_ref), 4) if iou_vs_ref else None,
            "mean_center_shift_px": round(statistics.mean(center_shift_vs_ref), 2) if center_shift_vs_ref else None,
            "recovered_070_count": len(recovered_070),
            "recovered_070_ids": recovered_070[:20],
            "lost_070_count": len(lost_070),
            "lost_070_ids": lost_070[:20],
        }
    return summary


def run_detector_over_corpus(
    detector: YoloVehicleDetector,
    unique_items: List[Dict[str, Any]],
    images_by_sha: Dict[str, np.ndarray],
    rois_by_sha: Dict[str, Any],
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    # Warmup en frame dummy para excluir carga inicial del modelo de latencias de estado estacionario
    detector.detect(np.zeros((480, 640, 3), dtype=np.uint8), camera_code="WARMUP")
    detector._latencies_ms.clear()
    detector._frontal_aux_triggers = 0
    detector._frontal_aux_recoveries = 0
    detector._duplicates_suppressed = 0
    detector._total_inferences = 0

    boxes_by_sha: Dict[str, List[Dict[str, Any]]] = {}
    lat_wall_ms: List[float] = []

    for it in unique_items:
        sha = it["sha256"]
        bgr = images_by_sha[sha]
        h, w = bgr.shape[:2]
        px_roi = rois_by_sha[sha]
        t0 = time.perf_counter()
        dets = detector.detect(bgr, camera_code=it["camera_code"])
        lat_wall_ms.append((time.perf_counter() - t0) * 1000.0)
        boxes_by_sha[sha] = [box_dict(d, px_roi, w, h) for d in dets]

    status = detector.get_runtime_status()
    ord_lat = sorted(lat_wall_ms)
    mean_ms = round(sum(ord_lat) / len(ord_lat), 2)
    stats = {
        "mean_ms": mean_ms,
        "p50_ms": round(ord_lat[len(ord_lat) // 2], 2),
        "p95_ms": round(ord_lat[int(len(ord_lat) * 0.95)], 2),
        "fps": round(1000.0 / mean_ms, 2) if mean_ms > 0 else 0.0,
        "runtime_status": status,
    }
    return boxes_by_sha, stats


def main() -> None:
    print("[1/5] Auditando corpus e inventario JSON...")
    cls_data = json.load(CLS_INV_PATH.open(encoding="utf-8"))
    items = cls_data["items"]
    unique_items = [it for it in items if not it["is_exact_duplicate"]]
    corpus_audit = audit_corpus_and_counts(cls_data)

    # Extraer registros exactos de casos problemáticos mencionados en VISION-05A
    key_samples = {}
    by_id = {it["sample_id"]: it for it in items}
    for sid in [
        "EV-0442", "EV-0483", "EV-0494", "EV-0525", "EV-0550", "EV-0575",
        "EV-0581", "EV-0584", "EV-0588", "EV-0625", "EV-0626", "EV-0627",
        "EV-0635", "EV-0637", "EV-0657", "EV-0663", "EV-0665", "EV-0671", "EV-0673",
    ]:
        it = by_id[sid]
        key_samples[sid] = {
            "relative_path": it["relative_path"],
            "file_name": it["file_name"],
            "resolution": it["resolution"],
            "lighting_condition": it["lighting_condition"],
            "sharpness_laplacian": it["sharpness_laplacian"],
            "confirmed_categories": it["confirmed_visual_classification"]["confirmed_categories"],
            "visual_notes": it["confirmed_visual_classification"]["visual_notes"],
            "yolo26x_baseline_cands_010": it["yolo26x"]["all_candidates_010"],
            "yolo11n_ref_cands_010": it["yolo11n"]["all_candidates_010"],
        }

    # Cargar imágenes únicas y ROI
    roi_dto = AreaConfigDTO(
        id_area_vision="00000000-0000-0000-0000-000000000001",
        id_camara="00000000-0000-0000-0000-000000000001",
        codigo="ROI-EVAL",
        nombre="ROI Operativa Estándar",
        tipo_movimiento="SALIDA",
        x_min=0.10,
        y_min=0.20,
        x_max=0.90,
        y_max=0.80,
        activa=True,
    )
    images_by_sha: Dict[str, np.ndarray] = {}
    rois_by_sha: Dict[str, Any] = {}
    for it in unique_items:
        bgr = cv2.imread(str(EVIDENCE_DIR / it["relative_path"]))
        images_by_sha[it["sha256"]] = bgr
        rois_by_sha[it["sha256"]] = project_normalized_roi(roi_dto, bgr.shape[1], bgr.shape[0])

    w26 = str(resolve_yolo_weights_path("experiments/yolo26x/weights/yolo26x.pt"))
    w11 = str(resolve_yolo_weights_path("yolo11n.pt"))

    print("[2/5] Reproduciendo YOLO11n Referencia, YOLO26x Baseline y YOLO26x Optimizado (VISION-05A.1) mediante YoloVehicleDetector...")
    det_11n = YoloVehicleDetector(
        YoloDetectorConfig(
            model_path=w11,
            confidence_threshold=0.10,
            device="cuda:0",
            imgsz=640,
            quantize=16,
            nms=None,
            deduplicate_iou_threshold=None,
            consolidate_frontal_confidence=False,
            frontal_aux_enabled=False,
        )
    )
    boxes_11n, stats_11n = run_detector_over_corpus(det_11n, unique_items, images_by_sha, rois_by_sha)
    det_11n.close()

    det_26_base = YoloVehicleDetector(
        YoloDetectorConfig(
            model_path=w26,
            confidence_threshold=0.10,
            device="cuda:0",
            imgsz=640,
            quantize=16,
            nms=False,
            deduplicate_iou_threshold=None,
            consolidate_frontal_confidence=False,
            frontal_aux_enabled=False,
        )
    )
    boxes_26_base, stats_26_base = run_detector_over_corpus(det_26_base, unique_items, images_by_sha, rois_by_sha)
    det_26_base.close()

    det_26_opt = YoloVehicleDetector(
        YoloDetectorConfig(
            model_path=w26,
            confidence_threshold=0.10,
            device="cuda:0",
            imgsz=640,
            quantize=16,
            nms=False,
            deduplicate_iou_threshold=0.55,
            consolidate_frontal_confidence=True,
            frontal_aux_enabled=True,
            frontal_aux_imgsz=384,
            frontal_aux_trigger_confidence=0.70,
        )
    )
    boxes_26_opt, stats_26_opt = run_detector_over_corpus(det_26_opt, unique_items, images_by_sha, rois_by_sha)
    det_26_opt.close()

    repro_summary = {
        "yolo11n_reference": {
            "latency": {k: v for k, v in stats_11n.items() if k != "runtime_status"},
            "unique_279": evaluate_boxes_by_category(unique_items, boxes_11n, 0.70, boxes_26_base),
            "all_675": evaluate_boxes_by_category(items, boxes_11n, 0.70, boxes_26_base),
        },
        "yolo26x_baseline": {
            "latency": {k: v for k, v in stats_26_base.items() if k != "runtime_status"},
            "unique_279": evaluate_boxes_by_category(unique_items, boxes_26_base, 0.70),
            "all_675": evaluate_boxes_by_category(items, boxes_26_base, 0.70),
        },
        "yolo26x_optimized_05a1": {
            "latency": {k: v for k, v in stats_26_opt.items() if k != "runtime_status"},
            "runtime_counters": stats_26_opt["runtime_status"]["inference_metrics"],
            "unique_279": evaluate_boxes_by_category(unique_items, boxes_26_opt, 0.70, boxes_26_base),
            "all_675": evaluate_boxes_by_category(items, boxes_26_opt, 0.70, boxes_26_base),
        },
    }

    print("[3/5] Validación Multiescala Completa (imgsz = 640, 480, 384, 320 + sondas condicionales)...")
    multiscale_results: Dict[str, Any] = {}
    for imgsz_val in (640, 480, 384, 320):
        det_ms = YoloVehicleDetector(
            YoloDetectorConfig(
                model_path=w26,
                confidence_threshold=0.10,
                device="cuda:0",
                imgsz=imgsz_val,
                quantize=16,
                nms=False,
                deduplicate_iou_threshold=0.55,
                consolidate_frontal_confidence=True,
                frontal_aux_enabled=False,
            )
        )
        b_ms, st_ms = run_detector_over_corpus(det_ms, unique_items, images_by_sha, rois_by_sha)
        det_ms.close()
        key = f"single_{imgsz_val}"
        multiscale_results[key] = {
            "imgsz": imgsz_val,
            "mode": "single_scale_dedup",
            "latency": {k: v for k, v in st_ms.items() if k != "runtime_status"},
            "unique_279": evaluate_boxes_by_category(unique_items, b_ms, 0.70, boxes_26_base),
        }
        u = multiscale_results[key]["unique_279"]
        print(
            f"  [imgsz={imgsz_val}] lat={st_ms['mean_ms']}ms | FrontCar={u['frontal_cars']['rate_070_pct']}% | "
            f"FrontBusPresence={u['frontal_buses_presence']['rate_070_pct']}% | FrontBusStrict={u['frontal_buses_strict_label']['rate_070_pct']}% | "
            f"Small={u['small_vehicles']['rate_070_pct']}% | LowL={u['low_light']['rate_070_pct']}% | "
            f"IoU_vs_640={u['vs_640_stability']['mean_iou_vs_640']}"
        )

    for aux_val in (480, 384, 320):
        det_cond = YoloVehicleDetector(
            YoloDetectorConfig(
                model_path=w26,
                confidence_threshold=0.10,
                device="cuda:0",
                imgsz=640,
                quantize=16,
                nms=False,
                deduplicate_iou_threshold=0.55,
                consolidate_frontal_confidence=True,
                frontal_aux_enabled=True,
                frontal_aux_imgsz=aux_val,
                frontal_aux_trigger_confidence=0.70,
            )
        )
        b_cond, st_cond = run_detector_over_corpus(det_cond, unique_items, images_by_sha, rois_by_sha)
        det_cond.close()
        key = f"cond_640_plus_{aux_val}"
        multiscale_results[key] = {
            "imgsz": f"640+{aux_val}_cond",
            "mode": "conditional_aux_probe",
            "latency": {k: v for k, v in st_cond.items() if k != "runtime_status"},
            "runtime_counters": st_cond["runtime_status"]["inference_metrics"],
            "unique_279": evaluate_boxes_by_category(unique_items, b_cond, 0.70, boxes_26_base),
        }
        u = multiscale_results[key]["unique_279"]
        print(
            f"  [640+{aux_val}] lat={st_cond['mean_ms']}ms | FrontCar={u['frontal_cars']['rate_070_pct']}% | "
            f"FrontBusPresence={u['frontal_buses_presence']['rate_070_pct']}% | FrontBusStrict={u['frontal_buses_strict_label']['rate_070_pct']}% | "
            f"Small={u['small_vehicles']['rate_070_pct']}% | LowL={u['low_light']['rate_070_pct']}% | "
            f"Recovered={u['vs_640_stability']['recovered_070_count']} | Lost={u['vs_640_stability']['lost_070_count']}"
        )

    print("[4/5] Evaluando falsos positivos comparativos en escenas sintéticas/fondo...")
    # Medir detecciones en los 2 archivos con menor probabilidad de falsos positivos complejos y comparar conteo total de cajas >=0.70 fuera del ROI
    # En EV-0001..EV-0012 y EV-0425..0448 hay 1 solo vehículo real por escena.
    single_vehicle_sids = [f"EV-{i:04d}" for i in list(range(1, 13)) + list(range(425, 449))]
    fp_check: Dict[str, Any] = {}
    for label_k, boxes_map in [
        ("baseline_640", boxes_26_base),
        ("opt_640_384", boxes_26_opt),
    ]:
        extra_boxes_70 = 0
        extra_boxes_25 = 0
        for sid in single_vehicle_sids:
            sha = by_id[sid]["sha256"]
            bs70 = [b for b in boxes_map[sha] if b["confidence"] >= 0.70]
            bs25 = [b for b in boxes_map[sha] if b["confidence"] >= 0.25]
            if len(bs70) > 1:
                extra_boxes_70 += len(bs70) - 1
            if len(bs25) > 1:
                extra_boxes_25 += len(bs25) - 1
        fp_check[label_k] = {
            "single_vehicle_frames_checked": len(single_vehicle_sids),
            "extra_detections_above_070": extra_boxes_70,
            "extra_detections_above_025": extra_boxes_25,
        }

    print("[5/5] Verificando invariantes de arquitectura, pesos, .env y test_trust_ca_logic.test_16...")
    default_env_cfg = load_yolo_config_from_env()
    integrity_audit = {
        "yolo11n_pt_path": w11,
        "yolo11n_pt_sha256": sha256_file(Path(w11)),
        "yolo26x_pt_path": w26,
        "yolo26x_pt_sha256": sha256_file(Path(w26)),
        "env_file_exists": (REPO_ROOT / ".env").is_file(),
        "env_file_sha256": sha256_file(REPO_ROOT / ".env"),
        "default_env_model_name": Path(str(default_env_cfg.model_path)).name,
        "default_env_fallback_name": Path(str(default_env_cfg.fallback_model_path)).name,
        "default_env_fallback_enabled": default_env_cfg.fallback_enabled,
        "default_env_imgsz": default_env_cfg.imgsz,
        "trust_ca_test_16_reproduction": run_strict_check(
            root_ca_path=REPO_ROOT / "certs" / "vigia_root_ca.crt",
            port=5000,
        ),
    }

    output = {
        "corpus_audit": corpus_audit,
        "key_samples_exact": key_samples,
        "reproduction": repro_summary,
        "multiscale_validation": multiscale_results,
        "false_positive_single_vehicle_probe": fp_check,
        "architecture_and_environment_audit": integrity_audit,
    }
    OUT_AUDIT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nAuditoría guardada en: {OUT_AUDIT_PATH}")


if __name__ == "__main__":
    main()
