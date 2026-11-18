"""
Paso 4 (VISION-03C.1): Benchmark comparativo CUDA/CPU/VRAM/Temperatura/Estabilidad.

Compara:
- yolo11n.pt (baseline actual)
- yolo11x.pt (referencia historica pesada con NMS tradicional)
- yolo26x.pt (arquitectura objetivo NMS-Free end2end=True y comparativa end2end=False)

Resoluciones evaluadas: imgsz in [640, 800, 960] x precision in [FP32, FP16].
Incluye medicion puntual de TTA (augment=True) y prueba sostenida de 200 frames.
"""

from __future__ import annotations

import gc
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import cv2
import numpy as np
import psutil
import pynvml
import torch
from ultralytics import YOLO

EXP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = EXP_ROOT.parents[1]


def _gpu_telemetry(nvml_handle: Any) -> Dict[str, float]:
    mem = pynvml.nvmlDeviceGetMemoryInfo(nvml_handle)
    util = pynvml.nvmlDeviceGetUtilizationRates(nvml_handle)
    temp = pynvml.nvmlDeviceGetTemperature(nvml_handle, pynvml.NVML_TEMPERATURE_GPU)
    power_mw = pynvml.nvmlDeviceGetPowerUsage(nvml_handle)
    return {
        "nvml_vram_used_mb": round(mem.used / (1024.0 * 1024.0), 2),
        "nvml_vram_free_mb": round(mem.free / (1024.0 * 1024.0), 2),
        "gpu_util_pct": float(util.gpu),
        "gpu_temp_c": float(temp),
        "gpu_power_w": round(power_mw / 1000.0, 2),
    }


