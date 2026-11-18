"""
VISION-07B — Evaluacion Integral Offline (Read-Only sobre Produccion)
====================================================================
Evalua de manera reproducible y no destructiva:
- FASE B: Deteccion vehicular con YoloVehicleDetector (YOLO26x prod config).
- FASE C: Clasificador de color de produccion (VIGIA_Vision.detection.color_classifier)
          vs clasificador evaluado en VISION-05B (VIGIA_Vision.classification.color_classifier)
          en las 12 categorias, corpus historico, capturas 20261117 y estabilidad temporal.
- FASE D: Integridad de asociacion vehiculo-color (aislamiento de crop, multi-vehiculo,
          coordinador aislado dual-camara en memoria y abstencion UNKNOWN).
- FASE G: Viabilidad optica preliminar para LPR/ANPR en CAM-ENTRADA y CAM-SALIDA.

No modifica .env, pesos, BD PostgreSQL, evidencias originales ni el servicio en ejecucion.
"""

from __future__ import annotations

import glob
import json
import os
import statistics
import sys
import tempfile
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

import cv2
import numpy as np
from dotenv import load_dotenv

ROOT = Path(r"C:\GEST.PROY.TI\Software\VIGIA_Vision_Systems")
ENV_PATH = Path(r"C:\GEST.PROY.TI\Software\.env")
sys.path.insert(0, str(ROOT))
load_dotenv(ENV_PATH)

from VIGIA_Vision.detection.yolo_detector import YoloVehicleDetector, load_yolo_config_from_env
from VIGIA_Vision.detection.models import BoundingBox, CaptureReadResult, RawVehicleDetection
from VIGIA_Vision.detection.roi_and_preprocess import PixelROI, filter_detections_by_roi
from VIGIA_Vision.detection.color_classifier import (
    ColorClassificationStatus as ProdColorStatus,
    VehicleColor as ProdVehicleColor,
    VehicleColorClassifier as ProdColorClassifier,
    load_color_config_from_env,
)
from VIGIA_Vision.classification import (
    VehicleColor as BenchVehicleColor,
    VehicleColorClassifier as BenchColorClassifier,
)
from VIGIA_Vision.runtime.coordinator import (
    IFrameCaptureSource,
    OperationalTopologyDTO,
    TopologyValidator,
    VisionEngineCoordinator,
    VisionEngineSettings,
)
from VIGIA_Vision.runtime.evidence_storage import LocalDiskEvidenceStorage

EVIDENCE_DIR = ROOT / "evidencias_vigia"
INVENTORY_PATH = ROOT / "experiments" / "vision_05a" / "results" / "etapa_a_b_classified_inventory.json"
BENCH_05B_PATH = ROOT / "experiments" / "vision_05b" / "results" / "benchmark_color_results.json"
OUT_JSON = ROOT / "experiments" / "vision_07b" / "results" / "vision_07b_evaluation_results.json"

ALL_12_COLORS = [
    "WHITE", "BLACK", "GRAY", "SILVER",
    "RED", "BLUE", "GREEN", "YELLOW",
    "BROWN", "ORANGE", "OTHER", "UNKNOWN",
]


def default_roi_for_frame(w: int, h: int) -> PixelROI:
    """ROI normativo de produccion: x in [0.1, 0.9], y in [0.2, 0.8]."""
    return PixelROI(
        x_min=int(round(0.1 * w)),
        y_min=int(round(0.2 * h)),
        x_max=int(round(0.9 * w)),
        y_max=int(round(0.8 * h)),
        frame_width=w,
        frame_height=h,
    )


def pct_stats(vals: List[float]) -> Dict[str, Any]:
    if not vals:
        return {"count": 0, "mean": None, "median": None, "p10": None, "p90": None, "p95": None, "p99": None, "min": None, "max": None}
    s = sorted(vals)
    n = len(s)
    def q(p: float) -> float:
        idx = min(n - 1, max(0, int(round(p * (n - 1)))))
        return round(float(s[idx]), 3)
    return {
        "count": n,
        "mean": round(float(statistics.mean(s)), 3),
        "median": round(float(statistics.median(s)), 3),
        "stdev": round(float(statistics.pstdev(s)), 3),
        "p10": q(0.10),
        "p90": q(0.90),
        "p95": q(0.95),
        "p99": q(0.99),
        "min": round(float(s[0]), 3),
        "max": round(float(s[-1]), 3),
    }


def compute_image_optical_metrics(img_bgr: np.ndarray) -> Dict[str, float]:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    lum = float(np.mean(gray))
    glare_pct = float(np.mean(gray >= 245) * 100.0)
    dark_pct = float(np.mean(gray <= 25) * 100.0)
    contrast_rms = float(np.std(gray))
    return {
        "laplacian_var": round(lap, 2),
        "luminance_mean": round(lum, 2),
        "contrast_rms": round(contrast_rms, 2),
        "glare_pct": round(glare_pct, 3),
        "dark_pct": round(dark_pct, 3),
    }


# ---------------------------------------------------------------------------
# FASE D — Pruebas de Integridad Vehiculo-Color (Aisladas en Memoria)
# ---------------------------------------------------------------------------

class _StubFrameSource:
    def __init__(self, frames: List[np.ndarray]):
        self._frames = list(frames)
        self._opened = True
        self._seq = 0

    def open(self) -> None:
        self._opened = True

    def is_opened(self) -> bool:
        return self._opened

    def read_frame(self) -> CaptureReadResult:
        if not self._frames:
            raise RuntimeError("No more stub frames")
        self._seq += 1
        arr = self._frames.pop(0) if len(self._frames) > 1 else self._frames[0].copy()
        return CaptureReadResult(
            ok=True,
            frame=arr,
            captured_at=datetime.now(timezone.utc),
            frame_sequence=self._seq,
        )

    def release(self) -> None:
        self._opened = False


class _InMemoryDetRepo:
    def __init__(self) -> None:
        self.rows: List[Any] = []
        self._lock = threading.Lock()

    def persist_detection(self, dto: Any) -> Any:
        with self._lock:
            self.rows.append(dto)
        return uuid4()


def _build_synthetic_vehicle_frame(
    width: int,
    height: int,
    vehicles: List[Tuple[Tuple[int, int, int, int], Tuple[int, int, int]]],
    bg_bgr: Tuple[int, int, int] = (50, 52, 48),
) -> np.ndarray:
    """Genera frame sintetico con vehiculo(s) con parabrisas/llantas simuladas."""
    img = np.full((height, width, 3), bg_bgr, dtype=np.uint8)
    for (x1, y1, x2, y2), bgr in vehicles:
        # Carroceria
        cv2.rectangle(img, (x1, y1), (x2, y2), bgr, thickness=-1)
        vw, vh = x2 - x1, y2 - y1
        # Parabrisas oscuro simulado en zona superior-media [0.24..0.42]
        wx1, wx2 = x1 + int(0.18 * vw), x2 - int(0.18 * vw)
        wy1, wy2 = y1 + int(0.24 * vh), y1 + int(0.42 * vh)
        cv2.rectangle(img, (wx1, wy1), (wx2, wy2), (35, 35, 38), thickness=-1)
        # Franja inferior simulando neumaticos/sombra
        cv2.rectangle(img, (x1, y2 - int(0.14 * vh)), (x2, y2), (20, 20, 20), thickness=-1)
    return img


