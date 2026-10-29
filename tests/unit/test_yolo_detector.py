"""
tests.unit.test_yolo_detector
=============================
Pruebas unitarias para el detector vehicular YOLO (SPRINT-02).

Cobertura de pruebas:
- PU-YOLO-01: Carga perezosa (lazy loading) e inicialización libre de efectos secundarios.
- PU-YOLO-02: Validación e inmutabilidad de la configuración YoloDetectorConfig.
- PU-YOLO-03: Rechazo de fotogramas inválidos con FrameValidationError.
- PU-YOLO-04: Parseo de detección unitaria y redondeo/clamping de BoundingBox.
- PU-YOLO-05: Mapeo y detección múltiple de las 4 clases vehiculares COCO (car, motorcycle, bus, truck).
- PU-YOLO-06: Descarte de clases no vehiculares (personas, bicicletas, semáforos, etc.).
- PU-YOLO-07: Filtrado estricto por umbral de confianza.
- PU-YOLO-08: Manejo seguro de fotogramas sin detecciones (retorna tupla vacía).
- PU-YOLO-09: Descarte de cajas delimitadoras degeneradas o invertidas tras clamping.
- PU-YOLO-10: Fallo de carga de modelo lanza ModelLoadError.
- PU-YOLO-11: Fallo de inferencia predictiva lanza InferenceError.
- PU-YOLO-12: Seguridad en concurrencia multihilo para la carga perezosa.
- PU-YOLO-13: Integración fluida con VisionEngineCoordinator como IVehicleDetector.
- PU-YOLO-14: Verificación de preservación e integridad de NullVehicleDetector.
- PU-YOLO-15: Inferencia real con pesos YOLO e imagen local en CPU.
"""

from __future__ import annotations

import os
import sys
import threading
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, List, Optional, Sequence
from uuid import uuid4

import numpy as np

# Asegurar raíz del repositorio en sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from VIGIA_Core.domain.vision_result import VisionStatus
from VIGIA_Vision.config.topology_validator import (
    AreaConfigDTO,
    CameraConfigDTO,
    ITopologyConfigRepository,
    OperationalTopologyDTO,
    TopologyValidator,
)
from VIGIA_Vision.detection.models import BoundingBox, RawVehicleDetection
from VIGIA_Vision.detection.roi_and_preprocess import FrameValidationError
from VIGIA_Vision.detection.yolo_detector import (
    COCO_VEHICLE_CLASSES,
    InferenceError,
    ModelLoadError,
    YoloDetectorConfig,
    YoloVehicleDetector,
)
from VIGIA_Vision.runtime.coordinator import (
    IVehicleDetector,
    NullVehicleDetector,
    VisionEngineCoordinator,
)


class MockBox:
    """Doble de prueba para simular una caja de detección Ultralytics."""

    def __init__(self, xyxy: Sequence[float], conf: float, cls: int) -> None:
        self.xyxy = np.array([xyxy], dtype=np.float32)
        self.conf = np.array([conf], dtype=np.float32)
        self.cls = np.array([cls], dtype=np.float32)


class MockResult:
    """Doble de prueba para simular el objeto Results retornado por YOLO.predict()."""

    def __init__(self, boxes: Optional[Sequence[MockBox]] = None) -> None:
        self.boxes = list(boxes) if boxes is not None else []


class MockYOLOModel:
    """Doble de prueba para el modelo YOLO desacoplado de dependencias externas."""

    def __init__(
        self,
        results_to_return: Optional[Sequence[Any]] = None,
        should_raise: bool = False,
    ) -> None:
        self.results_to_return = list(results_to_return) if results_to_return is not None else []
        self.should_raise = should_raise
        self.predict_calls: List[dict] = []

    def predict(self, **kwargs) -> List[Any]:
        if self.should_raise:
            raise RuntimeError("Inference engine internal error")
        self.predict_calls.append(kwargs)
        return self.results_to_return


class FakeTopologyRepo(ITopologyConfigRepository):
    """Repositorio de prueba para suministrar topología a VisionEngineCoordinator."""

    def __init__(self, topology: OperationalTopologyDTO) -> None:
        self.topology = topology

    def get_operational_topology(self) -> OperationalTopologyDTO:
        return self.topology