def _run_single_config(
    model_name: str,
    weights_path: Path,
    frames: List[np.ndarray],
    *,
    imgsz: int,
    half: bool,
    nms_arg: bool | None = None,
    augment: bool = False,
    warmup: int = 5,
    iters: int = 30,
    nvml_handle: Any = None,
    proc: psutil.Process | None = None,
) -> Dict[str, Any]:
    torch.cuda.empty_cache()
    gc.collect()
    torch.cuda.reset_peak_memory_stats(0)

    model = YOLO(str(weights_path))
    prec_label = "FP16" if half else "FP32"
    predict_kwargs: Dict[str, Any] = {
        "imgsz": imgsz,
        "conf": 0.25,
        "iou": 0.45,
        "classes": [2, 3, 5, 7],
        "device": "cuda:0",
        "verbose": False,
        "augment": augment,
    }
    if half:
        predict_kwargs["quantize"] = 16
    if nms_arg is not None:
        predict_kwargs["nms"] = nms_arg

    try:
        # Warm-up (no medido en latencia operativa, pero estabiliza kernels cuDNN/CUDA)
        t_w0 = time.perf_counter()
        for i in range(warmup):
            fr = frames[i % len(frames)]
            model.predict(fr, **predict_kwargs)
        torch.cuda.synchronize(0)
        warmup_ms = (time.perf_counter() - t_w0) * 1000.0

        ab_model = getattr(getattr(model, "predictor", None), "model", None)
        effective_e2e = bool(getattr(ab_model, "end2end", False))
        effective_fp16 = bool(getattr(ab_model, "fp16", False))

        latencies_ms: List[float] = []
        gpu_utils: List[float] = []
        temps_c: List[float] = []
        if proc is not None:
            proc.cpu_percent(interval=None)

        for i in range(iters):
            fr = frames[i % len(frames)]
            torch.cuda.synchronize(0)
            t0 = time.perf_counter()
            model.predict(fr, **predict_kwargs)
            torch.cuda.synchronize(0)
            latencies_ms.append((time.perf_counter() - t0) * 1000.0)
            if nvml_handle is not None and (i % 5 == 0 or i == iters - 1):
                tele = _gpu_telemetry(nvml_handle)
                gpu_utils.append(tele["gpu_util_pct"])
                temps_c.append(tele["gpu_temp_c"])

        cpu_pct = proc.cpu_percent(interval=None) if proc is not None else 0.0
        peak_alloc_mb = torch.cuda.max_memory_allocated(0) / (1024.0 * 1024.0)
        peak_reserved_mb = torch.cuda.max_memory_reserved(0) / (1024.0 * 1024.0)
        end_tele = _gpu_telemetry(nvml_handle) if nvml_handle is not None else {}

        arr = np.array(latencies_ms, dtype=np.float64)
        mean_ms = float(arr.mean())
        result = {
            "status": "OK",
            "model": model_name,
            "imgsz": imgsz,
            "precision": prec_label,
            "fp16_active": effective_fp16,
            "nms_arg": nms_arg,
            "end2end": effective_e2e,
            "tta_augment": augment,
            "iters": iters,
            "warmup_total_ms": round(warmup_ms, 2),
            "mean_ms": round(mean_ms, 3),
            "std_ms": round(float(arr.std()), 3),
            "p50_ms": round(float(np.percentile(arr, 50)), 3),
            "p95_ms": round(float(np.percentile(arr, 95)), 3),
            "p99_ms": round(float(np.percentile(arr, 99)), 3),
            "min_ms": round(float(arr.min()), 3),
            "max_ms": round(float(arr.max()), 3),
            "fps_mean": round(1000.0 / mean_ms, 2) if mean_ms > 0 else 0.0,
            "peak_vram_allocated_mb": round(peak_alloc_mb, 2),
            "peak_vram_reserved_mb": round(peak_reserved_mb, 2),
            "gpu_util_mean_pct": round(float(np.mean(gpu_utils)), 1) if gpu_utils else None,
            "gpu_util_max_pct": round(float(np.max(gpu_utils)), 1) if gpu_utils else None,
            "gpu_temp_max_c": round(float(np.max(temps_c)), 1) if temps_c else None,
            "process_cpu_pct": round(float(cpu_pct), 1),
            **end_tele,
        }
    except torch.cuda.OutOfMemoryError as oom:
        result = {
            "status": "OOM",
            "model": model_name,
            "imgsz": imgsz,
            "precision": prec_label,
            "error": str(oom),
        }
    except Exception as exc:
        result = {
            "status": "ERROR",
            "model": model_name,
            "imgsz": imgsz,
            "precision": prec_label,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        del model
        torch.cuda.empty_cache()
        gc.collect()
    return result


def _run_sustained_stress(
    weights_path: Path,
    frames: List[np.ndarray],
    *,
    imgsz: int,
    half: bool,
    nms_arg: bool | None = False,
    iters: int,
    nvml_handle: Any,
    proc: psutil.Process,
) -> Dict[str, Any]:
    torch.cuda.empty_cache()
    gc.collect()
    torch.cuda.reset_peak_memory_stats(0)

    model = YOLO(str(weights_path))
    predict_kwargs: Dict[str, Any] = {
        "imgsz": imgsz,
        "conf": 0.25,
        "classes": [2, 3, 5, 7],
        "device": "cuda:0",
        "verbose": False,
    }
    if half:
        predict_kwargs["quantize"] = 16
    if nms_arg is not None:
        predict_kwargs["nms"] = nms_arg

    # Warm-up
    for i in range(5):
        model.predict(frames[0], **predict_kwargs)
    torch.cuda.synchronize(0)
    ab_model = getattr(getattr(model, "predictor", None), "model", None)
    effective_e2e = bool(getattr(ab_model, "end2end", False))

    tele_start = _gpu_telemetry(nvml_handle)
    alloc_start_mb = torch.cuda.memory_allocated(0) / (1024.0 * 1024.0)
    latencies: List[float] = []
    temps: List[float] = []
    utils: List[float] = []
    errors = 0
    proc.cpu_percent(interval=None)

    for i in range(iters):
        fr = frames[i % len(frames)]
        try:
            torch.cuda.synchronize(0)
            t0 = time.perf_counter()
            model.predict(fr, **predict_kwargs)
            torch.cuda.synchronize(0)
            latencies.append((time.perf_counter() - t0) * 1000.0)
        except Exception:
            errors += 1
        if i % 20 == 0 or i == iters - 1:
            t_now = _gpu_telemetry(nvml_handle)
            temps.append(t_now["gpu_temp_c"])
            utils.append(t_now["gpu_util_pct"])

    cpu_pct = proc.cpu_percent(interval=None)
    alloc_end_mb = torch.cuda.memory_allocated(0) / (1024.0 * 1024.0)
    peak_alloc_mb = torch.cuda.max_memory_allocated(0) / (1024.0 * 1024.0)
    tele_end = _gpu_telemetry(nvml_handle)

    arr = np.array(latencies, dtype=np.float64)
    first_half = float(arr[: len(arr) // 2].mean())
    second_half = float(arr[len(arr) // 2 :].mean())

    del model
    torch.cuda.empty_cache()
    gc.collect()

    return {
        "precision": "FP16" if half else "FP32",
        "imgsz": imgsz,
        "end2end": effective_e2e,
        "iters": iters,
        "cuda_errors": errors,
        "mean_ms": round(float(arr.mean()), 3),
        "p50_ms": round(float(np.percentile(arr, 50)), 3),
        "p95_ms": round(float(np.percentile(arr, 95)), 3),
        "p99_ms": round(float(np.percentile(arr, 99)), 3),
        "fps_mean": round(1000.0 / float(arr.mean()), 2),
        "first_half_mean_ms": round(first_half, 3),
        "second_half_mean_ms": round(second_half, 3),
        "thermal_drift_ms": round(second_half - first_half, 3),
        "vram_alloc_start_mb": round(alloc_start_mb, 2),
        "vram_alloc_end_mb": round(alloc_end_mb, 2),
        "vram_leak_mb": round(alloc_end_mb - alloc_start_mb, 2),
        "vram_peak_allocated_mb": round(peak_alloc_mb, 2),
        "temp_start_c": tele_start["gpu_temp_c"],
        "temp_peak_c": round(float(max(temps)), 1),
        "temp_end_c": tele_end["gpu_temp_c"],
        "gpu_util_mean_pct": round(float(np.mean(utils)), 1),
        "power_end_w": tele_end["gpu_power_w"],
        "process_cpu_pct": round(float(cpu_pct), 1),
    }


def main() -> None:
    torch.cuda.init()
    _ = torch.zeros(1, device="cuda:0")
    pynvml.nvmlInit()
    nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    proc = psutil.Process()

    ev_20261114 = REPO_ROOT / "evidencias_vigia" / "20261114"
    sample_paths = (
        sorted((ev_20261114 / "CAM-ENTRADA").glob("*_orig.jpg"))[:3]
        + sorted((ev_20261114 / "CAM-SALIDA").glob("*_orig.jpg"))[-3:]
    )
    frames = [cv2.imread(str(p)) for p in sample_paths]
    if any(f is None for f in frames):
        raise RuntimeError("No se pudieron cargar fotogramas reales para el benchmark.")

    weights = {
        "yolo11n": EXP_ROOT / "weights" / "yolo11n.pt",
        "yolo11x": EXP_ROOT / "weights" / "yolo11x.pt",
        "yolo26x": EXP_ROOT / "weights" / "yolo26x.pt",
    }

    matrix_results: List[Dict[str, Any]] = []
    for m_name, wp in weights.items():
        # YOLO26x requiere nms=False para activar el cabezal nativo one2one NMS-Free
        nms_arg = False if m_name == "yolo26x" else None
        for imgsz in (640, 800, 960):
            for half in (False, True):
                res = _run_single_config(
                    m_name,
                    wp,
                    frames,
                    imgsz=imgsz,
                    half=half,
                    nms_arg=nms_arg,
                    warmup=5,
                    iters=30,
                    nvml_handle=nvml_handle,
                    proc=proc,
                )
                print(
                    f"[{m_name} {imgsz} {'FP16' if half else 'FP32'} e2e={res.get('end2end')}] -> "
                    f"status={res['status']}, mean={res.get('mean_ms')}ms, "
                    f"p95={res.get('p95_ms')}ms, fps={res.get('fps_mean')}, "
                    f"vram_peak={res.get('peak_vram_allocated_mb')}MB, temp={res.get('gpu_temp_max_c')}C"
                )
                matrix_results.append(res)

    # Comparativa especifica YOLO26x NMS-Free (nms=False -> end2end=True) vs NMS tradicional (nms=True -> end2end=False) en 640
    nms_ablation = [
        _run_single_config(
            "yolo26x_e2e_true_nms_false",
            weights["yolo26x"],
            frames,
            imgsz=640,
            half=True,
            nms_arg=False,
            nvml_handle=nvml_handle,
            proc=proc,
        ),
        _run_single_config(
            "yolo26x_e2e_false_nms_true",
            weights["yolo26x"],
            frames,
            imgsz=640,
            half=True,
            nms_arg=True,
            nvml_handle=nvml_handle,
            proc=proc,
        ),
    ]

    # Evaluacion puntual de TTA (augment=True) solo a 640 FP16:
    # 1) con nms=False (documenta reversion a single-scale en Ultralytics 8.4.171)
    # 2) con nms=True (one2many donde multi-scale TTA si ejecuta)
    tta_probe = {
        "yolo26x_e2e_true_tta": _run_single_config(
            "yolo26x_e2e_true_tta",
            weights["yolo26x"],
            frames,
            imgsz=640,
            half=True,
            nms_arg=False,
            augment=True,
            warmup=3,
            iters=15,
            nvml_handle=nvml_handle,
            proc=proc,
        ),
        "yolo26x_one2many_nms_tta": _run_single_config(
            "yolo26x_one2many_nms_tta",
            weights["yolo26x"],
            frames,
            imgsz=640,
            half=True,
            nms_arg=True,
            augment=True,
            warmup=3,
            iters=15,
            nvml_handle=nvml_handle,
            proc=proc,
        ),
    }

    # Prueba de inferencia sostenida (200 iteraciones FP16 + 200 iteraciones FP32) en modo nativo end2end=True
    sustained_fp16 = _run_sustained_stress(
        weights["yolo26x"],
        frames,
        imgsz=640,
        half=True,
        nms_arg=False,
        iters=200,
        nvml_handle=nvml_handle,
        proc=proc,
    )
    sustained_fp32 = _run_sustained_stress(
        weights["yolo26x"],
        frames,
        imgsz=640,
        half=False,
        nms_arg=False,
        iters=200,
        nvml_handle=nvml_handle,
        proc=proc,
    )

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "gpu_name": torch.cuda.get_device_name(0),
        "driver_version": pynvml.nvmlSystemGetDriverVersion(),
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "matrix_results": matrix_results,
        "nms_free_vs_traditional_ablation": nms_ablation,
        "tta_cost_probe": tta_probe,
        "sustained_stress_200_iters": {
            "fp16": sustained_fp16,
            "fp32": sustained_fp32,
        },
    }

    pynvml.nvmlShutdown()
    out_path = EXP_ROOT / "results" / "benchmark_matrix.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Benchmark saved to", out_path)


if __name__ == "__main__":
    main()
