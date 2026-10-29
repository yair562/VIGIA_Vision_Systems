"""
tests.unit.test_camera
======================
Pruebas unitarias para los adaptadores de captura propios de ``VIGIA_Vision.capture``
(``OpenCVCaptureSource``, ``MobilePushFrameBuffer`` y ``CameraSourceRegistry``)
en la Etapa 1 del motor de visión artificial de VIGÍA.

Completamente desacoplado del prototipo experimental: no importa ningún módulo
externo de prototipo y no requiere cámaras físicas ni GPU.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import numpy as np

# Asegurar raíz del repositorio en sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import VIGIA_Vision.capture.sources as sources_module
from VIGIA_Vision.capture.registry import (
    CameraSourceRegistry,
    UnregisteredCameraError,
)
from VIGIA_Vision.capture.sources import (
    IFrameCaptureSource,
    MobilePushFrameBuffer,
    OpenCVCaptureSource,
)
from VIGIA_Vision.config.topology_validator import (
    AreaConfigDTO,
    CameraConfigDTO,
    OperationalTopologyDTO,
)


class TestOpenCVCaptureSourceDecoupling(unittest.TestCase):
    """Verifica el ciclo de vida explícito y perezoso de OpenCVCaptureSource."""

    def test_import_does_not_open_hardware(self) -> None:
        """Importar VIGIA_Vision.capture.sources no instancia descriptores globales de cámara."""
        self.assertFalse(hasattr(sources_module, "cam"))
        self.assertFalse(hasattr(sources_module, "_default_camera"))

    def test_instantiation_does_not_invoke_capture_factory(self) -> None:
        """OpenCVCaptureSource(0) no adquiere hardware en __init__."""
        factory = MagicMock()
        source = OpenCVCaptureSource(0, capture_factory=factory)
        self.assertFalse(source.is_opened())
        factory.assert_not_called()

    def test_read_before_open_returns_not_open_without_activating_hardware(self) -> None:
        """read_frame() antes de open() retorna ok=False sin abrir implícitamente el hardware."""
        factory = MagicMock()
        source = OpenCVCaptureSource("rtsp://192.168.1.10/live", capture_factory=factory)
        res = source.read_frame()
        self.assertFalse(res.ok)
        self.assertIsNone(res.frame)
        self.assertEqual(res.error_reason, "CAPTURE_SOURCE_NOT_OPEN")
        factory.assert_not_called()

    def test_explicit_open_read_and_idempotent_release(self) -> None:
        """Apertura explícita, lectura numerada por secuencia y liberación idempotente."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, dummy_frame)
        factory = MagicMock(return_value=mock_cap)

        source = OpenCVCaptureSource(0, capture_factory=factory)
        self.assertTrue(source.open())
        factory.assert_called_once_with(0)
        self.assertTrue(source.is_opened())

        res1 = source.read_frame()
        self.assertTrue(res1.ok)
        self.assertIs(res1.frame, dummy_frame)
        self.assertEqual(res1.frame_sequence, 1)

        res2 = source.read_frame()
        self.assertTrue(res2.ok)
        self.assertEqual(res2.frame_sequence, 2)

        # Liberación idempotente (dos llamadas no fallan y llaman release() una sola vez)
        source.release()
        source.release()
        mock_cap.release.assert_called_once()
        self.assertFalse(source.is_opened())

    def test_read_frame_failure_reports_cleanly(self) -> None:
        """Si la cámara abierta retorna (False, None), read_frame() informa CAPTURE_EMPTY_FRAME."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)

        source = OpenCVCaptureSource(0, capture_factory=lambda _u: mock_cap)
        self.assertTrue(source.open())

        res = source.read_frame()
        self.assertFalse(res.ok)
        self.assertIsNone(res.frame)
        self.assertEqual(res.error_reason, "CAPTURE_EMPTY_FRAME")

    def test_context_manager_opens_and_releases(self) -> None:
        """El context manager abre al entrar y libera al salir."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True

        with OpenCVCaptureSource(0, capture_factory=lambda _u: mock_cap) as src:
            self.assertTrue(src.is_opened())

        mock_cap.release.assert_called_once()
        self.assertFalse(src.is_opened())


