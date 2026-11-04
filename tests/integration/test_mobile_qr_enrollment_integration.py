"""
tests.integration.test_mobile_qr_enrollment_integration
=======================================================
Pruebas de integración E2E para el Enrolamiento Seguro de Cámaras Móviles
mediante QR (MOB-QR-01).

Cobertura de escenarios requeridos:
 1. test_01_qr_generation_by_administrador: Admin genera QR efímero en /api/v1/devices/pairing-qr.
 2. test_02_forbidden_qr_generation_for_guardia_and_unauth: Rol GUARDIA y no autenticado reciben 401/403.
 3. test_03_pairing_request_expiration_handling: Solicitud con TTL vencido es rechazada al reclamar.
 4. test_04_one_time_use_of_claim_token: El claim_token solo puede reclamarse una sola vez.
 5. test_05_rejection_of_invalid_or_tampered_claim_token: Tokens manipulados o inexistentes dan 404/400.
 6. test_06_association_to_nonexistent_camera_rejected: Código de cámara inexistente retorna 404.
 7. test_07_successful_mobile_claim_and_polling: Flujo de claim móvil y obtención de stream_token vía polling.
 8. test_08_confirmation_and_purge_of_temporary_secret: Confirmación de recepción y purga de secreto temporal.
 9. test_09_valid_push_frame_ingestion_with_individual_stream_token: Ingesta de fotograma con token individual.
10. test_10_revocation_of_device_credential: Revocación explícita por Administrador.
11. test_11_immediate_rejection_on_push_with_revoked_token: Rechazo 401 inmediato con credencial revocada.
12. test_12_invariant_single_active_credential_per_camera: Invariante de una sola credencial activa por cámara.
13. test_13_listing_devices_in_devices_endpoint: Consulta unificada de dispositivos en GET /api/v1/devices.
14. test_14_evidence_storage_and_yolo_with_enrolled_mobile: Inferencia YOLO y guardado de evidencias con credencial móvil.
15. test_15_ca_bundle_endpoint_for_mobile_tls: Endpoint GET /api/v1/tls/ca.crt devuelve bundle PEM válido.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import psycopg2

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from VIGIA_API.ingest_service import (
    build_vision_engine_coordinator,
    create_ingest_app,
    generate_vigia_local_ca_bundle,
)
from VIGIA_Core.domain.user import UserDTO
from VIGIA_Core.repository.detection_repository import PsycopgDetectionRepository
from VIGIA_Core.repository.pairing_repository import PsycopgPairingRepository, hash_token_sha256
from VIGIA_Core.repository.user_repository import (
    PsycopgUserRepository,
    resolve_database_dsn,
)
from VIGIA_Core.security.password_hasher import hash_password
from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.config.psycopg_topology_repository import PsycopgTopologyConfigRepository
from VIGIA_Vision.runtime.evidence_storage import LocalDiskEvidenceStorage


class TestMobileQREnrollmentIntegration(unittest.TestCase):
    """Suite de integración E2E para el flujo de enrolamiento seguro QR (MOB-QR-01)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.dsn = resolve_database_dsn()
        try:
            conn = psycopg2.connect(cls.dsn, connect_timeout=5)
            conn.close()
        except Exception as exc:
            raise unittest.SkipTest(f"PostgreSQL no disponible en '{cls.dsn}': {exc}")

        # Localizar pesos YOLO11n e imagen vehicular bus.jpg
        import ultralytics

        cls.bus_image_path = Path(ultralytics.__file__).parent / "assets" / "bus.jpg"
        if not cls.bus_image_path.exists():
            raise unittest.SkipTest("Imagen bus.jpg no encontrada en ultralytics.")
        cls.bus_jpeg_bytes = cls.bus_image_path.read_bytes()

        # Repositorios
        cls.user_repo = PsycopgUserRepository(cls.dsn)
        cls.topo_repo = PsycopgTopologyConfigRepository(cls.dsn)
        cls.det_repo = PsycopgDetectionRepository(cls.dsn)
        cls.pairing_repo = PsycopgPairingRepository(cls.dsn)

        # Crear usuarios de prueba con roles específicos
        cls.admin_uname = f"admin_qr_{uuid4().hex[:6]}"
        cls.admin_pwd = "PasswordAdminQR123!"
        cls.admin_id = cls.user_repo.create_user(
            UserDTO(
                username=cls.admin_uname,
                contrasena_hash=hash_password(cls.admin_pwd),
                nombre_completo="Admin Enrolamiento QR",
                rol="ADMINISTRADOR",
                activo=True,
            )
        )

        cls.guardia_uname = f"guardia_qr_{uuid4().hex[:6]}"
        cls.guardia_pwd = "PasswordGuardiaQR123!"
        cls.guardia_id = cls.user_repo.create_user(
            UserDTO(
                username=cls.guardia_uname,
                contrasena_hash=hash_password(cls.guardia_pwd),
                nombre_completo="Guardia Caseta QR",
                rol="OPERADOR",  # Rol relacional mapeado a GUARDIA
                activo=True,
            )
        )

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            with psycopg2.connect(cls.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        DELETE FROM camara_credencial
                        WHERE id_solicitud IN (
                            SELECT id_solicitud FROM camera_pairing_request WHERE creado_por IN (%s, %s)
                        );
                        DELETE FROM camera_pairing_request WHERE creado_por IN (%s, %s);
                        DELETE FROM usuario WHERE id_usuario IN (%s, %s);
                        """,
                        (
                            str(cls.admin_id),
                            str(cls.guardia_id),
                            str(cls.admin_id),
                            str(cls.guardia_id),
                            str(cls.admin_id),
                            str(cls.guardia_id),
                        ),
                    )
                conn.commit()
        except Exception as exc:
            print(f"Error en tearDownClass: {exc}")

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="vigia_qr_test_"))
        self.certs_dir = self.temp_dir / "certs"
        self.certs_dir.mkdir(parents=True, exist_ok=True)
        self.settings = VisionEngineSettings(
            vehicle_confidence_threshold=0.70,
            mobile_frame_ttl_seconds=3.0,
        )
        self.evidence_storage = LocalDiskEvidenceStorage(base_directory=self.temp_dir)
        self.coordinator = build_vision_engine_coordinator(
            dsn=self.dsn,
            evidence_storage=self.evidence_storage,
            settings=self.settings,
        )
        self.app = create_ingest_app(
            coordinator=self.coordinator,
            auth_token="TEST_PUSH_SECRET_2026",
            user_repository=self.user_repo,
            topology_repository=self.topo_repo,
            pairing_repository=self.pairing_repo,
            allow_in_memory=False,
            certs_dir=self.certs_dir,
        )
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _login(self, client, username, password) -> None:
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        self.assertEqual(resp.status_code, 200)

    # -------------------------------------------------------------------------
    # 1. Generación de QR por ADMINISTRADOR
    # -------------------------------------------------------------------------
    def test_01_qr_generation_by_administrador(self):
        self._login(self.client, self.admin_uname, self.admin_pwd)
        resp = self.client.post(
            "/api/v1/devices/pairing-qr",
            json={"codigo_camara": "CAM-ENTRADA", "ttl_minutes": 10},
        )
        self.assertIn(resp.status_code, (200, 201))
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["codigo_camara"], "CAM-ENTRADA")
        self.assertIn("claim_token", data)
        self.assertTrue(data["claim_token"].startswith("vigia_claim_"))
        self.assertIn("qr_base64_data_url", data)
        self.assertTrue(data["qr_base64_data_url"].startswith("data:image/png;base64,"))
        self.assertIn("enrollment_url", data)
        self.assertIn(data["claim_token"], data["enrollment_url"])
        self.assertIn("expira_en", data)

    # -------------------------------------------------------------------------
    # 2. Control de Acceso RBAC (GUARDIA y no autenticado)
    # -------------------------------------------------------------------------
    def test_02_forbidden_qr_generation_for_guardia_and_unauth(self):
        # Sin sesión -> 401
        unauth_resp = self.client.post(
            "/api/v1/devices/pairing-qr",
            json={"codigo_camara": "CAM-ENTRADA"},
        )
        self.assertEqual(unauth_resp.status_code, 401)

        # Con sesión GUARDIA -> 403
        self._login(self.client, self.guardia_uname, self.guardia_pwd)
        guardia_resp = self.client.post(
            "/api/v1/devices/pairing-qr",
            json={"codigo_camara": "CAM-ENTRADA"},
        )
        self.assertEqual(guardia_resp.status_code, 403)

    # -------------------------------------------------------------------------
    # 3. Expiración de Solicitud de Enrolamiento
    # -------------------------------------------------------------------------
    def test_03_pairing_request_expiration_handling(self):
        self._login(self.client, self.admin_uname, self.admin_pwd)
        gen = self.client.post(
            "/api/v1/devices/pairing-qr",
            json={"codigo_camara": "CAM-ENTRADA", "ttl_minutes": 10},
        ).get_json()
        claim_token = gen["claim_token"]

        # Forzar expira_en al pasado en base de datos
        t_hash = hash_token_sha256(claim_token)
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE camera_pairing_request
                    SET creado_en = NOW() - INTERVAL '20 minutes',
                        expira_en = NOW() - INTERVAL '5 minutes'
                    WHERE token_claim_hash = %s;
                    """,
                    (t_hash,),
                )
            conn.commit()

        # Intentar reclamar la solicitud expirada desde el móvil
        resp = self.client.post(
            "/api/v1/mobile/pairing/claim",
            json={"claim_token": claim_token, "alias_dispositivo": "Teléfono Expirado"},
        )
        self.assertIn(resp.status_code, (400, 409))
        data = resp.get_json()
        self.assertFalse(data["ok"])

    # -------------------------------------------------------------------------
    # 4. Uso de un solo uso para claim_token
    # -------------------------------------------------------------------------
    def test_04_one_time_use_of_claim_token(self):
        self._login(self.client, self.admin_uname, self.admin_pwd)
        gen_resp = self.client.post(
            "/api/v1/devices/pairing-qr",
            json={"codigo_camara": "CAM-ENTRADA", "ttl_minutes": 5},
        )
        claim_token = gen_resp.get_json()["claim_token"]

        # Primer reclamo -> exitoso
        resp1 = self.client.post(
            "/api/v1/mobile/pairing/claim",
            json={"claim_token": claim_token, "alias_dispositivo": "Pixel 8 Test"},
        )
        self.assertEqual(resp1.status_code, 200)

        # Segundo reclamo con el mismo token -> rechazado
        resp2 = self.client.post(
            "/api/v1/mobile/pairing/claim",
            json={"claim_token": claim_token, "alias_dispositivo": "Pixel 8 Intruso"},
        )
        self.assertIn(resp2.status_code, (400, 404, 409))

    # -------------------------------------------------------------------------
    # 5. Rechazo ante claim_token manipulado o inexistente
    # -------------------------------------------------------------------------
    def test_05_rejection_of_invalid_or_tampered_claim_token(self):
        resp = self.client.post(
            "/api/v1/mobile/pairing/claim",
            json={"claim_token": "vigia_claim_token_falso_invalido_12345"},
        )
        self.assertEqual(resp.status_code, 404)

        empty_resp = self.client.post(
            "/api/v1/mobile/pairing/claim",
            json={"claim_token": ""},
        )
        self.assertEqual(empty_resp.status_code, 400)

    # -------------------------------------------------------------------------
    # 6. Rechazo de cámara inexistente en generación QR
    # -------------------------------------------------------------------------
    def test_06_association_to_nonexistent_camera_rejected(self):
        self._login(self.client, self.admin_uname, self.admin_pwd)
        resp = self.client.post(
            "/api/v1/devices/pairing-qr",
            json={"codigo_camara": "CAM-FANTASMA-999"},
        )
        self.assertEqual(resp.status_code, 404)

    # -------------------------------------------------------------------------
    # 7. Reclamo móvil exitoso y sondeo (polling) de credencial
    # -------------------------------------------------------------------------
    def test_07_successful_mobile_claim_and_polling(self):
        self._login(self.client, self.admin_uname, self.admin_pwd)
        gen = self.client.post(
            "/api/v1/devices/pairing-qr",
            json={"codigo_camara": "CAM-ENTRADA"},
        ).get_json()

        # Reclamo móvil
        claim_resp = self.client.post(
            "/api/v1/mobile/pairing/claim",
            json={
                "claim_token": gen["claim_token"],
                "alias_dispositivo": "Samsung Galaxy S24 Test",
            },
        )
        self.assertEqual(claim_resp.status_code, 200)
        claim_data = claim_resp.get_json()
        req_id = claim_data["request_id"]
        poll_secret = claim_data["poll_secret"]

        # Polling de estado
        poll_resp = self.client.get(
            f"/api/v1/mobile/pairing/status?request_id={req_id}&poll_secret={poll_secret}"
        )
        self.assertEqual(poll_resp.status_code, 200)
        poll_data = poll_resp.get_json()
        self.assertTrue(poll_data["ok"])
        self.assertEqual(poll_data["status"], "ISSUED")
        self.assertIn("stream_token", poll_data)
        self.assertTrue(poll_data["stream_token"].startswith("vigia_st_"))

    # -------------------------------------------------------------------------
    # 8. Confirmación y purga del secreto temporal
    # -------------------------------------------------------------------------
    def test_08_confirmation_and_purge_of_temporary_secret(self):
        self._login(self.client, self.admin_uname, self.admin_pwd)
        gen = self.client.post(
            "/api/v1/devices/pairing-qr",
            json={"codigo_camara": "CAM-SALIDA"},
        ).get_json()

        claim = self.client.post(
            "/api/v1/mobile/pairing/claim",
            json={"claim_token": gen["claim_token"], "alias_dispositivo": "iPhone 15 Pro"},
        ).get_json()

        req_id = claim["request_id"]
        poll_secret = claim["poll_secret"]

        # Confirmación de recepción por el teléfono
        conf_resp = self.client.post(
            "/api/v1/mobile/pairing/confirm",
            json={"request_id": req_id, "poll_secret": poll_secret},
        )
        self.assertEqual(conf_resp.status_code, 200)

        # Segundo polling tras confirmación: estado CONFIRMED, stream_token purgado (None)
        poll2 = self.client.get(
            f"/api/v1/mobile/pairing/status?request_id={req_id}&poll_secret={poll_secret}"
        ).get_json()
        self.assertEqual(poll2["status"], "CONFIRMED")
        self.assertIsNone(poll2.get("stream_token"))

    # -------------------------------------------------------------------------
    # 9. Ingesta de fotograma con stream_token individual
    # -------------------------------------------------------------------------
    def test_09_valid_push_frame_ingestion_with_individual_stream_token(self):
        self._login(self.client, self.admin_uname, self.admin_pwd)
        gen = self.client.post(
            "/api/v1/devices/pairing-qr",
            json={"codigo_camara": "CAM-ENTRADA"},
        ).get_json()

        claim = self.client.post(
            "/api/v1/mobile/pairing/claim",
            json={"claim_token": gen["claim_token"], "alias_dispositivo": "Motorola Edge"},
        ).get_json()

        poll = self.client.get(
            f"/api/v1/mobile/pairing/status?request_id={claim['request_id']}&poll_secret={claim['poll_secret']}"
        ).get_json()
        stream_token = poll["stream_token"]

        # Enviar fotograma vehicular real (bus.jpg) con la clave individual
        push_resp = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=self.bus_jpeg_bytes,
            headers={
                "Content-Type": "image/jpeg",
                "X-Camera-Key": stream_token,
                "X-Idempotency-Key": f"mob-frame-{uuid4().hex[:6]}",
            },
        )
        self.assertEqual(push_resp.status_code, 200)
        data = push_resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["codigo_camara"], "CAM-ENTRADA")
        self.assertTrue(data["vehicle_detected"])
        self.assertTrue(data["detection_persisted"])
        self.assertIsNotNone(data["id_deteccion"])

    # -------------------------------------------------------------------------
    # 10. Revocación de credencial de dispositivo por Administrador
    # -------------------------------------------------------------------------
    def test_10_revocation_of_device_credential(self):
        self._login(self.client, self.admin_uname, self.admin_pwd)
        gen = self.client.post(
            "/api/v1/devices/pairing-qr",
            json={"codigo_camara": "CAM-SALIDA"},
        ).get_json()

        claim = self.client.post(
            "/api/v1/mobile/pairing/claim",
            json={"claim_token": gen["claim_token"], "alias_dispositivo": "Device to Revoke"},
        ).get_json()

        poll = self.client.get(
            f"/api/v1/mobile/pairing/status?request_id={claim['request_id']}&poll_secret={claim['poll_secret']}"
        ).get_json()
        cred_id = poll["id_credencial"]

        # Revocar dispositivo
        revoke_resp = self.client.post(
            f"/api/v1/devices/{cred_id}/revoke",
            json={"motivo": "Prueba de revocación MOB-QR-01"},
        )
        self.assertEqual(revoke_resp.status_code, 200)
        rev_data = revoke_resp.get_json()
        self.assertTrue(rev_data["ok"])

    # -------------------------------------------------------------------------
    # 11. Rechazo 401 inmediato tras revocación de credencial
    # -------------------------------------------------------------------------
    def test_11_immediate_rejection_on_push_with_revoked_token(self):
        self._login(self.client, self.admin_uname, self.admin_pwd)
        gen = self.client.post(
            "/api/v1/devices/pairing-qr",
            json={"codigo_camara": "CAM-SALIDA"},
        ).get_json()

        claim = self.client.post(
            "/api/v1/mobile/pairing/claim",
            json={"claim_token": gen["claim_token"], "alias_dispositivo": "Device Revoked Push"},
        ).get_json()

        poll = self.client.get(
            f"/api/v1/mobile/pairing/status?request_id={claim['request_id']}&poll_secret={claim['poll_secret']}"
        ).get_json()
        stream_token = poll["stream_token"]
        cred_id = poll["id_credencial"]

        # Revocar inmediatamente
        self.client.post(
            f"/api/v1/devices/{cred_id}/revoke",
            json={"motivo": "Revocación inmediata"},
        )

        # Transmitir fotograma con el token revocado -> HTTP 401
        push_resp = self.client.post(
            "/api/v1/cameras/CAM-SALIDA/push",
            data=self.bus_jpeg_bytes,
            headers={
                "Content-Type": "image/jpeg",
                "X-Camera-Key": stream_token,
            },
        )
        self.assertEqual(push_resp.status_code, 401)

    # -------------------------------------------------------------------------
    # 12. Invariante: una sola credencial activa por cámara lógica
    # -------------------------------------------------------------------------
    def test_12_invariant_single_active_credential_per_camera(self):
        self._login(self.client, self.admin_uname, self.admin_pwd)

        # Enrolar Teléfono A en CAM-ENTRADA
        gen1 = self.client.post(
            "/api/v1/devices/pairing-qr", json={"codigo_camara": "CAM-ENTRADA"}
        ).get_json()
        claim1 = self.client.post(
            "/api/v1/mobile/pairing/claim",
            json={"claim_token": gen1["claim_token"], "alias_dispositivo": "Phone A"},
        ).get_json()
        poll1 = self.client.get(
            f"/api/v1/mobile/pairing/status?request_id={claim1['request_id']}&poll_secret={claim1['poll_secret']}"
        ).get_json()
        token1 = poll1["stream_token"]

        # Enrolar Teléfono B en la misma cámara (CAM-ENTRADA)
        gen2 = self.client.post(
            "/api/v1/devices/pairing-qr", json={"codigo_camara": "CAM-ENTRADA"}
        ).get_json()
        claim2 = self.client.post(
            "/api/v1/mobile/pairing/claim",
            json={"claim_token": gen2["claim_token"], "alias_dispositivo": "Phone B"},
        ).get_json()
        poll2 = self.client.get(
            f"/api/v1/mobile/pairing/status?request_id={claim2['request_id']}&poll_secret={claim2['poll_secret']}"
        ).get_json()
        token2 = poll2["stream_token"]

        # Phone B debe transmitir con éxito
        resp_b = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=self.bus_jpeg_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": token2},
        )
        self.assertEqual(resp_b.status_code, 200)

        # Phone A debe quedar revocado automáticamente (invariante única credencial activa)
        resp_a = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=self.bus_jpeg_bytes,
            headers={"Content-Type": "image/jpeg", "X-Camera-Key": token1},
        )
        self.assertEqual(resp_a.status_code, 401)

    # -------------------------------------------------------------------------
    # 13. Listado de dispositivos en GET /api/v1/devices
    # -------------------------------------------------------------------------
    def test_13_listing_devices_in_devices_endpoint(self):
        self._login(self.client, self.admin_uname, self.admin_pwd)
        resp = self.client.get("/api/v1/devices")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("devices", data)
        self.assertIsInstance(data["devices"], list)

    # -------------------------------------------------------------------------
    # 14. Inferencia YOLO y guardado de evidencias con credencial móvil
    # -------------------------------------------------------------------------
    def test_14_evidence_storage_and_yolo_with_enrolled_mobile(self):
        self._login(self.client, self.admin_uname, self.admin_pwd)
        gen = self.client.post(
            "/api/v1/devices/pairing-qr", json={"codigo_camara": "CAM-ENTRADA"}
        ).get_json()
        claim = self.client.post(
            "/api/v1/mobile/pairing/claim",
            json={"claim_token": gen["claim_token"], "alias_dispositivo": "YOLO Evidence Tester"},
        ).get_json()
        poll = self.client.get(
            f"/api/v1/mobile/pairing/status?request_id={claim['request_id']}&poll_secret={claim['poll_secret']}"
        ).get_json()
        token = poll["stream_token"]

        push_resp = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data=self.bus_jpeg_bytes,
            headers={
                "Content-Type": "image/jpeg",
                "X-Camera-Key": token,
                "X-Idempotency-Key": f"yolo-ev-{uuid4().hex[:6]}",
            },
        )
        self.assertEqual(push_resp.status_code, 200)
        data = push_resp.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["vehicle_detected"])
        self.assertTrue(data["evidence_saved"])
        self.assertIn("original_evidence_path", data)
        self.assertIn("annotated_evidence_path", data)

        orig_path = self.temp_dir / data["original_evidence_path"]
        annot_path = self.temp_dir / data["annotated_evidence_path"]
        self.assertTrue(orig_path.is_file())
        self.assertTrue(annot_path.is_file())

    # -------------------------------------------------------------------------
    # 15. Descarga de Certificado CA para HTTPS / TLS en Móviles
    # -------------------------------------------------------------------------
    def test_15_ca_bundle_endpoint_for_mobile_tls(self):
        generate_vigia_local_ca_bundle(
            target_ip="127.0.0.1",
            cert_dir=self.app.config["CERTS_DIR"],
            overwrite=True,
        )
        resp = self.client.get("/api/v1/tls/ca.crt")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/x-x509-ca-cert")
        data_text = resp.data.decode("utf-8")
        self.assertIn("BEGIN CERTIFICATE", data_text)


if __name__ == "__main__":
    unittest.main()
