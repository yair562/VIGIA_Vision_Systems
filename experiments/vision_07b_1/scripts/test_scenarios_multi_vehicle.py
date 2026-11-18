"""
test_scenarios_multi_vehicle.py
================================
Validación exhaustiva de los 8 escenarios multi-vehículo obligatorios
para la Fase VISION-07B.1 de VIGÍA Vision Systems.

Escenarios:
1. Un vehículo.
2. Dos vehículos.
3. Tres o más vehículos.
4. Vehículos de colores diferentes.
5. Vehículos parcialmente superpuestos.
6. Vehículos parcialmente ocultos.
7. Vehículos muy próximos.
8. Diferentes condiciones de iluminación.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from VIGIA_Vision.detection.color_classifier import (
    ColorClassificationStatus,
    VehicleColor,
    VehicleColorClassifier,
    VehicleColorConfig,
)
from VIGIA_Vision.detection.models import BoundingBox, RawVehicleDetection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def create_vehicle_canvas(
    width: int = 1280,
    height: int = 720,
    bg_color: Tuple[int, int, int] = (128, 128, 128),
) -> np.ndarray:
    return np.full((height, width, 3), bg_color, dtype=np.uint8)


def draw_synthetic_car(
    canvas: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    body_bgr: Tuple[int, int, int],
    glass_bgr: Tuple[int, int, int] = (40, 45, 50),
    tire_bgr: Tuple[int, int, int] = (20, 20, 20),
    occlusion_bottom_ratio: float = 0.0,
    glare: bool = False,
    illumination_factor: float = 1.0,
) -> BoundingBox:
    car_patch = np.zeros((h, w, 3), dtype=np.float32)
    car_patch[:, :] = np.array(body_bgr, dtype=np.float32)

    # Techo/cristal superior (25% superior)
    gw = int(w * 0.70)
    gh = int(h * 0.28)
    gx = int(w * 0.15)
    gy = int(h * 0.08)
    car_patch[gy : gy + gh, gx : gx + gw] = np.array(glass_bgr, dtype=np.float32)

    # Ruedas/neumáticos inferiores (18% inferior)
    tw = int(w * 0.22)
    th = int(h * 0.18)
    ty = h - th
    car_patch[ty:h, int(w * 0.10) : int(w * 0.10) + tw] = np.array(tire_bgr, dtype=np.float32)
    car_patch[ty:h, int(w * 0.68) : int(w * 0.68) + tw] = np.array(tire_bgr, dtype=np.float32)

    # Oclusión inferior (ej. barrera o asfalto)
    if occlusion_bottom_ratio > 0.0:
        occ_h = int(h * occlusion_bottom_ratio)
        car_patch[h - occ_h : h, :] = np.array((128, 128, 128), dtype=np.float32)

    # Deslumbramiento especular en el capó
    if glare:
        glare_cx = int(w * 0.5)
        glare_cy = int(h * 0.55)
        cv2.circle(car_patch, (glare_cx, glare_cy), int(min(w, h) * 0.18), (250, 250, 250), -1)

    # Ajuste de iluminación
    car_patch = car_patch * illumination_factor
    car_patch = np.clip(car_patch, 0, 255).astype(np.uint8)

    # Pegar en canvas
    canvas[y : y + h, x : x + w] = car_patch
    return BoundingBox(x, y, x + w, y + h)


def run_all_scenarios() -> Dict[str, Any]:
    clf = VehicleColorClassifier()
    results = {}

    # =========================================================================
    # ESCENARIO 1: Un vehículo individual
    # =========================================================================
    logger.info("Ejecutando Escenario 1: Un vehículo...")
    c1 = create_vehicle_canvas()
    b1 = draw_synthetic_car(c1, 400, 250, 280, 220, (25, 25, 220)) # RED
    r1 = clf.classify(c1, b1, vehicle_class="AUTOMOVIL", detection_confidence=0.95)
    e1_pass = (r1.predominant_color == VehicleColor.RED and r1.confidence >= 0.70)
    results["escenario_1_un_vehiculo"] = {
        "pass": bool(e1_pass),
        "expected": "RED",
        "predicted": r1.predominant_color.value,
        "confidence": float(r1.confidence),
        "status": r1.status.value,
    }

    # =========================================================================
    # ESCENARIO 2: Dos vehículos
    # =========================================================================
    logger.info("Ejecutando Escenario 2: Dos vehículos...")
    c2 = create_vehicle_canvas()
    b2_1 = draw_synthetic_car(c2, 150, 250, 260, 200, (220, 30, 20)) # BLUE
    b2_2 = draw_synthetic_car(c2, 650, 250, 260, 200, (20, 200, 220)) # YELLOW
    r2_1 = clf.classify(c2, b2_1, vehicle_class="AUTOMOVIL", detection_confidence=0.92)
    r2_2 = clf.classify(c2, b2_2, vehicle_class="CAMION", detection_confidence=0.89)
    e2_pass = (
        r2_1.predominant_color == VehicleColor.BLUE
        and r2_2.predominant_color == VehicleColor.YELLOW
        and r2_1.predominant_color != r2_2.predominant_color
    )
    results["escenario_2_dos_vehiculos"] = {
        "pass": bool(e2_pass),
        "vehiculo_1": {"expected": "BLUE", "predicted": r2_1.predominant_color.value, "confidence": float(r2_1.confidence)},
        "vehiculo_2": {"expected": "YELLOW", "predicted": r2_2.predominant_color.value, "confidence": float(r2_2.confidence)},
    }

    # =========================================================================
    # ESCENARIO 3: Tres o más vehículos
    # =========================================================================
    logger.info("Ejecutando Escenario 3: Tres o más vehículos...")
    c3 = create_vehicle_canvas(width=1600)
    b3_1 = draw_synthetic_car(c3, 100, 200, 260, 200, (20, 180, 20)) # GREEN
    b3_2 = draw_synthetic_car(c3, 500, 200, 260, 200, (240, 240, 240)) # WHITE
    b3_3 = draw_synthetic_car(c3, 900, 200, 260, 200, (30, 30, 30)) # BLACK
    b3_4 = draw_synthetic_car(c3, 1250, 200, 260, 200, (20, 20, 220)) # RED
    r3_1 = clf.classify(c3, b3_1, vehicle_class="AUTOMOVIL", detection_confidence=0.90)
    r3_2 = clf.classify(c3, b3_2, vehicle_class="CAMION", detection_confidence=0.94)
    r3_3 = clf.classify(c3, b3_3, vehicle_class="AUTOMOVIL", detection_confidence=0.91)
    r3_4 = clf.classify(c3, b3_4, vehicle_class="AUTOBUS", detection_confidence=0.93)
    e3_pass = (
        r3_1.predominant_color == VehicleColor.GREEN
        and r3_2.predominant_color == VehicleColor.WHITE
        and r3_3.predominant_color == VehicleColor.BLACK
        and r3_4.predominant_color == VehicleColor.RED
    )
    results["escenario_3_tres_o_mas_vehiculos"] = {
        "pass": bool(e3_pass),
        "total_vehiculos": 4,
        "vehiculo_1": {"expected": "GREEN", "predicted": r3_1.predominant_color.value, "confidence": float(r3_1.confidence)},
        "vehiculo_2": {"expected": "WHITE", "predicted": r3_2.predominant_color.value, "confidence": float(r3_2.confidence)},
        "vehiculo_3": {"expected": "BLACK", "predicted": r3_3.predominant_color.value, "confidence": float(r3_3.confidence)},
        "vehiculo_4": {"expected": "RED", "predicted": r3_4.predominant_color.value, "confidence": float(r3_4.confidence)},
    }

    # =========================================================================
    # ESCENARIO 4: Vehículos de colores diferentes
    # =========================================================================
    logger.info("Ejecutando Escenario 4: Vehículos de colores diferentes...")
    c4 = create_vehicle_canvas()
    b4_1 = draw_synthetic_car(c4, 200, 250, 260, 200, (15, 80, 220)) # ORANGE
    b4_2 = draw_synthetic_car(c4, 600, 250, 260, 200, (180, 180, 185)) # SILVER
    r4_1 = clf.classify(c4, b4_1, vehicle_class="AUTOMOVIL", detection_confidence=0.90)
    r4_2 = clf.classify(c4, b4_2, vehicle_class="AUTOMOVIL", detection_confidence=0.90)
    e4_pass = (r4_1.predominant_color in (VehicleColor.ORANGE, VehicleColor.RED) and r4_2.predominant_color == VehicleColor.SILVER)
    results["escenario_4_colores_diferentes"] = {
        "pass": bool(e4_pass),
        "vehiculo_1": {"expected": "ORANGE", "predicted": r4_1.predominant_color.value, "confidence": float(r4_1.confidence)},
        "vehiculo_2": {"expected": "SILVER", "predicted": r4_2.predominant_color.value, "confidence": float(r4_2.confidence)},
    }

    # =========================================================================
    # ESCENARIO 5: Vehículos parcialmente superpuestos
    # =========================================================================
    logger.info("Ejecutando Escenario 5: Vehículos parcialmente superpuestos...")
    c5 = create_vehicle_canvas()
    # Vehículo de fondo (Azul)
    b5_1 = draw_synthetic_car(c5, 250, 250, 260, 200, (220, 20, 20)) # BLUE
    # Vehículo frontal que solapa un 25% horizontal (Rojo)
    b5_2 = draw_synthetic_car(c5, 450, 250, 260, 200, (20, 20, 220)) # RED
    r5_1 = clf.classify(c5, b5_1, vehicle_class="AUTOMOVIL", detection_confidence=0.88)
    r5_2 = clf.classify(c5, b5_2, vehicle_class="AUTOMOVIL", detection_confidence=0.92)
    # Se evalúa que no haya contaminación cruzada mutua
    e5_pass = (r5_1.predominant_color == VehicleColor.BLUE and r5_2.predominant_color == VehicleColor.RED)
    results["escenario_5_parcialmente_superpuestos"] = {
        "pass": bool(e5_pass),
        "overlap_type": "horizontal_occlusion_25%",
        "vehiculo_1": {"expected": "BLUE", "predicted": r5_1.predominant_color.value, "confidence": float(r5_1.confidence)},
        "vehiculo_2": {"expected": "RED", "predicted": r5_2.predominant_color.value, "confidence": float(r5_2.confidence)},
    }

    # =========================================================================
    # ESCENARIO 6: Vehículos parcialmente ocultos
    # =========================================================================
    logger.info("Ejecutando Escenario 6: Vehículos parcialmente ocultos...")
    c6 = create_vehicle_canvas()
    # Vehículo con 25% inferior oculto por asfalto/barrera
    b6 = draw_synthetic_car(c6, 400, 250, 280, 220, (20, 180, 20), occlusion_bottom_ratio=0.25) # GREEN
    r6 = clf.classify(c6, b6, vehicle_class="AUTOMOVIL", detection_confidence=0.86)
    e6_pass = (r6.predominant_color == VehicleColor.GREEN and r6.confidence >= 0.65)
    results["escenario_6_parcialmente_ocultos"] = {
        "pass": bool(e6_pass),
        "occlusion_ratio": 0.25,
        "expected": "GREEN",
        "predicted": r6.predominant_color.value,
        "confidence": float(r6.confidence),
        "status": r6.status.value,
    }

    # =========================================================================
    # ESCENARIO 7: Vehículos muy próximos
    # =========================================================================
    logger.info("Ejecutando Escenario 7: Vehículos muy próximos...")
    c7 = create_vehicle_canvas()
    # Dos vehículos separados por solo 8 píxeles
    b7_1 = draw_synthetic_car(c7, 200, 250, 260, 200, (20, 200, 220)) # YELLOW
    b7_2 = draw_synthetic_car(c7, 468, 250, 260, 200, (220, 30, 20)) # BLUE
    r7_1 = clf.classify(c7, b7_1, vehicle_class="AUTOMOVIL", detection_confidence=0.91)
    r7_2 = clf.classify(c7, b7_2, vehicle_class="AUTOMOVIL", detection_confidence=0.91)
    e7_pass = (
        r7_1.predominant_color == VehicleColor.YELLOW
        and r7_2.predominant_color == VehicleColor.BLUE
        and r7_1.predominant_color != r7_2.predominant_color
    )
    results["escenario_7_vehiculos_muy_proximos"] = {
        "pass": bool(e7_pass),
        "gap_px": 8,
        "vehiculo_1": {"expected": "YELLOW", "predicted": r7_1.predominant_color.value, "confidence": float(r7_1.confidence)},
        "vehiculo_2": {"expected": "BLUE", "predicted": r7_2.predominant_color.value, "confidence": float(r7_2.confidence)},
    }

    # =========================================================================
    # ESCENARIO 8: Diferentes condiciones de iluminación
    # =========================================================================
    logger.info("Ejecutando Escenario 8: Diferentes condiciones de iluminación...")
    illum_subresults = {}
    illum_passes = 0

    # 8a: Baja iluminación (factor 0.35)
    c8_low = create_vehicle_canvas(bg_color=(30, 30, 30))
    b8_low = draw_synthetic_car(c8_low, 300, 200, 260, 200, (20, 20, 220), illumination_factor=0.35) # RED tenue
    r8_low = clf.classify(c8_low, b8_low, vehicle_class="AUTOMOVIL", detection_confidence=0.85)
    pass_low = (r8_low.predominant_color == VehicleColor.RED or r8_low.status == ColorClassificationStatus.LOW_ILLUMINATION)
    if pass_low: illum_passes += 1
    illum_subresults["baja_iluminacion"] = {
        "pass": bool(pass_low),
        "predicted": r8_low.predominant_color.value,
        "confidence": float(r8_low.confidence),
        "status": r8_low.status.value,
    }

    # 8b: Deslumbramiento/reflejo solar intenso
    c8_glare = create_vehicle_canvas()
    b8_glare = draw_synthetic_car(c8_glare, 300, 200, 260, 200, (220, 20, 20), glare=True) # BLUE con reflejo
    r8_glare = clf.classify(c8_glare, b8_glare, vehicle_class="AUTOMOVIL", detection_confidence=0.88)
    pass_glare = (r8_glare.predominant_color == VehicleColor.BLUE)
    if pass_glare: illum_passes += 1
    illum_subresults["deslumbramiento_solar"] = {
        "pass": bool(pass_glare),
        "predicted": r8_glare.predominant_color.value,
        "confidence": float(r8_glare.confidence),
        "status": r8_glare.status.value,
    }

    # 8c: Iluminación estándar óptima
    c8_std = create_vehicle_canvas()
    b8_std = draw_synthetic_car(c8_std, 300, 200, 260, 200, (240, 240, 240)) # WHITE
    r8_std = clf.classify(c8_std, b8_std, vehicle_class="AUTOMOVIL", detection_confidence=0.92)
    pass_std = (r8_std.predominant_color == VehicleColor.WHITE)
    if pass_std: illum_passes += 1
    illum_subresults["iluminacion_estandar"] = {
        "pass": bool(pass_std),
        "predicted": r8_std.predominant_color.value,
        "confidence": float(r8_std.confidence),
        "status": r8_std.status.value,
    }

    e8_pass = (illum_passes >= 3)
    results["escenario_8_diferentes_iluminaciones"] = {
        "pass": bool(e8_pass),
        "casos_evaluados": 3,
        "casos_exitosos": illum_passes,
        "detalle": illum_subresults,
    }

    total_scenarios = len(results)
    passed_scenarios = sum(1 for v in results.values() if v.get("pass", False))
    summary = {
        "total_scenarios": total_scenarios,
        "passed_scenarios": passed_scenarios,
        "all_passed": (passed_scenarios == total_scenarios),
        "results": results,
    }

    out_path = REPO_ROOT / "experiments" / "vision_07b_1" / "results" / "multi_vehicle_scenarios_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    logger.info("Resultados de los 8 escenarios guardados en: %s", out_path)
    return summary


if __name__ == "__main__":
    s = run_all_scenarios()
    print(f"RESUMEN: {s['passed_scenarios']}/{s['total_scenarios']} escenarios PASS (all_passed={s['all_passed']})")
    if not s["all_passed"]:
        sys.exit(1)
