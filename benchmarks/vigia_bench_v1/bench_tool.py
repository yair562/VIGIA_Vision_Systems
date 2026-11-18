"""CLI reproducible de inventario, anotacion y evaluacion para VIGIA-BENCH-v1.

Restricciones de diseno:
- No modifica ni duplica las imagenes originales en `evidencias_vigia/`.
- No inventa anotaciones Ground Truth ni declara metricas sin verificacion humana.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from typing import Any

import cv2
import numpy as np

BENCH_DIR = Path(__file__).resolve().parent
REPO_ROOT = BENCH_DIR.parent.parent
DEFAULT_CORPUS_ROOT = REPO_ROOT / "evidencias_vigia"
DEFAULT_MANIFEST = BENCH_DIR / "manifest_v1_seed.json"
DEFAULT_CSV = BENCH_DIR / "annotation_sheet_v1.csv"
DEFAULT_RUNS_DIR = BENCH_DIR / "runs"

SYNTHETIC_STOCK_SHA256 = {
    "81e969e79ce55dc828795403144bc06f0636560fbe4e70b887cdf55ab5d3bcc2": "640x480",
    "37c80acd7d2762b1c15b059795652c884e4043298568968062c61b64a83a5448": "810x1080_A",
    "22dd33ab189040a32003356a63aa955f1f1d6f45056be35dd2764efaee5e656b": "810x1080_B",
}

TARGET_CLASSES = ("CAR", "MOTORCYCLE", "BUS", "TRUCK")
ALLOWED_ANNOTATION_CLASSES = TARGET_CLASSES + ("IGNORE",)
COCO_ID_TO_BENCH_CLASS = {
    2: "CAR",
    3: "MOTORCYCLE",
    5: "BUS",
    7: "TRUCK",
}
CSV_HEADER = [
    "image_id",
    "rel_path",
    "camera_id",
    "session_id",
    "source_domain",
    "width",
    "height",
    "lighting_condition",
    "sharpness_tier",
    "annotation_status",
    "is_negative_sample",
    "class_label",
    "x_min",
    "y_min",
    "x_max",
    "y_max",
    "visibility_ratio",
    "occlusion_level",
    "estimated_distance",
    "lighting_local",
    "is_scale_model",
    "ignore_reason",
    "annotator_id",
]

FILENAME_TS_RE = re.compile(r"^(\d{8}T\d{6})_(\d{6})Z_([0-9a-f]+)_orig\.jpg$")


def compute_sha256(path: Path) -> str:
    """Calcula el digest SHA-256 hexadecimal de un archivo."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_capture_timestamp(fname: str) -> tuple[datetime | None, float | None]:
    """Extrae el timestamp UTC codificado en el nombre de archivo de evidencia."""
    match = FILENAME_TS_RE.match(fname)
    if not match:
        return None, None
    dt = datetime.strptime(match.group(1) + match.group(2), "%Y%m%dT%H%M%S%f").replace(
        tzinfo=timezone.utc
    )
    return dt, dt.timestamp()


def classify_lighting(mean_y: float) -> str:
    """Clasifica iluminacion global por luminancia media Y en escala 0..255."""
    if mean_y < 60.0:
        return "UNDEREXPOSED"
    if mean_y > 145.0:
        return "HARSH_GLARE"
    return "WELL_LIT"


def classify_sharpness(lap_var: float) -> str:
    """Clasifica nitidez optica por varianza del operador Laplaciano."""
    if lap_var < 20.0:
        return "SEVERE_BLUR"
    if lap_var < 100.0:
        return "MODERATE_BLUR"
    return "SHARP"


def classify_source_domain(rel_path: str, dt: datetime | None, sha256: str) -> str:
    """Asigna dominio visual de origen con base en huella SHA-256 y sesion."""
    if sha256 in SYNTHETIC_STOCK_SHA256:
        return "SYNTHETIC_STOCK"
    date_part = rel_path.split("/", 1)[0]
    if (date_part == "20261105" and dt is not None and dt.hour == 15) or date_part == "20261111":
        return "SCREEN_RECAPTURE"
    return "SCALE_MODEL_LAB"


