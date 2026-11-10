"""
scripts/run_rect_benchmark.py
=============================
Benchmark comparativo experimental de inferencia rectangular (rect=True) vs
cuadrada estándar (rect=False) en NVIDIA RTX 4050 Laptop GPU para YOLO11n.

Evalúa de acuerdo con VIGIA-VISION-OPT-00-R2:
1. Latencia granular: preprocesamiento, inferencia, postprocesamiento y total.
2. Estadísticas de distribución: media, desviación estándar (jitter), p50, p90, p95, p99.
3. Throughput (fotogramas por segundo / FPS).
4. Utilización de memoria VRAM (pico y asignación activa).
5. Concordancia numérica de detecciones: clases, confianza (MAE) y bounding boxes (IoU y MAE).
6. Evaluación multi-proporción:
   - Landscape 16:9 (1920x1080 y 1280x720)
   - Portrait 9:16 (720x1280 y 1080x1920)
   - Portrait 3:4 (810x1080)
7. Estrés por alternancia dinámica de forma (stream heterogéneo multicanal).
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

# Asegurar raíz en sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rect_benchmark")


def calculate_iou(boxA: List[float], boxB: List[float]) -> float:
    """Calcula IoU entre dos cajas [x1, y1, x2, y2]."""
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    inter_w = max(0.0, xB - xA)
    inter_h = max(0.0, yB - yA)
    inter_area = inter_w * inter_h

    areaA = max(0.0, (boxA[2] - boxA[0]) * (boxA[3] - boxA[1]))
    areaB = max(0.0, (boxB[2] - boxB[0]) * (boxB[3] - boxB[1]))
    union_area = areaA + areaB - inter_area
    if union_area <= 0.0:
        return 0.0
    return float(inter_area / union_area)


def compute_statistics(values: List[float]) -> Dict[str, float]:
    """Calcula métricas estadísticas estándar sobre una serie de valores."""
    if not values:
        return {"mean": 0.0, "std": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "min": 0.0, "max": 0.0}
    arr = np.array(values, dtype=np.float64)
    return {
        "mean": round(float(np.mean(arr)), 3),
        "std": round(float(np.std(arr)), 3),
        "p50": round(float(np.percentile(arr, 50)), 3),
        "p90": round(float(np.percentile(arr, 90)), 3),
        "p95": round(float(np.percentile(arr, 95)), 3),
        "p99": round(float(np.percentile(arr, 99)), 3),
        "min": round(float(np.min(arr)), 3),
        "max": round(float(np.max(arr)), 3),
    }


def prepare_benchmark_dataset(repo_root: Path) -> Dict[str, np.ndarray]:
    """Carga y prepara imágenes de prueba en proporciones representativas."""
    import ultralytics
    assets_dir = Path(ultralytics.__file__).parent / "assets"
    bus_path = assets_dir / "bus.jpg"
    zidane_path = assets_dir / "zidane.jpg"

    bus_img = cv2.imread(str(bus_path))  # 810 x 1080 (3:4)
    zidane_img = cv2.imread(str(zidane_path))  # 1280 x 720 (16:9)

    dataset: Dict[str, np.ndarray] = {}

    # 1. Portrait 3:4 (810x1080)
    if bus_img is not None:
        dataset["portrait_3_4_810x1080"] = bus_img

    # 2. Landscape 16:9 (1280x720)
    if zidane_img is not None:
        dataset["landscape_16_9_1280x720"] = zidane_img

    # 3. Landscape 16:9 Full HD (1920x1080) con vehículos reales
    # Creamos un canvas 1920x1080 y ubicamos el contenido vehicular
    canvas_1080p = np.zeros((1080, 1920, 3), dtype=np.uint8)
    if bus_img is not None:
        h, w = bus_img.shape[:2]
        # centrar imagen
        x_off = (1920 - w) // 2
        canvas_1080p[:h, x_off:x_off+w] = bus_img
    dataset["landscape_16_9_1920x1080"] = canvas_1080p

    # 4. Portrait 9:16 (720x1280) - captura real VIGÍA de teléfono móvil
    real_mobile = repo_root / "evidencias_vigia" / "20261104" / "CAM-ENTRADA" / "20261104T163435_585610Z_5f6dd24bfe47_orig.jpg"
    if real_mobile.exists():
        mob_img = cv2.imread(str(real_mobile))
        if mob_img is not None:
            dataset["portrait_9_16_720x1280_real"] = mob_img
    else:
        # Sintetizar 720x1280 si no está el archivo
        canvas_720x1280 = np.zeros((1280, 720, 3), dtype=np.uint8)
        if bus_img is not None:
            scaled = cv2.resize(bus_img, (720, 960))
            canvas_720x1280[160:160+960, :] = scaled
        dataset["portrait_9_16_720x1280_real"] = canvas_720x1280

    # 5. Portrait 9:16 Full HD (1080x1920)
    canvas_9_16_fhd = np.zeros((1920, 1080, 3), dtype=np.uint8)
    if bus_img is not None:
        canvas_9_16_fhd[420:420+1080, :810] = bus_img
    dataset["portrait_9_16_1080x1920"] = canvas_9_16_fhd

    return dataset


def run_single_variant_benchmark(
    model: Any,
    dataset: Dict[str, np.ndarray],
    rect: bool,
    device: str = "cuda:0",
    imgsz: int = 640,
    conf_thresh: float = 0.25,
    iou_thresh: float = 0.45,
    warmup_iters: int = 20,
    measure_iters: int = 60,
) -> Dict[str, Any]:
    """Ejecuta mediciones detalladas para una configuración (rect=False o rect=True)."""
    import torch

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats(0)
    torch.cuda.synchronize()

    # Warm-up inicial con la primera imagen
    first_img = next(iter(dataset.values()))
    for _ in range(warmup_iters):
        torch.cuda.synchronize()
        _ = model.predict(
            source=first_img,
            imgsz=imgsz,
            rect=rect,
            device=device,
            conf=conf_thresh,
            iou=iou_thresh,
            half=False,
            verbose=False,
        )
        torch.cuda.synchronize()

    results_per_format: Dict[str, Any] = {}
    all_total_latencies: List[float] = []
    all_infer_latencies: List[float] = []
    all_detections: Dict[str, List[Dict[str, Any]]] = {}

    for name, frame in dataset.items():
        h, w = frame.shape[:2]
        ar = round(w / h, 3)

        preprocess_ms: List[float] = []
        inference_ms: List[float] = []
        postprocess_ms: List[float] = []
        total_ms: List[float] = []
        captured_dets: List[Dict[str, Any]] = []

        # Pequeño warm-up por formato si rect=True (para adaptar tamaño de entrada)
        for _ in range(5):
            torch.cuda.synchronize()
            _ = model.predict(
                source=frame,
                imgsz=imgsz,
                rect=rect,
                device=device,
                conf=conf_thresh,
                iou=iou_thresh,
                half=False,
                verbose=False,
            )
            torch.cuda.synchronize()

        for it in range(measure_iters):
            torch.cuda.synchronize()
            t0 = time.perf_counter()

            preds = model.predict(
                source=frame,
                imgsz=imgsz,
                rect=rect,
                device=device,
                conf=conf_thresh,
                iou=iou_thresh,
                half=False,
                verbose=False,
            )

            torch.cuda.synchronize()
            t1 = time.perf_counter()

            tot = (t1 - t0) * 1000.0
            total_ms.append(tot)
            all_total_latencies.append(tot)

            speed = preds[0].speed
            p = speed.get("preprocess", 0.0)
            i = speed.get("inference", 0.0)
            post = speed.get("postprocess", 0.0)

            preprocess_ms.append(p)
            inference_ms.append(i)
            postprocess_ms.append(post)
            all_infer_latencies.append(i)

            if it == 0:
                boxes = preds[0].boxes
                for box in boxes:
                    xyxy = box.xyxy[0].tolist()
                    conf = float(box.conf[0].item())
                    cls_id = int(box.cls[0].item())
                    cls_name = model.names.get(cls_id, str(cls_id))
                    captured_dets.append({
                        "cls_id": cls_id,
                        "class_name": cls_name,
                        "confidence": round(conf, 4),
                        "bbox": [round(c, 2) for c in xyxy],
                    })

        all_detections[name] = captured_dets

        # Forma de entrada interna generada por letterbox
        # Obtenemos la forma resultante
        in_shape = getattr(preds[0], "shape", None) or getattr(preds[0], "orig_shape", None)

        fps = round(1000.0 / float(np.mean(total_ms)), 2) if total_ms else 0.0

        results_per_format[name] = {
            "resolution": f"{w}x{h}",
            "aspect_ratio": ar,
            "iterations": measure_iters,
            "fps": fps,
            "total_latency_ms": compute_statistics(total_ms),
            "preprocess_latency_ms": compute_statistics(preprocess_ms),
            "inference_latency_ms": compute_statistics(inference_ms),
            "postprocess_latency_ms": compute_statistics(postprocess_ms),
            "detections_count": len(captured_dets),
        }

    vram_peak_mb = round(torch.cuda.max_memory_allocated(0) / (1024.0 * 1024.0), 2)
    vram_alloc_mb = round(torch.cuda.memory_allocated(0) / (1024.0 * 1024.0), 2)
    overall_fps = round(1000.0 / float(np.mean(all_total_latencies)), 2) if all_total_latencies else 0.0

    return {
        "rect": rect,
        "device": device,
        "overall_fps": overall_fps,
        "overall_total_latency_ms": compute_statistics(all_total_latencies),
        "overall_inference_latency_ms": compute_statistics(all_infer_latencies),
        "vram_metrics_mb": {
            "peak_allocated": vram_peak_mb,
            "current_allocated": vram_alloc_mb,
        },
        "per_format": results_per_format,
        "detections": all_detections,
    }


def run_dynamic_switching_stress_test(
    model: Any,
    dataset: Dict[str, np.ndarray],
    rect: bool,
    iterations: int = 100,
    device: str = "cuda:0",
    imgsz: int = 640,
) -> Dict[str, Any]:
    """
    Evalúa el comportamiento ante un flujo continuo con alternancia dinámica de proporciones
    (simulando cámaras de distintas relaciones de aspecto transmitiendo concurrentemente).
    """
    import torch

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats(0)
    torch.cuda.synchronize()

    frames_list = list(dataset.values())
    names_list = list(dataset.keys())
    n_frames = len(frames_list)

    total_times: List[float] = []
    inference_times: List[float] = []

    for idx in range(iterations):
        frame = frames_list[idx % n_frames]
        torch.cuda.synchronize()
        t0 = time.perf_counter()

        preds = model.predict(
            source=frame,
            imgsz=imgsz,
            rect=rect,
            device=device,
            half=False,
            verbose=False,
        )

        torch.cuda.synchronize()
        t1 = time.perf_counter()

        tot = (t1 - t0) * 1000.0
        total_times.append(tot)
        inference_times.append(preds[0].speed.get("inference", 0.0))

    vram_peak_mb = round(torch.cuda.max_memory_allocated(0) / (1024.0 * 1024.0), 2)

    return {
        "rect": rect,
        "iterations": iterations,
        "total_latency_ms": compute_statistics(total_times),
        "inference_latency_ms": compute_statistics(inference_times),
        "vram_peak_mb": vram_peak_mb,
        "fps": round(1000.0 / float(np.mean(total_times)), 2) if total_times else 0.0,
    }


def compare_rect_concordance(
    dets_sq: Dict[str, List[Dict[str, Any]]],
    dets_rc: Dict[str, List[Dict[str, Any]]],
    iou_match_threshold: float = 0.50,
) -> Dict[str, Any]:
    """Calcula concordancia entre detecciones rect=False y rect=True."""
    per_image_comp: Dict[str, Any] = {}
    all_ious: List[float] = []
    conf_diffs: List[float] = []
    coord_diffs: List[float] = []

    total_sq_boxes = 0
    total_rc_boxes = 0
    total_matched = 0

    for img_name in dets_sq:
        sq_list = dets_sq[img_name]
        rc_list = dets_rc.get(img_name, [])

        total_sq_boxes += len(sq_list)
        total_rc_boxes += len(rc_list)

        matched_in_image = 0
        img_ious = []

        unmatched_rc = list(range(len(rc_list)))

        for sq_det in sq_list:
            sq_box = sq_det["bbox"]
            sq_cls = sq_det["cls_id"]
            sq_conf = sq_det["confidence"]

            best_iou = 0.0
            best_rc_idx = -1

            for rc_idx in unmatched_rc:
                rc_det = rc_list[rc_idx]
                if rc_det["cls_id"] == sq_cls:
                    iou = calculate_iou(sq_box, rc_det["bbox"])
                    if iou > best_iou:
                        best_iou = iou
                        best_rc_idx = rc_idx

            if best_iou >= iou_match_threshold and best_rc_idx >= 0:
                matched_in_image += 1
                total_matched += 1
                unmatched_rc.remove(best_rc_idx)
                rc_det = rc_list[best_rc_idx]

                all_ious.append(best_iou)
                img_ious.append(best_iou)
                conf_diffs.append(abs(sq_conf - rc_det["confidence"]))

                for c1, c2 in zip(sq_box, rc_det["bbox"]):
                    coord_diffs.append(abs(c1 - c2))

        per_image_comp[img_name] = {
            "sq_boxes_count": len(sq_list),
            "rc_boxes_count": len(rc_list),
            "matched_count": matched_in_image,
            "mean_iou": round(float(np.mean(img_ious)), 4) if img_ious else 0.0,
        }

    return {
        "total_sq_boxes": total_sq_boxes,
        "total_rc_boxes": total_rc_boxes,
        "total_matched": total_matched,
        "match_rate": round(total_matched / max(1, total_sq_boxes), 4),
        "mean_iou": round(float(np.mean(all_ious)), 4) if all_ious else 0.0,
        "median_iou": round(float(np.median(all_ious)), 4) if all_ious else 0.0,
        "min_iou": round(float(np.min(all_ious)), 4) if all_ious else 0.0,
        "confidence_mae": round(float(np.mean(conf_diffs)), 4) if conf_diffs else 0.0,
        "coordinates_mae_px": round(float(np.mean(coord_diffs)), 3) if coord_diffs else 0.0,
        "per_image": per_image_comp,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark comparativo rect=True vs rect=False en GPU CUDA")
    parser.add_argument("--weights", type=str, default=str(_REPO_ROOT / "yolo11n.pt"))
    parser.add_argument("--device", type=str, default="cuda:0")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--iters", type=int, default=60)
    parser.add_argument("--stress-iters", type=int, default=100)
    parser.add_argument("--out", type=str, default=str(_REPO_ROOT / "Docs" / "fase_1" / "benchmark_rect_results.json"))
    args = parser.parse_args()

    import torch
    from ultralytics import YOLO

    if not torch.cuda.is_available():
        logger.error("CUDA no está disponible. Este benchmark requiere GPU.")
        sys.exit(1)

    gpu_name = torch.cuda.get_device_name(0)
    vram_mb = round(torch.cuda.get_device_properties(0).total_memory / (1024.0 * 1024.0), 2)
    logger.info("GPU activa: %s (%.0f MB VRAM)", gpu_name, vram_mb)

    logger.info("Cargando modelo YOLO11n desde '%s'...", args.weights)
    model = YOLO(args.weights)
    model.to(args.device)

    logger.info("Preparando conjunto de datos con proporciones 16:9, 9:16 y 3:4...")
    dataset = prepare_benchmark_dataset(_REPO_ROOT)
    for k, v in dataset.items():
        h, w = v.shape[:2]
        logger.info("  Formato '%s': %dx%d (ar=%.3f)", k, w, h, w / h)

    # 1. Medir baseline rect=False
    logger.info("--- Ejecutando baseline: rect=False (cuadrada estándar 640x640) ---")
    res_sq = run_single_variant_benchmark(
        model=model,
        dataset=dataset,
        rect=False,
        device=args.device,
        imgsz=args.imgsz,
        warmup_iters=args.warmup,
        measure_iters=args.iters,
    )
    logger.info("Baseline completado: Latencia media total: %.2f ms | Inferencia pura: %.2f ms | FPS: %.1f | VRAM pico: %.1f MB",
                res_sq["overall_total_latency_ms"]["mean"],
                res_sq["overall_inference_latency_ms"]["mean"],
                res_sq["overall_fps"],
                res_sq["vram_metrics_mb"]["peak_allocated"])

    # 2. Medir candidato rect=True
    logger.info("--- Ejecutando candidato: rect=True (inferencia rectangular) ---")
    res_rc = run_single_variant_benchmark(
        model=model,
        dataset=dataset,
        rect=True,
        device=args.device,
        imgsz=args.imgsz,
        warmup_iters=args.warmup,
        measure_iters=args.iters,
    )
    logger.info("Candidato completado: Latencia media total: %.2f ms | Inferencia pura: %.2f ms | FPS: %.1f | VRAM pico: %.1f MB",
                res_rc["overall_total_latency_ms"]["mean"],
                res_rc["overall_inference_latency_ms"]["mean"],
                res_rc["overall_fps"],
                res_rc["vram_metrics_mb"]["peak_allocated"])

    # 3. Comparación numérica de concordancia
    logger.info("--- Comparando concordancia numérica de detecciones ---")
    concordance = compare_rect_concordance(res_sq["detections"], res_rc["detections"])
    logger.info("Concordancia: Match Rate=%.2f%% | IoU medio=%.4f | Conf MAE=%.4f | Coord MAE=%.2f px",
                concordance["match_rate"] * 100.0,
                concordance["mean_iou"],
                concordance["confidence_mae"],
                concordance["coordinates_mae_px"])

    # 4. Prueba de estrés con alternancia dinámica de forma
    logger.info("--- Prueba de estrés por alternancia dinámica de relaciones de aspecto ---")
    stress_sq = run_dynamic_switching_stress_test(
        model=model,
        dataset=dataset,
        rect=False,
        iterations=args.stress_iters,
        device=args.device,
        imgsz=args.imgsz,
    )
    stress_rc = run_dynamic_switching_stress_test(
        model=model,
        dataset=dataset,
        rect=True,
        iterations=args.stress_iters,
        device=args.device,
        imgsz=args.imgsz,
    )
    logger.info("Estrés alternado: rect=False -> %.2f ms (jitter std=%.2f, p95=%.2f, p99=%.2f)",
                stress_sq["total_latency_ms"]["mean"],
                stress_sq["total_latency_ms"]["std"],
                stress_sq["total_latency_ms"]["p95"],
                stress_sq["total_latency_ms"]["p99"])
    logger.info("Estrés alternado: rect=True  -> %.2f ms (jitter std=%.2f, p95=%.2f, p99=%.2f)",
                stress_rc["total_latency_ms"]["mean"],
                stress_rc["total_latency_ms"]["std"],
                stress_rc["total_latency_ms"]["p95"],
                stress_rc["total_latency_ms"]["p99"])

    # 5. Generar estructura de reporte final
    report_data = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gpu_name": gpu_name,
            "vram_total_mb": vram_mb,
            "torch_version": torch.__version__,
            "model": "yolo11n.pt",
            "resolution": args.imgsz,
            "warmup_iterations": args.warmup,
            "measure_iterations_per_format": args.iters,
            "stress_iterations": args.stress_iters,
        },
        "baseline_square_rect_false": res_sq,
        "candidate_rectangular_rect_true": res_rc,
        "concordance": concordance,
        "dynamic_switching_stress": {
            "rect_false": stress_sq,
            "rect_true": stress_rc,
        },
        "comparative_deltas": {
            "mean_total_latency_diff_ms": round(res_rc["overall_total_latency_ms"]["mean"] - res_sq["overall_total_latency_ms"]["mean"], 3),
            "mean_inference_latency_diff_ms": round(res_rc["overall_inference_latency_ms"]["mean"] - res_sq["overall_inference_latency_ms"]["mean"], 3),
            "percentage_total_latency_change": round((res_rc["overall_total_latency_ms"]["mean"] - res_sq["overall_total_latency_ms"]["mean"]) / res_sq["overall_total_latency_ms"]["mean"] * 100.0, 2),
            "fps_improvement": round(res_rc["overall_fps"] - res_sq["overall_fps"], 2),
            "vram_peak_diff_mb": round(res_rc["vram_metrics_mb"]["peak_allocated"] - res_sq["vram_metrics_mb"]["peak_allocated"], 2),
            "stress_mean_latency_diff_ms": round(stress_rc["total_latency_ms"]["mean"] - stress_sq["total_latency_ms"]["mean"], 3),
            "stress_std_jitter_diff_ms": round(stress_rc["total_latency_ms"]["std"] - stress_sq["total_latency_ms"]["std"], 3),
        }
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    logger.info("Resultados consolidados guardados en: %s", out_path)


if __name__ == "__main__":
    main()
