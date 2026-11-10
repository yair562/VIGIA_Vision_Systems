"""
scripts/run_cuda_benchmark.py
=============================
Script reproducible de caracterización y benchmark comparativo
entre CPU y GPU NVIDIA CUDA (RTX 4050 Laptop GPU) para YOLO11n.

Este script ejecuta:
1. Verificación del dispositivo CUDA y telemetría de hardware (VRAM, SM, Driver).
2. Carga y warm-up del modelo yolo11n.pt tanto en CPU como en CUDA.
3. Inferencia iterativa sobre el conjunto de imágenes reales de evidencias_vigia.
4. Desglose detallado de tiempos:
   - Tiempo de carga (T_load).
   - Tiempo de warm-up (T_warmup).
   - Preprocesamiento (T_preprocess).
   - Inferencia pura (T_inference).
   - Postprocesamiento / NMS (T_postprocess).
   - Latencia total por fotograma (T_total).
5. Sincronización explícita con torch.cuda.synchronize() para evitar sesgos asíncronos.
6. Comparación numérica de detecciones (conteo, clases, MAE de confianza, MAE de coordenadas e IoU).
7. Telemetría de utilización de memoria VRAM (torch.cuda.memory_allocated).
8. Exportación estructurada a formato JSON.
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

# Configurar logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cuda_benchmark")


def check_cuda_environment() -> Dict[str, Any]:
    """Inspecciona y valida el entorno PyTorch y la disponibilidad de hardware CUDA."""
    import torch

    cuda_available = torch.cuda.is_available()
    device_count = torch.cuda.device_count() if cuda_available else 0
    device_name = torch.cuda.get_device_name(0) if cuda_available else "N/A"
    capability = torch.cuda.get_device_capability(0) if cuda_available else (0, 0)
    cudnn_version = torch.backends.cudnn.version() if (cuda_available and torch.backends.cudnn.is_available()) else None

    vram_total_mb = 0.0
    if cuda_available:
        props = torch.cuda.get_device_properties(0)
        vram_total_mb = round(props.total_memory / (1024.0 * 1024.0), 2)

    return {
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cuda_available": cuda_available,
        "device_count": device_count,
        "device_name": device_name,
        "compute_capability": f"{capability[0]}.{capability[1]}",
        "cudnn_version": cudnn_version,
        "vram_total_mb": vram_total_mb,
    }


def compute_iou(box1: List[float], box2: List[float]) -> float:
    """Calcula la Intersección sobre Unión (IoU) entre dos bounding boxes [x1, y1, x2, y2]."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    inter_w = max(0.0, x2 - x1)
    inter_h = max(0.0, y2 - y1)
    inter_area = inter_w * inter_h

    area1 = max(0.0, box1[2] - box1[0]) * max(0.0, box1[3] - box1[1])
    area2 = max(0.0, box2[2] - box2[0]) * max(0.0, box2[3] - box2[1])
    union_area = area1 + area2 - inter_area

    if union_area <= 0:
        return 0.0
    return inter_area / union_area


