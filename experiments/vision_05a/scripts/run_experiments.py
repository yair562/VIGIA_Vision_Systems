"""
VIGIA-VISION-05A — Etapa D: Suite de Experimentación Controlada y Afinación
===========================================================================
Ejecuta experimentos aislados (una variable por experimento y luego combinaciones
justificadas) sobre el conjunto completo de evaluación (279 SHA-256 únicos -> 675
imágenes de evidencias_vigia/), midiendo:
- Detección en Automóviles Frontales (@0.70 y @0.25)
- Detección en Autobuses Frontales y Oblicuos (@0.70 y @0.25)
- Impacto en Vehículos Oblicuos, Laterales, Traseros, Pequeños y Baja Iluminación
- Pares duplicados intra-frame (IoU >= 0.50)
- Latencia media / p95 (ms) y FPS en GPU RTX 4050
"""

from __future__ import annotations

import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ultralytics import YOLO
from VIGIA_Vision.config.topology_validator import AreaConfigDTO
from VIGIA_Vision.detection.roi_and_preprocess import project_normalized_roi

EVIDENCE_DIR = REPO_ROOT / "evidencias_vigia"
INV_PATH = REPO_ROOT / "experiments" / "vision_05a" / "results" / "etapa_a_b_classified_inventory.json"
OUT_EXP_PATH = REPO_ROOT / "experiments" / "vision_05a" / "results" / "etapa_d_experiments_results.json"
W_26X = REPO_ROOT / "experiments" / "yolo26x" / "weights" / "yolo26x.pt"
W_11N = REPO_ROOT / "yolo11n.pt"

COCO_VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def bbox_iou(b1: Sequence[int], b2: Sequence[int]) -> float:
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


def apply_clahe_bgr(img: np.ndarray, clip_limit: float = 2.0) -> np.ndarray:
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    l2 = clahe.apply(l)
    return cv2.cvtColor(cv2.merge((l2, a, b)), cv2.COLOR_LAB2BGR)


def apply_unsharp(img: np.ndarray, sigma: float = 1.2, amount: float = 1.0) -> np.ndarray:
    blur = cv2.GaussianBlur(img, (0, 0), sigma)
    return cv2.addWeighted(img, 1.0 + amount, blur, -amount, 0)


def deduplicate_boxes(
    boxes: List[Dict[str, Any]],
    iou_thresh: float = 0.55,
    fuse_class_prob: bool = False,
    fuse_same_class_split: bool = False,
) -> List[Dict[str, Any]]:
    """
    Suprime cajas duplicadas intra-frame (mismo vehículo detectado múltiples veces por
    distintas anclas o distintas clases vehiculares en modo NMS-Free one2one).
    Si fuse_class_prob=True y dos cajas tienen IoU >= 0.75 sobre el mismo objeto físico,
    consolida la probabilidad partida entre anclas/clases sin inventar detecciones:
      p_consolidated = 1 - (1 - p1)*(1 - w*p2).
    """
    if not boxes:
        return []
    ordered = sorted(boxes, key=lambda x: x["confidence"], reverse=True)
    kept: List[Dict[str, Any]] = []
    for cand in ordered:
        merged = False
        for k in kept:
            iou_val = bbox_iou(cand["bbox"], k["bbox"])
            if iou_val >= iou_thresh:
                if iou_val >= 0.75:
                    if fuse_class_prob and cand["label"] != k["label"]:
                        p1 = k["confidence"]
                        p2 = cand["confidence"]
                        combined = 1.0 - (1.0 - p1) * (1.0 - p2)
                        k["confidence"] = round(min(0.99, combined), 4)
                        if cand["label"] == "bus" and cand["confidence"] >= 0.60 * p1:
                            k["label"] = "bus"
                    elif fuse_same_class_split and cand["label"] == k["label"]:
                        p1 = k["confidence"]
                        p2 = cand["confidence"]
                        combined = 1.0 - (1.0 - p1) * (1.0 - 0.65 * p2)
                        k["confidence"] = round(min(0.99, combined), 4)
                merged = True
                break
        if not merged:
            kept.append(dict(cand))
    kept.sort(key=lambda x: x["confidence"], reverse=True)
    return kept


