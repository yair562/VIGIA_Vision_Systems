"""Utilidades aisladas para recorte seguro de ROI y diagnostico fotometrico."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np


@dataclass(frozen=True)
class RoiExtractionResult:
    """Resultado estructurado de extraer una ROI vehicular desde una imagen BGR."""

    crop_bgr: np.ndarray
    clamped_bbox: Tuple[int, int, int, int]
    area_px: int
    luminance_y: float
    sharpness_laplacian: float


def extract_roi_crop(
    image_bgr: np.ndarray,
    roi_xyxy: Optional[Tuple[int, int, int, int]] = None,
    *,
    inner_margin_ratio: float = 0.0,
) -> RoiExtractionResult:
    """
    Extrae un recorte BGR valido a partir de ``roi_xyxy`` (o usa toda la imagen
    si ``roi_xyxy`` es ``None``). Permite aplicar recorte interior para atenuar
    fondo en los bordes de la caja delimitadora.
    """
    if image_bgr is None or image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        raise ValueError("Se requiere una imagen BGR valida de forma (H, W, 3).")
    if not (0.0 <= inner_margin_ratio < 0.45):
        raise ValueError("inner_margin_ratio debe estar en [0.0, 0.45).")

    h, w = image_bgr.shape[:2]
    if roi_xyxy is None:
        x1, y1, x2, y2 = 0, 0, w, h
    else:
        rx1, ry1, rx2, ry2 = roi_xyxy
        x1 = max(0, min(w - 1, int(rx1)))
        y1 = max(0, min(h - 1, int(ry1)))
        x2 = max(x1 + 1, min(w, int(rx2)))
        y2 = max(y1 + 1, min(h, int(ry2)))

    if inner_margin_ratio > 0.0 and (x2 - x1) >= 10 and (y2 - y1) >= 10:
        dx = int((x2 - x1) * inner_margin_ratio)
        dy = int((y2 - y1) * inner_margin_ratio)
        nx1, ny1, nx2, ny2 = x1 + dx, y1 + dy, x2 - dx, y2 - dy
        if nx2 > nx1 and ny2 > ny1:
            x1, y1, x2, y2 = nx1, ny1, nx2, ny2

    crop = image_bgr[y1:y2, x1:x2].copy()
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return RoiExtractionResult(
        crop_bgr=crop,
        clamped_bbox=(x1, y1, x2, y2),
        area_px=int(crop.shape[0] * crop.shape[1]),
        luminance_y=round(float(gray.mean()), 3),
        sharpness_laplacian=round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 3),
    )
