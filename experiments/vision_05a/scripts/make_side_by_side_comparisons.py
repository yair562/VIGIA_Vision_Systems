"""
Genera imágenes comparativas lado a lado (3 paneles: YOLO11n Referencia | YOLO26x Baseline | YOLO26x Optimizado EXP-10)
separadas por las 7 categorías requeridas en Etapa B y Etapa 11:
1. Automóviles frontales
2. Autobuses frontales
3. Vehículos oblicuos
4. Vehículos laterales
5. Vehículos traseros
6. Vehículos pequeños
7. Baja iluminación
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ultralytics import YOLO
from VIGIA_Vision.config.topology_validator import AreaConfigDTO
from VIGIA_Vision.detection.roi_and_preprocess import project_normalized_roi
from experiments.vision_05a.scripts.run_experiments import (
    COCO_VEHICLE_CLASSES,
    deduplicate_boxes,
    parse_ultralytics_boxes,
)

EVIDENCE_DIR = REPO_ROOT / "evidencias_vigia"
OUT_CMP_DIR = REPO_ROOT / "experiments" / "vision_05a" / "results" / "comparisons"
OUT_CMP_DIR.mkdir(parents=True, exist_ok=True)
W_26X = REPO_ROOT / "experiments" / "yolo26x" / "weights" / "yolo26x.pt"
W_11N = REPO_ROOT / "yolo11n.pt"


def draw_panel(
    bgr: np.ndarray,
    boxes: Sequence[Dict[str, Any]],
    px_roi: Any,
    title: str,
    thresh: float = 0.70,
) -> np.ndarray:
    canvas = bgr.copy()
    h, w = canvas.shape[:2]
    rx1, ry1, rx2, ry2 = px_roi.to_int_tuple()
    cv2.rectangle(canvas, (rx1, ry1), (rx2, ry2), (0, 215, 255), 2)

    for b in boxes:
        conf = b["confidence"]
        if conf < 0.25:
            continue
        x1, y1, x2, y2 = b["bbox"]
        in_roi = b["in_roi"]
        if in_roi and conf >= thresh:
            color = (0, 220, 0)  # Verde: válida en ROI >= 0.70
            thick = 2
        elif in_roi:
            color = (0, 140, 255)  # Naranja: en ROI pero < 0.70
            thick = 2
        else:
            color = (180, 180, 180)  # Gris: fuera de ROI
            thick = 1
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thick)
        txt = f"{b['label']} {conf:.2f}"
        cv2.rectangle(canvas, (x1, max(0, y1 - 18)), (min(w, x1 + 110), y1), color, -1)
        cv2.putText(canvas, txt, (x1 + 3, max(12, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

    # Banner superior
    banner = np.zeros((34, w, 3), dtype=np.uint8)
    roi_hits = [b for b in boxes if b["in_roi"] and b["confidence"] >= thresh]
    status_txt = f"ROI>=0.70: {len(roi_hits)} | Total>=0.25: {sum(1 for b in boxes if b['confidence']>=0.25)}"
    cv2.putText(banner, f"{title} | {status_txt}", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1, cv2.LINE_AA)
    return np.vstack([banner, canvas])


def main() -> None:
    m11 = YOLO(str(W_11N))
    m11.to("cuda:0")
    m26 = YOLO(str(W_26X))
    m26.to("cuda:0")

    roi_dto = AreaConfigDTO(
        id_area_vision="00000000-0000-0000-0000-000000000001",
        id_camara="00000000-0000-0000-0000-000000000001",
        codigo="ROI-EVAL",
        nombre="ROI Operativa Estándar",
        tipo_movimiento="SALIDA",
        x_min=0.10,
        y_min=0.20,
        x_max=0.90,
        y_max=0.80,
        activa=True,
    )

    samples = [
        ("01_automovil_frontal_EV0625", "20261116/CAM-SALIDA/20261116T172015_568913Z_c43de572acc5_orig.jpg"),
        ("01_automovil_frontal_EV0637", "20261116/CAM-SALIDA/20261116T172044_969280Z_957178f6e593_orig.jpg"),
        ("01_automovil_frontal_EV0657", "20261116/CAM-SALIDA/20261116T172113_418425Z_e8a735512bc2_orig.jpg"),
        ("02_autobus_frontal_EV0581", "20261114/CAM-SALIDA/20261114T010037_321148Z_29a0e74bbe1e_orig.jpg"),
        ("02_autobus_frontal_EV0584", "20261114/CAM-SALIDA/20261114T010046_419841Z_1d02f0a21e97_orig.jpg"),
        ("02_autobus_frontal_EV0588", "20261114/CAM-SALIDA/20261114T010054_443040Z_bbf2d0cdf38b_orig.jpg"),
        ("03_vehiculo_oblicuo_EV0665", "20261116/CAM-SALIDA/20261116T172140_190972Z_c2499a3ef3d5_orig.jpg"),
        ("04_vehiculo_lateral_EV0550", "20261114/CAM-SALIDA/20261114T005953_419239Z_5f4588730e82_orig.jpg"),
        ("05_vehiculo_trasero_EV0446", "20261110/CAM-ENTRADA/20261110T184456_859308Z_d30f0fa6dafd_orig.jpg"),
        ("06_vehiculo_pequeno_EV0450", "20261111/CAM-ENTRADA/20261111T224045_274030Z_95edf2ebf66c_orig.jpg"),
        ("07_baja_iluminacion_EV0494", "20261114/CAM-SALIDA/20261114T004957_154790Z_2271be730b5b_orig.jpg"),
    ]

    for name, rel in samples:
        bgr = cv2.imread(str(EVIDENCE_DIR / rel))
        if bgr.shape[1] != 640:
            # Escalar visualmente para panel uniforme manteniendo inferencia sobre tamaño nativo
            pass
        h, w = bgr.shape[:2]
        px_roi = project_normalized_roi(roi_dto, w, h)

        # 1. YOLO11n
        b11 = parse_ultralytics_boxes(
            m11.predict(bgr, imgsz=640, classes=[2, 3, 5, 7], conf=0.10, quantize=16, verbose=False),
            w,
            h,
            px_roi,
        )
        # 2. YOLO26x Baseline
        b26_base = parse_ultralytics_boxes(
            m26.predict(bgr, imgsz=640, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=False, verbose=False),
            w,
            h,
            px_roi,
        )
        # 3. YOLO26x Optimizado (EXP-10)
        b640 = deduplicate_boxes(list(b26_base), iou_thresh=0.55, fuse_class_prob=True, fuse_same_class_split=True)
        b384 = parse_ultralytics_boxes(
            m26.predict(bgr, imgsz=384, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=False, verbose=False),
            w,
            h,
            px_roi,
        )
        b384 = deduplicate_boxes(b384, iou_thresh=0.55, fuse_class_prob=True, fuse_same_class_split=True)
        b26_opt = deduplicate_boxes(b640 + b384, iou_thresh=0.55, fuse_class_prob=True, fuse_same_class_split=True)

        p1 = draw_panel(bgr, b11, px_roi, "YOLO11n (Ref)")
        p2 = draw_panel(bgr, b26_base, px_roi, "YOLO26x Base")
        p3 = draw_panel(bgr, b26_opt, px_roi, "YOLO26x Opt (05A)")

        combined = np.hstack([p1, p2, p3])
        out_file = OUT_CMP_DIR / f"{name}_comparison.jpg"
        cv2.imwrite(str(out_file), combined, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        print(f"Saved {out_file.name}")


if __name__ == "__main__":
    main()