def run_benchmark_on_device(
    model_path: Path,
    image_paths: List[Path],
    device: str,
    imgsz: int = 640,
    conf_thresh: float = 0.25,
    iou_thresh: float = 0.70,
    warmup_iters: int = 10,
    iterations_per_image: int = 5,
    half: bool = False,
) -> Dict[str, Any]:
    """Ejecuta la medición granular sobre un dispositivo específico ('cpu' o 'cuda')."""
    import torch
    from ultralytics import YOLO

    is_cuda = device.startswith("cuda")
    if is_cuda and not torch.cuda.is_available():
        raise RuntimeError("CUDA no está disponible en este entorno.")

    logger.info("Iniciando benchmark en dispositivo: %s (FP16/half=%s)...", device.upper(), half)

    if is_cuda:
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(0)
        torch.cuda.synchronize()

    # 1. Medir tiempo de carga del modelo
    t_load_start = time.perf_counter()
    model = YOLO(str(model_path))
    model.to(device)
    if is_cuda and half:
        model.model.half()
    if is_cuda:
        torch.cuda.synchronize()
    t_load_end = time.perf_counter()
    load_time_ms = (t_load_end - t_load_start) * 1000.0

    # 2. Warm-up del motor
    dummy_frame = np.zeros((imgsz, imgsz, 3), dtype=np.uint8)
    t_warmup_start = time.perf_counter()
    for _ in range(warmup_iters):
        if is_cuda:
            torch.cuda.synchronize()
        _ = model.predict(
            source=dummy_frame,
            imgsz=imgsz,
            conf=conf_thresh,
            iou=iou_thresh,
            half=half,
            device=device,
            verbose=False,
        )
        if is_cuda:
            torch.cuda.synchronize()
    t_warmup_end = time.perf_counter()
    warmup_time_ms = (t_warmup_end - t_warmup_start) * 1000.0

    # 3. Medición per-image con sincronización estricta
    preprocess_times: List[float] = []
    inference_times: List[float] = []
    postprocess_times: List[float] = []
    total_times: List[float] = []

    detection_results: Dict[str, List[Dict[str, Any]]] = {}

    for img_p in image_paths:
        frame_bgr = cv2.imread(str(img_p))
        if frame_bgr is None:
            logger.warning("No se pudo cargar la imagen: %s", img_p)
            continue

        per_image_dets = []
        for it in range(iterations_per_image):
            if is_cuda:
                torch.cuda.synchronize()
            t0 = time.perf_counter()

            results = model.predict(
                source=frame_bgr,
                imgsz=imgsz,
                conf=conf_thresh,
                iou=iou_thresh,
                half=half,
                device=device,
                verbose=False,
            )

            if is_cuda:
                torch.cuda.synchronize()
            t1 = time.perf_counter()

            total_ms = (t1 - t0) * 1000.0
            total_times.append(total_ms)

            # Extraer tiempos internos reportados por Ultralytics
            speed_dict = results[0].speed
            p_ms = speed_dict.get("preprocess", 0.0)
            i_ms = speed_dict.get("inference", 0.0)
            post_ms = speed_dict.get("postprocess", 0.0)

            preprocess_times.append(p_ms)
            inference_times.append(i_ms)
            postprocess_times.append(post_ms)

            # Registrar detecciones en la primera iteración
            if it == 0:
                boxes = results[0].boxes
                for box in boxes:
                    xyxy = box.xyxy[0].tolist()
                    conf = float(box.conf[0].item())
                    cls_id = int(box.cls[0].item())
                    cls_name = model.names.get(cls_id, str(cls_id))
                    per_image_dets.append({
                        "cls_id": cls_id,
                        "class_name": cls_name,
                        "confidence": round(conf, 4),
                        "bbox": [round(c, 2) for c in xyxy],
                    })

        detection_results[img_p.name] = per_image_dets

    # 4. Telemetría de VRAM
    vram_peak_mb = 0.0
    vram_alloc_mb = 0.0
    if is_cuda:
        vram_peak_mb = round(torch.cuda.max_memory_allocated(0) / (1024.0 * 1024.0), 2)
        vram_alloc_mb = round(torch.cuda.memory_allocated(0) / (1024.0 * 1024.0), 2)

    def stats(arr: List[float]) -> Dict[str, float]:
        if not arr:
            return {"mean": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0}
        a = np.array(arr)
        return {
            "mean": round(float(np.mean(a)), 3),
            "p50": round(float(np.percentile(a, 50)), 3),
            "p90": round(float(np.percentile(a, 90)), 3),
            "p95": round(float(np.percentile(a, 95)), 3),
            "min": round(float(np.min(a)), 3),
            "max": round(float(np.max(a)), 3),
        }

    return {
        "device": device,
        "half_precision": half,
        "load_time_ms": round(load_time_ms, 2),
        "warmup_time_ms": round(warmup_time_ms, 2),
        "warmup_iterations": warmup_iters,
        "total_inferences_measured": len(total_times),
        "timings_ms": {
            "preprocess": stats(preprocess_times),
            "inference": stats(inference_times),
            "postprocess": stats(postprocess_times),
            "total_per_image": stats(total_times),
        },
        "vram_metrics_mb": {
            "allocated": vram_alloc_mb,
            "peak": vram_peak_mb,
        },
        "detections": detection_results,
    }


