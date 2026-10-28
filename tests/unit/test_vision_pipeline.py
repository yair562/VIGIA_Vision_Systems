"""
tests.unit.test_vision_pipeline
===============================
Pruebas unitarias para VisionPipeline y su adaptación a VisionResult (Fase 2B).
Verifica compatibilidad con service.py y app.py sin requerir GPU, cámaras ni PyTorch.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Asegurar rutas en sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_VR_DIR = _REPO_ROOT / "VR_Semaforo"
for p in (_REPO_ROOT, _VR_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from VIGIA_Core.domain.vision_result import VisionResult, VisionStatus
from vision.pipeline import VisionPipeline, VisionPipelineResult
from vision.camera import CameraCapture, set_default_camera
from vision.service import process_pc_capture


class TestVisionPipeline(unittest.TestCase):
    def setUp(self):
        # Frame sintético simulado (dummy object o array)
        self.dummy_frame = object()

    def test_import_pipeline_does_not_load_yolo_nor_hardware(self):
        """2. Importar vision.pipeline no carga YOLO ni adquiere hardware."""
        import vision.pipeline as p_module
        self.assertTrue(hasattr(p_module, "VisionPipeline"))
        # Al instanciar con detector inyectado, processor.py no debe ser requerido
        pipe = VisionPipeline(detector=lambda f, **kw: 0)
        self.assertIsNotNone(pipe)

    def test_null_frame_produces_camera_error(self):
        """Un frame nulo produce CAMERA_ERROR y vehicle_detected=False."""
        pipe = VisionPipeline(detector=lambda f, **kw: 5)
        res = pipe.process(None)

        self.assertIsInstance(res, VisionPipelineResult)
        self.assertEqual(res.status, VisionStatus.CAMERA_ERROR)
        self.assertFalse(res.vehicle_detected)
        self.assertEqual(res.vehicle_count, 0)
        self.assertIn("Camera frame could not be captured", res.error)
        # Invariante canónica: error técnico no puede tener vehicle_detected=True
        self.assertFalse(res.canonical.vehicle_detected)
        self.assertEqual(res.canonical.status, VisionStatus.CAMERA_ERROR)

    def test_absence_of_vehicles_produces_coherent_state(self):
        """4. La ausencia de vehículos produce NO_VEHICLE_DETECTED, vehicle_count=0."""
        # Detector simulado que retorna 0 vehículos
        mock_detector = MagicMock(return_value=0)
        pipe = VisionPipeline(detector=mock_detector)

        res = pipe.process(self.dummy_frame)

        self.assertEqual(res.status, VisionStatus.NO_VEHICLE_DETECTED)
        self.assertFalse(res.vehicle_detected)
        self.assertEqual(res.vehicle_count, 0)
        self.assertEqual(res.vehicles, [])
        self.assertIsNone(res.canonical.vehicle_confidence)
        self.assertFalse(res.canonical.plate_located)
        self.assertIsNone(res.canonical.plate_text)

    def test_detection_produces_valid_vision_result(self):
        """3 y 5. Una detección produce VisionResult respetando las invariantes del dominio."""
        # Simular salida completa de contar_carritos con dibujar=True: (cantidad, frame_anotado, boxes)
        mock_annotated = object()
        mock_boxes = [(10, 20, 100, 150), (200, 250, 80, 90)]
        mock_detector = MagicMock(return_value=(2, mock_annotated, mock_boxes))

        pipe = VisionPipeline(detector=mock_detector)
        res = pipe.process(self.dummy_frame, draw=True)

        # Validación del adaptador
        self.assertEqual(res.vehicle_count, 2)
        self.assertTrue(res.vehicle_detected)
        self.assertEqual(res.status, VisionStatus.VEHICLE_DETECTED_NO_PLATE)
        self.assertIs(res.annotated_frame, mock_annotated)

        # Validación estricta del contrato canónico inmutable VisionResult
        canonical = res.canonical
        self.assertIsInstance(canonical, VisionResult)
        self.assertEqual(canonical.status, VisionStatus.VEHICLE_DETECTED_NO_PLATE)
        self.assertTrue(canonical.vehicle_detected)
        self.assertFalse(canonical.plate_located)
        self.assertIsNone(canonical.plate_text)
        self.assertIsNone(canonical.plate_confidence)
        self.assertIsNone(canonical.error_message)
        self.assertFalse(canonical.is_technical_error)
        self.assertTrue(canonical.requires_guard_review)

    def test_detector_error_is_handled_as_vision_error(self):
        """6. Un error del detector produce VISION_ERROR y no una detección exitosa."""
        def broken_detector(frame, **kw):
            raise RuntimeError("CUDA Out of Memory o fallo interno de tensor")

        pipe = VisionPipeline(detector=broken_detector)
        res = pipe.process(self.dummy_frame)

        self.assertEqual(res.status, VisionStatus.VISION_ERROR)
        self.assertFalse(res.vehicle_detected)
        self.assertEqual(res.vehicle_count, 0)
        self.assertIn("CUDA Out of Memory", res.error)
        # Invariante canónica: VISION_ERROR no puede tener vehicle_detected=True
        self.assertFalse(res.canonical.vehicle_detected)
        self.assertEqual(res.canonical.status, VisionStatus.VISION_ERROR)

    def test_output_compatibility_with_service_and_app(self):
        """7. La salida mantiene compatibilidad con las estructuras esperadas por service.py y app.py."""
        mock_boxes = [(100, 150, 50, 60)]
        mock_detector = MagicMock(return_value=(1, object(), mock_boxes))

        pipe = VisionPipeline(detector=mock_detector)
        res = pipe.process(self.dummy_frame, draw=True)

        d = res.to_dict()
        # Claves esperadas por service.py
        self.assertIn("status", d)
        self.assertIn("vehicle_detected", d)
        self.assertIn("vehicle_count", d)
        self.assertIn("vehicles", d)
        self.assertEqual(d["vehicle_count"], 1)

        # Estructura de boxes esperada por app.py: [vehicle["vehicle_bbox"] for vehicle in d["vehicles"]]
        self.assertEqual(len(d["vehicles"]), 1)
        self.assertIn("vehicle_bbox", d["vehicles"][0])
        bbox = d["vehicles"][0]["vehicle_bbox"]
        self.assertEqual(bbox, {"x": 100, "y": 150, "w": 50, "h": 60})

    def test_service_integration_with_simulated_camera_and_pipeline(self):
        """Integración de process_pc_capture() en service.py con cámara y pipeline simulados."""
        # 1. Caso con frame capturado exitosamente
        mock_cam = MagicMock(spec=CameraCapture)
        mock_cam.read_frame.return_value = (True, self.dummy_frame)
        set_default_camera(mock_cam)

        mock_detector = MagicMock(return_value=(3, object(), [(0, 0, 10, 10)] * 3))
        pipe = VisionPipeline(detector=mock_detector)

        resultado = process_pc_capture(pipeline=pipe)

        self.assertEqual(resultado["vehiculos"], 3)
        self.assertIn("estado", resultado)
        self.assertIn("tiempo_verde_segundos", resultado)
        self.assertIn("vision", resultado)
        self.assertEqual(resultado["vision"]["vehicle_count"], 3)
        self.assertEqual(resultado["vision"]["status"], "VEHICLE_DETECTED_NO_PLATE")

        # 2. Caso con fallo de cámara (frame is None)
        mock_cam.read_frame.return_value = (False, None)
        resultado_fallo = process_pc_capture(pipeline=pipe)

        self.assertEqual(resultado_fallo["vehiculos"], 0)
        self.assertEqual(resultado_fallo["vision"]["status"], "TECHNICAL_ERROR")
        self.assertFalse(resultado_fallo["vision"]["vehicle_detected"])

        set_default_camera(None)


if __name__ == "__main__":
    unittest.main()