def inspect_corpus(corpus_root: Path) -> list[dict[str, Any]]:
    """Escanea todos los frames *_orig.jpg sin modificar ni duplicar archivos."""
    orig_paths = sorted(corpus_root.rglob("*_orig.jpg"))
    records: list[dict[str, Any]] = []

    for path in orig_paths:
        rel_path = path.relative_to(corpus_root).as_posix()
        parts = rel_path.split("/")
        camera_id = parts[1] if len(parts) > 1 else "UNKNOWN"
        dt, ts_epoch = parse_capture_timestamp(path.name)
        sha256 = compute_sha256(path)
        size_bytes = path.stat().st_size

        img = cv2.imread(str(path))
        if img is None:
            raise RuntimeError(f"No se pudo decodificar imagen original: {path}")
        height, width = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        mean_y = float(gray.mean())
        thumb = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)

        records.append(
            {
                "rel_path": rel_path,
                "sha256": sha256,
                "size_bytes": size_bytes,
                "camera_id": camera_id,
                "capture_timestamp_utc": dt.isoformat() if dt else None,
                "ts_epoch": ts_epoch or 0.0,
                "width": int(width),
                "height": int(height),
                "source_domain": classify_source_domain(rel_path, dt, sha256),
                "lighting_condition": classify_lighting(mean_y),
                "sharpness_tier": classify_sharpness(lap_var),
                "mean_luminance_y": round(mean_y, 2),
                "laplacian_variance": round(lap_var, 3),
                "_thumb": thumb,
            }
        )
    return records


