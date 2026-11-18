"""
Baseline A — Reconocimiento experimental de color por Vision Artificial Clasica.

Combina:
1. Conversion BGR -> HSV y BGR -> CIELAB.
2. Enmascaramiento de fondo periferico (pesado espacial eliptico + margen).
3. Filtrado de sombras extremas, regiones sobreexpuestas/especulares y zonas
   poco informativas.
4. Evaluacion cromatica mediante mascaras de intervalos HSV y distancia perceptual
   en CIELAB (a*, b*, L*).
5. Emision explicita de ``INDETERMINATE`` cuando la calidad o evidencia resulta
   insuficiente para decidir sin adivinar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from src.dataset.annotation_schema import COLOR_CLASSES
from src.preprocessing.roi_crop import extract_roi_crop


@dataclass(frozen=True)
class ClassicColorConfig:
    """Parametros calibrables del analizador clasico de color (Baseline A)."""

    inner_crop_margin: float = 0.12
    min_roi_pixels: int = 400
    min_valid_pixel_ratio: float = 0.18
    # Umbrales de filtrado de artefactos (escala OpenCV 0..255)
    shadow_v_min: int = 32
    shadow_l_min: int = 18
    glare_v_max: int = 246
    glare_s_max: int = 26
    achromatic_s_max: int = 42
    min_confidence_for_decision: float = 0.32
    min_margin_over_second: float = 0.04


@dataclass(frozen=True)
class ColorPrediction:
    """Salida estructurada e interpretable de Baseline A."""

    predicted_color: str
    confidence: float
    category_scores: Dict[str, float]
    quality_indicator: Dict[str, float | str | bool]
    is_indeterminate: bool
    reason: str
    hsv_histogram_summary: Dict[str, float] = field(default_factory=dict)


def _compute_foreground_weight_mask(height: int, width: int) -> np.ndarray:
    """Peso espacial eliptico centrado para reducir contaminacion del fondo."""
    mask = np.zeros((height, width), dtype=np.float32)
    center = (width // 2, height // 2)
    axes = (max(1, int(width * 0.44)), max(1, int(height * 0.42)))
    cv2.ellipse(mask, center, axes, 0, 0, 360, 1.0, -1)
    # Dar peso completo al centro y peso atenuado (0.25) fuera de la elipse
    mask = np.where(mask > 0.5, 1.0, 0.25).astype(np.float32)
    return mask


def predict_color_classic(
    image_bgr: np.ndarray,
    roi_xyxy: Optional[Tuple[int, int, int, int]] = None,
    config: Optional[ClassicColorConfig] = None,
) -> ColorPrediction:
    """
    Estima el color vehicular dominante dentro de una ROI sin depender de modelos
    entrenados. Retorna ``INDETERMINATE`` si la ROI es demasiado pequena,
    subexpuesta, deslumbrada o ambigua.
    """
    cfg = config or ClassicColorConfig()
    roi = extract_roi_crop(
        image_bgr,
        roi_xyxy,
        inner_margin_ratio=cfg.inner_crop_margin,
    )
    crop = roi.crop_bgr
    h, w = crop.shape[:2]
    total_px = max(1, h * w)

    empty_scores = {c: (1.0 if c == "INDETERMINATE" else 0.0) for c in COLOR_CLASSES}
    if roi.area_px < cfg.min_roi_pixels:
        return ColorPrediction(
            predicted_color="INDETERMINATE",
            confidence=0.0,
            category_scores=empty_scores,
            quality_indicator={
                "area_px": roi.area_px,
                "usable_pixel_ratio": 0.0,
                "luminance_y": roi.luminance_y,
                "sharpness_laplacian": roi.sharpness_laplacian,
                "quality_flag": "ROI_TOO_SMALL",
            },
            is_indeterminate=True,
            reason=f"Area ROI insuficiente ({roi.area_px} px < {cfg.min_roi_pixels} px).",
        )

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)

    h_ch = hsv[:, :, 0]
    s_ch = hsv[:, :, 1]
    v_ch = hsv[:, :, 2]
    l_ch = lab[:, :, 0]
    a_ch = lab[:, :, 1].astype(np.float32) - 128.0
    b_ch = lab[:, :, 2].astype(np.float32) - 128.0

    # Filtrado de regiones poco informativas: sombras profundas y reflejo especular
    deep_shadow = (v_ch < cfg.shadow_v_min) & (l_ch < cfg.shadow_l_min)
    specular_glare = (v_ch > cfg.glare_v_max) & (s_ch < cfg.glare_s_max)

    fg_weights = _compute_foreground_weight_mask(h, w)
    # Consideramos validos los pixeles dentro de la elipse o no descartados por artefacto extremo
    valid_mask = (~deep_shadow) & (~specular_glare)
    valid_ratio = float(valid_mask.mean())
    shadow_ratio = float(deep_shadow.mean())
    glare_ratio = float(specular_glare.mean())

    # Deteccion de negro real vs subexposicion inutilizable:
    # Un vehiculo negro bajo iluminacion normal suele tener L* ~ [20..58] y V ~ [32..80],
    # mientras que un recorte completamente apagado (mean V < 24) carece de señal confiable.
    mean_v = float(v_ch.mean())
    mean_s = float(s_ch.mean())
    if mean_v < 24.0 or valid_ratio < cfg.min_valid_pixel_ratio:
        return ColorPrediction(
            predicted_color="INDETERMINATE",
            confidence=0.0,
            category_scores=empty_scores,
            quality_indicator={
                "area_px": roi.area_px,
                "usable_pixel_ratio": round(valid_ratio, 4),
                "shadow_ratio": round(shadow_ratio, 4),
                "glare_ratio": round(glare_ratio, 4),
                "luminance_y": roi.luminance_y,
                "sharpness_laplacian": roi.sharpness_laplacian,
                "quality_flag": "INSUFFICIENT_ILLUMINATION_OR_SIGNAL",
            },
            is_indeterminate=True,
            reason=(
                f"Senal cromatica insuficiente (mean_V={mean_v:.1f}, "
                f"usable_ratio={valid_ratio:.2f})."
            ),
        )

    # Si casi todo es reflejo especular sobreexpuesto (>75%), no podemos distinguir blanco vs destello
    if glare_ratio > 0.75:
        return ColorPrediction(
            predicted_color="INDETERMINATE",
            confidence=0.0,
            category_scores=empty_scores,
            quality_indicator={
                "area_px": roi.area_px,
                "usable_pixel_ratio": round(valid_ratio, 4),
                "shadow_ratio": round(shadow_ratio, 4),
                "glare_ratio": round(glare_ratio, 4),
                "luminance_y": roi.luminance_y,
                "sharpness_laplacian": roi.sharpness_laplacian,
                "quality_flag": "SEVERE_GLARE",
            },
            is_indeterminate=True,
            reason=f"Deslumbramiento especular severo ({glare_ratio:.1%}).",
        )

    w_valid = np.where(valid_mask, fg_weights, 0.0)
    total_w = float(w_valid.sum())
    if total_w <= 1e-6:
        total_w = 1.0

    # 1. Mascaras HSV por categoria cromatica (OpenCV Hue in [0, 179])
    chromatic = s_ch >= cfg.achromatic_s_max
    red_mask = chromatic & ((h_ch <= 8) | (h_ch >= 168)) & (v_ch >= 45)
    # Marron / guinda: rojo-naranja de bajo brillo/saturacion moderada o LAB a+>12, b+>8 con L* medio-bajo
    brown_mask = (
        chromatic
        & ((h_ch >= 6) & (h_ch <= 20))
        & (v_ch < 135)
    ) | (
        chromatic
        & ((h_ch >= 165) | (h_ch <= 10))
        & (v_ch < 95)
        & (l_ch < 48)
    )
    orange_mask = chromatic & (h_ch >= 9) & (h_ch <= 20) & (v_ch >= 135) & (~brown_mask)
    yellow_mask = chromatic & (h_ch >= 21) & (h_ch <= 34) & (v_ch >= 80)
    green_mask = chromatic & (h_ch >= 35) & (h_ch <= 85) & (v_ch >= 45)
    blue_mask = chromatic & (h_ch >= 90) & (h_ch <= 135) & (v_ch >= 45)

    # 2. Acromaticos mediante L* (CIELAB) + S/V (HSV)
    achrom = ~chromatic
    white_mask = achrom & (v_ch >= 195) & (l_ch >= 185)
    silver_mask = achrom & (v_ch >= 145) & (v_ch < 195) & (l_ch >= 140)
    gray_mask = achrom & (v_ch >= 75) & (v_ch < 145)
    black_mask = achrom & (v_ch < 75)

    raw_masks = {
        "RED": red_mask & (~brown_mask),
        "BROWN": brown_mask,
        "ORANGE": orange_mask,
        "YELLOW": yellow_mask,
        "GREEN": green_mask,
        "BLUE": blue_mask,
        "WHITE": white_mask,
        "SILVER": silver_mask,
        "GRAY": gray_mask,
        "BLACK": black_mask,
    }

    scores: Dict[str, float] = {c: 0.0 for c in COLOR_CLASSES}
    covered_mask = np.zeros((h, w), dtype=bool)
    for cname, m in raw_masks.items():
        active = m & valid_mask
        covered_mask |= active
        scores[cname] = float((w_valid * active).sum() / total_w)

    uncovered = valid_mask & (~covered_mask)
    scores["OTHER"] = float((w_valid * uncovered).sum() / total_w)

    # Refinamiento perceptual CIELAB para distinguir cromatismo sutil vs ruido achromatico
    mean_chroma = float(np.sqrt(a_ch[valid_mask] ** 2 + b_ch[valid_mask] ** 2).mean())
    if mean_chroma > 28.0:
        # Si hay alta cromaticidad media en CIELAB, atenuar falsos acromaticos por sombras de carroceria
        for ac in ("BLACK", "GRAY", "SILVER"):
            scores[ac] *= 0.65

    # Normalizar puntuaciones sobre las categorias evaluables (sin INDETERMINATE)
    eval_sum = sum(v for k, v in scores.items() if k != "INDETERMINATE")
    if eval_sum > 1e-6:
        for k in list(scores.keys()):
            if k != "INDETERMINATE":
                scores[k] = round(scores[k] / eval_sum, 4)

    ranked = sorted(
        ((k, v) for k, v in scores.items() if k != "INDETERMINATE"),
        key=lambda item: item[1],
        reverse=True,
    )
    best_color, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = best_score - second_score

    is_indet = False
    reason = "Clasificacion cromatica HSV+CIELAB consistente."
    if best_score < cfg.min_confidence_for_decision or margin < cfg.min_margin_over_second:
        is_indet = True
        predicted = "INDETERMINATE"
        scores["INDETERMINATE"] = round(max(0.5, 1.0 - best_score), 4)
        reason = (
            f"Ambiguedad cromatica (top1={best_color}:{best_score:.2f}, "
            f"margen={margin:.2f})."
        )
    else:
        predicted = best_color

    # Resumen compacto del histograma Hue valido (16 bins normalizados)
    hue_hist = cv2.calcHist([hsv], [0], valid_mask.astype(np.uint8), [16], [0, 180]).flatten()
    if hue_hist.sum() > 0:
        hue_hist = hue_hist / hue_hist.sum()
    dominant_bin = int(np.argmax(hue_hist))

    return ColorPrediction(
        predicted_color=predicted,
        confidence=round(float(best_score), 4),
        category_scores=scores,
        quality_indicator={
            "area_px": roi.area_px,
            "usable_pixel_ratio": round(valid_ratio, 4),
            "shadow_ratio": round(shadow_ratio, 4),
            "glare_ratio": round(glare_ratio, 4),
            "luminance_y": roi.luminance_y,
            "sharpness_laplacian": roi.sharpness_laplacian,
            "mean_lab_chroma": round(mean_chroma, 2),
            "quality_flag": "OK" if not is_indet else "AMBIGUOUS_CHROMA",
        },
        is_indeterminate=is_indet,
        reason=reason,
        hsv_histogram_summary={
            "mean_s": round(mean_s, 2),
            "mean_v": round(mean_v, 2),
            "dominant_hue_bin_16": dominant_bin,
        },
    )
