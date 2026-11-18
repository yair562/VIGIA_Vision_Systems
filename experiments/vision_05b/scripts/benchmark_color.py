"""
experiments/vision_05b/scripts/benchmark_color.py
==================================================
Script formal de evaluación cuantitativa, benchmark fotométrico y perfilado
de latencia para el clasificador de color vehicular (Fase VISION-05B).

Genera:
- Evaluación de calibración sintética (13 parches de referencia).
- Evaluación operativa sobre detecciones confirmadas en ROI (primary_roi_070).
- Evaluación exhaustiva sobre las 279 imágenes únicas del corpus congelado.
- Perfilado de latencia CPU (ms, FPS) y consumo.
- Exportación estructurada a benchmark_color_results.json.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

# Configuración de rutas del repositorio
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from VIGIA_Vision.detection.color_classifier import (
    ColorClassificationStatus,
    VehicleColor,
    VehicleColorClassifier,
    VehicleColorConfig,
    VehicleColorResult,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

INVENTORY_PATH = REPO_ROOT / "experiments" / "vision_05a" / "results" / "etapa_a_b_classified_inventory.json"
EVIDENCIAS_DIR = REPO_ROOT / "evidencias_vigia"
OUTPUT_JSON_PATH = REPO_ROOT / "experiments" / "vision_05b" / "results" / "benchmark_color_results.json"


def resolve_ground_truth_for_candidate(
    visual_notes: str,
    cand_label: str,
    cand_bbox: Tuple[int, int, int, int],
    file_name: str,
) -> Tuple[Optional[str], str]:
    """
    Resuelve el color Ground Truth del vehículo específico detectado por la caja.
    Distingue cuando en un mismo frame coexisten autobús amarillo y automóvil rojo.
    """
    vn = visual_notes.lower()

    # Condición de iluminación
    if "baja iluminación" in vn or "penumbra" in vn or "severa" in vn:
        lighting = "LOW_LIGHT"
    elif "luz intensa" in vn or "reflejo" in vn or "solar intensa" in vn or "contraluz" in vn:
        lighting = "GLARE_OR_HIGH_CONTRAST"
    else:
        lighting = "NORMAL"

    # Resolución precisa del vehículo de la caja delimitadora
    if "bus.jpg" in file_name or "autobús urbano azul" in vn or "auto azul oscuro" in vn:
        return "BLUE", lighting

    if cand_label == "bus" and "amarillo" in vn:
        return "YELLOW", lighting

    if "convertible rosa" in vn:
        return "OTHER", lighting

    if "convertible cian" in vn:
        return "BLUE", lighting

    if "auto deportivo rojo" in vn or "auto rojo" in vn:
        return "RED", lighting

    if "escala gris" in vn:
        return "GRAY", lighting

    if "recaptura" in vn or "cuadrícula" in vn or "google imágenes" in vn:
        return "OTHER", lighting

    if "amarillo" in vn:
        return "YELLOW", lighting

    return None, lighting


def build_synthetic_calibration_suite() -> List[Tuple[str, np.ndarray, str]]:
    """Genera parches y casos controlados para las 12 categorías del contrato."""
    cases = []
    size = (120, 160)

    def _solid(b: int, g: int, r: int) -> np.ndarray:
        arr = np.zeros((size[0], size[1], 3), dtype=np.uint8)
        arr[:, :] = (b, g, r)
        return arr

    # 1. Colores cromáticos
    cases.append(("RED_PURE", _solid(20, 20, 220), "RED"))
    cases.append(("BLUE_PURE", _solid(220, 40, 20), "BLUE"))
    cases.append(("YELLOW_PURE", _solid(20, 220, 230), "YELLOW"))
    cases.append(("GREEN_PURE", _solid(35, 185, 30), "GREEN"))
    cases.append(("ORANGE_PURE", _solid(15, 130, 240), "ORANGE"))
    cases.append(("BROWN_PURE", _solid(20, 50, 100), "BROWN"))

    # 2. Acromáticos
    cases.append(("WHITE_PURE", _solid(240, 240, 240), "WHITE"))
    cases.append(("BLACK_PURE", _solid(35, 35, 35), "BLACK"))
    cases.append(("GRAY_PURE", _solid(100, 100, 100), "GRAY"))
    cases.append(("SILVER_PURE", _solid(165, 165, 165), "SILVER"))

    # 3. OTHER y UNKNOWN
    cases.append(("PINK_OTHER", _solid(200, 20, 220), "OTHER"))
    cases.append(("EXTREME_DARK_UNKNOWN", _solid(6, 6, 8), "UNKNOWN"))
    cases.append(("EXTREME_GLARE_UNKNOWN", _solid(255, 255, 255), "UNKNOWN"))

    return cases


def run_color_benchmark() -> Dict[str, Any]:
    logger.info("Iniciando Benchmark de Clasificación de Color Vehicular (VISION-05B)...")

    if not INVENTORY_PATH.is_file():
        raise FileNotFoundError(f"Inventario no encontrado: {INVENTORY_PATH}")

    with open(INVENTORY_PATH, "r", encoding="utf-8") as f:
        inv = json.load(f)

    items = inv.get("items", [])
    unique_items = [it for it in items if not it.get("is_exact_duplicate", False)]
    logger.info("Cargadas %d imágenes únicas no duplicadas del corpus congelado.", len(unique_items))

    classifier = VehicleColorClassifier()

    # 1. Suite sintética de calibración (13 casos)
    synth_cases = build_synthetic_calibration_suite()
    synth_results = []
    synth_passed = 0

    for name, img, expected in synth_cases:
        h, w = img.shape[:2]
        t0 = time.perf_counter()
        res = classifier.classify(img, (0, 0, w, h), detection_confidence=1.0)
        dt_ms = (time.perf_counter() - t0) * 1000.0

        is_match = (res.color.value == expected)
        if is_match:
            synth_passed += 1

        synth_results.append({
            "case_name": name,
            "expected_color": expected,
            "predicted_color": res.color.value,
            "confidence": res.confidence,
            "status": res.status.value,
            "is_match": is_match,
            "latency_ms": round(dt_ms, 3),
            "reason": res.reason,
        })

    logger.info(
        "Suite sintética completada: %d/%d casos exitosos (%.1f%%).",
        synth_passed,
        len(synth_cases),
        (synth_passed / len(synth_cases)) * 100.0,
    )

    # 2. Evaluación Operativa: Vehículos confirmados dentro del ROI (primary_roi_070)
    roi_records = []
    roi_latencies: List[float] = []
    roi_color_stats = defaultdict(lambda: {"total": 0, "correct": 0, "unknown": 0, "wrong": 0})
    roi_lighting_stats = defaultdict(lambda: {"total": 0, "correct": 0, "unknown": 0, "wrong": 0})

    # 3. Evaluación Exhaustiva: Todo el corpus de 279 imágenes únicas
    exhaustive_records = []
    exhaustive_latencies: List[float] = []
    unknown_reasons = Counter()

    for it in unique_items:
        rel_path = it.get("relative_path")
        full_img_path = EVIDENCIAS_DIR / rel_path

        if not full_img_path.is_file():
            continue

        img_bgr = cv2.imread(str(full_img_path))
        if img_bgr is None:
            continue

        vn = it.get("confirmed_visual_classification", {}).get("visual_notes", "")
        yolo_data = it.get("yolo26x", {})

        # --- A) Evaluación Operativa ROI ---
        roi_cand = yolo_data.get("primary_roi_070")
        if roi_cand:
            bbox = roi_cand["bbox"]
            det_label = roi_cand["label"]
            det_conf = roi_cand["confidence"]

            gt_color, lighting = resolve_ground_truth_for_candidate(vn, det_label, bbox, it["file_name"])

            t0 = time.perf_counter()
            res = classifier.classify(img_bgr, bbox, detected_class=det_label, detection_confidence=det_conf)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            roi_latencies.append(dt_ms)

            is_match = (res.color.value == gt_color) if gt_color else False
            if gt_color:
                roi_color_stats[gt_color]["total"] += 1
                roi_lighting_stats[lighting]["total"] += 1
                if is_match:
                    roi_color_stats[gt_color]["correct"] += 1
                    roi_lighting_stats[lighting]["correct"] += 1
                elif res.color.value == "UNKNOWN":
                    roi_color_stats[gt_color]["unknown"] += 1
                    roi_lighting_stats[lighting]["unknown"] += 1
                else:
                    roi_color_stats[gt_color]["wrong"] += 1
                    roi_lighting_stats[lighting]["wrong"] += 1

            roi_records.append({
                "sample_id": it.get("sample_id"),
                "file_name": it.get("file_name"),
                "relative_path": rel_path,
                "cand_label": det_label,
                "cand_confidence": det_conf,
                "ground_truth_color": gt_color,
                "predicted_color": res.color.value,
                "confidence": res.confidence,
                "status": res.status.value,
                "is_match": is_match,
                "lighting_condition": lighting,
                "latency_ms": round(dt_ms, 3),
                "reason": res.reason,
            })

        # --- B) Evaluación Exhaustiva sobre 279 ---
        cand = (
            roi_cand
            or yolo_data.get("primary_025")
            or (yolo_data.get("all_candidates_010") and yolo_data["all_candidates_010"][0])
        )
        if cand:
            ex_bbox = cand["bbox"]
            ex_label = cand["label"]
            ex_conf = cand["confidence"]
        else:
            h, w = img_bgr.shape[:2]
            ex_bbox = (int(w * 0.15), int(h * 0.20), int(w * 0.85), int(h * 0.80))
            ex_label = "car"
            ex_conf = 0.55

        ex_gt, ex_light = resolve_ground_truth_for_candidate(vn, ex_label, ex_bbox, it["file_name"])

        t0 = time.perf_counter()
        ex_res = classifier.classify(img_bgr, ex_bbox, detected_class=ex_label, detection_confidence=ex_conf)
        ex_dt_ms = (time.perf_counter() - t0) * 1000.0
        exhaustive_latencies.append(ex_dt_ms)

        if ex_res.color.value == "UNKNOWN":
            reason_key = ex_res.reason.split("(")[0].strip()
            unknown_reasons[reason_key] += 1

        exhaustive_records.append({
            "sample_id": it.get("sample_id"),
            "file_name": it.get("file_name"),
            "relative_path": rel_path,
            "ground_truth_color": ex_gt,
            "predicted_color": ex_res.color.value,
            "confidence": ex_res.confidence,
            "status": ex_res.status.value,
            "is_match": (ex_res.color.value == ex_gt) if ex_gt else False,
            "latency_ms": round(ex_dt_ms, 3),
            "reason": ex_res.reason,
        })

    # Resumen cuantitativo Operativo (ROI)
    roi_evaluable = sum(v["total"] for v in roi_color_stats.values())
    roi_correct = sum(v["correct"] for v in roi_color_stats.values())
    roi_unknown = sum(v["unknown"] for v in roi_color_stats.values())
    roi_known_evaluable = roi_evaluable - roi_unknown

    roi_accuracy_overall = (roi_correct / roi_evaluable) if roi_evaluable > 0 else 0.0
    roi_accuracy_effective = (roi_correct / roi_known_evaluable) if roi_known_evaluable > 0 else 0.0
    roi_unknown_rate = (roi_unknown / roi_evaluable) if roi_evaluable > 0 else 0.0

    # Resumen Latencias
    all_lat = np.array(roi_latencies) if roi_latencies else np.array([0.0])
    latency_summary = {
        "mean_ms": round(float(all_lat.mean()), 3),
        "median_ms": round(float(np.median(all_lat)), 3),
        "p90_ms": round(float(np.percentile(all_lat, 90)), 3),
        "p99_ms": round(float(np.percentile(all_lat, 99)), 3),
        "min_ms": round(float(all_lat.min()), 3),
        "max_ms": round(float(all_lat.max()), 3),
        "throughput_fps": round(1000.0 / float(all_lat.mean()), 1) if float(all_lat.mean()) > 0 else 0.0,
    }

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "synthetic_suite_results": {
            "total": len(synth_cases),
            "passed": synth_passed,
            "pass_rate_pct": round((synth_passed / len(synth_cases)) * 100.0, 2),
            "details": synth_results,
        },
        "operational_roi_evaluation": {
            "total_roi_evaluable_samples": roi_evaluable,
            "correct_predictions": roi_correct,
            "unknown_abstentions": roi_unknown,
            "wrong_predictions": roi_evaluable - roi_correct - roi_unknown,
            "accuracy_overall_pct": round(roi_accuracy_overall * 100.0, 2),
            "accuracy_effective_excluding_unknown_pct": round(roi_accuracy_effective * 100.0, 2),
            "unknown_rate_pct": round(roi_unknown_rate * 100.0, 2),
            "color_breakdown": {
                k: {
                    "total": v["total"],
                    "correct": v["correct"],
                    "accuracy_pct": round((v["correct"] / v["total"]) * 100.0, 2) if v["total"] > 0 else 0.0,
                    "unknown": v["unknown"],
                    "wrong": v["wrong"],
                }
                for k, v in sorted(roi_color_stats.items())
            },
            "lighting_breakdown": {
                k: {
                    "total": v["total"],
                    "correct": v["correct"],
                    "accuracy_pct": round((v["correct"] / v["total"]) * 100.0, 2) if v["total"] > 0 else 0.0,
                    "unknown": v["unknown"],
                    "wrong": v["wrong"],
                }
                for k, v in sorted(roi_lighting_stats.items())
            },
        },
        "exhaustive_corpus_evaluation": {
            "total_unique_images": len(exhaustive_records),
            "unknown_reasons_breakdown": dict(unknown_reasons),
        },
        "latency_profile": latency_summary,
        "sample_roi_records": roi_records,
    }

    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    logger.info("Benchmark completado y guardado en: %s", OUTPUT_JSON_PATH)
    logger.info("MÉTRICAS OPERATIVAS EN ROI (Vehículos con confianza >= 0.70):")
    logger.info("  Muestras evaluadas: %d", roi_evaluable)
    logger.info("  Aciertos: %d (%.2f%%)", roi_correct, roi_accuracy_overall * 100.0)
    logger.info("  Precisión Efectiva (excluyendo UNKNOWN): %.2f%%", roi_accuracy_effective * 100.0)
    logger.info("  Tasa de Abstención UNKNOWN: %.2f%% (%d casos)", roi_unknown_rate * 100.0, roi_unknown)
    logger.info("  Latencia Media: %.3f ms (Throughput: %.1f FPS)", latency_summary["mean_ms"], latency_summary["throughput_fps"])

    return summary


if __name__ == "__main__":
    run_color_benchmark()
