"""
Paso 5 (VISION-03C.1): Evaluacion diagnostica sobre el corpus de evidencias
disponible, manteniendo estricta separacion por dominio de origen:
  - Dom A: SCREEN_RECAPTURE (20261111, CAM-ENTRADA, n=11)
  - Dom B: SCALE_MODEL_LAB  (20261114, CAM-ENTRADA n=15 + CAM-SALIDA n=130, total n=145)

IMPORTANTE: Este script realiza analisis diagnostico comparativo entre modelos
(yolo11n, yolo11x, yolo26x nms=False e2e, yolo26x nms=True) sin declarar Ground Truth
humano ni mAP/Recall reales de carretera (reservados para VIGIA-BENCH-REAL).
"""

from __future__ import annotations

import gc
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import cv2
import numpy as np
import torch
from ultralytics import YOLO

EXP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = EXP_ROOT.parents[1]
MANIFEST_PATH = REPO_ROOT / "experiments" / "vigia_ml" / "data" / "processed" / "manifest_v1.json"

COCO_VEHICLE_NAMES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def _is_partial_edge(xyxy: List[float], w: int, h: int, margin: float = 5.0) -> bool:
    x1, y1, x2, y2 = xyxy
    return x1 <= margin or y1 <= margin or x2 >= (w - margin) or y2 >= (h - margin)


