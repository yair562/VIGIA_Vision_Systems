"""
VIGIA-VISION-06 — FASE 4: Validación Empírica de Capacidad Operativa y Concurrencia GPU.
Ejecuta un soak test concurrente multicámara (100 inferencias reales YOLO26x FP16 NMS-Free + EXP-10
en RTX 4050 6GB) sin tocar cámaras físicas ni alterar la base de datos de producción.
"""

from __future__ import annotations

import gc
import json
import logging
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

import cv2
import numpy as np
import torch

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from VIGIA_Core.domain.vision_result import VisionStatus
from VIGIA_Core.repository.detection_repository import DetectionInsertDTO, IDetectionRepository
from VIGIA_Vision.capture.sources import MobilePushFrameBuffer
from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.config.topology_validator import AreaConfigDTO, CameraConfigDTO, TopologyValidator
from VIGIA_Vision.detection.yolo_detector import YoloDetectorConfig, YoloVehicleDetector, resolve_yolo_weights_path
from VIGIA_Vision.runtime.coordinator import VisionEngineCoordinator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("VISION-06-CAPACITY")


class _MockTopoRepo:
    def __init__(self) -> None:
        self.ent_id = uuid4()
        self.sal_id = uuid4()

    def get_cameras(self):
        return [
            CameraConfigDTO(id_camara=self.ent_id, codigo="CAM-ENTRADA", nombre="Entrada", uri_stream="push://cam-entrada", activa=True),
            CameraConfigDTO(id_camara=self.sal_id, codigo="CAM-SALIDA", nombre="Salida", uri_stream="push://cam-salida", activa=True),
        ]

    def get_areas(self):
        return [
            AreaConfigDTO(
                id_area_vision=uuid4(),
                id_camara=self.ent_id,
                codigo="ROI-ENT",
                nombre="ROI Entrada",
                tipo_movimiento="ENTRADA",
                x_min=0.05,
                y_min=0.05,
                x_max=0.95,
                y_max=0.95,
                activa=True,
            ),
            AreaConfigDTO(
                id_area_vision=uuid4(),
                id_camara=self.sal_id,
                codigo="ROI-SAL",
                nombre="ROI Salida",
                tipo_movimiento="SALIDA",
                x_min=0.05,
                y_min=0.05,
                x_max=0.95,
                y_max=0.95,
                activa=True,
            ),
        ]


class _MemDetRepo(IDetectionRepository):
    def __init__(self) -> None:
        self.count = 0

    def persist_detection(self, data: DetectionInsertDTO):
        self.count += 1
        return uuid4()


def _get_process_rss_mb() -> float:
    import ctypes
    from ctypes import wintypes

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    pmc = PROCESS_MEMORY_COUNTERS()
    pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.K32GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
        wintypes.DWORD,
    ]
    k32.K32GetProcessMemoryInfo.restype = wintypes.BOOL
    proc = k32.GetCurrentProcess()
    if k32.K32GetProcessMemoryInfo(proc, ctypes.byref(pmc), pmc.cb):
        return round(pmc.WorkingSetSize / (1024.0 * 1024.0), 2)
    return 0.0


