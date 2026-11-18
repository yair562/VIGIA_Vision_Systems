"""
tests.unit.test_usb_camera_integration
====================================
Suite integral de pruebas unitarias y de integración real para VIGIA-USB-02
(integración backend de cámaras USB locales reutilizando captura, inferencia y streaming).

Cubre:
1. Normalización de fuentes USB (`usb://N`, `N`, `"N"`) en `OpenCVCaptureSource` y `provision_topology.py`.
2. Sondeo seguro sin doble apertura cuando un worker USB ya gestiona un índice (`probe_local_usb_cameras`).
3. Ciclo de vida de `CameraPullWorker` y `CameraPullWorkerManager`:
   - Reutilización de `VisionEngineCoordinator.process_camera_step()` sin duplicar YOLO/ROI/persistencia.
   - Publicación de fotogramas anotados en `_latest_camera_frames`.
   - Prevención de workers duplicados por carril o mismo índice físico.
   - Desconexión física en caliente, purga de frames obsoletos y recuperación tras reconexión.
   - Liberación determinista de recursos al detener o revocar.
4. Persistencia y reglas fail-safe en `PsycopgPairingRepository` (sin revocación silenciosa).
5. Endpoints Flask (`/api/v1/devices/usb-cameras`, `/api/v1/devices/usb/enroll`,
   `/api/v1/devices/<id>/revoke`, recuperación automática en arranque, conmutación USB <-> Móvil).
6. Prueba real de captura física con cámara USB local (si existe hardware conectado en el host).
"""

from __future__ import annotations

import datetime
import io
import json
import os
import secrets
import shutil
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

from VIGIA_API.ingest_service import _latest_camera_frames, create_ingest_app
from VIGIA_API.usb_worker import CameraPullWorkerManager
from VIGIA_Core.domain.pairing import (
    ActiveDeviceDTO,
    CameraCredentialDTO,
    PairingRequestDTO,
    PairingRequestState,
)
from VIGIA_Core.domain.user import UserDTO
from VIGIA_Core.repository.detection_repository import DetectionInsertDTO
from VIGIA_Core.repository.pairing_repository import (
    ActiveCredentialConflictError,
    PsycopgPairingRepository,
    hash_token_sha256,
)
from VIGIA_Core.repository.user_repository import InMemoryUserRepository
from VIGIA_Core.security.password_hasher import hash_password
from VIGIA_Vision.capture.registry import BoundCameraSlot, CameraSourceRegistry
from VIGIA_Vision.capture.sources import (
    MobilePushFrameBuffer,
    OpenCVCaptureSource,
    parse_usb_source_uri,
    probe_local_usb_cameras,
)
from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.config.topology_validator import (
    AreaConfigDTO,
    CameraConfigDTO,
    ITopologyConfigRepository,
    TopologyValidator,
)
from VIGIA_Vision.detection.models import BoundingBox, RawVehicleDetection
from VIGIA_Vision.runtime.coordinator import IVehicleDetector, VisionEngineCoordinator
from VIGIA_Vision.runtime.evidence_storage import LocalDiskEvidenceStorage

# Importar validador de provision_topology desde Software/BD/scripts/
import importlib.util

_PROVISION_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent.parent / "BD" / "scripts" / "provision_topology.py"
)
_SPEC = importlib.util.spec_from_file_location("vigia_provision_topology", _PROVISION_SCRIPT)
_PROVISION_MOD = importlib.util.module_from_spec(_SPEC)
assert _SPEC is not None and _SPEC.loader is not None
_SPEC.loader.exec_module(_PROVISION_MOD)
validate_stream_uri = _PROVISION_MOD.validate_stream_uri


def _make_bgr_frame(width: int = 640, height: int = 480, color: Tuple[int, int, int] = (30, 80, 140)) -> np.ndarray:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = color
    cv2.rectangle(img, (180, 120), (420, 320), (220, 220, 220), -1)
    return img


class FakeVideoCapture:
    """Doble determinista de cv2.VideoCapture con soporte de fallo/desconexión y reconexión."""

    def __init__(
        self,
        *,
        open_succeeds: bool = True,
        frames: Optional[List[Tuple[bool, Optional[np.ndarray]]]] = None,
        backend_name: str = "DSHOW",
    ) -> None:
        self.open_succeeds = open_succeeds
        self.frames = list(frames) if frames is not None else [(True, _make_bgr_frame())]
        self.backend_name = backend_name
        self._opened = bool(open_succeeds)
        self.release_calls = 0
        self.read_calls = 0
        self.set_calls: List[Tuple[int, Any]] = []

    def isOpened(self) -> bool:
        return self._opened

    def open(self, *_args: Any) -> bool:
        self._opened = bool(self.open_succeeds)
        return self._opened

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        self.read_calls += 1
        if not self._opened:
            return False, None
        if len(self.frames) > 1:
            return self.frames.pop(0)
        return self.frames[0]

    def set(self, prop_id: int, val: Any) -> bool:
        self.set_calls.append((prop_id, val))
        return True

    def getBackendName(self) -> str:
        return self.backend_name

    def release(self) -> None:
        self.release_calls += 1
        self._opened = False


class StubVehicleDetector(IVehicleDetector):
    def __init__(self, detections: Sequence[RawVehicleDetection] = ()) -> None:
        self.detections = tuple(detections)
        self.calls = 0

    def detect(self, frame: Any) -> Sequence[RawVehicleDetection]:
        self.calls += 1
        return self.detections


class InMemoryDetectionRepo:
    def __init__(self) -> None:
        self.records: List[DetectionInsertDTO] = []

    def persist_detection(self, data: DetectionInsertDTO) -> UUID:
        self.records.append(data)
        return uuid4()


class MutableTopologyRepo(ITopologyConfigRepository):
    def __init__(self, cam_ent: CameraConfigDTO, cam_sal: CameraConfigDTO, area_ent: AreaConfigDTO, area_sal: AreaConfigDTO) -> None:
        self.cameras: Dict[str, CameraConfigDTO] = {
            cam_ent.codigo: cam_ent,
            cam_sal.codigo: cam_sal,
        }
        self.areas: List[AreaConfigDTO] = [area_ent, area_sal]

    def get_cameras(self) -> List[CameraConfigDTO]:
        return list(self.cameras.values())

    def get_all_cameras(self) -> List[CameraConfigDTO]:
        return list(self.cameras.values())

    def get_areas(self) -> List[AreaConfigDTO]:
        return list(self.areas)

    def update_uri(self, codigo: str, new_uri: str) -> None:
        cam = self.cameras[codigo]
        self.cameras[codigo] = CameraConfigDTO(
            id_camara=cam.id_camara,
            codigo=cam.codigo,
            nombre=cam.nombre,
            uri_stream=new_uri,
            activa=cam.activa,
        )