def run_fase_d_integrity(
    detector: YoloVehicleDetector,
    prod_color: ProdColorClassifier,
) -> Dict[str, Any]:
    print("[FASE D] Ejecutando suite aislada de integridad vehiculo-color...")
    results: Dict[str, Any] = {}

    # D1. Aislamiento estricto de ROI / cero fuga entre bounding boxes en frames reales multi-vehiculo
    multi_frames = [
        ("20261117_multi_3veh", EVIDENCE_DIR / "20261117/CAM-SALIDA/20261117T010754_845446Z_7d11d36aea9a_orig.jpg"),
        ("20261116_bus_red_2veh", EVIDENCE_DIR / "20261116/CAM-SALIDA/20261116T172203_520604Z_e0c6c9b2989f_orig.jpg"),
        ("20261116_pink_cyan_2veh", EVIDENCE_DIR / "20261116/CAM-SALIDA/20261116T171957_156573Z_06fd6441d05f_orig.jpg"),
        ("20261117_occluded_multi", EVIDENCE_DIR / "20261117/CAM-ENTRADA/20261117T013132_371353Z_4340677faa95_orig.jpg"),
    ]
    crop_isolation_cases = []
    all_crop_isolated = True
    for name, fpath in multi_frames:
        img = cv2.imread(str(fpath))
        h, w = img.shape[:2]
        roi = default_roi_for_frame(w, h)
        preds = detector.detect(img, camera_code="FASE_D")
        in_roi, _ = filter_detections_by_roi(preds, roi, min_confidence=0.25)
        per_det = []
        for idx, d in enumerate(in_roi):
            orig_res = prod_color.classify(img, d.bbox, vehicle_class=d.raw_label, detection_confidence=d.confidence)
            # Pintar TODO el resto del frame fuera de d.bbox de verde puro (0, 255, 0)
            perturbed = np.full_like(img, (0, 255, 0))
            bx1, by1 = max(0, d.bbox.x_min), max(0, d.bbox.y_min)
            bx2, by2 = min(w, d.bbox.x_max), min(h, d.bbox.y_max)
            perturbed[by1:by2, bx1:bx2] = img[by1:by2, bx1:bx2]
            pert_res = prod_color.classify(perturbed, d.bbox, vehicle_class=d.raw_label, detection_confidence=d.confidence)
            identical = (
                orig_res.predominant_color == pert_res.predominant_color
                and abs(orig_res.confidence - pert_res.confidence) < 1e-9
                and orig_res.status == pert_res.status
            )
            if not identical:
                all_crop_isolated = False
            per_det.append({
                "det_index": idx,
                "label": d.raw_label,
                "det_conf": round(d.confidence, 4),
                "bbox": [d.bbox.x_min, d.bbox.y_min, d.bbox.x_max, d.bbox.y_max],
                "color_pred": orig_res.predominant_color.value,
                "color_conf": round(orig_res.confidence, 4),
                "color_status": orig_res.status.value,
                "strict_crop_isolated": identical,
            })
        crop_isolation_cases.append({"case": name, "roi_detections_025": len(in_roi), "detections": per_det})

    # D2. Pruebas sinteticas de solapamiento controlado (vehiculo primario RED, vecino intrusivo BLUE en bordes)
    overlap_tests = []
    for overlap_frac in (0.0, 0.15, 0.30, 0.50):
        # Caja vehiculo A (objetivo): x=[200..420] (w=220), y=[150..350] (h=200)
        # Caja vecina pintando franja derecha dentro de A segun overlap_frac
        frame = _build_synthetic_vehicle_frame(640, 480, [((200, 150, 420, 350), (20, 20, 210))])
        if overlap_frac > 0:
            cut_x = 420 - int(220 * overlap_frac)
            cv2.rectangle(frame, (cut_x, 150), (580, 360), (210, 40, 20), thickness=-1)
        res_a = prod_color.classify(frame, BoundingBox(200, 150, 420, 350), vehicle_class="car", detection_confidence=0.95)
        overlap_tests.append({
            "neighbor_intrusion_width_frac": overlap_frac,
            "target_true_color": "RED",
            "intruder_color": "BLUE",
            "predicted_color": res_a.predominant_color.value,
            "confidence": round(res_a.confidence, 4),
            "status": res_a.status.value,
        })

    # D3. Comportamiento de VisionEngineCoordinator real en multi-vehiculo + aislamiento dual-camara
    coord_findings: Dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="vigia_07b_d3_") as tmpdir:
        tmp_path = Path(tmpdir)
        tv_g = TopologyValidator.validate.__globals__
        CamDTO = tv_g["CameraConfigDTO"]
        AreaDTO = tv_g["AreaConfigDTO"]
        TVResult = tv_g["TopologyValidationResult"]

        cam_ent = CamDTO(
            id_camara=uuid4(), codigo="CAM-ENTRADA", nombre="Entrada Test",
            uri_stream="stub://ent", activa=True,
        )
        area_ent = AreaDTO(
            id_area_vision=uuid4(), id_camara=cam_ent.id_camara, codigo="ROI-ENT",
            nombre="ROI Ent", tipo_movimiento="ENTRADA", x_min=0.1, y_min=0.2, x_max=0.9, y_max=0.8, activa=True,
        )
        cam_sal = CamDTO(
            id_camara=uuid4(), codigo="CAM-SALIDA", nombre="Salida Test",
            uri_stream="stub://sal", activa=True,
        )
        area_sal = AreaDTO(
            id_area_vision=uuid4(), id_camara=cam_sal.id_camara, codigo="ROI-SAL",
            nombre="ROI Sal", tipo_movimiento="SALIDA", x_min=0.1, y_min=0.2, x_max=0.9, y_max=0.8, activa=True,
        )
        topo = OperationalTopologyDTO(cam_entrada=cam_ent, area_entrada=area_ent, cam_salida=cam_sal, area_salida=area_sal)

        class _MockTopoValidator(TopologyValidator):
            def __init__(self) -> None:
                pass

            def validate(self, cameras=None, areas=None):
                return TVResult(is_valid=True, topology=topo)

        # Frames reales: 3-vehiculos para CAM-ENTRADA, bus amarillo+rojo para CAM-SALIDA
        frame_multi_3 = cv2.imread(str(EVIDENCE_DIR / "20261117/CAM-SALIDA/20261117T010754_845446Z_7d11d36aea9a_orig.jpg"))
        frame_yellow_bus = cv2.imread(str(EVIDENCE_DIR / "20261116/CAM-SALIDA/20261116T172150_234602Z_a749dee8704c_orig.jpg"))
        frame_blue_bus = cv2.imread(str(EVIDENCE_DIR / "20261101/CAM-ENTRADA/20261101T191753_054288Z_1ffcf7df4fd0_orig.jpg"))

        inmem_repo = _InMemoryDetRepo()
        ev_storage = LocalDiskEvidenceStorage(base_directory=tmp_path)
        settings = VisionEngineSettings(
            vehicle_confidence_threshold=0.70,
            evidence_directory=tmp_path,
            save_annotated_evidence=False,
        )
        # Stub detector determinista opcional no necesario; usamos YoloVehicleDetector real
        coord = VisionEngineCoordinator(
            topology_validator=_MockTopoValidator(),
            settings=settings,
            detector=detector,
            detection_repository=inmem_repo,
            evidence_storage=ev_storage,
            sources={
                "CAM-ENTRADA": _StubFrameSource([frame_multi_3] * 10),
                "CAM-SALIDA": _StubFrameSource([frame_yellow_bus] * 4 + [frame_blue_bus] * 4),
            },
            color_classifier=prod_color,
        )
        coord.initialize()

        env_multi = coord.process_camera_step("CAM-ENTRADA", persist_as_new_event=True)
        coord_findings["multi_vehicle_coordinator_test"] = {
            "detections_in_roi_count": len(env_multi.detections_in_roi) if env_multi else 0,
            "primary_bbox": (
                [env_multi.detections_in_roi[0].bbox.x_min, env_multi.detections_in_roi[0].bbox.y_min,
                 env_multi.detections_in_roi[0].bbox.x_max, env_multi.detections_in_roi[0].bbox.y_max]
                if env_multi and env_multi.detections_in_roi else None
            ),
            "vision_result_color_pred": env_multi.vision_result.vehicle_color_pred if env_multi else None,
            "vision_result_color_conf": env_multi.vision_result.vehicle_color_confidence if env_multi else None,
            "envelope_color_status": (
                env_multi.vehicle_color_result.status.value
                if env_multi and env_multi.vehicle_color_result else None
            ),
            "secondary_vehicles_color_dropped": (len(env_multi.detections_in_roi) > 1) if env_multi else False,
            "note": "VisionEngineCoordinator clasifica unicamente detections_in_roi[0]; colores de vehiculos secundarios [1..N] no se evaluan ni persisten.",
        }

        # Interleaved dual-camera concurrency stress (8 steps CAM-ENTRADA [3-veh] vs 8 steps CAM-SALIDA [4 yellow -> 4 blue])
        ent_preds: List[Optional[str]] = []
        sal_yellow_preds: List[Optional[str]] = []
        sal_blue_preds: List[Optional[str]] = []

        def run_ent():
            for _ in range(8):
                e = coord.process_camera_step("CAM-ENTRADA", persist_as_new_event=False)
                ent_preds.append(e.vision_result.vehicle_color_pred if e else None)

        def run_sal():
            for i in range(8):
                e = coord.process_camera_step("CAM-SALIDA", persist_as_new_event=False)
                c = e.vision_result.vehicle_color_pred if e else None
                if i < 4:
                    sal_yellow_preds.append(c)
                else:
                    sal_blue_preds.append(c)

        t1 = threading.Thread(target=run_ent)
        t2 = threading.Thread(target=run_sal)
        t1.start(); t2.start()
        t1.join(); t2.join()

        coord_findings["dual_camera_isolation_test"] = {
            "cam_entrada_multi_primary_preds": ent_preds,
            "cam_salida_yellow_bus_preds": sal_yellow_preds,
            "cam_salida_blue_bus_preds": sal_blue_preds,
            "zero_cross_camera_contamination": (
                all(p != "YELLOW" and p != "BLUE" for p in ent_preds)
                and all(p == "YELLOW" for p in sal_yellow_preds)
                and all(p == "BLUE" for p in sal_blue_preds)
            ),
            "coordinator_metrics_color_block": coord.get_operational_metrics().get("color_classifier"),
        }
        coord.shutdown()

    # D4. Abstenciones UNKNOWN en degradaciones extremas
    unknown_checks = []
    # Low-illumination dark frame
    dark_img = np.full((300, 300, 3), (5, 5, 6), dtype=np.uint8)
    u_dark = prod_color.classify(dark_img, BoundingBox(40, 40, 260, 260), "car", 0.90)
    # Overexposed glare frame
    glare_img = np.full((300, 300, 3), (255, 255, 255), dtype=np.uint8)
    u_glare = prod_color.classify(glare_img, BoundingBox(40, 40, 260, 260), "car", 0.90)
    # Tiny bbox (<28px)
    tiny_img = np.full((300, 300, 3), (0, 0, 220), dtype=np.uint8)
    u_tiny = prod_color.classify(tiny_img, BoundingBox(10, 10, 30, 30), "car", 0.90)
    # Low det confidence (<0.25)
    u_lowdet = prod_color.classify(tiny_img, BoundingBox(40, 40, 260, 260), "car", 0.10)
    for tag, r in [("dark", u_dark), ("glare", u_glare), ("tiny_bbox", u_tiny), ("low_det_conf", u_lowdet)]:
        unknown_checks.append({
            "scenario": tag,
            "pred": r.predominant_color.value,
            "conf": round(r.confidence, 4),
            "status": r.status.value,
            "is_unknown": r.predominant_color == ProdVehicleColor.UNKNOWN,
        })

    results["all_multi_vehicle_crops_isolated"] = all_crop_isolated
    results["multi_vehicle_crop_isolation"] = crop_isolation_cases
    results["synthetic_overlap_contamination"] = overlap_tests
    results["coordinator_association_and_dual_camera"] = coord_findings
    results["unknown_abstention_checks"] = unknown_checks
    return results


