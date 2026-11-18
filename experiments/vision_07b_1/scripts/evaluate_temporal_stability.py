"""
evaluate_temporal_stability.py
==============================
Fase E: Investigación empírica de estabilidad temporal de color vehicular.
Evalúa ráfaga real de 20 detecciones físicas en CAM-ENTRADA (20261117).
Compara:
- Modo Raw (cuadro a cuadro sin memoria).
- Modo Suavizado Temporal Ponderado (EMA + Consenso Modal Ponderado).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from VIGIA_Vision.detection.color_classifier import (
    ColorClassificationStatus,
    VehicleColor,
    VehicleColorClassifier,
)
from VIGIA_Vision.detection.models import BoundingBox, RawVehicleDetection
from VIGIA_Vision.detection.yolo_detector import YoloDetectorConfig, YoloVehicleDetector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BURST_FRAMES = [
    "20261117/CAM-ENTRADA/20261117T000625_139777Z_e105539291d8_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000628_778997Z_7c1decf7e523_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000629_659045Z_d3a8c64cc7a7_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000630_062904Z_c86985f176f2_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000630_263802Z_968f43325a17_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000630_399716Z_8d24fd52a63d_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000631_155957Z_24aad757b50c_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000634_053918Z_dcdb888b5e94_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000700_081138Z_8ce2cde8a714_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000700_822192Z_e09860159ede_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000701_092595Z_4c2a3951fa79_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000701_429329Z_66f145214d8f_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000701_563673Z_7bb4035b2f3a_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000701_700529Z_479c62f7ff64_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000705_543767Z_f08126fb9df1_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000706_083508Z_a6f2fefa48b0_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000706_353261Z_251330ce2d2e_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000707_027403Z_3c534cab35ec_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000708_327782Z_4fb44926818b_orig.jpg",
    "20261117/CAM-ENTRADA/20261117T000709_273159Z_c66508f01c15_orig.jpg",
]


class TemporalColorConsensusTracker:
    """
    Filtro de suavizado temporal y consenso modal con decaimiento exponencial.
    Mantiene el estado cromático por track / entidad vehicular.
    """

    def __init__(self, decay_lambda: float = 0.88, min_reliable_conf: float = 0.40):
        self.decay_lambda = decay_lambda
        self.min_reliable_conf = min_reliable_conf
        self._history: List[Tuple[VehicleColor, float]] = []

    def update(self, color_pred: VehicleColor, conf: float) -> Tuple[VehicleColor, float]:
        # Si la observación es UNKNOWN o de muy baja calidad, no contamina el historial
        if color_pred != VehicleColor.UNKNOWN and conf >= self.min_reliable_conf:
            self._history.append((color_pred, conf))

        if not self._history:
            return color_pred, conf

        # Votación ponderada con decaimiento exponencial hacia el pasado
        color_weights: Dict[VehicleColor, float] = {}
        total_weight = 0.0
        n = len(self._history)
        for i, (c, cf) in enumerate(self._history):
            # i = n - 1 es la más reciente (peso 1.0)
            weight = (self.decay_lambda ** (n - 1 - i)) * cf
            color_weights[c] = color_weights.get(c, 0.0) + weight
            total_weight += weight

        if total_weight <= 0.0:
            return color_pred, conf

        best_color = max(color_weights.keys(), key=lambda k: color_weights[k])
        consensus_conf = min(1.0, color_weights[best_color] / total_weight)
        return best_color, round(consensus_conf, 4)


def evaluate():
    logger.info("Iniciando evaluación de estabilidad temporal (Fase E)...")
    evid_root = REPO_ROOT / "evidencias_vigia"
    clf = VehicleColorClassifier()
    
    # Detector YOLO26x para extraer bboxes reales en cada frame de la ráfaga
    cfg = YoloDetectorConfig(
        model_path="experiments/yolo26x/weights/yolo26x.pt",
        device="cuda:0",
        quantize=16,
        confidence_threshold=0.50,
    )
    detector = YoloVehicleDetector(cfg)

    raw_predictions: List[Dict[str, Any]] = []
    smoothed_predictions: List[Dict[str, Any]] = []
    tracker = TemporalColorConsensusTracker()

    for idx, rel_path in enumerate(BURST_FRAMES):
        full_path = evid_root / rel_path
        if not full_path.exists():
            logger.warning("Archivo no encontrado: %s", full_path)
            continue
        img = cv2.imread(str(full_path))
        if img is None:
            continue

        dets = detector.detect(img)
        if not dets:
            continue

        primary = dets[0]
        res = clf.classify(img, primary.bbox, vehicle_class=primary.raw_label, detection_confidence=primary.confidence)
        
        # Raw record
        raw_predictions.append({
            "step": idx + 1,
            "file": rel_path,
            "bbox": primary.bbox.to_xywh_dict(),
            "raw_color": res.predominant_color.value,
            "raw_conf": float(res.confidence),
            "status": res.status.value,
        })

        # Smoothed record
        smooth_color, smooth_conf = tracker.update(res.predominant_color, float(res.confidence))
        smoothed_predictions.append({
            "step": idx + 1,
            "file": rel_path,
            "smoothed_color": smooth_color.value,
            "smoothed_conf": smooth_conf,
        })

    detector.unload()

    # Contar flips en crudo vs flips en suavizado
    raw_flips = 0
    raw_colors = [r["raw_color"] for r in raw_predictions]
    for i in range(1, len(raw_colors)):
        if raw_colors[i] != raw_colors[i - 1]:
            raw_flips += 1

    smooth_flips = 0
    smooth_colors = [s["smoothed_color"] for s in smoothed_predictions]
    for i in range(1, len(smooth_colors)):
        if smooth_colors[i] != smooth_colors[i - 1]:
            smooth_flips += 1

    summary = {
        "total_burst_frames": len(raw_predictions),
        "raw_color_sequence": raw_colors,
        "raw_flips_count": raw_flips,
        "raw_stability_ratio": round(1.0 - (raw_flips / max(1, len(raw_colors) - 1)), 4),
        "smoothed_color_sequence": smooth_colors,
        "smoothed_flips_count": smooth_flips,
        "smoothed_stability_ratio": round(1.0 - (smooth_flips / max(1, len(smooth_colors) - 1)), 4),
        "flips_reduction_percentage": round(((raw_flips - smooth_flips) / max(1, raw_flips)) * 100.0, 2),
        "dominant_entity_color": max(set(smooth_colors), key=smooth_colors.count) if smooth_colors else "UNKNOWN",
        "detailed_steps": [
            {
                "step": r["step"],
                "file": r["file"],
                "raw_color": r["raw_color"],
                "raw_conf": r["raw_conf"],
                "smoothed_color": s["smoothed_color"],
                "smoothed_conf": s["smoothed_conf"],
            }
            for r, s in zip(raw_predictions, smoothed_predictions)
        ],
    }

    out_file = REPO_ROOT / "experiments" / "vision_07b_1" / "results" / "temporal_stability_evaluation.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    logger.info("Evaluación de estabilidad temporal finalizada:")
    logger.info("  Frames analizados: %d", summary["total_burst_frames"])
    logger.info("  Flips en crudo (RAW): %d (estabilidad: %.1f%%)", raw_flips, summary["raw_stability_ratio"] * 100)
    logger.info("  Flips con suavizado: %d (estabilidad: %.1f%%)", smooth_flips, summary["smoothed_stability_ratio"] * 100)
    logger.info("  Reducción de flips: %.1f%%", summary["flips_reduction_percentage"])
    logger.info("  Color consolidado de entidad: %s", summary["dominant_entity_color"])
    return summary


if __name__ == "__main__":
    evaluate()