class InMemoryPairingRepo:
    """Repositorio en memoria fiel a las restricciones ACID del DDL V004 para pruebas unitarias de API."""

    def __init__(self, topo_repo: MutableTopologyRepo) -> None:
        self._topo = topo_repo
        self._lock = threading.RLock()
        self.requests: Dict[UUID, PairingRequestDTO] = {}
        self.credentials: Dict[UUID, CameraCredentialDTO] = {}
        self._raw_tokens_by_id: Dict[UUID, str] = {}

    def _find_cam_by_id(self, id_camara: UUID) -> CameraConfigDTO:
        for cam in self._topo.get_cameras():
            if cam.id_camara == id_camara:
                return cam
        raise KeyError(id_camara)

    def create_pairing_request(
        self,
        *,
        id_camara: UUID,
        token_claim_hash: str,
        creado_por: UUID,
        ttl_minutes: int = 10,
    ) -> PairingRequestDTO:
        with self._lock:
            now = datetime.datetime.now(datetime.timezone.utc)
            req = PairingRequestDTO(
                id_solicitud=uuid4(),
                id_camara=id_camara,
                token_claim_hash=token_claim_hash,
                token_poll_hash=None,
                estado=PairingRequestState.CREADA,
                dispositivo_info=None,
                creado_por=creado_por,
                resuelto_por=None,
                motivo_rechazo=None,
                creado_en=now,
                expira_en=now + datetime.timedelta(minutes=ttl_minutes),
                reclamado_en=None,
                resuelto_en=None,
                consumido_en=None,
                cancelado_en=None,
            )
            self.requests[req.id_solicitud] = req
            return req

    def claim_pairing_request(
        self,
        *,
        token_claim_hash: str,
        token_poll_hash: str,
        dispositivo_info: Dict[str, Any],
    ) -> PairingRequestDTO:
        with self._lock:
            now = datetime.datetime.now(datetime.timezone.utc)
            for rid, r in self.requests.items():
                if r.token_claim_hash == token_claim_hash and r.estado == PairingRequestState.CREADA:
                    upd = PairingRequestDTO(
                        id_solicitud=r.id_solicitud,
                        id_camara=r.id_camara,
                        token_claim_hash=r.token_claim_hash,
                        token_poll_hash=token_poll_hash,
                        estado=PairingRequestState.PENDIENTE,
                        dispositivo_info=dispositivo_info,
                        creado_por=r.creado_por,
                        resuelto_por=None,
                        motivo_rechazo=None,
                        creado_en=r.creado_en,
                        expira_en=r.expira_en,
                        reclamado_en=now,
                        resuelto_en=None,
                        consumido_en=None,
                        cancelado_en=None,
                    )
                    self.requests[rid] = upd
                    return upd
            raise ValueError("TOKEN_NOT_FOUND")

    def approve_and_issue_credential(
        self,
        *,
        id_solicitud: UUID,
        aprobado_por: UUID,
        token_transmision_hash: str,
        credencial_cifrada: str,
        clave_cifrado_id: str = "v1-plain-token",
    ) -> Tuple[PairingRequestDTO, CameraCredentialDTO]:
        with self._lock:
            now = datetime.datetime.now(datetime.timezone.utc)
            req = self.requests[id_solicitud]
            upd_req = PairingRequestDTO(
                id_solicitud=req.id_solicitud,
                id_camara=req.id_camara,
                token_claim_hash=req.token_claim_hash,
                token_poll_hash=req.token_poll_hash,
                estado=PairingRequestState.APROBADA,
                dispositivo_info=req.dispositivo_info,
                creado_por=req.creado_por,
                resuelto_por=aprobado_por,
                motivo_rechazo=None,
                creado_en=req.creado_en,
                expira_en=req.expira_en,
                reclamado_en=req.reclamado_en,
                resuelto_en=now,
                consumido_en=None,
                cancelado_en=None,
            )
            self.requests[id_solicitud] = upd_req

            for cid, c in list(self.credentials.items()):
                if c.id_camara == req.id_camara and c.activa:
                    self.credentials[cid] = CameraCredentialDTO(
                        id_credencial=c.id_credencial,
                        id_camara=c.id_camara,
                        id_solicitud=c.id_solicitud,
                        token_transmision_hash=c.token_transmision_hash,
                        clave_cifrado_id=c.clave_cifrado_id,
                        credencial_cifrada=c.credencial_cifrada,
                        intentos_entrega=c.intentos_entrega,
                        entregado_en=c.entregado_en,
                        activa=False,
                        revocado_por=aprobado_por,
                        motivo_revocacion="Sustituida por nueva aprobacion de enrolamiento",
                        creado_en=c.creado_en,
                        activado_en=c.activado_en,
                        revocado_en=now,
                    )

            cred = CameraCredentialDTO(
                id_credencial=uuid4(),
                id_camara=req.id_camara,
                id_solicitud=id_solicitud,
                token_transmision_hash=token_transmision_hash,
                clave_cifrado_id=clave_cifrado_id,
                credencial_cifrada=credencial_cifrada,
                intentos_entrega=0,
                entregado_en=None,
                activa=True,
                revocado_por=None,
                motivo_revocacion=None,
                creado_en=now,
                activado_en=now,
                revocado_en=None,
            )
            self.credentials[cred.id_credencial] = cred
            return upd_req, cred

    def enroll_usb_device(
        self,
        *,
        id_camara: UUID,
        codigo_camara: str,
        device_index: int,
        device_name: str,
        creado_por: UUID,
        dispositivo_info: Dict[str, Any],
        replace_active: bool = False,
    ) -> Tuple[PairingRequestDTO, CameraCredentialDTO]:
        with self._lock:
            now = datetime.datetime.now(datetime.timezone.utc)
            existing = next(
                (c for c in self.credentials.values() if c.id_camara == id_camara and c.activa),
                None,
            )
            if existing is not None:
                if not replace_active:
                    req_prev = self.requests.get(existing.id_solicitud)
                    ext_info = req_prev.dispositivo_info if req_prev and req_prev.dispositivo_info else {}
                    ext_name = ext_info.get("nombre") or "Dispositivo activo"
                    raise ActiveCredentialConflictError(
                        f"La cámara '{codigo_camara}' ya tiene un dispositivo activo ('{ext_name}').",
                        existing_info={"id_credencial": str(existing.id_credencial), "nombre_dispositivo": ext_name},
                    )
                self.credentials[existing.id_credencial] = CameraCredentialDTO(
                    id_credencial=existing.id_credencial,
                    id_camara=existing.id_camara,
                    id_solicitud=existing.id_solicitud,
                    token_transmision_hash=existing.token_transmision_hash,
                    clave_cifrado_id=existing.clave_cifrado_id,
                    credencial_cifrada=existing.credencial_cifrada,
                    intentos_entrega=existing.intentos_entrega,
                    entregado_en=existing.entregado_en,
                    activa=False,
                    revocado_por=creado_por,
                    motivo_revocacion="Sustituida explícitamente por cámara USB local",
                    creado_en=existing.creado_en,
                    activado_en=existing.activado_en,
                    revocado_en=now,
                )

            req = PairingRequestDTO(
                id_solicitud=uuid4(),
                id_camara=id_camara,
                token_claim_hash=hash_token_sha256(f"usb_claim_{secrets.token_urlsafe(16)}"),
                token_poll_hash=None,
                estado=PairingRequestState.CONSUMIDA,
                dispositivo_info=dispositivo_info,
                creado_por=creado_por,
                resuelto_por=creado_por,
                motivo_rechazo=None,
                creado_en=now,
                expira_en=now + datetime.timedelta(minutes=10),
                reclamado_en=now,
                resuelto_en=now,
                consumido_en=now,
                cancelado_en=None,
            )
            self.requests[req.id_solicitud] = req

            cred = CameraCredentialDTO(
                id_credencial=uuid4(),
                id_camara=id_camara,
                id_solicitud=req.id_solicitud,
                token_transmision_hash=hash_token_sha256(f"usb_tok_{secrets.token_urlsafe(16)}"),
                clave_cifrado_id="usb-local-pull",
                credencial_cifrada=None,
                intentos_entrega=0,
                entregado_en=now,
                activa=True,
                revocado_por=None,
                motivo_revocacion=None,
                creado_en=now,
                activado_en=now,
                revocado_en=None,
            )
            self.credentials[cred.id_credencial] = cred
            self._topo.update_uri(codigo_camara, f"usb://{int(device_index)}")
            return req, cred

    def get_credential_details(self, id_credencial: UUID) -> Optional[Dict[str, Any]]:
        with self._lock:
            cred = self.credentials.get(id_credencial)
            if cred is None:
                return None
            cam = self._find_cam_by_id(cred.id_camara)
            req = self.requests.get(cred.id_solicitud)
            d_info = req.dispositivo_info if req and req.dispositivo_info else {}
            is_usb = (
                cred.clave_cifrado_id == "usb-local-pull"
                or cam.uri_stream.lower().startswith("usb://")
                or d_info.get("modo") == "pull_usb"
            )
            return {
                "id_credencial": cred.id_credencial,
                "id_camara": cred.id_camara,
                "activa": cred.activa,
                "clave_cifrado_id": cred.clave_cifrado_id,
                "codigo_camara": cam.codigo,
                "nombre_camara": cam.nombre,
                "uri_stream": cam.uri_stream,
                "dispositivo_info": d_info,
                "is_usb": is_usb,
            }

    def revoke_credential_and_restore_lane(
        self,
        *,
        id_credencial: UUID,
        revocado_por: UUID,
        motivo: str = "Revocación manual",
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            cred = self.credentials.get(id_credencial)
            if cred is None or not cred.activa:
                return None
            now = datetime.datetime.now(datetime.timezone.utc)
            self.credentials[id_credencial] = CameraCredentialDTO(
                id_credencial=cred.id_credencial,
                id_camara=cred.id_camara,
                id_solicitud=cred.id_solicitud,
                token_transmision_hash=cred.token_transmision_hash,
                clave_cifrado_id=cred.clave_cifrado_id,
                credencial_cifrada=cred.credencial_cifrada,
                intentos_entrega=cred.intentos_entrega,
                entregado_en=cred.entregado_en,
                activa=False,
                revocado_por=revocado_por,
                motivo_revocacion=motivo,
                creado_en=cred.creado_en,
                activado_en=cred.activado_en,
                revocado_en=now,
            )
            cam = self._find_cam_by_id(cred.id_camara)
            req = self.requests.get(cred.id_solicitud)
            d_info = req.dispositivo_info if req and req.dispositivo_info else {}
            is_usb = (
                cred.clave_cifrado_id == "usb-local-pull"
                or cam.uri_stream.lower().startswith("usb://")
                or d_info.get("modo") == "pull_usb"
            )
            restored = f"push://{cam.codigo.lower()}"
            if is_usb:
                self._topo.update_uri(cam.codigo, restored)
            return {
                "id_credencial": id_credencial,
                "id_camara": cam.id_camara,
                "codigo_camara": cam.codigo,
                "is_usb": is_usb,
                "restored_uri": restored if is_usb else cam.uri_stream,
            }

    def revoke_credential(self, *, id_credencial: UUID, revocado_por: UUID, motivo: str = "") -> bool:
        return (
            self.revoke_credential_and_restore_lane(
                id_credencial=id_credencial, revocado_por=revocado_por, motivo=motivo
            )
            is not None
        )

    def restore_push_uri(self, *, id_camara: UUID, codigo_camara: str) -> str:
        target = f"push://{codigo_camara.strip().lower()}"
        self._topo.update_uri(codigo_camara.strip().upper(), target)
        return target

    def validate_stream_token(self, *, codigo_camara: str, token_transmision: str) -> bool:
        t_hash = hash_token_sha256(token_transmision)
        with self._lock:
            for cred in self.credentials.values():
                if not cred.activa or cred.clave_cifrado_id == "usb-local-pull":
                    continue
                cam = self._find_cam_by_id(cred.id_camara)
                if cam.codigo == codigo_camara and cam.activa and cred.token_transmision_hash == t_hash:
                    return True
            return False

    def list_active_devices(self) -> List[ActiveDeviceDTO]:
        with self._lock:
            out: List[ActiveDeviceDTO] = []
            for cred in self.credentials.values():
                cam = self._find_cam_by_id(cred.id_camara)
                req = self.requests.get(cred.id_solicitud)
                d_info = req.dispositivo_info if req else None
                name = (d_info or {}).get("nombre") or f"Dispositivo {cam.codigo}"
                out.append(
                    ActiveDeviceDTO(
                        id_credencial=cred.id_credencial,
                        id_camara=cred.id_camara,
                        codigo_camara=cam.codigo,
                        nombre_camara=cam.nombre,
                        nombre_dispositivo=name,
                        dispositivo_info=d_info,
                        activado_en=cred.activado_en,
                        activa=cred.activa,
                        ultima_actividad=None,
                    )
                )
            return out

    def get_pending_requests(self) -> List[PairingRequestDTO]:
        with self._lock:
            return [r for r in self.requests.values() if r.estado == PairingRequestState.PENDIENTE]


def _build_test_topology():
    cam_ent_id = uuid4()
    cam_sal_id = uuid4()
    cam_ent = CameraConfigDTO(cam_ent_id, "CAM-ENTRADA", "Entrada Principal", "push://cam-entrada", True)
    cam_sal = CameraConfigDTO(cam_sal_id, "CAM-SALIDA", "Salida Vehicular", "push://cam-salida", True)
    area_ent = AreaConfigDTO(uuid4(), cam_ent_id, "ROI-ENT", "Área Entrada", "ENTRADA", 0.1, 0.1, 0.9, 0.9, True)
    area_sal = AreaConfigDTO(uuid4(), cam_sal_id, "ROI-SAL", "Área Salida", "SALIDA", 0.1, 0.1, 0.9, 0.9, True)
    return MutableTopologyRepo(cam_ent, cam_sal, area_ent, area_sal)


class TestUsbUriNormalizationAndProvision(unittest.TestCase):
    """Pruebas de normalización de URI `usb://` e índices en OpenCVCaptureSource y provision_topology."""

    def test_parse_usb_source_uri_variants(self) -> None:
        self.assertEqual(parse_usb_source_uri(0), (0, True))
        self.assertEqual(parse_usb_source_uri(3), (3, True))
        self.assertEqual(parse_usb_source_uri("0"), (0, True))
        self.assertEqual(parse_usb_source_uri("  2 "), (2, True))
        self.assertEqual(parse_usb_source_uri("usb://0"), (0, True))
        self.assertEqual(parse_usb_source_uri("USB://1/"), (1, True))
        self.assertEqual(parse_usb_source_uri("rtsp://192.168.1.10/stream"), ("rtsp://192.168.1.10/stream", False))

    def test_parse_usb_source_uri_rejects_malformed(self) -> None:
        for bad in ("", "   ", "usb://", "usb://abc", "usb://-1", -1, True):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_usb_source_uri(bad)

    def test_provision_topology_validate_stream_uri_usb_and_compat(self) -> None:
        self.assertEqual(validate_stream_uri("0", "CAM-ENTRADA"), "usb://0")
        self.assertEqual(validate_stream_uri("usb://2/", "CAM-ENTRADA"), "usb://2")
        self.assertEqual(validate_stream_uri("USB://0", "CAM-SALIDA"), "usb://0")
        self.assertEqual(validate_stream_uri("push://cam-entrada", "CAM-ENTRADA"), "push://cam-entrada")
        self.assertEqual(validate_stream_uri("rtsp://10.0.0.2/live", "CAM-SALIDA"), "rtsp://10.0.0.2/live")
        with self.assertRaises(ValueError):
            validate_stream_uri("usb://invalido", "CAM-ENTRADA")


class TestOpenCvUsbSourceAndProbing(unittest.TestCase):
    """Verifica ciclo de vida lazy, get_last_frame y sondeo seguro sin doble apertura."""

    def test_lazy_init_last_frame_and_release_cleanup(self) -> None:
        frame = _make_bgr_frame()
        fake_cap = FakeVideoCapture(frames=[(True, frame)])
        src = OpenCVCaptureSource("usb://0", capture_factory=lambda idx: fake_cap)
        self.assertTrue(src.is_usb)
        self.assertEqual(src.source_uri, 0)
        self.assertEqual(src.raw_source_uri, "usb://0")
        self.assertFalse(src.is_opened())
        self.assertEqual(src.get_last_frame(), (0, None))

        self.assertTrue(src.open())
        res = src.read_frame()
        self.assertTrue(res.ok)
        self.assertEqual(res.frame_sequence, 1)
        seq, cached = src.get_last_frame()
        self.assertEqual(seq, 1)
        self.assertIsNotNone(cached)

        src.release()
        self.assertFalse(src.is_opened())
        self.assertEqual(src.get_last_frame(), (1, None))
        self.assertEqual(fake_cap.release_calls, 1)
        # Idempotente
        src.release()
        self.assertEqual(fake_cap.release_calls, 1)

    def test_probe_skips_active_indices_and_releases_probed_descriptors(self) -> None:
        opened_calls: List[int] = []
        created_caps: List[FakeVideoCapture] = []

        def fake_cv_capture(idx: int, *_args: Any) -> FakeVideoCapture:
            opened_calls.append(idx)
            cap = FakeVideoCapture(open_succeeds=(idx == 1), backend_name="DSHOW")
            cap.get = MagicMock(side_effect=lambda prop: 1280 if prop == cv2.CAP_PROP_FRAME_WIDTH else 720)
            created_caps.append(cap)
            return cap

        with patch("cv2.VideoCapture", side_effect=fake_cv_capture):
            found = probe_local_usb_cameras(
                max_index=3,
                active_indices={0: {"codigo_camara": "CAM-ENTRADA", "resolution": "640x480", "backend": "DSHOW"}},
            )

        # El índice 0 NO debe haberse intentado abrir por cv2.VideoCapture porque ya tiene worker activo
        self.assertNotIn(0, opened_calls)
        self.assertIn(1, opened_calls)
        self.assertIn(2, opened_calls)

        by_idx = {item["device_index"]: item for item in found}
        self.assertEqual(by_idx[0]["in_use_by_camera"], "CAM-ENTRADA")
        self.assertEqual(by_idx[1]["in_use_by_camera"], None)
        self.assertEqual(by_idx[1]["resolution"], "1280x720")
        self.assertTrue(all(c.release_calls >= 1 for c in created_caps))


class TestCameraPullWorker(unittest.TestCase):
    """Pruebas unitarias y de concurrencia para CameraPullWorker y CameraPullWorkerManager."""

    def setUp(self) -> None:
        _latest_camera_frames.clear()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="vigia_usb_worker_"))
        self.topo = _build_test_topology()
        self.det_repo = InMemoryDetectionRepo()
        self.detector = StubVehicleDetector(
            detections=[RawVehicleDetection(bbox=BoundingBox(150, 120, 420, 320), confidence=0.91, raw_label="car")]
        )
        self.fake_cap = FakeVideoCapture(open_succeeds=True, frames=[(True, _make_bgr_frame())])
        self.usb_src = OpenCVCaptureSource("usb://0", capture_factory=lambda _i: self.fake_cap)
        self.push_src = MobilePushFrameBuffer("CAM-SALIDA", ttl_seconds=5.0)
        self.coordinator = VisionEngineCoordinator(
            topology_validator=TopologyValidator(self.topo),
            settings=VisionEngineSettings(evidence_directory=self.temp_dir, vehicle_confidence_threshold=0.70),
            detector=self.detector,
            detection_repository=self.det_repo,
            evidence_storage=LocalDiskEvidenceStorage(base_directory=self.temp_dir),
            sources={"CAM-ENTRADA": self.usb_src, "CAM-SALIDA": self.push_src},
        )
        self.coordinator.initialize(open_sources=True)

        self.conds: Dict[str, threading.Condition] = {}
        self.locks: Dict[str, threading.RLock] = {}
        self.persist_states: Dict[str, Dict[str, Any]] = {}
        self.last_ts: Dict[str, float] = {}

        self.mgr = CameraPullWorkerManager(
            latest_frames_store=_latest_camera_frames,
            get_condition_fn=lambda c: self.conds.setdefault(c, threading.Condition()),
            get_process_lock_fn=lambda c: self.locks.setdefault(c, threading.RLock()),
            camera_persist_states=self.persist_states,
            last_persist_timestamps=self.last_ts,
            get_debounce_ttl_fn=lambda: 5.0,
        )

    def tearDown(self) -> None:
        self.mgr.stop_all(clear_frames=True, timeout=3.0)
        self.coordinator.shutdown()
        _latest_camera_frames.clear()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_worker_reuses_coordinator_publishes_live_frame_and_debounces_persistence(self) -> None:
        self.mgr.start_worker(
            codigo_camara="CAM-ENTRADA",
            coordinator=self.coordinator,
            device_index=0,
            target_fps=20.0,
        )
        deadline = time.time() + 3.0
        while "CAM-ENTRADA" not in _latest_camera_frames and time.time() < deadline:
            time.sleep(0.05)

        self.assertIn("CAM-ENTRADA", _latest_camera_frames)
        time.sleep(0.25)  # Varios ciclos adicionales bajo ventana de debounce de 5.0s

        info = _latest_camera_frames["CAM-ENTRADA"]
        self.assertTrue(info["jpeg"].startswith(b"\xff\xd8"))
        self.assertTrue(info["vehicle_detected"])
        self.assertEqual(info["tipo_vehiculo"], "AUTOMOVIL")
        self.assertGreaterEqual(self.detector.calls, 2)
        # Debounce evita inundar PostgreSQL: exactamente 1 detección persistida en ventana de 5s
        self.assertEqual(len(self.det_repo.records), 1)

        # Al detener el worker, purga frames obsoletos y libera hardware
        self.assertTrue(self.mgr.stop_worker("CAM-ENTRADA", clear_frames=True))
        self.assertNotIn("CAM-ENTRADA", _latest_camera_frames)
        self.assertFalse(self.usb_src.is_opened())
        self.assertGreaterEqual(self.fake_cap.release_calls, 1)

    def test_worker_manager_rejects_same_physical_device_across_lanes(self) -> None:
        self.mgr.start_worker(
            codigo_camara="CAM-ENTRADA",
            coordinator=self.coordinator,
            device_index=0,
            target_fps=10.0,
        )
        with self.assertRaises(RuntimeError):
            self.mgr.start_worker(
                codigo_camara="CAM-SALIDA",
                coordinator=self.coordinator,
                device_index=0,
                target_fps=10.0,
            )

    def test_worker_disconnect_clears_stale_frame_releases_and_recovers(self) -> None:
        # 2 frames válidos -> luego 5 fallos (purga live + release físico) -> reconexión automática
        seq_frames: List[Tuple[bool, Optional[np.ndarray]]] = [
            (True, _make_bgr_frame()),
            (True, _make_bgr_frame()),
            (False, None),
            (False, None),
            (False, None),
            (False, None),
            (False, None),
            (True, _make_bgr_frame()),
        ]
        reconn_cap = FakeVideoCapture(open_succeeds=False, frames=seq_frames)
        state_flags = {"open_attempts": 0, "cleared_before_reopen": False}

        def _reconnecting_factory(_idx: Any) -> FakeVideoCapture:
            state_flags["open_attempts"] += 1
            if state_flags["open_attempts"] >= 2:
                state_flags["cleared_before_reopen"] = "CAM-ENTRADA" not in _latest_camera_frames
            reconn_cap.open_succeeds = True
            reconn_cap.open()
            return reconn_cap

        reconn_src = OpenCVCaptureSource("usb://0", capture_factory=_reconnecting_factory)
        slot = self.coordinator.registry.get_slot("CAM-ENTRADA")
        self.coordinator.registry.register_slot(
            BoundCameraSlot(camera=slot.camera, area=slot.area, source=reconn_src)
        )

        self.mgr.start_worker(
            codigo_camara="CAM-ENTRADA",
            coordinator=self.coordinator,
            device_index=0,
            target_fps=25.0,
            reconnect_interval_seconds=0.2,
        )

        deadline = time.time() + 5.0
        recovered = False
        while time.time() < deadline:
            if (
                reconn_cap.release_calls >= 1
                and state_flags["open_attempts"] >= 2
                and "CAM-ENTRADA" in _latest_camera_frames
                and reconn_cap.read_calls >= 8
            ):
                recovered = True
                break
            time.sleep(0.05)

        self.assertTrue(recovered, "El worker debe liberar tras fallos consecutivos y recuperar la captura al reconectar.")
        self.assertTrue(state_flags["cleared_before_reopen"], "Los frames obsoletos deben purgarse al detectar pérdida de señal.")
        self.assertIn("CAM-ENTRADA", _latest_camera_frames)


