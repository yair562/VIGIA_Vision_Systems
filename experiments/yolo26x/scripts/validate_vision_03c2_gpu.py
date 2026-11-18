"""
experiments.yolo26x.scripts.validate_vision_03c2_gpu
==================================================
Validación experimental integrada en GPU CUDA real (RTX 4050) de YOLO26x
dentro de ``YoloVehicleDetector`` y ``VisionEngineCoordinator`` (VISION-03C.2).

No modifica código de producción ni archivos históricos; guarda métricas
verificables en ``experiments/yolo26x/results/vision_03c2_integration_metrics.json``.
"""

from __future__ import annotations

import json
import os
import shutil
import statistics
import sys
import tempfile
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch
from uuid import uuid4

import cv2
import numpy as np
import torch
import ultralytics

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from VIGIA_Core.domain.vision_result import VisionStatus
from VIGIA_Vision.capture.sources import MobilePushFrameBuffer
from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.config.topology_validator import (
    AreaConfigDTO,
    CameraConfigDTO,
    ITopologyConfigRepository,
    TopologyValidator,
)
from VIGIA_Vision.detection.yolo_detector import (
    YoloDetectorConfig,
    YoloVehicleDetector,
    load_yolo_config_from_env,
)
from VIGIA_Vision.runtime.coordinator import VisionEngineCoordinator
from VIGIA_Vision.runtime.evidence_storage import LocalDiskEvidenceStorage


