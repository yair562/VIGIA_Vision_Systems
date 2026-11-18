"""
experiments.yolo26x.scripts.validate_vision_03c3_operational
==========================================================
Validación operativa, comparativa diagnóstica, pipeline end-to-end simulado,
estabilidad térmica/VRAM sostenida y fallback controlado de YOLO26x (VISION-03C.3).

Guarda resultados verificables en:
``experiments/yolo26x/results/vision_03c3_operational_results.json``
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from unittest.mock import patch
from uuid import uuid4

import cv2
import numpy as np
import torch
import ultralytics

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from VIGIA_API.ingest_service import create_ingest_app
from VIGIA_Core.domain.vision_result import VisionStatus
from VIGIA_Core.repository.detection_repository import DetectionInsertDTO, IDetectionRepository
from VIGIA_Core.repository.user_repository import InMemoryUserRepository
from VIGIA_Core.security.password_hasher import hash_password
from VIGIA_Vision.capture.sources import MobilePushFrameBuffer
from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.config.topology_validator import (
    AreaConfigDTO,
    CameraConfigDTO,
    ITopologyConfigRepository,
    TopologyValidator,
)
from VIGIA_Vision.detection.models import RawVehicleDetection
from VIGIA_Vision.detection.roi_and_preprocess import filter_detections_by_roi, project_normalized_roi
from VIGIA_Vision.detection.yolo_detector import (
    YoloDetectorConfig,
    YoloVehicleDetector,
    load_yolo_config_from_env,
)
from VIGIA_Vision.runtime.coordinator import (
    VisionEngineCoordinator,
    map_raw_label_to_domain_vehicle_type,
)
from VIGIA_Vision.runtime.evidence_storage import LocalDiskEvidenceStorage
from VIGIA_Vision.runtime.temporal_state import CameraTemporalStateTracker, TemporalStateConfig


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


class _InMemoryDetectionRepo(IDetectionRepository):
    def __init__(self) -> None:
        self.records: List[DetectionInsertDTO] = []
        self._lock = threading.Lock()

    def persist_detection(self, data: DetectionInsertDTO) -> Any:
        with self._lock:
            self.records.append(data)
        return uuid4()


def _mib(bytes_val: int) -> float:
    return round(bytes_val / (1024.0 * 1024.0), 2)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _query_nvidia_smi() -> Dict[str, Any]:
    try:
        res = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=temperature.gpu,utilization.gpu,utilization.memory,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        parts = [p.strip() for p in res.stdout.strip().splitlines()[0].split(",")]
        return {
            "temp_c": float(parts[0]),
            "gpu_util_pct": float(parts[1]),
            "mem_util_pct": float(parts[2]),
            "vram_used_mb": float(parts[3]),
            "vram_total_mb": float(parts[4]),
        }
    except Exception as exc:
        return {"error": str(exc)}


def _latency_percentiles(ms_values: List[float]) -> Dict[str, Any]:
    ordered = sorted(ms_values)
    n = len(ordered)
    if n == 0:
        return {"count": 0}

    def pct(p: float) -> float:
        idx = min(n - 1, max(0, int(round(p * (n - 1)))))
        return round(ordered[idx], 3)

    mean_ms = statistics.mean(ordered)
    return {
        "count": n,
        "mean_ms": round(mean_ms, 3),
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": pct(0.95),
        "p99_ms": pct(0.99),
        "min_ms": round(ordered[0], 3),
        "max_ms": round(ordered[-1], 3),
        "fps": round(1000.0 / mean_ms, 2) if mean_ms > 0 else 0.0,
    }


def _bbox_iou(a: RawVehicleDetection, b: RawVehicleDetection) -> float:
    ax1, ay1, ax2, ay2 = a.bbox.x_min, a.bbox.y_min, a.bbox.x_max, a.bbox.y_max
    bx1, by1, bx2, by2 = b.bbox.x_min, b.bbox.y_min, b.bbox.x_max, b.bbox.y_max
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = float((ix2 - ix1) * (iy2 - iy1))
    area_a = float((ax2 - ax1) * (ay2 - ay1))
    area_b = float((bx2 - bx1) * (by2 - by1))
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _count_intra_duplicates(dets: Sequence[RawVehicleDetection], iou_thresh: float = 0.50) -> int:
    dups = 0
    for i in range(len(dets)):
        for j in range(i + 1, len(dets)):
            if _bbox_iou(dets[i], dets[j]) >= iou_thresh:
                dups += 1
    return dups


def phase_b_corpus_inventory() -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    ev_root = REPO_ROOT / "evidencias_vigia"
    orig_files = sorted(ev_root.rglob("*_orig.jpg"))
    annot_files = sorted(ev_root.rglob("*_annot.jpg"))

    hashes: Dict[str, int] = {}
    corrupt_files: List[str] = []
    resolutions: Counter = Counter()
    by_date: Counter = Counter()
    by_camera: Counter = Counter()

    for p in orig_files:
        rel_parts = p.relative_to(ev_root).parts
        if len(rel_parts) >= 2:
            by_date[rel_parts[0]] += 1
            by_camera[rel_parts[1]] += 1
        h = _sha256_file(p)
        hashes[h] = hashes.get(h, 0) + 1
        img = cv2.imread(str(p))
        if img is None:
            corrupt_files.append(str(p))
        else:
            resolutions[f"{img.shape[1]}x{img.shape[0]}"] += 1

    duplicate_groups = sum(1 for c in hashes.values() if c > 1)
    duplicate_extra_files = sum(c - 1 for c in hashes.values() if c > 1)

    # Cargar VIGIA-BENCH-v1
    bench_dir = REPO_ROOT / "benchmarks" / "vigia_bench_v1"
    manifest = json.loads((bench_dir / "manifest_v1_seed.json").read_text(encoding="utf-8"))
    bench_images = manifest.get("images", [])

    with (bench_dir / "annotation_sheet_v1.csv").open("r", encoding="utf-8") as fh:
        csv_rows = list(csv.DictReader(fh))
    annotated_human_count = sum(
        1 for r in csv_rows if r.get("annotation_status") != "PENDING_HUMAN_REVIEW"
    )

    bench_domains: Counter = Counter()
    bench_lighting: Counter = Counter()
    bench_sharpness: Counter = Counter()
    bench_resolutions: Counter = Counter()
    bench_readable = 0
    for item in bench_images:
        bench_domains[item.get("source_domain", "UNKNOWN")] += 1
        bench_lighting[item.get("lighting_condition", "UNKNOWN")] += 1
        bench_sharpness[item.get("sharpness_tier", "UNKNOWN")] += 1
        bench_resolutions[f"{item.get('width')}x{item.get('height')}"] += 1
        full_p = ev_root / item["rel_path"]
        if full_p.is_file() and cv2.imread(str(full_p)) is not None:
            bench_readable += 1

    inventory = {
        "evidencias_vigia_corpus": {
            "total_orig_images": len(orig_files),
            "total_annot_images": len(annot_files),
            "corrupt_or_unreadable": len(corrupt_files),
            "unique_sha256": len(hashes),
            "duplicate_groups": duplicate_groups,
            "duplicate_extra_files": duplicate_extra_files,
            "by_date": dict(sorted(by_date.items())),
            "by_camera": dict(sorted(by_camera.items())),
            "resolutions": dict(resolutions),
        },
        "vigia_bench_v1": {
            "total_selected": len(bench_images),
            "readable_files": bench_readable,
            "human_annotated_rows": annotated_human_count,
            "pending_human_review_rows": len(csv_rows) - annotated_human_count,
            "source_domains": dict(bench_domains),
            "real_1to1_vehicles_count": 0,
            "lighting_conditions": dict(bench_lighting),
            "sharpness_tiers": dict(bench_sharpness),
            "resolutions": dict(bench_resolutions),
        },
    }
    return inventory, bench_images


def phase_b_c_comparative_inference(bench_images: List[Dict[str, Any]]) -> Dict[str, Any]:
    ev_root = REPO_ROOT / "evidencias_vigia"
    yolo11_cfg = YoloDetectorConfig(
        model_path="yolo11n.pt",
        confidence_threshold=0.25,
        device="cuda:0",
        imgsz=640,
        quantize=None,
        nms=None,
        fallback_enabled=False,
    )
    yolo26_cfg = YoloDetectorConfig(
        model_path="yolo26x.pt",
        confidence_threshold=0.25,
        device="cuda:0",
        imgsz=640,
        quantize=16,
        nms=False,
        fallback_enabled=False,
    )

    det11 = YoloVehicleDetector(config=yolo11_cfg)
    det26 = YoloVehicleDetector(config=yolo26_cfg)
    det11.load_model()
    det26.load_model()

    # Warmup equivalente con imagen sintética
    warm = np.zeros((480, 640, 3), dtype=np.uint8)
    for _ in range(3):
        det11.detect(warm)
        det26.detect(warm)
    torch.cuda.synchronize(0)

    # ROI idéntico (0.05..0.95)
    eval_area = AreaConfigDTO(
        id_area_vision=uuid4(),
        id_camara=uuid4(),
        codigo="ROI-EVAL",
        nombre="ROI Evaluación",
        tipo_movimiento="ENTRADA",
        x_min=0.05,
        y_min=0.05,
        x_max=0.95,
        y_max=0.95,
        activa=True,
    )

    def _filter_roi(dets: Sequence[RawVehicleDetection], w: int, h: int) -> List[RawVehicleDetection]:
        roi = project_normalized_roi(eval_area, w, h)
        inside, _ = filter_detections_by_roi(dets, roi, 0.25)
        return list(inside)

    groups: Dict[str, Dict[str, Any]] = {}
    lat11_all: List[float] = []
    lat26_all: List[float] = []

    class_confusion: Counter = Counter()
    coco_vs_vigia_11: Counter = Counter()
    coco_vs_vigia_26: Counter = Counter()
    lighting_stats: Dict[str, Dict[str, int]] = {}
    size_anomalies = {"y11_tiny": 0, "y26_tiny": 0, "y11_huge": 0, "y26_huge": 0}
    small_vehicles_5pct = {"y11": 0, "y26": 0}
    intra_dups = {"y11": 0, "y26": 0}

    for item in bench_images:
        domain = item.get("source_domain", "UNKNOWN")
        light = item.get("lighting_condition", "UNKNOWN")
        full_p = ev_root / item["rel_path"]
        frame = cv2.imread(str(full_p))
        if frame is None:
            continue
        h, w = frame.shape[:2]
        frame_area = float(w * h)

        if domain not in groups:
            groups[domain] = {
                "images": 0,
                "y11_frames_with_det_025": 0,
                "y26_frames_with_det_025": 0,
                "y11_frames_with_det_070": 0,
                "y26_frames_with_det_070": 0,
                "y11_total_boxes_025": 0,
                "y26_total_boxes_025": 0,
                "y11_total_boxes_070": 0,
                "y26_total_boxes_070": 0,
                "y26_additional_boxes_025": 0,
                "y11_only_boxes_025": 0,
                "matched_iou_050": 0,
                "y11_classes_025": Counter(),
                "y26_classes_025": Counter(),
                "y11_classes_070": Counter(),
                "y26_classes_070": Counter(),
                "y11_mean_conf_025": [],
                "y26_mean_conf_025": [],
            }
        g = groups[domain]
        g["images"] += 1

        if light not in lighting_stats:
            lighting_stats[light] = {"images": 0, "y11_070": 0, "y26_070": 0, "y11_025": 0, "y26_025": 0}
        lighting_stats[light]["images"] += 1

        t0 = time.perf_counter()
        raw11 = _filter_roi(det11.detect(frame), w, h)
        torch.cuda.synchronize(0)
        lat11_all.append((time.perf_counter() - t0) * 1000.0)

        t0 = time.perf_counter()
        raw26 = _filter_roi(det26.detect(frame), w, h)
        torch.cuda.synchronize(0)
        lat26_all.append((time.perf_counter() - t0) * 1000.0)

        d11_070 = [d for d in raw11 if d.confidence >= 0.70]
        d26_070 = [d for d in raw26 if d.confidence >= 0.70]

        if raw11:
            g["y11_frames_with_det_025"] += 1
            lighting_stats[light]["y11_025"] += 1
        if raw26:
            g["y26_frames_with_det_025"] += 1
            lighting_stats[light]["y26_025"] += 1
        if d11_070:
            g["y11_frames_with_det_070"] += 1
            lighting_stats[light]["y11_070"] += 1
        if d26_070:
            g["y26_frames_with_det_070"] += 1
            lighting_stats[light]["y26_070"] += 1

        g["y11_total_boxes_025"] += len(raw11)
        g["y26_total_boxes_025"] += len(raw26)
        g["y11_total_boxes_070"] += len(d11_070)
        g["y26_total_boxes_070"] += len(d26_070)

        intra_dups["y11"] += _count_intra_duplicates(raw11)
        intra_dups["y26"] += _count_intra_duplicates(raw26)

        for d in raw11:
            g["y11_classes_025"][d.raw_label] += 1
            g["y11_mean_conf_025"].append(d.confidence)
            coco_vs_vigia_11[f"{d.raw_label}->{map_raw_label_to_domain_vehicle_type(d.raw_label)}"] += 1
            ar = (d.bbox.width * d.bbox.height) / frame_area
            if ar < 0.05:
                small_vehicles_5pct["y11"] += 1
            if ar < 0.002:
                size_anomalies["y11_tiny"] += 1
            if ar > 0.85:
                size_anomalies["y11_huge"] += 1

        for d in raw26:
            g["y26_classes_025"][d.raw_label] += 1
            g["y26_mean_conf_025"].append(d.confidence)
            coco_vs_vigia_26[f"{d.raw_label}->{map_raw_label_to_domain_vehicle_type(d.raw_label)}"] += 1
            ar = (d.bbox.width * d.bbox.height) / frame_area
            if ar < 0.05:
                small_vehicles_5pct["y26"] += 1
            if ar < 0.002:
                size_anomalies["y26_tiny"] += 1
            if ar > 0.85:
                size_anomalies["y26_huge"] += 1

        for d in d11_070:
            g["y11_classes_070"][d.raw_label] += 1
        for d in d26_070:
            g["y26_classes_070"][d.raw_label] += 1

        # Emparejamiento por IoU >= 0.50 entre modelos
        matched_26 = set()
        for d1 in raw11:
            best_j = None
            best_iou = 0.0
            for j, d2 in enumerate(raw26):
                if j in matched_26:
                    continue
                iou = _bbox_iou(d1, d2)
                if iou >= 0.50 and iou > best_iou:
                    best_iou = iou
                    best_j = j
            if best_j is not None:
                matched_26.add(best_j)
                g["matched_iou_050"] += 1
                d2 = raw26[best_j]
                if d1.raw_label != d2.raw_label:
                    class_confusion[f"{d1.raw_label}->{d2.raw_label}"] += 1
            else:
                g["y11_only_boxes_025"] += 1

        g["y26_additional_boxes_025"] += len(raw26) - len(matched_26)

    # Stock reference separada (bus.jpg)
    bus_path = Path(ultralytics.__file__).parent / "assets" / "bus.jpg"
    bus_img = cv2.imread(str(bus_path))
    bus_11 = det11.detect(bus_img)
    bus_26 = det26.detect(bus_img)

    # Serializar contadores y promedios
    formatted_groups = {}
    for dom, g in groups.items():
        formatted_groups[dom] = {
            **{k: v for k, v in g.items() if not isinstance(v, (Counter, list))},
            "y11_classes_025": dict(g["y11_classes_025"]),
            "y26_classes_025": dict(g["y26_classes_025"]),
            "y11_classes_070": dict(g["y11_classes_070"]),
            "y26_classes_070": dict(g["y26_classes_070"]),
            "y11_mean_conf_025": round(statistics.mean(g["y11_mean_conf_025"]), 4)
            if g["y11_mean_conf_025"]
            else None,
            "y26_mean_conf_025": round(statistics.mean(g["y26_mean_conf_025"]), 4)
            if g["y26_mean_conf_025"]
            else None,
        }

    del det11, det26
    torch.cuda.empty_cache()

    return {
        "ground_truth_available": False,
        "ground_truth_note": "Los 150 registros de annotation_sheet_v1.csv están en PENDING_HUMAN_REVIEW; análisis estrictamente diagnóstico sin métricas certificadas de precisión.",
        "groups": formatted_groups,
        "stock_reference_bus_jpg": {
            "yolo11n": [{"label": d.raw_label, "conf": round(d.confidence, 4)} for d in bus_11],
            "yolo26x": [{"label": d.raw_label, "conf": round(d.confidence, 4)} for d in bus_26],
        },
        "classification_analysis": {
            "yolo11_to_yolo26_label_diffs_on_matched_iou050": dict(class_confusion),
            "coco_to_vigia_mapping_yolo11": dict(coco_vs_vigia_11),
            "coco_to_vigia_mapping_yolo26": dict(coco_vs_vigia_26),
            "intra_frame_duplicate_boxes_iou050": intra_dups,
            "small_vehicles_lt_5pct_area": small_vehicles_5pct,
            "box_size_anomalies": size_anomalies,
            "lighting_breakdown": lighting_stats,
        },
        "latency_comparison_150_frames": {
            "yolo11n_fp32_cuda": _latency_percentiles(lat11_all),
            "yolo26x_fp16_e2e_cuda": _latency_percentiles(lat26_all),
        },
    }


def phase_d_operational_pipeline() -> Dict[str, Any]:
    tmp_dir = Path(tempfile.mkdtemp(prefix="vigia_03c3_pipe_"))
    try:
        ev_dir = tmp_dir / "ev"
        certs_dir = tmp_dir / "certs"
        empty_env = tmp_dir / ".env.empty"
        empty_env.write_text("", encoding="utf-8")

        topo_repo = _BenchTopoRepo()
        det_repo = _InMemoryDetectionRepo()
        user_repo = InMemoryUserRepository()
        from VIGIA_Core.domain.user import UserDTO

        admin_user = UserDTO(
            id_usuario=uuid4(),
            username="admin_03c3",
            nombre_completo="Admin 03C3",
            rol="ADMINISTRADOR",
            contrasena_hash=hash_password("VigiaTest2026!"),
            activo=True,
        )
        user_repo.create_user(admin_user)

        settings = VisionEngineSettings(
            vehicle_confidence_threshold=0.70,
            mobile_frame_ttl_seconds=5.0,
            evidence_directory=ev_dir,
            save_annotated_evidence=True,
            jpeg_quality=90,
            fail_fast_on_invalid_topology=True,
        )
        storage = LocalDiskEvidenceStorage(base_directory=ev_dir)
        buf_ent = MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=5.0)
        buf_sal = MobilePushFrameBuffer("CAM-SALIDA", ttl_seconds=5.0)

        env_vars = {
            **os.environ,
            "VIGIA_ENV_FILE": str(empty_env),
            "VIGIA_YOLO_MODEL": "yolo26x.pt",
            "VIGIA_YOLO_IMGSZ": "640",
            "VIGIA_YOLO_QUANTIZE": "16",
            "VIGIA_YOLO_NMS": "false",
            "VIGIA_YOLO_DEVICE": "cuda:0",
            "VIGIA_YOLO_FALLBACK_ENABLED": "true",
            "VIGIA_YOLO_FALLBACK_MODEL": "yolo11n.pt",
            "VIGIA_ALLOW_IN_MEMORY": "1",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            yolo_cfg = load_yolo_config_from_env(confidence_threshold=0.25)
            detector = YoloVehicleDetector(config=yolo_cfg)
            coordinator = VisionEngineCoordinator(
                topology_validator=TopologyValidator(repository=topo_repo),
                settings=settings,
                detector=detector,
                detection_repository=det_repo,
                evidence_storage=storage,
                sources={"CAM-ENTRADA": buf_ent, "CAM-SALIDA": buf_sal},
                new_event_predicate=lambda _c, dets: bool(dets),
            )
            coordinator.initialize(open_sources=True)
            app = create_ingest_app(
                coordinator=coordinator,
                user_repository=user_repo,
                topology_repository=topo_repo,
                allow_in_memory=True,
                auth_token="KEY_03C3_TEST",
                certs_dir=certs_dir,
                start_pull_workers=False,
            )

        client = app.test_client()
        # Login en Dashboard/API
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": "admin_03c3", "password": "VigiaTest2026!"},
        )

        # Enviar imagen real de bus.jpg codificada como JPEG por HTTP /push
        bus_img = cv2.imread(str(Path(ultralytics.__file__).parent / "assets" / "bus.jpg"))
        ok_enc, jpg_buf = cv2.imencode(".jpg", bus_img)
        assert ok_enc

        push_resp = client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=jpg_buf.tobytes(),
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": "KEY_03C3_TEST"},
        )
        push_json = push_resp.get_json()

        # Verificar endpoints consumidos por Dashboard
        cams_resp = client.get("/api/v1/cameras")
        status_resp = client.get("/api/v1/cameras/CAM-ENTRADA/status")
        live_resp = client.get("/api/v1/cameras/CAM-ENTRADA/live")
        sup_resp = client.get("/api/v1/supervision/status")
        dash_resp = client.get("/app")

        # Verificar archivos de evidencia generados en disco
        orig_saved = list(ev_dir.rglob("*_orig.jpg"))
        annot_saved = list(ev_dir.rglob("*_annot.jpg"))

        # Verificar compatibilidad de contrato con CameraTemporalStateTracker (aislado hasta 02B)
        fsm = CameraTemporalStateTracker(config=TemporalStateConfig())
        snap1 = fsm.update(
            "CAM-ENTRADA",
            True,
            raw_vehicle_detected=True,
            frame_sequence=1,
            vehicle_type=push_json.get("vehicle_type_pred"),
            vehicle_confidence=push_json.get("vehicle_confidence"),
        )
        snap2 = fsm.update(
            "CAM-ENTRADA",
            True,
            raw_vehicle_detected=True,
            frame_sequence=2,
            vehicle_type=push_json.get("vehicle_type_pred"),
            vehicle_confidence=push_json.get("vehicle_confidence"),
        )

        det_status = detector.get_runtime_status()
        coordinator.shutdown()

        return {
            "stage_1_yolo26x_init": {
                "passed": det_status["effective_model"] == "yolo26x.pt" and det_status["quantize"] == 16,
                "runtime_status": det_status,
            },
            "stage_2_nms_free_verified": {
                "passed": bool(det_status["end2end"]) and bool(det_status["end2end_verified"]),
            },
            "stage_3_http_push_and_coordinator": {
                "passed": push_resp.status_code == 200 and bool(push_json.get("vehicle_detected")),
                "http_status": push_resp.status_code,
                "response": push_json,
            },
            "stage_4_temporal_fsm": {
                "integrated_in_coordinator": False,
                "note": "CameraTemporalStateTracker permanece aislado por diseño de VISION-02A.1 hasta VISION-02B; contrato verificado manualmente.",
                "contract_probe_statuses": [snap1.detection_status.value, snap2.detection_status.value],
            },
            "stage_5_persistence_in_memory_vs_postgres": {
                "in_memory_records_saved": len(det_repo.records),
                "postgres_live_status": "BLOCKED (Docker/PostgreSQL offline en 127.0.0.1:5434)",
            },
            "stage_6_evidence_files_on_disk": {
                "orig_count": len(orig_saved),
                "annot_count": len(annot_saved),
            },
            "stage_7_dashboard_and_streaming_endpoints": {
                "login_status": login_resp.status_code,
                "get_app_html_status": dash_resp.status_code,
                "get_cameras_status": cams_resp.status_code,
                "get_camera_status_code": status_resp.status_code,
                "get_camera_status_payload": status_resp.get_json(),
                "get_camera_live_status": live_resp.status_code,
                "get_camera_live_content_type": live_resp.content_type,
                "get_supervision_status": sup_resp.status_code,
            },
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def phase_e_stability_and_performance(soak_seconds: float = 90.0) -> Dict[str, Any]:
    ev_dir = REPO_ROOT / "evidencias_vigia" / "20261114"
    ent_frames = [cv2.imread(str(p)) for p in sorted((ev_dir / "CAM-ENTRADA").glob("*_orig.jpg"))[:8]]
    sal_frames = [cv2.imread(str(p)) for p in sorted((ev_dir / "CAM-SALIDA").glob("*_orig.jpg"))[-8:]]
    ent_frames = [f for f in ent_frames if f is not None]
    sal_frames = [f for f in sal_frames if f is not None]

    cfg = YoloDetectorConfig(
        model_path="yolo26x.pt",
        confidence_threshold=0.25,
        device="cuda:0",
        imgsz=640,
        quantize=16,
        nms=False,
        fallback_enabled=True,
        fallback_model_path="yolo11n.pt",
    )
    detector = YoloVehicleDetector(config=cfg)
    detector.load_model()
    for i in range(4):
        detector.detect(ent_frames[i % len(ent_frames)])
    torch.cuda.synchronize(0)

    # 1. Inferencia aislada (200 frames)
    iso_lat: List[float] = []
    for i in range(200):
        fr = ent_frames[i % len(ent_frames)] if i % 2 == 0 else sal_frames[i % len(sal_frames)]
        t0 = time.perf_counter()
        detector.detect(fr)
        torch.cuda.synchronize(0)
        iso_lat.append((time.perf_counter() - t0) * 1000.0)

    # 2. Multi-worker concurrente (2 hilos CAM-ENTRADA y CAM-SALIDA en VisionEngineCoordinator)
    tmp_dir = Path(tempfile.mkdtemp(prefix="vigia_03c3_perf_"))
    try:
        topo_repo = _BenchTopoRepo()
        buf_ent = MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=10.0)
        buf_sal = MobilePushFrameBuffer("CAM-SALIDA", ttl_seconds=10.0)
        coord = VisionEngineCoordinator(
            topology_validator=TopologyValidator(repository=topo_repo),
            settings=VisionEngineSettings(
                vehicle_confidence_threshold=0.70,
                evidence_directory=tmp_dir / "ev",
                save_annotated_evidence=False,
            ),
            detector=detector,
            evidence_storage=LocalDiskEvidenceStorage(base_directory=tmp_dir / "ev"),
            sources={"CAM-ENTRADA": buf_ent, "CAM-SALIDA": buf_sal},
        )
        coord.initialize(open_sources=True)

        worker_lats: Dict[str, List[float]] = {"CAM-ENTRADA": [], "CAM-SALIDA": []}
        worker_errors: List[str] = []
        w_lock = threading.Lock()

        def _worker(cam: str, frames: List[np.ndarray], count: int) -> None:
            try:
                slot = coord.registry.get_slot(cam)
                for idx in range(count):
                    slot.source.push_frame(frames[idx % len(frames)])
                    t0 = time.perf_counter()
                    env = coord.process_camera_step(cam)
                    torch.cuda.synchronize(0)
                    dt = (time.perf_counter() - t0) * 1000.0
                    with w_lock:
                        worker_lats[cam].append(dt)
                        if env is None or env.vision_result.status == VisionStatus.VISION_ERROR:
                            worker_errors.append(f"{cam} idx={idx} status={env.vision_result.status if env else None}")
            except BaseException as exc:
                with w_lock:
                    worker_errors.append(f"{cam}: {exc}")

        t_w0 = time.perf_counter()
        t1 = threading.Thread(target=_worker, args=("CAM-ENTRADA", ent_frames, 100))
        t2 = threading.Thread(target=_worker, args=("CAM-SALIDA", sal_frames, 100))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        wall_ms = (time.perf_counter() - t_w0) * 1000.0

        # 3. End-to-end HTTP ingest (100 pushes via Flask test_client, JPEG encode/decode + coordinator + storage)
        user_repo = InMemoryUserRepository()
        det_repo = _InMemoryDetectionRepo()
        coord_e2e = VisionEngineCoordinator(
            topology_validator=TopologyValidator(repository=topo_repo),
            settings=VisionEngineSettings(
                vehicle_confidence_threshold=0.70,
                evidence_directory=tmp_dir / "ev_e2e",
                save_annotated_evidence=True,
            ),
            detector=detector,
            detection_repository=det_repo,
            evidence_storage=LocalDiskEvidenceStorage(base_directory=tmp_dir / "ev_e2e"),
            sources={
                "CAM-ENTRADA": MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=10.0),
                "CAM-SALIDA": MobilePushFrameBuffer("CAM-SALIDA", ttl_seconds=10.0),
            },
            new_event_predicate=lambda _c, dets: bool(dets),
        )
        coord_e2e.initialize(open_sources=True)
        app = create_ingest_app(
            coordinator=coord_e2e,
            user_repository=user_repo,
            topology_repository=topo_repo,
            allow_in_memory=True,
            auth_token="KEY_E2E_03C3",
            certs_dir=tmp_dir / "certs",
            start_pull_workers=False,
        )
        client = app.test_client()
        jpg_payloads = []
        for fr in ent_frames[:4]:
            ok, buf = cv2.imencode(".jpg", fr)
            assert ok
            jpg_payloads.append(buf.tobytes())

        e2e_lats: List[float] = []
        e2e_errors = 0
        for idx in range(100):
            payload = jpg_payloads[idx % len(jpg_payloads)]
            t0 = time.perf_counter()
            r = client.post(
                "/api/v1/cameras/CAM-ENTRADA/push",
                data=payload,
                headers={"Content-Type": "image/jpeg", "X-Camera-Key": "KEY_E2E_03C3"},
            )
            e2e_lats.append((time.perf_counter() - t0) * 1000.0)
            if r.status_code != 200:
                e2e_errors += 1

        # 4. Prueba sostenida GPU (soak_seconds continuos)
        torch.cuda.reset_peak_memory_stats(0)
        vram_start = _mib(torch.cuda.memory_allocated(0))
        telemetry_samples: List[Dict[str, Any]] = []
        soak_frames = 0
        soak_errors = 0
        soak_lats: List[float] = []
        t_start = time.perf_counter()
        last_sample = -10.0
        cpu_start = time.process_time()

        while (time.perf_counter() - t_start) < soak_seconds:
            fr = ent_frames[soak_frames % len(ent_frames)] if soak_frames % 2 == 0 else sal_frames[soak_frames % len(sal_frames)]
            t0 = time.perf_counter()
            try:
                detector.detect(fr)
                torch.cuda.synchronize(0)
                soak_lats.append((time.perf_counter() - t0) * 1000.0)
            except Exception:
                soak_errors += 1
            soak_frames += 1
            elapsed = time.perf_counter() - t_start
            if elapsed - last_sample >= 15.0:
                last_sample = elapsed
                smi = _query_nvidia_smi()
                telemetry_samples.append(
                    {
                        "elapsed_s": round(elapsed, 1),
                        "frames": soak_frames,
                        "vram_allocated_mb": _mib(torch.cuda.memory_allocated(0)),
                        "vram_reserved_mb": _mib(torch.cuda.memory_reserved(0)),
                        **smi,
                    }
                )

        soak_wall = time.perf_counter() - t_start
        cpu_used = time.process_time() - cpu_start
        vram_end = _mib(torch.cuda.memory_allocated(0))
        smi_end = _query_nvidia_smi()

        coord.shutdown()
        coord_e2e.shutdown()

        return {
            "isolated_inference_200_frames": _latency_percentiles(iso_lat),
            "multi_worker_200_frames_concurrent": {
                "cam_entrada_100": _latency_percentiles(worker_lats["CAM-ENTRADA"]),
                "cam_salida_100": _latency_percentiles(worker_lats["CAM-SALIDA"]),
                "combined_wall_ms": round(wall_ms, 2),
                "combined_aggregate_fps": round(200.0 / (wall_ms / 1000.0), 2),
                "errors": worker_errors,
            },
            "end_to_end_http_push_100_frames": {
                "latency": _latency_percentiles(e2e_lats),
                "http_errors": e2e_errors,
                "persisted_in_memory": len(det_repo.records),
            },
            "sustained_gpu_soak": {
                "duration_s": round(soak_wall, 2),
                "total_frames": soak_frames,
                "errors": soak_errors,
                "using_fallback_after_soak": detector.using_fallback,
                "effective_model_after_soak": Path(detector.effective_model_path).name,
                "latency": _latency_percentiles(soak_lats),
                "vram_start_mb": vram_start,
                "vram_end_mb": vram_end,
                "vram_delta_mb": round(vram_end - vram_start, 2),
                "vram_peak_allocated_mb": _mib(torch.cuda.max_memory_allocated(0)),
                "vram_peak_reserved_mb": _mib(torch.cuda.max_memory_reserved(0)),
                "cpu_process_pct_single_core": round((cpu_used / soak_wall) * 100.0, 2),
                "final_gpu_smi": smi_end,
                "telemetry_samples": telemetry_samples,
            },
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        del detector
        torch.cuda.empty_cache()


def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA no está disponible.")

    torch.cuda.init()
    print("[1/4] Fase B: Inventario de corpus...")
    inventory, bench_images = phase_b_corpus_inventory()

    print("[2/4] Fase B/C: Comparativa YOLO11n vs YOLO26x sobre 150 imagenes...")
    comparative = phase_b_c_comparative_inference(bench_images)

    print("[3/4] Fase D: Validación del pipeline operativo...")
    pipeline = phase_d_operational_pipeline()

    print("[4/4] Fase E: Estabilidad sostenida GPU (90s) y rendimiento...")
    stability = phase_e_stability_and_performance(soak_seconds=90.0)

    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "hardware": {
            "gpu_name": torch.cuda.get_device_name(0),
            "total_vram_mb": _mib(torch.cuda.get_device_properties(0).total_memory),
            "torch_version": torch.__version__,
            "ultralytics_version": ultralytics.__version__,
        },
        "phase_b_inventory": inventory,
        "phase_bc_comparative": comparative,
        "phase_d_pipeline": pipeline,
        "phase_e_stability": stability,
    }
    out_path = REPO_ROOT / "experiments" / "yolo26x" / "results" / "vision_03c3_operational_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OK -> {out_path}")


if __name__ == "__main__":
    main()
