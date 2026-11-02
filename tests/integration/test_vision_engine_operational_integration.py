"""
tests.integration.test_vision_engine_operational_integration
============================================================
Pruebas de integración operativa de extremo a extremo para el motor de visión
artificial conectado a VIGÍA Backend y PostgreSQL 16 (VIGIA-IMPLEMENTATION-01).

Cobertura de escenarios requeridos (Fase E):
1. PI-VISION-01: Inicialización de VisionEngineCoordinator mediante la fábrica
   explícita build_vision_engine_coordinator() contra PostgreSQL real.
2. PI-VISION-02: Validación topológica R1-R8 (aceptación de topología canónica
   y rechazo fail-fast ante violaciones topológicas sin fallback en memoria).
3. PI-VISION-03: Recepción e inyección de un fotograma válido en MobilePushFrameBuffer.
4. PI-VISION-04: Inferencia real YOLO11n sobre fotograma vehicular (bus.jpg).
5. PI-VISION-05: Filtrado geométrico ROI (inclusión dentro del ROI y exclusión
   fuera del ROI).
6. PI-VISION-06: Persistencia real de detección en tabla PostgreSQL 'deteccion'.
7. PI-VISION-07: Escritura dual de evidencias fotográficas (*_orig.jpg y *_annot.jpg).
8. PI-VISION-08: Manejo de errores (fallo de disco, fallo de BD con rollback de
   archivos, fotograma sin vehículos y deduplicación de reintentos HTTP).
9. PI-VISION-09: Prueba HTTP E2E de POST /api/v1/cameras/<codigo>/push y
   transporte seguro LAN/PKI (GET /api/v1/tls/ca.crt + X.509v3).
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List
from uuid import UUID

import cv2
import numpy as np
import psycopg2
from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID

# Asegurar raíz del repositorio en sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from VIGIA_API.ingest_service import (
    build_vision_engine_coordinator,
    create_ingest_app,
    discover_lan_ipv4,
    generate_vigia_local_ca_bundle,
    validate_private_lan_or_loopback_ip,
)
from VIGIA_Core.domain.vision_result import VisionStatus
from VIGIA_Core.repository.detection_repository import (
    DatabasePersistenceError,
    IDetectionRepository,
    PsycopgDetectionRepository,
)
from VIGIA_Core.repository.user_repository import (
    PsycopgUserRepository,
    resolve_database_dsn,
)
from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.config.psycopg_topology_repository import PsycopgTopologyConfigRepository
from VIGIA_Vision.config.topology_validator import (
    AreaConfigDTO,
    CameraConfigDTO,
    ITopologyConfigRepository,
    TopologyValidationError,
    TopologyValidator,
)
from VIGIA_Vision.detection.models import BoundingBox, RawVehicleDetection
from VIGIA_Vision.runtime.coordinator import IVehicleDetector
from VIGIA_Vision.runtime.evidence_storage import (
    EvidenceSaveResult,
    IEvidenceStorageService,
    LocalDiskEvidenceStorage,
)


class _FixedDetector(IVehicleDetector):
    """Detector determinista para pruebas controladas de filtrado geométrico ROI."""

    def __init__(self, detections: List[RawVehicleDetection]) -> None:
        self._detections = tuple(detections)

    def detect(self, frame: np.ndarray):
        return self._detections


class _FailingDetectionRepository(IDetectionRepository):
    """Repositorio que simula un fallo transaccional de PostgreSQL tras guardar evidencia."""

    def persist_detection(self, dto) -> UUID:
        raise DatabasePersistenceError(
            "[ERR_DB_SIMULATED_FAILURE] Fallo simulado al insertar en tabla deteccion."
        )


class _FailingEvidenceStorage(IEvidenceStorageService):
    """Servicio de evidencia que simula fallo de escritura en disco (saved=False)."""

    def save_evidence(
        self,
        original_frame,
        codigo_camara,
        timestamp=None,
        annotated_frame=None,
    ) -> EvidenceSaveResult:
        return EvidenceSaveResult(
            saved=False,
            original_rel_path=None,
            annotated_rel_path=None,
            error_message="Simulated disk write failure",
        )

    def rollback_evidence(self, result: EvidenceSaveResult) -> int:
        return 0


class TestVisionEngineOperationalIntegration(unittest.TestCase):
    """Suite de integración operativa entre VIGIA_API, VIGIA_Vision y PostgreSQL 16."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.dsn = resolve_database_dsn()
        try:
            conn = psycopg2.connect(cls.dsn, connect_timeout=5)
            conn.close()
        except Exception as exc:
            raise unittest.SkipTest(
                f"PostgreSQL no disponible en '{cls.dsn}': {exc}"
            )

        # Localizar pesos YOLO11n e imagen de muestra real bus.jpg
        weights_candidates = [
            _REPO_ROOT / "yolo11n.pt",
            _REPO_ROOT / "models" / "yolo11n.pt",
        ]
        cls.weights_path = next((p for p in weights_candidates if p.exists()), None)
        if cls.weights_path is None:
            raise unittest.SkipTest("Pesos yolo11n.pt no encontrados en el repositorio.")

        import ultralytics

        cls.bus_image_path = Path(ultralytics.__file__).parent / "assets" / "bus.jpg"
        if not cls.bus_image_path.exists():
            raise unittest.SkipTest("Imagen bus.jpg no encontrada en assets de ultralytics.")

        cls.bus_jpeg_bytes = cls.bus_image_path.read_bytes()

        # Generar un fotograma JPEG vacío (sin vehículos: superficie uniforme)
        empty_img = np.full((480, 640, 3), 120, dtype=np.uint8)
        ok, buf = cv2.imencode(".jpg", empty_img)
        assert ok
        cls.empty_jpeg_bytes = buf.tobytes()

        cls.user_repo = PsycopgUserRepository(cls.dsn)
        cls.topo_repo = PsycopgTopologyConfigRepository(cls.dsn)
        cls.det_repo = PsycopgDetectionRepository(cls.dsn)

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="vigia_test_evidencias_"))
        self.settings = VisionEngineSettings(
            vehicle_confidence_threshold=0.70,
            mobile_frame_ttl_seconds=3.0,
            evidence_directory=self.temp_dir,
            save_annotated_evidence=True,
            jpeg_quality=90,
            fail_fast_on_invalid_topology=True,
        )
        self.storage = LocalDiskEvidenceStorage(
            base_directory=self.temp_dir,
            jpeg_quality=90,
        )
        self.created_detection_ids: List[str] = []

    def tearDown(self) -> None:
        # Eliminar filas de prueba insertadas en la tabla deteccion
        if self.created_detection_ids:
            with psycopg2.connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM deteccion WHERE id_deteccion = ANY(%s::uuid[]);",
                        (self.created_detection_ids,),
                    )
                conn.commit()
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_pi_vision_01_coordinator_initialization_and_composition(self) -> None:
        """1. Inicialización del coordinador con dependencias reales y apertura de buffers."""
        coordinator = build_vision_engine_coordinator(
            topology_repository=self.topo_repo,
            detection_repository=self.det_repo,
            evidence_storage=self.storage,
            settings=self.settings,
            yolo_weights_path=self.weights_path,
            open_sources=True,
        )
        try:
            self.assertTrue(coordinator.is_initialized)
            self.assertIsNotNone(coordinator.active_topology)
            self.assertEqual(
                set(coordinator.registry.registered_camera_codes),
                {"CAM-ENTRADA", "CAM-SALIDA"},
            )
            slot_ent = coordinator.registry.get_slot("CAM-ENTRADA")
            slot_sal = coordinator.registry.get_slot("CAM-SALIDA")
            self.assertTrue(slot_ent.source.is_opened())
            self.assertTrue(slot_sal.source.is_opened())
        finally:
            coordinator.shutdown()
            self.assertFalse(coordinator.is_initialized)

    def test_pi_vision_02_topological_validation_r1_r8_and_fail_fast(self) -> None:
        """2. Validación topológica R1-R8: éxito canónico y rechazo fail-fast ante topología inválida."""
        validator = TopologyValidator(repository=self.topo_repo)
        val_res = validator.validate()
        self.assertTrue(val_res.is_valid)
        self.assertIsNotNone(val_res.topology)
        self.assertEqual(val_res.topology.cam_entrada.codigo, "CAM-ENTRADA")
        self.assertEqual(val_res.topology.cam_salida.codigo, "CAM-SALIDA")

        # Caso negativo: repositorio sin cámaras debe abortar el arranque (Regla R1)
        class _EmptyTopoRepo(ITopologyConfigRepository):
            def get_cameras(self) -> List[CameraConfigDTO]:
                return []

            def get_areas(self) -> List[AreaConfigDTO]:
                return []

        with self.assertRaises(TopologyValidationError) as ctx:
            build_vision_engine_coordinator(
                topology_repository=_EmptyTopoRepo(),
                detection_repository=self.det_repo,
                evidence_storage=self.storage,
                settings=self.settings,
                yolo_weights_path=self.weights_path,
                open_sources=True,
            )
        self.assertIn("ERR_CAM_ENTRADA_FALTANTE", str(ctx.exception))

    def test_pi_vision_03_valid_frame_reception_in_push_buffer(self) -> None:
        """3. Recepción de un fotograma válido en MobilePushFrameBuffer a través del registro."""
        coordinator = build_vision_engine_coordinator(
            topology_repository=self.topo_repo,
            detection_repository=self.det_repo,
            evidence_storage=self.storage,
            settings=self.settings,
            yolo_weights_path=self.weights_path,
            open_sources=True,
        )
        try:
            slot = coordinator.registry.get_slot("CAM-ENTRADA")
            frame = cv2.imread(str(self.bus_image_path))
            seq = slot.source.push_frame(frame)
            self.assertEqual(seq, 1)
            read_res = slot.source.read_frame()
            self.assertTrue(read_res.ok)
            self.assertEqual(read_res.frame_sequence, 1)
            self.assertEqual(read_res.frame.shape, frame.shape)
        finally:
            coordinator.shutdown()

    def test_pi_vision_04_06_07_yolo_inference_evidence_and_postgres_persistence(self) -> None:
        """4, 6 y 7. Inferencia real YOLO11n, escritura de evidencias y persistencia en PostgreSQL."""
        coordinator = build_vision_engine_coordinator(
            topology_repository=self.topo_repo,
            detection_repository=self.det_repo,
            evidence_storage=self.storage,
            settings=self.settings,
            yolo_weights_path=self.weights_path,
            open_sources=True,
        )
        try:
            slot = coordinator.registry.get_slot("CAM-ENTRADA")
            frame = cv2.imread(str(self.bus_image_path))
            slot.source.push_frame(frame)

            envelope = coordinator.process_camera_step(
                "CAM-ENTRADA", persist_as_new_event=True
            )
            self.assertIsNotNone(envelope)
            vr = envelope.vision_result
            self.assertEqual(vr.status, VisionStatus.VEHICLE_DETECTED_NO_PLATE)
            self.assertTrue(vr.vehicle_detected)
            self.assertGreaterEqual(vr.vehicle_confidence, 0.70)
            self.assertEqual(vr.vehicle_type_pred, "AUTOBUS")

            # 7. Verificar escritura física de *_orig.jpg y *_annot.jpg
            self.assertIsNotNone(envelope.original_evidence_path)
            self.assertIsNotNone(envelope.annotated_evidence_path)
            orig_file = self.temp_dir / envelope.original_evidence_path
            annot_file = self.temp_dir / envelope.annotated_evidence_path
            self.assertTrue(orig_file.is_file(), f"No existe archivo original: {orig_file}")
            self.assertTrue(annot_file.is_file(), f"No existe archivo anotado: {annot_file}")
            self.assertGreater(orig_file.stat().st_size, 1000)
            self.assertGreater(annot_file.stat().st_size, 1000)

            # 6. Verificar registro persistido en tabla PostgreSQL 'deteccion'
            self.assertIsNotNone(envelope.id_deteccion)
            det_id_str = str(envelope.id_deteccion)
            self.created_detection_ids.append(det_id_str)

            with psycopg2.connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id_area_vision::text, confianza_vehiculo::float,
                               tipo_vehiculo_pred::text, ruta_evidencia_foto
                        FROM deteccion
                        WHERE id_deteccion = %s::uuid;
                        """,
                        (det_id_str,),
                    )
                    row = cur.fetchone()

            self.assertIsNotNone(row, "La detección no fue encontrada en PostgreSQL.")
            db_area_id, db_conf, db_tipo, db_ruta = row
            self.assertEqual(db_area_id, str(envelope.id_area_vision))
            self.assertAlmostEqual(db_conf, round(vr.vehicle_confidence, 3), places=3)
            # Mapeo canónico DOC-01: AUTOBUS -> OTRO en PostgreSQL
            self.assertEqual(db_tipo, "OTRO")
            self.assertEqual(db_ruta, envelope.original_evidence_path)
        finally:
            coordinator.shutdown()

    def test_pi_vision_05_roi_filtering_inside_vs_outside(self) -> None:
        """5. Filtrado ROI: vehículo fuera del ROI [0.1, 0.2, 0.9, 0.8] es descartado y no persiste."""
        # En un frame 640x480, el ROI [0.1, 0.2, 0.9, 0.8] equivale a x=[64..576], y=[96..384].
        # Detección en esquina superior izquierda (x=[5..45], y=[5..45]) -> centroide (25, 25) fuera del ROI.
        outside_detection = RawVehicleDetection(
            bbox=BoundingBox(x_min=5, y_min=5, x_max=45, y_max=45),
            confidence=0.92,
            raw_label="car",
        )
        coordinator = build_vision_engine_coordinator(
            topology_repository=self.topo_repo,
            detection_repository=self.det_repo,
            evidence_storage=self.storage,
            detector=_FixedDetector([outside_detection]),
            settings=self.settings,
            open_sources=True,
        )
        try:
            slot = coordinator.registry.get_slot("CAM-ENTRADA")
            slot.source.push_frame(np.zeros((480, 640, 3), dtype=np.uint8))

            envelope = coordinator.process_camera_step(
                "CAM-ENTRADA", persist_as_new_event=True
            )
            self.assertIsNotNone(envelope)
            self.assertEqual(envelope.vision_result.status, VisionStatus.NO_VEHICLE_DETECTED)
            self.assertEqual(envelope.metrics.excluded_outside_roi, 1)
            self.assertIsNone(envelope.id_deteccion)
            self.assertIsNone(envelope.annotated_evidence_path)
        finally:
            coordinator.shutdown()

    def test_pi_vision_08_error_handling_rollback_and_storage_failure(self) -> None:
        """8. Manejo de errores (BD con rollback de evidencia y fallo de almacenamiento en disco)."""
        # 8a. Fallo de persistencia en PostgreSQL debe eliminar archivos de evidencia y devolver HTTP 500
        failing_db_coord = build_vision_engine_coordinator(
            topology_repository=self.topo_repo,
            detection_repository=_FailingDetectionRepository(),
            evidence_storage=self.storage,
            settings=self.settings,
            yolo_weights_path=self.weights_path,
            open_sources=True,
        )
        failing_app = create_ingest_app(
            coordinator=failing_db_coord,
            user_repository=self.user_repo,
            topology_repository=self.topo_repo,
            allow_in_memory=False,
            auth_token="TEST_PUSH_SECRET_2026",
        )
        client_fail = failing_app.test_client()
        try:
            resp_fail = client_fail.post(
                "/api/v1/cameras/CAM-ENTRADA/push",
                data=self.bus_jpeg_bytes,
                headers={
                    "Content-Type": "image/jpeg",
                    "X-Camera-Key": "TEST_PUSH_SECRET_2026",
                },
            )
            self.assertEqual(resp_fail.status_code, 500)
            fail_json = resp_fail.get_json()
            self.assertFalse(fail_json["ok"])
            self.assertEqual(fail_json["error"], "PERSISTENCE_ERROR")
            self.assertFalse(fail_json["detection_persisted"])
            self.assertFalse(fail_json["evidence_saved"])
            self.assertIsNone(fail_json["id_deteccion"])

            # Verificar que el rollback limpió los archivos JPEG del directorio temporal
            leftover_jpgs = list(self.temp_dir.rglob("*.jpg"))
            self.assertEqual(
                len(leftover_jpgs),
                0,
                f"El rollback ante fallo de BD debía eliminar evidencias huérfanas: {leftover_jpgs}",
            )
        finally:
            failing_db_coord.shutdown()

        # 8b. Fallo de almacenamiento en disco (STORAGE_ERROR) reporta HTTP 500 y detection_persisted=False
        failing_storage_coord = build_vision_engine_coordinator(
            topology_repository=self.topo_repo,
            detection_repository=self.det_repo,
            evidence_storage=_FailingEvidenceStorage(),
            settings=self.settings,
            yolo_weights_path=self.weights_path,
            open_sources=True,
        )
        storage_fail_app = create_ingest_app(
            coordinator=failing_storage_coord,
            user_repository=self.user_repo,
            topology_repository=self.topo_repo,
            allow_in_memory=False,
            auth_token="TEST_PUSH_SECRET_2026",
        )
        client_storage_fail = storage_fail_app.test_client()
        try:
            resp_sf = client_storage_fail.post(
                "/api/v1/cameras/CAM-ENTRADA/push",
                data=self.bus_jpeg_bytes,
                headers={
                    "Content-Type": "image/jpeg",
                    "X-Camera-Key": "TEST_PUSH_SECRET_2026",
                },
            )
            self.assertEqual(resp_sf.status_code, 500)
            sf_json = resp_sf.get_json()
            self.assertFalse(sf_json["ok"])
            self.assertEqual(sf_json["error"], "STORAGE_ERROR")
            self.assertFalse(sf_json["detection_persisted"])
            self.assertFalse(sf_json["evidence_saved"])
            if sf_json.get("id_deteccion"):
                self.created_detection_ids.append(sf_json["id_deteccion"])
        finally:
            failing_storage_coord.shutdown()

    def test_pi_vision_09_http_ingest_endpoint_e2e_and_tls_ca_bundle(self) -> None:
        """9. Prueba HTTP E2E del endpoint de ingesta (detección, frame vacío, deduplicación) y CA local."""
        coordinator = build_vision_engine_coordinator(
            topology_repository=self.topo_repo,
            detection_repository=self.det_repo,
            evidence_storage=self.storage,
            settings=self.settings,
            yolo_weights_path=self.weights_path,
            open_sources=True,
        )
        app = create_ingest_app(
            coordinator=coordinator,
            user_repository=self.user_repo,
            topology_repository=self.topo_repo,
            allow_in_memory=False,
            auth_token="TEST_PUSH_SECRET_2026",
        )
        client = app.test_client()
        try:
            # 9a. Envío HTTP real con vehículo (bus.jpg) -> HTTP 200 + persistencia en BD + evidencia
            resp = client.post(
                "/api/v1/cameras/CAM-ENTRADA/push",
                data=self.bus_jpeg_bytes,
                headers={
                    "Content-Type": "image/jpeg",
                    "X-Camera-Key": "TEST_PUSH_SECRET_2026",
                    "X-Idempotency-Key": "frame-bus-001",
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["ok"])
            self.assertEqual(data["codigo_camara"], "CAM-ENTRADA")
            self.assertEqual(data["codigo_area"], "ROI-ENT")
            self.assertEqual(data["tipo_movimiento"], "ENTRADA")
            self.assertEqual(data["status"], "VEHICLE_DETECTED_NO_PLATE")
            self.assertTrue(data["vehicle_detected"])
            self.assertTrue(data["detection_persisted"])
            self.assertTrue(data["evidence_saved"])
            self.assertFalse(data["duplicate_retry"])
            self.assertIsNotNone(data["id_deteccion"])
            self.created_detection_ids.append(data["id_deteccion"])

            # Verificar archivos en disco
            self.assertTrue((self.temp_dir / data["original_evidence_path"]).is_file())
            self.assertTrue((self.temp_dir / data["annotated_evidence_path"]).is_file())

            # 9b. Reintento HTTP con misma clave de idempotencia -> no duplica registro en BD
            retry_resp = client.post(
                "/api/v1/cameras/CAM-ENTRADA/push",
                data=self.bus_jpeg_bytes,
                headers={
                    "Content-Type": "image/jpeg",
                    "X-Camera-Key": "TEST_PUSH_SECRET_2026",
                    "X-Idempotency-Key": "frame-bus-001",
                },
            )
            self.assertEqual(retry_resp.status_code, 200)
            retry_data = retry_resp.get_json()
            self.assertTrue(retry_data["ok"])
            self.assertTrue(retry_data["duplicate_retry"])
            self.assertFalse(retry_data["detection_persisted"])
            self.assertEqual(retry_data["id_deteccion"], data["id_deteccion"])

            # 9c. Fotograma sin vehículos -> NO_VEHICLE_DETECTED, no persiste ni guarda evidencia
            empty_resp = client.post(
                "/api/v1/cameras/CAM-SALIDA/push",
                data=self.empty_jpeg_bytes,
                headers={
                    "Content-Type": "image/jpeg",
                    "X-Camera-Key": "TEST_PUSH_SECRET_2026",
                },
            )
            self.assertEqual(empty_resp.status_code, 200)
            empty_data = empty_resp.get_json()
            self.assertTrue(empty_data["ok"])
            self.assertEqual(empty_data["status"], "NO_VEHICLE_DETECTED")
            self.assertFalse(empty_data["detection_persisted"])
            self.assertFalse(empty_data["evidence_saved"])
            self.assertIsNone(empty_data["id_deteccion"])

            # 9d. Transporte seguro: generación de CA local de 2 niveles y descarga en /api/v1/tls/ca.crt
            _if_name, lan_ip = discover_lan_ipv4()
            validate_private_lan_or_loopback_ip(lan_ip)
            ca_dir = self.temp_dir / "certs"
            srv_cert_path, srv_key_path, ca_crt_path = generate_vigia_local_ca_bundle(
                lan_ip, cert_dir=ca_dir
            )
            app.config["CERTS_DIR"] = ca_dir

            ca_resp = client.get("/api/v1/tls/ca.crt")
            self.assertEqual(ca_resp.status_code, 200)
            self.assertIn(b"BEGIN CERTIFICATE", ca_resp.data)

            # Validar extensiones X.509v3 del certificado de servidor firmado por la CA
            srv_cert = x509.load_pem_x509_certificate(srv_cert_path.read_bytes())
            bc = srv_cert.extensions.get_extension_for_oid(
                ExtensionOID.BASIC_CONSTRAINTS
            ).value
            self.assertFalse(bc.ca)
            eku = srv_cert.extensions.get_extension_for_oid(
                ExtensionOID.EXTENDED_KEY_USAGE
            ).value
            self.assertIn(ExtendedKeyUsageOID.SERVER_AUTH, list(eku))
        finally:
            coordinator.shutdown()


if __name__ == "__main__":
    unittest.main()
