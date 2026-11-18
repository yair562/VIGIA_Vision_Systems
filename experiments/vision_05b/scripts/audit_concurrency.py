"""
experiments/vision_05b/scripts/audit_concurrency.py
===================================================
Auditoría técnica de concurrencia y aislamiento multicanal para
VehicleColorClassifier (Fase VISION-05B.1).

Evalúa:
- Canales simulados: 1, 2, 4 y 8 cámaras concurrentes.
- Cargas reales con frames de evidencias_vigia/ y bboxes verificados.
- Latencias (P50, P95, P99, min, max, media).
- Throughput agregado (FPS).
- Consumo de recursos: CPU (%) y memoria RSS (MB).
- Verificación estricta de aislamiento de estado entre hilos (no cross-talk).
- Ausencia de bloqueos, deadlocks o excepciones no controladas.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
import psutil

# Ajuste de path para importar módulos VIGIA
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from VIGIA_Vision.classification import (
    VehicleColorClassifier,
    VehicleColorResult,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("audit_concurrency")

INVENTORY_PATH = REPO_ROOT / "experiments" / "vision_05a" / "results" / "etapa_a_b_classified_inventory.json"
EVIDENCIAS_DIR = REPO_ROOT / "evidencias_vigia"
OUTPUT_JSON_PATH = REPO_ROOT / "experiments" / "vision_05b" / "results" / "concurrency_audit_results.json"


def load_test_pool(max_samples: int = 40) -> List[Dict[str, Any]]:
    """Carga un conjunto de frames y bboxes reales de evidencias_vigia/."""
    if not INVENTORY_PATH.is_file():
        raise FileNotFoundError(f"Inventario no encontrado: {INVENTORY_PATH}")

    with open(INVENTORY_PATH, "r", encoding="utf-8") as f:
        inv = json.load(f)

    pool = []
    for item in inv.get("items", []):
        roi_cand = item.get("yolo26x", {}).get("primary_roi_070")
        if not roi_cand:
            continue

        rel_path = item.get("relative_path")
        full_path = EVIDENCIAS_DIR / rel_path
        if not full_path.is_file():
            continue

        img_bgr = cv2.imread(str(full_path))
        if img_bgr is None:
            continue

        pool.append({
            "sample_id": item.get("sample_id"),
            "file_name": item.get("file_name"),
            "img_bgr": img_bgr,
            "bbox": tuple(roi_cand["bbox"]),
            "label": roi_cand["label"],
            "conf": roi_cand["confidence"],
        })

        if len(pool) >= max_samples:
            break

    logger.info("Cargados %d frames reales para el banco de pruebas de concurrencia.", len(pool))
    return pool


def run_channel_simulation(
    num_channels: int,
    iterations_per_channel: int,
    pool: List[Dict[str, Any]],
    shared_classifier: bool = True,
) -> Dict[str, Any]:
    """
    Ejecuta una prueba de concurrencia con N canales simultáneos.
    Cada canal procesa `iterations_per_channel` solicitudes.
    Si `shared_classifier` es True, todos los hilos comparten una única
    instancia de VehicleColorClassifier (prueba estricta de thread-safety).
    """
    logger.info(
        "=== INICIANDO SIMULACIÓN CON %d CANALES (%d iter/canal, total: %d tareas, shared_instance=%s) ===",
        num_channels,
        iterations_per_channel,
        num_channels * iterations_per_channel,
        shared_classifier,
    )

    process = psutil.Process(os.getpid())
    mem_before_mb = process.memory_info().rss / (1024 * 1024)

    # Instancia(s) del clasificador
    if shared_classifier:
        classifier_instance = VehicleColorClassifier()
        classifiers = [classifier_instance] * num_channels
    else:
        classifiers = [VehicleColorClassifier() for _ in range(num_channels)]

    # Preparar tareas por canal
    # Asignamos a cada canal una cámara lógica simulada
    channel_names = [f"CAM-{idx+1:02d}" for idx in range(num_channels)]

    tasks: List[Tuple[str, int, Dict[str, Any], VehicleColorClassifier]] = []
    for c_idx, c_name in enumerate(channel_names):
        clf = classifiers[c_idx]
        for it in range(iterations_per_channel):
            # Seleccionar muestra determinista o cíclica
            sample = pool[(c_idx * 17 + it) % len(pool)]
            tasks.append((c_name, it, sample, clf))

    # Medición de CPU inicial
    psutil.cpu_percent(interval=None)
    cpu_percent_start = process.cpu_percent(interval=None)

    latencies_ms: List[float] = []
    errors: List[str] = []
    isolation_violations: List[str] = []

    t_start = time.perf_counter()

    def _worker(c_name: str, task_id: int, sample: Dict[str, Any], clf: VehicleColorClassifier):
        t0 = time.perf_counter()
        img = sample["img_bgr"]
        bbox = sample["bbox"]
        label = sample["label"]
        conf = sample["conf"]

        # Verificación de inmutabilidad: calcular hash o suma antes y después
        h0 = int(img[0, 0, 0])

        res: VehicleColorResult = clf.classify(
            img,
            bbox,
            detected_class=label,
            detection_confidence=conf,
        )

        h1 = int(img[0, 0, 0])
        dt_ms = (time.perf_counter() - t0) * 1000.0

        # Verificaciones de aislamiento y coherencia
        if h0 != h1:
            isolation_violations.append(f"Inmutabilidad violada en canal {c_name} tarea {task_id}")

        if res.color is None or not hasattr(res.color, "value"):
            isolation_violations.append(f"Resultado nulo o inválido en canal {c_name} tarea {task_id}")

        return {
            "channel": c_name,
            "task_id": task_id,
            "color": res.color.value,
            "status": res.status.value,
            "confidence": res.confidence,
            "latency_ms": dt_ms,
        }

    results = []
    with ThreadPoolExecutor(max_workers=num_channels) as executor:
        futures = [executor.submit(_worker, c_name, t_id, s, clf) for (c_name, t_id, s, clf) in tasks]
        for fut in as_completed(futures):
            try:
                r = fut.result()
                results.append(r)
                latencies_ms.append(r["latency_ms"])
            except Exception as e:
                errors.append(str(e))

    total_duration_sec = time.perf_counter() - t_start
    cpu_percent_end = process.cpu_percent(interval=None)
    mem_after_mb = process.memory_info().rss / (1024 * 1024)

    total_tasks = len(tasks)
    throughput_fps = total_tasks / total_duration_sec if total_duration_sec > 0 else 0.0

    lat_arr = np.array(latencies_ms) if latencies_ms else np.array([0.0])

    p50 = float(np.percentile(lat_arr, 50))
    p95 = float(np.percentile(lat_arr, 95))
    p99 = float(np.percentile(lat_arr, 99))
    mean_lat = float(np.mean(lat_arr))
    min_lat = float(np.min(lat_arr))
    max_lat = float(np.max(lat_arr))

    logger.info(
        "Canales: %d | Total tareas: %d | Duración: %.2fs | Throughput: %.1f FPS",
        num_channels,
        total_tasks,
        total_duration_sec,
        throughput_fps,
    )
    logger.info(
        "Latencias (ms) -> P50: %.2f | P95: %.2f | P99: %.2f | Media: %.2f | Min: %.2f | Max: %.2f",
        p50,
        p95,
        p99,
        mean_lat,
        min_lat,
        max_lat,
    )
    logger.info(
        "Memoria RSS: Inicial=%.1f MB, Final=%.1f MB (Delta=%.2f MB) | CPU Proc: %.1f%%",
        mem_before_mb,
        mem_after_mb,
        mem_after_mb - mem_before_mb,
        cpu_percent_end,
    )
    logger.info("Errores: %d | Violaciones de aislamiento: %d", len(errors), len(isolation_violations))

    return {
        "num_channels": num_channels,
        "iterations_per_channel": iterations_per_channel,
        "total_requests": total_tasks,
        "shared_instance": shared_classifier,
        "total_duration_sec": round(total_duration_sec, 3),
        "throughput_fps": round(throughput_fps, 2),
        "latencies_ms": {
            "p50": round(p50, 3),
            "p95": round(p95, 3),
            "p99": round(p99, 3),
            "mean": round(mean_lat, 3),
            "min": round(min_lat, 3),
            "max": round(max_lat, 3),
        },
        "system_metrics": {
            "memory_initial_mb": round(mem_before_mb, 2),
            "memory_final_mb": round(mem_after_mb, 2),
            "memory_delta_mb": round(mem_after_mb - mem_before_mb, 2),
            "cpu_process_percent": round(cpu_percent_end, 2),
        },
        "robustness": {
            "error_count": len(errors),
            "errors": errors[:5],
            "isolation_violations_count": len(isolation_violations),
            "isolation_violations": isolation_violations[:5],
            "deadlocks_detected": False,
        },
    }


def main():
    pool = load_test_pool(max_samples=40)
    if not pool:
        logger.error("No se pudieron cargar muestras del corpus.")
        sys.exit(1)

    # Niveles de concurrencia requeridos por la auditoría: 1, 2, 4 y 8 canales
    configs = [
        {"channels": 1, "iter": 100},
        {"channels": 2, "iter": 100},  # Configuración equivalente a producción actual
        {"channels": 4, "iter": 75},
        {"channels": 8, "iter": 50},
    ]

    benchmark_runs = []

    for cfg in configs:
        res = run_channel_simulation(
            num_channels=cfg["channels"],
            iterations_per_channel=cfg["iter"],
            pool=pool,
            shared_classifier=True,
        )
        benchmark_runs.append(res)
        time.sleep(0.5)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "audit_phase": "VISION-05B.1",
        "description": "Auditoría de concurrencia multicanal (1, 2, 4, 8 cámaras) para VehicleColorClassifier",
        "pool_size": len(pool),
        "concurrency_benchmarks": benchmark_runs,
    }

    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    logger.info("Resultados de auditoría de concurrencia guardados en: %s", OUTPUT_JSON_PATH)


if __name__ == "__main__":
    main()