def main() -> int:
    weights_path = resolve_yolo_weights_path("experiments/yolo26x/weights/yolo26x.pt")
    fallback_path = resolve_yolo_weights_path("yolo11n.pt")

    # Cargar muestras reales del corpus (vehículos reales) + cuadro vacío
    ev_dir = _REPO_ROOT / "evidencias_vigia"
    sample_candidates = [
        ev_dir / "20261116" / "CAM-SALIDA" / "20261116T172113_418425Z_e8a735512bc2_orig.jpg",
        ev_dir / "20261114" / "CAM-SALIDA" / "20261114T005953_419239Z_5f4588730e82_orig.jpg",
        ev_dir / "20261114" / "CAM-SALIDA" / "20261114T010037_321148Z_29a0e74bbe1e_orig.jpg",
    ]
    vehicle_frames = [cv2.imread(str(p)) for p in sample_candidates if p.is_file()]
    vehicle_frames = [f for f in vehicle_frames if f is not None]
    if not vehicle_frames:
        raise RuntimeError("No se encontraron imágenes vehiculares reales para prueba de capacidad.")
    empty_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    free_b, total_b = torch.cuda.mem_get_info(0)
    vram_free_before = round(free_b / (1024.0**2), 2)
    vram_total_mb = round(total_b / (1024.0**2), 2)
    rss_before_mb = _get_process_rss_mb()

    det = YoloVehicleDetector(
        config=YoloDetectorConfig(
            model_path=str(weights_path),
            confidence_threshold=0.25,
            device="cuda:0",
            imgsz=640,
            quantize=16,
            nms=False,
            augment=False,
            fallback_enabled=True,
            fallback_model_path=str(fallback_path),
            deduplicate_iou_threshold=0.55,
            consolidate_frontal_confidence=True,
            frontal_aux_enabled=True,
            frontal_aux_imgsz=384,
            frontal_aux_trigger_confidence=0.70,
        )
    )

    src_ent = MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=10.0)
    src_sal = MobilePushFrameBuffer("CAM-SALIDA", ttl_seconds=10.0)
    with tempfile.TemporaryDirectory() as tmpdir:
        coord = VisionEngineCoordinator(
            topology_validator=TopologyValidator(repository=_MockTopoRepo()),
            settings=VisionEngineSettings(evidence_directory=Path(tmpdir)),
            detector=det,
            detection_repository=_MemDetRepo(),
            sources={"CAM-ENTRADA": src_ent, "CAM-SALIDA": src_sal},
        )
        coord.initialize(open_sources=True)
        try:
            # Warmup explícito en CUDA (1 frame vehicular)
            src_ent.push_frame(vehicle_frames[0])
            coord.process_camera_step("CAM-ENTRADA", persist_as_new_event=False)
            vram_post_warmup_alloc = round(torch.cuda.memory_allocated() / (1024.0**2), 2)

            # Reset peak stats after warmup to observe steady-state multi-cam load
            det._latencies_ms.clear()
            det._queue_waits_ms.clear()
            det._total_inferences = 0
            det._inferences_by_model.clear()
            det._frontal_aux_triggers = 0
            det._frontal_aux_recoveries = 0

            # Stress test concurrente: 2 hilos x 50 frames = 100 inferencias reales
            # Mix realista: 50% cuadros vacíos (dispara sonda 384) y 50% cuadros vehiculares
            errors: List[str] = []
            step_times_by_cam: Dict[str, List[float]] = {"CAM-ENTRADA": [], "CAM-SALIDA": []}
            cam_locks = {"CAM-ENTRADA": threading.RLock(), "CAM-SALIDA": threading.RLock()}

            def cam_worker(cam_code: str, buf: MobilePushFrameBuffer, count: int) -> None:
                for idx in range(count):
                    frame = vehicle_frames[idx % len(vehicle_frames)] if (idx % 2 == 0) else empty_frame
                    t0 = time.perf_counter()
                    try:
                        with cam_locks[cam_code]:
                            buf.push_frame(frame)
                            env = coord.process_camera_step(cam_code, persist_as_new_event=False)
                            assert env is not None
                            assert env.vision_result.status in (
                                VisionStatus.VEHICLE_DETECTED_NO_PLATE,
                                VisionStatus.NO_VEHICLE_DETECTED,
                            )
                        step_times_by_cam[cam_code].append((time.perf_counter() - t0) * 1000.0)
                    except Exception as exc:
                        errors.append(f"{cam_code}#{idx}: {type(exc).__name__}: {exc}")

            t_wall0 = time.perf_counter()
            t1 = threading.Thread(target=cam_worker, args=("CAM-ENTRADA", src_ent, 50))
            t2 = threading.Thread(target=cam_worker, args=("CAM-SALIDA", src_sal, 50))
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            wall_elapsed_s = round(time.perf_counter() - t_wall0, 3)

            st = det.get_runtime_status()
            op = coord.get_operational_metrics()
            vram_end_alloc = round(torch.cuda.memory_allocated() / (1024.0**2), 2)
            vram_peak_alloc = round(torch.cuda.max_memory_allocated() / (1024.0**2), 2)
            vram_end_res = round(torch.cuda.memory_reserved() / (1024.0**2), 2)
            vram_peak_res = round(torch.cuda.max_memory_reserved() / (1024.0**2), 2)
            free_after_b, _ = torch.cuda.mem_get_info(0)
            vram_device_free_during = round(free_after_b / (1024.0**2), 2)
            rss_peak_mb = _get_process_rss_mb()
        finally:
            coord.shutdown()

    gc.collect()
    torch.cuda.empty_cache()
    vram_post_unload_alloc = round(torch.cuda.memory_allocated() / (1024.0**2), 2)

    result = {
        "timestamp_utc": st["inference_metrics"]["last_inference_at"],
        "vram_hardware": {
            "total_mb": vram_total_mb,
            "free_before_mb": vram_free_before,
            "device_free_during_load_mb": vram_device_free_during,
            "post_warmup_allocated_mb": vram_post_warmup_alloc,
            "end_allocated_mb": vram_end_alloc,
            "peak_allocated_mb": vram_peak_alloc,
            "end_reserved_mb": vram_end_res,
            "peak_reserved_mb": vram_peak_res,
            "vram_drift_mb": round(vram_end_alloc - vram_post_warmup_alloc, 2),
            "post_unload_allocated_mb": vram_post_unload_alloc,
        },
        "process_memory_mb": {
            "rss_before_mb": rss_before_mb,
            "rss_after_100_mb": rss_peak_mb,
        },
        "concurrent_workload": {
            "cameras": ["CAM-ENTRADA", "CAM-SALIDA"],
            "total_inferences": st["inference_metrics"]["total_inferences"],
            "wall_elapsed_s": wall_elapsed_s,
            "aggregate_throughput_fps": round(100.0 / wall_elapsed_s, 2) if wall_elapsed_s > 0 else 0.0,
            "errors": errors,
            "inferences_by_model": st["inference_metrics"]["inferences_by_model"],
            "detector_metrics": st["inference_metrics"],
            "cam_metrics": op["cameras"],
            "detector_config_verified": {
                "effective_model": st["effective_model"],
                "device": st["device"],
                "effective_fp16": st["effective_fp16"],
                "end2end": st["end2end"],
                "using_fallback": st["using_fallback"],
                "frontal_aux_imgsz": st["frontal_aux_imgsz"],
                "deduplicate_iou_threshold": st["deduplicate_iou_threshold"],
            },
        },
    }

    out_path = _REPO_ROOT / "experiments" / "yolo26x" / "results" / "vision_06_capacity_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"SUCCESS: {out_path}")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
