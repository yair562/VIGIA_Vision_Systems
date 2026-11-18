"""
tests.unit.test_vision_05b_color_classifier
=========================================
Pruebas unitarias e integración modular para el clasificador de color vehicular
de VIGÍA Vision Systems (VIGÍA-VISION-05B).

Cobertura verificada:
1. Las 12 categorías canónicas (`WHITE`, `BLACK`, `GRAY`, `SILVER`, `RED`,
   `BLUE`, `GREEN`, `YELLOW`, `BROWN`, `ORANGE`, `OTHER`, `UNKNOWN`).
2. Criterios conservadores hacia `UNKNOWN`: color ambiguo, región insuficiente,
   reflejos especulares excesivos, baja iluminación severa, detección inválida.
3. Exclusión de fondo perimetral, cristales/parabrisas y neumáticos inferiores.
4. Normalizador (`VehicleColorNormalizer`) y carga centralizada (`VIGIA_COLOR_*`).
5. Inmutabilidad del frame y de `RawVehicleDetection`.
6. Tolerancia a fallos (`fail-safe`) dentro de `VisionEngineCoordinator`.
7. Compatibilidad real desacoplada con `YOLO26x`, `YOLO11n` e ingesta
   simultánea USB + móvil PUSH sobre evidencias reales de `evidencias_vigia/`.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional, Sequence
from unittest.mock import patch
from uuid import uuid4

import cv2
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from VIGIA_Core.domain.vision_result import VisionStatus
from VIGIA_Vision.capture.sources import MobilePushFrameBuffer
from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.config.topology_validator import (
    AreaConfigDTO,
    CameraConfigDTO,
    ITopologyConfigRepository,
    TopologyValidator,
)
from VIGIA_Vision.detection.color_classifier import (
    ColorClassificationStatus,
    VehicleColor,
    VehicleColorClassifier,
    VehicleColorConfig,
    VehicleColorNormalizer,
    VehicleColorResult,
    load_color_config_from_env,
)
from VIGIA_Vision.detection.models import BoundingBox, RawVehicleDetection
from VIGIA_Vision.detection.yolo_detector import (
    YoloDetectorConfig,
    YoloVehicleDetector,
    resolve_yolo_weights_path,
)
from VIGIA_Vision.runtime.coordinator import IVehicleDetector, VisionEngineCoordinator


def _make_synthetic_vehicle_frame(
    body_bgr: tuple[int, int, int],
    *,
    bg_bgr: tuple[int, int, int] = (145, 145, 145),
    metallic_sheen: bool = False,
    vehicle_w: int = 240,
    vehicle_h: int = 180,
) -> tuple[np.ndarray, BoundingBox]:
    """
    Construye un fotograma BGR realista de prueba con vehículo pintado,
    fondo contrastante perimetral, parabrisas superior oscuro y neumáticos negros.
    """
    fh, fw = vehicle_h + 120, vehicle_w + 120
    frame = np.full((fh, fw, 3), bg_bgr, dtype=np.uint8)
    x1, y1 = 60, 60
    x2, y2 = x1 + vehicle_w, y1 + vehicle_h
    crop = frame[y1:y2, x1:x2]

    # Zona principal de carrocería (22%..82% en Y, 10%..90% en X)
    by1, by2 = int(vehicle_h * 0.20), int(vehicle_h * 0.84)
    bx1, bx2 = int(vehicle_w * 0.08), int(vehicle_w * 0.92)
    crop[by1:by2, bx1:bx2] = body_bgr

    if metallic_sheen:
        # Gradiente especular realista de pintura metálica (sin saturar clipping)
        rows = np.linspace(-18.0, 22.0, by2 - by1, dtype=np.float32)[:, None, None]
        patched = np.clip(crop[by1:by2, bx1:bx2].astype(np.float32) + rows, 0, 244).astype(np.uint8)
        crop[by1:by2, bx1:bx2] = patched

    # Techo / banda de parabrisas oscuro (24%..38% en Y, 24%..76% en X)
    wy1, wy2 = int(vehicle_h * 0.24), int(vehicle_h * 0.39)
    wx1, wx2 = int(vehicle_w * 0.24), int(vehicle_w * 0.76)
    crop[wy1:wy2, wx1:wx2] = (28, 30, 32)

    # Neumáticos y franja inferior oscura (82%..98% en Y)
    crop[int(vehicle_h * 0.82) :, :] = (16, 16, 18)

    return frame, BoundingBox(x1, y1, x2, y2)


class _DummyTopoRepo(ITopologyConfigRepository):
    def __init__(self) -> None:
        self.id_ent = uuid4()
        self.id_sal = uuid4()
        self._cams = [
            CameraConfigDTO(self.id_ent, "CAM-ENTRADA", "USB Test", "usb://0", True),
            CameraConfigDTO(self.id_sal, "CAM-SALIDA", "Móvil PUSH Test", "push://cam-salida", True),
        ]
        self._areas = [
            AreaConfigDTO(uuid4(), self.id_ent, "AREA-ENT", "Entrada", "ENTRADA", 0.0, 0.0, 1.0, 1.0, True),
            AreaConfigDTO(uuid4(), self.id_sal, "AREA-SAL", "Salida", "SALIDA", 0.0, 0.0, 1.0, 1.0, True),
        ]

    def get_cameras(self):
        return self._cams

    def get_areas(self):
        return self._areas

    def get_all_cameras(self):
        return self._cams

    def get_all_vision_areas(self):
        return self._areas


class _StaticDetector(IVehicleDetector):
    def __init__(self, dets: Sequence[RawVehicleDetection]) -> None:
        self._dets = tuple(dets)

    def detect(self, frame: Any) -> Sequence[RawVehicleDetection]:
        return self._dets


class _FailingColorClassifier:
    def classify(
        self,
        frame: np.ndarray,
        bbox: BoundingBox,
        vehicle_class: Optional[str] = None,
        detection_confidence: Optional[float] = None,
    ) -> VehicleColorResult:
        raise RuntimeError("Error simulado interno de clasificación cromática")


class TestVehicleColorClassifierUnit(unittest.TestCase):
    """Pruebas unitarias exhaustivas de las 12 categorías y reglas conservadoras."""

    def setUp(self) -> None:
        self.clf = VehicleColorClassifier(VehicleColorConfig())

    def test_all_eleven_determined_color_categories(self) -> None:
        """Verifica clasificación correcta en las 11 categorías determinadas."""
        cases = [
            ("WHITE", (232, 234, 236), (65, 65, 65), False, VehicleColor.WHITE),
            ("BLACK", (38, 38, 40), (190, 190, 190), False, VehicleColor.BLACK),
            ("GRAY", (112, 114, 116), (225, 225, 225), False, VehicleColor.GRAY),
            ("SILVER", (184, 186, 190), (45, 45, 45), True, VehicleColor.SILVER),
            ("RED", (28, 30, 205), (140, 140, 140), False, VehicleColor.RED),
            ("BLUE", (200, 95, 25), (140, 140, 140), False, VehicleColor.BLUE),
            ("GREEN", (45, 165, 45), (140, 140, 140), False, VehicleColor.GREEN),
            ("YELLOW", (25, 205, 235), (70, 70, 70), False, VehicleColor.YELLOW),
            ("BROWN", (32, 66, 114), (200, 200, 200), False, VehicleColor.BROWN),
            ("ORANGE", (22, 128, 240), (90, 90, 90), False, VehicleColor.ORANGE),
            ("OTHER", (180, 115, 230), (140, 140, 140), False, VehicleColor.OTHER),
        ]
        for label, body_bgr, bg_bgr, metallic, expected in cases:
            with self.subTest(category=label):
                frame, bbox = _make_synthetic_vehicle_frame(
                    body_bgr=body_bgr,
                    bg_bgr=bg_bgr,
                    metallic_sheen=metallic,
                )
                res = self.clf.classify(frame, bbox, vehicle_class="AUTOMOVIL", detection_confidence=0.90)
                self.assertEqual(res.predominant_color, expected)
                self.assertEqual(res.status, ColorClassificationStatus.CLASSIFIED)
                self.assertGreaterEqual(res.confidence, 0.45)
                self.assertTrue(res.quality.is_sufficient)

    def test_ambiguous_split_color_returns_unknown(self) -> None:
        """Vehículo mitad azul y mitad rojo evita clasificación forzada -> UNKNOWN."""
        frame, bbox = _make_synthetic_vehicle_frame(body_bgr=(200, 80, 20))
        crop = frame[bbox.y_min : bbox.y_max, bbox.x_min : bbox.x_max]
        mid_x = crop.shape[1] // 2
        by1, by2 = int(crop.shape[0] * 0.20), int(crop.shape[0] * 0.82)
        crop[by1:by2, mid_x : int(crop.shape[1] * 0.90)] = (25, 25, 205)
        res = self.clf.classify(frame, bbox, vehicle_class="AUTOMOVIL", detection_confidence=0.88)
        self.assertEqual(res.predominant_color, VehicleColor.UNKNOWN)
        self.assertEqual(res.status, ColorClassificationStatus.AMBIGUOUS_COLOR)
        self.assertIn("AMBIGUOUS_TOP2_COLORS", res.quality.limitations)

    def test_small_or_partial_region_returns_insufficient_unknown(self) -> None:
        """Bounding box demasiado pequeño/parcial devuelve UNKNOWN."""
        frame = np.full((240, 320, 3), (30, 30, 200), dtype=np.uint8)
        tiny_bbox = BoundingBox(10, 10, 30, 28)  # 20x18 px
        res = self.clf.classify(frame, tiny_bbox, vehicle_class="AUTOMOVIL", detection_confidence=0.85)
        self.assertEqual(res.predominant_color, VehicleColor.UNKNOWN)
        self.assertEqual(res.status, ColorClassificationStatus.INSUFFICIENT_REGION)
        self.assertFalse(res.quality.is_sufficient)

    def test_excessive_glare_vs_moderate_glare(self) -> None:
        """Reflejo moderado penaliza confianza; reflejo severo devuelve UNKNOWN."""
        # Reflejo severo (> 75% de píxeles de carrocería quemados en [255, 255, 255])
        frame_sev, bbox_sev = _make_synthetic_vehicle_frame(body_bgr=(255, 255, 255), bg_bgr=(60, 60, 60))
        res_sev = self.clf.classify(frame_sev, bbox_sev, vehicle_class="AUTOMOVIL", detection_confidence=0.90)
        self.assertEqual(res_sev.predominant_color, VehicleColor.UNKNOWN)
        self.assertEqual(res_sev.status, ColorClassificationStatus.OVEREXPOSED_GLARE)
        self.assertIn("EXCESSIVE_SPECULAR_GLARE", res_sev.quality.limitations)

        # Reflejo moderado (~35%) sobre auto rojo -> reduce confianza respecto a limpio
        frame_clean, bbox_clean = _make_synthetic_vehicle_frame(body_bgr=(25, 25, 200))
        res_clean = self.clf.classify(frame_clean, bbox_clean, "AUTOMOVIL", 0.90)

        frame_glare = frame_clean.copy()
        crop_g = frame_glare[bbox_clean.y_min : bbox_clean.y_max, bbox_clean.x_min : bbox_clean.x_max]
        ch, cw = crop_g.shape[:2]
        crop_g[int(ch * 0.42) : int(ch * 0.65), int(cw * 0.25) : int(cw * 0.78)] = (254, 254, 254)
        res_glare = self.clf.classify(frame_glare, bbox_clean, "AUTOMOVIL", 0.90)
        self.assertEqual(res_glare.predominant_color, VehicleColor.RED)
        self.assertIn("MODERATE_SPECULAR_GLARE", res_glare.quality.limitations)
        self.assertLess(res_glare.confidence, res_clean.confidence)

    def test_low_illumination_returns_unknown_with_limitation(self) -> None:
        """Escena subexpuesta crítica devuelve UNKNOWN y registra LOW_AMBIENT_ILLUMINATION."""
        frame, bbox = _make_synthetic_vehicle_frame(body_bgr=(12, 12, 14), bg_bgr=(10, 10, 10))
        res = self.clf.classify(frame, bbox, "AUTOMOVIL", 0.85)
        self.assertEqual(res.predominant_color, VehicleColor.UNKNOWN)
        self.assertEqual(res.status, ColorClassificationStatus.LOW_ILLUMINATION)
        self.assertIn("LOW_AMBIENT_ILLUMINATION", res.quality.limitations)

    def test_invalid_detection_confidence_and_frame_rejected(self) -> None:
        """Detección con confianza insuficiente o frame inválido no clasifica."""
        frame, bbox = _make_synthetic_vehicle_frame(body_bgr=(200, 80, 20))
        res_low = self.clf.classify(frame, bbox, "AUTOMOVIL", detection_confidence=0.10)
        self.assertEqual(res_low.predominant_color, VehicleColor.UNKNOWN)
        self.assertEqual(res_low.status, ColorClassificationStatus.INVALID_DETECTION)

        res_bad_frame = self.clf.classify(np.zeros((100, 100), dtype=np.uint8), bbox, "AUTOMOVIL", 0.90)
        self.assertEqual(res_bad_frame.predominant_color, VehicleColor.UNKNOWN)
        self.assertEqual(res_bad_frame.status, ColorClassificationStatus.INVALID_DETECTION)

    def test_different_orientations_and_low_resolution_crop(self) -> None:
        """Soporta distintas relaciones de aspecto (frontal, lateral, autobús) y baja resolución."""
        for (vw, vh, cls_name) in [(90, 90, "AUTOMOVIL"), (160, 75, "AUTOBUS"), (40, 38, "AUTOMOVIL")]:
            frame, bbox = _make_synthetic_vehicle_frame(
                body_bgr=(30, 195, 225),
                vehicle_w=vw,
                vehicle_h=vh,
            )
            res = self.clf.classify(frame, bbox, vehicle_class=cls_name, detection_confidence=0.88)
            self.assertEqual(res.predominant_color, VehicleColor.YELLOW)
            if max(vw, vh) < 56:
                self.assertIn("LOW_RESOLUTION_CROP", res.quality.limitations)

    def test_inputs_are_never_mutated(self) -> None:
        """Verifica que el fotograma y RawVehicleDetection permanecen inmutables."""
        frame, bbox = _make_synthetic_vehicle_frame(body_bgr=(30, 30, 200))
        snapshot = frame.copy()
        raw_det = RawVehicleDetection(bbox=bbox, confidence=0.92, raw_label="car")
        raw_det_before = deepcopy(raw_det)

        _ = self.clf.classify(frame, raw_det.bbox, "AUTOMOVIL", raw_det.confidence)
        self.assertTrue(np.array_equal(frame, snapshot))
        self.assertEqual(raw_det, raw_det_before)

    def test_normalizer_and_centralized_env_config(self) -> None:
        """Verifica VehicleColorNormalizer y lectura centralizada VIGIA_COLOR_*."""
        self.assertEqual(VehicleColorNormalizer.normalize_label("gris"), VehicleColor.GRAY)
        self.assertEqual(VehicleColorNormalizer.normalize_label("plateado"), VehicleColor.SILVER)
        self.assertEqual(VehicleColorNormalizer.normalize_label("rojo"), VehicleColor.RED)
        self.assertEqual(VehicleColorNormalizer.normalize_label("desconocido"), VehicleColor.UNKNOWN)
        self.assertEqual(VehicleColorNormalizer.normalize_label(None), VehicleColor.UNKNOWN)

        with patch.dict(
            os.environ,
            {
                "VIGIA_COLOR_ENABLED": "true",
                "VIGIA_COLOR_MIN_CONFIDENCE": "0.52",
                "VIGIA_COLOR_MIN_MARGIN": "0.09",
                "VIGIA_COLOR_NORMALIZE_ILLUMINANT": "false",
            },
            clear=False,
        ):
            cfg = load_color_config_from_env()
            self.assertTrue(cfg.enabled)
            self.assertAlmostEqual(cfg.min_confidence_threshold, 0.52)
            self.assertAlmostEqual(cfg.min_margin_over_runner_up, 0.09)
            self.assertFalse(cfg.apply_illuminant_normalization)


class TestColorCoordinatorAndModelIntegration(unittest.TestCase):
    """Pruebas de integración controlada, fail-safe, YOLO26x/YOLO11n y USB+Móvil PUSH."""

    def test_coordinator_fail_safe_on_classifier_exception(self) -> None:
        """Si VehicleColorClassifier lanza una excepción, la detección vehicular NO se detiene."""
        src_ent = MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=10.0)
        src_sal = MobilePushFrameBuffer("CAM-SALIDA", ttl_seconds=10.0)
        frame, bbox = _make_synthetic_vehicle_frame(body_bgr=(30, 30, 200))
        det = RawVehicleDetection(bbox=bbox, confidence=0.91, raw_label="car")

        with tempfile.TemporaryDirectory(prefix="vigia_05b_err_") as tmpdir:
            coord = VisionEngineCoordinator(
                topology_validator=TopologyValidator(_DummyTopoRepo()),
                settings=VisionEngineSettings(
                    vehicle_confidence_threshold=0.70,
                    evidence_directory=Path(tmpdir),
                    save_annotated_evidence=False,
                ),
                detector=_StaticDetector([det]),
                sources={"CAM-ENTRADA": src_ent, "CAM-SALIDA": src_sal},
                color_classifier=_FailingColorClassifier(),
            )
            coord.initialize(open_sources=True)
            src_ent.push_frame(frame)
            env = coord.process_camera_step("CAM-ENTRADA", persist_as_new_event=False)

            self.assertIsNotNone(env)
            assert env is not None
            self.assertEqual(env.vision_result.status, VisionStatus.VEHICLE_DETECTED_NO_PLATE)
            self.assertTrue(env.vision_result.vehicle_detected)
            self.assertEqual(env.vision_result.vehicle_type_pred, "AUTOMOVIL")
            self.assertEqual(env.vision_result.vehicle_color_pred, "UNKNOWN")
            self.assertEqual(env.vision_result.vehicle_color_confidence, 0.0)
            self.assertIsNotNone(env.vehicle_color_result)
            self.assertEqual(env.vehicle_color_result.status, ColorClassificationStatus.CLASSIFIER_ERROR)
            metrics = coord.get_operational_metrics()
            self.assertEqual(metrics["color_classifier"]["error_total"], 1)

    def test_decoupled_compatibility_yolo26x_yolo11n_and_usb_mobile_push(self) -> None:
        """
        Verifica sobre evidencias reales de `evidencias_vigia/` que el mismo
        `VehicleColorClassifier` funciona con YOLO26x y YOLO11n y en ingesta
        simultánea USB + móvil PUSH.
        """
        evid_root = _REPO_ROOT / "evidencias_vigia"
        real_cases = [
            (
                "20261101/CAM-ENTRADA/20261101T191753_054288Z_1ffcf7df4fd0_orig.jpg",
                VehicleColor.BLUE,   # Autobús urbano azul
            ),
            (
                "20261104/CAM-ENTRADA/20261104T200530_515339Z_98cfa78a543c_orig.jpg",
                VehicleColor.RED,    # Auto rojo
            ),
            (
                "20261114/CAM-SALIDA/20261114T005953_150100Z_b8911e91fc8c_orig.jpg",
                VehicleColor.YELLOW, # Autobús escolar amarillo
            ),
            (
                "20261116/CAM-SALIDA/20261116T172046_659417Z_6f0944ab7505_orig.jpg",
                VehicleColor.OTHER,  # Convertible rosa/magenta
            ),
            (
                "20261114/CAM-SALIDA/20261114T004945_898871Z_b988770981b1_orig.jpg",
                VehicleColor.UNKNOWN, # Baja iluminación severa
            ),
        ]
        # Si el inventario o evidencias locales existen, validar con pesos reales
        for rel_p, _ in real_cases:
            if not (evid_root / rel_p).is_file():
                self.skipTest(f"Evidencia real no encontrada: {rel_p}")

        clf = VehicleColorClassifier(VehicleColorConfig())
        w26 = resolve_yolo_weights_path("experiments/yolo26x/weights/yolo26x.pt")
        w11 = resolve_yolo_weights_path("yolo11n.pt")
        if not Path(w26).is_file() or not Path(w11).is_file():
            self.skipTest("Pesos YOLO26x/YOLO11n no disponibles localmente.")

        import torch
        device = "cuda:0" if torch.cuda.is_available() else "cpu"

        det26 = YoloVehicleDetector(
            YoloDetectorConfig(
                model_path=w26,
                confidence_threshold=0.25,
                device=device,
                imgsz=640,
                quantize=16 if device.startswith("cuda") else None,
                nms=False,
            )
        )
        det11 = YoloVehicleDetector(
            YoloDetectorConfig(
                model_path=w11,
                confidence_threshold=0.25,
                device=device,
                imgsz=640,
            )
        )

        src_usb = MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=10.0)
        src_mob = MobilePushFrameBuffer("CAM-SALIDA", ttl_seconds=10.0)
        try:
            with tempfile.TemporaryDirectory(prefix="vigia_05b_real_") as tmpdir:
                coord26 = VisionEngineCoordinator(
                    topology_validator=TopologyValidator(_DummyTopoRepo()),
                    settings=VisionEngineSettings(
                        vehicle_confidence_threshold=0.50,
                        evidence_directory=Path(tmpdir),
                        save_annotated_evidence=False,
                    ),
                    detector=det26,
                    sources={"CAM-ENTRADA": src_usb, "CAM-SALIDA": src_mob},
                    color_classifier=clf,
                )
                coord26.initialize(open_sources=True)

                # Ingesta simultánea USB (autobús azul EV-0001) + Móvil PUSH (auto rojo EV-0446)
                img_bus = cv2.imread(str(evid_root / real_cases[0][0]))
                img_car = cv2.imread(str(evid_root / real_cases[1][0]))
                src_usb.push_frame(img_bus)
                src_mob.push_frame(img_car)

                env_usb = coord26.process_camera_step("CAM-ENTRADA", persist_as_new_event=False)
                env_mob = coord26.process_camera_step("CAM-SALIDA", persist_as_new_event=False)

                self.assertEqual(env_usb.vision_result.vehicle_color_pred, VehicleColor.BLUE.value)
                self.assertEqual(env_mob.vision_result.vehicle_color_pred, VehicleColor.RED.value)

                # Verificar también amarillo, rosa/OTHER y baja iluminación con YOLO26x y YOLO11n
                for rel_p, expected_color in real_cases:
                    img = cv2.imread(str(evid_root / rel_p))
                    dets26 = det26.detect(img)
                    self.assertTrue(len(dets26) >= 1, f"YOLO26x no detectó {rel_p}")
                    res26 = clf.classify(img, dets26[0].bbox, dets26[0].raw_label, dets26[0].confidence)
                    self.assertEqual(res26.predominant_color, expected_color, f"Mismatch YOLO26x en {rel_p}: {res26}")

                    dets11 = det11.detect(img)
                    if dets11:
                        res11 = clf.classify(img, dets11[0].bbox, dets11[0].raw_label, dets11[0].confidence)
                        self.assertEqual(res11.predominant_color, expected_color, f"Mismatch YOLO11n en {rel_p}: {res11}")
        finally:
            det26.unload()
            det11.unload()

    def test_multi_vehicle_independent_color_classification(self) -> None:
        """VISION-07B.1: Verifica que múltiples vehículos en ROI reciban clasificación independiente."""
        src_ent = MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=10.0)
        src_sal = MobilePushFrameBuffer("CAM-SALIDA", ttl_seconds=10.0)

        # Crear frame sintético con 2 vehículos distintos (Rojo y Azul)
        frame = np.full((480, 640, 3), (120, 120, 120), dtype=np.uint8)
        # Vehículo 1: Rojo en (40, 40, 180, 180)
        frame[40:180, 40:180] = (20, 20, 210)
        # Vehículo 2: Azul en (240, 40, 380, 180)
        frame[40:180, 240:380] = (210, 20, 20)

        bbox1 = BoundingBox(40, 40, 180, 180)
        bbox2 = BoundingBox(240, 40, 380, 180)
        det1 = RawVehicleDetection(bbox=bbox1, confidence=0.92, raw_label="car")
        det2 = RawVehicleDetection(bbox=bbox2, confidence=0.88, raw_label="car")

        clf = VehicleColorClassifier()
        with tempfile.TemporaryDirectory(prefix="vigia_07b1_multi_") as tmpdir:
            coord = VisionEngineCoordinator(
                topology_validator=TopologyValidator(_DummyTopoRepo()),
                settings=VisionEngineSettings(
                    vehicle_confidence_threshold=0.50,
                    evidence_directory=Path(tmpdir),
                    save_annotated_evidence=False,
                ),
                detector=_StaticDetector([det1, det2]),
                sources={"CAM-ENTRADA": src_ent, "CAM-SALIDA": src_sal},
                color_classifier=clf,
            )
            coord.initialize(open_sources=True)
            src_ent.push_frame(frame)
            env = coord.process_camera_step("CAM-ENTRADA", persist_as_new_event=False)

            self.assertIsNotNone(env)
            assert env is not None
            self.assertEqual(len(env.detections_in_roi), 2)
            # Verificación de vehículo 1 (Rojo)
            self.assertIsNotNone(env.detections_in_roi[0].color_result)
            self.assertEqual(env.detections_in_roi[0].color_result.predominant_color, VehicleColor.RED)
            # Verificación de vehículo 2 (Azul)
            self.assertIsNotNone(env.detections_in_roi[1].color_result)
            self.assertEqual(env.detections_in_roi[1].color_result.predominant_color, VehicleColor.BLUE)
            # Verificación de sobre y compatibilidad con vehículo primario
            self.assertEqual(env.vehicle_color_result.predominant_color, VehicleColor.RED)
            self.assertEqual(len(env.vehicle_color_results), 2)
            self.assertEqual(env.vehicle_color_results[0].predominant_color, VehicleColor.RED)
            self.assertEqual(env.vehicle_color_results[1].predominant_color, VehicleColor.BLUE)


if __name__ == "__main__":
    unittest.main()