class TestYoloDetectorDecoupled(unittest.TestCase):
    """Pruebas unitarias totalmente desacopladas (sin GPU, disco ni red)."""

    def setUp(self) -> None:
        self.frame_640x480 = np.zeros((480, 640, 3), dtype=np.uint8)

    def test_pu_yolo_01_lazy_loading(self) -> None:
        """PU-YOLO-01: Instanciar YoloVehicleDetector no carga el modelo hasta invocar detect()."""
        factory_called = False

        def spy_factory(path):
            nonlocal factory_called
            factory_called = True
            return MockYOLOModel()

        detector = YoloVehicleDetector(
            config=YoloDetectorConfig(model_path="dummy.pt"),
            model_factory=spy_factory,
        )
        self.assertFalse(detector.is_loaded)
        self.assertFalse(factory_called)

        # Cargar explícitamente o via detect()
        detector.detect(self.frame_640x480)
        self.assertTrue(detector.is_loaded)
        self.assertTrue(factory_called)

    def test_pu_yolo_02_config_validation_and_immutability(self) -> None:
        """PU-YOLO-02: Validación de parámetros e inmutabilidad de YoloDetectorConfig."""
        cfg = YoloDetectorConfig()
        self.assertEqual(cfg.confidence_threshold, 0.25)
        self.assertEqual(cfg.device, "cpu")
        self.assertEqual(cfg.imgsz, 640)
        self.assertEqual(cfg.iou_threshold, 0.45)
        self.assertEqual(cfg.classes, (2, 3, 5, 7))

        # Inmutabilidad
        with self.assertRaises(FrozenInstanceError):
            cfg.confidence_threshold = 0.50  # type: ignore

        # Validaciones de umbrales inválidos
        with self.assertRaises(ValueError):
            YoloDetectorConfig(confidence_threshold=-0.1)
        with self.assertRaises(ValueError):
            YoloDetectorConfig(confidence_threshold=1.1)
        with self.assertRaises(ValueError):
            YoloDetectorConfig(confidence_threshold=True)  # bool no permitido

        with self.assertRaises(ValueError):
            YoloDetectorConfig(iou_threshold=-0.05)
        with self.assertRaises(ValueError):
            YoloDetectorConfig(iou_threshold=1.05)

        with self.assertRaises(ValueError):
            YoloDetectorConfig(imgsz=0)
        with self.assertRaises(ValueError):
            YoloDetectorConfig(imgsz=-640)

        with self.assertRaises(ValueError):
            YoloDetectorConfig(device="")
        with self.assertRaises(ValueError):
            YoloDetectorConfig(model_path="")
        with self.assertRaises(ValueError):
            YoloDetectorConfig(classes=())
        with self.assertRaises(ValueError):
            YoloDetectorConfig(classes=(-1,))

    def test_pu_yolo_03_frame_validation(self) -> None:
        """PU-YOLO-03: Rechazo de fotogramas inválidos con FrameValidationError."""
        detector = YoloVehicleDetector(model_factory=lambda _: MockYOLOModel())

        with self.assertRaises(FrameValidationError):
            detector.detect(None)  # type: ignore

        # 2D (escala de grises)
        with self.assertRaises(FrameValidationError):
            detector.detect(np.zeros((480, 640), dtype=np.uint8))

        # 4 canales (BGRA)
        with self.assertRaises(FrameValidationError):
            detector.detect(np.zeros((480, 640, 4), dtype=np.uint8))

        # Tipo float32
        with self.assertRaises(FrameValidationError):
            detector.detect(np.zeros((480, 640, 3), dtype=np.float32))

        # Dimensiones cero
        with self.assertRaises(FrameValidationError):
            detector.detect(np.zeros((0, 0, 3), dtype=np.uint8))

    def test_pu_yolo_04_single_detection_parsing_and_clamping(self) -> None:
        """PU-YOLO-04: Parseo de coordenadas, redondeo, clamping a límites del frame y mapeo."""
        # Caja con coordenadas que rebasan límites y tienen decimales
        # Frame es 640x480 (width=640, height=480)
        mock_box = MockBox(xyxy=[-15.7, -5.2, 700.3, 500.8], conf=0.88, cls=2)
        mock_model = MockYOLOModel([MockResult([mock_box])])

        detector = YoloVehicleDetector(model_factory=lambda _: mock_model)
        detections = detector.detect(self.frame_640x480)

        self.assertEqual(len(detections), 1)
        det = detections[0]
        self.assertEqual(det.raw_label, "car")
        self.assertAlmostEqual(det.confidence, 0.88, places=2)
        # Clamped: x_min=0, y_min=0, x_max=640, y_max=480
        self.assertEqual(det.bbox.x_min, 0)
        self.assertEqual(det.bbox.y_min, 0)
        self.assertEqual(det.bbox.x_max, 640)
        self.assertEqual(det.bbox.y_max, 480)

    def test_pu_yolo_05_all_vehicle_classes_mapped(self) -> None:
        """PU-YOLO-05: Detección y mapeo correcto de las 4 clases COCO vehiculares."""
        boxes = [
            MockBox(xyxy=[10, 10, 50, 50], conf=0.90, cls=2),  # car
            MockBox(xyxy=[60, 60, 90, 90], conf=0.85, cls=3),  # motorcycle
            MockBox(xyxy=[100, 100, 250, 250], conf=0.92, cls=5),  # bus
            MockBox(xyxy=[300, 200, 450, 400], conf=0.87, cls=7),  # truck
        ]
        mock_model = MockYOLOModel([MockResult(boxes)])
        detector = YoloVehicleDetector(model_factory=lambda _: mock_model)
        detections = detector.detect(self.frame_640x480)

        self.assertEqual(len(detections), 4)
        labels = [d.raw_label for d in detections]
        self.assertEqual(labels, ["car", "motorcycle", "bus", "truck"])

    def test_pu_yolo_06_non_vehicle_classes_filtered_out(self) -> None:
        """PU-YOLO-06: Personas, bicicletas, semáforos y animales son descartados."""
        boxes = [
            MockBox(xyxy=[10, 10, 50, 50], conf=0.95, cls=0),  # person
            MockBox(xyxy=[60, 60, 90, 90], conf=0.89, cls=1),  # bicycle
            MockBox(xyxy=[100, 100, 250, 250], conf=0.91, cls=2),  # car (válido)
            MockBox(xyxy=[260, 100, 300, 150], conf=0.85, cls=9),  # traffic light
            MockBox(xyxy=[310, 100, 350, 150], conf=0.75, cls=16),  # dog
        ]
        mock_model = MockYOLOModel([MockResult(boxes)])
        detector = YoloVehicleDetector(model_factory=lambda _: mock_model)
        detections = detector.detect(self.frame_640x480)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].raw_label, "car")

    def test_pu_yolo_07_confidence_threshold_filtering(self) -> None:
        """PU-YOLO-07: Las detecciones bajo el umbral de confianza son descartadas."""
        boxes = [
            MockBox(xyxy=[10, 10, 50, 50], conf=0.20, cls=2),  # bajo umbral (0.25)
            MockBox(xyxy=[60, 60, 90, 90], conf=0.25, cls=2),  # en umbral exacto
            MockBox(xyxy=[100, 100, 150, 150], conf=0.75, cls=2),  # sobre umbral
        ]
        mock_model = MockYOLOModel([MockResult(boxes)])
        detector = YoloVehicleDetector(
            config=YoloDetectorConfig(confidence_threshold=0.25),
            model_factory=lambda _: mock_model,
        )
        detections = detector.detect(self.frame_640x480)

        self.assertEqual(len(detections), 2)
        confs = [d.confidence for d in detections]
        self.assertEqual(confs, [0.25, 0.75])

    def test_pu_yolo_08_zero_detections_returns_empty_tuple(self) -> None:
        """PU-YOLO-08: Cuando no hay detecciones, retorna tupla vacía sin errores."""
        mock_model = MockYOLOModel([MockResult([])])
        detector = YoloVehicleDetector(model_factory=lambda _: mock_model)
        detections = detector.detect(self.frame_640x480)

        self.assertEqual(detections, ())
        self.assertIsInstance(detections, tuple)

        # También si predict() retorna lista vacía
        mock_model_empty = MockYOLOModel([])
        detector_empty = YoloVehicleDetector(model_factory=lambda _: mock_model_empty)
        self.assertEqual(detector_empty.detect(self.frame_640x480), ())

    def test_pu_yolo_09_degenerate_boxes_skipped(self) -> None:
        """PU-YOLO-09: Cajas degeneradas (ancho <= 0 o alto <= 0 tras clamping) son omitidas."""
        boxes = [
            MockBox(xyxy=[50, 50, 50, 50], conf=0.90, cls=2),  # x1 == x2
            MockBox(xyxy=[60, 70, 80, 70], conf=0.90, cls=2),  # y1 == y2
            MockBox(xyxy=[-20, -20, -10, -10], conf=0.90, cls=2),  # completamente fuera a la izq/arriba
            MockBox(xyxy=[10, 10, 100, 100], conf=0.90, cls=2),  # válida
        ]
        mock_model = MockYOLOModel([MockResult(boxes)])
        detector = YoloVehicleDetector(model_factory=lambda _: mock_model)
        detections = detector.detect(self.frame_640x480)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].bbox.width, 90)

    def test_pu_yolo_10_model_load_failure_raises_model_load_error(self) -> None:
        """PU-YOLO-10: Excepciones al cargar pesos lanzan ModelLoadError estructurado."""
        def failing_factory(path):
            raise FileNotFoundError(f"Model file {path} not found")

        detector = YoloVehicleDetector(
            config=YoloDetectorConfig(model_path="missing_weights.pt"),
            model_factory=failing_factory,
        )
        with self.assertRaises(ModelLoadError) as ctx:
            detector.load_model()
        self.assertIn("Fallo al instanciar el modelo", str(ctx.exception))

    def test_pu_yolo_11_inference_failure_raises_inference_error(self) -> None:
        """PU-YOLO-11: Fallo en runtime durante predict() lanza InferenceError."""
        failing_model = MockYOLOModel(should_raise=True)
        detector = YoloVehicleDetector(model_factory=lambda _: failing_model)

        with self.assertRaises(InferenceError) as ctx:
            detector.detect(self.frame_640x480)
        self.assertIn("Error durante la inferencia YOLO", str(ctx.exception))

    def test_pu_yolo_12_thread_safe_lazy_loading(self) -> None:
        """PU-YOLO-12: Múltiples hilos invocando load_model() solo ejecutan la fábrica una vez."""
        factory_calls = 0
        call_lock = threading.Lock()

        def slow_factory(path):
            nonlocal factory_calls
            with call_lock:
                factory_calls += 1
            import time
            time.sleep(0.01)
            return MockYOLOModel()

        detector = YoloVehicleDetector(model_factory=slow_factory)

        threads = []
        for _ in range(8):
            t = threading.Thread(target=detector.load_model)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(factory_calls, 1)
        self.assertTrue(detector.is_loaded)

    def test_pu_yolo_13_integration_with_vision_engine_coordinator(self) -> None:
        """PU-YOLO-13: Inyección en VisionEngineCoordinator detecta vehículo y actualiza VisionResult."""
        cam_ent_id = uuid4()
        cam_sal_id = uuid4()
        area_ent_id = uuid4()
        area_sal_id = uuid4()

        cam_ent = CameraConfigDTO(
            id_camara=cam_ent_id,
            codigo="CAM-ENTRADA",
            nombre="Cámara Entrada",
            uri_stream="push://cam-entrada",
            activa=True,
        )
        cam_sal = CameraConfigDTO(
            id_camara=cam_sal_id,
            codigo="CAM-SALIDA",
            nombre="Cámara Salida",
            uri_stream="push://cam-salida",
            activa=True,
        )
        area_ent = AreaConfigDTO(
            id_area_vision=area_ent_id,
            id_camara=cam_ent_id,
            codigo="ROI-ENT",
            nombre="ROI Entrada",
            tipo_movimiento="ENTRADA",
            x_min=0.1,
            y_min=0.1,
            x_max=0.9,
            y_max=0.9,
            activa=True,
        )
        area_sal = AreaConfigDTO(
            id_area_vision=area_sal_id,
            id_camara=cam_sal_id,
            codigo="ROI-SAL",
            nombre="ROI Salida",
            tipo_movimiento="SALIDA",
            x_min=0.1,
            y_min=0.1,
            x_max=0.9,
            y_max=0.9,
            activa=True,
        )

        class MockRepo(ITopologyConfigRepository):
            def get_cameras(self):
                return [cam_ent, cam_sal]
            def get_areas(self):
                return [area_ent, area_sal]

        validator = TopologyValidator(repository=MockRepo())

        # Mock YOLO model que detecta un automóvil centrado en el ROI
        # Frame es 640x480. ROI: x in [64, 576], y in [48, 432]
        # Auto centrado en x=300, y=200
        box = MockBox(xyxy=[250, 150, 350, 250], conf=0.88, cls=2)  # car
        mock_model = MockYOLOModel([MockResult([box])])
        yolo_detector = YoloVehicleDetector(model_factory=lambda _: mock_model)

        from VIGIA_Vision.capture.sources import MobilePushFrameBuffer

        buf_ent = MobilePushFrameBuffer("CAM-ENTRADA")
        buf_sal = MobilePushFrameBuffer("CAM-SALIDA")
        buf_ent.open()
        buf_sal.open()
        buf_ent.push_frame(self.frame_640x480)

        coordinator = VisionEngineCoordinator(
            topology_validator=validator,
            detector=yolo_detector,
            sources={"CAM-ENTRADA": buf_ent, "CAM-SALIDA": buf_sal},
        )
        coordinator.initialize()

        envelope = coordinator.process_camera_step("CAM-ENTRADA")
        self.assertIsNotNone(envelope)
        self.assertEqual(envelope.vision_result.status, VisionStatus.VEHICLE_DETECTED_NO_PLATE)
        self.assertTrue(envelope.vision_result.vehicle_detected)
        self.assertEqual(envelope.vision_result.vehicle_type_pred, "AUTOMOVIL")
        self.assertAlmostEqual(envelope.vision_result.vehicle_confidence, 0.88, places=2)
        self.assertEqual(envelope.metrics.in_roi_now, 1)

    def test_pu_yolo_14_null_vehicle_detector_intact(self) -> None:
        """PU-YOLO-14: NullVehicleDetector mantiene su comportamiento y cumple IVehicleDetector."""
        null_detector = NullVehicleDetector()
        self.assertIsInstance(null_detector, IVehicleDetector)
        self.assertEqual(null_detector.detect(self.frame_640x480), ())