# ---------------------------------------------------------------------------
# Clasificacion de visual_notes del inventario historico (279 unicas)
# ---------------------------------------------------------------------------

def infer_hist_ground_truth(rec: Dict[str, Any]) -> Dict[str, Any]:
    cv = rec.get("confirmed_visual_classification") or {}
    cats = cv.get("confirmed_categories") or []
    notes = (cv.get("visual_notes") or "").lower()
    orient = cv.get("primary_orientation") or "UNKNOWN"
    lighting = rec.get("lighting_condition") or "NORMAL"
    has_contraluz = "Contraluz" in cats or "contraluz" in notes or "luz solar intensa" in notes or "luz intensa" in notes

    # Determinacion de clase primaria esperada (sin inventar gt donde es collage de pantalla)
    if rec.get("evidence_type") == "SCREEN_RECAPTURE" and orient == "MULTI_ORIENTATION_SCREEN":
        primary_type = "MULTI_SCREEN"
    elif "camión" in notes:
        primary_type = "truck"
    elif notes.startswith("autobús") or "bus urbano" in notes or "semilla sintética bus.jpg" in notes:
        primary_type = "bus"
    else:
        primary_type = "car"

    # Subtipo especial: Autobus escolar amarillo frontal directo 0 grados vs oblicuo/lateral
    is_school_bus_frontal = ("autobús escolar" in notes and "directamente de frente" in notes)
    is_school_bus_any = ("autobús escolar" in notes)
    is_partial = "Oclusión parcial" in cats or "parcial" in notes or "recortado" in notes
    is_small = "Vehículo pequeño o lejano" in cats or "pequeñ" in notes or "lejan" in notes

    # Color GT visualmente verificable en inventario historico
    # OJO: solo asignamos GT donde el sujeto primario descrito en visual_notes es univoco en color.
    gt_color = None
    if primary_type != "MULTI_SCREEN":
        if notes.startswith("dos automóviles convertibles"):
            gt_color = None  # Dual ambiguo (rosa o cian pueden ganar)
        elif "auto deportivo rojo" in notes or notes.startswith("auto rojo"):
            gt_color = "RED"
        elif "auto azul oscuro" in notes or "autobús urbano azul" in notes or "autobús azul" in notes:
            gt_color = "BLUE"
        elif "autobús escolar amarillo" in notes:
            gt_color = "YELLOW"
        elif "auto a escala gris" in notes:
            gt_color = "GRAY"
        elif "convertible rosa" in notes:
            gt_color = "OTHER"
        elif "convertible cian" in notes:
            gt_color = None  # Cian/turquesa es frontera BLUE/GREEN; evaluado por separado

    return {
        "primary_type": primary_type,
        "orientation": orient,
        "lighting_bucket": "LOW_LIGHT" if lighting == "LOW_LIGHT" else ("BACKLIGHT_GLARE" if has_contraluz else "NORMAL_DAY"),
        "is_school_bus_frontal": is_school_bus_frontal,
        "is_school_bus_any": is_school_bus_any,
        "is_partial": is_partial,
        "is_small": is_small,
        "gt_color": gt_color,
    }