def parse_ultralytics_boxes(res: Any, w: int, h: int, px_roi: Any) -> List[Dict[str, Any]]:
    out = []
    if not res or res[0].boxes is None:
        return out
    for b in res[0].boxes:
        cls_id = int(b.cls[0])
        if cls_id not in COCO_VEHICLE_CLASSES:
            continue
        conf = float(b.conf[0])
        coords = b.xyxy[0].tolist()
        x1 = max(0, min(int(round(coords[0])), w - 1))
        y1 = max(0, min(int(round(coords[1])), h - 1))
        x2 = max(0, min(int(round(coords[2])), w))
        y2 = max(0, min(int(round(coords[3])), h))
        if x2 <= x1 or y2 <= y1:
            continue
        cx = x1 + (x2 - x1) / 2.0
        cy = y1 + (y2 - y1) / 2.0
        in_roi = px_roi.contains_point(cx, cy)
        out.append(
            {
                "label": COCO_VEHICLE_CLASSES[cls_id],
                "confidence": round(conf, 4),
                "bbox": [x1, y1, x2, y2],
                "in_roi": in_roi,
            }
        )
    out.sort(key=lambda x: x["confidence"], reverse=True)
    return out


def main() -> None:
    data = json.load(open(INV_PATH, encoding="utf-8"))
    items = data["items"]
    unique_items = [it for it in items if not it["is_exact_duplicate"]]
    sha_to_unique = {it["sha256"]: it for it in unique_items}

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

    # Pre-load unique images in memory to measure pure inference + postprocessing latency accurately
    images_by_sha: Dict[str, np.ndarray] = {}
    rois_by_sha: Dict[str, Any] = {}
    for it in unique_items:
        bgr = cv2.imread(str(EVIDENCE_DIR / it["relative_path"]))
        images_by_sha[it["sha256"]] = bgr
        rois_by_sha[it["sha256"]] = project_normalized_roi(roi_dto, bgr.shape[1], bgr.shape[0])

    # Load two instances of YOLO26x: one fused for nms=False (one2one) and one fused for nms=True (one2many)
    m_o2o = YOLO(str(W_26X))
    m_o2o.to("cuda:0")
    dummy = np.zeros((480, 640, 3), dtype=np.uint8)
    m_o2o.predict(dummy, imgsz=640, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=False, verbose=False)

    m_o2m = YOLO(str(W_26X))
    m_o2m.to("cuda:0")
    m_o2m.predict(dummy, imgsz=640, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=True, verbose=False)

    def evaluate_strategy(
        exp_id: str,
        hypothesis: str,
        params_desc: Dict[str, Any],
        infer_fn: Callable[[np.ndarray, Any], List[Dict[str, Any]]],
        eval_thresh: float = 0.70,
    ) -> Dict[str, Any]:
        cache_boxes: Dict[str, List[Dict[str, Any]]] = {}
        latencies_ms: List[float] = []

        for sha, bgr in images_by_sha.items():
            px_roi = rois_by_sha[sha]
            t0 = time.perf_counter()
            boxes = infer_fn(bgr, px_roi)
            latencies_ms.append((time.perf_counter() - t0) * 1000.0)
            cache_boxes[sha] = boxes

        # Compute metrics across all 675 items and across the 279 unique SHA items
        def summarize_subset(subset: List[Dict[str, Any]]) -> Dict[str, Any]:
            groups = {
                "all": [],
                "frontal_cars": [],
                "frontal_buses": [],
                "frontal_and_oblique_school_bus": [],
                "oblique_vehicles": [],
                "lateral_vehicles": [],
                "rear_vehicles": [],
                "small_vehicles": [],
                "low_light": [],
                "cam_salida_20261114": [],
                "cam_salida_20261116": [],
            }
            dup_frames_025 = 0
            total_dup_pairs_025 = 0

            for it in subset:
                sha = it["sha256"]
                boxes = cache_boxes[sha]
                conf_info = it["confirmed_visual_classification"]
                cats = set(conf_info["confirmed_categories"])
                idx = int(it["sample_id"].split("-")[1])

                roi_hit_thresh = any(b["in_roi"] and b["confidence"] >= eval_thresh for b in boxes)
                roi_hit_025 = any(b["in_roi"] and b["confidence"] >= 0.25 for b in boxes)

                boxes_025 = [b for b in boxes if b["confidence"] >= 0.25]
                dp = 0
                for i in range(len(boxes_025)):
                    for j in range(i + 1, len(boxes_025)):
                        if bbox_iou(boxes_025[i]["bbox"], boxes_025[j]["bbox"]) >= 0.50:
                            dp += 1
                if dp > 0:
                    dup_frames_025 += 1
                    total_dup_pairs_025 += dp

                groups["all"].append((roi_hit_thresh, roi_hit_025))
                if conf_info["has_frontal_car"]:
                    car_hit = any(b["in_roi"] and b["label"] == "car" and b["confidence"] >= eval_thresh for b in boxes)
                    car_025 = any(b["in_roi"] and b["label"] == "car" and b["confidence"] >= 0.25 for b in boxes)
                    groups["frontal_cars"].append((car_hit, car_025))
                if conf_info["has_frontal_bus"]:
                    # Evaluamos tanto detección vehicular del autobús (bus/truck/car en la posición del autobús) como etiqueta exacta
                    # En EV-0573..0588 y EV-0668..0671 verificamos si el objeto autobús fue detectado >= eval_thresh
                    bus_any_hit = False
                    bus_025_hit = False
                    for b in boxes:
                        if not b["in_roi"]:
                            continue
                        # En EV-0573..0576 el auto pequeño de fondo está en x1>450, y2<160
                        if 573 <= idx <= 576 and b["bbox"][0] > 450:
                            continue
                        # En EV-0579..0587 el auto de fondo tiene y2 < 185, el bus frontal tiene y2 > 280
                        if 579 <= idx <= 587 and b["bbox"][3] < 200:
                            continue
                        # En EV-0588 el auto rojo está a la izquierda (x1 < 150), el bus frontal en x1 > 280
                        if idx == 588 and b["bbox"][0] < 200:
                            continue
                        # En EV-0671 el bus frontal está a la izquierda (x1 < 200), el auto rojo en x1 > 230
                        if idx == 671 and b["bbox"][0] > 220:
                            continue
                        if b["confidence"] >= eval_thresh:
                            bus_any_hit = True
                        if b["confidence"] >= 0.25:
                            bus_025_hit = True
                    groups["frontal_buses"].append((bus_any_hit, bus_025_hit))

                if conf_info["has_frontal_bus"] or (577 <= idx <= 578) or (662 <= idx <= 667) or (672 <= idx <= 675):
                    # Todas las tomas frontales y frontales-oblicuas del autobús escolar
                    groups["frontal_and_oblique_school_bus"].append((roi_hit_thresh, roi_hit_025))

                if "Vehículo frontal oblicuo" in cats:
                    groups["oblique_vehicles"].append((roi_hit_thresh, roi_hit_025))
                if "Vehículo lateral" in cats:
                    groups["lateral_vehicles"].append((roi_hit_thresh, roi_hit_025))
                if "Vehículo trasero" in cats:
                    groups["rear_vehicles"].append((roi_hit_thresh, roi_hit_025))
                if "Vehículo pequeño o lejano" in cats:
                    groups["small_vehicles"].append((roi_hit_thresh, roi_hit_025))
                if "Baja iluminación" in cats:
                    groups["low_light"].append((roi_hit_thresh, roi_hit_025))
                if it["date_folder"] == "20261114" and it["camera_code"] == "CAM-SALIDA":
                    groups["cam_salida_20261114"].append((roi_hit_thresh, roi_hit_025))
                if it["date_folder"] == "20261116" and it["camera_code"] == "CAM-SALIDA":
                    groups["cam_salida_20261116"].append((roi_hit_thresh, roi_hit_025))

            out_summary = {}
            for gk, gvals in groups.items():
                n = len(gvals)
                hits_th = sum(1 for h_th, _ in gvals if h_th)
                hits_25 = sum(1 for _, h_25 in gvals if h_25)
                out_summary[gk] = {
                    "total": n,
                    "hits_at_thresh": hits_th,
                    "rate_at_thresh_pct": round((hits_th / n) * 100.0, 2) if n else 0.0,
                    "hits_at_025": hits_25,
                    "rate_at_025_pct": round((hits_25 / n) * 100.0, 2) if n else 0.0,
                }
            out_summary["dup_frames_025"] = dup_frames_025
            out_summary["total_dup_pairs_025"] = total_dup_pairs_025
            return out_summary

        ord_lat = sorted(latencies_ms)
        mean_ms = round(sum(ord_lat) / len(ord_lat), 2)
        p50_ms = round(ord_lat[len(ord_lat) // 2], 2)
        p95_ms = round(ord_lat[int(len(ord_lat) * 0.95)], 2)

        res = {
            "exp_id": exp_id,
            "hypothesis": hypothesis,
            "parameters": params_desc,
            "eval_threshold": eval_thresh,
            "latency": {
                "mean_ms": mean_ms,
                "p50_ms": p50_ms,
                "p95_ms": p95_ms,
                "fps": round(1000.0 / mean_ms, 2) if mean_ms > 0 else 0.0,
            },
            "unique_279": summarize_subset(unique_items),
            "all_675": summarize_subset(items),
        }
        u = res["unique_279"]
        print(
            f"[{exp_id:8s}] lat={mean_ms:5.1f}ms ({res['latency']['fps']:4.1f} FPS) | "
            f"FrontCar={u['frontal_cars']['hits_at_thresh']:2d}/{u['frontal_cars']['total']} ({u['frontal_cars']['rate_at_thresh_pct']:5.1f}%) [0.25:{u['frontal_cars']['hits_at_025']:2d}] | "
            f"FrontBus={u['frontal_buses']['hits_at_thresh']:2d}/{u['frontal_buses']['total']} ({u['frontal_buses']['rate_at_thresh_pct']:5.1f}%) [0.25:{u['frontal_buses']['hits_at_025']:2d}] | "
            f"Lat={u['lateral_vehicles']['hits_at_thresh']:3d}/{u['lateral_vehicles']['total']} | "
            f"Rear={u['rear_vehicles']['hits_at_thresh']:2d}/{u['rear_vehicles']['total']} | "
            f"LowL={u['low_light']['hits_at_thresh']:2d}/{u['low_light']['total']} | "
            f"Dups={u['total_dup_pairs_025']:2d}"
        )
        return res

    experiments = []

    # BASELINE: YOLO26x (imgsz=640, FP16, nms=False, thresh=0.70)
    experiments.append(
        evaluate_strategy(
            "BASELINE",
            "Configuración base VISION-04A (YOLO26x, imgsz=640, FP16, nms=False, umbral ROI=0.70).",
            {"imgsz": 640, "quantize": 16, "nms": False, "threshold": 0.70, "preprocess": "none", "dedup": False},
            lambda bgr, roi: parse_ultralytics_boxes(
                m_o2o.predict(bgr, imgsz=640, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=False, verbose=False),
                bgr.shape[1],
                bgr.shape[0],
                roi,
            ),
            eval_thresh=0.70,
        )
    )

    # EXP-01A / 01B / 01C: Umbral de confianza (0.60, 0.55, 0.50) manteniendo imgsz=640, nms=False
    for th_idx, th_val in enumerate((0.60, 0.55, 0.50), start=1):
        experiments.append(
            evaluate_strategy(
                f"EXP-01{chr(64+th_idx)}",
                f"Reducir únicamente el umbral operativo de validación ROI a {th_val:.2f} (manteniendo imgsz=640, nms=False).",
                {"imgsz": 640, "quantize": 16, "nms": False, "threshold": th_val, "preprocess": "none", "dedup": False},
                lambda bgr, roi: parse_ultralytics_boxes(
                    m_o2o.predict(bgr, imgsz=640, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=False, verbose=False),
                    bgr.shape[1],
                    bgr.shape[0],
                    roi,
                ),
                eval_thresh=th_val,
            )
        )

    # EXP-02A / 02B / 02C: Resolución de inferencia (imgsz=384, 480, 960) manteniendo nms=False, thresh=0.70
    for sz_idx, sz_val in enumerate((384, 480, 960), start=1):
        experiments.append(
            evaluate_strategy(
                f"EXP-02{chr(64+sz_idx)}",
                f"Modificar únicamente la resolución de inferencia a imgsz={sz_val} (manteniendo nms=False, umbral=0.70).",
                {"imgsz": sz_val, "quantize": 16, "nms": False, "threshold": 0.70, "preprocess": "none", "dedup": False},
                lambda bgr, roi, sz=sz_val: parse_ultralytics_boxes(
                    m_o2o.predict(bgr, imgsz=sz, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=False, verbose=False),
                    bgr.shape[1],
                    bgr.shape[0],
                    roi,
                ),
                eval_thresh=0.70,
            )
        )

    # EXP-03: Rama de detección one2many con NMS clásico (nms=True) a imgsz=640, thresh=0.70
    experiments.append(
        evaluate_strategy(
            "EXP-03",
            "Activar la rama one2many nativa de YOLO26x mediante nms=True (manteniendo imgsz=640, umbral=0.70).",
            {"imgsz": 640, "quantize": 16, "nms": True, "threshold": 0.70, "preprocess": "none", "dedup": False},
            lambda bgr, roi: parse_ultralytics_boxes(
                m_o2m.predict(bgr, imgsz=640, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=True, verbose=False),
                bgr.shape[1],
                bgr.shape[0],
                roi,
            ),
            eval_thresh=0.70,
        )
    )

    # EXP-04A / 04B: Mejora de contraste CLAHE y Nitidez Unsharp Mask (manteniendo imgsz=640, nms=False, thresh=0.70)
    experiments.append(
        evaluate_strategy(
            "EXP-04A",
            "Aplicar ecualización adaptativa de contraste CLAHE en canal L* (CIELAB) antes de inferir (imgsz=640, nms=False).",
            {"imgsz": 640, "quantize": 16, "nms": False, "threshold": 0.70, "preprocess": "CLAHE_LAB_2.0", "dedup": False},
            lambda bgr, roi: parse_ultralytics_boxes(
                m_o2o.predict(apply_clahe_bgr(bgr, 2.0), imgsz=640, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=False, verbose=False),
                bgr.shape[1],
                bgr.shape[0],
                roi,
            ),
            eval_thresh=0.70,
        )
    )
    experiments.append(
        evaluate_strategy(
            "EXP-04B",
            "Aplicar realce de bordes Unsharp Masking (sigma=1.2, amount=1.0) antes de inferir (imgsz=640, nms=False).",
            {"imgsz": 640, "quantize": 16, "nms": False, "threshold": 0.70, "preprocess": "UNSHARP_1.2_1.0", "dedup": False},
            lambda bgr, roi: parse_ultralytics_boxes(
                m_o2o.predict(apply_unsharp(bgr, 1.2, 1.0), imgsz=640, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=False, verbose=False),
                bgr.shape[1],
                bgr.shape[0],
                roi,
            ),
            eval_thresh=0.70,
        )
    )

    # EXP-05: Deduplicación espacial inter-clase y fusión de probabilidad en cabeza one2one (nms=False, imgsz=640)
    experiments.append(
        evaluate_strategy(
            "EXP-05",
            "Aplicar deduplicación espacial agnóstica de clase (IoU>=0.55) con consolidación de probabilidad inter-clase sobre nms=False.",
            {"imgsz": 640, "quantize": 16, "nms": False, "threshold": 0.70, "preprocess": "none", "dedup": True, "fuse_class_prob": True},
            lambda bgr, roi: deduplicate_boxes(
                parse_ultralytics_boxes(
                    m_o2o.predict(bgr, imgsz=640, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=False, verbose=False),
                    bgr.shape[1],
                    bgr.shape[0],
                    roi,
                ),
                iou_thresh=0.55,
                fuse_class_prob=True,
            ),
            eval_thresh=0.70,
        )
    )

    # EXP-06: Inferencia multiescala condicional para recuperación frontal (imgsz=640 + escala auxiliar 384 si conf_roi < 0.70) con nms=False + dedup
    def multiscale_o2o(bgr: np.ndarray, roi: Any) -> List[Dict[str, Any]]:
        b640 = parse_ultralytics_boxes(
            m_o2o.predict(bgr, imgsz=640, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=False, verbose=False),
            bgr.shape[1],
            bgr.shape[0],
            roi,
        )
        b640 = deduplicate_boxes(b640, iou_thresh=0.55, fuse_class_prob=True)
        # Si no hay detección primaria sólida (>=0.70) o hay candidato frontal débil, ejecutar sonda auxiliar a 384
        has_strong_roi = any(b["in_roi"] and b["confidence"] >= 0.70 for b in b640)
        has_weak_candidate = any(0.10 <= b["confidence"] < 0.70 for b in b640)
        if not has_strong_roi or has_weak_candidate:
            b384 = parse_ultralytics_boxes(
                m_o2o.predict(bgr, imgsz=384, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=False, verbose=False),
                bgr.shape[1],
                bgr.shape[0],
                roi,
            )
            b384 = deduplicate_boxes(b384, iou_thresh=0.55, fuse_class_prob=True)
            return deduplicate_boxes(b640 + b384, iou_thresh=0.55, fuse_class_prob=True)
        return b640

    experiments.append(
        evaluate_strategy(
            "EXP-06",
            "Estrategia multiescala condicional NMS-Free (imgsz=640 + sonda auxiliar imgsz=384 ante candidatos débiles/ausentes + deduplicación inter-clase).",
            {"imgsz": "640+384_cond", "quantize": 16, "nms": False, "threshold": 0.70, "preprocess": "none", "dedup": True},
            multiscale_o2o,
            eval_thresh=0.70,
        )
    )

    # EXP-07: Estrategia multiescala condicional sobre rama one2many (nms=True, imgsz=640 + auxiliar 384 + dedup inter-clase)
    def multiscale_o2m(bgr: np.ndarray, roi: Any) -> List[Dict[str, Any]]:
        b640 = parse_ultralytics_boxes(
            m_o2m.predict(bgr, imgsz=640, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=True, verbose=False),
            bgr.shape[1],
            bgr.shape[0],
            roi,
        )
        b640 = deduplicate_boxes(b640, iou_thresh=0.55, fuse_class_prob=True)
        has_strong_roi = any(b["in_roi"] and b["confidence"] >= 0.70 for b in b640)
        has_weak_candidate = any(0.10 <= b["confidence"] < 0.70 for b in b640)
        if not has_strong_roi or has_weak_candidate:
            b384 = parse_ultralytics_boxes(
                m_o2m.predict(bgr, imgsz=384, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=True, verbose=False),
                bgr.shape[1],
                bgr.shape[0],
                roi,
            )
            b384 = deduplicate_boxes(b384, iou_thresh=0.55, fuse_class_prob=True)
            return deduplicate_boxes(b640 + b384, iou_thresh=0.55, fuse_class_prob=True)
        return b640

    experiments.append(
        evaluate_strategy(
            "EXP-07",
            "Rama one2many (nms=True) con inferencia multiescala condicional (640 + 384) y deduplicación inter-clase a umbral 0.70.",
            {"imgsz": "640+384_cond", "quantize": 16, "nms": True, "threshold": 0.70, "preprocess": "none", "dedup": True},
            multiscale_o2m,
            eval_thresh=0.70,
        )
    )

    # EXP-08: EXP-06 (NMS-Free 640+384 + dedup) con umbral operativo calibrado a 0.55
    experiments.append(
        evaluate_strategy(
            "EXP-08",
            "Estrategia multiescala condicional NMS-Free (640+384 + deduplicación inter-clase) con umbral operativo calibrado a 0.55.",
            {"imgsz": "640+384_cond", "quantize": 16, "nms": False, "threshold": 0.55, "preprocess": "none", "dedup": True},
            multiscale_o2o,
            eval_thresh=0.55,
        )
    )

    # EXP-09: EXP-07 (one2many nms=True 640+384 + dedup) con umbral operativo calibrado a 0.55
    experiments.append(
        evaluate_strategy(
            "EXP-09",
            "Rama one2many (nms=True) multiescala condicional (640+384 + deduplicación inter-clase) con umbral operativo calibrado a 0.55.",
            {"imgsz": "640+384_cond", "quantize": 16, "nms": True, "threshold": 0.55, "preprocess": "none", "dedup": True},
            multiscale_o2m,
            eval_thresh=0.55,
        )
    )

    # EXP-10: NMS-Free (nms=False) con sonda auxiliar 384 + consolidación espacial de anclas e inter-clase a umbral 0.70
    def multiscale_o2o_consensus(bgr: np.ndarray, roi: Any) -> List[Dict[str, Any]]:
        b640 = parse_ultralytics_boxes(
            m_o2o.predict(bgr, imgsz=640, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=False, verbose=False),
            bgr.shape[1],
            bgr.shape[0],
            roi,
        )
        b640 = deduplicate_boxes(b640, iou_thresh=0.55, fuse_class_prob=True, fuse_same_class_split=True)
        has_strong_roi = any(b["in_roi"] and b["confidence"] >= 0.70 for b in b640)
        has_weak_candidate = any(0.10 <= b["confidence"] < 0.70 for b in b640)
        if not has_strong_roi or has_weak_candidate:
            b384 = parse_ultralytics_boxes(
                m_o2o.predict(bgr, imgsz=384, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=False, verbose=False),
                bgr.shape[1],
                bgr.shape[0],
                roi,
            )
            b384 = deduplicate_boxes(b384, iou_thresh=0.55, fuse_class_prob=True, fuse_same_class_split=True)
            return deduplicate_boxes(b640 + b384, iou_thresh=0.55, fuse_class_prob=True, fuse_same_class_split=True)
        return b640

    experiments.append(
        evaluate_strategy(
            "EXP-10",
            "NMS-Free (nms=False) + sonda condicional imgsz=384 + deduplicación espacial y consolidación de confianza intra/inter-escala a umbral 0.70.",
            {"imgsz": "640+384_cond", "quantize": 16, "nms": False, "threshold": 0.70, "preprocess": "none", "dedup": True, "consensus": True},
            multiscale_o2o_consensus,
            eval_thresh=0.70,
        )
    )

    with OUT_EXP_PATH.open("w", encoding="utf-8") as f:
        json.dump({"experiments": experiments}, f, indent=2, ensure_ascii=False)
    print(f"\nGuardados resultados experimentales en {OUT_EXP_PATH}")


if __name__ == "__main__":
    main()
