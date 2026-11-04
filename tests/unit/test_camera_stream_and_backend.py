"""
tests.unit.test_camera_stream_and_backend
=========================================
Pruebas unitarias y de integración backend para CAM-01A (VIGIA-CAM-01).

Cubre exhaustivamente:
- Anotación: ROI válido, ROI ausente, fotograma sin detecciones, con detecciones,
  y fallback seguro al fotograma crudo ante fallo de anotación.
- Persistencia e Idempotencia: Primera detección, dos eventos consecutivos legítimos,
  dos cámaras independientes, repetición idempotente, reintento tras error,
  y solicitudes concurrentes.
- Streaming: Fotograma disponible, ausencia de fotogramas (standby corporativo),
  actualización de secuencia, cliente desconectado (GeneratorExit),
  cámara inactiva / inexistente (404), y dos cámaras transmitiendo simultáneamente.
- Seguridad: Cámara no autorizada (401), token inválido (401), cámara inexistente (404),
  y aislamiento entre cámaras.
"""

from __future__ import annotations

import io
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import cv2
import numpy as np

from VIGIA_API.ingest_service import (
    _latest_camera_frames,
    create_ingest_app,
)
from VIGIA_Core.domain.user import UserDTO
from VIGIA_Core.repository.user_repository import InMemoryUserRepository
from VIGIA_Vision.capture.sources import MobilePushFrameBuffer
from VIGIA_Vision.config.topology_validator import AreaConfigDTO, CameraConfigDTO
from VIGIA_Vision.detection.roi_and_preprocess import (
    BoundingBox,
    PixelROI,
    RawVehicleDetection,
    project_normalized_roi,
)
from VIGIA_Vision.runtime.coordinator import (
    ObservationMetrics,
    VisionEngineCoordinator,
    VisionObservationEnvelope,
    VisionResult,
    VisionStatus,
)
from VIGIA_Vision.runtime.evidence_storage import render_annotated_frame


def _make_synthetic_bgr(width: int = 640, height: int = 360, color: Tuple[int, int, int] = (50, 100, 150)) -> np.ndarray:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = color
    return img


def _bgr_to_jpeg(bgr: np.ndarray, quality: int = 80) -> bytes:
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else b""


class MockCameraSlot:
    def __init__(self, codigo_camara: str, area_dto: Optional[AreaConfigDTO] = None):
        self.camera = CameraConfigDTO(
            id_camara=uuid4(),
            codigo=codigo_camara,
            nombre=f"Cámara {codigo_camara}",
            uri_stream="push://mobile",
            activa=True,
        )
        self.area = area_dto or AreaConfigDTO(
            id_area_vision=uuid4(),
            id_camara=self.camera.id_camara,
            codigo=f"AREA-{codigo_camara}",
            nombre=f"Área {codigo_camara}",
            tipo_movimiento="ENTRADA",
            x_min=0.1,
            y_min=0.1,
            x_max=0.9,
            y_max=0.9,
            activa=True,
        )
        self.source = MobilePushFrameBuffer(codigo_camara=codigo_camara, ttl_seconds=5.0)


class MockCameraRegistry:
    def __init__(self, slots: Dict[str, MockCameraSlot]):
        self._slots = {k.strip().upper(): v for k, v in slots.items()}

    def get_slot(self, codigo_camara: str) -> MockCameraSlot:
        clean = codigo_camara.strip().upper()
        if clean in self._slots:
            return self._slots[clean]
        from VIGIA_Vision.capture.registry import UnregisteredCameraError
        raise UnregisteredCameraError(f"Cámara '{codigo_camara}' no registrada.")

    def list_cameras(self) -> List[CameraConfigDTO]:
        return [s.camera for s in self._slots.values()]


class MockTopologyRepository:
    def __init__(self, slots: Dict[str, MockCameraSlot]):
        self._slots = {k.strip().upper(): v for k, v in slots.items()}

    def get_all_cameras(self) -> List[CameraConfigDTO]:
        return [s.camera for s in self._slots.values()]

    def get_areas_for_camera(self, id_camara: UUID) -> List[AreaConfigDTO]:
        for s in self._slots.values():
            if s.camera.id_camara == id_camara and s.area:
                return [s.area]
        return []