class TestPairingRepositoryUsbSqlContracts(unittest.TestCase):
    """Verifica el SQL emitido y protección anti-push/conflictos en PsycopgPairingRepository."""

    def test_enroll_usb_conflict_aborts_without_silent_revoke(self) -> None:
        executed_sql: List[str] = []

        class MockCur:
            def __init__(self) -> None:
                self._res = {
                    "id_credencial": uuid4(),
                    "clave_cifrado_id": "v1-plain-token",
                    "dispositivo_info": {"nombre": "iPhone Guardia"},
                }

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, sql, params=None):
                executed_sql.append(sql)

            def fetchone(self):
                return self._res

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor = MagicMock(return_value=MockCur())

        repo = PsycopgPairingRepository("postgresql://fake/db")
        with patch.object(repo, "_get_connection", return_value=mock_conn):
            with self.assertRaises(ActiveCredentialConflictError):
                repo.enroll_usb_device(
                    id_camara=uuid4(),
                    codigo_camara="CAM-ENTRADA",
                    device_index=0,
                    device_name="Webcam USB",
                    creado_por=uuid4(),
                    dispositivo_info={"nombre": "Webcam USB", "modo": "pull_usb", "device_index": 0},
                    replace_active=False,
                )

        # Solo se ejecutó SELECT ... FOR UPDATE; no UPDATE ni INSERT destructivos
        self.assertEqual(len(executed_sql), 1)
        self.assertIn("FOR UPDATE", executed_sql[0])

    def test_validate_stream_token_excludes_usb_credentials(self) -> None:
        captured: List[str] = []

        class MockCur:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, sql, params=None):
                captured.append(sql)

            def fetchone(self):
                return None

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor = MagicMock(return_value=MockCur())

        repo = PsycopgPairingRepository("postgresql://fake/db")
        with patch.object(repo, "_get_connection", return_value=mock_conn):
            ok = repo.validate_stream_token(codigo_camara="CAM-ENTRADA", token_transmision="vigia_st_fake")
        self.assertFalse(ok)
        self.assertIn("clave_cifrado_id <> 'usb-local-pull'", captured[0])