def _evaluate_model_on_corpus(
    label: str,
    weights_path: Path,
    records: List[Dict[str, Any]],
    *,
    imgsz: int,
    quantize16: bool,
    nms_arg: bool | None,
) -> Dict[str, Any]:
    torch.cuda.empty_cache()
    gc.collect()

    model = YOLO(str(weights_path))
    predict_kwargs: Dict[str, Any] = {
        "imgsz": imgsz,
        "conf": 0.25,
        "iou": 0.45,
        "classes": [2, 3, 5, 7],
        "device": "cuda:0",
        "verbose": False,
    }
    if quantize16:
        predict_kwargs["quantize"] = 16
    if nms_arg is not None:
        predict_kwargs["nms"] = nms_arg

    per_image: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        rel = rec["image_path"].replace("../../", "")
        img_path = REPO_ROOT / rel
        frame = cv2.imread(str(img_path))
        if frame is None:
            continue
        h, w = frame.shape[:2]
        frame_area = float(w * h)
        res = model.predict(frame, **predict_kwargs)[0]

        boxes_out = []
        if res.boxes is not None:
            for b in res.boxes:
                cid = int(b.cls[0].item())
                conf = float(b.conf[0].item())
                x1, y1, x2, y2 = [float(v) for v in b.xyxy[0].tolist()]
                area_ratio = max(0.0, (x2 - x1) * (y2 - y1)) / frame_area
                boxes_out.append(
                    {
                        "cls_id": cid,
                        "label": COCO_VEHICLE_NAMES.get(cid, str(cid)),
                        "conf": round(conf, 4),
                        "xyxy": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                        "area_ratio": round(area_ratio, 4),
                        "is_small": area_ratio < 0.05,
                        "is_partial_edge": _is_partial_edge([x1, y1, x2, y2], w, h),
                    }
                )
        boxes_out.sort(key=lambda d: d["conf"], reverse=True)
        top_conf = boxes_out[0]["conf"] if boxes_out else 0.0
        per_image[rec["sample_id"]] = {
            "sample_id": rec["sample_id"],
            "file": img_path.name,
            "date_folder": rec["date_folder"],
            "source_domain": rec["source_domain"],
            "camera_id": rec["camera_id"],
            "unique_rep": rec["exact_duplicate_of"] is None,
            "luminance_mean_y": rec["luminance_mean_y"],
            "sharpness_laplacian": rec["sharpness_laplacian"],
            "num_detections": len(boxes_out),
            "top_conf": top_conf,
            "top_label": boxes_out[0]["label"] if boxes_out else None,
            "boxes": boxes_out,
        }

    ab_model = getattr(getattr(model, "predictor", None), "model", None)
    effective_e2e = bool(getattr(ab_model, "end2end", False))
    del model
    torch.cuda.empty_cache()
    gc.collect()

    # Resumen por dominio y por camara
    slices: Dict[str, List[Dict[str, Any]]] = {
        "SCREEN_RECAPTURE__ALL_20261111": [
            v for v in per_image.values() if v["source_domain"] == "SCREEN_RECAPTURE"
        ],
        "SCALE_MODEL_LAB__ALL_20261114": [
            v for v in per_image.values() if v["source_domain"] == "SCALE_MODEL_LAB"
        ],
        "SCALE_MODEL_LAB__CAM_ENTRADA": [
            v for v in per_image.values()
            if v["source_domain"] == "SCALE_MODEL_LAB" and v["camera_id"] == "CAM-ENTRADA"
        ],
        "SCALE_MODEL_LAB__CAM_SALIDA": [
            v for v in per_image.values()
            if v["source_domain"] == "SCALE_MODEL_LAB" and v["camera_id"] == "CAM-SALIDA"
        ],
        "SCALE_MODEL_LAB__DARK_Y_LT_40": [
            v for v in per_image.values()
            if v["source_domain"] == "SCALE_MODEL_LAB" and v["luminance_mean_y"] < 40.0
        ],
        "SANDBOX_UNIQUE_REPS__20261111_20261114": [
            v for v in per_image.values() if v["unique_rep"]
        ],
    }

    summary: Dict[str, Any] = {}
    for slice_name, rows in slices.items():
        n = len(rows)
        all_boxes = [b for r in rows for b in r["boxes"]]
        top_confs = [r["top_conf"] for r in rows if r["num_detections"] > 0]
        all_confs = [b["conf"] for b in all_boxes]
        cls_top = Counter(r["top_label"] for r in rows if r["top_label"] is not None)
        cls_all = Counter(b["label"] for b in all_boxes)
        summary[slice_name] = {
            "images": n,
            "frames_with_det_ge_0_25": sum(1 for r in rows if r["top_conf"] >= 0.25),
            "frames_with_det_ge_0_50": sum(1 for r in rows if r["top_conf"] >= 0.50),
            "frames_with_det_ge_0_70": sum(1 for r in rows if r["top_conf"] >= 0.70),
            "total_boxes": len(all_boxes),
            "small_boxes_lt_5pct": sum(1 for b in all_boxes if b["is_small"]),
            "partial_edge_boxes": sum(1 for b in all_boxes if b["is_partial_edge"]),
            "top1_class_counts": dict(cls_top),
            "all_boxes_class_counts": dict(cls_all),
            "top_conf_mean": round(float(np.mean(top_confs)), 4) if top_confs else 0.0,
            "top_conf_median": round(float(np.median(top_confs)), 4) if top_confs else 0.0,
            "top_conf_min": round(float(np.min(top_confs)), 4) if top_confs else 0.0,
            "top_conf_max": round(float(np.max(top_confs)), 4) if top_confs else 0.0,
            "all_boxes_conf_mean": round(float(np.mean(all_confs)), 4) if all_confs else 0.0,
        }

    return {
        "config_label": label,
        "weights": weights_path.name,
        "imgsz": imgsz,
        "precision": "FP16" if quantize16 else "FP32",
        "nms_arg": nms_arg,
        "effective_end2end": effective_e2e,
        "slice_summaries": summary,
        "per_image": per_image,
    }