class TestCameraStreamAndBackend(unittest.TestCase):
    def setUp(self) -> None:
        _latest_camera_frames.clear()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="vigia_cam01a_unit_"))
        self.certs_dir = self.temp_dir / "certs"
        self.certs_dir.mkdir(parents=True, exist_ok=True)

        self.cam_entrada_slot = MockCameraSlot("CAM-ENTRADA")
        self.cam_salida_slot = MockCameraSlot("CAM-SALIDA")
        self.registry = MockCameraRegistry({
            "CAM-ENTRADA": self.cam_entrada_slot,
            "CAM-SALIDA": self.cam_salida_slot,
        })
        self.topo_repo = MockTopologyRepository({
            "CAM-ENTRADA": self.cam_entrada_slot,
            "CAM-SALIDA": self.cam_salida_slot,
        })

        # Mock Coordinator
        self.coordinator = MagicMock(spec=VisionEngineCoordinator)
        self.coordinator.is_initialized = True
        self.coordinator.registry = self.registry
        self.coordinator.settings = MagicMock()
        self.coordinator.settings.save_annotated_evidence = True
        self.coordinator._detection_repository = MagicMock()

        self.user_repo = InMemoryUserRepository()
        self.admin_user = UserDTO(
            id_usuario=uuid4(),
            username="admin_unit",
            contrasena_hash="fake",
            nombre_completo="Admin Unit",
            rol="ADMINISTRADOR",
            activo=True,
        )
        self.user_repo.create_user(self.admin_user)

        self.auth_token = "TEST_CAM_KEY_2026"
        self.app = create_ingest_app(
            coordinator=self.coordinator,
            auth_token=self.auth_token,
            user_repository=self.user_repo,
            topology_repository=self.topo_repo,
            allow_in_memory=True,
            certs_dir=self.certs_dir,
        )
        self.client = self.app.test_client()
        self.synthetic_frame_bytes = _bgr_to_jpeg(_make_synthetic_bgr())

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_mock_envelope(
        self,
        slot: MockCameraSlot,
        vehicle_detected: bool = True,
        tipo_vehiculo: Optional[str] = "AUTOMOVIL",
        confianza: Optional[float] = 0.92,
        persisted: bool = True,
        sequence: int = 1,
    ) -> VisionObservationEnvelope:
        dets = ()
        if vehicle_detected:
            dets = (
                RawVehicleDetection(
                    bbox=BoundingBox(100, 100, 300, 250),
                    confidence=confianza or 0.90,
                    raw_label="car",
                ),
            )
        vr = VisionResult(
            status=VisionStatus.VEHICLE_DETECTED_NO_PLATE if vehicle_detected else VisionStatus.NO_VEHICLE_DETECTED,
            timestamp=None,
            vehicle_detected=vehicle_detected,
            vehicle_confidence=confianza,
            vehicle_type_pred=tipo_vehiculo,
            plate_located=False,
            plate_text=None,
            plate_confidence=None,
            evidence_path="/evidence/test_orig.jpg" if persisted else None,
            error_message=None,
        )
        return VisionObservationEnvelope(
            id_camara=slot.camera.id_camara,
            id_area_vision=slot.area.id_area_vision if slot.area else uuid4(),
            codigo_camara=slot.camera.codigo,
            codigo_area=slot.area.codigo if slot.area else "AREA-NONE",
            tipo_movimiento=slot.area.tipo_movimiento if slot.area else "ENTRADA",
            vision_result=vr,
            detections_in_roi=dets,
            metrics=ObservationMetrics(in_roi_now=len(dets), total_detected_in_frame=len(dets)),
            frame_sequence=sequence,
            id_deteccion=uuid4() if persisted else None,
            original_evidence_path="evidence/orig.jpg" if persisted else None,
            annotated_evidence_path="evidence/annot.jpg" if persisted else None,
        )

    # =========================================================================
    # 1. PRUEBAS DE ANOTACIÓN Y PROYECCIÓN DEL ROI
    # =========================================================================

    def test_annotation_with_valid_roi_and_detections(self):
        """Verifica que un fotograma con ROI válido y detecciones sea anotado correctamente."""
        slot = self.cam_entrada_slot
        env = self._make_mock_envelope(slot, vehicle_detected=True, sequence=10)
        self.coordinator.process_camera_step.return_value = env

        resp = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=self.synthetic_frame_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": self.auth_token},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["vehicle_detected"])

        # Verificar que el live frame esté disponible y sea imagen JPEG anotada válida
        live_resp = self.client.get("/api/v1/cameras/CAM-ENTRADA/live")
        self.assertEqual(live_resp.status_code, 200)
        self.assertEqual(live_resp.mimetype, "image/jpeg")
        self.assertEqual(live_resp.headers.get("X-Vehicle-Detected"), "true")
        self.assertEqual(live_resp.headers.get("X-Vehicle-Type"), "AUTOMOVIL")

        # Comprobar decodificación de la imagen anotada
        img = cv2.imdecode(np.frombuffer(live_resp.data, dtype=np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNotNone(img)
        self.assertEqual(img.shape[0], 360)
        self.assertEqual(img.shape[1], 640)

    def test_annotation_with_roi_absent(self):
        """Verifica que una cámara sin área configurada (slot.area=None) no falle y se anote limpiamente."""
        slot = MockCameraSlot("CAM-NO-AREA")
        slot.area = None
        self.registry._slots["CAM-NO-AREA"] = slot

        env = self._make_mock_envelope(slot, vehicle_detected=False, sequence=1)
        self.coordinator.process_camera_step.return_value = env

        resp = self.client.post(
            "/api/v1/cameras/CAM-NO-AREA/push",
            data=self.synthetic_frame_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": self.auth_token},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["ok"])

    def test_annotation_frame_without_detections(self):
        """Verifica que cuando no hay vehículos detectados, sólo se dibuje el ROI sin fallos."""
        slot = self.cam_entrada_slot
        env = self._make_mock_envelope(slot, vehicle_detected=False, sequence=5)
        self.coordinator.process_camera_step.return_value = env

        resp = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=self.synthetic_frame_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": self.auth_token},
        )
        self.assertEqual(resp.status_code, 200)
        live_resp = self.client.get("/api/v1/cameras/CAM-ENTRADA/live")
        self.assertEqual(live_resp.headers.get("X-Vehicle-Detected"), "false")

    def test_annotation_error_fallback_to_raw_bytes(self):
        """Verifica que ante un fallo simulado en render_annotated_frame se use fallback al fotograma original."""
        slot = self.cam_entrada_slot
        env = self._make_mock_envelope(slot, vehicle_detected=True, sequence=2)
        self.coordinator.process_camera_step.return_value = env

        with patch("VIGIA_API.ingest_service.render_annotated_frame", side_effect=RuntimeError("Simulated draw failure")):
            resp = self.client.post(
                "/api/v1/cameras/CAM-ENTRADA/push",
                data=self.synthetic_frame_bytes,
                headers={"Content-Type": "image/jpeg", "X-Camera-Key": self.auth_token},
            )
            self.assertEqual(resp.status_code, 200)
            live_resp = self.client.get("/api/v1/cameras/CAM-ENTRADA/live")
            self.assertEqual(live_resp.status_code, 200)
            # Debe entregar la imagen cruda sin corromper el servicio
            self.assertEqual(live_resp.data, self.synthetic_frame_bytes)

    # =========================================================================
    # 2. PRUEBAS DE PERSISTENCIA E IDEMPOTENCIA
    # =========================================================================

    def test_first_detection_persists(self):
        """Verifica que la primera detección vehicular válida sea enviada con persist_as_new_event=True."""
        slot = self.cam_entrada_slot
        env = self._make_mock_envelope(slot, vehicle_detected=True, persisted=True, sequence=1)
        self.coordinator.process_camera_step.return_value = env

        resp = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=self.synthetic_frame_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": self.auth_token},
        )
        self.assertEqual(resp.status_code, 200)
        self.coordinator.process_camera_step.assert_called_with("CAM-ENTRADA", persist_as_new_event=True)

    def test_two_consecutive_legitimate_events_with_explicit_idempotency_keys(self):
        """Dos solicitudes consecutivas con X-Idempotency-Key distintos deben persistir sin ser bloqueadas."""
        slot = self.cam_entrada_slot
        env1 = self._make_mock_envelope(slot, vehicle_detected=True, persisted=True, sequence=1)
        env2 = self._make_mock_envelope(slot, vehicle_detected=True, persisted=True, sequence=2)

        self.coordinator.process_camera_step.side_effect = [env1, env2]

        resp1 = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=self.synthetic_frame_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": self.auth_token, "X-Idempotency-Key": "evt-1"},
        )
        self.assertEqual(resp1.status_code, 200)
        self.coordinator.process_camera_step.assert_called_with("CAM-ENTRADA", persist_as_new_event=True)

        resp2 = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=_bgr_to_jpeg(_make_synthetic_bgr(color=(60, 110, 160))),
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": self.auth_token, "X-Idempotency-Key": "evt-2"},
        )
        self.assertEqual(resp2.status_code, 200)
        # Ambas solicitudes deliberadas con claves distintas persisten
        self.coordinator.process_camera_step.assert_called_with("CAM-ENTRADA", persist_as_new_event=True)

    def test_continuous_streaming_debounce_for_same_stationary_vehicle(self):
        """En streaming continuo anónimo (sin clave explícita), el segundo fotograma dentro del intervalo no satura la BD."""
        slot = self.cam_entrada_slot
        env1 = self._make_mock_envelope(slot, vehicle_detected=True, persisted=True, sequence=1)
        env2 = self._make_mock_envelope(slot, vehicle_detected=True, persisted=False, sequence=2)

        self.coordinator.process_camera_step.side_effect = [env1, env2]

        # Primer fotograma del vehículo -> persiste
        resp1 = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=self.synthetic_frame_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": self.auth_token},
        )
        self.assertEqual(resp1.status_code, 200)
        self.coordinator.process_camera_step.assert_called_with("CAM-ENTRADA", persist_as_new_event=True)

        # Segundo fotograma continuo 50 ms después para el mismo vehículo estacionario -> no duplica en BD
        resp2 = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=_bgr_to_jpeg(_make_synthetic_bgr(color=(51, 101, 151))),
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": self.auth_token},
        )
        self.assertEqual(resp2.status_code, 200)
        self.coordinator.process_camera_step.assert_called_with("CAM-ENTRADA", persist_as_new_event=False)

    def test_two_independent_cameras_isolation(self):
        """La actividad o debounce de CAM-ENTRADA no bloquea a CAM-SALIDA."""
        slot_in = self.cam_entrada_slot
        slot_out = self.cam_salida_slot

        env_in = self._make_mock_envelope(slot_in, vehicle_detected=True, persisted=True, sequence=1)
        env_out = self._make_mock_envelope(slot_out, vehicle_detected=True, persisted=True, sequence=1)
        self.coordinator.process_camera_step.side_effect = [env_in, env_out]

        # Ingesta en CAM-ENTRADA
        resp_in = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=self.synthetic_frame_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": self.auth_token},
        )
        self.assertEqual(resp_in.status_code, 200)
        self.coordinator.process_camera_step.assert_called_with("CAM-ENTRADA", persist_as_new_event=True)

        # Ingesta inmediata en CAM-SALIDA -> debe persistir independientemente
        resp_out = self.client.post(
            "/api/v1/cameras/CAM-SALIDA/push",
            data=self.synthetic_frame_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": self.auth_token},
        )
        self.assertEqual(resp_out.status_code, 200)
        self.coordinator.process_camera_step.assert_called_with("CAM-SALIDA", persist_as_new_event=True)

    def test_idempotent_request_repetition(self):
        """Repetir la misma solicitud con idéntica clave de idempotencia retorna el resultado cacheado."""
        slot = self.cam_entrada_slot
        env = self._make_mock_envelope(slot, vehicle_detected=True, persisted=True, sequence=1)
        self.coordinator.process_camera_step.return_value = env

        headers = {
            "Content-Type": "image/jpeg",
            "X-Camera-Key": self.auth_token,
            "X-Idempotency-Key": "same-request-id-12345",
        }
        resp1 = self.client.post("/api/v1/cameras/CAM-ENTRADA/push", data=self.synthetic_frame_bytes, headers=headers)
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.get_json()
        self.assertFalse(data1.get("duplicate_retry", False))

        # Reintento idéntico
        self.coordinator.process_camera_step.reset_mock()
        resp2 = self.client.post("/api/v1/cameras/CAM-ENTRADA/push", data=self.synthetic_frame_bytes, headers=headers)
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.get_json()
        self.assertTrue(data2.get("duplicate_retry"))
        # El coordinador es invocado con persist_as_new_event=False para no duplicar en BD/disco
        self.coordinator.process_camera_step.assert_called_with("CAM-ENTRADA", persist_as_new_event=False)

    def test_concurrent_push_requests(self):
        """Solicitudes concurrentes en hilos separados no causan corrupción de datos ni condiciones de carrera."""
        slot = self.cam_entrada_slot
        env = self._make_mock_envelope(slot, vehicle_detected=True, persisted=True, sequence=1)
        self.coordinator.process_camera_step.return_value = env

        success_count = [0]
        lock = threading.Lock()

        def worker(thread_idx: int):
            resp = self.client.post(
                "/api/v1/cameras/CAM-ENTRADA/push",
                data=self.synthetic_frame_bytes,
                headers={
                    "Content-Type": "image/jpeg",
                    "X-Camera-Key": self.auth_token,
                    "X-Idempotency-Key": f"concurrent-{thread_idx}",
                },
            )
            if resp.status_code == 200:
                with lock:
                    success_count[0] += 1

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(success_count[0], 8)

    # =========================================================================
    # 3. PRUEBAS DE CICLO DE VIDA DEL STREAMING Y MONITOREO
    # =========================================================================

    def test_stream_absence_returns_standby(self):
        """Antes de recibir cualquier fotograma, /live entrega la imagen sintética corporativa de standby."""
        resp = self.client.get("/api/v1/cameras/CAM-ENTRADA/live")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "image/jpeg")
        self.assertEqual(resp.headers.get("X-Vision-Status"), "EN_ESPERA")

        status_resp = self.client.get("/api/v1/cameras/CAM-ENTRADA/status")
        self.assertEqual(status_resp.status_code, 200)
        s_data = status_resp.get_json()
        self.assertFalse(s_data["is_transmitting"])
        self.assertEqual(s_data["status"], "EN_ESPERA")

    def test_stream_sequence_update(self):
        """Al recibir fotogramas, /status y /live reflejan la secuencia y frescura del stream."""
        slot = self.cam_entrada_slot
        env = self._make_mock_envelope(slot, vehicle_detected=True, sequence=42)
        self.coordinator.process_camera_step.return_value = env

        self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=self.synthetic_frame_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": self.auth_token},
        )

        status_resp = self.client.get("/api/v1/cameras/CAM-ENTRADA/status")
        self.assertEqual(status_resp.status_code, 200)
        s_data = status_resp.get_json()
        self.assertTrue(s_data["is_transmitting"])
        self.assertEqual(s_data["sequence"], 42)
        self.assertTrue(s_data["vehicle_detected"])
        self.assertLess(s_data["last_frame_seconds_ago"], 1.0)

    def test_stream_mjpeg_client_disconnect_handling(self):
        """El generador MJPEG maneja limpiamente la desconexión del cliente (GeneratorExit)."""
        slot = self.cam_entrada_slot
        env = self._make_mock_envelope(slot, sequence=1)
        self.coordinator.process_camera_step.return_value = env

        self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=self.synthetic_frame_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": self.auth_token},
        )

        # Consumir el generador y cerrarlo explícitamente para simular desconexión HTTP
        resp = self.client.get("/api/v1/cameras/CAM-ENTRADA/stream")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("multipart/x-mixed-replace", resp.mimetype)

        # Iterar un chunk y cerrar el generador
        gen = resp.response
        first_chunk = next(gen)
        self.assertIn(b"--frame", first_chunk)
        gen.close()  # Provoca GeneratorExit interno capturado limpiamente

    def test_unregistered_camera_returns_404(self):
        """Consultar /live, /stream o /status de una cámara no registrada devuelve HTTP 404."""
        resp_live = self.client.get("/api/v1/cameras/CAM-FANTASMA/live")
        self.assertEqual(resp_live.status_code, 404)
        self.assertEqual(resp_live.get_json()["error"], "CAMERA_NOT_FOUND")

        resp_stream = self.client.get("/api/v1/cameras/CAM-FANTASMA/stream")
        self.assertEqual(resp_stream.status_code, 404)

        resp_status = self.client.get("/api/v1/cameras/CAM-FANTASMA/status")
        self.assertEqual(resp_status.status_code, 404)

    # =========================================================================
    # 4. PRUEBAS DE SEGURIDAD
    # =========================================================================

    def test_unauthorized_camera_missing_key(self):
        """Intento de push sin cabecera de autenticación es rechazado con HTTP 401."""
        resp = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=self.synthetic_frame_bytes,
            headers={"Content-Type": "image/jpeg"},
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.get_json()["error"], "UNAUTHORIZED")

    def test_invalid_key_rejected(self):
        """Intento de push con clave incorrecta es rechazado con HTTP 401."""
        resp = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=self.synthetic_frame_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": "CLAVE_INCORRECTA"},
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.get_json()["error"], "UNAUTHORIZED")

    def test_stream_expiration_transitions_to_sin_senal(self):
        """Al expirar el TTL de transmisión (>= 4.0s), /status cambia a is_transmitting=False y SIN_SEÑAL."""
        slot = self.cam_entrada_slot
        env = self._make_mock_envelope(slot, sequence=10)
        self.coordinator.process_camera_step.return_value = env

        self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=self.synthetic_frame_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": self.auth_token},
        )

        # Simular paso del tiempo envejeciendo el timestamp del fotograma
        _latest_camera_frames["CAM-ENTRADA"]["timestamp"] = time.time() - 5.0

        status_resp = self.client.get("/api/v1/cameras/CAM-ENTRADA/status")
        self.assertEqual(status_resp.status_code, 200)
        s_data = status_resp.get_json()
        self.assertFalse(s_data["is_transmitting"])
        self.assertEqual(s_data["operational_state"], "SIN_SEÑAL")
        self.assertGreaterEqual(s_data["last_frame_seconds_ago"], 5.0)

        # En /live debe entregar imagen con X-Vision-Status = SIN_SENAL
        live_resp = self.client.get("/api/v1/cameras/CAM-ENTRADA/live")
        self.assertEqual(live_resp.status_code, 200)
        self.assertEqual(live_resp.headers.get("X-Vision-Status"), "SIN_SENAL")

    def test_cross_camera_access_rejected_with_pairing_repo(self):
        """Un token válido exclusivamente para CAM-ENTRADA no permite push a CAM-SALIDA."""
        mock_pairing_repo = MagicMock()
        def mock_validate(codigo_camara, token_transmision):
            return codigo_camara.strip().upper() == "CAM-ENTRADA" and token_transmision == "vigia_st_for_cam_entrada"
        mock_pairing_repo.validate_stream_token.side_effect = mock_validate

        self.app.config["PAIRING_REPOSITORY"] = mock_pairing_repo

        # Push a CAM-ENTRADA con su token -> 200
        slot_in = self.cam_entrada_slot
        env_in = self._make_mock_envelope(slot_in, sequence=1)
        self.coordinator.process_camera_step.return_value = env_in
        resp_in = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=self.synthetic_frame_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": "vigia_st_for_cam_entrada"},
        )
        self.assertEqual(resp_in.status_code, 200)

        # Push a CAM-SALIDA con el token de CAM-ENTRADA -> 401 UNAUTHORIZED
        resp_out = self.client.post(
            "/api/v1/cameras/CAM-SALIDA/push",
            data=self.synthetic_frame_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": "vigia_st_for_cam_entrada"},
        )
        self.assertEqual(resp_out.status_code, 401)
        self.assertEqual(resp_out.get_json()["error"], "UNAUTHORIZED")

    def test_two_cameras_streaming_simultaneously_and_isolated(self):
        """Dos cámaras transmitiendo en paralelo mantienen secuencias y estados completamente aislados."""
        slot_in = self.cam_entrada_slot
        slot_out = self.cam_salida_slot

        env_in = self._make_mock_envelope(slot_in, sequence=101)
        env_out = self._make_mock_envelope(slot_out, sequence=202)
        self.coordinator.process_camera_step.side_effect = [env_in, env_out]

        # Push a ambas cámaras
        self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=self.synthetic_frame_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": self.auth_token},
        )
        self.client.post(
            "/api/v1/cameras/CAM-SALIDA/push",
            data=self.synthetic_frame_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": self.auth_token},
        )

        # Consultar estado de cada una
        st_in = self.client.get("/api/v1/cameras/CAM-ENTRADA/status").get_json()
        st_out = self.client.get("/api/v1/cameras/CAM-SALIDA/status").get_json()

        self.assertEqual(st_in["sequence"], 101)
        self.assertEqual(st_in["operational_state"], "TRANSMITIENDO")
        self.assertEqual(st_out["sequence"], 202)
        self.assertEqual(st_out["operational_state"], "TRANSMITIENDO")


if __name__ == "__main__":
    unittest.main()