class TestMobilePushFrameBuffer(unittest.TestCase):
    """Verifica el buffer push móvil: ranura única, sobrescritura, secuencia y TTL."""

    def setUp(self) -> None:
        self.current_time = datetime(2026, 10, 29, 6, 0, 0, tzinfo=timezone.utc)
        self.frame_a = np.zeros((100, 100, 3), dtype=np.uint8)
        self.frame_b = np.ones((100, 100, 3), dtype=np.uint8) * 128

    def _clock(self) -> datetime:
        return self.current_time

    def test_push_requires_open_buffer(self) -> None:
        """No se permite depositar fotogramas si el buffer no fue abierto."""
        buf = MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=3.0, clock=self._clock)
        with self.assertRaises(RuntimeError):
            buf.push_frame(self.frame_a)

    def test_single_slot_overwrite_and_monotonic_sequence(self) -> None:
        """Depositar dos fotogramas antes de leer sobrescribe el primero e incrementa la secuencia."""
        buf = MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=3.0, clock=self._clock)
        buf.open()

        seq1 = buf.push_frame(self.frame_a)
        seq2 = buf.push_frame(self.frame_b)

        self.assertEqual(seq1, 1)
        self.assertEqual(seq2, 2)

        read_res = buf.read_frame()
        self.assertTrue(read_res.ok)
        self.assertIs(read_res.frame, self.frame_b)
        self.assertEqual(read_res.frame_sequence, 2)
        self.assertFalse(read_res.is_already_processed)

    def test_does_not_reprocess_same_sequence_indefinitely(self) -> None:
        """Una segunda lectura sin nuevo push informa is_already_processed=True."""
        buf = MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=3.0, clock=self._clock)
        buf.open()
        buf.push_frame(self.frame_a)

        first = buf.read_frame()
        self.assertTrue(first.ok)
        self.assertEqual(first.frame_sequence, 1)

        second = buf.read_frame()
        self.assertFalse(second.ok)
        self.assertTrue(second.is_already_processed)
        self.assertEqual(second.frame_sequence, 1)
        self.assertEqual(second.error_reason, "NO_NEW_FRAME_SEQUENCE")

    def test_expired_frame_by_ttl_is_rejected(self) -> None:
        """Si transcurre más tiempo que ttl_seconds, el fotograma es rechazado como expirado."""
        buf = MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=2.0, clock=self._clock)
        buf.open()
        buf.push_frame(self.frame_a)

        # Avanzar el reloj 2.5 segundos (> TTL de 2.0 s)
        self.current_time = self.current_time + timedelta(seconds=2.5)

        res = buf.read_frame()
        self.assertFalse(res.ok)
        self.assertFalse(res.is_already_processed)
        self.assertIsNone(res.frame)
        self.assertIn("MOBILE_FRAME_EXPIRED_TTL", res.error_reason or "")


class TestCameraSourceRegistry(unittest.TestCase):
    """Verifica que el registro enlaza estrictamente la topología y rechaza cámaras externas."""

    def setUp(self) -> None:
        id_ent = uuid4()
        id_sal = uuid4()
        self.topology = OperationalTopologyDTO(
            cam_entrada=CameraConfigDTO(
                id_camara=id_ent,
                codigo="CAM-ENTRADA",
                nombre="Cámara Entrada",
                uri_stream="push://cam-entrada",
                activa=True,
            ),
            area_entrada=AreaConfigDTO(
                id_area_vision=uuid4(),
                id_camara=id_ent,
                codigo="ROI-ENT",
                nombre="ROI Entrada",
                tipo_movimiento="ENTRADA",
                x_min=0.1,
                y_min=0.1,
                x_max=0.9,
                y_max=0.9,
                activa=True,
            ),
            cam_salida=CameraConfigDTO(
                id_camara=id_sal,
                codigo="CAM-SALIDA",
                nombre="Cámara Salida",
                uri_stream="push://cam-salida",
                activa=True,
            ),
            area_salida=AreaConfigDTO(
                id_area_vision=uuid4(),
                id_camara=id_sal,
                codigo="ROI-SAL",
                nombre="ROI Salida",
                tipo_movimiento="SALIDA",
                x_min=0.1,
                y_min=0.1,
                x_max=0.9,
                y_max=0.9,
                activa=True,
            ),
        )

    def test_registry_binds_topology_without_opening_sources_on_init(self) -> None:
        """Construir CameraSourceRegistry no abre las fuentes en __init__."""
        src_ent = MagicMock(spec=IFrameCaptureSource)
        src_sal = MagicMock(spec=IFrameCaptureSource)

        reg = CameraSourceRegistry(
            topology=self.topology,
            sources={"CAM-ENTRADA": src_ent, "CAM-SALIDA": src_sal},
        )

        self.assertEqual(reg.registered_camera_codes, ("CAM-ENTRADA", "CAM-SALIDA"))
        src_ent.open.assert_not_called()
        src_sal.open.assert_not_called()

    def test_registry_rejects_unregistered_camera_code(self) -> None:
        """Cualquier cámara fuera de OperationalTopologyDTO es rechazada con UnregisteredCameraError."""
        reg = CameraSourceRegistry(topology=self.topology)
        with self.assertRaises(UnregisteredCameraError):
            reg.get_slot("CAM-INTRUSA")

        with self.assertRaises(UnregisteredCameraError):
            CameraSourceRegistry(
                topology=self.topology,
                sources={"CAM-TELEFONO-ARBITRARIO": MagicMock(spec=IFrameCaptureSource)},
            )


if __name__ == "__main__":
    unittest.main()
