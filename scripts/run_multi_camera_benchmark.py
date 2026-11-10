"""
VIGIA-OPT-MULTI-01: Benchmark y Caracterización Rigurosa de Pipeline Multicámara
================================================================================
Evalúa el comportamiento del motor de visión bajo concurrencia multicámara:
- E1: 1 cámara (CAM-ENTRADA)
- E2: 2 cámaras (CAM-ENTRADA, CAM-SALIDA)
- E3: 3 cámaras (CAM-ENTRADA, CAM-SALIDA, CAM-03)
- E4: 4 cámaras (CAM-ENTRADA, CAM-SALIDA, CAM-03, CAM-04)

Regímenes:
- Nominal: ~1.0 FPS por cámara (pacing controlado)
- Stress / Saturación: 0 delay (máximo throughput / concurrencia directa)
"""

import argparse
import concurrent.futures
import json
import logging
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import psutil
import psycopg2
import requests
import urllib3

urllib3.disable_warnings()

# Añadir raíz de VIGIA_Vision_Systems al sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PARENT_ROOT = REPO_ROOT.parent
sys.path.insert(0, str(REPO_ROOT))

from VIGIA_Core.config.env_loader import get_setting, load_project_env
from VIGIA_Core.repository.user_repository import resolve_database_dsn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("multi_camera_benchmark")

# Intentar inicializar NVML para telemetría GPU precisa
HAVE_NVML = False
try:
    import pynvml
    pynvml.nvmlInit()
    nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    HAVE_NVML = True
except Exception as nvml_exc:
    logger.warning("NVML no disponible: %s. Se omitirá telemetría directa de GPU.", nvml_exc)
    nvml_handle = None


class TelemetryCollector:
    """Recolecta métricas de hardware (GPU, CPU, RAM) a intervalos de 100 ms."""

    def __init__(self, interval_seconds: float = 0.1):
        self.interval = interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.samples: List[Dict[str, float]] = []

    def start(self):
        self.samples.clear()
        self._running = True
        self._thread = threading.Thread(target=self._collect_loop, daemon=True)
        self._thread.start()

    def stop(self) -> Dict[str, Any]:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

        if not self.samples:
            return {
                "gpu_util_mean": 0.0, "gpu_util_peak": 0.0,
                "vram_used_mean_mb": 0.0, "vram_used_peak_mb": 0.0,
                "cpu_util_mean": 0.0, "cpu_util_peak": 0.0,
                "ram_used_mean_mb": 0.0, "ram_used_peak_mb": 0.0,
                "gpu_temp_peak_c": 0.0,
            }

        gpu_utils = [s["gpu_util"] for s in self.samples]
        vram_used = [s["vram_used_mb"] for s in self.samples]
        cpu_utils = [s["cpu_util"] for s in self.samples]
        ram_used = [s["ram_used_mb"] for s in self.samples]
        gpu_temps = [s["gpu_temp"] for s in self.samples]

        return {
            "gpu_util_mean": round(float(np.mean(gpu_utils)), 2),
            "gpu_util_peak": round(float(np.max(gpu_utils)), 2),
            "vram_used_mean_mb": round(float(np.mean(vram_used)), 2),
            "vram_used_peak_mb": round(float(np.max(vram_used)), 2),
            "cpu_util_mean": round(float(np.mean(cpu_utils)), 2),
            "cpu_util_peak": round(float(np.max(cpu_utils)), 2),
            "ram_used_mean_mb": round(float(np.mean(ram_used)), 2),
            "ram_used_peak_mb": round(float(np.max(ram_used)), 2),
            "gpu_temp_peak_c": round(float(np.max(gpu_temps)), 2),
            "sample_count": len(self.samples),
        }

    def _collect_loop(self):
        process = psutil.Process()
        while self._running:
            gpu_util = 0.0
            vram_mb = 0.0
            gpu_temp = 0.0
            if HAVE_NVML and nvml_handle:
                try:
                    rates = pynvml.nvmlDeviceGetUtilizationRates(nvml_handle)
                    gpu_util = float(rates.gpu)
                    mem = pynvml.nvmlDeviceGetMemoryInfo(nvml_handle)
                    vram_mb = float(mem.used) / (1024.0 * 1024.0)
                    gpu_temp = float(pynvml.nvmlDeviceGetTemperature(nvml_handle, pynvml.NVML_TEMPERATURE_GPU))
                except Exception:
                    pass

            cpu_util = psutil.cpu_percent(interval=None)
            mem_info = process.memory_info()
            ram_mb = float(mem_info.rss) / (1024.0 * 1024.0)

            self.samples.append({
                "ts": time.monotonic(),
                "gpu_util": gpu_util,
                "vram_used_mb": vram_mb,
                "cpu_util": cpu_util,
                "ram_used_mb": ram_mb,
                "gpu_temp": gpu_temp,
            })
            time.sleep(self.interval)


