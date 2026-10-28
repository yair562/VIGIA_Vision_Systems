"""
tests.unit.test_camera
======================
Pruebas unitarias para la abstracción de captura de cámara desacoplada (Fase 2B).
Verifica que la importación no adquiere hardware y que las operaciones son explícitas.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Asegurar rutas en sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_VR_DIR = _REPO_ROOT / "VR_Semaforo"
for p in (_REPO_ROOT, _VR_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import vision.camera as camera_module
from vision.camera import CameraCapture, get_default_camera, set_default_camera, capture_pc


class TestCameraDecoupling(unittest.TestCase):
    def setUp(self):
        set_default_camera(None)

    def tearDown(self):
        set_default_camera(None)

    def test_import_does_not_open_camera(self):
        """1. Importar vision.camera no abre la cámara ni invoca VideoCapture en importación."""
        self.assertFalse(hasattr(camera_module, "cam"), "camera.py no debe tener variable global 'cam'")
        cam = get_default_camera()
        self.assertFalse(cam.is_opened(), "La cámara por omisión no debe estar abierta al instanciarse")

    def test_camera_capture_instantiation_does_not_open_hardware(self):
        """CameraCapture(0) no adquiere hardware en __init__."""
        capture = CameraCapture(0)
        self.assertFalse(capture.is_opened())
        self.assertIsNone(capture._cap)

    @patch("vision.camera.cv2")
    def test_explicit_open_and_release(self, mock_cv2):
        """8. La apertura y liberación tienen un ciclo de vida explícito y liberan recursos."""
        mock_cap_instance = MagicMock()
        mock_cap_instance.isOpened.return_value = True
        mock_cv2.VideoCapture.return_value = mock_cap_instance

        capture = CameraCapture(0)
        self.assertTrue(capture.open())
        mock_cv2.VideoCapture.assert_called_once_with(0)
        self.assertTrue(capture.is_opened())

        capture.release()
        mock_cap_instance.release.assert_called_once()
        self.assertFalse(capture.is_opened())
        self.assertIsNone(capture._cap)

    @patch("vision.camera.cv2")
    def test_read_frame_success(self, mock_cv2):
        """read_frame() retorna (True, frame) cuando la lectura tiene éxito."""
        mock_cap_instance = MagicMock()
        mock_cap_instance.isOpened.return_value = True
        dummy_frame = object()
        mock_cap_instance.read.return_value = (True, dummy_frame)
        mock_cv2.VideoCapture.return_value = mock_cap_instance

        capture = CameraCapture(0)
        success, frame = capture.read_frame()

        self.assertTrue(success)
        self.assertIs(frame, dummy_frame)

    @patch("vision.camera.cv2")
    def test_read_frame_failure_reports_cleanly(self, mock_cv2):
        """read_frame() retorna (False, None) si la captura falla sin lanzar excepciones."""
        mock_cap_instance = MagicMock()
        mock_cap_instance.isOpened.return_value = True
        mock_cap_instance.read.return_value = (False, None)
        mock_cv2.VideoCapture.return_value = mock_cap_instance

        capture = CameraCapture(0)
        success, frame = capture.read_frame()

        self.assertFalse(success)
        self.assertIsNone(frame)

    @patch("vision.camera.cv2")
    def test_context_manager(self, mock_cv2):
        """El context manager abre y libera el recurso automáticamente."""
        mock_cap_instance = MagicMock()
        mock_cap_instance.isOpened.return_value = True
        mock_cv2.VideoCapture.return_value = mock_cap_instance

        with CameraCapture(0) as cam:
            self.assertTrue(cam.is_opened())

        mock_cap_instance.release.assert_called_once()
        self.assertFalse(cam.is_opened())

    def test_capture_pc_with_injected_test_double(self):
        """capture_pc() funciona con un doble de prueba inyectado sin tocar hardware."""
        mock_cam = MagicMock(spec=CameraCapture)
        dummy_frame = object()
        mock_cam.read_frame.return_value = (True, dummy_frame)

        set_default_camera(mock_cam)
        frame = capture_pc()

        self.assertIs(frame, dummy_frame)
        mock_cam.read_frame.assert_called_once()

    def test_capture_pc_failure_returns_none(self):
        """capture_pc() retorna None ante fallo de lectura sin lanzar excepciones."""
        mock_cam = MagicMock(spec=CameraCapture)
        mock_cam.read_frame.return_value = (False, None)

        set_default_camera(mock_cam)
        frame = capture_pc()

        self.assertIsNone(frame)


if __name__ == "__main__":
    unittest.main()