def size_bucket(rel_area_pct: float) -> str:
    if rel_area_pct < 2.0:
        return "<2% (Lejano/Pequeno)"
    if rel_area_pct < 10.0:
        return "2-10% (Intermedio-Lejano)"
    if rel_area_pct < 25.0:
        return "10-25% (Intermedio)"
    return ">25% (Cercano)"


def confusion_and_metrics(pairs: List[Tuple[str, str]], labels: List[str]) -> Dict[str, Any]:
    cm: Dict[str, Dict[str, int]] = {g: {p: 0 for p in labels} for g in labels}
    for g, p in pairs:
        if g in cm and p in cm[g]:
            cm[g][p] += 1
    total = len(pairs)
    correct = sum(1 for g, p in pairs if g == p)
    per_class = {}
    for c in labels:
        tp = cm[c][c]
        fp = sum(cm[g][c] for g in labels if g != c)
        fn = sum(cm[c][p] for p in labels if p != c)
        supp = tp + fn
        prec = (tp / (tp + fp)) if (tp + fp) > 0 else None
        rec = (tp / supp) if supp > 0 else None
        f1 = (2 * prec * rec / (prec + rec)) if (prec is not None and rec is not None and (prec + rec) > 0) else None
        per_class[c] = {
            "support": supp,
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(prec, 4) if prec is not None else None,
            "recall": round(rec, 4) if rec is not None else None,
            "f1": round(f1, 4) if f1 is not None else None,
        }
    return {
        "total": total,
        "correct": correct,
        "accuracy_pct": round(100.0 * correct / total, 2) if total else None,
        "labels": labels,
        "confusion_matrix": cm,
        "per_class": per_class,
    }


# ---------------------------------------------------------------------------
# FASE B & FASE C — Corpus Historico (279 unicas) + Benchmark 05B (185) + Sintetico 12 Clases
# ---------------------------------------------------------------------------