def compute_statistics(values: List[float]) -> Dict[str, float]:
    """Calcula métricas estadísticas estándar sobre una serie de valores."""
    if not values:
        return {"mean": 0.0, "std": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "min": 0.0, "max": 0.0}
    arr = np.array(values, dtype=np.float64)
    return {
        "mean": round(float(np.mean(arr)), 2),
        "std": round(float(np.std(arr)), 2),
        "p50": round(float(np.percentile(arr, 50)), 2),
        "p90": round(float(np.percentile(arr, 90)), 2),
        "p95": round(float(np.percentile(arr, 95)), 2),
        "p99": round(float(np.percentile(arr, 99)), 2),
        "min": round(float(np.min(arr)), 2),
        "max": round(float(np.max(arr)), 2),
    }


def load_sample_frames() -> Tuple[bytes, bytes]:
    """Carga fotograma con vehículo y fotograma sin vehículo para pruebas balanceadas."""
    import ultralytics
    assets_dir = Path(ultralytics.__file__).parent / "assets"
    bus_path = assets_dir / "bus.jpg"

    if bus_path.is_file():
        img_bus = cv2.imread(str(bus_path))
        # Redimensionar a estándar 640x480 manteniendo aspecto
        img_bus = cv2.resize(img_bus, (640, 480))
    else:
        # Sintético con vehículo
        img_bus = np.zeros((480, 640, 3), dtype=np.uint8)
        img_bus[100:350, 150:450] = (180, 180, 180)

    # Fotograma vacío / fondo sin vehículo
    img_empty = np.zeros((480, 640, 3), dtype=np.uint8)
    img_empty[200:220, 200:220] = (50, 50, 50)

    _, enc_bus = cv2.imencode(".jpg", img_bus, [cv2.IMWRITE_JPEG_QUALITY, 85])
    _, enc_empty = cv2.imencode(".jpg", img_empty, [cv2.IMWRITE_JPEG_QUALITY, 85])

    return enc_bus.tobytes(), enc_empty.tobytes()


def run_camera_worker(
    camera_code: str,
    base_url: str,
    api_key: str,
    frames_bytes: List[bytes],
    regime: str,
    num_requests: int,
    target_fps: float = 1.0,
) -> List[Dict[str, Any]]:
    """Trabajador que simula una cámara transmitiendo fotogramas vía HTTP POST."""
    results = []
    url = f"{base_url}/api/v1/cameras/{camera_code}/push"
    session = requests.Session()
    session.verify = False

    interval = 1.0 / target_fps if target_fps > 0 else 0.0

    for i in range(num_requests):
        req_start = time.monotonic()
        frame_data = frames_bytes[i % len(frames_bytes)]

        # Unique token per request to avoid accidental retry deduplication
        req_id = str(uuid.uuid4())
        headers = {
            "X-Camera-Key": api_key,
            "X-Request-Id": req_id,
            "Content-Type": "image/jpeg",
        }

        try:
            t0 = time.monotonic()
            resp = session.post(url, data=frame_data, headers=headers, timeout=10.0)
            t1 = time.monotonic()
            latency_ms = (t1 - t0) * 1000.0

            status_code = resp.status_code
            resp_json = resp.json() if resp.status_code == 200 else {}
            is_ok = resp_json.get("ok", False)
            id_det = resp_json.get("id_deteccion")
            persisted = resp_json.get("detection_persisted", False)
            veh_detected = resp_json.get("vehicle_detected", False)
            err = resp_json.get("error")

            results.append({
                "camera": camera_code,
                "seq": i,
                "status_code": status_code,
                "latency_ms": latency_ms,
                "is_ok": is_ok,
                "id_deteccion": id_det,
                "detection_persisted": persisted,
                "vehicle_detected": veh_detected,
                "error": err,
            })
        except Exception as exc:
            results.append({
                "camera": camera_code,
                "seq": i,
                "status_code": 0,
                "latency_ms": 0.0,
                "is_ok": False,
                "id_deteccion": None,
                "detection_persisted": False,
                "vehicle_detected": False,
                "error": str(exc),
            })

        # Control de cadencia si régimen nominal
        if regime == "nominal" and interval > 0:
            elapsed = time.monotonic() - req_start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    return results