class TestUsbFlaskEndpoints(unittest.TestCase):
    """Pruebas E2E Flask de endpoints USB, RBAC, conflictos, revocación y compatibilidad móvil."""

    def setUp(self) -> None:
        _latest_camera_frames.clear()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="vigia_usb_api_"))
        self.certs_dir = self.temp_dir / "certs"
        self.certs_dir.mkdir(parents=True, exist_ok=True)
        self.topo = _build_test_topology()
        self.pairing_repo = InMemoryPairingRepo(self.topo)
        self.det_repo = InMemoryDetectionRepo()
        self.detector = StubVehicleDetector(
            detections=[RawVehicleDetection(bbox=BoundingBox(150, 120, 420, 320), confidence=0.89, raw_label="truck")]
        )
        self.coordinator = VisionEngineCoordinator(
            topology_validator=TopologyValidator(self.topo),
            settings=VisionEngineSettings(evidence_directory=self.temp_dir),
            detector=self.detector,
            detection_repository=self.det_repo,
            evidence_storage=LocalDiskEvidenceStorage(base_directory=self.temp_dir),
        )
        self.coordinator.initialize(open_sources=True)

        self.user_repo = InMemoryUserRepository()
        self.admin_id = uuid4()
        self.guardia_id = uuid4()
        self.user_repo.create_user(
            UserDTO(
                id_usuario=self.admin_id,
                username="admin_usb",
                contrasena_hash=hash_password("AdminUsb123!"),
                nombre_completo="Admin USB",
                rol="ADMINISTRADOR",
                activo=True,
            )
        )
        self.user_repo.create_user(
            UserDTO(
                id_usuario=self.guardia_id,
                username="guardia_usb",
                contrasena_hash=hash_password("GuardiaUsb123!"),
                nombre_completo="Guardia USB",
                rol="OPERADOR",
                activo=True,
            )
        )

        self.app = create_ingest_app(
            coordinator=self.coordinator,
            auth_token="test_cam_key",
            user_repository=self.user_repo,
            topology_repository=self.topo,
            pairing_repository=self.pairing_repo,
            allow_in_memory=True,
            certs_dir=self.certs_dir,
        )
        self.app.config["TESTING"] = True
        self.app.config["USB_TARGET_FPS"] = 20.0
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        usb_mgr: CameraPullWorkerManager = self.app.config["USB_WORKER_MANAGER"]
        usb_mgr.stop_all(clear_frames=True, timeout=3.0)
        self.coordinator.shutdown()
        _latest_camera_frames.clear()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _login(self, client, username: str, password: str) -> None:
        resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
        self.assertEqual(resp.status_code, 200)

    def test_rbac_and_validation_on_usb_endpoints(self) -> None:
        self.app.config["USB_PROBE_FN"] = lambda **_kw: [
            {"device_index": 0, "uri": "usb://0", "name": "Mock Webcam 0", "resolution": "640x480", "available": True, "in_use_by_camera": None}
        ]
        # Sin autenticar -> 401
        self.assertEqual(self.client.get("/api/v1/devices/usb-cameras").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/devices/usb/enroll", json={"codigo_camara": "CAM-ENTRADA", "device_index": 0}).status_code, 401)

        # Rol GUARDIA puede listar USB (200), pero no enrolar (403)
        self._login(self.client, "guardia_usb", "GuardiaUsb123!")
        resp_list = self.client.get("/api/v1/devices/usb-cameras")
        self.assertEqual(resp_list.status_code, 200)
        self.assertEqual(resp_list.get_json()["total"], 1)

        resp_enroll_guard = self.client.post("/api/v1/devices/usb/enroll", json={"codigo_camara": "CAM-ENTRADA", "device_index": 0})
        self.assertEqual(resp_enroll_guard.status_code, 403)

        # Rol ADMINISTRADOR con índice inválido -> 400
        admin_client = self.app.test_client()
        self._login(admin_client, "admin_usb", "AdminUsb123!")
        for bad_idx in (-1, "abc", None, True):
            r_bad = admin_client.post("/api/v1/devices/usb/enroll", json={"codigo_camara": "CAM-ENTRADA", "device_index": bad_idx})
            self.assertEqual(r_bad.status_code, 400)

    def test_enroll_conflict_replacement_device_exclusion_stream_and_revoke(self) -> None:
        caps_by_idx: Dict[int, FakeVideoCapture] = {}

        def mock_source_factory(idx: int) -> OpenCVCaptureSource:
            def _cap_factory(_u):
                cap = FakeVideoCapture(open_succeeds=(idx != 9), frames=[(True, _make_bgr_frame())])
                caps_by_idx[idx] = cap
                return cap

            return OpenCVCaptureSource(f"usb://{idx}", capture_factory=_cap_factory)

        self.app.config["USB_SOURCE_FACTORY"] = mock_source_factory

        admin_client = self.app.test_client()
        self._login(admin_client, "admin_usb", "AdminUsb123!")

        # 1. Enrolar un teléfono móvil previo en CAM-ENTRADA (compatibilidad QR intacta)
        qr_res = admin_client.post("/api/v1/devices/pairing-qr", json={"codigo_camara": "CAM-ENTRADA"}).get_json()
        claim_res = self.app.test_client().post(
            "/api/v1/mobile/pairing/claim",
            json={"claim_token": qr_res["claim_token"], "device_name": "Teléfono Entrada"},
        ).get_json()
        mobile_token = claim_res["stream_token"]
        self.assertTrue(self.pairing_repo.validate_stream_token(codigo_camara="CAM-ENTRADA", token_transmision=mobile_token))

        # 2. Cámara no conectada (idx=9) con confirm_replace=True -> falla apertura (422) sin borrar móvil previo
        r_fail_open = admin_client.post(
            "/api/v1/devices/usb/enroll",
            json={"codigo_camara": "CAM-ENTRADA", "device_index": 9, "confirm_replace": True},
        )
        self.assertEqual(r_fail_open.status_code, 422)
        self.assertEqual(r_fail_open.get_json()["error"], "USB_CAMERA_OPEN_FAILED")
        self.assertTrue(self.pairing_repo.validate_stream_token(codigo_camara="CAM-ENTRADA", token_transmision=mobile_token))

        # 3. Intentar asignar USB índice 0 a CAM-ENTRADA SIN confirm_replace -> HTTP 409 ACTIVE_CREDENTIAL_CONFLICT
        r_conflict = admin_client.post(
            "/api/v1/devices/usb/enroll",
            json={"codigo_camara": "CAM-ENTRADA", "device_index": 0, "device_name": "Webcam Caseta"},
        )
        self.assertEqual(r_conflict.status_code, 409)
        self.assertEqual(r_conflict.get_json()["error"], "ACTIVE_CREDENTIAL_CONFLICT")
        self.assertTrue(self.pairing_repo.validate_stream_token(codigo_camara="CAM-ENTRADA", token_transmision=mobile_token))

        # 4. Reemplazo explícito confirm_replace=True -> HTTP 201, inicia worker e invalida token móvil previo
        r_enroll = admin_client.post(
            "/api/v1/devices/usb/enroll",
            json={
                "codigo_camara": "CAM-ENTRADA",
                "device_index": 0,
                "device_name": "Webcam Caseta Entrada",
                "confirm_replace": True,
            },
        )
        self.assertEqual(r_enroll.status_code, 201)
        enroll_data = r_enroll.get_json()
        self.assertEqual(enroll_data["uri_stream"], "usb://0")
        self.assertTrue(enroll_data["worker_started"])
        self.assertTrue(enroll_data["replaced_previous"])
        cred_id = enroll_data["id_credencial"]
        self.assertFalse(self.pairing_repo.validate_stream_token(codigo_camara="CAM-ENTRADA", token_transmision=mobile_token))

        # Esperar primer frame real del worker en /live y /status
        deadline = time.time() + 3.0
        while "CAM-ENTRADA" not in _latest_camera_frames and time.time() < deadline:
            time.sleep(0.05)

        r_status = admin_client.get("/api/v1/cameras/CAM-ENTRADA/status").get_json()
        self.assertEqual(r_status["operational_state"], "TRANSMITIENDO")
        self.assertEqual(r_status["tipo_vehiculo"], "CAMION")
        r_live = admin_client.get("/api/v1/cameras/CAM-ENTRADA/live")
        self.assertEqual(r_live.status_code, 200)
        self.assertTrue(r_live.data.startswith(b"\xff\xd8"))

        # 5. GET /api/v1/devices lista el dispositivo USB unificado
        dev_list = admin_client.get("/api/v1/devices").get_json()
        active_usb = [d for d in dev_list["devices"] if d["id_credencial"] == cred_id and d["activa"]]
        self.assertEqual(len(active_usb), 1)
        self.assertEqual(active_usb[0]["dispositivo_info"]["modo"], "pull_usb")

        # 6. Intentar usar el MISMO índice físico 0 en CAM-SALIDA (incluso con confirm_replace=True) -> HTTP 409 USB_DEVICE_IN_USE
        r_cross = admin_client.post(
            "/api/v1/devices/usb/enroll",
            json={"codigo_camara": "CAM-SALIDA", "device_index": 0, "confirm_replace": True},
        )
        self.assertEqual(r_cross.status_code, 409)
        self.assertEqual(r_cross.get_json()["error"], "USB_DEVICE_IN_USE")

        # 7. Mientras CAM-ENTRADA usa USB 0, CAM-SALIDA sigue aceptando push móvil sin interferencia
        _, jpeg_buf = cv2.imencode(".jpg", _make_bgr_frame())
        r_push_sal = self.client.post(
            "/api/v1/cameras/CAM-SALIDA/push",
            data={"frame": (io.BytesIO(jpeg_buf.tobytes()), "sal.jpg")},
            headers={"X-Camera-Key": "test_cam_key"},
            content_type="multipart/form-data",
        )
        self.assertEqual(r_push_sal.status_code, 200)

        # 8. Revocar la credencial USB detiene worker, purga _latest_camera_frames y restaura push://
        r_rev = admin_client.post(f"/api/v1/devices/{cred_id}/revoke", json={"motivo": "Prueba revocación USB"})
        self.assertEqual(r_rev.status_code, 200)
        usb_mgr: CameraPullWorkerManager = self.app.config["USB_WORKER_MANAGER"]
        self.assertFalse(usb_mgr.is_running("CAM-ENTRADA"))
        self.assertNotIn("CAM-ENTRADA", _latest_camera_frames)
        self.assertGreaterEqual(caps_by_idx[0].release_calls, 1)
        self.assertEqual(self.topo.cameras["CAM-ENTRADA"].uri_stream, "push://cam-entrada")

        # Confirmar que CAM-ENTRADA volvió a modo MobilePushFrameBuffer y acepta push móvil
        r_push_ent = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data={"frame": (io.BytesIO(jpeg_buf.tobytes()), "ent.jpg")},
            headers={"X-Camera-Key": "test_cam_key"},
            content_type="multipart/form-data",
        )
        self.assertEqual(r_push_ent.status_code, 200)

    def test_startup_recovery_of_persisted_usb_slot(self) -> None:
        # Simular arranque cuando BD tiene CAM-ENTRADA persistida como usb://0
        self.topo.update_uri("CAM-ENTRADA", "usb://0")
        usb_boot_cap = FakeVideoCapture(open_succeeds=True, frames=[(True, _make_bgr_frame())])
        usb_boot_src = OpenCVCaptureSource("usb://0", capture_factory=lambda _i: usb_boot_cap)

        boot_coord = VisionEngineCoordinator(
            topology_validator=TopologyValidator(self.topo),
            settings=VisionEngineSettings(evidence_directory=self.temp_dir),
            detector=self.detector,
            sources={"CAM-ENTRADA": usb_boot_src, "CAM-SALIDA": MobilePushFrameBuffer("CAM-SALIDA")},
        )
        boot_coord.initialize(open_sources=True)

        boot_app = create_ingest_app(
            coordinator=boot_coord,
            auth_token="boot_key",
            user_repository=self.user_repo,
            topology_repository=self.topo,
            pairing_repository=self.pairing_repo,
            allow_in_memory=True,
            certs_dir=self.certs_dir,
        )
        try:
            usb_mgr: CameraPullWorkerManager = boot_app.config["USB_WORKER_MANAGER"]
            self.assertTrue(usb_mgr.is_running("CAM-ENTRADA"))
            deadline = time.time() + 3.0
            while "CAM-ENTRADA" not in _latest_camera_frames and time.time() < deadline:
                time.sleep(0.05)
            self.assertIn("CAM-ENTRADA", _latest_camera_frames)
        finally:
            boot_app.config["USB_WORKER_MANAGER"].stop_all(clear_frames=True, timeout=3.0)
            boot_coord.shutdown()

    def test_switch_usb_back_to_mobile_qr_claim_stops_worker(self) -> None:
        caps_by_idx: Dict[int, FakeVideoCapture] = {}

        def mock_source_factory(idx: int) -> OpenCVCaptureSource:
            def _cap_factory(_u):
                cap = FakeVideoCapture(open_succeeds=True, frames=[(True, _make_bgr_frame())])
                caps_by_idx[idx] = cap
                return cap

            return OpenCVCaptureSource(f"usb://{idx}", capture_factory=_cap_factory)

        self.app.config["USB_SOURCE_FACTORY"] = mock_source_factory
        admin_client = self.app.test_client()
        self._login(admin_client, "admin_usb", "AdminUsb123!")

        r_enroll = admin_client.post(
            "/api/v1/devices/usb/enroll",
            json={"codigo_camara": "CAM-ENTRADA", "device_index": 0},
        )
        self.assertEqual(r_enroll.status_code, 201)
        usb_mgr: CameraPullWorkerManager = self.app.config["USB_WORKER_MANAGER"]
        self.assertTrue(usb_mgr.is_running("CAM-ENTRADA"))

        # Administrador genera QR para volver a usar móvil en CAM-ENTRADA y móvil reclama token
        qr_res = admin_client.post("/api/v1/devices/pairing-qr", json={"codigo_camara": "CAM-ENTRADA"}).get_json()
        claim_res = self.app.test_client().post(
            "/api/v1/mobile/pairing/claim",
            json={"claim_token": qr_res["claim_token"], "device_name": "Celular Reemplazo"},
        )
        self.assertEqual(claim_res.status_code, 200)
        stream_token = claim_res.get_json()["stream_token"]

        self.assertFalse(usb_mgr.is_running("CAM-ENTRADA"))
        self.assertGreaterEqual(caps_by_idx[0].release_calls, 1)
        self.assertEqual(self.topo.cameras["CAM-ENTRADA"].uri_stream, "push://cam-entrada")
        self.assertIsInstance(self.coordinator.registry.get_slot("CAM-ENTRADA").source, MobilePushFrameBuffer)

        _, jpeg_buf = cv2.imencode(".jpg", _make_bgr_frame())
        r_push = self.client.post(
            "/api/v1/cameras/CAM-ENTRADA/push",
            data={"frame": (io.BytesIO(jpeg_buf.tobytes()), "mob.jpg")},
            headers={"X-Camera-Key": stream_token},
            content_type="multipart/form-data",
        )
        self.assertEqual(r_push.status_code, 200)