class TestYoloRealInference(unittest.TestCase):
    """
    Prueba de inferencia real en CPU con pesos YOLO preentrenados y muestra de imagen.
    """

    def test_pu_yolo_15_real_inference_on_sample_image(self) -> None:
        """PU-YOLO-15: Inferencia real con yolo11n.pt sobre imagen de prueba en CPU."""
        # Localizar pesos disponibles en raíz o variable de entorno
        repo_root = Path(__file__).resolve().parent.parent.parent
        env_weights = os.environ.get("VIGIA_YOLO_WEIGHTS")
        candidate_weights = [
            Path(env_weights) if env_weights else None,
            repo_root / "yolo11n.pt",
            repo_root / "models" / "yolo11n.pt",
        ]
        weights_path = next((p for p in candidate_weights if p is not None and p.exists()), None)
        if weights_path is None:
            self.skipTest("Archivo de pesos yolo11n.pt no encontrado para prueba real.")

        try:
            import ultralytics
            import cv2
        except ImportError:
            self.skipTest("ultralytics o opencv no instalados en el entorno.")

        # Localizar imagen de prueba estándar incluida en assets de Ultralytics
        assets_dir = Path(ultralytics.__file__).parent / "assets"
        bus_image_path = assets_dir / "bus.jpg"
        if not bus_image_path.exists():
            self.skipTest("Imagen de muestra bus.jpg no encontrada en assets de ultralytics.")

        frame = cv2.imread(str(bus_image_path))
        self.assertIsNotNone(frame, "No se pudo leer bus.jpg con OpenCV.")

        # Configurar detector con modelo real en CPU
        config = YoloDetectorConfig(
            model_path=str(weights_path),
            confidence_threshold=0.25,
            device="cpu",
            imgsz=640,
        )
        detector = YoloVehicleDetector(config=config)

        self.assertFalse(detector.is_loaded, "El detector no debería estar cargado antes de detect().")

        # Ejecutar inferencia real
        detections = detector.detect(frame)

        self.assertTrue(detector.is_loaded, "El detector debe reportar is_loaded=True tras detect().")
        self.assertGreaterEqual(len(detections), 1, "Debe detectar al menos un vehículo en bus.jpg.")

        # Verificar que la detección es un autobús
        labels = [d.raw_label for d in detections]
        self.assertIn("bus", labels, "El vehículo detectado debe incluir la clase 'bus'.")

        # Verificar invariantes de la detección
        bus_det = next(d for d in detections if d.raw_label == "bus")
        self.assertGreaterEqual(bus_det.confidence, 0.70)
        self.assertGreater(bus_det.bbox.width, 0)
        self.assertGreater(bus_det.bbox.height, 0)
        self.assertGreaterEqual(bus_det.bbox.x_min, 0)
        self.assertLessEqual(bus_det.bbox.x_max, frame.shape[1])
        self.assertGreaterEqual(bus_det.bbox.y_min, 0)
        self.assertLessEqual(bus_det.bbox.y_max, frame.shape[0])

        # Verificar que las personas presentes en bus.jpg fueron filtradas
        self.assertNotIn("person", labels)


if __name__ == "__main__":
    unittest.main()