def query_db_detections_count(dsn: str) -> int:
    """Retorna el conteo total de detecciones en la base de datos."""
    try:
        conn = psycopg2.connect(dsn)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM deteccion;")
            count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception as exc:
        logger.error("Error al consultar PostgreSQL: %s", exc)
        return -1


def run_scenario(
    scenario_name: str,
    cameras: List[str],
    regime: str,
    num_requests_per_camera: int,
    base_url: str,
    api_key: str,
    bus_bytes: bytes,
    empty_bytes: bytes,
    telemetry: TelemetryCollector,
    dsn: str,
) -> Dict[str, Any]:
    """Ejecuta un escenario multicámara completo registrando telemetría y métricas."""
    logger.info(
        "=== Iniciando Escenario %s [%s] (%d cámaras: %s, %d req/cam) ===",
        scenario_name, regime.upper(), len(cameras), ", ".join(cameras), num_requests_per_camera
    )

    db_count_before = query_db_detections_count(dsn)

    # Alternar imágenes: 70% con vehículo, 30% vacías para simular flujo realista de tráfico
    frames_mix = []
    for idx in range(num_requests_per_camera):
        if idx % 3 == 0:
            frames_mix.append(empty_bytes)
        else:
            frames_mix.append(bus_bytes)

    telemetry.start()
    wall_start = time.monotonic()

    # Ejecutar cámaras en paralelo mediante ThreadPoolExecutor
    all_results: List[Dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(cameras)) as executor:
        futures = {
            executor.submit(
                run_camera_worker,
                camera_code=cam,
                base_url=base_url,
                api_key=api_key,
                frames_bytes=frames_mix,
                regime=regime,
                num_requests=num_requests_per_camera,
                target_fps=1.0 if regime == "nominal" else 0.0,
            ): cam
            for cam in cameras
        }
        for fut in concurrent.futures.as_completed(futures):
            cam = futures[fut]
            try:
                res = fut.result()
                all_results.extend(res)
            except Exception as e:
                logger.error("Error en worker de cámara %s: %s", cam, e)

    wall_duration = time.monotonic() - wall_start
    hw_metrics = telemetry.stop()
    db_count_after = query_db_detections_count(dsn)
    db_persisted_delta = db_count_after - db_count_before

    # Procesar métricas por cámara y agregadas
    total_submitted = len(all_results)
    success_requests = [r for r in all_results if r["is_ok"]]
    total_success = len(success_requests)
    success_rate = (total_success / total_submitted * 100.0) if total_submitted > 0 else 0.0

    aggregate_fps = round(total_success / wall_duration, 2) if wall_duration > 0 else 0.0
    latencies = [r["latency_ms"] for r in success_requests]
    latency_stats = compute_statistics(latencies)

    # Estadísticas desglosadas por cámara
    per_camera_stats = {}
    for cam in cameras:
        cam_res = [r for r in success_requests if r["camera"] == cam]
        cam_lat = [r["latency_ms"] for r in cam_res]
        cam_fps = round(len(cam_res) / wall_duration, 2) if wall_duration > 0 else 0.0
        per_camera_stats[cam] = {
            "success_count": len(cam_res),
            "fps": cam_fps,
            "latency": compute_statistics(cam_lat),
        }

    persisted_in_responses = sum(1 for r in success_requests if r.get("detection_persisted"))

    logger.info(
        "Escenario %s [%s] finalizado en %.2fs: %d/%d OK (%.1f%%). Throughput Agregado: %.2f FPS. Latencia media: %.2f ms (p95: %.2f ms). Persistidos: %d (DB delta: %d)",
        scenario_name, regime.upper(), wall_duration, total_success, total_submitted, success_rate,
        aggregate_fps, latency_stats["mean"], latency_stats["p95"], persisted_in_responses, db_persisted_delta
    )

    return {
        "scenario": scenario_name,
        "regime": regime,
        "camera_count": len(cameras),
        "cameras": cameras,
        "num_requests_per_camera": num_requests_per_camera,
        "total_submitted": total_submitted,
        "total_success": total_success,
        "success_rate_pct": success_rate,
        "wall_duration_s": round(wall_duration, 3),
        "aggregate_fps": aggregate_fps,
        "latency_ms": latency_stats,
        "per_camera": per_camera_stats,
        "telemetry_hardware": hw_metrics,
        "data_integrity": {
            "persisted_in_responses": persisted_in_responses,
            "db_count_before": db_count_before,
            "db_count_after": db_count_after,
            "db_persisted_delta": db_persisted_delta,
            "db_matches_responses": (persisted_in_responses == db_persisted_delta),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="VIGIA OPT-MULTI-01 Benchmark Runner")
    parser.add_argument("--output", type=str, default="Docs/fase_1/benchmark_multi_baseline.json", help="Ruta de salida JSON")
    parser.add_argument("--nominal-requests", type=int, default=15, help="Peticiones por cámara en régimen nominal")
    parser.add_argument("--stress-requests", type=int, default=25, help="Peticiones por cámara en régimen stress")
    args = parser.parse_args()

    load_project_env()
    api_key = get_setting("VIGIA_CAMERA_KEY", "")
    if not api_key:
        logger.error("VIGIA_CAMERA_KEY no configurado en entorno.")
        sys.exit(1)

    dsn = resolve_database_dsn()
    base_url = "https://127.0.0.1:5000"

    logger.info("Cargando fotogramas de prueba...")
    bus_bytes, empty_bytes = load_sample_frames()

    telemetry = TelemetryCollector(interval_seconds=0.1)

    # Definición de la matriz experimental E1, E2, E3, E4
    matrix = [
        {"name": "E1", "cameras": ["CAM-ENTRADA"]},
        {"name": "E2", "cameras": ["CAM-ENTRADA", "CAM-SALIDA"]},
        {"name": "E3", "cameras": ["CAM-ENTRADA", "CAM-SALIDA", "CAM-03"]},
        {"name": "E4", "cameras": ["CAM-ENTRADA", "CAM-SALIDA", "CAM-03", "CAM-04"]},
    ]

    all_scenario_results = []

    # Calentamiento rápido (warmup)
    logger.info("Ejecutando calentamiento previo...")
    for cam in ["CAM-ENTRADA", "CAM-SALIDA"]:
        run_camera_worker(cam, base_url, api_key, [bus_bytes], "stress", 3)
    time.sleep(1.0)

    # Ejecutar todos los escenarios en régimen NOMINAL
    for item in matrix:
        res = run_scenario(
            scenario_name=item["name"],
            cameras=item["cameras"],
            regime="nominal",
            num_requests_per_camera=args.nominal_requests,
            base_url=base_url,
            api_key=api_key,
            bus_bytes=bus_bytes,
            empty_bytes=empty_bytes,
            telemetry=telemetry,
            dsn=dsn,
        )
        all_scenario_results.append(res)
        time.sleep(1.0)

    # Ejecutar todos los escenarios en régimen STRESS / SATURACIÓN
    for item in matrix:
        res = run_scenario(
            scenario_name=item["name"],
            cameras=item["cameras"],
            regime="stress",
            num_requests_per_camera=args.stress_requests,
            base_url=base_url,
            api_key=api_key,
            bus_bytes=bus_bytes,
            empty_bytes=empty_bytes,
            telemetry=telemetry,
            dsn=dsn,
        )
        all_scenario_results.append(res)
        time.sleep(1.0)

    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": time.time(),
                "benchmark": "VIGIA-OPT-MULTI-01",
                "hardware": {
                    "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "N/A",
                    "vram_total_mb": round(torch.cuda.get_device_properties(0).total_memory / (1024.0 * 1024.0), 2) if torch.cuda.is_available() else 0,
                    "cuda_version": torch.version.cuda if torch.cuda.is_available() else "N/A",
                    "cpu_count_logical": psutil.cpu_count(logical=True),
                    "cpu_count_physical": psutil.cpu_count(logical=False),
                },
                "results": all_scenario_results,
            },
            f,
            indent=2,
        )
    logger.info("Resultados de benchmark guardados exitosamente en: %s", out_path)


if __name__ == "__main__":
    import torch
    main()