def main() -> None:
    torch.cuda.init()
    _ = torch.zeros(1, device="cuda:0")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    records = [
        r for r in manifest["records"]
        if r.get("date_folder") in ("20261111", "20261114") and r.get("is_readable", True)
    ]

    weights_dir = EXP_ROOT / "weights"
    configs = [
        ("yolo11n_640_fp32_baseline", weights_dir / "yolo11n.pt", 640, False, None),
        ("yolo11x_640_fp16", weights_dir / "yolo11x.pt", 640, True, None),
        ("yolo26x_640_fp32_e2e", weights_dir / "yolo26x.pt", 640, False, False),
        ("yolo26x_640_fp16_e2e", weights_dir / "yolo26x.pt", 640, True, False),
        ("yolo26x_800_fp16_e2e", weights_dir / "yolo26x.pt", 800, True, False),
        ("yolo26x_640_fp16_nms", weights_dir / "yolo26x.pt", 640, True, True),
    ]

    evals: Dict[str, Any] = {}
    for label, wp, imgsz, q16, nms_arg in configs:
        print(f"Evaluating {label}...")
        evals[label] = _evaluate_model_on_corpus(
            label, wp, records, imgsz=imgsz, quantize16=q16, nms_arg=nms_arg
        )

    # Identificar subconjunto borderline historico: frames de 20261114/CAM-SALIDA donde yolo11n < 0.70
    base_per_img = evals["yolo11n_640_fp32_baseline"]["per_image"]
    borderline_ids = sorted(
        sid for sid, row in base_per_img.items()
        if row["date_folder"] == "20261114"
        and row["camera_id"] == "CAM-SALIDA"
        and row["top_conf"] < 0.70
    )

    borderline_comparison: Dict[str, Any] = {"borderline_count": len(borderline_ids), "models": {}}
    for label, ev in evals.items():
        b_rows = [ev["per_image"][sid] for sid in borderline_ids]
        confs = [r["top_conf"] for r in b_rows]
        borderline_comparison["models"][label] = {
            "recovered_ge_0_70": sum(1 for c in confs if c >= 0.70),
            "recovered_ge_0_50": sum(1 for c in confs if c >= 0.50),
            "detected_ge_0_25": sum(1 for c in confs if c >= 0.25),
            "top_conf_mean": round(float(np.mean(confs)), 4) if confs else 0.0,
            "top_conf_min": round(float(np.min(confs)), 4) if confs else 0.0,
            "top_conf_max": round(float(np.max(confs)), 4) if confs else 0.0,
            "top1_classes": dict(Counter(r["top_label"] for r in b_rows if r["top_label"] is not None)),
        }

    # Compactar JSON final sin per_image completo duplicado x6, o guardar resumen + casos discordantes clave
    compact_evals = {
        k: {key: val for key, val in v.items() if key != "per_image"}
        for k, v in evals.items()
    }

    # Discrepancias de clase o deteccion entre yolo11n baseline y yolo26x_640_fp16_e2e
    y26_per_img = evals["yolo26x_640_fp16_e2e"]["per_image"]
    key_diffs = []
    for sid, b_row in base_per_img.items():
        y_row = y26_per_img[sid]
        if (
            b_row["top_label"] != y_row["top_label"]
            or abs(b_row["top_conf"] - y_row["top_conf"]) >= 0.15
            or (b_row["num_detections"] == 0) != (y_row["num_detections"] == 0)
        ):
            key_diffs.append(
                {
                    "sample_id": sid,
                    "file": b_row["file"],
                    "domain": b_row["source_domain"],
                    "camera_id": b_row["camera_id"],
                    "luminance_y": b_row["luminance_mean_y"],
                    "yolo11n_top": {"label": b_row["top_label"], "conf": b_row["top_conf"], "n": b_row["num_detections"]},
                    "yolo26x_640_fp16_e2e_top": {"label": y_row["top_label"], "conf": y_row["top_conf"], "n": y_row["num_detections"]},
                }
            )

    out_report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "corpus_counts": {
            "total_evaluated": len(records),
            "screen_recapture_20261111": sum(1 for r in records if r["source_domain"] == "SCREEN_RECAPTURE"),
            "scale_model_lab_20261114": sum(1 for r in records if r["source_domain"] == "SCALE_MODEL_LAB"),
        },
        "models": compact_evals,
        "borderline_cam_salida_lt_0_70_subset": borderline_comparison,
        "notable_differences_y11n_vs_y26x_640_fp16_e2e": key_diffs,
    }

    out_path = EXP_ROOT / "results" / "domain_evaluation.json"
    out_path.write_text(json.dumps(out_report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Domain evaluation saved to", out_path)


if __name__ == "__main__":
    main()