def compare_detections(
    cpu_dets: Dict[str, List[Dict[str, Any]]],
    cuda_dets: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Compara cuantitativamente las salidas de detección entre CPU y CUDA."""
    all_images = sorted(list(set(cpu_dets.keys()) | set(cuda_dets.keys())))

    conf_diffs: List[float] = []
    box_coord_diffs: List[float] = []
    ious: List[float] = []
    class_mismatches = 0
    total_matched_pairs = 0

    per_image_comparison = []

    for img_name in all_images:
        c_list = cpu_dets.get(img_name, [])
        g_list = cuda_dets.get(img_name, [])

        img_comp = {
            "image": img_name,
            "cpu_count": len(c_list),
            "cuda_count": len(g_list),
            "count_equal": len(c_list) == len(g_list),
            "matches": [],
        }

        # Emparejar detecciones por máxima IoU
        matched_g_indices = set()
        for c_idx, c_det in enumerate(c_list):
            best_iou = 0.0
            best_g_idx = -1
            for g_idx, g_det in enumerate(g_list):
                if g_idx in matched_g_indices:
                    continue
                iou = compute_iou(c_det["bbox"], g_det["bbox"])
                if iou > best_iou:
                    best_iou = iou
                    best_g_idx = g_idx

            if best_g_idx >= 0 and best_iou > 0.5:
                matched_g_indices.add(best_g_idx)
                g_det = g_list[best_g_idx]
                total_matched_pairs += 1

                c_conf = c_det["confidence"]
                g_conf = g_det["confidence"]
                diff_conf = abs(c_conf - g_conf)
                conf_diffs.append(diff_conf)

                # MAE de las 4 coordenadas [x1, y1, x2, y2]
                box_c = c_det["bbox"]
                box_g = g_det["bbox"]
                coord_err = sum(abs(box_c[k] - box_g[k]) for k in range(4)) / 4.0
                box_coord_diffs.append(coord_err)
                ious.append(best_iou)

                class_match = (c_det["cls_id"] == g_det["cls_id"])
                if not class_match:
                    class_mismatches += 1

                img_comp["matches"].append({
                    "cpu_class": c_det["class_name"],
                    "cuda_class": g_det["class_name"],
                    "class_match": class_match,
                    "cpu_conf": c_conf,
                    "cuda_conf": g_conf,
                    "conf_diff": round(diff_conf, 5),
                    "iou": round(best_iou, 4),
                    "coord_mae_px": round(coord_err, 3),
                })

        per_image_comparison.append(img_comp)

    mae_conf = float(np.mean(conf_diffs)) if conf_diffs else 0.0
    mae_coords = float(np.mean(box_coord_diffs)) if box_coord_diffs else 0.0
    mean_iou = float(np.mean(ious)) if ious else 1.0

    return {
        "total_images_compared": len(all_images),
        "total_matched_detections": total_matched_pairs,
        "class_mismatches": class_mismatches,
        "mae_confidence": round(mae_conf, 6),
        "mae_box_coords_pixels": round(mae_coords, 4),
        "mean_iou_overlap": round(mean_iou, 5),
        "exact_numerical_equivalence": bool(mae_conf == 0.0 and mae_coords == 0.0 and class_mismatches == 0),
        "per_image": per_image_comparison,
    }


def main():
    parser = argparse.ArgumentParser(description="VIGIA Vision Systems — Benchmark Comparativo YOLO11n CPU vs CUDA")
    parser.add_argument("--model", type=str, default="yolo11n.pt", help="Ruta al modelo yolo11n.pt")
    parser.add_argument("--images-dir", type=str, default="evidencias_vigia/20261104/CAM-ENTRADA", help="Directorio de imágenes")
    parser.add_argument("--imgsz", type=int, default=640, help="Resolución de inferencia (default: 640)")
    parser.add_argument("--warmup", type=int, default=10, help="Iteraciones de warm-up (default: 10)")
    parser.add_argument("--iterations-per-image", type=int, default=5, help="Repeticiones por imagen (default: 5)")
    parser.add_argument("--output", type=str, default="scratch/cuda_benchmark_results.json", help="Ruta de exportación JSON")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    model_path = Path(args.model)
    if not model_path.is_absolute():
        model_path = repo_root / model_path

    if not model_path.exists():
        raise FileNotFoundError(f"Modelo YOLO no encontrado en: {model_path}")

    # Seleccionar imágenes para el benchmark
    img_dir = Path(args.images_dir)
    if not img_dir.is_absolute():
        img_dir = repo_root / img_dir

    all_images = sorted(list(img_dir.glob("*_orig.jpg")))
    if not all_images:
        all_images = sorted(list(img_dir.glob("*.jpg")))
    if not all_images:
        logger.warning("No se encontraron imágenes en %s. Creando 5 fotogramas sintéticos...", img_dir)
        temp_img_dir = repo_root / "scratch" / "bench_images"
        temp_img_dir.mkdir(parents=True, exist_ok=True)
        all_images = []
        for idx in range(5):
            synth_p = temp_img_dir / f"synth_frame_{idx}.jpg"
            img = np.full((720, 1280, 3), (120, 120, 120), dtype=np.uint8)
            cv2.rectangle(img, (200 + idx * 30, 300, 600 + idx * 30, 600), (0, 0, 200), -1)
            cv2.imwrite(str(synth_p), img)
            all_images.append(synth_p)

    # Limitar a máximo 10 imágenes para un benchmark representativo y rápido
    selected_images = all_images[:10]
    logger.info("Imágenes seleccionadas para benchmark (%d fotogramas):", len(selected_images))
    for p in selected_images:
        logger.info(" - %s", p.name)

    # 1. Diagnóstico de hardware y entorno
    cuda_env = check_cuda_environment()
    logger.info("Diagnóstico de Entorno: %s", json.dumps(cuda_env, indent=2))

    if not cuda_env["cuda_available"]:
        logger.error("CUDA no está disponible en este entorno. Abortando benchmark GPU.")
        sys.exit(1)

    # 2. Benchmark CPU
    cpu_results = run_benchmark_on_device(
        model_path=model_path,
        image_paths=selected_images,
        device="cpu",
        imgsz=args.imgsz,
        warmup_iters=args.warmup,
        iterations_per_image=args.iterations_per_image,
        half=False,
    )

    # 3. Benchmark CUDA (FP32)
    cuda_fp32_results = run_benchmark_on_device(
        model_path=model_path,
        image_paths=selected_images,
        device="cuda:0",
        imgsz=args.imgsz,
        warmup_iters=args.warmup,
        iterations_per_image=args.iterations_per_image,
        half=False,
    )

    # 4. Benchmark CUDA (FP16 / Half)
    cuda_fp16_results = run_benchmark_on_device(
        model_path=model_path,
        image_paths=selected_images,
        device="cuda:0",
        imgsz=args.imgsz,
        warmup_iters=args.warmup,
        iterations_per_image=args.iterations_per_image,
        half=True,
    )

    # 5. Comparativa de detecciones CPU vs CUDA FP32
    det_comparison_fp32 = compare_detections(
        cpu_results["detections"],
        cuda_fp32_results["detections"],
    )

    # 6. Comparativa de detecciones CPU vs CUDA FP16
    det_comparison_fp16 = compare_detections(
        cpu_results["detections"],
        cuda_fp16_results["detections"],
    )

    # 7. Speedups calculados
    cpu_infer_mean = cpu_results["timings_ms"]["inference"]["mean"]
    cuda_fp32_infer_mean = cuda_fp32_results["timings_ms"]["inference"]["mean"]
    cuda_fp16_infer_mean = cuda_fp16_results["timings_ms"]["inference"]["mean"]

    cpu_total_mean = cpu_results["timings_ms"]["total_per_image"]["mean"]
    cuda_fp32_total_mean = cuda_fp32_results["timings_ms"]["total_per_image"]["mean"]
    cuda_fp16_total_mean = cuda_fp16_results["timings_ms"]["total_per_image"]["mean"]

    speedup_infer_fp32 = round(cpu_infer_mean / cuda_fp32_infer_mean, 2) if cuda_fp32_infer_mean > 0 else 0.0
    speedup_infer_fp16 = round(cpu_infer_mean / cuda_fp16_infer_mean, 2) if cuda_fp16_infer_mean > 0 else 0.0
    speedup_total_fp32 = round(cpu_total_mean / cuda_fp32_total_mean, 2) if cuda_fp32_total_mean > 0 else 0.0
    speedup_total_fp16 = round(cpu_total_mean / cuda_fp16_total_mean, 2) if cuda_fp16_total_mean > 0 else 0.0

    report = {
        "metadata": {
            "benchmark_title": "VIGIA-OPT-CUDA-01: Benchmark Comparativo YOLO11n CPU vs CUDA",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "model_path": str(model_path.resolve()),
            "imgsz": args.imgsz,
            "images_count": len(selected_images),
            "warmup_iterations": args.warmup,
            "iterations_per_image": args.iterations_per_image,
        },
        "environment": cuda_env,
        "cpu_benchmark": cpu_results,
        "cuda_fp32_benchmark": cuda_fp32_results,
        "cuda_fp16_benchmark": cuda_fp16_results,
        "speedup_summary": {
            "inference_speedup_fp32": speedup_infer_fp32,
            "inference_speedup_fp16": speedup_infer_fp16,
            "total_e2e_speedup_fp32": speedup_total_fp32,
            "total_e2e_speedup_fp16": speedup_total_fp16,
            "cpu_inference_mean_ms": cpu_infer_mean,
            "cuda_fp32_inference_mean_ms": cuda_fp32_infer_mean,
            "cuda_fp16_inference_mean_ms": cuda_fp16_infer_mean,
            "cpu_total_mean_ms": cpu_total_mean,
            "cuda_fp32_total_mean_ms": cuda_fp32_total_mean,
            "cuda_fp16_total_mean_ms": cuda_fp16_total_mean,
        },
        "detection_comparison_fp32": det_comparison_fp32,
        "detection_comparison_fp16": det_comparison_fp16,
    }

    # Imprimir resumen en consola
    print("\n" + "=" * 80)
    print(" VIGÍA VISION SYSTEMS — BENCHMARK YOLO11n CPU vs NVIDIA RTX 4050 (CUDA)")
    print("=" * 80)
    print(f"GPU Detectada:       {cuda_env['device_name']} (Compute Capability {cuda_env['compute_capability']})")
    print(f"VRAM Total:          {cuda_env['vram_total_mb']} MB | PyTorch: {cuda_env['torch_version']}")
    print("-" * 80)
    print(f"{'Etapa':<25} | {'CPU (FP32)':<15} | {'CUDA (FP32)':<15} | {'CUDA (FP16)':<15}")
    print("-" * 80)
    print(f"{'Carga de Modelo':<25} | {cpu_results['load_time_ms']:<15.2f} | {cuda_fp32_results['load_time_ms']:<15.2f} | {cuda_fp16_results['load_time_ms']:<15.2f}")
    print(f"{'Warm-up Total':<25} | {cpu_results['warmup_time_ms']:<15.2f} | {cuda_fp32_results['warmup_time_ms']:<15.2f} | {cuda_fp16_results['warmup_time_ms']:<15.2f}")
    print(f"{'Preproceso (media)':<25} | {cpu_results['timings_ms']['preprocess']['mean']:<15.2f} | {cuda_fp32_results['timings_ms']['preprocess']['mean']:<15.2f} | {cuda_fp16_results['timings_ms']['preprocess']['mean']:<15.2f}")
    print(f"{'Inferencia (media)':<25} | {cpu_infer_mean:<15.2f} | {cuda_fp32_infer_mean:<15.2f} | {cuda_fp16_infer_mean:<15.2f}")
    print(f"{'Postproceso (media)':<25} | {cpu_results['timings_ms']['postprocess']['mean']:<15.2f} | {cuda_fp32_results['timings_ms']['postprocess']['mean']:<15.2f} | {cuda_fp16_results['timings_ms']['postprocess']['mean']:<15.2f}")
    print(f"{'Total / Frame (media)':<25} | {cpu_total_mean:<15.2f} | {cuda_fp32_total_mean:<15.2f} | {cuda_fp16_total_mean:<15.2f}")
    print(f"{'Total / Frame (p95)':<25} | {cpu_results['timings_ms']['total_per_image']['p95']:<15.2f} | {cuda_fp32_results['timings_ms']['total_per_image']['p95']:<15.2f} | {cuda_fp16_results['timings_ms']['total_per_image']['p95']:<15.2f}")
    print("-" * 80)
    print(f"Speedup Inferencia Pura:   {speedup_infer_fp32:.2f}x (CUDA FP32) | {speedup_infer_fp16:.2f}x (CUDA FP16)")
    print(f"Speedup Total por Frame:   {speedup_total_fp32:.2f}x (CUDA FP32) | {speedup_total_fp16:.2f}x (CUDA FP16)")
    print(f"VRAM Pico Utilizada:       {cuda_fp32_results['vram_metrics_mb']['peak']} MB (FP32) | {cuda_fp16_results['vram_metrics_mb']['peak']} MB (FP16)")
    print("-" * 80)
    print("Consistencia Numérica CPU vs CUDA FP32:")
    print(f" - Discrepancia de clases: {det_comparison_fp32['class_mismatches']}")
    print(f" - MAE de confianza:       {det_comparison_fp32['mae_confidence']:.6f}")
    print(f" - MAE coords bbox:        {det_comparison_fp32['mae_box_coords_pixels']:.4f} px")
    print(f" - IoU medio de solape:    {det_comparison_fp32['mean_iou_overlap']:.5f}")
    print("=" * 80)

    # Exportar archivo JSON
    out_p = Path(args.output)
    if not out_p.is_absolute():
        out_p = repo_root / out_p
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    logger.info("Informe estructurado guardado en: %s", out_p)


if __name__ == "__main__":
    main()
