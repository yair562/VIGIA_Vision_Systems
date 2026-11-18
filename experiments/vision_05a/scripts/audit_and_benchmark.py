"""
VIGIA-VISION-05A — Etapa A & B: Auditoría Reproducible del Corpus y Benchmark Base
==================================================================================
Inspecciona recursivamente VIGIA_Vision_Systems/evidencias_vigia/ sin modificar
ninguna evidencia original y ejecuta evaluación comparativa controlada entre
yolo26x.pt y yolo11n.pt exclusivamente sobre imágenes *_orig.jpg.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
    resolve_yolo_weights_path,
)

EVIDENCE_DIR = REPO_ROOT / "evidencias_vigia"
OUT_DIR = REPO_ROOT / "experiments" / "vision_05a" / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_dhash(gray: np.ndarray, hash_size: int = 8) -> int:
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    val = 0
    for bit in diff.flatten():
        val = (val << 1) | int(bool(bit))
    return val


def hamming_distance(h1: int, h2: int) -> int:
    return (h1 ^ h2).bit_count()


def parse_timestamp_from_stem(stem: str) -> Optional[datetime]:
    # Format: YYYYMMDDTHHMMSS_uuuuuuZ_<hex>_orig
    parts = stem.split("_")
    if len(parts) < 3:
        return None
    try:
        dt_str = f"{parts[0]}_{parts[1]}"
        return datetime.strptime(dt_str, "%Y%m%dT%H%M%S_%fZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def compute_image_quality(bgr: np.ndarray) -> Dict[str, Any]:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    y_mean = float(gray.mean())
    y_std = float(gray.std())
    pct_dark = float((gray < 40).mean() * 100.0)
    pct_bright = float((gray > 235).mean() * 100.0)
    # Backlight / contraluz heuristic: simultaneously high bright region and high dark/shadow region, or strong top/bottom luminance gradient
    h = gray.shape[0]
    top_half_mean = float(gray[: h // 2, :].mean())
    bot_half_mean = float(gray[h // 2 :, :].mean())
    backlight_index = top_half_mean - bot_half_mean
    dhash = compute_dhash(gray)

    if lap_var < 15.0:
        blur_grade = "SEVERE_BLUR"
    elif lap_var < 60.0:
        blur_grade = "MODERATE_BLUR"
    else:
        blur_grade = "SHARP"

    if y_mean < 55.0 or pct_dark > 45.0:
        lighting = "LOW_LIGHT"
    elif (pct_bright > 8.0 and pct_dark > 15.0) or (backlight_index > 45.0 and pct_bright > 5.0):
        lighting = "BACKLIGHT"
    elif pct_bright > 12.0 or y_mean > 175.0:
        lighting = "GLARE"
    else:
        lighting = "NORMAL"

    return {
        "sharpness_laplacian": round(lap_var, 2),
        "luminance_mean": round(y_mean, 2),
        "contrast_rms": round(y_std, 2),
        "pct_dark": round(pct_dark, 2),
        "pct_bright": round(pct_bright, 2),
        "top_bottom_diff": round(backlight_index, 2),
        "blur_grade": blur_grade,
        "lighting_condition": lighting,
        "dhash_int": dhash,
        "dhash_hex": f"{dhash:016x}",
    }


def bbox_iou(b1: Tuple[int, int, int, int], b2: Tuple[int, int, int, int]) -> float:
    x1 = max(b1[0], b2[0])
    y1 = max(b1[1], b2[1])
    x2 = min(b1[2], b2[2])
    y2 = min(b1[3], b2[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter <= 0:
        return 0.0
    a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    return inter / float(a1 + a2 - inter)


def main() -> None:
    print("[1/4] Escaneando recursivamente evidencias_vigia/...")
    all_files = sorted(EVIDENCE_DIR.rglob("*"))
    files_only = [p for p in all_files if p.is_file()]
    orig_files = sorted([p for p in files_only if p.name.endswith("_orig.jpg")])
    annot_files = sorted([p for p in files_only if p.name.endswith("_annot.jpg")])
    other_files = [p for p in files_only if not (p.name.endswith("_orig.jpg") or p.name.endswith("_annot.jpg"))]

    annot_map = {p.name[:-10]: p for p in annot_files}  # prefix without _annot.jpg

    # Load DB metadata if PostgreSQL is reachable (read-only)
    db_records: Dict[str, Dict[str, Any]] = {}
    try:
        import psycopg2
        from VIGIA_Core.repository.user_repository import resolve_database_dsn

        conn = psycopg2.connect(resolve_database_dsn(), connect_timeout=3)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ruta_evidencia_foto, tipo_vehiculo_pred, confianza_vehiculo, fecha_hora
            FROM deteccion
            WHERE ruta_evidencia_foto IS NOT NULL;
            """
        )
        for ruta, tipo, conf, fh in cur.fetchall():
            norm_key = str(ruta).replace("\\", "/")
            db_records[norm_key] = {
                "db_tipo_vehiculo_pred": tipo,
                "db_confianza_vehiculo": float(conf) if conf is not None else None,
                "db_fecha_hora": fh.isoformat() if fh is not None else None,
            }
        conn.close()
        print(f"  -> PostgreSQL leído (solo lectura): {len(db_records)} registros con ruta de evidencia.")
    except Exception as exc:
        print(f"  -> Aviso lectura PostgreSQL: {exc}")

    inventory: List[Dict[str, Any]] = []
    sha_to_first_id: Dict[str, str] = {}
    exact_dup_groups: Dict[str, List[str]] = defaultdict(list)

    corrupt_orig = 0
    corrupt_annot = 0

    prev_dt_by_cam: Dict[str, datetime] = {}
    prev_small_by_cam: Dict[str, np.ndarray] = {}
    session_counter = 0
    perceptual_cluster_counter = 0
    prev_dhash_by_cam: Dict[str, int] = {}
    current_cluster_by_cam: Dict[str, str] = {}

    # Cache BGR by sha256 to avoid decoding 396 identical images multiple times if needed,
    # though we will still record per-file metrics.
    for idx, orig_path in enumerate(orig_files, start=1):
        rel_path = orig_path.relative_to(EVIDENCE_DIR).as_posix()
        parts = rel_path.split("/")
        date_folder = parts[0] if len(parts) > 0 else "UNKNOWN"
        camera_code = parts[1] if len(parts) > 1 else "UNKNOWN"
        prefix = orig_path.name[:-9]  # strip _orig.jpg
        sample_id = f"EV-{idx:04d}"

        sha256_hex = compute_sha256(orig_path)
        exact_dup_groups[sha256_hex].append(sample_id)
        is_exact_dup = sha256_hex in sha_to_first_id
        if not is_exact_dup:
            sha_to_first_id[sha256_hex] = sample_id
        exact_group_id = f"SHA-{sha_to_first_id[sha256_hex]}"

        file_size = orig_path.stat().st_size
        bgr = cv2.imread(str(orig_path))
        if bgr is None or bgr.size == 0:
            corrupt_orig += 1
            continue

        h, w, c = bgr.shape
        annot_path = orig_path.with_name(f"{prefix}_annot.jpg")
        has_annot = annot_path.is_file()
        annot_valid = False
        if has_annot:
            abgr = cv2.imread(str(annot_path))
            if abgr is not None and abgr.size > 0:
                annot_valid = True
            else:
                corrupt_annot += 1

        dt = parse_timestamp_from_stem(orig_path.stem)
        cam_key = f"{date_folder}/{camera_code}"
        if dt is not None:
            prev_dt = prev_dt_by_cam.get(cam_key)
            if prev_dt is None or (dt - prev_dt).total_seconds() > 60.0:
                session_counter += 1
            prev_dt_by_cam[cam_key] = dt
        else:
            session_counter += 1
        session_id = f"SEQ-{session_counter:03d}"

        qual = compute_image_quality(bgr)
        small_gray = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (64, 48), interpolation=cv2.INTER_AREA)
        prev_small = prev_small_by_cam.get(cam_key)
        mad_prev = (
            float(np.abs(small_gray.astype(np.float32) - prev_small.astype(np.float32)).mean())
            if prev_small is not None
            else None
        )
        prev_small_by_cam[cam_key] = small_gray

        prev_dh = prev_dhash_by_cam.get(cam_key)
        dh_dist = hamming_distance(qual["dhash_int"], prev_dh) if prev_dh is not None else 99
        prev_dhash_by_cam[cam_key] = qual["dhash_int"]

        if is_exact_dup:
            # Find perceptual cluster of first occurrence
            perceptual_group = f"PCLUSTER-EXACT-{sha_to_first_id[sha256_hex]}"
            if cam_key not in current_cluster_by_cam:
                current_cluster_by_cam[cam_key] = perceptual_group
        else:
            if cam_key in current_cluster_by_cam and ((mad_prev is not None and mad_prev < 8.0) or dh_dist <= 6):
                perceptual_group = current_cluster_by_cam[cam_key]
            else:
                perceptual_cluster_counter += 1
                perceptual_group = f"PCLUSTER-{perceptual_cluster_counter:03d}"
                current_cluster_by_cam[cam_key] = perceptual_group

        # Evidence domain classification based on verified provenance
        if date_folder in ("20261101", "20261102", "20261105"):
            evidence_domain = "SYNTHETIC_OR_BENCHMARK_SEED"
        elif date_folder == "20261111":
            evidence_domain = "SCREEN_RECAPTURE"
        elif date_folder in ("20261104", "20261106", "20261110", "20261114", "20261116"):
            evidence_domain = "PHYSICAL_CAMERA_SCALE_MODEL"
        else:
            evidence_domain = "UNKNOWN"

        db_info = db_records.get(rel_path, {})

        inventory.append(
            {
                "sample_id": sample_id,
                "file_name": orig_path.name,
                "relative_path": rel_path,
                "date_folder": date_folder,
                "camera_code": camera_code,
                "timestamp_utc": dt.isoformat() if dt else None,
                "sha256": sha256_hex,
                "is_exact_duplicate": is_exact_dup,
                "exact_duplicate_group": exact_group_id,
                "perceptual_duplicate_group": perceptual_group,
                "session_id": session_id,
                "consecutive_mad": round(mad_prev, 2) if mad_prev is not None else None,
                "dhash_hamming_prev": dh_dist if dh_dist < 99 else None,
                "width": w,
                "height": h,
                "channels": c,
                "resolution": f"{w}x{h}",
                "file_size_bytes": file_size,
                "has_annot_pair": has_annot and annot_valid,
                "evidence_type": evidence_domain,
                **qual,
                **db_info,
            }
        )

    print(
        f"  -> Inventariados {len(inventory)} pares _orig.jpg (corruptos orig={corrupt_orig}, annot={corrupt_annot}, otros={len(other_files)})."
    )
    print(f"  -> Hashes SHA-256 únicos: {len(sha_to_first_id)}.")

    # Etapa B: Reproducción del problema y Benchmark Base (YOLO26x vs YOLO11n)
    # Evaluamos sobre cada SHA-256 único para no falsear cachés, midiendo también latencia por frame
    print("[2/4] Inicializando detectores YOLO26x y YOLO11n bajo condiciones idénticas...")
    w_yolo26x = resolve_yolo_weights_path("experiments/yolo26x/weights/yolo26x.pt")
    w_yolo11n = resolve_yolo_weights_path("yolo11n.pt")

    # Condiciones idénticas de evaluación inicial (conf=0.10 para capturar todas las detecciones débiles y evaluar cortes en 0.25 y 0.70)
    cfg_26x = YoloDetectorConfig(
        model_path=str(w_yolo26x),
        confidence_threshold=0.10,
        device="cuda:0",
        imgsz=640,
        iou_threshold=0.45,
        classes=(2, 3, 5, 7),
        quantize=16,
        nms=False,
        augment=False,
        fallback_enabled=False,
    )
    cfg_11n = YoloDetectorConfig(
        model_path=str(w_yolo11n),
        confidence_threshold=0.10,
        device="cuda:0",
        imgsz=640,
        iou_threshold=0.45,
        classes=(2, 3, 5, 7),
        quantize=16,
        nms=None,
        augment=False,
        fallback_enabled=False,
    )

    det_26x = YoloVehicleDetector(config=cfg_26x)
    det_11n = YoloVehicleDetector(config=cfg_11n)

    # Warmup
    dummy = np.zeros((480, 640, 3), dtype=np.uint8)
    det_26x.detect(dummy)
    det_11n.detect(dummy)

    # ROI operativa estándar (0.10, 0.20, 0.90, 0.80) según PostgreSQL area_vision
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

    print("[3/4] Ejecutando inferencia comparativa sobre imágenes originales...")
    sha_cache: Dict[str, Dict[str, Any]] = {}

    for item in inventory:
        sha = item["sha256"]
        if sha in sha_cache:
            cached = sha_cache[sha]
            item["yolo26x"] = cached["yolo26x"]
            item["yolo11n"] = cached["yolo11n"]
            continue

        img_path = EVIDENCE_DIR / item["relative_path"]
        bgr = cv2.imread(str(img_path))
        h, w = bgr.shape[:2]
        frame_area = float(w * h)
        px_roi = project_normalized_roi(roi_dto, w, h)

        t0 = time.perf_counter()
        raw_26x = det_26x.detect(bgr)
        ms_26x = round((time.perf_counter() - t0) * 1000.0, 3)

        t1 = time.perf_counter()
        raw_11n = det_11n.detect(bgr)
        ms_11n = round((time.perf_counter() - t1) * 1000.0, 3)

        def summarize_preds(raw_list: Sequence[RawVehicleDetection], elapsed_ms: float) -> Dict[str, Any]:
            all_boxes = []
            for d in raw_list:
                in_roi = px_roi.contains_bbox_centroid(d.bbox)
                rel_area = round((d.bbox.area / frame_area) * 100.0, 3)
                aspect = round(d.bbox.width / float(max(1, d.bbox.height)), 3)
                all_boxes.append(
                    {
                        "label": d.raw_label,
                        "confidence": round(d.confidence, 4),
                        "bbox": [d.bbox.x_min, d.bbox.y_min, d.bbox.x_max, d.bbox.y_max],
                        "width": d.bbox.width,
                        "height": d.bbox.height,
                        "rel_area_pct": rel_area,
                        "aspect_ratio_wh": aspect,
                        "in_roi": in_roi,
                    }
                )
            boxes_025 = [b for b in all_boxes if b["confidence"] >= 0.25]
            boxes_050 = [b for b in all_boxes if b["confidence"] >= 0.50]
            boxes_070 = [b for b in all_boxes if b["confidence"] >= 0.70]
            roi_025 = [b for b in boxes_025 if b["in_roi"]]
            roi_070 = [b for b in boxes_070 if b["in_roi"]]

            # Count intra-frame duplicates at >=0.25 (IoU >= 0.50 regardless of class or same class)
            dup_pairs_025 = 0
            for i in range(len(boxes_025)):
                for j in range(i + 1, len(boxes_025)):
                    if bbox_iou(tuple(boxes_025[i]["bbox"]), tuple(boxes_025[j]["bbox"])) >= 0.50:
                        dup_pairs_025 += 1

            return {
                "inference_ms": elapsed_ms,
                "all_candidates_010": all_boxes,
                "count_025": len(boxes_025),
                "count_050": len(boxes_050),
                "count_070": len(boxes_070),
                "roi_count_025": len(roi_025),
                "roi_count_070": len(roi_070),
                "primary_025": boxes_025[0] if boxes_025 else None,
                "primary_roi_070": roi_070[0] if roi_070 else None,
                "intra_frame_dup_pairs_025": dup_pairs_025,
            }

        res_entry = {
            "yolo26x": summarize_preds(raw_26x, ms_26x),
            "yolo11n": summarize_preds(raw_11n, ms_11n),
        }
        sha_cache[sha] = res_entry
        item["yolo26x"] = res_entry["yolo26x"]
        item["yolo11n"] = res_entry["yolo11n"]

    det_26x.close()
    det_11n.close()

    out_json = OUT_DIR / "etapa_a_b_raw_inventory.json"
    with out_json.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "total_files_scanned": len(files_only),
                "total_orig_jpg": len(orig_files),
                "total_annot_jpg": len(annot_files),
                "total_other_files": len(other_files),
                "corrupt_orig_jpg": corrupt_orig,
                "corrupt_annot_jpg": corrupt_annot,
                "unique_sha256_count": len(sha_to_first_id),
                "total_sessions": session_counter,
                "total_perceptual_clusters": perceptual_cluster_counter,
                "items": inventory,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"[4/4] Guardado inventario y resultados crudos en {out_json}")


if __name__ == "__main__":
    main()
