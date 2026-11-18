"""
VIGIA-VISION-05A — Etapa C: Diagnóstico Técnico de Fallos Frontales en YOLO26x
==============================================================================
Inspecciona la arquitectura interna de yolo26x.pt y evalúa aisladamente el efecto
de cada factor (arquitectura one2one vs one2many, FP16 vs FP32, imgsz, escala/padding
geométrico, nitidez/contraste y partición de confianza inter-clase).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
import cv2
import numpy as np
import torch
from ultralytics import YOLO

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EVIDENCE_DIR = REPO_ROOT / "evidencias_vigia"
W_26X = REPO_ROOT / "experiments" / "yolo26x" / "weights" / "yolo26x.pt"
W_11N = REPO_ROOT / "yolo11n.pt"


def inspect_model_internals(model: YOLO) -> dict:
    inner = model.model
    head = inner.model[-1]
    ckpt = getattr(model, "ckpt", {}) or {}
    train_args = ckpt.get("train_args", {}) if isinstance(ckpt, dict) else {}
    return {
        "model_type": type(inner).__name__,
        "head_type": type(head).__name__,
        "end2end": getattr(head, "end2end", None),
        "has_one2one_cv2": getattr(head, "one2one_cv2", None) is not None,
        "has_one2one_cv3": getattr(head, "one2one_cv3", None) is not None,
        "has_cv2": getattr(head, "cv2", None) is not None,
        "has_cv3": getattr(head, "cv3", None) is not None,
        "stride": head.stride.tolist() if hasattr(head, "stride") else None,
        "nc": getattr(head, "nc", None),
        "reg_max": getattr(head, "reg_max", None),
        "max_det": getattr(head, "max_det", None),
        "vehicle_names": {k: inner.names[k] for k in (2, 3, 5, 7) if k in inner.names},
        "train_imgsz": train_args.get("imgsz"),
        "train_data": train_args.get("data"),
        "train_epochs": train_args.get("epochs"),
    }


def run_single(model: YOLO, img: np.ndarray, **kwargs) -> list:
    res = model.predict(
        source=img,
        classes=[2, 3, 5, 7],
        conf=0.05,
        verbose=False,
        device="cuda:0",
        **kwargs,
    )
    out = []
    if res and res[0].boxes is not None:
        for b in res[0].boxes:
            c_id = int(b.cls[0])
            conf = float(b.conf[0])
            xyxy = [int(round(x)) for x in b.xyxy[0].tolist()]
            out.append((model.names[c_id], round(conf, 4), xyxy))
    return out


def pad_zoom_out(img: np.ndarray, scale: float = 0.65) -> np.ndarray:
    """Reduce el tamaño aparente del vehículo en el encuadre con relleno reflect/border."""
    h, w = img.shape[:2]
    nh, nw = int(round(h * scale)), int(round(w * scale))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    top = (h - nh) // 2
    bottom = h - nh - top
    left = (w - nw) // 2
    right = w - nw - left
    return cv2.copyMakeBorder(resized, top, bottom, left, right, cv2.BORDER_REPLICATE)


def apply_clahe_bgr(img: np.ndarray, clip_limit: float = 2.0) -> np.ndarray:
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    l2 = clahe.apply(l)
    return cv2.cvtColor(cv2.merge((l2, a, b)), cv2.COLOR_LAB2BGR)


def apply_unsharp(img: np.ndarray, sigma: float = 1.5, amount: float = 1.5) -> np.ndarray:
    blur = cv2.GaussianBlur(img, (0, 0), sigma)
    return cv2.addWeighted(img, 1.0 + amount, blur, -amount, 0)


def main() -> None:
    m26 = YOLO(str(W_26X))
    m26.to("cuda:0")
    info = inspect_model_internals(m26)
    print("=== Internals YOLO26x ===")
    print(json.dumps(info, indent=2))

    # Casos problemáticos representativos:
    # 1. Automóvil frontal cyan + rosa (20261116T172036_202643Z_df5e1071c00f_orig.jpg) -> EV-0635
    # 2. Automóvil frontal cyan solo (20261116T172020_828094Z_dc015465e05a_orig.jpg) -> EV-0627
    # 3. Automóvil frontal rosa grande (20261116T172044_969280Z_957178f6e593_orig.jpg) -> EV-0637
    # 4. Autobús frontal amarillo en mano (20261114T010013_064537Z_07ac07b83576_orig.jpg) -> EV-0575
    # 5. Autobús frontal amarillo + auto frontal vino (20261114T010037_321148Z_29a0e74bbe1e_orig.jpg) -> EV-0581
    # 6. Autobús frontal amarillo + auto rojo (20261114T010054_443040Z_bbf2d0cdf38b_orig.jpg) -> EV-0588
    # 7. Autobús frontal amarillo + auto rojo (20261116T172203_520604Z_e0c6c9b2989f_orig.jpg) -> EV-0671
    # 8. Autobús frontal oblicuo (20261116T172140_190972Z_c2499a3ef3d5_orig.jpg) -> EV-0665
    # 9. Automóvil frontal baja luz (20261114T004957_154790Z_2271be730b5b_orig.jpg) -> EV-0494

    test_cases = [
        ("EV-0635_car_frontal_cyan_pink", "20261116/CAM-SALIDA/20261116T172036_202643Z_df5e1071c00f_orig.jpg"),
        ("EV-0627_car_frontal_cyan", "20261116/CAM-SALIDA/20261116T172020_828094Z_dc015465e05a_orig.jpg"),
        ("EV-0637_car_frontal_pink", "20261116/CAM-SALIDA/20261116T172044_969280Z_957178f6e593_orig.jpg"),
        ("EV-0575_bus_frontal_hand", "20261114/CAM-SALIDA/20261114T010013_064537Z_07ac07b83576_orig.jpg"),
        ("EV-0581_bus_frontal_table", "20261114/CAM-SALIDA/20261114T010037_321148Z_29a0e74bbe1e_orig.jpg"),
        ("EV-0588_bus_frontal_redcar", "20261114/CAM-SALIDA/20261114T010054_443040Z_bbf2d0cdf38b_orig.jpg"),
        ("EV-0671_bus_frontal_20261116", "20261116/CAM-SALIDA/20261116T172203_520604Z_e0c6c9b2989f_orig.jpg"),
        ("EV-0665_bus_oblique_20261116", "20261116/CAM-SALIDA/20261116T172140_190972Z_c2499a3ef3d5_orig.jpg"),
        ("EV-0494_car_lowlight_20261114", "20261114/CAM-SALIDA/20261114T004957_154790Z_2271be730b5b_orig.jpg"),
    ]

    for label, rel in test_cases:
        img = cv2.imread(str(EVIDENCE_DIR / rel))
        print(f"\n--- {label} ({rel}) ---")
        print("  baseline (640, fp16, nms=False): ", run_single(m26, img, imgsz=640, half=True, nms=False))
        print("  fp32     (640, fp32, nms=False): ", run_single(m26, img, imgsz=640, half=False, nms=False))
        print("  imgsz=320(320, fp16, nms=False): ", run_single(m26, img, imgsz=320, half=True, nms=False))
        print("  imgsz=480(480, fp16, nms=False): ", run_single(m26, img, imgsz=480, half=True, nms=False))
        print("  imgsz=960(960, fp16, nms=False): ", run_single(m26, img, imgsz=960, half=True, nms=False))
        print("  imgsz=1280(1280,fp16,nms=False): ", run_single(m26, img, imgsz=1280, half=True, nms=False))
        print("  zoom_0.65(640, fp16, nms=False): ", run_single(m26, pad_zoom_out(img, 0.65), imgsz=640, half=True, nms=False))
        print("  clahe    (640, fp16, nms=False): ", run_single(m26, apply_clahe_bgr(img, 2.0), imgsz=640, half=True, nms=False))
        print("  unsharp  (640, fp16, nms=False): ", run_single(m26, apply_unsharp(img, 1.5, 1.5), imgsz=640, half=True, nms=False))

    # Also check if one2many branch (cv2/cv3) still exists on a fresh YOLO(W_26X) before fuse/AutoBackend
    fresh = YOLO(str(W_26X))
    head = fresh.model.model[-1]
    print("\n=== Fresh model head branches before predict ===")
    print("  end2end:", getattr(head, "end2end", None))
    print("  cv2:", type(getattr(head, "cv2", None)).__name__)
    print("  cv3:", type(getattr(head, "cv3", None)).__name__)
    print("  one2one_cv2:", type(getattr(head, "one2one_cv2", None)).__name__)
    print("  one2one_cv3:", type(getattr(head, "one2one_cv3", None)).__name__)


if __name__ == "__main__":
    main()
