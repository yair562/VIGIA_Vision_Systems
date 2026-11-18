"""
Extractor de caracteristicas cromaticas HSV + CIELAB para Baseline B (ML clasico).

Produce un vector determinista de longitud fija a partir de histogramas
normalizados y estadisticas robustas tras enmascarar sombras extremas y
reflejos especulares.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

from src.preprocessing.roi_crop import extract_roi_crop


@dataclass(frozen=True)
class ColorFeatureConfig:
    inner_crop_margin: float = 0.12
    hue_bins: int = 16
    sv_bins: int = 8
    lab_bins: int = 8
    shadow_v_min: int = 25
    glare_v_max: int = 246
    glare_s_max: int = 26

    @property
    def feature_dim(self) -> int:
        # Histograms: hue + S + V + L + a + b
        hist_dim = self.hue_bins + (2 * self.sv_bins) + (3 * self.lab_bins)
        # Summary stats: (mean, std, p10, p50, p90) x 6 channels + 3 quality ratios
        return hist_dim + (6 * 5) + 3


def _normalized_hist_1d(channel: np.ndarray, mask: np.ndarray, bins: int, upper: float) -> np.ndarray:
    hist = cv2.calcHist([channel], [0], mask.astype(np.uint8), [bins], [0, upper]).flatten()
    total = float(hist.sum())
    return (hist / total).astype(np.float32) if total > 0 else np.zeros(bins, dtype=np.float32)


def extract_color_feature_vector(
    image_bgr: np.ndarray,
    roi_xyxy: Optional[Tuple[int, int, int, int]] = None,
    config: Optional[ColorFeatureConfig] = None,
) -> np.ndarray:
    """
    Extrae un vector 1D normalizado de caracteristicas HSV + CIELAB + calidad
    para entrenar o evaluar modelos tabulares (SVM / Random Forest).
    """
    cfg = config or ColorFeatureConfig()
    roi = extract_roi_crop(image_bgr, roi_xyxy, inner_margin_ratio=cfg.inner_crop_margin)
    crop = roi.crop_bgr

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)

    v_ch = hsv[:, :, 2]
    s_ch = hsv[:, :, 1]
    shadow_mask = v_ch < cfg.shadow_v_min
    glare_mask = (v_ch > cfg.glare_v_max) & (s_ch < cfg.glare_s_max)
    valid_mask = (~shadow_mask) & (~glare_mask)
    if int(valid_mask.sum()) < 16:
        valid_mask = np.ones(v_ch.shape, dtype=bool)

    parts = [
        _normalized_hist_1d(hsv[:, :, 0], valid_mask, cfg.hue_bins, 180.0),
        _normalized_hist_1d(hsv[:, :, 1], valid_mask, cfg.sv_bins, 256.0),
        _normalized_hist_1d(hsv[:, :, 2], valid_mask, cfg.sv_bins, 256.0),
        _normalized_hist_1d(lab[:, :, 0], valid_mask, cfg.lab_bins, 256.0),
        _normalized_hist_1d(lab[:, :, 1], valid_mask, cfg.lab_bins, 256.0),
        _normalized_hist_1d(lab[:, :, 2], valid_mask, cfg.lab_bins, 256.0),
    ]

    stats = []
    for ch in (
        hsv[:, :, 0],
        hsv[:, :, 1],
        hsv[:, :, 2],
        lab[:, :, 0],
        lab[:, :, 1],
        lab[:, :, 2],
    ):
        vals = ch[valid_mask].astype(np.float32)
        p10, p50, p90 = np.percentile(vals, [10, 50, 90])
        stats.extend([float(vals.mean()), float(vals.std()), float(p10), float(p50), float(p90)])

    ratios = [
        float(valid_mask.mean()),
        float(shadow_mask.mean()),
        float(glare_mask.mean()),
    ]
    parts.append(np.array(stats + ratios, dtype=np.float32))
    return np.concatenate(parts, axis=0)