class TestRealPhysicalUsbWebcam(unittest.TestCase):
    """
    Prueba de extremo a extremo contra la cámara USB física conectada al host Windows (si existe).
    Ejecuta flujo completo: probe -> enroll -> CameraPullWorker -> Coordinator -> /live & /status & /stream -> revoke -> liberación limpia.
    """

    def test_real_usb_webcam_end_to_end_if_present(self) -> None:
        probed = probe_local_usb_cameras(max_index=4)
        if not probed:
            self.skipTest("No se detectó ninguna cámara USB física activa en el host para la prueba hardware real.")

        target_dev = probed[0]
        dev_idx = int(target_dev["device_index"])

        _latest_camera_frames.clear()
        temp_dir = Path(tempfile.mkdtemp(prefix="vigia_real_usb_e2e_"))
        certs_dir = temp_dir / "certs"
        certs_dir.mkdir(parents=True, exist_ok=True)
        topo = _build_test_topology()
        pairing_repo = InMemoryPairingRepo(topo)
        detector = StubVehicleDetector(detections=())
        coord = VisionEngineCoordinator(
            topology_validator=TopologyValidator(topo),
            settings=VisionEngineSettings(evidence_directory=temp_dir),
            detector=detector,
            evidence_storage=LocalDiskEvidenceStorage(base_directory=temp_dir),
        )
        coord.initialize(open_sources=True)

        user_repo = InMemoryUserRepository()
        user_repo.create_user(
            UserDTO(
                id_usuario=uuid4(),
                username="admin_hw",
                contrasena_hash=hash_password("HwTest123!"),
                nombre_completo="Admin Hardware",
                rol="ADMINISTRADOR",
                activo=True,
            )
        )

        app = create_ingest_app(
            coordinator=coord,
            auth_token="hw_key",
            user_repository=user_repo,
            topology_repository=topo,
            pairing_repository=pairing_repo,
            allow_in_memory=True,
            certs_dir=certs_dir,
        )
        app.config["TESTING"] = True
        app.config["USB_TARGET_FPS"] = 10.0
        client = app.test_client()

        try:
            self.assertEqual(
                client.post("/api/v1/auth/login", json={"username": "admin_hw", "password": "HwTest123!"}).status_code,
                200,
            )

            # 1. Enrolar la cámara USB física real
            r_enroll = client.post(
                "/api/v1/devices/usb/enroll",
                json={"codigo_camara": "CAM-ENTRADA", "device_index": dev_idx, "device_name": "Cámara Física Host"},
            )
            self.assertEqual(r_enroll.status_code, 201, r_enroll.get_data(as_text=True))
            cred_id = r_enroll.get_json()["id_credencial"]

            # 2. Esperar fotogramas reales capturados desde el hardware físico
            deadline = time.time() + 6.0
            while "CAM-ENTRADA" not in _latest_camera_frames and time.time() < deadline:
                time.sleep(0.1)

            self.assertIn("CAM-ENTRADA", _latest_camera_frames, "La cámara física USB no publicó frames reales dentro del tiempo límite.")

            # 3. Verificar /status, /live y 1 chunk de /stream (MJPEG)
            r_status = client.get("/api/v1/cameras/CAM-ENTRADA/status")
            self.assertEqual(r_status.status_code, 200)
            st = r_status.get_json()
            self.assertEqual(st["operational_state"], "TRANSMITIENDO")
            self.assertIsNotNone(st["sequence"])

            r_live = client.get("/api/v1/cameras/CAM-ENTRADA/live")
            self.assertEqual(r_live.status_code, 200)
            self.assertTrue(r_live.data.startswith(b"\xff\xd8"))
            self.assertGreater(len(r_live.data), 1000)

            r_stream = client.get("/api/v1/cameras/CAM-ENTRADA/stream", buffered=False)
            self.assertEqual(r_stream.status_code, 200)
            chunk = next(r_stream.response)
            r_stream.close()
            self.assertIn(b"--frame", chunk)
            self.assertIn(b"Content-Type: image/jpeg", chunk)

            # 4. Sondeo mientras está activa NO debe fallar ni arrojar errores, reportando in_use_by_camera
            r_probe_active = client.get("/api/v1/devices/usb-cameras")
            self.assertEqual(r_probe_active.status_code, 200)
            active_items = [c for c in r_probe_active.get_json()["cameras"] if c["device_index"] == dev_idx]
            self.assertEqual(len(active_items), 1)
            self.assertEqual(active_items[0]["in_use_by_camera"], "CAM-ENTRADA")

            # 5. Revocar y confirmar liberación física limpia (permite reapertura inmediata del mismo hardware)
            slot_before_rev = coord.registry.get_slot("CAM-ENTRADA")
            r_rev = client.post(f"/api/v1/devices/{cred_id}/revoke", json={"motivo": "Fin de prueba física"})
            self.assertEqual(r_rev.status_code, 200)
            self.assertFalse(app.config["USB_WORKER_MANAGER"].is_running("CAM-ENTRADA"))
            self.assertFalse(slot_before_rev.source.is_opened())
            self.assertNotIn("CAM-ENTRADA", _latest_camera_frames)

            # Verificar reapertura física tras revocación
            reprobe = probe_local_usb_cameras(max_index=dev_idx + 1)
            self.assertTrue(any(c["device_index"] == dev_idx for c in reprobe))
        finally:
            app.config["USB_WORKER_MANAGER"].stop_all(clear_frames=True, timeout=3.0)
            coord.shutdown()
            _latest_camera_frames.clear()
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
