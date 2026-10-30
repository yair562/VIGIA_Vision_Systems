"""
tests.unit.test_mobile_ingest_api
=================================
Pruebas unitarias para el servicio de ingesta HTTP móvil (VO-03 / VO-03B).

Cobertura de pruebas:
- PU-INGEST-01: GET /mobile entrega la interfaz HTML con Content-Type text/html.
- PU-INGEST-02: Rechazo de solicitudes sin archivo o con carga útil vacía (HTTP 400).
- PU-INGEST-03: Rechazo de archivos de imagen con 0 bytes (HTTP 400).
- PU-INGEST-04: Rechazo de bytes corruptos no decodificables con OpenCV (HTTP 422).
- PU-INGEST-05: Rechazo de fotogramas que exceden dimensiones máximas configuradas (HTTP 422).
- PU-INGEST-06: Rechazo de carga útil que excede el tamaño máximo permitido de 8 MiB (HTTP 413).
- PU-INGEST-07: Rechazo de solicitudes hacia cámaras no registradas en la topología (HTTP 404).
- PU-INGEST-08: Rechazo de solicitudes hacia cámaras no configuradas para push móvil (HTTP 400).
- PU-INGEST-09: Control de autorización: rechazo con HTTP 401 si el token es inválido o ausente.
- PU-INGEST-10: Control de autorización: aceptación con HTTP 200 cuando el token es válido.
- PU-INGEST-11: Recepción exitosa, entrega al MobilePushFrameBuffer y procesamiento por el coordinador (HTTP 200).
- PU-INGEST-12: Fallo de inferencia encapsulado limpiamente como VISION_ERROR por el coordinador.
- PU-INGEST-13: Rechazo de métodos HTTP no permitidos (HTTP 405).
- PU-INGEST-14: Excepciones críticas del coordinador devuelven HTTP 500 sin exponer trazas.
- PU-INGEST-15: Disponibilidad del servicio cuando el coordinador es None (HTTP 503).
- PU-INGEST-16: Modo seguro fail-closed: si no hay token configurado, rechaza peticiones de push (HTTP 503).
- PU-INGEST-33: Cambio de IP respecto al SAN del certificado existente detiene el arranque de forma segura.
- PU-INGEST-34: Regeneración explícita de certificado TLS autorizada ante cambio de IP Wi-Fi.
- PU-INGEST-35: Generación y validación atómica exitosa (manifiesto y archivos canónicos consistentes).
- PU-INGEST-36: Fallo durante la generación de clave privada preserva el par anterior y limpia temporales.
- PU-INGEST-37: Fallo durante la creación/firma del certificado preserva el par anterior y limpia temporales.
- PU-INGEST-38: Fallo en validación preventiva previo a la activación cancela y preserva el par anterior.
- PU-INGEST-39: Manejo seguro ante archivo faltante en canónico (recuperación o rechazo seguro sin mezclar pares).
- PU-INGEST-40: Activación atómica de nueva generación actualiza el manifiesto sin ventanas de inconsistencia.
- PU-INGEST-41: Arranque normal consume el par versionado activo sin regeneraciones innecesarias si es válido.
- PU-INGEST-42: Manifiesto G2 con archivos canónicos G1: resuelve par versionado G2 y sincroniza canónicos.
- PU-INGEST-43: Manifiesto G2 con par canónico cruzado/mismatched: resuelve par versionado G2 y repara canónicos.
- PU-INGEST-44: Manifiesto corrupto o incompleto es rechazado de forma segura sin fallback a canónicos.
- PU-INGEST-45: Rutas con '..' o absolutas fuera del directorio de generaciones son rechazadas (anti-traversal).
- PU-INGEST-46: Referencia a generación inexistente o archivos versionados ausentes falla de forma segura.
- PU-INGEST-47: Generación válida para IP distinta de la solicitada falla de forma segura por SAN mismatch.
- PU-INGEST-48: Compatibilidad heredada cuando no existe manifiesto y el par canónico completo es válido.
- PU-INGEST-49: Verificación de que Werkzeug recibe rutas versionadas validadas del par activo.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import unittest
from collections import namedtuple
from pathlib import Path
from typing import Any, List, Optional, Sequence
from uuid import uuid4
from unittest.mock import patch

import cv2
import numpy as np

# Asegurar raíz del repositorio en sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from VIGIA_API.ingest_service import (
    MANIFEST_FILENAME,
    create_ingest_app,
    discover_wifi_ipv4,
    generate_vigia_tls_certificate,
    get_local_ipv4_addresses,
    is_usable_ipv4,
    regenerate_vigia_tls_certificate,
    resolve_active_tls_pair,
    run_ingest_server,
    validate_listen_ip,
    validate_tls_certificate_pair,
    NetworkDiscoveryError,
    TLSConfigError,
)
from VIGIA_Core.domain.vision_result import VisionResult, VisionStatus
from VIGIA_Vision.capture.sources import MobilePushFrameBuffer, OpenCVCaptureSource
from VIGIA_Vision.config.topology_validator import (
    AreaConfigDTO,
    CameraConfigDTO,
    ITopologyConfigRepository,
    TopologyValidator,
)
from VIGIA_Vision.detection.models import BoundingBox, RawVehicleDetection
from VIGIA_Vision.runtime.coordinator import IVehicleDetector, VisionEngineCoordinator


def _create_jpeg_bytes(width: int = 320, height: int = 240, color: int = 120) -> bytes:
    """Genera bytes de una imagen JPEG sintética válida mediante OpenCV."""
    img = np.full((height, width, 3), fill_value=color, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


class StubVehicleDetector(IVehicleDetector):
    """Detector vehicular controlado para pruebas."""

    def __init__(
        self,
        detections: Sequence[RawVehicleDetection] = (),
        should_fail: bool = False,
    ) -> None:
        self.detections = tuple(detections)
        self.should_fail = should_fail

    def detect(self, frame: Any) -> Sequence[RawVehicleDetection]:
        if self.should_fail:
            raise RuntimeError("Fallo simulado en motor de inferencia.")
        return self.detections


class TestMobileIngestAPI(unittest.TestCase):
    """Pruebas unitarias de la API de ingesta móvil en memoria con test_client de Flask."""

    def setUp(self) -> None:
        self.default_auth_token = "vigia_test_token_2026"
        self.auth_headers = {"X-Camera-Key": self.default_auth_token}

        self.cam_ent_id = uuid4()
        self.cam_sal_id = uuid4()
        self.area_ent_id = uuid4()
        self.area_sal_id = uuid4()

        self.cam_ent = CameraConfigDTO(
            id_camara=self.cam_ent_id,
            codigo="CAM-ENTRADA",
            nombre="Cámara Entrada Móvil",
            uri_stream="push://cam-entrada",
            activa=True,
        )
        self.cam_sal = CameraConfigDTO(
            id_camara=self.cam_sal_id,
            codigo="CAM-SALIDA",
            nombre="Cámara Salida Fija",
            uri_stream="rtsp://fake/stream",
            activa=True,
        )
        self.area_ent = AreaConfigDTO(
            id_area_vision=self.area_ent_id,
            id_camara=self.cam_ent_id,
            codigo="ROI-ENT",
            nombre="ROI Entrada",
            tipo_movimiento="ENTRADA",
            x_min=0.1,
            y_min=0.1,
            x_max=0.9,
            y_max=0.9,
            activa=True,
        )
        self.area_sal = AreaConfigDTO(
            id_area_vision=self.area_sal_id,
            id_camara=self.cam_sal_id,
            codigo="ROI-SAL",
            nombre="ROI Salida",
            tipo_movimiento="SALIDA",
            x_min=0.1,
            y_min=0.1,
            x_max=0.9,
            y_max=0.9,
            activa=True,
        )

        class MockTopologyRepo(ITopologyConfigRepository):
            def __init__(self, c_ent, c_sal, a_ent, a_sal):
                self.c_ent = c_ent
                self.c_sal = c_sal
                self.a_ent = a_ent
                self.a_sal = a_sal

            def get_cameras(self):
                return [self.c_ent, self.c_sal]

            def get_areas(self):
                return [self.a_ent, self.a_sal]

        repo = MockTopologyRepo(self.cam_ent, self.cam_sal, self.area_ent, self.area_sal)
        self.validator = TopologyValidator(repository=repo)

        # Buffer móvil para CAM-ENTRADA y fuente dummy para CAM-SALIDA
        self.buf_entrada = MobilePushFrameBuffer("CAM-ENTRADA", ttl_seconds=5.0)
        self.buf_entrada.open()

        class DummyPullSource:
            def open(self): return True
            def is_opened(self): return True
            def read_frame(self):
                from VIGIA_Vision.detection.models import CaptureReadResult
                return CaptureReadResult(ok=False, error_reason="NO_FRAME")
            def release(self): pass

        self.detector = StubVehicleDetector(
            detections=[
                RawVehicleDetection(
                    bbox=BoundingBox(50, 50, 150, 150),
                    confidence=0.88,
                    raw_label="car",
                )
            ]
        )

        self.coordinator = VisionEngineCoordinator(
            topology_validator=self.validator,
            detector=self.detector,
            sources={"CAM-ENTRADA": self.buf_entrada, "CAM-SALIDA": DummyPullSource()},
        )
        self.coordinator.initialize(open_sources=True)

        # Flask app con token de autenticación obligatorio para pruebas base
        self.app = create_ingest_app(
            coordinator=self.coordinator,
            auth_token=self.default_auth_token,
            max_content_length=8 * 1024 * 1024,
            max_dimensions=(1920, 1080),
        )
        self.client = self.app.test_client()

    def test_pu_ingest_01_get_mobile_interface(self) -> None:
        """PU-INGEST-01: GET /mobile entrega la interfaz HTML con Content-Type text/html."""
        resp = self.client.get("/mobile")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.content_type)
        html_text = resp.data.decode("utf-8")
        self.assertIn("VIGÍA VISION SYSTEMS", html_text)
        self.assertIn("navigator.mediaDevices.getUserMedia", html_text)

    def test_pu_ingest_02_empty_payload_rejected(self) -> None:
        """PU-INGEST-02: Rechazo de solicitudes sin archivo o con cuerpo vacío (HTTP 400)."""
        resp = self.client.post("/api/v1/cameras/CAM-ENTRADA/push", headers=self.auth_headers)
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "EMPTY_PAYLOAD")

    def test_pu_ingest_03_empty_file_rejected(self) -> None:
        """PU-INGEST-03: Rechazo de archivos de imagen con 0 bytes (HTTP 400)."""
        data = {"frame": (io.BytesIO(b""), "empty.jpg")}
        resp = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=data,
            headers=self.auth_headers,
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 400)
        res_json = resp.get_json()
        self.assertFalse(res_json["ok"])
        self.assertEqual(res_json["error"], "EMPTY_FILE")

    def test_pu_ingest_04_corrupted_bytes_rejected(self) -> None:
        """PU-INGEST-04: Rechazo de bytes corruptos no decodificables con OpenCV (HTTP 422)."""
        garbage_bytes = b"ESTO NO ES UN ARCHIVO JPEG O PNG VALIDO 123456789"
        data = {"frame": (io.BytesIO(garbage_bytes), "corrupt.jpg")}
        resp = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=data,
            headers=self.auth_headers,
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 422)
        res_json = resp.get_json()
        self.assertFalse(res_json["ok"])
        self.assertEqual(res_json["error"], "DECODE_ERROR")

    def test_pu_ingest_05_excessive_dimensions_rejected(self) -> None:
        """PU-INGEST-05: Rechazo de fotogramas que exceden dimensiones máximas (HTTP 422)."""
        oversized_jpeg = _create_jpeg_bytes(width=2000, height=1200)
        data = {"frame": (io.BytesIO(oversized_jpeg), "large.jpg")}
        resp = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=data,
            headers=self.auth_headers,
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 422)
        res_json = resp.get_json()
        self.assertFalse(res_json["ok"])
        self.assertEqual(res_json["error"], "DIMENSIONS_EXCEEDED")

    def test_pu_ingest_06_excessive_payload_size_rejected(self) -> None:
        """PU-INGEST-06: Rechazo de carga útil que excede el tamaño máximo permitido (HTTP 413)."""
        small_app = create_ingest_app(
            coordinator=self.coordinator,
            auth_token=self.default_auth_token,
            max_content_length=1000,
        )
        small_client = small_app.test_client()
        jpeg_bytes = _create_jpeg_bytes(width=320, height=240)
        data = {"frame": (io.BytesIO(jpeg_bytes), "frame.jpg")}
        resp = small_client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=data,
            headers=self.auth_headers,
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 413)
        res_json = resp.get_json()
        self.assertFalse(res_json["ok"])
        self.assertEqual(res_json["error"], "PAYLOAD_TOO_LARGE")

    def test_pu_ingest_07_unregistered_camera_rejected(self) -> None:
        """PU-INGEST-07: Rechazo de solicitudes hacia cámaras no registradas (HTTP 404)."""
        jpeg_bytes = _create_jpeg_bytes()
        data = {"frame": (io.BytesIO(jpeg_bytes), "valid.jpg")}
        resp = self.client.post(
            "/api/v1/cameras/CAM-INEXISTENTE/push",
            data=data,
            headers=self.auth_headers,
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 404)
        res_json = resp.get_json()
        self.assertFalse(res_json["ok"])
        self.assertEqual(res_json["error"], "CAMERA_NOT_FOUND")

    def test_pu_ingest_08_pull_camera_rejected_for_push(self) -> None:
        """PU-INGEST-08: Rechazo de solicitudes hacia cámaras no configuradas para push móvil (HTTP 400)."""
        jpeg_bytes = _create_jpeg_bytes()
        data = {"frame": (io.BytesIO(jpeg_bytes), "valid.jpg")}
        resp = self.client.post(
            "/api/v1/cameras/CAM-SALIDA/push",  # CAM-SALIDA es pull/RTSP
            data=data,
            headers=self.auth_headers,
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 400)
        res_json = resp.get_json()
        self.assertFalse(res_json["ok"])
        self.assertEqual(res_json["error"], "CAMERA_NOT_PUSH_CAPABLE")

    def test_pu_ingest_09_unauthorized_request_rejected(self) -> None:
        """PU-INGEST-09: Rechazo con HTTP 401 si el token configurado es inválido o ausente."""
        auth_app = create_ingest_app(
            coordinator=self.coordinator,
            auth_token="secret_token_123",
        )
        auth_client = auth_app.test_client()

        # Sin encabezado
        resp = auth_client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data={"frame": (io.BytesIO(_create_jpeg_bytes()), "valid.jpg")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.get_json()["error"], "UNAUTHORIZED")

        # Con token erróneo
        resp_wrong = auth_client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data={"frame": (io.BytesIO(_create_jpeg_bytes()), "valid.jpg")},
            headers={"X-Camera-Key": "wrong_token"},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp_wrong.status_code, 401)

    def test_pu_ingest_10_authorized_request_accepted(self) -> None:
        """PU-INGEST-10: Aceptación con HTTP 200 cuando el token es correcto."""
        auth_app = create_ingest_app(
            coordinator=self.coordinator,
            auth_token="secret_token_123",
        )
        auth_client = auth_app.test_client()

        resp = auth_client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data={"frame": (io.BytesIO(_create_jpeg_bytes()), "valid.jpg")},
            headers={"X-Camera-Key": "secret_token_123"},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 200)
        res_json = resp.get_json()
        self.assertTrue(res_json["ok"])

    def test_pu_ingest_11_successful_push_and_coordinator_processing(self) -> None:
        """PU-INGEST-11: Recepción exitosa, entrega al buffer y procesamiento por el coordinador (HTTP 200)."""
        jpeg_bytes = _create_jpeg_bytes(width=640, height=480)
        data = {"frame": (io.BytesIO(jpeg_bytes), "capture.jpg")}

        resp = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=data,
            headers=self.auth_headers,
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 200)
        res = resp.get_json()

        self.assertTrue(res["ok"])
        self.assertEqual(res["codigo_camara"], "CAM-ENTRADA")
        self.assertEqual(res["frame_sequence"], 1)
        self.assertEqual(res["status"], VisionStatus.VEHICLE_DETECTED_NO_PLATE.value)
        self.assertTrue(res["vehicle_detected"])
        self.assertEqual(res["tipo_vehiculo"], "AUTOMOVIL")
        self.assertAlmostEqual(res["confianza"], 0.88, places=2)
        self.assertEqual(res["in_roi_now"], 1)

    def test_pu_ingest_12_inference_failure_produces_vision_error(self) -> None:
        """PU-INGEST-12: Fallo en inferencia es encapsulado como VISION_ERROR por el coordinador."""
        self.detector.should_fail = True
        jpeg_bytes = _create_jpeg_bytes()
        data = {"frame": (io.BytesIO(jpeg_bytes), "capture.jpg")}

        resp = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=data,
            headers=self.auth_headers,
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 200)
        res_json = resp.get_json()
        self.assertTrue(res_json["ok"])
        self.assertEqual(res_json["status"], VisionStatus.VISION_ERROR.value)
        self.assertFalse(res_json["vehicle_detected"])

    def test_pu_ingest_13_method_not_allowed_rejected(self) -> None:
        """PU-INGEST-13: Rechazo de métodos HTTP no permitidos (HTTP 405)."""
        resp = self.client.get("/api/v1/cameras/CAM-ENTRADA/push")
        self.assertEqual(resp.status_code, 405)
        self.assertEqual(resp.get_json()["error"], "METHOD_NOT_ALLOWED")

    def test_pu_ingest_14_unexpected_processing_exception_handled_cleanly(self) -> None:
        """PU-INGEST-14: Excepciones críticas del coordinador devuelven HTTP 500 sin exponer trazas."""
        from unittest.mock import patch
        with patch.object(self.coordinator, "process_camera_step", side_effect=RuntimeError("Fallo crítico de memoria")):
            jpeg_bytes = _create_jpeg_bytes()
            data = {"frame": (io.BytesIO(jpeg_bytes), "capture.jpg")}
            resp = self.client.post(
                "/api/v1/cameras/CAM-ENTRADA/push",
                data=data,
                headers=self.auth_headers,
                content_type="multipart/form-data",
            )
            self.assertEqual(resp.status_code, 500)
            res_json = resp.get_json()
            self.assertFalse(res_json["ok"])
            self.assertEqual(res_json["error"], "PROCESSING_ERROR")
            self.assertNotIn("Traceback", res_json["message"])

    def test_pu_ingest_15_coordinator_unavailable(self) -> None:
        """PU-INGEST-15: Disponibilidad del servicio cuando el coordinador es None (HTTP 503)."""
        unattached_app = create_ingest_app(
            coordinator=None,
            auth_token=self.default_auth_token,
        )
        unattached_client = unattached_app.test_client()
        jpeg_bytes = _create_jpeg_bytes()
        data = {"frame": (io.BytesIO(jpeg_bytes), "capture.jpg")}

        resp = unattached_client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=data,
            headers=self.auth_headers,
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.get_json()["error"], "ENGINE_NOT_ATTACHED")

    def test_pu_ingest_16_missing_auth_configuration_fails_closed(self) -> None:
        """PU-INGEST-16: Modo seguro fail-closed: si no hay token configurado, rechaza peticiones de push."""
        # Limpiar temporalmente variable de entorno si existe
        old_env = os.environ.pop("VIGIA_CAMERA_KEY", None)
        try:
            unconfigured_app = create_ingest_app(
                coordinator=self.coordinator,
                auth_token=None,
            )
            unconfigured_client = unconfigured_app.test_client()
            jpeg_bytes = _create_jpeg_bytes()
            data = {"frame": (io.BytesIO(jpeg_bytes), "capture.jpg")}

            resp = unconfigured_client.post(
                "/api/v1/cameras/CAM-ENTRADA/push",
                data=data,
                headers={"X-Camera-Key": "cualquier_clave"},
                content_type="multipart/form-data",
            )
            self.assertEqual(resp.status_code, 503)
            res_json = resp.get_json()
            self.assertFalse(res_json["ok"])
            self.assertEqual(res_json["error"], "AUTH_CONFIGURATION_MISSING")
        finally:
            if old_env is not None:
                os.environ["VIGIA_CAMERA_KEY"] = old_env

    def test_pu_ingest_17_generate_vigia_tls_certificate(self) -> None:
        """PU-INGEST-17: Generación de certificados TLS auto-firmados específicos de VIGÍA para contexto seguro."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_tls_test_"))
        try:
            cert_file = temp_dir / "test_cert.pem"
            key_file = temp_dir / "test_key.pem"
            target_ip = "192.168.1.120"

            c_path, k_path = generate_vigia_tls_certificate(
                target_ip=target_ip,
                cert_path=cert_file,
                key_path=key_file,
                valid_days=7,
            )

            self.assertTrue(c_path.exists())
            self.assertTrue(k_path.exists())
            self.assertGreater(c_path.stat().st_size, 500)
            self.assertGreater(k_path.stat().st_size, 500)

            # Verificar contenido del certificado
            from cryptography import x509
            cert = x509.load_pem_x509_certificate(c_path.read_bytes())
            san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            san_values = [str(name.value) for name in san.value]
            self.assertIn(target_ip, san_values)
            self.assertIn("localhost", san_values)
            self.assertIn("127.0.0.1", san_values)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_18_concurrency_atomicity(self) -> None:
        """PU-INGEST-18: Atomicidad de concurrencia: serialización estricta de push_frame y process_camera_step."""
        # Verificar que múltiples solicitudes concurrentes en hilos procesan sin solapamiento
        results: List[int] = []
        lock = threading.Lock()

        def worker(client, thread_id):
            jpeg_bytes = _create_jpeg_bytes(color=thread_id * 30 + 10)
            data = {"frame": (io.BytesIO(jpeg_bytes), f"worker_{thread_id}.jpg")}
            resp = client.post(
                "/api/v1/cameras/CAM-ENTRADA/push",
                data=data,
                headers=self.auth_headers,
                content_type="multipart/form-data",
            )
            if resp.status_code == 200 and resp.get_json().get("ok"):
                with lock:
                    results.append(resp.get_json()["frame_sequence"])

        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(self.client, i + 1))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Todas las 5 solicitudes fueron atendidas atómicamente con números de secuencia únicos
        self.assertEqual(len(results), 5)
        self.assertEqual(len(set(results)), 5)

    def test_pu_ingest_19_tls_matching_cert_and_key_accepted(self) -> None:
        """PU-INGEST-19: Aceptación preventiva de par de certificado y clave criptográfica coincidentes."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_tls_match_"))
        try:
            cert_file = temp_dir / "valid_cert.pem"
            key_file = temp_dir / "valid_key.pem"
            target_ip = "192.168.1.100"

            generate_vigia_tls_certificate(
                target_ip=target_ip,
                cert_path=cert_file,
                key_path=key_file,
                valid_days=15,
            )

            cert, key = validate_tls_certificate_pair(
                cert_path=cert_file,
                key_path=key_file,
                target_ip=target_ip,
            )
            self.assertIsNotNone(cert)
            self.assertIsNotNone(key)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_20_tls_mismatched_cert_and_key_rejected(self) -> None:
        """PU-INGEST-20: Rechazo preventivo de certificado y clave privada incompatibles."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_tls_mismatch_"))
        try:
            cert_a = temp_dir / "cert_a.pem"
            key_a = temp_dir / "key_a.pem"
            cert_b = temp_dir / "cert_b.pem"
            key_b = temp_dir / "key_b.pem"

            generate_vigia_tls_certificate("192.168.1.101", cert_a, key_a)
            generate_vigia_tls_certificate("192.168.1.102", cert_b, key_b)

            with self.assertRaises(TLSConfigError) as ctx:
                validate_tls_certificate_pair(cert_path=cert_a, key_path=key_b)
            self.assertIn("no forman un par criptográfico coincidente", str(ctx.exception))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_21_tls_expired_certificate_rejected(self) -> None:
        """PU-INGEST-21: Rechazo preventivo de certificado TLS expirado."""
        import datetime
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_tls_expired_"))
        try:
            cert_file = temp_dir / "expired_cert.pem"
            key_file = temp_dir / "expired_key.pem"

            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            now = datetime.datetime.now(datetime.timezone.utc)
            cert = (
                x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "Expired VIGIA")]))
                .issuer_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "Expired VIGIA")]))
                .public_key(key.public_key())
                .serial_number(12345)
                .not_valid_before(now - datetime.timedelta(days=10))
                .not_valid_after(now - datetime.timedelta(days=1))  # Expiró ayer
                .add_extension(
                    x509.SubjectAlternativeName([x509.DNSName("localhost")]),
                    critical=False,
                )
                .sign(key, hashes.SHA256())
            )
            cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            key_file.write_bytes(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.TraditionalOpenSSL,
                    serialization.NoEncryption(),
                )
            )

            with self.assertRaises(TLSConfigError) as ctx:
                validate_tls_certificate_pair(cert_path=cert_file, key_path=key_file)
            self.assertIn("ha expirado", str(ctx.exception))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_22_tls_missing_san_rejected(self) -> None:
        """PU-INGEST-22: Rechazo de certificado TLS que no contiene SAN para la IP de acceso configurada."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_tls_san_"))
        try:
            cert_file = temp_dir / "san_cert.pem"
            key_file = temp_dir / "san_key.pem"

            generate_vigia_tls_certificate(
                target_ip="192.168.1.50",
                cert_path=cert_file,
                key_path=key_file,
            )

            # Intentar validar para una IP diferente que no está en el SAN
            with self.assertRaises(TLSConfigError) as ctx:
                validate_tls_certificate_pair(
                    cert_path=cert_file,
                    key_path=key_file,
                    target_ip="10.200.200.1",
                )
            self.assertIn("no contiene SAN para la dirección", str(ctx.exception))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_23_tls_silent_overwrite_prevented(self) -> None:
        """PU-INGEST-23: Prevención de sobrescritura silenciosa de certificados o claves existentes."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_tls_overwrite_"))
        try:
            cert_file = temp_dir / "cert.pem"
            key_file = temp_dir / "key.pem"

            generate_vigia_tls_certificate("192.168.1.60", cert_file, key_file)

            # Intento de regeneración sin overwrite=True debe lanzar FileExistsError
            with self.assertRaises(FileExistsError) as ctx:
                generate_vigia_tls_certificate("192.168.1.60", cert_file, key_file, overwrite=False)
            self.assertIn("No se sobrescriben archivos existentes de forma silenciosa", str(ctx.exception))

            # Con overwrite=True explícito debe permitir la regeneración
            c_path, k_path = generate_vigia_tls_certificate(
                "192.168.1.60", cert_file, key_file, overwrite=True
            )
            self.assertTrue(c_path.exists())
            self.assertTrue(k_path.exists())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_24_validate_listen_ip_rejects_non_local_or_invalid(self) -> None:
        """PU-INGEST-24: Rechazo explícito de IPs que no pertenecen a interfaces locales o son inválidas."""
        # IP no perteneciente al equipo (ejemplo bloque reservado para documentación)
        with self.assertRaises(ValueError) as ctx:
            validate_listen_ip("192.0.2.1")
        self.assertIn("no pertenece a ninguna interfaz IPv4 activa", str(ctx.exception))

        # Cadena que no es dirección IP válida
        with self.assertRaises(ValueError) as ctx:
            validate_listen_ip("ip_invalida_o_nombre_host")
        self.assertIn("no es una dirección IPv4 válida", str(ctx.exception))

        # Intento de comodín 0.0.0.0 rechazado explícitamente sin sustitución silenciosa
        with self.assertRaises(ValueError) as ctx:
            validate_listen_ip("0.0.0.0")
        self.assertIn("no pertenece a ninguna interfaz IPv4 activa", str(ctx.exception))

        # Cadena vacía
        with self.assertRaises(ValueError) as ctx:
            validate_listen_ip("")
        self.assertIn("no puede ser nula ni vacía", str(ctx.exception))

    def test_pu_ingest_25_validate_listen_ip_accepts_valid_local(self) -> None:
        """PU-INGEST-25: Aceptación de IP local válida mediante prueba aislada sin alterar la red del PC."""
        # 127.0.0.1 es universalmente una interfaz local activa
        res = validate_listen_ip("127.0.0.1")
        self.assertEqual(res, "127.0.0.1")

        # Prueba aislada simulando una IP LAN asignada mediante patch
        with patch("VIGIA_API.ingest_service.get_local_ipv4_addresses", return_value={"127.0.0.1", "192.168.1.85"}):
            lan_res = validate_listen_ip("192.168.1.85")
            self.assertEqual(lan_res, "192.168.1.85")

    def test_pu_ingest_26_documentation_contains_no_literal_credentials(self) -> None:
        """PU-INGEST-26: Validación documental: ausencia estricta de credenciales operativas literales."""
        doc_path = _REPO_ROOT / "Docs" / "operaciones" / "VO-03_validacion_ingesta_movil.md"
        self.assertTrue(doc_path.exists(), f"El documento operativo debe existir en {doc_path}")

        content = doc_path.read_text(encoding="utf-8")

        # Prohibir contraseñas o secretos en texto plano en ejemplos
        self.assertNotIn("vigia_pass", content, "El documento contiene la contraseña literal 'vigia_pass'.")
        self.assertNotIn("vigia-secreto-operativo-2026", content, "El documento contiene el token literal de ejemplo.")

        # Exigir presencia de marcadores de posición estandarizados
        self.assertIn("<db_user>", content)
        self.assertIn("<db_password>", content)
        self.assertIn("<clave_de_acceso_autorizada>", content)

    def test_pu_ingest_27_discover_wifi_single_valid_interface(self) -> None:
        """PU-INGEST-27: Detección dinámica exitosa de una única interfaz Wi-Fi activa con IPv4 válida."""
        SnicAddr = namedtuple("SnicAddr", ["family", "address"])
        SnicStats = namedtuple("SnicStats", ["isup"])

        mock_addrs = {
            "Wi-Fi": [SnicAddr(family=socket.AF_INET, address="192.168.1.88")],
            "Ethernet": [SnicAddr(family=socket.AF_INET, address="192.168.1.75")],
        }
        mock_stats = {
            "Wi-Fi": SnicStats(isup=True),
            "Ethernet": SnicStats(isup=True),
        }

        with patch("psutil.net_if_addrs", return_value=mock_addrs), \
             patch("psutil.net_if_stats", return_value=mock_stats), \
             patch("VIGIA_API.ingest_service.get_windows_wlan_interfaces", return_value={"Wi-Fi": "connected"}):
            if_name, ip = discover_wifi_ipv4()
            self.assertEqual(if_name, "Wi-Fi")
            self.assertEqual(ip, "192.168.1.88")

    def test_pu_ingest_28_discover_wifi_disconnected_rejected(self) -> None:
        """PU-INGEST-28: Rechazo explícito cuando la interfaz Wi-Fi está desconectada."""
        SnicAddr = namedtuple("SnicAddr", ["family", "address"])
        SnicStats = namedtuple("SnicStats", ["isup"])

        mock_addrs = {
            "Wi-Fi": [SnicAddr(family=socket.AF_INET, address="192.168.1.88")],
        }
        mock_stats = {
            "Wi-Fi": SnicStats(isup=False),
        }

        with patch("psutil.net_if_addrs", return_value=mock_addrs), \
             patch("psutil.net_if_stats", return_value=mock_stats), \
             patch("VIGIA_API.ingest_service.get_windows_wlan_interfaces", return_value={"Wi-Fi": "disconnected"}):
            with self.assertRaises(NetworkDiscoveryError) as ctx:
                discover_wifi_ipv4()
            self.assertIn("No se encontró ninguna interfaz Wi-Fi activa", str(ctx.exception))

    def test_pu_ingest_29_discover_wifi_apipa_and_loopback_rejected(self) -> None:
        """PU-INGEST-29: Rechazo de direcciones APIPA (169.254.x.x) y loopback en adaptador Wi-Fi."""
        SnicAddr = namedtuple("SnicAddr", ["family", "address"])
        SnicStats = namedtuple("SnicStats", ["isup"])

        mock_addrs = {
            "Wi-Fi": [
                SnicAddr(family=socket.AF_INET, address="169.254.187.115"),
                SnicAddr(family=socket.AF_INET, address="127.0.0.1"),
            ],
        }
        mock_stats = {"Wi-Fi": SnicStats(isup=True)}

        with patch("psutil.net_if_addrs", return_value=mock_addrs), \
             patch("psutil.net_if_stats", return_value=mock_stats), \
             patch("VIGIA_API.ingest_service.get_windows_wlan_interfaces", return_value={"Wi-Fi": "connected"}):
            with self.assertRaises(NetworkDiscoveryError) as ctx:
                discover_wifi_ipv4()
            self.assertIn("No se encontró ninguna interfaz Wi-Fi activa", str(ctx.exception))

    def test_pu_ingest_30_discover_wifi_multiple_candidates_requires_selection(self) -> None:
        """PU-INGEST-30: Múltiples interfaces Wi-Fi candidatas detienen el arranque solicitando selección explícita."""
        SnicAddr = namedtuple("SnicAddr", ["family", "address"])
        SnicStats = namedtuple("SnicStats", ["isup"])

        mock_addrs = {
            "Wi-Fi 1": [SnicAddr(family=socket.AF_INET, address="192.168.1.10")],
            "Wi-Fi 2": [SnicAddr(family=socket.AF_INET, address="192.168.1.20")],
        }
        mock_stats = {
            "Wi-Fi 1": SnicStats(isup=True),
            "Wi-Fi 2": SnicStats(isup=True),
        }

        with patch("psutil.net_if_addrs", return_value=mock_addrs), \
             patch("psutil.net_if_stats", return_value=mock_stats), \
             patch("VIGIA_API.ingest_service.get_windows_wlan_interfaces", return_value={"Wi-Fi 1": "connected", "Wi-Fi 2": "connected"}):
            with self.assertRaises(NetworkDiscoveryError) as ctx:
                discover_wifi_ipv4()
            self.assertIn("múltiples interfaces Wi-Fi candidatas", str(ctx.exception))

    def test_pu_ingest_31_discover_wifi_preferred_selection_success(self) -> None:
        """PU-INGEST-31: Selección explícita exitosa de interfaz Wi-Fi candidata mediante parámetro o entorno."""
        SnicAddr = namedtuple("SnicAddr", ["family", "address"])
        SnicStats = namedtuple("SnicStats", ["isup"])

        mock_addrs = {
            "Wi-Fi 1": [SnicAddr(family=socket.AF_INET, address="192.168.1.10")],
            "Wi-Fi 2": [SnicAddr(family=socket.AF_INET, address="192.168.1.20")],
        }
        mock_stats = {
            "Wi-Fi 1": SnicStats(isup=True),
            "Wi-Fi 2": SnicStats(isup=True),
        }

        with patch("psutil.net_if_addrs", return_value=mock_addrs), \
             patch("psutil.net_if_stats", return_value=mock_stats), \
             patch("VIGIA_API.ingest_service.get_windows_wlan_interfaces", return_value={"Wi-Fi 1": "connected", "Wi-Fi 2": "connected"}):
            if_name, ip = discover_wifi_ipv4(preferred_interface="Wi-Fi 2")
            self.assertEqual(if_name, "Wi-Fi 2")
            self.assertEqual(ip, "192.168.1.20")

    def test_pu_ingest_32_discover_wifi_no_ethernet_fallback(self) -> None:
        """PU-INGEST-32: Ausencia estricta de sustitución automática por Ethernet cuando Wi-Fi no está disponible."""
        SnicAddr = namedtuple("SnicAddr", ["family", "address"])
        SnicStats = namedtuple("SnicStats", ["isup"])

        # Ethernet disponible y conectado, pero sin adaptador Wi-Fi conectado
        mock_addrs = {
            "Ethernet": [SnicAddr(family=socket.AF_INET, address="192.168.1.75")],
            "Wi-Fi": [SnicAddr(family=socket.AF_INET, address="192.168.1.76")],
        }
        mock_stats = {
            "Ethernet": SnicStats(isup=True),
            "Wi-Fi": SnicStats(isup=False),
        }

        with patch("psutil.net_if_addrs", return_value=mock_addrs), \
             patch("psutil.net_if_stats", return_value=mock_stats), \
             patch("VIGIA_API.ingest_service.get_windows_wlan_interfaces", return_value={"Wi-Fi": "disconnected"}):
            with self.assertRaises(NetworkDiscoveryError) as ctx:
                discover_wifi_ipv4()
            self.assertIn("sustitución automática por ethernet", str(ctx.exception).lower())

    def test_pu_ingest_33_tls_san_mismatch_on_ip_change_halts_startup(self) -> None:
        """PU-INGEST-33: Cambio de IP respecto al SAN del certificado existente detiene el arranque de forma segura."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_ip_change_"))
        try:
            c_path = temp_dir / "vigia_cert.pem"
            k_path = temp_dir / "vigia_key.pem"
            # Certificado generado originalmente para 192.168.1.50
            generate_vigia_tls_certificate("192.168.1.50", c_path, k_path)

            # La IP Wi-Fi cambió a 192.168.1.99
            with self.assertRaises(TLSConfigError) as ctx:
                validate_tls_certificate_pair(c_path, k_path, target_ip="192.168.1.99")
            self.assertIn("no contiene SAN para la dirección de acceso '192.168.1.99'", str(ctx.exception))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_34_explicit_cert_regeneration_for_new_ip(self) -> None:
        """PU-INGEST-34: Regeneración explícita de certificado TLS autorizada ante cambio de IP Wi-Fi."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_ip_regen_"))
        try:
            c_path = temp_dir / "vigia_cert.pem"
            k_path = temp_dir / "vigia_key.pem"
            generate_vigia_tls_certificate("192.168.1.50", c_path, k_path)

            # Regeneración autorizada explícita para la nueva IP
            regenerate_vigia_tls_certificate("192.168.1.99", c_path, k_path)

            cert, key = validate_tls_certificate_pair(c_path, k_path, target_ip="192.168.1.99")
            self.assertIsNotNone(cert)
            self.assertIsNotNone(key)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_35_atomic_generation_manifest_and_canonical_consistency(self) -> None:
        """PU-INGEST-35: Generación y validación atómica exitosa (manifiesto y archivos canónicos consistentes)."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_atomic_gen_"))
        try:
            c_path = temp_dir / "vigia_cert.pem"
            k_path = temp_dir / "vigia_key.pem"
            manifest_path = temp_dir / MANIFEST_FILENAME

            ret_c, ret_k = generate_vigia_tls_certificate("192.168.1.50", c_path, k_path)
            self.assertEqual(ret_c, c_path)
            self.assertEqual(ret_k, k_path)
            self.assertTrue(c_path.exists())
            self.assertTrue(k_path.exists())
            self.assertTrue(manifest_path.exists())

            # Verificar contenido del manifiesto
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIn("generation_id", manifest_data)
            self.assertEqual(manifest_data["target_ip"], "192.168.1.50")

            gen_cert = temp_dir / manifest_data["cert_relpath"]
            gen_key = temp_dir / manifest_data["key_relpath"]
            self.assertTrue(gen_cert.exists())
            self.assertTrue(gen_key.exists())

            # Archivos canónicos deben ser copias exactas del par de la generación activa
            self.assertEqual(c_path.read_bytes(), gen_cert.read_bytes())
            self.assertEqual(k_path.read_bytes(), gen_key.read_bytes())

            # Validación preventiva exitosa
            cert_obj, key_obj = validate_tls_certificate_pair(c_path, k_path, target_ip="192.168.1.50")
            self.assertIsNotNone(cert_obj)
            self.assertIsNotNone(key_obj)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_36_failure_during_key_generation_preserves_previous_pair(self) -> None:
        """PU-INGEST-36: Fallo durante la generación de clave privada preserva el par anterior y limpia temporales."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_fail_key_"))
        try:
            c_path = temp_dir / "vigia_cert.pem"
            k_path = temp_dir / "vigia_key.pem"
            manifest_path = temp_dir / MANIFEST_FILENAME

            # Generar par inicial para 192.168.1.50
            generate_vigia_tls_certificate("192.168.1.50", c_path, k_path)
            orig_cert_bytes = c_path.read_bytes()
            orig_key_bytes = k_path.read_bytes()
            orig_manifest_content = manifest_path.read_text(encoding="utf-8")

            # Simular fallo durante generación de clave privada RSA
            with patch(
                "cryptography.hazmat.primitives.asymmetric.rsa.generate_private_key",
                side_effect=RuntimeError("Fallo simulado en generación RSA"),
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    regenerate_vigia_tls_certificate("192.168.1.99", c_path, k_path)
                self.assertIn("Fallo simulado en generación RSA", str(ctx.exception))

            # Verificar que el par canónico y el manifiesto no sufrieron alteración
            self.assertEqual(c_path.read_bytes(), orig_cert_bytes)
            self.assertEqual(k_path.read_bytes(), orig_key_bytes)
            self.assertEqual(manifest_path.read_text(encoding="utf-8"), orig_manifest_content)

            # Verificar que no quedaron archivos temporales .tmp en temp_dir
            tmp_files = list(temp_dir.glob("*.tmp*"))
            self.assertEqual(len(tmp_files), 0)

            # El par previo sigue siendo 100% válido y operativo
            cert_obj, key_obj = validate_tls_certificate_pair(c_path, k_path, target_ip="192.168.1.50")
            self.assertIsNotNone(cert_obj)
            self.assertIsNotNone(key_obj)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_37_failure_during_cert_signing_preserves_previous_pair(self) -> None:
        """PU-INGEST-37: Fallo durante la creación/firma del certificado preserva el par anterior y limpia temporales."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_fail_cert_"))
        try:
            c_path = temp_dir / "vigia_cert.pem"
            k_path = temp_dir / "vigia_key.pem"
            manifest_path = temp_dir / MANIFEST_FILENAME

            generate_vigia_tls_certificate("192.168.1.50", c_path, k_path)
            orig_cert_bytes = c_path.read_bytes()
            orig_key_bytes = k_path.read_bytes()
            orig_manifest_content = manifest_path.read_text(encoding="utf-8")

            # Simular fallo durante firma x509
            with patch(
                "cryptography.x509.CertificateBuilder.sign",
                side_effect=RuntimeError("Fallo simulado al firmar certificado"),
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    regenerate_vigia_tls_certificate("192.168.1.99", c_path, k_path)
                self.assertIn("Fallo simulado al firmar certificado", str(ctx.exception))

            self.assertEqual(c_path.read_bytes(), orig_cert_bytes)
            self.assertEqual(k_path.read_bytes(), orig_key_bytes)
            self.assertEqual(manifest_path.read_text(encoding="utf-8"), orig_manifest_content)

            tmp_files = list(temp_dir.glob("*.tmp*"))
            self.assertEqual(len(tmp_files), 0)

            # Validar que el par anterior conserva su validez
            cert_obj, key_obj = validate_tls_certificate_pair(c_path, k_path, target_ip="192.168.1.50")
            self.assertIsNotNone(cert_obj)
            self.assertIsNotNone(key_obj)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_38_validation_failure_before_activation_aborts_and_preserves_previous(self) -> None:
        """PU-INGEST-38: Fallo en validación preventiva previo a la activación cancela y preserva el par anterior."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_fail_val_"))
        try:
            c_path = temp_dir / "vigia_cert.pem"
            k_path = temp_dir / "vigia_key.pem"
            manifest_path = temp_dir / MANIFEST_FILENAME

            generate_vigia_tls_certificate("192.168.1.50", c_path, k_path)
            orig_cert_bytes = c_path.read_bytes()
            orig_key_bytes = k_path.read_bytes()
            orig_manifest_content = manifest_path.read_text(encoding="utf-8")

            # Simular fallo en la validación preventiva de staging
            orig_val = validate_tls_certificate_pair

            def mock_val(cert_path, key_path, target_ip=None):
                if "generations" in str(cert_path):
                    raise TLSConfigError("Fallo simulado: SAN inconsistente en par staged")
                return orig_val(cert_path, key_path, target_ip=target_ip)

            with patch("VIGIA_API.ingest_service.validate_tls_certificate_pair", side_effect=mock_val):
                with self.assertRaises(TLSConfigError) as ctx:
                    regenerate_vigia_tls_certificate("192.168.1.99", c_path, k_path)
                self.assertIn("Fallo simulado: SAN inconsistente en par staged", str(ctx.exception))

            # Verificar que el par anterior sigue activo e inalterado
            self.assertEqual(c_path.read_bytes(), orig_cert_bytes)
            self.assertEqual(k_path.read_bytes(), orig_key_bytes)
            self.assertEqual(manifest_path.read_text(encoding="utf-8"), orig_manifest_content)

            # El par anterior sigue validando contra 192.168.1.50
            cert_obj, key_obj = validate_tls_certificate_pair(c_path, k_path, target_ip="192.168.1.50")
            self.assertIsNotNone(cert_obj)
            self.assertIsNotNone(key_obj)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_39_missing_canonical_file_safe_handling(self) -> None:
        """PU-INGEST-39: Manejo seguro ante archivo faltante en canónico (recuperación o rechazo seguro sin mezclar pares)."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_missing_canon_"))
        try:
            c_path = temp_dir / "vigia_cert.pem"
            k_path = temp_dir / "vigia_key.pem"
            manifest_path = temp_dir / MANIFEST_FILENAME

            # 1. Caso con generación activa válida: si se elimina la clave privada canónica,
            # resolve_active_tls_pair resuelve la generación activa versionada y re-sincroniza el canónico.
            generate_vigia_tls_certificate("192.168.1.50", c_path, k_path)
            orig_key_bytes = k_path.read_bytes()
            k_path.unlink()

            m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            gen_cert = temp_dir / m_data["cert_relpath"]
            gen_key = temp_dir / m_data["key_relpath"]

            self.assertFalse(k_path.exists())
            resolved_c, resolved_k = resolve_active_tls_pair(c_path, k_path, target_ip="192.168.1.50")
            self.assertTrue(k_path.exists())
            self.assertEqual(k_path.read_bytes(), orig_key_bytes)
            self.assertEqual(resolved_c, gen_cert)
            self.assertEqual(resolved_k, gen_key)

            # 2. Caso sin manifiesto ni generación: si falta un archivo y no hay generación activa,
            # falla explícitamente sin mezclar ni inventar claves.
            temp_dir2 = Path(tempfile.mkdtemp(prefix="vigia_no_manifest_"))
            try:
                c2_path = temp_dir2 / "vigia_cert.pem"
                k2_path = temp_dir2 / "vigia_key.pem"
                c2_path.write_bytes(c_path.read_bytes())
                with self.assertRaises(FileNotFoundError) as ctx:
                    resolve_active_tls_pair(c2_path, k2_path, target_ip="192.168.1.50")
                self.assertIn("vigia_key.pem", str(ctx.exception))
            finally:
                shutil.rmtree(temp_dir2, ignore_errors=True)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_40_atomic_manifest_switch_on_new_generation(self) -> None:
        """PU-INGEST-40: Activación atómica de nueva generación actualiza el manifiesto sin ventanas de inconsistencia."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_atomic_switch_"))
        try:
            c_path = temp_dir / "vigia_cert.pem"
            k_path = temp_dir / "vigia_key.pem"
            manifest_path = temp_dir / MANIFEST_FILENAME

            # Generación 1
            generate_vigia_tls_certificate("192.168.1.50", c_path, k_path)
            m1 = json.loads(manifest_path.read_text(encoding="utf-8"))
            gen_id_1 = m1["generation_id"]
            self.assertEqual(m1["target_ip"], "192.168.1.50")

            # Generación 2 (regeneración autorizada para nueva IP)
            regenerate_vigia_tls_certificate("192.168.1.99", c_path, k_path)
            m2 = json.loads(manifest_path.read_text(encoding="utf-8"))
            gen_id_2 = m2["generation_id"]

            self.assertNotEqual(gen_id_1, gen_id_2)
            self.assertEqual(m2["target_ip"], "192.168.1.99")

            # Verificar que el manifiesto apunta a los archivos de la generación 2
            gen2_cert = temp_dir / m2["cert_relpath"]
            gen2_key = temp_dir / m2["key_relpath"]
            self.assertTrue(gen2_cert.exists())
            self.assertTrue(gen2_key.exists())
            self.assertEqual(c_path.read_bytes(), gen2_cert.read_bytes())
            self.assertEqual(k_path.read_bytes(), gen2_key.read_bytes())

            # El manifiesto es un JSON válido y no quedaron archivos temporales de reemplazo
            self.assertEqual(len(list(temp_dir.glob("*.tmp*"))), 0)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_41_normal_startup_consumes_active_pair_without_unnecessary_regeneration(self) -> None:
        """PU-INGEST-41: Arranque normal consume el par versionado activo sin regeneraciones innecesarias si es válido."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_startup_active_"))
        try:
            c_path = temp_dir / "vigia_cert.pem"
            k_path = temp_dir / "vigia_key.pem"
            manifest_path = temp_dir / MANIFEST_FILENAME
            generate_vigia_tls_certificate("192.168.1.50", c_path, k_path)

            m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            gen_cert = temp_dir / m_data["cert_relpath"]
            gen_key = temp_dir / m_data["key_relpath"]

            orig_cert_bytes = c_path.read_bytes()
            orig_key_bytes = k_path.read_bytes()
            orig_c_mtime = c_path.stat().st_mtime_ns
            orig_k_mtime = k_path.stat().st_mtime_ns

            app = create_ingest_app(
                coordinator=None,
                auth_token="TEST_TOKEN",
            )

            with patch("VIGIA_API.ingest_service.run_simple") as mock_run_simple:
                run_ingest_server(
                    app=app,
                    host="192.168.1.50",
                    port=8443,
                    ssl_cert=c_path,
                    ssl_key=k_path,
                    validate_host=False,
                )

                # Werkzeug recibe las rutas versionadas de la generación activa
                mock_run_simple.assert_called_once_with(
                    hostname="192.168.1.50",
                    port=8443,
                    application=app,
                    ssl_context=(str(gen_cert), str(gen_key)),
                    threaded=True,
                )

            self.assertEqual(c_path.read_bytes(), orig_cert_bytes)
            self.assertEqual(k_path.read_bytes(), orig_key_bytes)
            self.assertEqual(c_path.stat().st_mtime_ns, orig_c_mtime)
            self.assertEqual(k_path.stat().st_mtime_ns, orig_k_mtime)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_42_manifest_g2_with_canonical_g1_resolves_g2(self) -> None:
        """PU-INGEST-42: Manifiesto G2 con archivos canónicos en G1 resuelve el par versionado G2 y re-sincroniza canónicos."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_g2_canon_g1_"))
        try:
            c_path = temp_dir / "vigia_cert.pem"
            k_path = temp_dir / "vigia_key.pem"
            manifest_path = temp_dir / MANIFEST_FILENAME

            # Generación 1 para 192.168.1.50
            generate_vigia_tls_certificate("192.168.1.50", c_path, k_path)
            g1_cert_bytes = c_path.read_bytes()
            g1_key_bytes = k_path.read_bytes()

            # Generación 2 para 192.168.1.99
            regenerate_vigia_tls_certificate("192.168.1.99", c_path, k_path)
            g2_m = json.loads(manifest_path.read_text(encoding="utf-8"))
            g2_cert = temp_dir / g2_m["cert_relpath"]
            g2_key = temp_dir / g2_m["key_relpath"]

            # Simular corte: revertir canónicos a G1
            c_path.write_bytes(g1_cert_bytes)
            k_path.write_bytes(g1_key_bytes)

            # Resolver para 192.168.1.99: debe resolver G2 y re-sincronizar canónicos
            res_c, res_k = resolve_active_tls_pair(c_path, k_path, target_ip="192.168.1.99")
            self.assertEqual(res_c, g2_cert)
            self.assertEqual(res_k, g2_key)
            self.assertEqual(c_path.read_bytes(), g2_cert.read_bytes())
            self.assertEqual(k_path.read_bytes(), g2_key.read_bytes())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_43_manifest_g2_with_mismatched_canonical_pair_resolves_g2(self) -> None:
        """PU-INGEST-43: Manifiesto G2 con par canónico cruzado (cert G2 y clave G1) resuelve G2 y auto-repara canónicos."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_cross_canon_"))
        try:
            c_path = temp_dir / "vigia_cert.pem"
            k_path = temp_dir / "vigia_key.pem"
            manifest_path = temp_dir / MANIFEST_FILENAME

            # G1
            generate_vigia_tls_certificate("192.168.1.50", c_path, k_path)
            g1_key_bytes = k_path.read_bytes()

            # G2
            regenerate_vigia_tls_certificate("192.168.1.99", c_path, k_path)
            g2_m = json.loads(manifest_path.read_text(encoding="utf-8"))
            g2_cert = temp_dir / g2_m["cert_relpath"]
            g2_key = temp_dir / g2_m["key_relpath"]

            # Simular interrupción entre el replace de cert y el replace de key: cert=G2, key=G1
            k_path.write_bytes(g1_key_bytes)
            # Asegurar que los canónicos son incompatibles entre sí
            with self.assertRaises(TLSConfigError):
                validate_tls_certificate_pair(c_path, k_path)

            # resolve_active_tls_pair NO debe fallar porque el manifiesto es la SSoT
            res_c, res_k = resolve_active_tls_pair(c_path, k_path, target_ip="192.168.1.99")
            self.assertEqual(res_c, g2_cert)
            self.assertEqual(res_k, g2_key)
            # Y los canónicos deben haber sido reparados a G2
            self.assertEqual(c_path.read_bytes(), g2_cert.read_bytes())
            self.assertEqual(k_path.read_bytes(), g2_key.read_bytes())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_44_corrupt_manifest_rejected_safely(self) -> None:
        """PU-INGEST-44: Manifiesto corrupto o incompleto es rechazado de forma segura sin fallback a canónicos."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_corrupt_m_"))
        try:
            c_path = temp_dir / "vigia_cert.pem"
            k_path = temp_dir / "vigia_key.pem"
            manifest_path = temp_dir / MANIFEST_FILENAME

            generate_vigia_tls_certificate("192.168.1.50", c_path, k_path)

            # Caso 1: JSON sintácticamente corrupto
            manifest_path.write_text("{corrupt json", encoding="utf-8")
            with self.assertRaises(TLSConfigError) as ctx1:
                resolve_active_tls_pair(c_path, k_path, target_ip="192.168.1.50")
            self.assertIn("corrupto o no es un json válido", str(ctx1.exception).lower())

            # Caso 2: Falta campo obligatorio generation_id
            manifest_path.write_text(json.dumps({"cert_relpath": "a", "key_relpath": "b"}), encoding="utf-8")
            with self.assertRaises(TLSConfigError) as ctx2:
                resolve_active_tls_pair(c_path, k_path, target_ip="192.168.1.50")
            self.assertIn("generation_id", str(ctx2.exception))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_45_path_traversal_in_manifest_rejected_safely(self) -> None:
        """PU-INGEST-45: Rutas con '..' o absolutas fuera del directorio de generaciones son rechazadas (anti-traversal)."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_traversal_"))
        try:
            c_path = temp_dir / "vigia_cert.pem"
            k_path = temp_dir / "vigia_key.pem"
            manifest_path = temp_dir / MANIFEST_FILENAME

            generate_vigia_tls_certificate("192.168.1.50", c_path, k_path)
            orig_m = json.loads(manifest_path.read_text(encoding="utf-8"))

            # Intento 1: Secuencia de escape '..'
            m_evil_1 = dict(orig_m)
            m_evil_1["cert_relpath"] = f"generations/{orig_m['generation_id']}/../../vigia_cert.pem"
            manifest_path.write_text(json.dumps(m_evil_1), encoding="utf-8")
            with self.assertRaises(TLSConfigError) as ctx1:
                resolve_active_tls_pair(c_path, k_path, target_ip="192.168.1.50")
            self.assertIn("escape de directorio", str(ctx1.exception).lower())

            # Intento 2: Ruta absoluta no autorizada
            m_evil_2 = dict(orig_m)
            m_evil_2["cert_relpath"] = "C:/Windows/System32/drivers/etc/hosts"
            manifest_path.write_text(json.dumps(m_evil_2), encoding="utf-8")
            with self.assertRaises(TLSConfigError) as ctx2:
                resolve_active_tls_pair(c_path, k_path, target_ip="192.168.1.50")
            self.assertIn("rutas absolutas no autorizadas", str(ctx2.exception).lower())

            # Intento 3: Apuntar a otra generación distinta de generation_id
            m_evil_3 = dict(orig_m)
            m_evil_3["cert_relpath"] = "generations/gen_OTRA_GENERACION/vigia_cert.pem"
            manifest_path.write_text(json.dumps(m_evil_3), encoding="utf-8")
            with self.assertRaises(TLSConfigError) as ctx3:
                resolve_active_tls_pair(c_path, k_path, target_ip="192.168.1.50")
            self.assertIn("escapan del directorio de generación autorizada", str(ctx3.exception).lower())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_46_missing_versioned_file_rejected_safely(self) -> None:
        """PU-INGEST-46: Referencia a generación inexistente o archivos versionados ausentes falla de forma segura."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_missing_ver_"))
        try:
            c_path = temp_dir / "vigia_cert.pem"
            k_path = temp_dir / "vigia_key.pem"
            manifest_path = temp_dir / MANIFEST_FILENAME

            generate_vigia_tls_certificate("192.168.1.50", c_path, k_path)
            orig_m = json.loads(manifest_path.read_text(encoding="utf-8"))
            gen_cert = temp_dir / orig_m["cert_relpath"]

            # Eliminar físicamente el certificado versionado dentro de generations/
            gen_cert.unlink()

            with self.assertRaises(FileNotFoundError) as ctx:
                resolve_active_tls_pair(c_path, k_path, target_ip="192.168.1.50")
            self.assertIn("archivo de certificado de la generación activa no encontrado", str(ctx.exception).lower())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_47_target_ip_san_mismatch_rejected_safely(self) -> None:
        """PU-INGEST-47: Generación válida para IP distinta de la solicitada falla de forma segura por SAN mismatch."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_ip_mismatch_"))
        try:
            c_path = temp_dir / "vigia_cert.pem"
            k_path = temp_dir / "vigia_key.pem"

            # Generar para 192.168.1.50
            generate_vigia_tls_certificate("192.168.1.50", c_path, k_path)

            # Intentar resolver para 192.168.1.99
            with self.assertRaises(TLSConfigError) as ctx:
                resolve_active_tls_pair(c_path, k_path, target_ip="192.168.1.99")
            self.assertIn("no contiene san para la dirección de acceso '192.168.1.99'", str(ctx.exception).lower())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_48_legacy_compatibility_without_manifest(self) -> None:
        """PU-INGEST-48: Compatibilidad heredada cuando no existe manifiesto y el par canónico completo es válido."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_legacy_mode_"))
        try:
            c_path = temp_dir / "vigia_cert.pem"
            k_path = temp_dir / "vigia_key.pem"
            manifest_path = temp_dir / MANIFEST_FILENAME

            generate_vigia_tls_certificate("192.168.1.50", c_path, k_path)

            # Eliminar manifiesto para simular entorno heredado
            manifest_path.unlink()
            self.assertFalse(manifest_path.exists())

            # Con canónicos válidos, debe resolver en modo heredado devolviendo los canónicos
            res_c, res_k = resolve_active_tls_pair(c_path, k_path, target_ip="192.168.1.50")
            self.assertEqual(res_c, c_path)
            self.assertEqual(res_k, k_path)

            # Si se elimina un archivo canónico en modo heredado, falla con FileNotFoundError
            k_path.unlink()
            with self.assertRaises(FileNotFoundError) as ctx:
                resolve_active_tls_pair(c_path, k_path, target_ip="192.168.1.50")
            self.assertIn("no se encontró un manifiesto tls activo", str(ctx.exception).lower())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pu_ingest_49_werkzeug_receives_versioned_paths(self) -> None:
        """PU-INGEST-49: Verificación de que Werkzeug recibe rutas versionadas validadas del par activo."""
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_werkzeug_ver_"))
        try:
            c_path = temp_dir / "vigia_cert.pem"
            k_path = temp_dir / "vigia_key.pem"
            manifest_path = temp_dir / MANIFEST_FILENAME

            generate_vigia_tls_certificate("192.168.1.50", c_path, k_path)
            m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            gen_cert = temp_dir / m_data["cert_relpath"]
            gen_key = temp_dir / m_data["key_relpath"]

            app = create_ingest_app(
                coordinator=None,
                auth_token="TEST_TOKEN",
            )

            with patch("VIGIA_API.ingest_service.run_simple") as mock_run_simple:
                run_ingest_server(
                    app=app,
                    host="192.168.1.50",
                    port=8443,
                    ssl_cert=c_path,
                    ssl_key=k_path,
                    validate_host=False,
                )

                # Confirmar que ssl_context son las rutas versionadas
                mock_run_simple.assert_called_once_with(
                    hostname="192.168.1.50",
                    port=8443,
                    application=app,
                    ssl_context=(str(gen_cert), str(gen_key)),
                    threaded=True,
                )
                self.assertIn("generations", mock_run_simple.call_args[1]["ssl_context"][0])
                self.assertIn("generations", mock_run_simple.call_args[1]["ssl_context"][1])
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