class _BenchTopoRepo(ITopologyConfigRepository):
    def __init__(self) -> None:
        self.cam_ent_id = uuid4()
        self.cam_sal_id = uuid4()
        self.cameras = [
            CameraConfigDTO(
                id_camara=self.cam_ent_id,
                codigo="CAM-ENTRADA",
                nombre="Cámara Entrada",
                uri_stream="push://cam-entrada",
                activa=True,
            ),
            CameraConfigDTO(
                id_camara=self.cam_sal_id,
                codigo="CAM-SALIDA",
                nombre="Cámara Salida",
                uri_stream="push://cam-salida",
                activa=True,
            ),
        ]
        self.areas = [
            AreaConfigDTO(
                id_area_vision=uuid4(),
                id_camara=self.cam_ent_id,
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
                id_camara=self.cam_sal_id,
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

    def get_cameras(self) -> List[CameraConfigDTO]:
        return self.cameras

    def get_areas(self) -> List[AreaConfigDTO]:
        return self.areas


def _latency_stats(ms_values: List[float]) -> Dict[str, Any]:
    ordered = sorted(ms_values)
    p95_idx = min(len(ordered) - 1, max(0, int(round(0.95 * (len(ordered) - 1)))))
    mean_ms = statistics.mean(ordered)
    return {
        "count": len(ordered),
        "mean_ms": round(mean_ms, 3),
        "median_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[p95_idx], 3),
        "min_ms": round(ordered[0], 3),
        "max_ms": round(ordered[-1], 3),
        "fps_effective": round(1000.0 / mean_ms, 2) if mean_ms > 0 else 0.0,
    }


def _collect_real_frames() -> Dict[str, List[np.ndarray]]:
    ev_dir = REPO_ROOT / "evidencias_vigia" / "20261114"
    ent_paths = sorted((ev_dir / "CAM-ENTRADA").glob("*_orig.jpg"))[:10]
    sal_paths = sorted((ev_dir / "CAM-SALIDA").glob("*_orig.jpg"))[-10:]
    ent_frames = [f for p in ent_paths if (f := cv2.imread(str(p))) is not None]
    sal_frames = [f for p in sal_paths if (f := cv2.imread(str(p))) is not None]
    if not ent_frames or not sal_frames:
        raise RuntimeError("No se encontraron imágenes reales de CAM-ENTRADA o CAM-SALIDA.")
    return {"CAM-ENTRADA": ent_frames, "CAM-SALIDA": sal_frames}


def _build_coordinator(detector: YoloVehicleDetector, temp_ev_dir: Path) -> VisionEngineCoordinator:
    topo_repo = _BenchTopoRepo()
    validator = TopologyValidator(repository=topo_repo)
    buf_ent = MobilePushFrameBuffer("CAM-ENTRADA")
    buf_sal = MobilePushFrameBuffer("CAM-SALIDA")
    buf_ent.open()
    buf_sal.open()
    settings = VisionEngineSettings(
        vehicle_confidence_threshold=0.70,
        evidence_directory=temp_ev_dir,
        save_annotated_evidence=False,
    )
    return VisionEngineCoordinator(
        topology_validator=validator,
        settings=settings,
        detector=detector,
        evidence_storage=LocalDiskEvidenceStorage(base_directory=temp_ev_dir),
        sources={"CAM-ENTRADA": buf_ent, "CAM-SALIDA": buf_sal},
    )


def _mib(bytes_val: int) -> float:
    return round(bytes_val / (1024.0 * 1024.0), 2)


def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA no está disponible en .venv_cuda.")

    torch.cuda.init()
    gpu_props = torch.cuda.get_device_properties(0)
    real_frames = _collect_real_frames()
    bus_img = cv2.imread(str(Path(ultralytics.__file__).parent / "assets" / "bus.jpg"))
    if bus_img is None:
        raise RuntimeError("No se pudo leer ultralytics/assets/bus.jpg.")

    tmp_root = Path(tempfile.mkdtemp(prefix="vigia_03c2_val_"))
    empty_env = tmp_root / ".env.empty"
    empty_env.write_text("# empty env\n", encoding="utf-8")

    try:
        clean_base = {
            k: v
            for k, v in os.environ.items()
            if k
            not in {
                "VIGIA_YOLO_MODEL",
                "VIGIA_YOLO_WEIGHTS",
                "VIGIA_YOLO_IMGSZ",
                "VIGIA_YOLO_QUANTIZE",
                "VIGIA_YOLO_NMS",
                "VIGIA_YOLO_DEVICE",
                "VIGIA_INFERENCE_DEVICE",
                "VIGIA_YOLO_FALLBACK_ENABLED",
                "VIGIA_YOLO_FALLBACK_MODEL",
            }
        }
        clean_base["VIGIA_ENV_FILE"] = str(empty_env)

        # ------------------------------------------------------------------
        # Escenario 1: Baseline por defecto (yolo11n.pt)
        # ------------------------------------------------------------------
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(0)
        with patch.dict(os.environ, {**clean_base, "VIGIA_INFERENCE_DEVICE": "cuda:0"}, clear=True):
            cfg_base = load_yolo_config_from_env(confidence_threshold=0.25)

        det_base = YoloVehicleDetector(config=cfg_base)
        coord_base = _build_coordinator(det_base, tmp_root / "ev_base")
        coord_base.initialize()

        t_load0 = time.perf_counter()
        det_base.load_model()
        base_load_ms = round((time.perf_counter() - t_load0) * 1000.0, 2)

        # Warmup 3 frames
        for i in range(3):
            cam = "CAM-ENTRADA" if i % 2 == 0 else "CAM-SALIDA"
            fr = real_frames[cam][i % len(real_frames[cam])]
            coord_base.registry.get_slot(cam).source.push_frame(fr)
            coord_base.process_camera_step(cam)
        torch.cuda.synchronize(0)

        base_latencies: List[float] = []
        base_classes: Counter = Counter()
        for i in range(30):
            cam = "CAM-ENTRADA" if i % 2 == 0 else "CAM-SALIDA"
            fr = real_frames[cam][i % len(real_frames[cam])]
            coord_base.registry.get_slot(cam).source.push_frame(fr)
            t0 = time.perf_counter()
            env = coord_base.process_camera_step(cam)
            torch.cuda.synchronize(0)
            base_latencies.append((time.perf_counter() - t0) * 1000.0)
            if env:
                for d in env.detections_in_roi:
                    base_classes[d.raw_label] += 1

        scenario_1 = {
            "runtime_status": det_base.get_runtime_status(),
            "load_time_ms": base_load_ms,
            "latency": _latency_stats(base_latencies),
            "vram": {
                "allocated_mb": _mib(torch.cuda.memory_allocated(0)),
                "reserved_mb": _mib(torch.cuda.memory_reserved(0)),
                "peak_allocated_mb": _mib(torch.cuda.max_memory_allocated(0)),
                "peak_reserved_mb": _mib(torch.cuda.max_memory_reserved(0)),
            },
            "roi_detections_by_class": dict(base_classes),
        }
        coord_base.shutdown()
        del det_base, coord_base
        torch.cuda.empty_cache()

        # ------------------------------------------------------------------
        # Escenario 2: Experimental YOLO26x (imgsz=640, quantize=16, nms=False)
        # Flujo secuencial alternado + ráfaga concurrente multi-hilo
        # ------------------------------------------------------------------
        torch.cuda.reset_peak_memory_stats(0)
        exp_env = {
            **clean_base,
            "VIGIA_YOLO_MODEL": "yolo26x.pt",
            "VIGIA_YOLO_IMGSZ": "640",
            "VIGIA_YOLO_QUANTIZE": "16",
            "VIGIA_YOLO_NMS": "false",
            "VIGIA_YOLO_DEVICE": "cuda:0",
            "VIGIA_YOLO_FALLBACK_ENABLED": "true",
            "VIGIA_YOLO_FALLBACK_MODEL": "yolo11n.pt",
        }
        with patch.dict(os.environ, exp_env, clear=True):
            cfg_exp = load_yolo_config_from_env(confidence_threshold=0.25)

        det_exp = YoloVehicleDetector(config=cfg_exp)
        coord_exp = _build_coordinator(det_exp, tmp_root / "ev_exp")
        coord_exp.initialize()

        t_load0 = time.perf_counter()
        det_exp.load_model()
        exp_load_ms = round((time.perf_counter() - t_load0) * 1000.0, 2)
        vram_after_load_mb = _mib(torch.cuda.memory_allocated(0))

        # Warmup 4 frames (2 CAM-ENTRADA + 2 CAM-SALIDA)
        for i in range(4):
            cam = "CAM-ENTRADA" if i % 2 == 0 else "CAM-SALIDA"
            fr = real_frames[cam][i % len(real_frames[cam])]
            coord_exp.registry.get_slot(cam).source.push_frame(fr)
            coord_exp.process_camera_step(cam)
        torch.cuda.synchronize(0)
        vram_post_warmup_mb = _mib(torch.cuda.memory_allocated(0))

        # Inspeccion interna de AutoBackend tras warmup
        ab = det_exp._model.predictor.model
        head = ab.model.model[-1]
        autobackend_inspection = {
            "end2end": bool(getattr(ab, "end2end", False)),
            "one2one_cv2_present": getattr(head, "one2one_cv2", None) is not None,
            "one2many_cv2_released": getattr(head, "cv2", None) is None,
            "param_dtype": str(next(ab.model.parameters()).dtype),
        }

        # 2A. Flujo alternado multi-cámara (40 frames: 20 ENTRADA, 20 SALIDA)
        seq_latencies: List[float] = []
        seq_classes: Counter = Counter()
        seq_statuses: Counter = Counter()
        for i in range(40):
            cam = "CAM-ENTRADA" if i % 2 == 0 else "CAM-SALIDA"
            fr = real_frames[cam][i % len(real_frames[cam])]
            coord_exp.registry.get_slot(cam).source.push_frame(fr)
            t0 = time.perf_counter()
            env = coord_exp.process_camera_step(cam)
            torch.cuda.synchronize(0)
            seq_latencies.append((time.perf_counter() - t0) * 1000.0)
            if env is not None:
                seq_statuses[env.vision_result.status.value] += 1
                for d in env.detections_in_roi:
                    seq_classes[d.raw_label] += 1

        vram_post_seq_mb = _mib(torch.cuda.memory_allocated(0))

        # 2B. Ráfaga concurrente multi-hilo (CAM-ENTRADA + CAM-SALIDA simultáneos, 20+20)
        concurrent_errors: List[str] = []
        concurrent_counts: Counter = Counter()
        conc_lock = threading.Lock()

        def _cam_worker(cam_code: str, frames: List[np.ndarray], count: int) -> None:
            try:
                slot = coord_exp.registry.get_slot(cam_code)
                for idx in range(count):
                    slot.source.push_frame(frames[idx % len(frames)])
                    env = coord_exp.process_camera_step(cam_code)
                    with conc_lock:
                        concurrent_counts[env.vision_result.status.value if env else "NONE"] += 1
            except BaseException as exc:
                with conc_lock:
                    concurrent_errors.append(f"{cam_code}: {type(exc).__name__}: {exc}")

        t_conc0 = time.perf_counter()
        th_ent = threading.Thread(
            target=_cam_worker, args=("CAM-ENTRADA", real_frames["CAM-ENTRADA"], 20)
        )
        th_sal = threading.Thread(
            target=_cam_worker, args=("CAM-SALIDA", real_frames["CAM-SALIDA"], 20)
        )
        th_ent.start()
        th_sal.start()
        th_ent.join()
        th_sal.join()
        torch.cuda.synchronize(0)
        concurrent_wall_ms = round((time.perf_counter() - t_conc0) * 1000.0, 2)
        vram_post_burst_mb = _mib(torch.cuda.memory_allocated(0))

        scenario_2 = {
            "runtime_status": det_exp.get_runtime_status(),
            "load_time_ms": exp_load_ms,
            "autobackend_inspection": autobackend_inspection,
            "alternating_40_frames": {
                "latency": _latency_stats(seq_latencies),
                "statuses": dict(seq_statuses),
                "roi_detections_by_class": dict(seq_classes),
            },
            "concurrent_40_frames_multithread": {
                "total_wall_ms": concurrent_wall_ms,
                "effective_throughput_fps": round(40.0 / (concurrent_wall_ms / 1000.0), 2),
                "statuses": dict(concurrent_counts),
                "errors": concurrent_errors,
            },
            "vram": {
                "after_load_allocated_mb": vram_after_load_mb,
                "post_warmup_allocated_mb": vram_post_warmup_mb,
                "post_seq_allocated_mb": vram_post_seq_mb,
                "post_burst_allocated_mb": vram_post_burst_mb,
                "delta_warmup_to_burst_mb": round(vram_post_burst_mb - vram_post_warmup_mb, 2),
                "reserved_mb": _mib(torch.cuda.memory_reserved(0)),
                "peak_allocated_mb": _mib(torch.cuda.max_memory_allocated(0)),
                "peak_reserved_mb": _mib(torch.cuda.max_memory_reserved(0)),
            },
        }
        coord_exp.shutdown()
        del det_exp, coord_exp
        torch.cuda.empty_cache()

        # ------------------------------------------------------------------
        # Escenario 3: Pruebas controladas de Fallback en GPU CUDA
        # ------------------------------------------------------------------
        # 3a. Fallo en inicialización (archivo .pt corrupto)
        corrupt_pt = tmp_root / "corrupt_primary.pt"
        corrupt_pt.write_bytes(b"CORRUPTED_CHECKPOINT_BYTES")
        det_fb_init = YoloVehicleDetector(
            config=YoloDetectorConfig(
                model_path=str(corrupt_pt),
                confidence_threshold=0.25,
                device="cuda:0",
                imgsz=640,
                quantize=16,
                nms=False,
                fallback_enabled=True,
                fallback_model_path="yolo11n.pt",
            )
        )
        dets_init_fb = det_fb_init.detect(bus_img)
        fb_init_info = {
            "using_fallback": det_fb_init.using_fallback,
            "fallback_reason": det_fb_init.fallback_reason,
            "effective_model": Path(det_fb_init.effective_model_path).name,
            "detections_count": len(dets_init_fb),
            "labels": [d.raw_label for d in dets_init_fb],
        }

        # 3b. Fallo en runtime dentro de VisionEngineCoordinator con recuperación en vivo
        det_fb_rt = YoloVehicleDetector(
            config=YoloDetectorConfig(
                model_path="yolo26x.pt",
                confidence_threshold=0.25,
                device="cuda:0",
                imgsz=640,
                quantize=16,
                nms=False,
                fallback_enabled=True,
                fallback_model_path="yolo11n.pt",
            )
        )
        coord_fb = _build_coordinator(det_fb_rt, tmp_root / "ev_fb")
        coord_fb.initialize()
        det_fb_rt.load_model()

        # Inyectar fallo CUDA OOM simulado en una sola llamada de predict()
        real_model_obj = det_fb_rt._model
        orig_predict = real_model_obj.predict

        def _failing_predict_once(*args: Any, **kwargs: Any) -> Any:
            real_model_obj.predict = orig_predict
            raise RuntimeError("CUDA out of memory simulated on runtime batch")

        real_model_obj.predict = _failing_predict_once  # type: ignore[method-assign]
        coord_fb.registry.get_slot("CAM-ENTRADA").source.push_frame(bus_img)
        env_recovered = coord_fb.process_camera_step("CAM-ENTRADA")
        coord_fb.registry.get_slot("CAM-SALIDA").source.push_frame(real_frames["CAM-SALIDA"][0])
        env_next = coord_fb.process_camera_step("CAM-SALIDA")
        fb_rt_info = {
            "using_fallback": det_fb_rt.using_fallback,
            "fallback_reason": det_fb_rt.fallback_reason,
            "effective_model": Path(det_fb_rt.effective_model_path).name,
            "recovered_frame_status": env_recovered.vision_result.status.value if env_recovered else None,
            "recovered_detections": len(env_recovered.detections_in_roi) if env_recovered else 0,
            "next_camera_frame_status": env_next.vision_result.status.value if env_next else None,
        }
        coord_fb.shutdown()

        output = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "hardware": {
                "gpu_name": torch.cuda.get_device_name(0),
                "total_vram_mb": _mib(gpu_props.total_memory),
                "torch_version": torch.__version__,
                "ultralytics_version": ultralytics.__version__,
            },
            "scenario_1_default_yolo11n": scenario_1,
            "scenario_2_experimental_yolo26x": scenario_2,
            "scenario_3_fallback_gpu": {
                "init_corrupt_weights": fb_init_info,
                "runtime_coordinator_recovery": fb_rt_info,
            },
        }

        out_path = REPO_ROOT / "experiments" / "yolo26x" / "results" / "vision_03c2_integration_metrics.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(output, indent=2, ensure_ascii=False))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    main()
