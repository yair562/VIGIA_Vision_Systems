"""
VIGIA_Vision.classification.normalizer
======================================
Normalizador fotométrico y extractor de muestreo anatómico corporal de vehículos
para VIGÍA Vision Systems (Fase VISION-05B).

Implementa:
- Extracción defensiva de la caja delimitadora con recorte a límites de imagen.
- Muestreo anatómico de carrocería (excluye parabrisas, ventanas, techo, neumáticos y sombra).
- Ponderación espacial elíptica para priorizar chapa central sobre bordes externos.
- Filtrado de sombras profundas y reflejos especulares.
- Cálculo de métricas objetivas de calidad fotométrica.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple

import cv2
import numpy as np

from VIGIA_Vision.classification.config import VehicleColorConfig
from VIGIA_Vision.classification.models import ColorQualityMetrics


@dataclass(frozen=True)
class NormalizedBodyCrop:
    """Resultado estructurado de la normalización y muestreo anatómico."""

    crop_bgr: np.ndarray
    hsv: np.ndarray
    lab: np.ndarray
    valid_mask: np.ndarray
    spatial_weights: np.ndarray
    quality_metrics: ColorQualityMetrics
    clamped_bbox: Tuple[int, int, int, int]
    anatomical_bbox: Tuple[int, int, int, int]


class VehicleColorNormalizer:
    """
    Normalizador y preparador de regiones corporales vehiculares.
    Garantiza que la clasificación cromática se ejecute sobre chapa vehicular
    limpia y no sobre asfalto, cristales reflectantes o neumáticos.
    """

    def __init__(self, config: Optional[VehicleColorConfig] = None) -> None:
        self.config = config or VehicleColorConfig()

    @staticmethod
    def parse_bbox_coordinates(bbox: Any, frame_w: int, frame_h: int) -> Tuple[int, int, int, int]:
        """
        Interpreta defensivamente BoundingBox, dict o tuplas (x1, y1, x2, y2)
        y las recorta a los límites de la imagen.
        """
        if bbox is None:
            raise ValueError("bbox no puede ser None.")

        # 1. Instancia BoundingBox de VIGIA_Vision
        if hasattr(bbox, "x_min") and hasattr(bbox, "y_min") and hasattr(bbox, "x_max") and hasattr(bbox, "y_max"):
            x1, y1, x2, y2 = int(bbox.x_min), int(bbox.y_min), int(bbox.x_max), int(bbox.y_max)
        # 2. Dict con claves {'x_min', 'y_min', 'x_max', 'y_max'} o {'x', 'y', 'w', 'h'}
        elif isinstance(bbox, dict):
            if "x_min" in bbox and "y_min" in bbox and "x_max" in bbox and "y_max" in bbox:
                x1, y1, x2, y2 = int(bbox["x_min"]), int(bbox["y_min"]), int(bbox["x_max"]), int(bbox["y_max"])
            elif "x" in bbox and "y" in bbox and "w" in bbox and "h" in bbox:
                x1, y1 = int(bbox["x"]), int(bbox["y"])
                x2, y2 = x1 + int(bbox["w"]), y1 + int(bbox["h"])
            else:
                raise ValueError(f"Diccionario bbox con claves no reconocidas: {list(bbox.keys())}")
        # 3. Secuencia (tupla o lista) de 4 elementos
        elif isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        else:
            raise ValueError(f"Formato de bbox no soportado: {type(bbox)}")

        # Clamping defensivo
        cx1 = max(0, min(frame_w - 1, x1))
        cy1 = max(0, min(frame_h - 1, y1))
        cx2 = max(cx1 + 1, min(frame_w, x2))
        cy2 = max(cy1 + 1, min(frame_h, y2))

        return cx1, cy1, cx2, cy2

    def extract_anatomical_body_crop(
        self,
        image_bgr: np.ndarray,
        bbox: Any,
    ) -> NormalizedBodyCrop:
        """
        Extrae y normaliza la región corporal del vehículo aplicando muestreo
        anatómico para excluir parabrisas, ventanas, techo, ruedas y sombra de asfalto.
        """
        if image_bgr is None or not isinstance(image_bgr, np.ndarray) or image_bgr.ndim != 3:
            raise ValueError("image_bgr debe ser un arreglo NumPy tridimensional (H, W, 3).")
        if image_bgr.shape[2] != 3:
            raise ValueError(f"image_bgr debe tener 3 canales BGR, recibido shape={image_bgr.shape}.")

        frame_h, frame_w = image_bgr.shape[:2]
        x1, y1, x2, y2 = self.parse_bbox_coordinates(bbox, frame_w, frame_h)
        bw = x2 - x1
        bh = y2 - y1
        bbox_area = bw * bh

        # Muestreo anatómico corporal:
        # Altura: [y_min_ratio * bh .. y_max_ratio * bh] (descarta cristales y ruedas)
        # Ancho: margen lateral para reducir fondo
        if bw >= 20 and bh >= 20:
            dx = int(bw * self.config.anatomical_crop_x_margin_ratio)
            dy_top = int(bh * self.config.anatomical_crop_y_min_ratio)
            dy_bottom = int(bh * (1.0 - self.config.anatomical_crop_y_max_ratio))

            ax1 = max(0, min(frame_w - 1, x1 + dx))
            ay1 = max(0, min(frame_h - 1, y1 + dy_top))
            ax2 = max(ax1 + 1, min(frame_w, x2 - dx))
            ay2 = max(ay1 + 1, min(frame_h, y2 - dy_bottom))
        else:
            ax1, ay1, ax2, ay2 = x1, y1, x2, y2

        crop = image_bgr[ay1:ay2, ax1:ax2].copy()
        ch, cw = crop.shape[:2]
        sampled_area = ch * cw

        # Conversiones de espacio de color
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        v_ch = hsv[:, :, 2]
        s_ch = hsv[:, :, 1]
        l_ch = lab[:, :, 0]
        a_ch = lab[:, :, 1].astype(np.float32) - 128.0
        b_ch = lab[:, :, 2].astype(np.float32) - 128.0

        # Detección de sombras profundas y reflejos especulares
        deep_shadow = (v_ch < self.config.shadow_v_min) & (l_ch < self.config.shadow_l_min)
        specular_glare = (v_ch > self.config.glare_v_max) & (s_ch < self.config.glare_s_max)
        valid_mask = (~deep_shadow) & (~specular_glare)

        # Si el filtrado elimina casi todo, preservar señal mínima
        if int(valid_mask.sum()) < 16:
            valid_mask = np.ones((ch, cw), dtype=bool)

        shadow_ratio = float(deep_shadow.mean())
        glare_ratio = float(specular_glare.mean())
        usable_pixel_ratio = float(valid_mask.mean())

        # Métricas fotométricas objetivas
        mean_lum = float(gray.mean())
        mean_sat = float(s_ch[valid_mask].mean()) if valid_mask.any() else float(s_ch.mean())
        chroma = np.sqrt(a_ch**2 + b_ch**2)
        mean_chroma = float(chroma[valid_mask].mean()) if valid_mask.any() else float(chroma.mean())
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        # Ponderación espacial elíptica: chapa central tiene más peso que bordes
        weight_mask = np.zeros((ch, cw), dtype=np.float32)
        center = (cw // 2, ch // 2)
        axes = (max(1, int(cw * 0.44)), max(1, int(ch * 0.42)))
        cv2.ellipse(weight_mask, center, axes, 0, 0, 360, 1.0, -1)
        spatial_weights = np.where(weight_mask > 0.5, 1.0, 0.30).astype(np.float32)

        quality_metrics = ColorQualityMetrics(
            bbox_area=bbox_area,
            sampled_area=sampled_area,
            usable_pixel_ratio=round(usable_pixel_ratio, 4),
            shadow_ratio=round(shadow_ratio, 4),
            glare_ratio=round(glare_ratio, 4),
            mean_luminance=round(mean_lum, 3),
            mean_saturation=round(mean_sat, 3),
            mean_lab_chroma=round(mean_chroma, 3),
            sharpness_laplacian=round(sharpness, 3),
            quality_flag="OK",
        )

        return NormalizedBodyCrop(
            crop_bgr=crop,
            hsv=hsv,
            lab=lab,
            valid_mask=valid_mask,
            spatial_weights=spatial_weights,
            quality_metrics=quality_metrics,
            clamped_bbox=(x1, y1, x2, y2),
            anatomical_bbox=(ax1, ay1, ax2, ay2),
        )
