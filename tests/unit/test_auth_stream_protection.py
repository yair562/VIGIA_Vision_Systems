"""
VIGIA_Vision_Systems - Pruebas Unitarias de Protección RBAC para Video y Telemetría
Fase 1 / Milestone VIGIA-AUTH-01-IMPLEMENTATION

Verifica determinísticamente el control de acceso en los endpoints:
- GET /api/v1/cameras/<codigo>/stream
- GET /api/v1/cameras/<codigo>/live
- GET /api/v1/cameras/<codigo>/status

Casos cubiertos:
1. Petición sin cookie de sesión (HTTP 401).
2. Cookie con token sintético o inválido (HTTP 401).
3. Sesión expirada por inactividad o TTL absoluto (HTTP 401).
4. Sesión revocada explícitamente vía SessionManager.revoke_session (HTTP 401).
5. Rol ADMINISTRADOR permitido (HTTP 200).
6. Rol GUARDIA / OPERADOR permitido (HTTP 200).
7. Rol AUDITOR denegado (HTTP 403 Forbidden).
8. Cámara inexistente con sesión autorizada (HTTP 404).
9. Expiración de sesión durante flujo activo MJPEG (cierre automático del generador).
10. Revocación de sesión durante flujo activo MJPEG (cierre automático del generador).
11. Desconexión limpia del cliente (GeneratorExit).
12. Encabezados Cache-Control anti-almacenamiento (no-store, no-cache, max-age=0).
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import tempfile
import time
import unittest
from typing import Dict, Optional, Tuple
from unittest.mock import MagicMock, patch
from uuid import uuid4

import cv2
import numpy as np

from VIGIA_API.ingest_service import (
    _camera_conditions,
    _latest_camera_frames,
    create_ingest_app,
)
from VIGIA_Core.domain.user import UserDTO
from VIGIA_Core.repository.user_repository import InMemoryUserRepository
from VIGIA_Vision.capture.registry import UnregisteredCameraError
from VIGIA_Vision.capture.sources import MobilePushFrameBuffer
from VIGIA_Vision.config.topology_validator import AreaConfigDTO, CameraConfigDTO
from VIGIA_Vision.detection.roi_and_preprocess import (
    BoundingBox,
    RawVehicleDetection,
)
from VIGIA_Vision.runtime.coordinator import (
    ObservationMetrics,
    VisionEngineCoordinator,
    VisionObservationEnvelope,
    VisionResult,
    VisionStatus,
)


def _make_synthetic_bgr(width: int = 640, height: int = 360, color: Tuple[int, int, int] = (60, 120, 180)) -> np.ndarray:
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
        raise UnregisteredCameraError(f"Cámara '{codigo_camara}' no registrada.")


class MockTopologyRepository:
    def __init__(self, slots: Dict[str, MockCameraSlot]):
        self._slots = {k.strip().upper(): v for k, v in slots.items()}

    def get_all_cameras(self):
        return [s.camera for s in self._slots.values()]

    def get_areas_for_camera(self, id_camara):
        for s in self._slots.values():
            if s.camera.id_camara == id_camara and s.area:
                return [s.area]
        return []


class TestAuthStreamProtection(unittest.TestCase):
    def setUp(self) -> None:
        _latest_camera_frames.clear()
        _camera_conditions.clear()
        self.temp_dir = tempfile.mkdtemp()
        self.certs_dir = tempfile.mkdtemp()

        self.cam_slot = MockCameraSlot("CAM-PROTEGIDA")
        self.registry = MockCameraRegistry({"CAM-PROTEGIDA": self.cam_slot})
        self.topo_repo = MockTopologyRepository({"CAM-PROTEGIDA": self.cam_slot})

        self.coordinator = MagicMock(spec=VisionEngineCoordinator)
        self.coordinator.is_initialized = True
        self.coordinator.registry = self.registry
        self.coordinator.settings = MagicMock()
        self.coordinator.settings.save_annotated_evidence = True
        self.coordinator._detection_repository = MagicMock()

        self.user_repo = InMemoryUserRepository()
        self.admin_user = UserDTO(
            id_usuario=uuid4(),
            username="admin_vigia",
            contrasena_hash="fake_hash",
            nombre_completo="Administrador de Seguridad",
            rol="ADMINISTRADOR",
            activo=True,
        )
        self.guardia_user = UserDTO(
            id_usuario=uuid4(),
            username="guardia_vigia",
            contrasena_hash="fake_hash",
            nombre_completo="Guardia de Acceso",
            rol="GUARDIA",
            activo=True,
        )
        self.auditor_user = UserDTO(
            id_usuario=uuid4(),
            username="auditor_vigia",
            contrasena_hash="fake_hash",
            nombre_completo="Auditor de Cumplimiento",
            rol="AUDITOR",
            activo=True,
        )
        self.user_repo.create_user(self.admin_user)
        self.user_repo.create_user(self.guardia_user)
        self.user_repo.create_user(self.auditor_user)

        self.auth_token = "TEST_AUTH_TOKEN_2026"
        self.app = create_ingest_app(
            coordinator=self.coordinator,
            auth_token=self.auth_token,
            user_repository=self.user_repo,
            topology_repository=self.topo_repo,
            allow_in_memory=True,
            certs_dir=self.certs_dir,
        )
        self.session_manager = self.app.config["SESSION_MANAGER"]
        self.client = self.app.test_client()
        self.synthetic_frame_bytes = _bgr_to_jpeg(_make_synthetic_bgr())

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.certs_dir, ignore_errors=True)

    def _push_frame(self, sequence: int = 1):
        env = VisionObservationEnvelope(
            id_camara=self.cam_slot.camera.id_camara,
            id_area_vision=self.cam_slot.area.id_area_vision,
            codigo_camara="CAM-PROTEGIDA",
            codigo_area="AREA-CAM-PROTEGIDA",
            tipo_movimiento="ENTRADA",
            vision_result=VisionResult(
                status=VisionStatus.VEHICLE_DETECTED_NO_PLATE,
                timestamp=None,
                vehicle_detected=True,
                vehicle_confidence=0.91,
                vehicle_type_pred="AUTOMOVIL",
                plate_located=False,
                plate_text=None,
                plate_confidence=None,
                evidence_path=None,
                error_message=None,
            ),
            detections_in_roi=(
                RawVehicleDetection(
                    bbox=BoundingBox(100, 100, 300, 250),
                    confidence=0.91,
                    raw_label="car",
                ),
            ),
            metrics=ObservationMetrics(in_roi_now=1, total_detected_in_frame=1),
            frame_sequence=sequence,
            id_deteccion=uuid4(),
            original_evidence_path="evidence/orig.jpg",
            annotated_evidence_path="evidence/annot.jpg",
        )
        self.coordinator.process_camera_step.return_value = env
        resp = self.client.post(
            "/api/v1/cameras/CAM-PROTEGIDA/push",
            data=self.synthetic_frame_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": self.auth_token},
        )
        self.assertEqual(resp.status_code, 200, f"Error en push: {resp.get_json()}")

    # =========================================================================
    # 1. AUTENTICACIÓN: Sin cookie o con credenciales inválidas / expiradas
    # =========================================================================

    def test_unauthenticated_request_returns_401(self):
        """Peticiones sin cookie 'vigia_session' son rechazadas con HTTP 401 en los tres endpoints."""
        for path in [
            "/api/v1/cameras/CAM-PROTEGIDA/live",
            "/api/v1/cameras/CAM-PROTEGIDA/stream",
            "/api/v1/cameras/CAM-PROTEGIDA/status",
        ]:
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 401, f"Fallo en {path}: esperaba 401, obtuve {resp.status_code}")
            body = resp.get_json()
            self.assertFalse(body["ok"])
            self.assertEqual(body["error"], "UNAUTHORIZED")

    def test_invalid_cookie_returns_401(self):
        """Tokens sintéticos o no registrados en SessionManager devuelven HTTP 401."""
        self.client.set_cookie("vigia_session", "token_completamente_falso_1234567890")
        for path in [
            "/api/v1/cameras/CAM-PROTEGIDA/live",
            "/api/v1/cameras/CAM-PROTEGIDA/stream",
            "/api/v1/cameras/CAM-PROTEGIDA/status",
        ]:
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 401, f"Fallo en {path}")
            self.assertEqual(resp.get_json()["error"], "UNAUTHORIZED")

    def test_expired_session_returns_401(self):
        """Una sesión vencida (inactiva o expirada) es rechazada con HTTP 401."""
        sess = self.session_manager.create_session(self.admin_user)
        expired_sess = replace(sess, expires_at=datetime.now(timezone.utc) - timedelta(seconds=10))
        with self.session_manager._lock:
            self.session_manager._sessions[sess.token] = expired_sess

        self.client.set_cookie("vigia_session", sess.token)
        for path in [
            "/api/v1/cameras/CAM-PROTEGIDA/live",
            "/api/v1/cameras/CAM-PROTEGIDA/stream",
            "/api/v1/cameras/CAM-PROTEGIDA/status",
        ]:
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 401, f"Fallo en {path} con sesión expirada")

    def test_revoked_session_returns_401(self):
        """Una sesión revocada explícitamente devuelve HTTP 401 en todas las rutas."""
        sess = self.session_manager.create_session(self.guardia_user)
        self.session_manager.revoke_session(sess.token)

        self.client.set_cookie("vigia_session", sess.token)
        for path in [
            "/api/v1/cameras/CAM-PROTEGIDA/live",
            "/api/v1/cameras/CAM-PROTEGIDA/stream",
            "/api/v1/cameras/CAM-PROTEGIDA/status",
        ]:
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 401, f"Fallo en {path} con sesión revocada")

    # =========================================================================
    # 2. AUTORIZACIÓN RBAC: Roles permitidos y denegados
    # =========================================================================

    def test_role_administrador_permitted(self):
        """Rol ADMINISTRADOR puede acceder a live, stream y status (HTTP 200)."""
        sess = self.session_manager.create_session(self.admin_user)
        self.client.set_cookie("vigia_session", sess.token)
        self._push_frame(sequence=10)

        # 1. Live
        r_live = self.client.get("/api/v1/cameras/CAM-PROTEGIDA/live")
        self.assertEqual(r_live.status_code, 200)
        self.assertEqual(r_live.mimetype, "image/jpeg")

        # 2. Status
        r_stat = self.client.get("/api/v1/cameras/CAM-PROTEGIDA/status")
        self.assertEqual(r_stat.status_code, 200)
        self.assertTrue(r_stat.get_json()["ok"])

        # 3. Stream (1 fotograma)
        r_stream = self.client.get("/api/v1/cameras/CAM-PROTEGIDA/stream")
        self.assertEqual(r_stream.status_code, 200)
        self.assertIn("multipart/x-mixed-replace", r_stream.mimetype)
        gen = r_stream.response
        chunk = next(gen)
        self.assertIn(b"--frame", chunk)
        gen.close()

    def test_role_guardia_permitted(self):
        """Rol GUARDIA puede acceder a live, stream y status (HTTP 200)."""
        sess = self.session_manager.create_session(self.guardia_user)
        self.client.set_cookie("vigia_session", sess.token)
        self._push_frame(sequence=20)

        # 1. Live
        r_live = self.client.get("/api/v1/cameras/CAM-PROTEGIDA/live")
        self.assertEqual(r_live.status_code, 200)

        # 2. Status
        r_stat = self.client.get("/api/v1/cameras/CAM-PROTEGIDA/status")
        self.assertEqual(r_stat.status_code, 200)
        self.assertTrue(r_stat.get_json()["ok"])

        # 3. Stream
        r_stream = self.client.get("/api/v1/cameras/CAM-PROTEGIDA/stream")
        self.assertEqual(r_stream.status_code, 200)
        gen = r_stream.response
        chunk = next(gen)
        self.assertIn(b"--frame", chunk)
        gen.close()

    def test_role_auditor_forbidden_403(self):
        """Rol AUDITOR recibe HTTP 403 Forbidden en los tres endpoints de streaming y telemetría."""
        sess = self.session_manager.create_session(self.auditor_user)
        self.client.set_cookie("vigia_session", sess.token)

        for path in [
            "/api/v1/cameras/CAM-PROTEGIDA/live",
            "/api/v1/cameras/CAM-PROTEGIDA/stream",
            "/api/v1/cameras/CAM-PROTEGIDA/status",
        ]:
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 403, f"Fallo en {path}: esperaba 403, obtuve {resp.status_code}")
            body = resp.get_json()
            self.assertFalse(body["ok"])
            self.assertEqual(body["error"], "FORBIDDEN")

    def test_unregistered_camera_with_valid_session_returns_404(self):
        """Una sesión autorizada consultando una cámara no registrada recibe 404."""
        sess = self.session_manager.create_session(self.admin_user)
        self.client.set_cookie("vigia_session", sess.token)

        for path in [
            "/api/v1/cameras/CAM-INEXISTENTE/live",
            "/api/v1/cameras/CAM-INEXISTENTE/stream",
            "/api/v1/cameras/CAM-INEXISTENTE/status",
        ]:
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 404, f"Fallo en {path}: esperaba 404, obtuve {resp.status_code}")
            self.assertEqual(resp.get_json()["error"], "CAMERA_NOT_FOUND")

    # =========================================================================
    # 3. CICLO DE VIDA MJPEG: Revocación y expiración durante streaming
    # =========================================================================

    def test_mjpeg_stream_terminates_when_session_revoked(self):
        """Durante un flujo continuo MJPEG, si la sesión es revocada, el generador finaliza limpiamente."""
        sess = self.session_manager.create_session(self.admin_user)
        self.client.set_cookie("vigia_session", sess.token)
        self._push_frame(sequence=1)

        real_time = time.time
        current_virtual_time = [real_time()]

        def mock_time():
            return current_virtual_time[0]

        with patch("time.time", side_effect=mock_time):
            resp = self.client.get("/api/v1/cameras/CAM-PROTEGIDA/stream")
            self.assertEqual(resp.status_code, 200)
            gen = resp.response

            first_chunk = next(gen)
            self.assertIn(b"--frame", first_chunk)

            # Revocar la sesión en el SessionManager
            self.session_manager.revoke_session(sess.token)

            # Avanzar el tiempo simulado más allá del intervalo de 10 segundos
            current_virtual_time[0] += 15.0

            # Enviar nuevo fotograma para despertar al generador
            self._push_frame(sequence=2)

            # Al iterar el generador, debe detectar que la sesión fue revocada y terminar (StopIteration)
            with self.assertRaises(StopIteration):
                next(gen)

    def test_mjpeg_stream_terminates_when_session_expires(self):
        """Durante un flujo continuo MJPEG, si la sesión expira, el generador finaliza limpiamente."""
        sess = self.session_manager.create_session(self.guardia_user)
        self.client.set_cookie("vigia_session", sess.token)
        self._push_frame(sequence=1)

        real_time = time.time
        current_virtual_time = [real_time()]

        def mock_time():
            return current_virtual_time[0]

        with patch("time.time", side_effect=mock_time):
            resp = self.client.get("/api/v1/cameras/CAM-PROTEGIDA/stream")
            self.assertEqual(resp.status_code, 200)
            gen = resp.response

            first_chunk = next(gen)
            self.assertIn(b"--frame", first_chunk)

            # Expirar la sesión
            expired_sess = replace(sess, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
            with self.session_manager._lock:
                self.session_manager._sessions[sess.token] = expired_sess

            # Avanzar tiempo simulado más allá del intervalo de 10 segundos
            current_virtual_time[0] += 15.0

            # Enviar nuevo fotograma para despertar al generador
            self._push_frame(sequence=2)

            # Al iterar, debe detectar la expiración y finalizar
            with self.assertRaises(StopIteration):
                next(gen)

    def test_mjpeg_stream_client_disconnect_handling(self):
        """El generador MJPEG maneja limpiamente la desconexión del cliente (GeneratorExit)."""
        sess = self.session_manager.create_session(self.admin_user)
        self.client.set_cookie("vigia_session", sess.token)
        self._push_frame(sequence=1)

        resp = self.client.get("/api/v1/cameras/CAM-PROTEGIDA/stream")
        self.assertEqual(resp.status_code, 200)
        gen = resp.response
        chunk = next(gen)
        self.assertIn(b"--frame", chunk)

        # Cerrar el generador emite GeneratorExit internamente
        try:
            gen.close()
        except Exception as e:
            self.fail(f"gen.close() no debió levantar excepciones: {e}")

    # =========================================================================
    # 4. ENCABEZADOS CACHE-CONTROL ANTI-ALMACENAMIENTO
    # =========================================================================

    def test_cache_control_headers_prevent_caching(self):
        """Los endpoints protegidos deben incluir Cache-Control no-store y max-age=0."""
        sess = self.session_manager.create_session(self.admin_user)
        self.client.set_cookie("vigia_session", sess.token)
        self._push_frame(sequence=1)

        # 1. Live
        r_live = self.client.get("/api/v1/cameras/CAM-PROTEGIDA/live")
        cc_live = r_live.headers.get("Cache-Control", "")
        self.assertIn("no-store", cc_live)
        self.assertIn("no-cache", cc_live)
        self.assertIn("must-revalidate", cc_live)
        self.assertIn("max-age=0", cc_live)

        # 2. Status
        r_stat = self.client.get("/api/v1/cameras/CAM-PROTEGIDA/status")
        cc_stat = r_stat.headers.get("Cache-Control", "")
        self.assertIn("no-store", cc_stat)
        self.assertIn("no-cache", cc_stat)
        self.assertIn("must-revalidate", cc_stat)
        self.assertIn("max-age=0", cc_stat)

        # 3. Stream
        r_stream = self.client.get("/api/v1/cameras/CAM-PROTEGIDA/stream")
        cc_stream = r_stream.headers.get("Cache-Control", "")
        self.assertIn("no-store", cc_stream)
        self.assertIn("no-cache", cc_stream)
        self.assertIn("must-revalidate", cc_stream)
        self.assertIn("max-age=0", cc_stream)
        r_stream.response.close()


if __name__ == "__main__":
    unittest.main()