def select_seed_records(
    records: list[dict[str, Any]],
    *,
    session_gap_seconds: float = 60.0,
    min_delta_seconds: float = 8.0,
    min_thumb_mad: float = 8.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Aplica deduplicacion exacta (SHA-256) y de rafagas intra-sesion."""
    stock_records = [r for r in records if r["sha256"] in SYNTHETIC_STOCK_SHA256]
    physical_records = sorted(
        (r for r in records if r["sha256"] not in SYNTHETIC_STOCK_SHA256),
        key=lambda r: (r["camera_id"], r["ts_epoch"], r["rel_path"]),
    )

    selected_stock: list[dict[str, Any]] = []
    seen_stock_variants: set[str] = set()
    for rec in sorted(stock_records, key=lambda r: r["rel_path"]):
        variant = SYNTHETIC_STOCK_SHA256[rec["sha256"]]
        target_bucket = "640x480" if variant == "640x480" else "810x1080"
        if target_bucket not in seen_stock_variants:
            seen_stock_variants.add(target_bucket)
            rec_copy = dict(rec)
            rec_copy["session_id"] = f"STOCK_{target_bucket}"
            selected_stock.append(rec_copy)

    selected_physical: list[dict[str, Any]] = []
    burst_dropped = 0
    session_idx = 0
    prev_cam: str | None = None
    prev_ts: float | None = None
    last_kept: dict[str, Any] | None = None

    for rec in physical_records:
        new_session = (
            prev_cam != rec["camera_id"]
            or prev_ts is None
            or (rec["ts_epoch"] - prev_ts) > session_gap_seconds
        )
        if new_session:
            session_idx += 1
        session_id = f"S{session_idx:02d}"
        prev_cam = rec["camera_id"]
        prev_ts = rec["ts_epoch"]

        keep = False
        if new_session or last_kept is None:
            keep = True
        else:
            dt_kept = rec["ts_epoch"] - last_kept["ts_epoch"]
            mad = float(np.mean(np.abs(rec["_thumb"] - last_kept["_thumb"])))
            if dt_kept >= min_delta_seconds or mad >= min_thumb_mad:
                keep = True

        if keep:
            rec_copy = dict(rec)
            rec_copy["session_id"] = session_id
            selected_physical.append(rec_copy)
            last_kept = rec_copy
        else:
            burst_dropped += 1

    combined = sorted(
        selected_physical + selected_stock,
        key=lambda r: (r["source_domain"], r["camera_id"], r["ts_epoch"], r["rel_path"]),
    )

    manifest_images: list[dict[str, Any]] = []
    for rec in combined:
        image_id = f"VB1_{rec['camera_id']}_{rec['sha256'][:12]}"
        manifest_images.append(
            {
                "image_id": image_id,
                "rel_path": rec["rel_path"],
                "sha256": rec["sha256"],
                "size_bytes": rec["size_bytes"],
                "camera_id": rec["camera_id"],
                "session_id": rec["session_id"],
                "capture_timestamp_utc": rec["capture_timestamp_utc"],
                "width": rec["width"],
                "height": rec["height"],
                "source_domain": rec["source_domain"],
                "is_negative_sample": False,
                "lighting_condition": rec["lighting_condition"],
                "sharpness_tier": rec["sharpness_tier"],
                "mean_luminance_y": rec["mean_luminance_y"],
                "laplacian_variance": rec["laplacian_variance"],
                "annotation_status": "PENDING_HUMAN_REVIEW",
                "notes": (
                    "Testigo de stock Ultralytics bus.jpg incluido solo para regresion tecnica; excluir de metricas de mundo real."
                    if rec["source_domain"] == "SYNTHETIC_STOCK"
                    else None
                ),
                "annotations": [],
            }
        )

    summary = {
        "total_corpus_orig_files": len(records),
        "unique_sha256_in_corpus": len({r["sha256"] for r in records}),
        "synthetic_stock_total_files": len(stock_records),
        "synthetic_stock_selected_witnesses": len(selected_stock),
        "physical_total_files": len(physical_records),
        "physical_burst_duplicates_dropped": burst_dropped,
        "physical_selected": len(selected_physical),
        "seed_total_images": len(manifest_images),
        "seed_by_domain": dict(Counter(img["source_domain"] for img in manifest_images)),
        "seed_by_camera": dict(Counter(img["camera_id"] for img in manifest_images)),
        "seed_by_lighting": dict(Counter(img["lighting_condition"] for img in manifest_images)),
        "seed_by_sharpness": dict(Counter(img["sharpness_tier"] for img in manifest_images)),
        "sessions_detected": session_idx,
    }
    return manifest_images, summary


def write_annotation_csv(images: list[dict[str, Any]], csv_path: Path) -> None:
    """Genera hoja CSV con una fila vacia por imagen para captura manual de cajas."""
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADER)
        writer.writeheader()
        for img in images:
            writer.writerow(
                {
                    "image_id": img["image_id"],
                    "rel_path": img["rel_path"],
                    "camera_id": img["camera_id"],
                    "session_id": img["session_id"],
                    "source_domain": img["source_domain"],
                    "width": img["width"],
                    "height": img["height"],
                    "lighting_condition": img["lighting_condition"],
                    "sharpness_tier": img["sharpness_tier"],
                    "annotation_status": img["annotation_status"],
                    "is_negative_sample": str(img["is_negative_sample"]).lower(),
                    "class_label": "",
                    "x_min": "",
                    "y_min": "",
                    "x_max": "",
                    "y_max": "",
                    "visibility_ratio": "",
                    "occlusion_level": "",
                    "estimated_distance": "",
                    "lighting_local": "",
                    "is_scale_model": "true" if img["source_domain"] == "SCALE_MODEL_LAB" else "false",
                    "ignore_reason": "",
                    "annotator_id": "",
                }
            )


def cmd_build_seed(args: argparse.Namespace) -> int:
    """Construye manifest_v1_seed.json y annotation_sheet_v1.csv sin inventar cajas."""
    manifest_path = Path(args.manifest)
    if manifest_path.exists() and not args.force:
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        verified = sum(
            1 for img in existing.get("images", []) if img.get("annotation_status") == "ANNOTATED_VERIFIED"
        )
        if verified > 0:
            print(
                f"ERROR: {manifest_path} ya contiene {verified} imagenes ANNOTATED_VERIFIED. Usa --force para regenerar.",
                file=sys.stderr,
            )
            return 1

    corpus_root = Path(args.corpus_root)
    records = inspect_corpus(corpus_root)
    images, summary = select_seed_records(records)

    payload = {
        "dataset_version": "VIGIA-BENCH-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "corpus_root_relative": "evidencias_vigia",
        "selection_policy": {
            "exact_dedup": "sha256_stock_bus_collapsed_to_2_witnesses",
            "burst_dedup_min_delta_seconds": 8.0,
            "burst_dedup_min_thumbnail_mad": 8.0,
            "session_gap_seconds": 60.0,
            "synthetic_stock_witnesses": 2,
        },
        "summary": summary,
        "images": images,
    }
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_annotation_csv(images, Path(args.csv))

    print(f"Manifest semilla generado: {manifest_path}")
    print(f"Hoja de anotacion CSV:    {args.csv}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def assess_manifest_readiness(manifest: dict[str, Any], corpus_root: Path) -> dict[str, Any]:
    """Verifica hashes SHA-256 y cuotas minimas de completitud y estratificacion."""
    images = manifest.get("images", [])
    sha_errors: list[str] = []
    status_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()
    negative_verified = 0
    real_full_scale_verified = 0

    for img in images:
        status_counts[img["annotation_status"]] += 1
        img_path = corpus_root / img["rel_path"]
        if not img_path.exists():
            sha_errors.append(f"MISSING: {img['rel_path']}")
        else:
            actual_sha = compute_sha256(img_path)
            if actual_sha != img["sha256"]:
                sha_errors.append(f"HASH_MISMATCH: {img['rel_path']}")

        if img["annotation_status"] == "ANNOTATED_VERIFIED":
            domain_counts[img["source_domain"]] += 1
            if img.get("is_negative_sample"):
                negative_verified += 1
            if img["source_domain"] == "REAL_FULL_SCALE":
                real_full_scale_verified += 1
            for ann in img.get("annotations", []):
                class_counts[ann["class_label"]] += 1

    blocking_reasons: list[str] = []
    observations: list[str] = []

    if sha_errors:
        blocking_reasons.append(f"Integridad SHA-256 comprometida en {len(sha_errors)} archivo(s).")
    if status_counts["PENDING_HUMAN_REVIEW"] > 0:
        blocking_reasons.append(
            f"Faltan anotaciones manuales verificadas en {status_counts['PENDING_HUMAN_REVIEW']} imagen(es)."
        )
    if status_counts["ANNOTATED_VERIFIED"] == 0:
        blocking_reasons.append("0 imagenes con estado ANNOTATED_VERIFIED.")
    if negative_verified < 60:
        blocking_reasons.append(
            f"Muestras negativas verificadas insuficientes ({negative_verified}/60 requeridas)."
        )

    missing_classes = [cls for cls in TARGET_CLASSES if class_counts[cls] == 0]
    if missing_classes:
        blocking_reasons.append(
            f"Clases sin ejemplares verificados: {', '.join(missing_classes)}."
        )
    if real_full_scale_verified == 0:
        observations.append(
            "0 imagenes REAL_FULL_SCALE (solo modelos a escala / recapturas de pantalla)."
        )

    if blocking_reasons:
        verdict = "BENCHMARK INCOMPLETE"
    elif observations:
        verdict = "BENCHMARK READY WITH OBSERVATIONS"
    else:
        verdict = "BENCHMARK READY"

    return {
        "verdict": verdict,
        "total_images": len(images),
        "status_counts": dict(status_counts),
        "sha_errors": sha_errors,
        "negative_verified": negative_verified,
        "real_full_scale_verified": real_full_scale_verified,
        "verified_class_counts": dict(class_counts),
        "verified_domain_counts": dict(domain_counts),
        "blocking_reasons": blocking_reasons,
        "observations": observations,
    }


def cmd_status(args: argparse.Namespace) -> int:
    """Imprime el estado de integridad y completitud del manifiesto."""
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    report = assess_manifest_readiness(manifest, Path(args.corpus_root))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.strict and report["verdict"] == "BENCHMARK INCOMPLETE":
        return 2
    return 0


def classify_relative_size(bbox: list[int], width: int, height: int) -> str:
    """Clasifica el tamano relativo del bounding box respecto al area del frame."""
    area_ratio = ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) / max(1, width * height)
    if area_ratio < 0.02:
        return "SMALL"
    if area_ratio <= 0.15:
        return "MEDIUM"
    return "LARGE"


def cmd_import_csv(args: argparse.Namespace) -> int:
    """Importa anotaciones manuales desde CSV validando esquema y rangos."""
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    by_id = {img["image_id"]: img for img in manifest["images"]}
    now_iso = datetime.now(timezone.utc).isoformat()
    grouped_rows: dict[str, list[dict[str, str]]] = {}

    with Path(args.csv).open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            grouped_rows.setdefault(row["image_id"], []).append(row)

    updated = 0
    for image_id, rows in grouped_rows.items():
        if image_id not in by_id:
            raise ValueError(f"image_id desconocido en CSV: {image_id}")
        rec = by_id[image_id]
        row_statuses = {r["annotation_status"].strip() for r in rows if r["annotation_status"].strip()}
        if "ANNOTATED_VERIFIED" not in row_statuses and "EXCLUDED" not in row_statuses:
            continue

        if "EXCLUDED" in row_statuses:
            rec["annotation_status"] = "EXCLUDED"
            rec["annotations"] = []
            updated += 1
            continue

        first = rows[0]
        is_neg = first.get("is_negative_sample", "").strip().lower() == "true" or (
            first.get("class_label", "").strip().upper() == "NEGATIVE"
        )
        new_anns: list[dict[str, Any]] = []
        if is_neg:
            rec["is_negative_sample"] = True
            rec["annotation_status"] = "ANNOTATED_VERIFIED"
            rec["annotations"] = []
            updated += 1
            continue

        for idx, row in enumerate(rows, start=1):
            cls_label = row["class_label"].strip().upper()
            if not cls_label:
                continue
            if cls_label not in ALLOWED_ANNOTATION_CLASSES:
                raise ValueError(f"{image_id}: clase invalida '{cls_label}'")
            x1, y1, x2, y2 = (int(row["x_min"]), int(row["y_min"]), int(row["x_max"]), int(row["y_max"]))
            if not (0 <= x1 < x2 <= rec["width"] and 0 <= y1 < y2 <= rec["height"]):
                raise ValueError(f"{image_id}: bbox fuera de limites {[x1, y1, x2, y2]}")
            vis = float(row["visibility_ratio"] or "1.0")
            if not (0.0 <= vis <= 1.0):
                raise ValueError(f"{image_id}: visibility_ratio invalido {vis}")
            occ = (row["occlusion_level"].strip().upper() or "NONE")
            if occ not in {"NONE", "PARTIAL", "HEAVY"}:
                raise ValueError(f"{image_id}: occlusion_level invalido '{occ}'")
            bbox = [x1, y1, x2, y2]
            is_border = x1 <= 2 or y1 <= 2 or x2 >= (rec["width"] - 2) or y2 >= (rec["height"] - 2)
            new_anns.append(
                {
                    "annotation_id": f"{image_id}_A{idx:02d}",
                    "image_id": image_id,
                    "class_label": cls_label,
                    "bbox_xyxy": bbox,
                    "visibility_ratio": round(vis, 3),
                    "occlusion_level": occ,
                    "relative_size": classify_relative_size(bbox, rec["width"], rec["height"]),
                    "estimated_distance": row.get("estimated_distance", "").strip().upper() or "UNKNOWN",
                    "lighting_local": row.get("lighting_local", "").strip().upper() or rec["lighting_condition"],
                    "is_scale_model": row.get("is_scale_model", "").strip().lower() == "true",
                    "is_partial_border": is_border,
                    "ignore_reason": row.get("ignore_reason", "").strip() or None,
                    "annotator_id": row.get("annotator_id", "").strip() or "human_annotator",
                    "annotated_at_utc": now_iso,
                }
            )
        if not new_anns:
            raise ValueError(f"{image_id}: ANNOTATED_VERIFIED sin cajas ni marca is_negative_sample.")
        rec["is_negative_sample"] = False
        rec["annotation_status"] = "ANNOTATED_VERIFIED"
        rec["annotations"] = new_anns
        updated += 1

    out_path = Path(args.output)
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Manifiesto actualizado escrito en {out_path} (imagenes actualizadas: {updated}).")
    return 0


def compute_iou(box_a: list[int] | list[float], box_b: list[int] | list[float]) -> float:
    """Calcula Interseccion sobre Union entre dos cajas [x1, y1, x2, y2]."""
    ix1, iy1 = max(box_a[0], box_b[0]), max(box_a[1], box_b[1])
    ix2, iy2 = min(box_a[2], box_b[2]), min(box_a[3], box_b[3])
    iw = max(0.0, float(ix2 - ix1))
    ih = max(0.0, float(iy2 - iy1))
    inter = iw * ih
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, float((box_a[2] - box_a[0]) * (box_a[3] - box_a[1])))
    area_b = max(0.0, float((box_b[2] - box_b[0]) * (box_b[3] - box_b[1])))
    union = area_a + area_b - inter
    return inter / union if union > 0.0 else 0.0


def compute_ioa(pred_box: list[float], ignore_box: list[int]) -> float:
    """Calcula fraccion de pred_box cubierta por una region IGNORE."""
    ix1, iy1 = max(pred_box[0], ignore_box[0]), max(pred_box[1], ignore_box[1])
    ix2, iy2 = min(pred_box[2], ignore_box[2]), min(pred_box[3], ignore_box[3])
    inter = max(0.0, float(ix2 - ix1)) * max(0.0, float(iy2 - iy1))
    area_p = max(1e-6, float((pred_box[2] - pred_box[0]) * (pred_box[3] - pred_box[1])))
    return inter / area_p


def compute_coco_101_ap(recalls: list[float], precisions: list[float]) -> float:
    """Calcula Average Precision mediante interpolacion COCO de 101 puntos."""
    if not recalls or not precisions:
        return 0.0
    r_arr = np.asarray([0.0] + recalls + [1.0], dtype=np.float64)
    p_arr = np.asarray([1.0] + precisions + [0.0], dtype=np.float64)
    for idx in range(len(p_arr) - 2, -1, -1):
        p_arr[idx] = max(p_arr[idx], p_arr[idx + 1])
    thresholds = np.linspace(0.0, 1.0, 101)
    ap_vals = [float(p_arr[np.searchsorted(r_arr[:-1], thr, side="left")]) for thr in thresholds]
    return float(np.mean(ap_vals))


def evaluate_class_ap(
    gt_by_image: dict[str, list[dict[str, Any]]],
    ignore_by_image: dict[str, list[list[int]]],
    preds: list[dict[str, Any]],
    iou_thr: float,
) -> dict[str, Any]:
    """Evalua TP, FP, FN y AP para una clase y un umbral IoU dado."""
    total_gt = sum(len(v) for v in gt_by_image.values())
    matched_flags = {img_id: [False] * len(boxes) for img_id, boxes in gt_by_image.items()}
    sorted_preds = sorted(preds, key=lambda p: p["confidence"], reverse=True)

    tps: list[int] = []
    fps: list[int] = []

    for pred in sorted_preds:
        img_id = pred["image_id"]
        gt_boxes = gt_by_image.get(img_id, [])
        best_iou = 0.0
        best_idx = -1
        for idx, gt in enumerate(gt_boxes):
            if matched_flags[img_id][idx]:
                continue
            iou = compute_iou(pred["bbox"], gt["bbox_xyxy"])
            if iou > best_iou:
                best_iou = iou
                best_idx = idx

        if best_idx >= 0 and best_iou >= iou_thr:
            matched_flags[img_id][best_idx] = True
            tps.append(1)
            fps.append(0)
        else:
            ignored = any(
                compute_ioa(pred["bbox"], ign) >= 0.50 for ign in ignore_by_image.get(img_id, [])
            )
            if not ignored:
                tps.append(0)
                fps.append(1)

    tp_sum = int(sum(tps))
    fp_sum = int(sum(fps))
    fn_sum = max(0, total_gt - tp_sum)
    precision = tp_sum / (tp_sum + fp_sum) if (tp_sum + fp_sum) > 0 else (1.0 if total_gt == 0 else 0.0)
    recall = tp_sum / total_gt if total_gt > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    cum_tp = np.cumsum(tps) if tps else np.asarray([], dtype=np.float64)
    cum_fp = np.cumsum(fps) if fps else np.asarray([], dtype=np.float64)
    recalls = (cum_tp / total_gt).tolist() if total_gt > 0 and len(cum_tp) > 0 else []
    precisions = (cum_tp / np.maximum(1.0, cum_tp + cum_fp)).tolist() if len(cum_tp) > 0 else []
    ap = compute_coco_101_ap(recalls, precisions) if total_gt > 0 else None

    return {
        "gt_count": total_gt,
        "tp": tp_sum,
        "fp": fp_sum,
        "fn": fn_sum,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "ap": round(ap, 4) if ap is not None else None,
    }


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Ejecuta evaluacion reproducible solo si el benchmark cuenta con Ground Truth."""
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    corpus_root = Path(args.corpus_root)
    readiness = assess_manifest_readiness(manifest, corpus_root)

    if readiness["status_counts"].get("PENDING_HUMAN_REVIEW", 0) > 0 or readiness["sha_errors"] or (
        readiness["status_counts"].get("ANNOTATED_VERIFIED", 0) == 0
    ) or readiness["negative_verified"] < args.min_negatives:
        print(
            "BENCHMARK INCOMPLETE — Evaluation refused until manual Ground Truth and negative samples are verified.",
            file=sys.stderr,
        )
        print(json.dumps(readiness, indent=2, ensure_ascii=False), file=sys.stderr)
        return 2

    import torch
    from ultralytics import YOLO

    weights_path = Path(args.weights)
    model = YOLO(str(weights_path))
    verified_images = [
        img
        for img in manifest["images"]
        if img["annotation_status"] == "ANNOTATED_VERIFIED"
        and (args.include_stock or img["source_domain"] != "SYNTHETIC_STOCK")
    ]

    preds_by_class: dict[str, list[dict[str, Any]]] = {c: [] for c in TARGET_CLASSES}
    gt_by_class_img: dict[str, dict[str, list[dict[str, Any]]]] = {c: {} for c in TARGET_CLASSES}
    ignore_by_img: dict[str, list[list[int]]] = {}
    latencies_ms: list[float] = []

    for img_rec in verified_images:
        img_id = img_rec["image_id"]
        for ann in img_rec["annotations"]:
            if ann["class_label"] == "IGNORE":
                ignore_by_img.setdefault(img_id, []).append(ann["bbox_xyxy"])
            elif ann["class_label"] in TARGET_CLASSES:
                gt_by_class_img[ann["class_label"]].setdefault(img_id, []).append(ann)

        frame = cv2.imread(str(corpus_root / img_rec["rel_path"]))
        if args.device.startswith("cuda") and torch.cuda.is_available():
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        results = model.predict(
            source=frame,
            imgsz=args.imgsz,
            conf=args.conf,
            iou=args.iou,
            agnostic_nms=args.agnostic_nms,
            classes=list(COCO_ID_TO_BENCH_CLASS.keys()),
            device=args.device,
            verbose=False,
        )
        if args.device.startswith("cuda") and torch.cuda.is_available():
            torch.cuda.synchronize()
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            continue
        for cls_id, conf_val, xyxy in zip(boxes.cls.tolist(), boxes.conf.tolist(), boxes.xyxy.tolist()):
            cls_name = COCO_ID_TO_BENCH_CLASS.get(int(cls_id))
            if cls_name:
                preds_by_class[cls_name].append(
                    {"image_id": img_id, "confidence": float(conf_val), "bbox": xyxy}
                )

    iou_grid = [round(0.50 + 0.05 * idx, 2) for idx in range(10)]
    per_class: dict[str, Any] = {}
    for cls_name in TARGET_CLASSES:
        res_50 = evaluate_class_ap(gt_by_class_img[cls_name], ignore_by_img, preds_by_class[cls_name], 0.50)
        aps = [
            evaluate_class_ap(gt_by_class_img[cls_name], ignore_by_img, preds_by_class[cls_name], thr)["ap"]
            for thr in iou_grid
        ]
        valid_aps = [v for v in aps if v is not None]
        res_50["map50_95"] = round(float(np.mean(valid_aps)), 4) if valid_aps else None
        per_class[cls_name] = res_50

    DEFAULT_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_payload = {
        "dataset_version": manifest["dataset_version"],
        "manifest_sha256": compute_sha256(manifest_path),
        "evaluation_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "weights_path": str(weights_path),
        "weights_sha256": compute_sha256(weights_path),
        "inference_config": {
            "imgsz": args.imgsz,
            "conf": args.conf,
            "iou": args.iou,
            "agnostic_nms": args.agnostic_nms,
            "device": args.device,
        },
        "images_evaluated": len(verified_images),
        "mean_latency_ms": round(float(np.mean(latencies_ms)), 2) if latencies_ms else None,
        "per_class": per_class,
    }
    run_file = DEFAULT_RUNS_DIR / f"eval_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    run_file.write_text(json.dumps(run_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(run_payload, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construye el parser CLI de VIGIA-BENCH-v1."""
    parser = argparse.ArgumentParser(description="Herramienta reproducible para VIGIA-BENCH-v1.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_seed = sub.add_parser("build-seed", help="Inventariar corpus y generar manifest semilla y CSV.")
    p_seed.add_argument("--corpus-root", default=str(DEFAULT_CORPUS_ROOT))
    p_seed.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    p_seed.add_argument("--csv", default=str(DEFAULT_CSV))
    p_seed.add_argument("--force", action="store_true")

    p_status = sub.add_parser("status", help="Verificar hashes SHA-256 y dictamen de completitud.")
    p_status.add_argument("--corpus-root", default=str(DEFAULT_CORPUS_ROOT))
    p_status.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    p_status.add_argument("--strict", action="store_true")

    p_imp = sub.add_parser("import-csv", help="Importar anotaciones manuales verificadas desde CSV.")
    p_imp.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    p_imp.add_argument("--csv", default=str(DEFAULT_CSV))
    p_imp.add_argument("--output", default=str(BENCH_DIR / "manifest_v1_annotated.json"))

    p_eval = sub.add_parser("evaluate", help="Ejecutar protocolo de evaluacion (solo con GT completo).")
    p_eval.add_argument("--corpus-root", default=str(DEFAULT_CORPUS_ROOT))
    p_eval.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    p_eval.add_argument("--weights", default=str(REPO_ROOT / "yolo11n.pt"))
    p_eval.add_argument("--imgsz", type=int, default=640)
    p_eval.add_argument("--conf", type=float, default=0.25)
    p_eval.add_argument("--iou", type=float, default=0.45)
    p_eval.add_argument("--agnostic-nms", action="store_true")
    p_eval.add_argument("--device", default="cuda:0")
    p_eval.add_argument("--min-negatives", type=int, default=1)
    p_eval.add_argument("--include-stock", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada CLI."""
    args = build_parser().parse_args(argv)
    if args.command == "build-seed":
        return cmd_build_seed(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "import-csv":
        return cmd_import_csv(args)
    return cmd_evaluate(args)


if __name__ == "__main__":
    raise SystemExit(main())