def run_historical_and_color_eval(
    detector: YoloVehicleDetector,
    prod_color: ProdColorClassifier,
    bench_color: BenchColorClassifier,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    print("[FASE B/C] Evaluando 279 imagenes unicas del corpus historico...")
    inv = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    uniq: Dict[str, Dict[str, Any]] = {}
    for r in inv["items"]:
        uniq.setdefault(r["sha256"], r)
    records = list(uniq.values())

    # Warmup GPU detector (3 pasadas)
    dummy_img = cv2.imread(str(EVIDENCE_DIR / records[0]["relative_path"]))
    for _ in range(3):
        detector.detect(dummy_img, camera_code="WARMUP")

    latencies: List[float] = []
    by_orientation: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_class_gt: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_lighting: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_blur: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_size_070: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    class_pairs_070: List[Tuple[str, str]] = []
    class_pairs_025: List[Tuple[str, str]] = []
    school_bus_frontal_rows: List[Dict[str, Any]] = []
    partial_rows: List[Dict[str, Any]] = []
    small_rows: List[Dict[str, Any]] = []

    color_gt_pairs_prod: List[Tuple[str, str]] = []
    color_gt_pairs_bench: List[Tuple[str, str]] = []
    color_hist_details: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        fpath = EVIDENCE_DIR / rec["relative_path"]
        img = cv2.imread(str(fpath))
        h, w = img.shape[:2]
        frame_area = float(h * w)
        roi = default_roi_for_frame(w, h)

        t0 = time.perf_counter()
        raw_preds = detector.detect(img, camera_code="AUDIT_HIST")
        dt_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(dt_ms)

        in_roi_070, _ = filter_detections_by_roi(raw_preds, roi, min_confidence=0.70)
        in_roi_025, _ = filter_detections_by_roi(raw_preds, roi, min_confidence=0.25)

        gt = infer_hist_ground_truth(rec)
        top_070 = in_roi_070[0] if in_roi_070 else None
        top_025 = in_roi_025[0] if in_roi_025 else None

        rel_area_070 = (top_070.bbox.area / frame_area * 100.0) if top_070 else 0.0
        rel_area_025 = (top_025.bbox.area / frame_area * 100.0) if top_025 else 0.0

        row_summary = {
            "sample_id": rec["sample_id"],
            "primary_gt": gt["primary_type"],
            "orientation": gt["orientation"],
            "lighting": gt["lighting_bucket"],
            "blur": rec.get("blur_grade"),
            "det_070": top_070 is not None,
            "pred_lbl_070": top_070.raw_label if top_070 else "NONE",
            "pred_conf_070": round(top_070.confidence, 4) if top_070 else None,
            "det_025": top_025 is not None,
            "pred_lbl_025": top_025.raw_label if top_025 else "NONE",
            "pred_conf_025": round(top_025.confidence, 4) if top_025 else None,
            "rel_area_070": round(rel_area_070, 2),
            "rel_area_025": round(rel_area_025, 2),
            "lat_ms": round(dt_ms, 2),
        }

        by_orientation[gt["orientation"]].append(row_summary)
        by_class_gt[gt["primary_type"]].append(row_summary)
        by_lighting[gt["lighting_bucket"]].append(row_summary)
        by_blur[str(rec.get("blur_grade"))].append(row_summary)

        if top_070:
            by_size_070[size_bucket(rel_area_070)].append(row_summary)
        else:
            by_size_070["MISSED_AT_070"].append(row_summary)

        if gt["is_partial"]:
            partial_rows.append(row_summary)
        if gt["is_small"]:
            small_rows.append(row_summary)
        if gt["is_school_bus_frontal"]:
            school_bus_frontal_rows.append(row_summary)

        if gt["primary_type"] in ("car", "bus"):
            class_pairs_070.append((gt["primary_type"], top_070.raw_label if top_070 else "NONE"))
            class_pairs_025.append((gt["primary_type"], top_025.raw_label if top_025 else "NONE"))

        # Color sobre mejor deteccion ROI >=0.25 cuando hay gt_color univoco
        if gt["gt_color"] is not None and top_025 is not None:
            pc = prod_color.classify(img, top_025.bbox, vehicle_class=top_025.raw_label, detection_confidence=top_025.confidence)
            bc = bench_color.classify(img, top_025.bbox, detected_class=top_025.raw_label, detection_confidence=top_025.confidence)
            color_gt_pairs_prod.append((gt["gt_color"], pc.predominant_color.value))
            color_gt_pairs_bench.append((gt["gt_color"], bc.predominant_color.value))
            color_hist_details.append({
                "sample_id": rec["sample_id"],
                "gt_color": gt["gt_color"],
                "lighting": gt["lighting_bucket"],
                "blur": rec.get("blur_grade"),
                "is_partial": gt["is_partial"],
                "det_conf": round(top_025.confidence, 4),
                "prod_pred": pc.predominant_color.value,
                "prod_conf": round(pc.confidence, 4),
                "prod_status": pc.status.value,
                "bench_pred": bc.predominant_color.value,
                "bench_conf": round(bc.confidence, 4),
                "bench_status": bc.status.value,
            })

        if (idx + 1) % 60 == 0:
            time.sleep(0.05)  # Cortesia GPU para servicio en produccion

    def summarize_group(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        n = len(rows)
        if not n:
            return {"total": 0}
        d070 = [r for r in rows if r["det_070"]]
        d025 = [r for r in rows if r["det_025"]]
        lbl070 = Counter(r["pred_lbl_070"] for r in rows)
        lbl025 = Counter(r["pred_lbl_025"] for r in rows)
        return {
            "total": n,
            "detected_roi_070": len(d070),
            "missed_roi_070": n - len(d070),
            "presence_recall_070_pct": round(100.0 * len(d070) / n, 2),
            "detected_roi_025": len(d025),
            "presence_recall_025_pct": round(100.0 * len(d025) / n, 2),
            "avg_conf_070": round(statistics.mean(r["pred_conf_070"] for r in d070), 4) if d070 else None,
            "avg_conf_025": round(statistics.mean(r["pred_conf_025"] for r in d025), 4) if d025 else None,
            "avg_latency_ms": round(statistics.mean(r["lat_ms"] for r in rows), 2),
            "pred_labels_070": dict(lbl070),
            "pred_labels_025": dict(lbl025),
        }

    det_labels = ["car", "bus", "truck", "motorcycle", "NONE"]
    cm_070 = confusion_and_metrics(class_pairs_070, det_labels)
    cm_025 = confusion_and_metrics(class_pairs_025, det_labels)

    fase_b_hist = {
        "total_unique_images": len(records),
        "ground_truth_scope_note": (
            "Evaluacion basada en ground truth visual nivel-imagen (confirmed_visual_classification). "
            "No existen anotaciones manuales de bounding-box en pixeles [x1,y1,x2,y2] (manifest_v1=UNANNOTATED, "
            "vigia_bench_v1=PENDING_HUMAN_REVIEW), por lo cual AP por clase, mAP@0.5 y mAP@0.5:0.95 no son calculables."
        ),
        "overall_presence": summarize_group([r for grp in by_orientation.values() for r in grp]),
        "latency_stats_ms": pct_stats(latencies),
        "by_orientation": {k: summarize_group(v) for k, v in sorted(by_orientation.items())},
        "by_primary_gt_class": {k: summarize_group(v) for k, v in sorted(by_class_gt.items())},
        "by_lighting": {k: summarize_group(v) for k, v in sorted(by_lighting.items())},
        "by_blur": {k: summarize_group(v) for k, v in sorted(by_blur.items())},
        "by_apparent_bbox_size_070_approx": {k: summarize_group(v) for k, v in sorted(by_size_070.items())},
        "special_subsets": {
            "school_bus_type_c_frontal_0deg": summarize_group(school_bus_frontal_rows),
            "partial_occlusion": summarize_group(partial_rows),
            "small_or_distant": summarize_group(small_rows),
        },
        "class_confusion_single_primary_070": cm_070,
        "class_confusion_single_primary_025": cm_025,
    }

    # --- FASE C1: Suite Sintetica Calibrada (12 categorias x 3 variantes = 36 muestras) ---
    print("[FASE C] Evaluando suite sintetica de 12 categorias (36 casos)...")
    # Base BGR para cada categoria vehicular (BGR, esperado_12)
    synth_specs = [
        ("WHITE", [(238, 240, 242), (218, 222, 226), (250, 250, 248)]),
        ("BLACK", [(18, 18, 20), (30, 32, 34), (12, 12, 14)]),
        ("GRAY", [(105, 108, 110), (85, 88, 92), (125, 124, 122)]),
        ("SILVER", [(192, 195, 200), (175, 180, 185), (205, 210, 214)]),
        ("RED", [(25, 25, 210), (35, 30, 175), (45, 38, 235)]),
        ("BLUE", [(205, 70, 25), (160, 50, 20), (225, 130, 45)]),
        ("GREEN", [(40, 170, 40), (35, 125, 35), (85, 190, 55)]),
        ("YELLOW", [(20, 215, 235), (25, 185, 215), (40, 235, 245)]),
        ("BROWN", [(35, 70, 115), (45, 85, 130), (25, 50, 88)]),
        ("ORANGE", [(20, 115, 235), (25, 135, 245), (30, 95, 205)]),
        ("OTHER", [(180, 95, 235), (210, 65, 165), (150, 80, 215)]),  # Pink / Magenta / Purple
    ]
    synth_pairs_prod: List[Tuple[str, str]] = []
    synth_pairs_bench: List[Tuple[str, str]] = []
    synth_details: List[Dict[str, Any]] = []
    for gt_c, bgr_list in synth_specs:
        for var_i, bgr in enumerate(bgr_list):
            frame = _build_synthetic_vehicle_frame(400, 300, [((60, 40, 340, 260), bgr)], bg_bgr=(60, 65, 62))
            bbox = BoundingBox(60, 40, 340, 260)
            pc = prod_color.classify(frame, bbox, vehicle_class="car", detection_confidence=0.95)
            bc = bench_color.classify(frame, bbox, detected_class="car", detection_confidence=0.95)
            synth_pairs_prod.append((gt_c, pc.predominant_color.value))
            synth_pairs_bench.append((gt_c, bc.predominant_color.value))
            synth_details.append({
                "variant": f"{gt_c}_v{var_i}", "bgr": list(bgr), "gt_color": gt_c,
                "prod_pred": pc.predominant_color.value, "prod_conf": round(pc.confidence, 4), "prod_status": pc.status.value,
                "bench_pred": bc.predominant_color.value, "bench_conf": round(bc.confidence, 4), "bench_status": bc.status.value,
            })
    # Agregar 3 muestras UNKNOWN sinteticas (oscuro extremo, deslumbramiento, bbox insuficiente)
    unknown_frames = [
        ("UNKNOWN_dark", np.full((300, 400, 3), (6, 6, 7), dtype=np.uint8), BoundingBox(60, 40, 340, 260), 0.92),
        ("UNKNOWN_glare", np.full((300, 400, 3), (254, 255, 254), dtype=np.uint8), BoundingBox(60, 40, 340, 260), 0.92),
        ("UNKNOWN_tiny", np.full((300, 400, 3), (20, 20, 220), dtype=np.uint8), BoundingBox(100, 100, 120, 120), 0.92),
    ]
    for tag, frame, bbox, dc in unknown_frames:
        pc = prod_color.classify(frame, bbox, vehicle_class="car", detection_confidence=dc)
        bc = bench_color.classify(frame, bbox, detected_class="car", detection_confidence=dc)
        synth_pairs_prod.append(("UNKNOWN", pc.predominant_color.value))
        synth_pairs_bench.append(("UNKNOWN", bc.predominant_color.value))
        synth_details.append({
            "variant": tag, "bgr": None, "gt_color": "UNKNOWN",
            "prod_pred": pc.predominant_color.value, "prod_conf": round(pc.confidence, 4), "prod_status": pc.status.value,
            "bench_pred": bc.predominant_color.value, "bench_conf": round(bc.confidence, 4), "bench_status": bc.status.value,
        })

    # --- FASE C2: Comparacion exacta contra los 185 registros GT de VISION-05B ---
    print("[FASE C] Re-evaluando los 185 registros GT de VISION-05B con el clasificador de PRODUCCION...")
    bench_05b = json.loads(BENCH_05B_PATH.read_text(encoding="utf-8"))
    # Reconstruir bboxes usando YOLO26x sobre la imagen del sample_id
    inv_by_sid = {r["sample_id"]: r for r in inv["items"]}
    comp_05b_pairs_prod: List[Tuple[str, str]] = []
    comp_05b_pairs_bench_saved: List[Tuple[str, str]] = []
    comp_05b_clean_prod: List[Tuple[str, str]] = []  # Excluyendo collages de pantalla EV-0295..303 / 449..456
    comp_05b_clean_bench: List[Tuple[str, str]] = []
    prod_status_05b = Counter()
    prod_lat_05b: List[float] = []
    by_light_05b: Dict[str, List[Tuple[str, str]]] = defaultdict(list)

    for rec in bench_05b["sample_roi_records"]:
        gt_c = rec.get("ground_truth_color")
        if not gt_c:
            continue
        inv_rec = inv_by_sid.get(rec["sample_id"])
        if not inv_rec:
            continue
        fpath = EVIDENCE_DIR / rec["relative_path"]
        img = cv2.imread(str(fpath))
        h, w = img.shape[:2]
        roi = default_roi_for_frame(w, h)
        preds = detector.detect(img, camera_code="AUDIT_05B")
        in_roi, _ = filter_detections_by_roi(preds, roi, min_confidence=0.25)
        if not in_roi:
            continue
        top = in_roi[0]
        t0 = time.perf_counter()
        pc = prod_color.classify(img, top.bbox, vehicle_class=top.raw_label, detection_confidence=top.confidence)
        prod_lat_05b.append((time.perf_counter() - t0) * 1000.0)
        prod_status_05b[pc.status.value] += 1

        comp_05b_pairs_prod.append((gt_c, pc.predominant_color.value))
        comp_05b_pairs_bench_saved.append((gt_c, rec["predicted_color"]))
        by_light_05b[rec.get("lighting_condition", "NORMAL")].append((gt_c, pc.predominant_color.value))

        is_screen = (inv_rec.get("evidence_type") == "SCREEN_RECAPTURE")
        if not is_screen:
            comp_05b_clean_prod.append((gt_c, pc.predominant_color.value))
            comp_05b_clean_bench.append((gt_c, rec["predicted_color"]))

    def color_accuracy_metrics(pairs: List[Tuple[str, str]]) -> Dict[str, Any]:
        total = len(pairs)
        unk = sum(1 for _, p in pairs if p == "UNKNOWN")
        non_unk_pairs = [(g, p) for g, p in pairs if p != "UNKNOWN"]
        abs_correct = sum(1 for g, p in pairs if g == p)
        eff_correct = sum(1 for g, p in non_unk_pairs if g == p)
        cm = confusion_and_metrics(pairs, ALL_12_COLORS)
        return {
            "total": total,
            "unknown_count": unk,
            "unknown_rate_pct": round(100.0 * unk / total, 2) if total else None,
            "absolute_concordance_correct": abs_correct,
            "absolute_concordance_pct": round(100.0 * abs_correct / total, 2) if total else None,
            "accuracy_excluding_unknown_correct": eff_correct,
            "accuracy_excluding_unknown_pct": round(100.0 * eff_correct / len(non_unk_pairs), 2) if non_unk_pairs else None,
            "matrix_and_per_class": cm,
        }

    # --- FASE C4: Sensibilidad a degradaciones controladas (Luminancia y Recorte Parcial) en frames reales nitidos ---
    print("[FASE C] Ejecutando analisis de sensibilidad a iluminacion y oclusion parcial...")
    sensitivity_cases = [
        ("yellow_bus", EVIDENCE_DIR / "20261116/CAM-SALIDA/20261116T172150_234602Z_a749dee8704c_orig.jpg", "YELLOW"),
        ("blue_bus", EVIDENCE_DIR / "20261101/CAM-ENTRADA/20261101T191753_054288Z_1ffcf7df4fd0_orig.jpg", "BLUE"),
        ("red_toy_cam_salida", EVIDENCE_DIR / "20261117/CAM-SALIDA/20261117T010754_845446Z_7d11d36aea9a_orig.jpg", "RED"),
        ("dark_blue_corsa", EVIDENCE_DIR / "20261106/CAM-ENTRADA/20261106T163401_494745Z_199563b21612_orig.jpg", "BLUE"),
    ]
    light_sens_results = []
    crop_sens_results = []
    for cname, fpath, expected_c in sensitivity_cases:
        img = cv2.imread(str(fpath))
        h, w = img.shape[:2]
        roi = default_roi_for_frame(w, h)
        preds = detector.detect(img, camera_code="SENS")
        in_roi, _ = filter_detections_by_roi(preds, roi, min_confidence=0.25)
        if not in_roi:
            continue
        # Para 20261117 multi seleccionamos el carrito rojo si expected_c=='RED'
        cand = in_roi[0]
        if cname == "red_toy_cam_salida":
            for d in in_roi:
                if d.bbox.width < 120:
                    cand = d
                    break

        for scale in (0.25, 0.50, 0.75, 1.0, 1.35):
            scaled = np.clip(img.astype(np.float32) * scale, 0, 255).astype(np.uint8)
            pc = prod_color.classify(scaled, cand.bbox, cand.raw_label, cand.confidence)
            light_sens_results.append({
                "case": cname, "expected": expected_c, "brightness_scale": scale,
                "pred": pc.predominant_color.value, "conf": round(pc.confidence, 4), "status": pc.status.value,
            })

        b = cand.bbox
        bw, bh = b.width, b.height
        partials = {
            "full": b,
            "left_50pct": BoundingBox(b.x_min, b.y_min, b.x_min + max(30, bw // 2), b.y_max),
            "right_50pct": BoundingBox(b.x_max - max(30, bw // 2), b.y_min, b.x_max, b.y_max),
            "top_50pct": BoundingBox(b.x_min, b.y_min, b.x_max, b.y_min + max(30, bh // 2)),
            "bottom_50pct": BoundingBox(b.x_min, b.y_max - max(30, bh // 2), b.x_max, b.y_max),
        }
        for pname, pb in partials.items():
            pc = prod_color.classify(img, pb, cand.raw_label, cand.confidence)
            crop_sens_results.append({
                "case": cname, "expected": expected_c, "crop_mode": pname,
                "pred": pc.predominant_color.value, "conf": round(pc.confidence, 4), "status": pc.status.value,
            })

    fase_c = {
        "architecture_audit_note": (
            "VisionEngineCoordinator usa VIGIA_Vision.detection.color_classifier.VehicleColorClassifier (Produccion), "
            "mientras que el benchmark VISION-05B evaluo VIGIA_Vision.classification.color_classifier.VehicleColorClassifier."
        ),
        "synthetic_12_category_suite_36_cases": {
            "production_classifier": color_accuracy_metrics(synth_pairs_prod),
            "vision05b_classifier": color_accuracy_metrics(synth_pairs_bench),
            "sample_details": synth_details,
        },
        "vision05b_185_gt_comparison": {
            "production_classifier_all_185": color_accuracy_metrics(comp_05b_pairs_prod),
            "vision05b_baseline_saved_185": color_accuracy_metrics(comp_05b_pairs_bench_saved),
            "production_excluding_screen_collages": color_accuracy_metrics(comp_05b_clean_prod),
            "vision05b_excluding_screen_collages": color_accuracy_metrics(comp_05b_clean_bench),
            "production_by_lighting": {k: color_accuracy_metrics(v) for k, v in by_light_05b.items()},
            "production_status_counts": dict(prod_status_05b),
            "production_latency_ms": pct_stats(prod_lat_05b),
        },
        "historical_unique_unambiguous_color_gt": {
            "production_classifier": color_accuracy_metrics(color_gt_pairs_prod),
            "vision05b_classifier": color_accuracy_metrics(color_gt_pairs_bench),
        },
        "sensitivity_brightness": light_sens_results,
        "sensitivity_partial_crop": crop_sens_results,
    }
    return fase_b_hist, fase_c


# ---------------------------------------------------------------------------
# FASE B/C/G — Capturas Fisicas 20261117 (No Anotadas + Rafagas Temporales + LPR Optico)
# ---------------------------------------------------------------------------

def _parse_ts_from_filename(fname: str) -> Optional[float]:
    # Format: 20261117T000625_139777Z_...
    try:
        stem = fname.split("_orig")[0]
        parts = stem.split("_")
        dt_part = parts[0]  # 20261117T000625
        us_part = parts[1].rstrip("Z")
        dt = datetime.strptime(f"{dt_part}.{us_part}", "%Y%m%dT%H%M%S.%f").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def run_20261117_and_lpr_eval(
    detector: YoloVehicleDetector,
    prod_color: ProdColorClassifier,
    bench_color: BenchColorClassifier,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    print("[FASE B/C/G] Evaluando capturas fisicas reales 20261117 (CAM-ENTRADA, CAM-SALIDA, CAM-03)...")
    dir17 = EVIDENCE_DIR / "20261117"

    ent_all = sorted(glob.glob(str(dir17 / "CAM-ENTRADA" / "*_orig.jpg")))
    sal_all = sorted(glob.glob(str(dir17 / "CAM-SALIDA" / "*_orig.jpg")))
    cam03_all = sorted(glob.glob(str(dir17 / "CAM-03" / "*_orig.jpg")))

    # Cadencias temporales sobre TODOS los archivos 20261117 en disco
    cadence: Dict[str, Any] = {}
    for cam_name, files in [("CAM-ENTRADA", ent_all), ("CAM-SALIDA", sal_all), ("CAM-03", cam03_all)]:
        ts = [_parse_ts_from_filename(os.path.basename(f)) for f in files]
        ts = [t for t in ts if t is not None]
        deltas = [ts[i + 1] - ts[i] for i in range(len(ts) - 1) if ts[i + 1] >= ts[i]]
        cadence[cam_name] = {
            "total_orig_files": len(files),
            "delta_t_sec_stats": pct_stats(deltas),
            "effective_saved_detection_rate_hz": round(1.0 / statistics.median(deltas), 3) if deltas and statistics.median(deltas) > 0 else None,
        }

    # Para CAM-ENTRADA (2,093+ frames): muestreo estratificado determinista (~360 frames distribuidos uniformemente + 3 rafagas consecutivas)
    stride = max(1, len(ent_all) // 300)
    ent_eval_set = list(dict.fromkeys(ent_all[::stride] + ent_all[20:45] + ent_all[1500:1525] + ent_all[-35:]))

    cam_eval: Dict[str, Any] = {}
    lpr_stats: Dict[str, Any] = {}
    temporal_bursts_raw: List[Tuple[str, str, List[str]]] = [
        ("20261117_CAM-ENTRADA_burst_inicio", "CAM-ENTRADA", ent_all[15:35]),
        ("20261117_CAM-ENTRADA_burst_medio", "CAM-ENTRADA", ent_all[1000:1020]),
        ("20261117_CAM-ENTRADA_burst_ocluido_final", "CAM-ENTRADA", ent_all[-25:-5]),
        ("20261117_CAM-SALIDA_burst_nitido_multi", "CAM-SALIDA", sal_all[-25:-5]),
        ("20261117_CAM-SALIDA_burst_inicio", "CAM-SALIDA", sal_all[:20]),
    ]

    for cam_name, file_list, total_on_disk in [
        ("CAM-ENTRADA", ent_eval_set, len(ent_all)),
        ("CAM-SALIDA", sal_all, len(sal_all)),
        ("CAM-03", cam03_all, len(cam03_all)),
    ]:
        lat_ms_list: List[float] = []
        raw_labels_070 = Counter()
        raw_labels_025 = Counter()
        prod_colors_070 = Counter()
        bench_colors_070 = Counter()
        det_counts_070 = Counter()
        bbox_widths: List[float] = []
        bbox_heights: List[float] = []
        bbox_rel_areas: List[float] = []
        est_plate_widths_px: List[float] = []
        est_plate_heights_px: List[float] = []
        lap_list: List[float] = []
        lum_list: List[float] = []
        glare_list: List[float] = []
        size_kb_list: List[float] = []
        res_counts = Counter()
        no_det_070 = 0
        multi_det_070 = 0

        for idx, fp in enumerate(file_list):
            img = cv2.imread(fp)
            if img is None:
                continue
            h, w = img.shape[:2]
            res_counts[f"{w}x{h}"] += 1
            size_kb_list.append(os.path.getsize(fp) / 1024.0)
            opt = compute_image_optical_metrics(img)
            lap_list.append(opt["laplacian_var"])
            lum_list.append(opt["luminance_mean"])
            glare_list.append(opt["glare_pct"])

            roi = default_roi_for_frame(w, h)
            t0 = time.perf_counter()
            preds = detector.detect(img, camera_code=cam_name)
            lat_ms_list.append((time.perf_counter() - t0) * 1000.0)

            in070, _ = filter_detections_by_roi(preds, roi, min_confidence=0.70)
            in025, _ = filter_detections_by_roi(preds, roi, min_confidence=0.25)

            det_counts_070[len(in070)] += 1
            if not in070:
                no_det_070 += 1
            if len(in070) >= 2:
                multi_det_070 += 1

            for d in in025:
                raw_labels_025[d.raw_label] += 1
            for d in in070:
                raw_labels_070[d.raw_label] += 1
                bbox_widths.append(float(d.bbox.width))
                bbox_heights.append(float(d.bbox.height))
                bbox_rel_areas.append(float(d.bbox.area / (w * h) * 100.0))
                # Aproximacion geometrica de placa frontal/trasera (~16.7% del ancho vehiculo, ~8% alto)
                est_plate_widths_px.append(float(d.bbox.width * 0.167))
                est_plate_heights_px.append(float(d.bbox.height * 0.08))

            if in070:
                primary = in070[0]
                pc = prod_color.classify(img, primary.bbox, primary.raw_label, primary.confidence)
                bc = bench_color.classify(img, primary.bbox, primary.raw_label, primary.confidence)
                prod_colors_070[pc.predominant_color.value] += 1
                bench_colors_070[bc.predominant_color.value] += 1

            if (idx + 1) % 60 == 0:
                time.sleep(0.04)

        n_eval = len(file_list)
        plate_ge_80 = sum(1 for pw in est_plate_widths_px if pw >= 80.0)
        plate_ge_60 = sum(1 for pw in est_plate_widths_px if pw >= 60.0)
        blur_severe = sum(1 for l in lap_list if l < 50.0)
        blur_mod = sum(1 for l in lap_list if 50.0 <= l < 120.0)
        blur_sharp = sum(1 for l in lap_list if l >= 120.0)

        cam_eval[cam_name] = {
            "total_files_on_disk": total_on_disk,
            "evaluated_files": n_eval,
            "resolutions": dict(res_counts),
            "operational_detection_rate_roi_070_pct": round(100.0 * (n_eval - no_det_070) / n_eval, 2) if n_eval else None,
            "multi_vehicle_frames_roi_070": multi_det_070,
            "roi_det_count_histogram_070": dict(sorted(det_counts_070.items())),
            "raw_labels_roi_070": dict(raw_labels_070),
            "raw_labels_roi_025": dict(raw_labels_025),
            "prod_primary_colors_070": dict(prod_colors_070),
            "bench_primary_colors_070": dict(bench_colors_070),
            "inference_latency_ms": pct_stats(lat_ms_list),
            "note": "Tasa operativa en capturas fisicas recientes sin anotacion bbox formal; no representa Precision/Recall.",
        }

        lpr_stats[cam_name] = {
            "resolutions": dict(res_counts),
            "file_size_kb": pct_stats(size_kb_list),
            "sharpness_laplacian": pct_stats(lap_list),
            "sharpness_distribution": {"severe_blur_<50": blur_severe, "moderate_50_120": blur_mod, "sharp_>=120": blur_sharp},
            "luminance_mean": pct_stats(lum_list),
            "glare_pct": pct_stats(glare_list),
            "detected_bbox_width_px": pct_stats(bbox_widths),
            "detected_bbox_height_px": pct_stats(bbox_heights),
            "detected_bbox_rel_area_pct": pct_stats(bbox_rel_areas),
            "estimated_plate_width_px_167ratio": pct_stats(est_plate_widths_px),
            "estimated_plate_height_px_080ratio": pct_stats(est_plate_heights_px),
            "detections_with_est_plate_>=80px": plate_ge_80,
            "detections_with_est_plate_>=60px": plate_ge_60,
            "detections_total_for_lpr_est": len(est_plate_widths_px),
            "pct_est_plate_>=80px": round(100.0 * plate_ge_80 / len(est_plate_widths_px), 2) if est_plate_widths_px else None,
            "capture_cadence": cadence.get(cam_name),
        }

    # --- Estabilidad temporal en rafagas consecutivas reales ---
    burst_results = []
    for bname, cam_name, bfiles in temporal_bursts_raw:
        if len(bfiles) < 2:
            continue
        seq_prod_colors: List[str] = []
        seq_prod_confs: List[float] = []
        seq_bench_colors: List[str] = []
        seq_labels: List[str] = []
        for fp in bfiles:
            img = cv2.imread(fp)
            if img is None:
                continue
            h, w = img.shape[:2]
            roi = default_roi_for_frame(w, h)
            preds = detector.detect(img, camera_code=cam_name)
            in070, _ = filter_detections_by_roi(preds, roi, min_confidence=0.70)
            if not in070:
                seq_labels.append("NONE")
                seq_prod_colors.append("NO_DET")
                seq_bench_colors.append("NO_DET")
                continue
            primary = in070[0]
            seq_labels.append(primary.raw_label)
            pc = prod_color.classify(img, primary.bbox, primary.raw_label, primary.confidence)
            bc = bench_color.classify(img, primary.bbox, primary.raw_label, primary.confidence)
            seq_prod_colors.append(pc.predominant_color.value)
            seq_prod_confs.append(pc.confidence)
            seq_bench_colors.append(bc.predominant_color.value)

        det_prod = [c for c in seq_prod_colors if c != "NO_DET"]
        flips_prod = sum(1 for i in range(1, len(det_prod)) if det_prod[i] != det_prod[i - 1])
        det_bench = [c for c in seq_bench_colors if c != "NO_DET"]
        flips_bench = sum(1 for i in range(1, len(det_bench)) if det_bench[i] != det_bench[i - 1])
        mode_prod = Counter(det_prod).most_common(1)[0] if det_prod else (None, 0)
        mode_bench = Counter(det_bench).most_common(1)[0] if det_bench else (None, 0)

        burst_results.append({
            "burst_name": bname,
            "camera": cam_name,
            "frames": len(bfiles),
            "detected_frames": len(det_prod),
            "labels_counter": dict(Counter(seq_labels)),
            "prod_color_sequence": seq_prod_colors,
            "prod_mode_color": mode_prod[0],
            "prod_mode_consistency_pct": round(100.0 * mode_prod[1] / len(det_prod), 2) if det_prod else None,
            "prod_frame_to_frame_flips": flips_prod,
            "prod_conf_stdev": round(statistics.pstdev(seq_prod_confs), 4) if len(seq_prod_confs) >= 2 else None,
            "bench_mode_color": mode_bench[0],
            "bench_mode_consistency_pct": round(100.0 * mode_bench[1] / len(det_bench), 2) if det_bench else None,
            "bench_frame_to_frame_flips": flips_bench,
        })

    return cam_eval, {"temporal_bursts": burst_results}, lpr_stats


def main() -> None:
    t_start = time.perf_counter()
    yolo_cfg = load_yolo_config_from_env()
    color_cfg = load_color_config_from_env()

    detector = YoloVehicleDetector(config=yolo_cfg)
    prod_color = ProdColorClassifier(config=color_cfg)
    bench_color = BenchColorClassifier()

    fase_d = run_fase_d_integrity(detector, prod_color)
    fase_b_hist, fase_c = run_historical_and_color_eval(detector, prod_color, bench_color)
    fase_bc_20261117, temporal_20261117, fase_g_lpr = run_20261117_and_lpr_eval(detector, prod_color, bench_color)

    fase_c["temporal_stability_bursts_20261117"] = temporal_20261117["temporal_bursts"]

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_eval_runtime_sec": round(time.perf_counter() - t_start, 2),
        "runtime_config_verified": {
            "yolo_model": yolo_cfg.model_path,
            "device": yolo_cfg.device,
            "imgsz": yolo_cfg.imgsz,
            "quantize": yolo_cfg.quantize,
            "nms": yolo_cfg.nms,
            "deduplicate_iou": yolo_cfg.deduplicate_iou_threshold,
            "frontal_aux_enabled": yolo_cfg.frontal_aux_enabled,
            "frontal_aux_imgsz": yolo_cfg.frontal_aux_imgsz,
            "frontal_aux_trigger_conf": yolo_cfg.frontal_aux_trigger_confidence,
            "vehicle_confidence_threshold_prod": float(os.environ.get("VIGIA_VEHICLE_CONFIDENCE_THRESHOLD", "0.70")),
            "prod_color_config": {
                "min_detection_confidence": color_cfg.min_detection_confidence,
                "min_confidence_threshold": color_cfg.min_confidence_threshold,
                "min_margin_over_runner_up": color_cfg.min_margin_over_runner_up,
                "min_luminance_v": color_cfg.min_luminance_v,
                "max_glare_ratio": color_cfg.max_glare_ratio,
                "apply_illuminant_normalization": color_cfg.apply_illuminant_normalization,
            },
        },
        "fase_b_historical_279": fase_b_hist,
        "fase_b_operational_20261117_unannotated": fase_bc_20261117,
        "fase_c_color_evaluation": fase_c,
        "fase_d_association_integrity": fase_d,
        "fase_g_lpr_optical_feasibility": fase_g_lpr,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[OK] Evaluacion VISION-07B completada en {report['total_eval_runtime_sec']}s -> {OUT_JSON}")

    # Resumen compacto en stdout
    print("SYNTH 12-CAT PROD:", {k: fase_c["synthetic_12_category_suite_36_cases"]["production_classifier"][k] for k in ("total", "absolute_concordance_pct", "accuracy_excluding_unknown_pct", "unknown_rate_pct")})
    print("SYNTH 12-CAT BENCH:", {k: fase_c["synthetic_12_category_suite_36_cases"]["vision05b_classifier"][k] for k in ("total", "absolute_concordance_pct", "accuracy_excluding_unknown_pct", "unknown_rate_pct")})
    print("05B-185 PROD:", {k: fase_c["vision05b_185_gt_comparison"]["production_classifier_all_185"][k] for k in ("total", "absolute_concordance_pct", "accuracy_excluding_unknown_pct", "unknown_rate_pct")})
    print("05B-185 BENCH_SAVED:", {k: fase_c["vision05b_185_gt_comparison"]["vision05b_baseline_saved_185"][k] for k in ("total", "absolute_concordance_pct", "accuracy_excluding_unknown_pct", "unknown_rate_pct")})
    print("FASE D multi_crop_isolated:", fase_d["all_multi_vehicle_crops_isolated"], "dual_cam_clean:", fase_d["coordinator_association_and_dual_camera"]["dual_camera_isolation_test"]["zero_cross_camera_contamination"])
    print("HIST 279 presence_070:", fase_b_hist["overall_presence"]["presence_recall_070_pct"], "presence_025:", fase_b_hist["overall_presence"]["presence_recall_025_pct"])


if __name__ == "__main__":
    main()
