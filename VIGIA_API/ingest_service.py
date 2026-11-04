"""
VIGIA_API.ingest_service
========================
Servicio HTTP de ingesta móvil para VIGÍA Vision Systems (VO-03 / VO-03B).

Expone:
- ``GET /mobile``: Entrega la interfaz web responsiva de captura física.
- ``POST /api/v1/cameras/<codigo_camara>/push``: Recibe capturas fotográficas,
  las valida, las decodifica con OpenCV y las entrega a ``MobilePushFrameBuffer``
  para procesamiento síncrono atómico con ``VisionEngineCoordinator``.

Características de seguridad y robustez (VO-03B):
- **Autenticación obligatoria (Fail-Closed):** Si no se configura una clave de acceso,
  el servicio rechaza de forma segura todas las solicitudes de escritura (HTTP 503).
- **Comparación en tiempo constante:** Uso estricto de ``hmac.compare_digest()``.
- **Concurrencia atómica:** La inserción en el buffer y la llamada al coordinador
  ocurren bajo el mismo bloqueo para impedir carreras o cruces de fotogramas.
- **Soporte TLS/HTTPS nativo:** Utilidad de generación de certificados locales
  específicos para la IP autorizada y ejecución mediante ``werkzeug.serving.run_simple``.
"""

from __future__ import annotations

import datetime
import functools
import hashlib
import hmac
import http.server
import ipaddress
import json
import logging
import os
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# Garantizar que la raíz de VIGIA_Vision_Systems esté en sys.path al ejecutar el archivo directamente
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    import cv2
except ModuleNotFoundError:
    _venv_python = _REPO_ROOT / '.venv' / 'Scripts' / 'python.exe'
    if (
        __name__ == '__main__'
        and _venv_python.is_file()
        and Path(sys.executable).resolve() != _venv_python.resolve()
    ):
        raise SystemExit(subprocess.call([str(_venv_python), *sys.argv]))
    raise
import numpy as np
from flask import Flask, Response, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.serving import ThreadedWSGIServer, load_ssl_context, run_simple as _werkzeug_run_simple

from VIGIA_API.security.auth_service import AuthService
from VIGIA_API.security.session_manager import SessionManager, UserSession
from VIGIA_Core.domain.user import UserDTO
from VIGIA_Core.domain.pairing import PairingRequestState
from VIGIA_Core.repository.pairing_repository import PsycopgPairingRepository, hash_token_sha256
from VIGIA_Core.repository.detection_repository import (
    DatabaseConnectionError,
    DatabasePersistenceError,
    IDetectionRepository,
    PsycopgDetectionRepository,
)
from VIGIA_Core.repository.user_repository import (
    IUserRepository,
    InMemoryUserRepository,
    PsycopgUserRepository,
    build_default_user_repository,
    resolve_database_dsn,
)
from VIGIA_Core.security.password_hasher import hash_password
from VIGIA_Vision.capture.registry import UnregisteredCameraError
from VIGIA_Vision.capture.sources import MobilePushFrameBuffer
from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.config.psycopg_topology_repository import PsycopgTopologyConfigRepository
from VIGIA_Vision.config.topology_validator import (
    ITopologyConfigRepository,
    TopologyValidationError,
    TopologyValidator,
)
from VIGIA_Vision.detection.roi_and_preprocess import (
    FrameValidationError,
    project_normalized_roi,
    validate_bgr_frame,
)
from VIGIA_Vision.detection.yolo_detector import (
    ModelLoadError,
    YoloDetectorConfig,
    YoloVehicleDetector,
)
from VIGIA_Vision.runtime.coordinator import IVehicleDetector, VisionEngineCoordinator
from VIGIA_Vision.runtime.evidence_storage import (
    IEvidenceStorageService,
    LocalDiskEvidenceStorage,
    render_annotated_frame,
)

logger = logging.getLogger(__name__)

# Límites operativos canónicos de seguridad
DEFAULT_MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MiB
DEFAULT_MAX_WIDTH = 3840                     # 4K UHD horizontal
DEFAULT_MAX_HEIGHT = 2160                    # 4K UHD vertical
DEFAULT_RETRY_DEDUP_TTL_SECONDS = 30.0       # Ventana de deduplicación ante reintentos HTTP

# Lista blanca estricta de recursos gráficos oficiales SVG permitidos en /assets/brand/<filename>
ALLOWED_BRAND_SVGS: Set[str] = {
    "empresa_figura.svg",
    "empresa_figura_dark.svg",
    "empresa_nombre.svg",
    "empresa_nombre_dark.svg",
    "producto_figura.svg",
    "producto_figura_dark.svg",
    "producto_nombre.svg",
    "producto_nombre_dark.svg",
}

# Lista blanca estricta de activos estáticos del Dashboard permitidos en /dashboard-assets/<path:filename>
ALLOWED_DASHBOARD_ASSETS: Set[str] = {
    "css/tokens.css",
    "css/base.css",
    "css/login.css",
    "css/admin-devices.css",
    "js/app.js",
    "js/router.js",
    "js/data/devices-demo-data.js",
    "js/services/device-service.js",
    "js/services/api-service.js",
    "js/components/admin-navbar.js",
    "js/components/devices-table.js",
    "js/views/login-view.js",
    "js/views/devices-view.js",
    "js/views/cameras-view.js",
}


def build_vision_engine_coordinator(
    *,
    dsn: Optional[str] = None,
    topology_repository: Optional[ITopologyConfigRepository] = None,
    detection_repository: Optional[IDetectionRepository] = None,
    evidence_storage: Optional[IEvidenceStorageService] = None,
    detector: Optional[IVehicleDetector] = None,
    settings: Optional[VisionEngineSettings] = None,
    yolo_weights_path: Optional[Union[str, Path]] = None,
    open_sources: bool = True,
) -> VisionEngineCoordinator:
    """
    Fábrica de composición explícita del motor propio de visión artificial de VIGÍA.

    Ensambla de forma determinista y sin repositorios en memoria de respaldo:
    1. ``PsycopgTopologyConfigRepository``
    2. ``TopologyValidator`` (Reglas R1–R8)
    3. ``VisionEngineSettings``
    4. ``YoloVehicleDetector`` (``yolo11n.pt``)
    5. ``LocalDiskEvidenceStorage``
    6. ``PsycopgDetectionRepository``
    7. ``VisionEngineCoordinator`` + ``CameraSourceRegistry`` (al ejecutar ``initialize``)

    Lanza ``DatabaseConnectionError``, ``TopologyValidationError`` o ``ModelLoadError``
    si cualquiera de las dependencias reales o las reglas R1–R8 falla en el arranque.
    """
    repo_root = Path(__file__).resolve().parent.parent

    resolved_dsn: Optional[str] = dsn
    if topology_repository is None or detection_repository is None:
        if not resolved_dsn:
            resolved_dsn = resolve_database_dsn()

    if topology_repository is not None:
        resolved_topo_repo = topology_repository
    else:
        assert resolved_dsn is not None
        resolved_topo_repo = PsycopgTopologyConfigRepository(dsn=resolved_dsn)

    if detection_repository is not None:
        resolved_det_repo = detection_repository
    else:
        assert resolved_dsn is not None
        resolved_det_repo = PsycopgDetectionRepository(dsn=resolved_dsn)

    if settings is not None:
        resolved_settings = settings
    else:
        raw_ev_dir = os.environ.get("VIGIA_EVIDENCE_DIR", "").strip()
        ev_dir = Path(raw_ev_dir).resolve() if raw_ev_dir else (repo_root / "evidencias_vigia").resolve()
        raw_conf = os.environ.get("VIGIA_VEHICLE_CONFIDENCE_THRESHOLD", "").strip()
        conf_thresh = float(raw_conf) if raw_conf else 0.70
        raw_ttl = os.environ.get("VIGIA_MOBILE_FRAME_TTL_SECONDS", "").strip()
        ttl_sec = float(raw_ttl) if raw_ttl else 3.0
        resolved_settings = VisionEngineSettings(
            vehicle_confidence_threshold=conf_thresh,
            mobile_frame_ttl_seconds=ttl_sec,
            evidence_directory=ev_dir,
            save_annotated_evidence=True,
            jpeg_quality=90,
            fail_fast_on_invalid_topology=True,
        )

    if evidence_storage is not None:
        resolved_storage = evidence_storage
    else:
        resolved_storage = LocalDiskEvidenceStorage(
            base_directory=resolved_settings.evidence_directory,
            jpeg_quality=resolved_settings.jpeg_quality,
        )

    if detector is not None:
        resolved_detector = detector
    else:
        raw_weights = (
            str(yolo_weights_path).strip()
            if yolo_weights_path is not None
            else os.environ.get("VIGIA_YOLO_WEIGHTS", "").strip()
        )
        weights_file = Path(raw_weights).resolve() if raw_weights else (repo_root / "yolo11n.pt").resolve()
        if not weights_file.is_file():
            raise ModelLoadError(
                f"No se encontró el archivo de pesos del modelo YOLO en '{weights_file}'."
            )
        yolo_cfg = YoloDetectorConfig(
            model_path=str(weights_file),
            confidence_threshold=min(0.25, resolved_settings.vehicle_confidence_threshold),
        )
        resolved_detector = YoloVehicleDetector(config=yolo_cfg)

    validator = TopologyValidator(repository=resolved_topo_repo)
    coordinator = VisionEngineCoordinator(
        topology_validator=validator,
        settings=resolved_settings,
        detector=resolved_detector,
        detection_repository=resolved_det_repo,
        evidence_storage=resolved_storage,
        new_event_predicate=lambda _cam_code, detections: bool(detections),
    )
    coordinator.initialize(open_sources=open_sources)
    return coordinator



# =========================================================================
# ESTADO EN TIEMPO REAL Y TRANSMISIÓN CONTINUA DE CÁMARAS (VIGIA-CAM-01)
# =========================================================================
_latest_camera_frames: Dict[str, Dict[str, Any]] = {}
_camera_conditions: Dict[str, threading.Condition] = {}
_camera_conditions_lock = threading.Lock()
_last_persist_timestamps: Dict[str, float] = {}
_standby_cache: Dict[Tuple[str, str], bytes] = {}


def _get_camera_condition(codigo_camara: str) -> threading.Condition:
    """Retorna o inicializa de forma atómica la variable de condición para una cámara."""
    with _camera_conditions_lock:
        if codigo_camara not in _camera_conditions:
            _camera_conditions[codigo_camara] = threading.Condition()
        return _camera_conditions[codigo_camara]


def _generate_standby_jpeg(codigo_camara: str, message: str = "EN ESPERA DE TRANSMISION") -> bytes:
    """Genera un fotograma JPEG sintético con la estética corporativa de VIGÍA para el estado de espera."""
    cache_key = (codigo_camara, message)
    if cache_key in _standby_cache:
        return _standby_cache[cache_key]

    width, height = 640, 360
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = (26, 17, 13)  # Fondo oscuro corporativo

    # Borde sutil
    cv2.rectangle(img, (12, 12), (width - 12, height - 12), (55, 40, 25), 2)
    # Título institucional
    cv2.putText(img, "VIGIA VISION SYSTEMS", (36, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (180, 180, 180), 2)
    cv2.putText(img, f"CANAL: {codigo_camara}", (36, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (90, 215, 110), 2)
    # Estado
    cv2.putText(img, f"ESTADO: {message}", (36, 175), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (90, 170, 250), 2)
    cv2.putText(img, "Pulse 'Abrir camara' en el telefono enrolado", (36, 245), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (150, 150, 150), 1)
    cv2.putText(img, "Transmision y percepcion visual continua", (36, 315), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (110, 110, 110), 1)

    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    data = buf.tobytes() if ok else b""
    _standby_cache[cache_key] = data
    return data


def create_ingest_app(
    coordinator: Optional[VisionEngineCoordinator] = None,
    auth_token: Optional[str] = None,
    max_content_length: int = DEFAULT_MAX_CONTENT_LENGTH,
    max_dimensions: Tuple[int, int] = (DEFAULT_MAX_WIDTH, DEFAULT_MAX_HEIGHT),
    mobile_html_path: Optional[Union[str, Path]] = None,
    enable_frontend_demo: Optional[bool] = None,
    user_repository: Optional[IUserRepository] = None,
    session_manager: Optional[SessionManager] = None,
    auth_service: Optional[AuthService] = None,
    topology_repository: Optional[ITopologyConfigRepository] = None,
    pairing_repository: Optional[PsycopgPairingRepository] = None,
    allow_in_memory: Optional[bool] = None,
    initialize_vision_engine: Optional[bool] = None,
    retry_dedup_ttl_seconds: float = DEFAULT_RETRY_DEDUP_TTL_SECONDS,
    enable_tls: Optional[bool] = None,
    dev_port: Optional[int] = None,
    certs_dir: Optional[Union[str, Path]] = None,
) -> Flask:
    """
    Fábrica de la aplicación web Flask para el servicio de ingesta de VIGIA_API.

    Parámetros
    ----------
    coordinator : Optional[VisionEngineCoordinator]
        Instancia activa del coordinador de visión de VIGÍA.
    auth_token : Optional[str]
        Token secreto para autorizar peticiones de ingesta. Si es ``None``, se busca
        la variable de entorno ``VIGIA_CAMERA_KEY``. Si ninguna está definida, el
        servicio entra en modo seguro restrictivo (*fail-closed*).
    max_content_length : int
        Tamaño máximo permitido para la carga útil HTTP en bytes (por omisión 8 MiB).
    max_dimensions : Tuple[int, int]
        Dimensiones máximas ``(ancho, alto)`` en píxeles permitidas para el fotograma.
    mobile_html_path : Optional[Union[str, Path]]
        Ruta personalizada al archivo ``index.html`` de la interfaz móvil.
    enable_frontend_demo : Optional[bool]
        Habilita o deshabilita explícitamente el modo DEMO en la interfaz web.
    user_repository : Optional[IUserRepository]
        Repositorio de usuarios para autenticación y RBAC. Si es ``None``, se
        construye mediante ``build_default_user_repository()`` conectando a PostgreSQL.
    session_manager : Optional[SessionManager]
        Gestor de sesiones activas del servidor.
    auth_service : Optional[AuthService]
        Servicio de autenticación para verificación Argon2id y emisión de sesiones.
    topology_repository : Optional[ITopologyConfigRepository]
        Repositorio de configuración y topología de cámaras.
    allow_in_memory : Optional[bool]
        Habilita explícitamente el uso de repositorios en memoria (exclusivo para pruebas).
    initialize_vision_engine : Optional[bool]
        Si es ``True`` (o si la variable de entorno ``VIGIA_ENABLE_VISION_ENGINE`` es ``1``)
        y ``coordinator`` es ``None``, construye e inicializa ``VisionEngineCoordinator``
        mediante ``build_vision_engine_coordinator()`` verificando R1–R8 de forma *fail-fast*.
    retry_dedup_ttl_seconds : float
        Ventana en segundos durante la cual se evita persistir por duplicado reintentos
        de un mismo fotograma o ``X-Idempotency-Key`` por cámara.

    Retorna
    -------
    Flask
        Instancia configurada de la aplicación WSGI.
    """
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = max_content_length
    app.config["RETRY_DEDUP_TTL_SECONDS"] = float(retry_dedup_ttl_seconds)

    # Resolver token: argumento explícito o variable de entorno
    resolved_token = auth_token or os.environ.get("VIGIA_CAMERA_KEY")
    app.config["AUTH_TOKEN"] = resolved_token.strip() if resolved_token else None
    app.config["MAX_DIMENSIONS"] = max_dimensions

    # Resolver bandera explícita de modo DEMO del frontend (deshabilitado por defecto)
    if enable_frontend_demo is not None:
        resolved_demo = bool(enable_frontend_demo)
    else:
        raw_demo = os.environ.get("VIGIA_ENABLE_FRONTEND_DEMO", "").strip().lower()
        resolved_demo = raw_demo in {"1", "true", "yes", "on"}
    app.config["FRONTEND_DEMO_ENABLED"] = resolved_demo

    # Resolver estado de TLS y puerto de desarrollo (VIGIA-TLS-01)
    if enable_tls is not None:
        resolved_tls = bool(enable_tls)
    else:
        raw_tls = os.environ.get("VIGIA_ENABLE_TLS", "").strip().lower()
        resolved_tls = raw_tls in {"1", "true", "yes", "on"}
    app.config["TLS_ENABLED"] = resolved_tls

    if dev_port is not None:
        resolved_port = int(dev_port)
    else:
        default_port = 8443 if resolved_tls else 5000
        resolved_port = int(os.environ.get("VIGIA_DEV_PORT", str(default_port)))
    app.config["DEV_PORT"] = resolved_port

    # Resolver modo en memoria explícito (prohibido fallback silencioso)
    if allow_in_memory is not None:
        explicit_allow_mem = bool(allow_in_memory)
    else:
        raw_mem = os.environ.get("VIGIA_ALLOW_IN_MEMORY", "").strip().lower()
        explicit_allow_mem = raw_mem in {"1", "true", "yes", "on"}

    # Configuración de Autenticación y Sesiones RBAC (ENR-02A / Fase 3A)
    resolved_session_mgr = session_manager or SessionManager()
    if user_repository is not None:
        resolved_user_repo = user_repository
    else:
        resolved_user_repo = build_default_user_repository(allow_in_memory=explicit_allow_mem)

    resolved_auth_svc = auth_service or AuthService(
        user_repository=resolved_user_repo,
        session_manager=resolved_session_mgr,
    )
    app.config["SESSION_MANAGER"] = resolved_session_mgr
    app.config["USER_REPOSITORY"] = resolved_user_repo
    app.config["AUTH_SERVICE"] = resolved_auth_svc

    # Configuración de Repositorio de Topología de Cámaras
    resolved_dsn: Optional[str] = None
    if topology_repository is not None:
        resolved_topo_repo = topology_repository
    elif explicit_allow_mem:
        resolved_topo_repo = None
    else:
        resolved_dsn = resolve_database_dsn()
        resolved_topo_repo = PsycopgTopologyConfigRepository(dsn=resolved_dsn)
    app.config["TOPOLOGY_REPOSITORY"] = resolved_topo_repo
    # Repositorio de Enrolamiento y Dispositivos QR (MOB-QR-01)
    if pairing_repository is not None:
        resolved_pairing_repo = pairing_repository
    elif not explicit_allow_mem:
        if resolved_dsn is None:
            resolved_dsn = resolve_database_dsn()
        resolved_pairing_repo = PsycopgPairingRepository(dsn=resolved_dsn)
    else:
        resolved_pairing_repo = None
    app.config["PAIRING_REPOSITORY"] = resolved_pairing_repo

    # Composición e inicialización opcional/operativa del Motor de Visión (sin duplicar instancias)
    if coordinator is not None:
        resolved_coordinator: Optional[VisionEngineCoordinator] = coordinator
    else:
        if initialize_vision_engine is not None:
            should_init_engine = bool(initialize_vision_engine)
        else:
            raw_eng = os.environ.get("VIGIA_ENABLE_VISION_ENGINE", "").strip().lower()
            should_init_engine = raw_eng in {"1", "true", "yes", "on"}

        if should_init_engine:
            if explicit_allow_mem and resolved_topo_repo is None:
                raise RuntimeError(
                    "Modo operativo del motor de visión rechazado: no se permite usar "
                    "repositorios en memoria ni omitir PostgreSQL."
                )
            resolved_coordinator = build_vision_engine_coordinator(
                dsn=resolved_dsn,
                topology_repository=resolved_topo_repo,
                open_sources=True,
            )
        else:
            resolved_coordinator = None

    app.config["COORDINATOR"] = resolved_coordinator

    # Ruta a la interfaz móvil y al Dashboard web en VIGIA_Dashboard
    repo_root = Path(__file__).resolve().parent.parent
    default_html = repo_root / "VIGIA_Dashboard" / "mobile" / "index.html"
    html_target = Path(mobile_html_path) if mobile_html_path else default_html
    app.config["MOBILE_HTML_PATH"] = html_target
    app.config["DASHBOARD_WEB_DIR"] = (repo_root / "VIGIA_Dashboard" / "web").resolve()
    app.config["BRAND_SVG_DIR"] = (
        repo_root / "Docs" / "GEST_PROY_SOFT" / "02_Logos_accesibilidad" / "svg"
    ).resolve()
    if certs_dir is not None:
        app.config["CERTS_DIR"] = Path(certs_dir).resolve()
    else:
        app.config["CERTS_DIR"] = (repo_root / "certs").resolve()

    # Lock para serializar atómicamente push_frame + process_camera_step y caché de deduplicación
    process_lock = threading.RLock()
    persisted_retry_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
    camera_persist_states: Dict[str, Dict[str, Any]] = {}

    @app.errorhandler(RequestEntityTooLarge)
    def handle_entity_too_large(exc: Exception):  # type: ignore
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "PAYLOAD_TOO_LARGE",
                    "message": f"El tamaño del archivo excede el límite máximo permitido de {max_content_length // (1024 * 1024)} MiB.",
                }
            ),
            413,
        )

    @app.errorhandler(404)
    def handle_not_found(exc: Exception):  # type: ignore
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "NOT_FOUND",
                    "message": "El recurso o la ruta solicitada no existe.",
                }
            ),
            404,
        )

    @app.errorhandler(405)
    def handle_method_not_allowed(exc: Exception):  # type: ignore
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "METHOD_NOT_ALLOWED",
                    "message": "Método HTTP no permitido para esta ruta.",
                }
            ),
            405,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_exception(exc: Exception):  # type: ignore
        if isinstance(exc, HTTPException):
            return exc
        logger.error("Error inesperado en servicio de ingesta: %s", exc, exc_info=True)
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "INTERNAL_ERROR",
                    "message": "Fallo interno durante el procesamiento de la solicitud.",
                }
            ),
            500,
        )

    @app.before_request
    def validate_csrf():  # type: ignore
        """
        Protección CSRF para peticiones mutacionales que utilicen autenticación basada en cookie.
        Si la petición incluye la cookie 'vigia_session' y un encabezado Origin foráneo no autorizado,
        se rechaza de inmediato con HTTP 403 Forbidden.
        """
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            if "vigia_session" in request.cookies:
                origin = request.headers.get("Origin")
                if origin:
                    server_origin = request.host_url.rstrip("/")
                    raw_allowed = os.environ.get("VIGIA_ALLOWED_ORIGINS", "")
                    allowed_origins = {server_origin}
                    if raw_allowed:
                        allowed_origins.update(o.strip() for o in raw_allowed.split(",") if o.strip())

                    is_allowed = (
                        origin in allowed_origins
                        or origin.startswith(
                            ("http://localhost", "http://127.0.0.1", "https://localhost", "https://127.0.0.1")
                        )
                    )
                    if not is_allowed:
                        logger.warning(
                            "Solicitud mutacional rechazada por violación CSRF. Origin '%s' no autorizado.",
                            origin,
                        )
                        return (
                            jsonify(
                                {
                                    "ok": False,
                                    "error": "CSRF_ERROR",
                                    "message": "Origen de solicitud no autorizado.",
                                }
                            ),
                            403,
                        )

    @app.after_request
    def apply_security_headers(response):  # type: ignore
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if request.path.startswith("/dashboard-assets/") or request.path in ("/app", "/mobile"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        origin = request.headers.get("Origin")
        if origin:
            server_origin = request.host_url.rstrip("/")
            raw_allowed = os.environ.get("VIGIA_ALLOWED_ORIGINS", "")
            allowed_origins = {server_origin}
            if raw_allowed:
                allowed_origins.update(o.strip() for o in raw_allowed.split(",") if o.strip())

            # Permitir localhost/127.0.0.1 y orígenes configurados en lista blanca
            if (
                origin in allowed_origins
                or origin.startswith(("http://localhost", "http://127.0.0.1", "https://localhost", "https://127.0.0.1"))
            ):
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, DELETE"
                response.headers["Access-Control-Allow-Headers"] = (
                    "Content-Type, X-Camera-Key, X-API-Key, Authorization, X-Idempotency-Key"
                )
                response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    @app.route("/", methods=["GET"])
    def index():  # type: ignore
        return jsonify(
            {
                "service": "VIGIA Vision Systems - Ingest API",
                "version": "VO-03B",
                "status": "ONLINE",
            }
        )

    @app.route("/mobile", methods=["GET"])
    def serve_mobile_interface():  # type: ignore
        """Sirve la interfaz web móvil responsiva de VIGIA_Dashboard."""
        target_file = app.config["MOBILE_HTML_PATH"]
        if not target_file.exists():
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "UI_NOT_FOUND",
                        "message": "La interfaz móvil no se encuentra instalada en el servidor.",
                    }
                ),
                404,
            )
        return (
            target_file.read_text(encoding="utf-8"),
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.route("/app", methods=["GET"])
    def serve_dashboard_app():  # type: ignore
        """Sirve la pantalla principal de VIGIA_Dashboard (web/index.html) con el estado de DEMO."""
        dashboard_dir: Path = app.config["DASHBOARD_WEB_DIR"]
        target_file = (dashboard_dir / "index.html").resolve()
        if not target_file.exists():
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "DASHBOARD_NOT_FOUND",
                        "message": "La interfaz web del Dashboard no se encuentra disponible.",
                    }
                ),
                404,
            )
        raw_html = target_file.read_text(encoding="utf-8")
        demo_flag = "true" if app.config.get("FRONTEND_DEMO_ENABLED", False) else "false"
        rendered_html = raw_html.replace(
            'data-demo-enabled="false"',
            f'data-demo-enabled="{demo_flag}"',
            1,
        )
        return (
            rendered_html,
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.route("/dashboard-assets/<path:filename>", methods=["GET"])
    def serve_dashboard_asset(filename: str):  # type: ignore
        """Sirve de forma controlada los recursos estáticos autorizados de VIGIA_Dashboard/web/."""
        normalized_rel = filename.replace("\\", "/").lstrip("/")
        if normalized_rel not in ALLOWED_DASHBOARD_ASSETS:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "ASSET_NOT_FOUND",
                        "message": "El recurso estático solicitado no existe o no está autorizado.",
                    }
                ),
                404,
            )

        dashboard_dir: Path = app.config["DASHBOARD_WEB_DIR"]
        candidate = (dashboard_dir / normalized_rel).resolve()
        try:
            candidate.relative_to(dashboard_dir)
        except ValueError:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "ASSET_NOT_FOUND",
                        "message": "Ruta de recurso inválida.",
                    }
                ),
                404,
            )

        if not candidate.is_file():
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "ASSET_NOT_FOUND",
                        "message": "El recurso estático solicitado no se encuentra en el servidor.",
                    }
                ),
                404,
            )

        mimetype = "text/plain"
        if normalized_rel.endswith(".css"):
            mimetype = "text/css"
        elif normalized_rel.endswith(".js"):
            mimetype = "application/javascript"

        return send_from_directory(
            str(dashboard_dir),
            normalized_rel,
            mimetype=mimetype,
        )

    @app.route("/assets/brand/<filename>", methods=["GET"])
    def serve_brand_svg(filename: str):  # type: ignore
        """Sirve exclusivamente los archivos SVG oficiales autorizados de identidad visual."""
        if (
            not filename
            or "/" in filename
            or "\\" in filename
            or ".." in filename
            or filename not in ALLOWED_BRAND_SVGS
        ):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "BRAND_ASSET_NOT_FOUND",
                        "message": "El recurso gráfico solicitado no existe o no está autorizado.",
                    }
                ),
                404,
            )

        brand_dir: Path = app.config["BRAND_SVG_DIR"]
        candidate = (brand_dir / filename).resolve()
        try:
            candidate.relative_to(brand_dir)
        except ValueError:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "BRAND_ASSET_NOT_FOUND",
                        "message": "Ruta de recurso gráfico inválida.",
                    }
                ),
                404,
            )

        if not candidate.is_file():
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "BRAND_ASSET_NOT_FOUND",
                        "message": "El archivo SVG oficial no se encuentra en el servidor.",
                    }
                ),
                404,
            )

        return send_from_directory(
            str(brand_dir),
            filename,
            mimetype="image/svg+xml",
        )

    # =========================================================================
    # Funciones auxiliares y decoradores de seguridad RBAC (ENR-02A)
    # =========================================================================

    def _extract_session_token() -> Optional[str]:
        # La cookie HttpOnly es el único mecanismo de sesión para el Dashboard (Fase 3A)
        cookie_tok = request.cookies.get("vigia_session", "").strip()
        if cookie_tok:
            return cookie_tok
        return None

    def _resolve_session() -> Optional[UserSession]:
        tok = _extract_session_token()
        if not tok:
            return None
        sess_mgr: SessionManager = app.config["SESSION_MANAGER"]
        return sess_mgr.get_session(tok)

    def require_session_auth(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            sess = _resolve_session()
            if sess is None:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": "UNAUTHORIZED",
                            "message": "Sesión inválida, ausente o expirada.",
                        }
                    ),
                    401,
                )
            g.current_session = sess
            return f(*args, **kwargs)
        return wrapper

    def require_rbac(*allowed_roles: str):
        def decorator(f):
            @functools.wraps(f)
            def wrapper(*args, **kwargs):
                sess = _resolve_session()
                if sess is None:
                    return (
                        jsonify(
                            {
                                "ok": False,
                                "error": "UNAUTHORIZED",
                                "message": "Sesión inválida, ausente o expirada.",
                            }
                        ),
                        401,
                    )

                allowed_norm = {r.strip().upper() for r in allowed_roles}
                if "GUARDIA" in allowed_norm:
                    allowed_norm.add("OPERADOR")
                if "OPERADOR" in allowed_norm:
                    allowed_norm.add("GUARDIA")

                user_func_role = sess.rol.upper()
                user_db_role = sess.db_rol.upper()

                if user_func_role not in allowed_norm and user_db_role not in allowed_norm:
                    logger.warning(
                        "Acceso denegado a '%s' para usuario '%s' con rol '%s' (requiere: %s)",
                        request.path,
                        sess.username,
                        sess.rol,
                        list(allowed_roles),
                    )
                    return (
                        jsonify(
                            {
                                "ok": False,
                                "error": "FORBIDDEN",
                                "message": f"Acceso restringido: requiere rol {list(allowed_roles)}.",
                            }
                        ),
                        403,
                    )

                g.current_session = sess
                return f(*args, **kwargs)
            return wrapper
        return decorator

    # =========================================================================
    # Endpoints de Autenticación y Autorización RBAC (ENR-02A)
    # =========================================================================

    @app.route("/api/v1/auth/login", methods=["POST"])
    def auth_login():
        """
        Inicia sesión mediante credenciales de usuario y genera un token de sesión opaco.
        Valida contraseñas con Argon2id y responde 401 genérico ante cualquier error.
        """
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "BAD_REQUEST",
                        "message": "Cuerpo de solicitud JSON inválido o ausente.",
                    }
                ),
                400,
            )

        username = payload.get("username")
        password = payload.get("password")

        if not username or not password or not isinstance(username, str) or not isinstance(password, str):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "MISSING_CREDENTIALS",
                        "message": "Se requiere identificación de usuario y contraseña.",
                    }
                ),
                400,
            )

        svc: AuthService = app.config["AUTH_SERVICE"]
        sess = svc.authenticate(username, password)

        if sess is None:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "INVALID_CREDENTIALS",
                        "message": "Credenciales inválidas o usuario inactivo.",
                    }
                ),
                401,
            )

        sess_mgr: SessionManager = app.config["SESSION_MANAGER"]
        response = jsonify(
            {
                "ok": True,
                "user": {
                    "id_usuario": str(sess.user_id),
                    "username": sess.username,
                    "nombre_completo": sess.nombre_completo,
                    "rol": sess.rol,
                },
                "expires_at": sess.expires_at.isoformat(),
            }
        )
        response.set_cookie(
            "vigia_session",
            sess.token,
            httponly=True,
            samesite="Strict",
            path="/",
            secure=request.is_secure,
            max_age=sess_mgr.default_ttl_seconds,
        )
        return response, 200

    @app.route("/api/v1/auth/logout", methods=["POST"])
    def auth_logout():
        """
        Revoca inmediatamente la sesión activa actual en el servidor y borra la cookie vigia_session.
        Idempotente: siempre responde HTTP 200 y borra la cookie incluso si la sesión ya no existe.
        """
        tok = _extract_session_token()
        if tok:
            sess_mgr: SessionManager = app.config["SESSION_MANAGER"]
            sess_mgr.revoke_session(tok)

        response = jsonify(
            {
                "ok": True,
                "message": "Sesión finalizada exitosamente.",
            }
        )
        response.delete_cookie(
            "vigia_session",
            path="/",
            samesite="Strict",
            secure=request.is_secure,
            httponly=True,
        )
        return response, 200

    @app.route("/api/v1/auth/me", methods=["GET"])
    @require_session_auth
    def auth_me():
        """
        Retorna la identidad y el rol del usuario autenticado en la sesión actual.
        """
        sess: UserSession = g.current_session
        return jsonify(
            {
                "ok": True,
                "user": {
                    "id_usuario": str(sess.user_id),
                    "username": sess.username,
                    "nombre_completo": sess.nombre_completo,
                    "rol": sess.rol,
                },
                "expires_at": sess.expires_at.isoformat(),
            }
        )

    @app.route("/api/v1/supervision/status", methods=["GET"])
    @require_rbac("ADMINISTRADOR", "GUARDIA")
    def supervision_status():
        """
        Endpoint operativo de supervisión de caseta.
        Accesible tanto por ADMINISTRADOR como por GUARDIA (OPERADOR).
        """
        sess: UserSession = g.current_session
        engine_coordinator: Optional[VisionEngineCoordinator] = app.config.get("COORDINATOR")
        engine_ready = bool(engine_coordinator and engine_coordinator.is_initialized)

        return jsonify(
            {
                "ok": True,
                "status": "OPERATIONAL" if engine_ready else "STANDBY",
                "engine_initialized": engine_ready,
                "user": sess.username,
                "role": sess.rol,
                "supervised_positions": ["ENTRADA", "SALIDA"],
            }
        )

    @app.route("/api/v1/admin/users", methods=["GET"])
    @require_rbac("ADMINISTRADOR")
    def list_admin_users():
        """
        Consulta la lista de usuarios. Acceso restringido exclusivamente a ADMINISTRADOR.
        """
        repo: IUserRepository = app.config["USER_REPOSITORY"]
        users = repo.list_users()
        return jsonify(
            {
                "ok": True,
                "users": [
                    {
                        "id_usuario": str(u.id_usuario),
                        "username": u.username,
                        "nombre_completo": u.nombre_completo,
                        "rol": u.functional_role,
                        "db_rol": u.rol,
                        "activo": u.activo,
                    }
                    for u in users
                ],
            }
        )

    @app.route("/api/v1/admin/users", methods=["POST"])
    @require_rbac("ADMINISTRADOR")
    def create_admin_user():
        """
        Crea un nuevo usuario en el sistema con contraseña hasheada mediante Argon2id.
        Acceso restringido exclusivamente a ADMINISTRADOR.
        """
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "BAD_REQUEST",
                        "message": "Cuerpo de solicitud JSON inválido.",
                    }
                ),
                400,
            )

        username = str(payload.get("username", "")).strip()
        raw_password = str(payload.get("password", ""))
        nombre_completo = str(payload.get("nombre_completo", "")).strip()
        rol = str(payload.get("rol", "")).strip().upper()

        if not username or not raw_password or not nombre_completo or not rol:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "MISSING_FIELDS",
                        "message": "Los campos 'username', 'password', 'nombre_completo' y 'rol' son obligatorios.",
                    }
                ),
                400,
            )

        try:
            pw_hash = hash_password(raw_password)
            user_dto = UserDTO(
                username=username,
                contrasena_hash=pw_hash,
                nombre_completo=nombre_completo,
                rol=rol,
                activo=bool(payload.get("activo", True)),
            )
            repo: IUserRepository = app.config["USER_REPOSITORY"]
            user_id = repo.create_user(user_dto)
            return (
                jsonify(
                    {
                        "ok": True,
                        "id_usuario": str(user_id),
                        "username": user_dto.username,
                        "rol": user_dto.functional_role,
                        "message": "Usuario creado exitosamente.",
                    }
                ),
                201,
            )
        except ValueError as val_err:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "VALIDATION_ERROR",
                        "message": str(val_err),
                    }
                ),
                400,
            )
        except Exception as exc:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "PERSISTENCE_ERROR",
                        "message": f"Fallo al registrar usuario: {exc}",
                    }
                ),
                409,
            )

    @app.route("/api/v1/admin/users/<uuid_usuario>", methods=["DELETE"])
    @require_rbac("ADMINISTRADOR")
    def deactivate_admin_user(uuid_usuario: str):
        """
        Desactiva un usuario por su UUID y revoca todas sus sesiones activas.
        Acceso restringido exclusivamente a ADMINISTRADOR.
        """
        try:
            target_id = uuid.UUID(uuid_usuario)
        except ValueError:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "INVALID_UUID",
                        "message": "El formato del identificador UUID es inválido.",
                    }
                ),
                400,
            )

        repo: IUserRepository = app.config["USER_REPOSITORY"]
        ok = repo.deactivate_user(target_id)
        if not ok:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "USER_NOT_FOUND",
                        "message": f"Usuario con ID '{uuid_usuario}' no encontrado.",
                    }
                ),
                404,
            )

        sess_mgr: SessionManager = app.config["SESSION_MANAGER"]
        sess_mgr.revoke_user_sessions(target_id)

        return jsonify(
            {
                "ok": True,
                "message": f"Usuario '{uuid_usuario}' desactivado y sesiones revocadas.",
            }
        )

    @app.route("/api/v1/cameras", methods=["GET"])
    @require_rbac("ADMINISTRADOR", "GUARDIA")
    def list_cameras():
        """
        Consulta las cámaras lógicas y sus áreas de visión persistidas en PostgreSQL.
        Acceso restringido exclusivamente a ADMINISTRADOR y GUARDIA (OPERADOR en BD).
        AUDITOR queda restringido (HTTP 403 Forbidden).
        No expone uri_stream, credenciales ni infiere estado del motor de visión.
        """
        topo_repo: Optional[ITopologyConfigRepository] = app.config.get("TOPOLOGY_REPOSITORY")
        if topo_repo is None:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "SERVICE_UNAVAILABLE",
                        "message": "Repositorio de topología de cámaras no configurado.",
                    }
                ),
                503,
            )

        try:
            cameras = topo_repo.get_cameras()
            areas = topo_repo.get_areas()
        except DatabaseConnectionError as conn_err:
            logger.error("Error de base de datos al consultar cámaras: %s", conn_err)
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "DATABASE_UNAVAILABLE",
                        "message": "Fallo de conexión al consultar la base de datos de cámaras.",
                    }
                ),
                503,
            )
        except Exception as exc:
            logger.error("Error inesperado al consultar cámaras: %s", exc, exc_info=True)
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "INTERNAL_ERROR",
                        "message": "Fallo interno al consultar las cámaras.",
                    }
                ),
                500,
            )

        areas_by_cam: Dict[Any, List[Dict[str, Any]]] = {}
        for area in areas:
            cid = area.id_camara
            if cid not in areas_by_cam:
                areas_by_cam[cid] = []
            areas_by_cam[cid].append(
                {
                    "id_area_vision": str(area.id_area_vision),
                    "codigo": area.codigo,
                    "nombre": area.nombre,
                    "tipo_movimiento": area.tipo_movimiento,
                }
            )

        now_ts = time.time()
        camera_list = []
        for cam in cameras:
            cam_code = cam.codigo.strip().upper()
            cam_entry = _latest_camera_frames.get(cam_code)
            is_tx = bool(cam_entry and (now_ts - cam_entry.get("timestamp", 0.0) < 4.0))
            camera_list.append(
                {
                    "id_camara": str(cam.id_camara),
                    "codigo": cam.codigo,
                    "nombre": cam.nombre,
                    "activa": bool(cam.activa),
                    "areas": areas_by_cam.get(cam.id_camara, []),
                    "is_transmitting": is_tx,
                    "last_frame_seconds_ago": round(now_ts - cam_entry.get("timestamp", 0.0), 1) if cam_entry else None,
                    "operational_status": "TRANSMITIENDO" if is_tx else ("EN_ESPERA" if cam.activa else "INACTIVA"),
                    "latest_metrics": {
                        "status": cam_entry.get("status", "SIN_SENAL"),
                        "vehicle_detected": cam_entry.get("vehicle_detected", False),
                        "vehicle_type": cam_entry.get("tipo_vehiculo"),
                        "confianza": cam_entry.get("confianza"),
                        "in_roi": cam_entry.get("in_roi", 0),
                        "sequence": cam_entry.get("sequence"),
                    } if cam_entry else None,
                }
            )

        return (
            jsonify(
                {
                    "ok": True,
                    "cameras": camera_list,
                    "total": len(camera_list),
                }
            ),
            200,
        )

    @app.route("/api/v1/cameras/<codigo_camara>/push", methods=["POST", "OPTIONS"])
    def push_camera_frame(codigo_camara: str):  # type: ignore
        """
        Recibe un fotograma capturado por un dispositivo móvil para la cámara indicada.
        """
        start_push_time = time.time()
        if request.method == "OPTIONS":
            return "", 204

        # 1. Validación de Autorización Obligatoria (Fail-Closed)
        configured_token: Optional[str] = app.config.get("AUTH_TOKEN")
        pairing_repo: Optional[PsycopgPairingRepository] = app.config.get("PAIRING_REPOSITORY")

        provided_key = request.headers.get("X-Camera-Key") or request.headers.get("X-API-Key")
        if not provided_key:
            auth_hdr = request.headers.get("Authorization", "")
            if auth_hdr.startswith("Bearer "):
                provided_key = auth_hdr[7:].strip()

        is_authorized = False
        if provided_key and provided_key.startswith("vigia_st_"):
            if pairing_repo is None:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": "PAIRING_REPOSITORY_UNAVAILABLE",
                            "message": "Servicio de credenciales móviles no disponible.",
                        }
                    ),
                    503,
                )
            try:
                if pairing_repo.validate_stream_token(codigo_camara=codigo_camara, token_transmision=provided_key):
                    is_authorized = True
            except Exception as val_exc:
                logger.warning("Error validando token individual: %s", val_exc)
        else:
            if not configured_token:
                logger.warning(
                    "Intento de ingesta hacia '%s' rechazado: servicio sin clave de acceso configurada.",
                    codigo_camara,
                )
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": "AUTH_CONFIGURATION_MISSING",
                            "message": "El servicio de ingesta está deshabilitado por falta de configuración de clave de acceso.",
                        }
                    ),
                    503,
                )
            if provided_key and hmac.compare_digest(provided_key, configured_token):
                is_authorized = True

        if not is_authorized:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "UNAUTHORIZED",
                        "message": "Credencial de cámara no válida o ausente.",
                    }
                ),
                401,
            )

        # 2. Extracción segura del payload de imagen
        raw_bytes: Optional[bytes] = None
        file_obj = (
            request.files.get("frame")
            or request.files.get("image")
            or request.files.get("file")
        )

        if file_obj is not None:
            raw_bytes = file_obj.read()
        elif request.data:
            raw_bytes = request.data

        if raw_bytes is None:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "EMPTY_PAYLOAD",
                        "message": "No se recibió ninguna imagen en la solicitud HTTP.",
                    }
                ),
                400,
            )

        if len(raw_bytes) == 0:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "EMPTY_FILE",
                        "message": "El archivo de imagen recibido tiene 0 bytes.",
                    }
                ),
                400,
            )

        # 3. Decodificación de la imagen mediante OpenCV
        np_arr = np.frombuffer(raw_bytes, dtype=np.uint8)
        frame_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame_bgr is None:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "DECODE_ERROR",
                        "message": "Los datos recibidos no corresponden a un formato de imagen decodificable.",
                    }
                ),
                422,
            )

        # 4. Validación de dimensiones máximas de seguridad
        h, w = frame_bgr.shape[:2]
        max_w, max_h = app.config["MAX_DIMENSIONS"]
        if w > max_w or h > max_h:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "DIMENSIONS_EXCEEDED",
                        "message": f"Dimensiones de imagen ({w}x{h}) exceden el límite permitido ({max_w}x{max_h}).",
                    }
                ),
                422,
            )

        # 5. Validación canónica mediante contrato de dominio VIGIA_Vision
        try:
            validate_bgr_frame(frame_bgr)
        except FrameValidationError as val_err:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "INVALID_FRAME",
                        "message": str(val_err),
                    }
                ),
                422,
            )

        # 6. Resolución de la cámara en el coordinador de visión
        engine_coordinator: Optional[VisionEngineCoordinator] = app.config.get("COORDINATOR")
        if engine_coordinator is None:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "ENGINE_NOT_ATTACHED",
                        "message": "El motor de visión no está configurado en el servicio de ingesta.",
                    }
                ),
                503,
            )

        if not engine_coordinator.is_initialized:
            try:
                engine_coordinator.initialize(open_sources=True)
            except Exception as init_err:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": "INITIALIZATION_FAILED",
                            "message": f"Fallo al inicializar topología operativa: {init_err}",
                        }
                    ),
                    503,
                )

        registry = engine_coordinator.registry
        if registry is None:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "REGISTRY_UNAVAILABLE",
                        "message": "El registro de fuentes no está disponible.",
                    }
                ),
                503,
            )

        try:
            slot = registry.get_slot(codigo_camara)
        except UnregisteredCameraError as cam_err:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "CAMERA_NOT_FOUND",
                        "message": str(cam_err),
                    }
                ),
                404,
            )

        # Verificar que la fuente admita ingesta push
        if not hasattr(slot.source, "push_frame") or not isinstance(slot.source, MobilePushFrameBuffer):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "CAMERA_NOT_PUSH_CAPABLE",
                        "message": f"La cámara '{codigo_camara}' no está configurada para ingesta push móvil.",
                    }
                ),
                400,
            )

        # 7 y 8. Entrega, Deduplicación de Reintentos e Inferencia Atómica Protegida por Bloqueo
        # Garantiza que ninguna otra solicitud concurrente pueda sobrescribir el buffer
        # antes de que esta solicitud complete su ciclo de procesamiento.
        frame_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        explicit_idemp_key = (
            request.headers.get("X-Idempotency-Key")
            or request.headers.get("X-Request-Id")
            or ""
        ).strip()
        dedup_token = explicit_idemp_key or frame_sha256
        cache_key = (codigo_camara, dedup_token)
        dedup_ttl: float = float(app.config.get("RETRY_DEDUP_TTL_SECONDS", DEFAULT_RETRY_DEDUP_TTL_SECONDS))

        has_persistence_configured = (
            getattr(engine_coordinator, "_detection_repository", None) is not None
        )

        with process_lock:
            now_mono = time.monotonic()
            expired_keys = [
                k
                for k, v in persisted_retry_cache.items()
                if (now_mono - float(v.get("ts_monotonic", 0.0))) > dedup_ttl
            ]
            for k in expired_keys:
                persisted_retry_cache.pop(k, None)

            cached_entry = persisted_retry_cache.get(cache_key)
            is_duplicate_retry = cached_entry is not None

            # Si es un reintento de un fotograma ya persistido, no volver a escribir en disco ni en BD.
            # Si no es reintento y el coordinador cuenta con repositorio de detecciones configurado,
            # activar la persistencia para detecciones vehiculares válidas dentro del ROI.
            # Separación canónica: Idempotencia vs. Deduplicación vs. Decisión de Persistencia (CAM-01A)
            cam_persist_state = camera_persist_states.setdefault(
                codigo_camara, {"last_persist_ts": 0.0, "had_vehicle": False}
            )
            if explicit_idemp_key:
                # Solicitud deliberada con identificador único: no se bloquea por intervalo
                persist_debounce_ok = True
            else:
                last_ts = float(cam_persist_state.get("last_persist_ts", 0.0))
                debounce_ttl = float(app.config.get("STREAM_PERSIST_DEBOUNCE_SECONDS", 3.0))
                time_elapsed_ok = (now_mono - last_ts) >= debounce_ttl
                new_arrival = not bool(cam_persist_state.get("had_vehicle", False))
                persist_debounce_ok = bool(time_elapsed_ok or new_arrival)

            persist_flag = bool(has_persistence_configured and not is_duplicate_retry and persist_debounce_ok)

            if not slot.source.is_opened():
                slot.source.open()

            seq = slot.source.push_frame(frame_bgr)

            try:
                envelope = engine_coordinator.process_camera_step(
                    codigo_camara,
                    persist_as_new_event=persist_flag,
                )
            except (DatabaseConnectionError, DatabasePersistenceError) as db_err:
                logger.error(
                    "Fallo de persistencia PostgreSQL durante process_camera_step en '%s': %s",
                    codigo_camara,
                    db_err,
                )
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": "PERSISTENCE_ERROR",
                            "message": "Fallo al persistir la detección en PostgreSQL; evidencia revertida.",
                            "codigo_camara": codigo_camara,
                            "detection_persisted": False,
                            "evidence_saved": False,
                            "id_deteccion": None,
                        }
                    ),
                    500,
                )
            except Exception as proc_err:
                logger.error("Error durante process_camera_step: %s", proc_err, exc_info=True)
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": "PROCESSING_ERROR",
                            "message": "Fallo durante la inferencia y procesamiento del fotograma.",
                            "codigo_camara": codigo_camara,
                            "detection_persisted": False,
                            "evidence_saved": False,
                            "id_deteccion": None,
                        }
                    ),
                    500,
                )

            # 9. Respuesta estructurada al dispositivo móvil verificando integridad de almacenamiento y BD
            if envelope is None:
                return jsonify(
                    {
                        "ok": True,
                        "codigo_camara": codigo_camara,
                        "frame_sequence": seq,
                        "status": "ALREADY_PROCESSED_OR_SKIPPED",
                        "vehicle_detected": False,
                        "tipo_vehiculo": None,
                        "confianza": None,
                        "detections_count": 0,
                        "in_roi_now": 0,
                        "detection_persisted": False,
                        "evidence_saved": False,
                        "duplicate_retry": is_duplicate_retry,
                        "id_deteccion": None,
                    }
                )

            vr = envelope.vision_result
            evidence_ok = bool(
                envelope.original_evidence_path is not None
                and (
                    not engine_coordinator.settings.save_annotated_evidence
                    or envelope.annotated_evidence_path is not None
                )
            )
            db_ok = bool(envelope.id_deteccion is not None)

            # Si se solicitó persistir una detección válida en el ROI pero falló el almacenamiento
            # de evidencia o la inserción relacional, NO informar detección persistida (HTTP 500).
            if persist_flag and vr.vehicle_detected:
                if not evidence_ok or not db_ok:
                    logger.error(
                        "Persistencia incompleta en cámara '%s': evidence_ok=%s, db_ok=%s",
                        codigo_camara,
                        evidence_ok,
                        db_ok,
                    )
                    return (
                        jsonify(
                            {
                                "ok": False,
                                "error": "STORAGE_ERROR" if not evidence_ok else "PERSISTENCE_ERROR",
                                "message": (
                                    "Fallo al almacenar las imágenes de evidencia en disco."
                                    if not evidence_ok
                                    else "La detección no pudo ser persistida en PostgreSQL."
                                ),
                                "codigo_camara": codigo_camara,
                                "status": vr.status.value,
                                "vehicle_detected": vr.vehicle_detected,
                                "detection_persisted": False,
                                "evidence_saved": evidence_ok,
                                "id_deteccion": str(envelope.id_deteccion) if envelope.id_deteccion else None,
                                "original_evidence_path": envelope.original_evidence_path,
                                "annotated_evidence_path": envelope.annotated_evidence_path,
                            }
                        ),
                        500,
                    )

                cam_persist_state["last_persist_ts"] = now_mono
                _last_persist_timestamps[codigo_camara] = now_mono
                persisted_retry_cache[cache_key] = {
                    "ts_monotonic": time.monotonic(),
                    "id_deteccion": str(envelope.id_deteccion),
                    "original_evidence_path": envelope.original_evidence_path,
                    "annotated_evidence_path": envelope.annotated_evidence_path,
                }

            cam_persist_state["had_vehicle"] = bool(vr.vehicle_detected)

        persisted_id = (
            str(envelope.id_deteccion)
            if envelope.id_deteccion is not None
            else (cached_entry["id_deteccion"] if cached_entry is not None else None)
        )
        orig_path = (
            envelope.original_evidence_path
            if envelope.original_evidence_path is not None
            else (cached_entry["original_evidence_path"] if cached_entry is not None else None)
        )
        annot_path = (
            envelope.annotated_evidence_path
            if envelope.annotated_evidence_path is not None
            else (cached_entry["annotated_evidence_path"] if cached_entry is not None else None)
        )

        # Actualizar fotograma anotado para streaming en tiempo real en Dashboard (VIGIA-CAM-01)
        try:
            pixel_roi = None
            if slot.area is not None:
                pixel_roi = project_normalized_roi(slot.area, frame_width=w, frame_height=h)
            dets = envelope.detections_in_roi if envelope else ()
            annotated_bgr = render_annotated_frame(frame_bgr, detections_in_roi=dets, pixel_roi=pixel_roi)
            ok_enc, enc_bytes = cv2.imencode(".jpg", annotated_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
            live_jpeg = enc_bytes.tobytes() if ok_enc else raw_bytes
        except Exception as annot_exc:
            logger.warning("Fallo al anotar fotograma para streaming en cámara '%s': %s", codigo_camara, annot_exc)
            live_jpeg = raw_bytes

        cam_code_clean = codigo_camara.strip().upper()
        cam_cond = _get_camera_condition(cam_code_clean)
        with cam_cond:
            _latest_camera_frames[cam_code_clean] = {
                "jpeg": live_jpeg,
                "sequence": envelope.frame_sequence or seq,
                "timestamp": time.time(),
                "status": vr.status.value,
                "vehicle_detected": bool(vr.vehicle_detected),
                "tipo_vehiculo": vr.vehicle_type_pred,
                "confianza": vr.vehicle_confidence,
                "in_roi": envelope.metrics.in_roi_now if envelope else 0,
                "latency_ms": round((time.time() - start_push_time) * 1000),
            }
            cam_cond.notify_all()

        return jsonify(
            {
                "ok": True,
                "codigo_camara": codigo_camara,
                "id_camara": str(envelope.id_camara),
                "id_area_vision": str(envelope.id_area_vision),
                "codigo_area": envelope.codigo_area,
                "tipo_movimiento": envelope.tipo_movimiento,
                "frame_sequence": envelope.frame_sequence or seq,
                "status": vr.status.value,
                "vehicle_detected": vr.vehicle_detected,
                "tipo_vehiculo": vr.vehicle_type_pred,
                "confianza": vr.vehicle_confidence,
                "detections_count": len(envelope.detections_in_roi),
                "in_roi_now": envelope.metrics.in_roi_now,
                "total_detected_in_frame": envelope.metrics.total_detected_in_frame,
                "excluded_outside_roi": envelope.metrics.excluded_outside_roi,
                "detection_persisted": bool(evidence_ok and db_ok and not is_duplicate_retry),
                "evidence_saved": bool(evidence_ok and not is_duplicate_retry),
                "duplicate_retry": bool(is_duplicate_retry),
                "id_deteccion": persisted_id,
                "original_evidence_path": orig_path,
                "annotated_evidence_path": annot_path,
                "timestamp": vr.timestamp.isoformat() if vr.timestamp else None,
            }
        )


    # =========================================================================
    # ENDPOINTS DE VISUALIZACIÓN EN VIVO Y MONITOREO DE CÁMARAS (VIGIA-CAM-01)
    # =========================================================================

    def _is_camera_registered(codigo: str) -> bool:
        coord = app.config.get("COORDINATOR")
        if coord and coord.registry:
            try:
                coord.registry.get_slot(codigo)
                return True
            except UnregisteredCameraError:
                return False
        topo = app.config.get("TOPOLOGY_REPOSITORY")
        if topo:
            try:
                cams = topo.get_all_cameras()
                return any(c.codigo.strip().upper() == codigo for c in cams)
            except Exception:
                pass
        return True

    @app.route("/api/v1/cameras/<codigo_camara>/live", methods=["GET"])
    def get_camera_live_frame(codigo_camara: str):
        """
        Retorna el fotograma JPEG anotado más reciente de la cámara con metadatos en encabezados.
        Si la cámara no está transmitiendo, entrega el fotograma de espera correspondiente.
        """
        codigo_clean = codigo_camara.strip().upper()
        if not _is_camera_registered(codigo_clean):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "CAMERA_NOT_FOUND",
                        "message": f"La cámara '{codigo_clean}' no está registrada en el sistema.",
                    }
                ),
                404,
            )

        cond = _get_camera_condition(codigo_clean)
        with cond:
            frame_info = _latest_camera_frames.get(codigo_clean)
            now = time.time()
            is_fresh = bool(frame_info and (now - frame_info.get("timestamp", 0.0) < 4.0))

            if is_fresh and frame_info:
                headers = {
                    "Content-Type": "image/jpeg",
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "X-Vision-Status": str(frame_info.get("status", "SIN_DATOS")),
                    "X-Vehicle-Detected": "true" if frame_info.get("vehicle_detected") else "false",
                    "X-Vehicle-Type": str(frame_info.get("tipo_vehiculo") or "NINGUNO"),
                    "X-Vehicle-Confidence": str(frame_info.get("confianza") or "0.0"),
                    "X-In-ROI": str(frame_info.get("in_roi", 0)),
                    "X-Frame-Sequence": str(frame_info.get("sequence", 0)),
                    "X-Last-Frame-Age": f"{now - frame_info['timestamp']:.2f}",
                }
                return Response(frame_info["jpeg"], mimetype="image/jpeg", headers=headers)
            else:
                standby_msg = "SIN SENAL" if frame_info else "EN ESPERA DE TRANSMISION"
                standby = _generate_standby_jpeg(codigo_clean, standby_msg)
                headers = {
                    "Content-Type": "image/jpeg",
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "X-Vision-Status": "SIN_SENAL" if frame_info else "EN_ESPERA",
                    "X-Vehicle-Detected": "false",
                    "X-In-ROI": "0",
                }
                return Response(standby, mimetype="image/jpeg", headers=headers)

    @app.route("/api/v1/cameras/<codigo_camara>/stream", methods=["GET"])
    def stream_camera_mjpeg(codigo_camara: str):
        """
        Emite un flujo continuo MJPEG (multipart/x-mixed-replace) con los fotogramas anotados
        en tiempo real para visualización directa en el Dashboard (VIGIA-CAM-01).
        """
        codigo_clean = codigo_camara.strip().upper()
        if not _is_camera_registered(codigo_clean):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "CAMERA_NOT_FOUND",
                        "message": f"La cámara '{codigo_clean}' no está registrada en el sistema.",
                    }
                ),
                404,
            )

        def generate_mjpeg():
            cond = _get_camera_condition(codigo_clean)
            last_seq = -1
            standby_sent_time = 0.0

            try:
                while True:
                    jpeg_data = None
                    with cond:
                        frame_info = _latest_camera_frames.get(codigo_clean)
                        now = time.time()
                        is_fresh = bool(frame_info and (now - frame_info.get("timestamp", 0.0) < 4.0))

                        if is_fresh and frame_info.get("sequence") != last_seq:
                            last_seq = frame_info["sequence"]
                            jpeg_data = frame_info["jpeg"]
                        else:
                            cond.wait(timeout=1.0)
                            frame_info = _latest_camera_frames.get(codigo_clean)
                            now = time.time()
                            is_fresh = bool(frame_info and (now - frame_info.get("timestamp", 0.0) < 4.0))
                            if is_fresh and frame_info.get("sequence") != last_seq:
                                last_seq = frame_info["sequence"]
                                jpeg_data = frame_info["jpeg"]
                            elif not is_fresh and (now - standby_sent_time > 1.0):
                                jpeg_data = _generate_standby_jpeg(codigo_clean, "EN ESPERA DE TRANSMISION")
                                standby_sent_time = now

                    if jpeg_data:
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n"
                            b"Content-Length: " + str(len(jpeg_data)).encode("ascii") + b"\r\n\r\n"
                            + jpeg_data + b"\r\n"
                        )
            except (GeneratorExit, ConnectionResetError, BrokenPipeError, OSError):
                logger.debug("Cliente desconectado de flujo MJPEG para '%s'", codigo_clean)
                return

        return Response(
            generate_mjpeg(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.route("/api/v1/cameras/<codigo_camara>/status", methods=["GET"])
    def get_camera_operational_status(codigo_camara: str):
        """
        Retorna el estado operativo en tiempo real de la cámara y sus indicadores de visión.
        """
        codigo_clean = codigo_camara.strip().upper()
        if not _is_camera_registered(codigo_clean):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "CAMERA_NOT_FOUND",
                        "message": f"La cámara '{codigo_clean}' no está registrada en el sistema.",
                    }
                ),
                404,
            )

        cond = _get_camera_condition(codigo_clean)
        with cond:
            frame_info = _latest_camera_frames.get(codigo_clean)
            now = time.time()
            is_transmitting = bool(frame_info and (now - frame_info.get("timestamp", 0.0) < 4.0))

            operational_state = "EN_ESPERA"
            if frame_info:
                age = now - frame_info.get("timestamp", 0.0)
                last_vis_status = frame_info.get("status", "")
                if last_vis_status in ("CAMERA_ERROR", "PROCESSING_ERROR", "PERSISTENCE_ERROR"):
                    operational_state = "ERROR"
                elif age < 4.0:
                    operational_state = "TRANSMITIENDO"
                else:
                    operational_state = "SIN_SEÑAL"
            else:
                pairing_repo = app.config.get("PAIRING_REPOSITORY")
                has_enrolled_device = False
                if pairing_repo:
                    try:
                        active_devs = pairing_repo.list_active_devices()
                        has_enrolled_device = any(
                            d.codigo_camara.strip().upper() == codigo_clean for d in active_devs
                        )
                    except Exception:
                        pass
                operational_state = "ENROLADA" if has_enrolled_device else "EN_ESPERA"

            return jsonify(
                {
                    "ok": True,
                    "codigo_camara": codigo_clean,
                    "is_transmitting": is_transmitting,
                    "operational_state": operational_state,
                    "last_frame_seconds_ago": round(now - frame_info["timestamp"], 2) if frame_info else None,
                    "status": (
                        frame_info.get("status", "DESCONOCIDO")
                        if is_transmitting
                        else "EN_ESPERA"
                    ),
                    "vehicle_detected": frame_info.get("vehicle_detected", False) if is_transmitting else False,
                    "tipo_vehiculo": frame_info.get("tipo_vehiculo") if is_transmitting else None,
                    "confianza": frame_info.get("confianza") if is_transmitting else None,
                    "in_roi": frame_info.get("in_roi", 0) if is_transmitting else 0,
                    "sequence": frame_info.get("sequence") if frame_info else None,
                }
            )


    # =========================================================================
    # ENDPOINTS DE ENROLAMIENTO QR Y GESTIÓN DE DISPOSITIVOS (MOB-QR-01)
    # =========================================================================

    @app.route("/api/v1/devices/pairing-qr", methods=["POST"])
    @require_rbac("ADMINISTRADOR")
    def generate_camera_pairing_qr():
        """
        Genera un nuevo código QR de enrolamiento efímero para una cámara lógica.
        Solo accesible para usuarios con rol ADMINISTRADOR.
        """
        pairing_repo = app.config.get("PAIRING_REPOSITORY")
        topo_repo = app.config.get("TOPOLOGY_REPOSITORY")
        if pairing_repo is None or topo_repo is None:
            return jsonify({"ok": False, "error": "PAIRING_UNAVAILABLE", "message": "Servicio de enrolamiento no disponible en este modo."}), 503

        data = request.get_json(silent=True) or {}
        codigo_camara = (data.get("codigo_camara") or data.get("codigo") or "").strip().upper()
        if not codigo_camara:
            return jsonify({"ok": False, "error": "MISSING_CAMERA_CODE", "message": "Debe especificar el código de la cámara (ej. CAM-ENTRADA)."}), 400

        cameras = topo_repo.get_cameras()
        target_cam = next((c for c in cameras if c.codigo == codigo_camara and c.activa), None)
        if not target_cam:
            return jsonify({"ok": False, "error": "CAMERA_NOT_FOUND", "message": f"La cámara '{codigo_camara}' no existe o no está activa."}), 404

        import secrets, io, base64
        import qrcode

        raw_claim_token = f"vigia_claim_{secrets.token_urlsafe(32)}"
        claim_hash = hash_token_sha256(raw_claim_token)
        current_sess = getattr(g, "current_session", None)
        if not current_sess:
            return jsonify({"ok": False, "error": "UNAUTHORIZED"}), 401
        user_id = current_sess.user_id

        ttl_minutes = int(data.get("ttl_minutes", 10))
        if ttl_minutes < 1 or ttl_minutes > 60:
            ttl_minutes = 10

        try:
            req_dto = pairing_repo.create_pairing_request(
                id_camara=target_cam.id_camara,
                token_claim_hash=claim_hash,
                creado_por=user_id,
                ttl_minutes=ttl_minutes,
            )
        except Exception as exc:
            logger.error("Error al crear pairing request: %s", exc)
            return jsonify({"ok": False, "error": "PAIRING_CREATION_FAILED", "message": str(exc)}), 500

        port = int(app.config.get("DEV_PORT") or os.environ.get("VIGIA_DEV_PORT", "5000"))
        tls_enabled = bool(request.is_secure or app.config.get("TLS_ENABLED"))

        try:
            urls = resolve_access_urls(port=port, tls_enabled=tls_enabled, app_config=app.config)
        except ValueError as val_err:
            return jsonify({
                "ok": False,
                "error": "INVALID_CONFIGURATION",
                "message": f"Configuración de URL de acceso inválida: {val_err}"
            }), 400

        qr_base_url = urls.get("effective_qr_base_url")
        if not qr_base_url:
            return jsonify({
                "ok": False,
                "error": "NO_LAN_ADDRESS_AVAILABLE",
                "message": (
                    "No se detectó una interfaz de red LAN física activa accesible para dispositivos móviles. "
                    "Conecte el equipo a una red Wi-Fi/Ethernet o configure 'VIGIA_PUBLIC_BASE_URL' en Software/.env."
                )
            }), 503

        # Rechazo explícito de loopback / 0.0.0.0 para enrolamiento móvil (VIGIA-NET-01)
        import urllib.parse
        parsed_qr = urllib.parse.urlsplit(qr_base_url)
        qr_host = (parsed_qr.hostname or "").lower()
        if qr_host in ("127.0.0.1", "localhost", "0.0.0.0") and not app.config.get("TESTING"):
            return jsonify({
                "ok": False,
                "error": "INVALID_QR_BASE_URL",
                "message": (
                    f"La dirección '{qr_base_url}' no es accesible desde un teléfono móvil. "
                    "Configure 'VIGIA_PUBLIC_BASE_URL' con la IP LAN del equipo en Software/.env."
                )
            }), 400

        pairing_url = f"{qr_base_url}/mobile?claim={raw_claim_token}&cam={target_cam.codigo}"
        local_pairing_url = f"{urls['local_url']}/mobile?claim={raw_claim_token}&cam={target_cam.codigo}"

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(pairing_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_base64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

        return jsonify({
            "ok": True,
            "id_solicitud": str(req_dto.id_solicitud),
            "request_id": str(req_dto.id_solicitud),
            "codigo_camara": target_cam.codigo,
            "nombre_camara": target_cam.nombre,
            "claim_token": raw_claim_token,
            "pairing_url": pairing_url,
            "enrollment_url": pairing_url,
            "lan_url": pairing_url,
            "local_url": local_pairing_url,
            "qr_image_data": qr_base64,
            "qr_base64_data_url": qr_base64,
            "expira_en": req_dto.expira_en.isoformat(),
            "estado": req_dto.estado.value,
        }), 201

    @app.route("/api/v1/devices", methods=["GET"])
    @require_rbac("ADMINISTRADOR", "GUARDIA")
    def list_authorized_devices():
        """Lista los dispositivos reales autorizados para las cámaras lógicas."""
        pairing_repo = app.config.get("PAIRING_REPOSITORY")
        if pairing_repo is None:
            return jsonify({"ok": True, "devices": [], "pending_requests": [], "total": 0}), 200

        try:
            devices = pairing_repo.list_active_devices()
            pending = pairing_repo.get_pending_requests()
            return jsonify({
                "ok": True,
                "devices": [
                    {
                        "id_credencial": str(d.id_credencial),
                        "id_camara": str(d.id_camara),
                        "codigo_camara": d.codigo_camara,
                        "nombre_camara": d.nombre_camara,
                        "nombre_dispositivo": d.nombre_dispositivo,
                        "dispositivo_info": d.dispositivo_info,
                        "activado_en": d.activado_en.isoformat(),
                        "activa": d.activa,
                        "ultima_actividad": d.ultima_actividad.isoformat() if d.ultima_actividad else None,
                    }
                    for d in devices
                ],
                "pending_requests": [
                    {
                        "id_solicitud": str(p.id_solicitud),
                        "id_camara": str(p.id_camara),
                        "estado": p.estado.value,
                        "dispositivo_info": p.dispositivo_info,
                        "creado_en": p.creado_en.isoformat(),
                        "expira_en": p.expira_en.isoformat(),
                    }
                    for p in pending
                ],
                "total": len(devices),
            }), 200
        except Exception as exc:
            logger.error("Error al listar dispositivos: %s", exc)
            return jsonify({"ok": False, "error": "QUERY_ERROR", "message": str(exc)}), 500

    @app.route("/api/v1/devices/<uuid:id_credencial>/revoke", methods=["POST"])
    @require_rbac("ADMINISTRADOR")
    def revoke_device_credential(id_credencial):
        """Revoca de forma inmediata una credencial de dispositivo físico."""
        pairing_repo = app.config.get("PAIRING_REPOSITORY")
        if pairing_repo is None:
            return jsonify({"ok": False, "error": "PAIRING_UNAVAILABLE"}), 503

        current_sess = getattr(g, "current_session", None)
        user_id = current_sess.user_id if current_sess else id_credencial

        body = request.get_json(silent=True) or {}
        motivo = (body.get("motivo") or "Revocación solicitada por Administrador").strip()

        try:
            revoked = pairing_repo.revoke_credential(
                id_credencial=id_credencial,
                revocado_por=user_id,
                motivo=motivo,
            )
            if not revoked:
                return jsonify({"ok": False, "error": "DEVICE_NOT_FOUND_OR_INACTIVE", "message": "Dispositivo no encontrado o ya revocado."}), 404
            return jsonify({"ok": True, "message": "Credencial de dispositivo revocada exitosamente."}), 200
        except Exception as exc:
            logger.error("Error al revocar dispositivo: %s", exc)
            return jsonify({"ok": False, "error": "REVOCATION_FAILED", "message": str(exc)}), 500

    # -------------------------------------------------------------------------
    # Flujo Móvil (Reclamo, Sondeo y Confirmación)
    # -------------------------------------------------------------------------

    @app.route("/api/v1/mobile/pairing/claim", methods=["POST"])
    def mobile_claim_pairing_token():
        """El dispositivo móvil escanea el QR y reclama el token efímero T_claim."""
        pairing_repo = app.config.get("PAIRING_REPOSITORY")
        topo_repo = app.config.get("TOPOLOGY_REPOSITORY")
        if pairing_repo is None or topo_repo is None:
            return jsonify({"ok": False, "error": "PAIRING_UNAVAILABLE"}), 503

        data = request.get_json(silent=True) or {}
        raw_claim = (data.get("claim_token") or "").strip()
        if not raw_claim:
            return jsonify({"ok": False, "error": "MISSING_CLAIM_TOKEN", "message": "Se requiere claim_token."}), 400

        claim_hash = hash_token_sha256(raw_claim)
        
        import secrets
        raw_poll_secret = secrets.token_urlsafe(32)
        poll_hash = hash_token_sha256(raw_poll_secret)

        disp_info = {
            "nombre": (data.get("device_name") or data.get("nombre") or "Cámara Móvil").strip()[:60],
            "user_agent": request.headers.get("User-Agent", "")[:255],
            "ip_origen": request.remote_addr,
            "reclamado_en": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        try:
            req_dto = pairing_repo.claim_pairing_request(
                token_claim_hash=claim_hash,
                token_poll_hash=poll_hash,
                dispositivo_info=disp_info,
            )
            cams = topo_repo.get_cameras()
            target_cam = next((c for c in cams if c.id_camara == req_dto.id_camara), None)
            cam_code = target_cam.codigo if target_cam else "UNKNOWN"
            cam_name = target_cam.nombre if target_cam else ""

            raw_stream_token = f"vigia_st_{secrets.token_urlsafe(32)}"
            stream_hash = hash_token_sha256(raw_stream_token)
            
            req_app, cred_app = pairing_repo.approve_and_issue_credential(
                id_solicitud=req_dto.id_solicitud,
                aprobado_por=req_dto.creado_por,
                token_transmision_hash=stream_hash,
                credencial_cifrada=raw_stream_token,
            )
            return jsonify({
                "ok": True,
                "estado": "APROBADA",
                "id_solicitud": str(req_dto.id_solicitud),
                "request_id": str(req_dto.id_solicitud),
                "id_credencial": str(cred_app.id_credencial),
                "codigo_camara": cam_code,
                "nombre_camara": cam_name,
                "poll_token": raw_poll_secret,
                "poll_secret": raw_poll_secret,
                "stream_token": raw_stream_token,
            }), 200

        except ValueError as val_err:
            err_code = str(val_err)
            if "NOT_FOUND" in err_code:
                return jsonify({"ok": False, "error": err_code, "message": "Código QR no encontrado."}), 404
            elif "EXPIRED" in err_code:
                return jsonify({"ok": False, "error": err_code, "message": "El código QR ha expirado."}), 409
            else:
                return jsonify({"ok": False, "error": err_code, "message": "El código QR ya fue utilizado o no es válido."}), 400
        except Exception as exc:
            logger.error("Error en mobile claim: %s", exc)
            return jsonify({"ok": False, "error": "CLAIM_FAILED", "message": str(exc)}), 500

    @app.route("/api/v1/mobile/pairing/status", methods=["GET"])
    def mobile_poll_pairing_status():
        """El móvil consulta periódicamente el estado de su solicitud."""
        pairing_repo = app.config.get("PAIRING_REPOSITORY")
        if pairing_repo is None:
            return jsonify({"ok": False, "error": "PAIRING_UNAVAILABLE"}), 503

        raw_poll = (request.args.get("poll_secret") or request.args.get("poll_token") or request.headers.get("X-Poll-Token") or "").strip()
        if not raw_poll:
            return jsonify({"ok": False, "error": "MISSING_POLL_TOKEN"}), 400

        poll_hash = hash_token_sha256(raw_poll)
        try:
            req_dto, cred_payload = pairing_repo.get_poll_status_and_credential(token_poll_hash=poll_hash)
            cred_id = None
            if req_dto.id_solicitud:
                try:
                    c_conn = pairing_repo._get_connection()
                    with c_conn:
                        with c_conn.cursor() as c_cur:
                            c_cur.execute("SELECT id_credencial FROM camara_credencial WHERE id_solicitud = %s;", (str(req_dto.id_solicitud),))
                            c_row = c_cur.fetchone()
                            if c_row:
                                cred_id = str(c_row[0])
                    c_conn.close()
                except Exception:
                    pass

            norm_status = "ISSUED" if (req_dto.estado.value == "APROBADA" and cred_payload) else ("CONFIRMED" if req_dto.estado.value == "CONSUMIDA" else req_dto.estado.value)
            return jsonify({
                "ok": True,
                "estado": req_dto.estado.value,
                "status": norm_status,
                "id_solicitud": str(req_dto.id_solicitud),
                "request_id": str(req_dto.id_solicitud),
                "id_credencial": cred_id,
                "credencial": cred_payload,
                "stream_token": cred_payload,
            }), 200
        except ValueError as val_err:
            return jsonify({"ok": False, "error": str(val_err), "message": "Token de sondeo no válido."}), 404
        except Exception as exc:
            logger.error("Error en mobile poll status: %s", exc)
            return jsonify({"ok": False, "error": "POLL_FAILED", "message": str(exc)}), 500

    @app.route("/api/v1/mobile/pairing/confirm", methods=["POST"])
    def mobile_confirm_credential():
        """El móvil confirma la recepción y almacenamiento de su credencial individual."""
        pairing_repo = app.config.get("PAIRING_REPOSITORY")
        if pairing_repo is None:
            return jsonify({"ok": False, "error": "PAIRING_UNAVAILABLE"}), 503

        data = request.get_json(silent=True) or {}
        raw_poll = (data.get("poll_secret") or data.get("poll_token") or request.headers.get("X-Poll-Token") or "").strip()
        if not raw_poll:
            return jsonify({"ok": False, "error": "MISSING_POLL_TOKEN"}), 400

        poll_hash = hash_token_sha256(raw_poll)
        try:
            confirmed = pairing_repo.confirm_credential_receipt(token_poll_hash=poll_hash)
            return jsonify({"ok": bool(confirmed)}), 200
        except Exception as exc:
            logger.error("Error en mobile confirm: %s", exc)
            return jsonify({"ok": False, "error": "CONFIRM_FAILED", "message": str(exc)}), 500


    @app.route("/api/v1/tls/ca.crt", methods=["GET"])
    def download_local_ca_cert():
        """
        Entrega el certificado público de la Autoridad Certificadora (CA) raíz local de VIGÍA
        para su instalación en el almacén de confianza de dispositivos móviles Android e iOS.
        """
        certs_dir: Path = app.config["CERTS_DIR"]
        ca_cert_file = (certs_dir / "vigia_root_ca.crt").resolve()
        if not ca_cert_file.is_file():
            ca_pem_file = (certs_dir / "vigia_root_ca.pem").resolve()
            if ca_pem_file.is_file():
                ca_cert_file = ca_pem_file
            else:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": "CA_CERT_NOT_FOUND",
                            "message": "El certificado raíz CA local aún no ha sido generado en el servidor.",
                        }
                    ),
                    404,
                )

        return (
            ca_cert_file.read_bytes(),
            200,
            {
                "Content-Type": "application/x-x509-ca-cert",
                "Content-Disposition": 'attachment; filename="vigia_root_ca.crt"',
            },
        )

    @app.route("/api/v1/tls/ca.crl", methods=["GET", "HEAD"])
    def download_local_ca_crl():
        """
        Entrega la Lista de Revocación de Certificados (CRL) X.509 de VIGÍA (VIGIA-TLS-02D)
        en formato binario DER (RFC 5280) con tipo MIME application/pkix-crl.
        """
        certs_dir: Path = app.config["CERTS_DIR"]
        crl_file = (certs_dir / CRL_FILENAME).resolve()
        if not crl_file.is_file():
            try:
                crl_file = ensure_crl_is_valid(certs_dir)
            except Exception as exc:
                logger.error("Error al asegurar CRL en endpoint Flask: %s", exc)
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": "CRL_NOT_FOUND",
                            "message": f"No fue posible generar o recuperar la CRL local: {exc}",
                        }
                    ),
                    404,
                )
        if request.method == "HEAD":
            resp = Response(b"", status=200, mimetype="application/pkix-crl")
            resp.headers["Content-Length"] = str(crl_file.stat().st_size)
            resp.headers["Cache-Control"] = "public, max-age=3600"
            resp.headers["X-Content-Type-Options"] = "nosniff"
            return resp
        return (
            crl_file.read_bytes(),
            200,
            {
                "Content-Type": "application/pkix-crl",
                "Content-Disposition": f'attachment; filename="{CRL_FILENAME}"',
                "Cache-Control": "public, max-age=3600",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.route("/api/v1/system/network", methods=["GET"])
    def get_system_network_info():
        """
        Retorna las direcciones de red de acceso local y LAN de VIGÍA Vision Systems (VIGIA-NET-01).
        Endpoint de solo lectura, sin credenciales, secretos ni tokens.
        """
        port = int(app.config.get("DEV_PORT") or os.environ.get("VIGIA_DEV_PORT", "5000"))
        tls_enabled = bool(request.is_secure or app.config.get("TLS_ENABLED"))

        urls = resolve_access_urls(port=port, tls_enabled=tls_enabled, app_config=app.config)

        return jsonify({
            "ok": True,
            "local_url": urls["local_url"],
            "lan_urls": urls["lan_urls"],
            "recommended_lan_url": urls["recommended_lan_url"],
            "public_base_url": urls["public_base_url"],
            "effective_qr_base_url": urls["effective_qr_base_url"],
            "port": urls["port"],
            "tls_enabled": urls["tls_enabled"],
            "interfaces": [
                {
                    "name": c["interface"],
                    "ip": c["ip"],
                    "url": f"{'https' if tls_enabled else 'http'}://{c['ip']}:{port}",
                    "is_recommended": c.get("is_recommended", False),
                }
                for c in urls["candidates"]
            ],
        }), 200

    return app


class TLSConfigError(ValueError):
    """Excepción para errores de configuración, formato o coherencia de certificados TLS."""


# Utilidades de descubrimiento de red delegadas a VIGIA_Core.network.lan_detector (VIGIA-NET-02)
from VIGIA_Core.network.lan_detector import (
    NetworkDiscoveryError,
    discover_wifi_ipv4,
    get_local_ipv4_addresses,
    get_windows_wlan_interfaces,
    is_usable_ipv4,
)


def validate_listen_ip(ip_str: str) -> str:
    """
    Valida que la IP indicada sea una IPv4 válida y pertenezca a una interfaz activa del PC.

    Falla explícitamente sin sustituciones automáticas por 0.0.0.0 ni 127.0.0.1.
    """
    if not ip_str or not isinstance(ip_str, str):
        raise ValueError("La dirección IP de escucha no puede ser nula ni vacía.")

    stripped_ip = ip_str.strip()
    try:
        parsed = ipaddress.IPv4Address(stripped_ip)
    except (ipaddress.AddressValueError, ValueError) as err:
        raise ValueError(
            f"La dirección IP '{stripped_ip}' no es una dirección IPv4 válida."
        ) from err

    cleaned_ip = str(parsed)
    local_ips = get_local_ipv4_addresses()
    if cleaned_ip not in local_ips:
        raise ValueError(
            f"La dirección IP configurada '{cleaned_ip}' no pertenece a ninguna interfaz IPv4 "
            f"activa de este equipo. Direcciones locales detectadas: {sorted(local_ips)}."
        )

    return cleaned_ip


def validate_tls_certificate_pair(
    cert_path: Union[str, Path],
    key_path: Union[str, Path],
    target_ip: Optional[str] = None,
) -> Tuple[Any, Any]:
    """
    Valida preventivamente que el certificado y la clave privada formen un par criptográfico
    válido, vigente y con la extensión SAN requerida para la IP de acceso.

    No imprime ni expone secretos ni el contenido de la clave privada.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    from cryptography.x509.oid import ExtensionOID

    cert_p = Path(cert_path).resolve()
    key_p = Path(key_path).resolve()

    if not cert_p.exists():
        raise FileNotFoundError(f"Archivo de certificado no encontrado: '{cert_p}'.")
    if not key_p.exists():
        raise FileNotFoundError(f"Archivo de clave privada no encontrado: '{key_p}'.")

    try:
        cert_bytes = cert_p.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_bytes)
    except Exception as err:
        raise TLSConfigError(f"No fue posible cargar o parsear el certificado PEM: {err}") from err

    try:
        key_bytes = key_p.read_bytes()
        private_key = serialization.load_pem_private_key(key_bytes, password=None)
    except Exception as err:
        raise TLSConfigError(f"No fue posible cargar o parsear la clave privada PEM: {err}") from err

    # 1. Comprobar correspondencia de par criptográfico (clave pública idéntica)
    cert_pub_bytes = cert.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_pub_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    if cert_pub_bytes != key_pub_bytes:
        raise TLSConfigError(
            "El certificado TLS y la clave privada no forman un par criptográfico coincidente."
        )

    # 2. Comprobar vigencia temporal
    now = datetime.datetime.now(datetime.timezone.utc)
    not_before = getattr(cert, "not_valid_before_utc", None) or cert.not_valid_before.replace(
        tzinfo=datetime.timezone.utc
    )
    not_after = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after.replace(
        tzinfo=datetime.timezone.utc
    )

    if now < not_before:
        raise TLSConfigError(
            f"El certificado TLS aún no es vigente (válido a partir de {not_before.isoformat()})."
        )
    if now > not_after:
        raise TLSConfigError(
            f"El certificado TLS ha expirado (vigencia finalizó en {not_after.isoformat()})."
        )

    # 3. Comprobar presencia de SAN para target_ip si se especifica
    if target_ip:
        clean_target = target_ip.strip()
        try:
            target_ip_obj = ipaddress.ip_address(clean_target)
        except ValueError:
            target_ip_obj = None

        try:
            san_ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            san_values = san_ext.value
        except x509.ExtensionNotFound as err:
            raise TLSConfigError(
                "El certificado TLS no contiene la extensión Subject Alternative Name (SAN)."
            ) from err

        has_target = False
        for general_name in san_values:
            if isinstance(general_name, x509.IPAddress):
                if target_ip_obj and general_name.value == target_ip_obj:
                    has_target = True
                    break
            elif isinstance(general_name, x509.DNSName):
                if general_name.value.lower() == clean_target.lower():
                    has_target = True
                    break

        if not has_target:
            raise TLSConfigError(
                f"El certificado TLS no contiene SAN para la dirección de acceso '{clean_target}'."
            )

    return cert, private_key


MANIFEST_FILENAME = "active_generation.json"
CRL_FILENAME = "vigia_root_ca.crl"
CRL_STATE_FILENAME = "crl_state.json"
DEFAULT_CRL_HTTP_PORT = 5080


def resolve_active_tls_pair(
    cert_dir_or_cert_path: Union[str, Path],
    key_path: Optional[Union[str, Path]] = None,
    target_ip: Optional[str] = None,
) -> Tuple[Path, Path]:
    """
    Resuelve y valida preventivamente el par de certificados TLS activo (VO-04E).

    Prioridad y Fuente de Verdad:
    1. Si existe ``active_generation.json`` en el directorio de certificados, este
       manifiesto constituye la ÚNICA FUENTE DE VERDAD:
       - Valida estructura del manifiesto y campos obligatorios.
       - Valida que las rutas de certificado y clave residan estrictamente dentro
         del subdirectorio autorizado ``generations/<gen_id>/``, rechazando rutas
         absolutas, secuencias de escape ('..') o resolución de enlaces simbólicos
         que escapen de dicho directorio.
       - Comprueba la existencia de ambos archivos versionados en disco.
       - Valida correspondencia criptográfica, vigencia temporal y SAN para ``target_ip``.
       - Sincroniza de forma secundaria y segura los archivos canónicos si difieren
         o están ausentes, sin que un fallo de sincronización canónica invalide la
         generación activa ni altere las rutas devueltas.
       - Devuelve directamente las rutas versionadas validadas que alimentan a Werkzeug.
       - Si el manifiesto está corrupto, es inseguro o apunta a una generación incompleta,
         falla de forma segura (fail-closed); nunca recurre silenciosamente a canónicos.
    2. Si NO existe el manifiesto (modo de compatibilidad heredada):
       - Solo si el par canónico completo existe y es válido, se resuelve dicho par.
       - Falla explícitamente si faltan archivos o son inconsistentes.

    Parámetros
    ----------
    cert_dir_or_cert_path : Union[str, Path]
        Ruta al directorio de certificados o ruta directa al archivo de certificado.
    key_path : Optional[Union[str, Path]]
        Ruta al archivo de clave privada (opcional si cert_dir_or_cert_path es un directorio).
    target_ip : Optional[str]
        Dirección IP de acceso esperada para verificar SAN.

    Retorna
    -------
    Tuple[Path, Path]
        (cert_path, key_path) versionados (o canónicos en modo heredado) validados y coherentes.
    """
    input_path = Path(cert_dir_or_cert_path).resolve()
    if input_path.is_dir():
        base_dir = input_path
        manifest_p = base_dir / MANIFEST_FILENAME
        cert_p = base_dir / "vigia_cert.pem"
        key_p = base_dir / "vigia_key.pem"
    else:
        cert_p = input_path
        base_dir = cert_p.parent
        manifest_p = base_dir / MANIFEST_FILENAME
        if key_path is not None:
            key_p = Path(key_path).resolve()
        else:
            key_p = base_dir / "vigia_key.pem"

    # =========================================================================
    # CASO 1: Existe el manifiesto activo (ÚNICA FUENTE DE VERDAD)
    # =========================================================================
    if manifest_p.exists():
        # A. Lectura y deserialización JSON segura
        try:
            raw_content = manifest_p.read_text(encoding="utf-8")
            manifest_data = json.loads(raw_content)
        except Exception as exc:
            raise TLSConfigError(
                f"El manifiesto TLS activo '{manifest_p}' está corrupto o no es un JSON válido: {exc}"
            ) from exc

        if not isinstance(manifest_data, dict):
            raise TLSConfigError(
                f"Estructura inválida en manifiesto TLS '{manifest_p}': se esperaba un objeto JSON."
            )

        # B. Validación de campos obligatorios
        gen_id = manifest_data.get("generation_id")
        rel_cert = manifest_data.get("cert_relpath")
        rel_key = manifest_data.get("key_relpath")

        if not gen_id or not isinstance(gen_id, str) or not gen_id.strip():
            raise TLSConfigError("El manifiesto TLS carece de un 'generation_id' válido.")
        if not rel_cert or not isinstance(rel_cert, str) or not rel_cert.strip():
            raise TLSConfigError("El manifiesto TLS carece de un 'cert_relpath' válido.")
        if not rel_key or not isinstance(rel_key, str) or not rel_key.strip():
            raise TLSConfigError("El manifiesto TLS carece de un 'key_relpath' válido.")

        # C. Contención de rutas y prevención estricta de Path Traversal
        p_rel_cert = Path(rel_cert)
        p_rel_key = Path(rel_key)

        if p_rel_cert.is_absolute() or p_rel_key.is_absolute():
            raise TLSConfigError(
                f"El manifiesto TLS contiene rutas absolutas no autorizadas: cert='{rel_cert}', key='{rel_key}'."
            )

        if ".." in p_rel_cert.parts or ".." in p_rel_key.parts:
            raise TLSConfigError(
                "El manifiesto TLS contiene secuencias de escape de directorio ('..') no autorizadas."
            )

        generations_dir = (base_dir / "generations").resolve()
        expected_gen_dir = (generations_dir / gen_id.strip()).resolve()

        gen_cert = (base_dir / rel_cert).resolve()
        gen_key = (base_dir / rel_key).resolve()

        try:
            gen_cert.relative_to(expected_gen_dir)
            gen_key.relative_to(expected_gen_dir)
        except ValueError as err:
            raise TLSConfigError(
                f"Las rutas del manifiesto escapan del directorio de generación autorizada '{expected_gen_dir}'."
            ) from err

        # D. Comprobar existencia física de ambos archivos versionados
        if not gen_cert.exists():
            raise FileNotFoundError(
                f"Archivo de certificado de la generación activa no encontrado en '{gen_cert}'."
            )
        if not gen_key.exists():
            raise FileNotFoundError(
                f"Archivo de clave privada de la generación activa no encontrado en '{gen_key}'."
            )

        # E. Validación criptográfica, temporal y de SAN sobre el par versionado
        validate_tls_certificate_pair(cert_path=gen_cert, key_path=gen_key, target_ip=target_ip)

        # F. Sincronización secundaria segura de archivos canónicos (best-effort, sin invalidar)
        try:
            if not cert_p.exists() or cert_p.read_bytes() != gen_cert.read_bytes():
                tmp_c = base_dir / f".{cert_p.name}.tmp.{uuid.uuid4().hex[:8]}"
                tmp_c.write_bytes(gen_cert.read_bytes())
                os.replace(tmp_c, cert_p)
            if not key_p.exists() or key_p.read_bytes() != gen_key.read_bytes():
                tmp_k = base_dir / f".{key_p.name}.tmp.{uuid.uuid4().hex[:8]}"
                tmp_k.write_bytes(gen_key.read_bytes())
                os.replace(tmp_k, key_p)
        except Exception as sync_err:
            logger.warning(
                "Aviso de compatibilidad: no fue posible sincronizar archivos canónicos "
                "(la generación versionada activa prevalece sin afectación): %s",
                sync_err,
            )

        # G. Devolver directamente el par versionado validado
        logger.info(
            "Generación TLS activa '%s' resuelta y validada exitosamente para IP '%s'.",
            gen_id,
            target_ip or "sin_filtrado_ip",
        )
        return gen_cert, gen_key

    # =========================================================================
    # CASO 2: Modo de compatibilidad heredada (sin manifiesto)
    # =========================================================================
    logger.warning(
        "No se encontró '%s' en '%s'. Evaluando par canónico en modo de compatibilidad heredada.",
        MANIFEST_FILENAME,
        base_dir,
    )
    if cert_p.exists() and key_p.exists():
        validate_tls_certificate_pair(cert_path=cert_p, key_path=key_p, target_ip=target_ip)
        logger.info("Modo heredado exitoso: par canónico completo y validado en '%s'.", base_dir)
        return cert_p, key_p

    missing = []
    if not cert_p.exists():
        missing.append(str(cert_p))
    if not key_p.exists():
        missing.append(str(key_p))
    raise FileNotFoundError(
        f"No se encontró un manifiesto TLS activo en '{manifest_p}' ni un par canónico completo válido. "
        f"Archivos ausentes: {', '.join(missing)}."
    )


def generate_vigia_tls_certificate(
    target_ip: str,
    cert_path: Union[str, Path],
    key_path: Union[str, Path],
    valid_days: int = 30,
    overwrite: bool = False,
) -> Tuple[Path, Path]:
    """
    Genera un certificado y clave privada TLS auto-firmados específicos para VIGÍA.

    Incluye la IP objetivo y localhost en SubjectAlternativeName (SAN) para que
    los navegadores móviles reconozcan la correspondencia del host bajo HTTPS.

    Parámetros
    ----------
    target_ip : str
        Dirección IP de la interfaz local autorizada (ej. '192.168.1.85').
    cert_path : Union[str, Path]
        Ruta de destino para el archivo de certificado (ej. '.certs/vigia_cert.pem').
    key_path : Union[str, Path]
        Ruta de destino para la clave privada (ej. '.certs/vigia_key.pem').
    valid_days : int
        Días de vigencia del certificado (por omisión 30).
    overwrite : bool
        Si es ``False`` (por omisión), no sobrescribe archivos existentes y lanza
        ``FileExistsError``.

    Retorna
    -------
    Tuple[Path, Path]
        (cert_path, key_path) validados y generados.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    cert_p = Path(cert_path).resolve()
    key_p = Path(key_path).resolve()
    base_dir = cert_p.parent
    manifest_p = base_dir / MANIFEST_FILENAME

    if not overwrite and (cert_p.exists() or key_p.exists()):
        raise FileExistsError(
            f"El certificado o clave ya existen en '{cert_p}' / '{key_p}'. "
            "No se sobrescriben archivos existentes de forma silenciosa. "
            "Establezca overwrite=True si desea regenerarlos explícitamente."
        )

    base_dir.mkdir(parents=True, exist_ok=True)

    # 1. Crear staging aislado por versión/ID de generación
    gen_id = f"gen_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    generations_dir = base_dir / "generations"
    gen_dir = generations_dir / gen_id
    gen_dir.mkdir(parents=True, exist_ok=True)

    staged_cert_p = gen_dir / cert_p.name
    staged_key_p = gen_dir / key_p.name

    try:
        # A. Clave privada RSA 2048-bit
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # B. Sujeto y Emisor
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "MX"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "VIGIA Vision Systems"),
                x509.NameAttribute(NameOID.COMMON_NAME, f"VIGIA Local Ingest ({target_ip})"),
            ]
        )

        # C. Subject Alternative Name (SAN)
        san_entries = [
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        ]
        try:
            parsed_ip = ipaddress.ip_address(target_ip.strip())
            if str(parsed_ip) != "127.0.0.1":
                san_entries.append(x509.IPAddress(parsed_ip))
        except ValueError:
            if target_ip.strip().lower() != "localhost":
                san_entries.append(x509.DNSName(target_ip.strip()))

        now = datetime.datetime.now(datetime.timezone.utc)
        ski = x509.SubjectKeyIdentifier.from_public_key(private_key.public_key())
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=min(valid_days, 397)))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=True,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                critical=False,
            )
            .add_extension(ski, critical=False)
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(ski),
                critical=False,
            )
            .add_extension(
                x509.SubjectAlternativeName(san_entries),
                critical=False,
            )
            .sign(private_key, hashes.SHA256())
        )

        # D. Escribir archivos staged en gen_dir
        staged_key_p.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        staged_cert_p.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

        # E. Validación preventiva pre-activación del par generado en staging
        validate_tls_certificate_pair(
            cert_path=staged_cert_p,
            key_path=staged_key_p,
            target_ip=target_ip,
        )

    except Exception as exc:
        # Purga inmediata y segura del staging: los archivos activos previos permanecen intactos
        shutil.rmtree(gen_dir, ignore_errors=True)
        logger.error(
            "Fallo en generación o validación preventiva de certificados TLS. Operación abortada: %s",
            exc,
        )
        raise

    # 2. Activación Atómica (sólo se alcanza si la validación previa fue 100% exitosa)
    tmp_manifest = base_dir / f".{MANIFEST_FILENAME}.tmp.{uuid.uuid4().hex[:8]}"
    manifest_data = {
        "generation_id": gen_id,
        "target_ip": target_ip,
        "cert_file": str(staged_cert_p.name),
        "key_file": str(staged_key_p.name),
        "cert_relpath": f"generations/{gen_id}/{staged_cert_p.name}",
        "key_relpath": f"generations/{gen_id}/{staged_key_p.name}",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    tmp_manifest.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    os.replace(tmp_manifest, manifest_p)

    # Actualizar atómicamente los archivos canónicos para compatibilidad transparente
    tmp_cert = base_dir / f".{cert_p.name}.tmp.{uuid.uuid4().hex[:8]}"
    tmp_key = base_dir / f".{key_p.name}.tmp.{uuid.uuid4().hex[:8]}"
    try:
        tmp_cert.write_bytes(staged_cert_p.read_bytes())
        tmp_key.write_bytes(staged_key_p.read_bytes())
        os.replace(tmp_cert, cert_p)
        os.replace(tmp_key, key_p)
    finally:
        if tmp_cert.exists():
            tmp_cert.unlink(missing_ok=True)
        if tmp_key.exists():
            tmp_key.unlink(missing_ok=True)

    logger.info("Generación TLS '%s' activada exitosamente para la IP: %s", gen_id, target_ip)
    return cert_p, key_p


def load_crl_state(cert_dir: Union[str, Path]) -> Dict[str, Any]:
    """
    Carga de forma segura el estado persistente de la CRL (crl_state.json).
    Si el archivo no existe o está corrupto, intenta recuperar la secuencia y certificados
    revocados leyendo vigia_root_ca.crl (DER). Si tampoco existe, inicializa un estado limpio.
    """
    from cryptography import x509

    base_dir = Path(cert_dir).resolve()
    state_file = base_dir / CRL_STATE_FILENAME
    crl_file = base_dir / CRL_FILENAME

    if state_file.is_file():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "crl_number" in data and "revoked_serials" in data:
                return data
        except Exception as exc:
            logger.warning(
                "Archivo %s corrupto o ilegible (%s). Intentando recuperación desde %s...",
                state_file.name,
                exc,
                crl_file.name,
            )

    # Recuperación desde CRL DER si existe
    if crl_file.is_file():
        try:
            der_bytes = crl_file.read_bytes()
            crl = x509.load_der_x509_crl(der_bytes)
            recovered_num = 1
            try:
                crl_num_ext = crl.extensions.get_extension_for_oid(x509.ExtensionOID.CRL_NUMBER)
                recovered_num = int(crl_num_ext.value.crl_number)
            except Exception:
                pass

            recovered_revoked: List[Dict[str, Any]] = []
            for r in crl:
                rev_dt = getattr(r, "revocation_date_utc", None) or r.revocation_date
                if rev_dt.tzinfo is None:
                    rev_dt = rev_dt.replace(tzinfo=datetime.timezone.utc)
                recovered_revoked.append(
                    {
                        "serial_number": int(r.serial_number),
                        "revocation_date": rev_dt.isoformat(),
                        "reason": "keyCompromise",
                    }
                )

            logger.info(
                "Estado CRL recuperado desde archivo DER existente: secuencia #%d, %d serial(es) revocados.",
                recovered_num,
                len(recovered_revoked),
            )
            return {
                "crl_number": recovered_num,
                "revoked_serials": recovered_revoked,
            }
        except Exception as der_err:
            logger.warning("Fallo al recuperar estado desde CRL DER: %s", der_err)

    return {
        "crl_number": 0,
        "revoked_serials": [],
    }


def save_crl_state_atomic(cert_dir: Union[str, Path], state_data: Dict[str, Any]) -> Path:
    """
    Persiste atómicamente el estado de la CRL en crl_state.json mediante archivo temporal.
    """
    base_dir = Path(cert_dir).resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    state_file = base_dir / CRL_STATE_FILENAME
    tmp_file = base_dir / f".{CRL_STATE_FILENAME}.tmp.{uuid.uuid4().hex[:8]}"
    try:
        tmp_file.write_text(json.dumps(state_data, indent=2), encoding="utf-8")
        os.replace(tmp_file, state_file)
    finally:
        if tmp_file.exists():
            tmp_file.unlink(missing_ok=True)
    return state_file


def generate_vigia_crl(
    cert_dir: Union[str, Path],
    crl_number: Optional[int] = None,
    revoked_serials: Optional[List[Dict[str, Any]]] = None,
    valid_days: int = 7,
) -> Tuple[Path, Path]:
    """
    Genera atómicamente la Lista de Revocación de Certificados (CRL) X.509 v2 de VIGÍA (RFC 5280).
    Firmada con la clave privada de vigia_root_ca_key.pem y hashes.SHA256().
    Incorpora extensiones AuthorityKeyIdentifier y CRLNumber de secuencia monótona estricta.
    Retorna (crl_file_path, state_file_path).
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization

    base_dir = Path(cert_dir).resolve()
    ca_cert_p = base_dir / "vigia_root_ca.crt"
    ca_key_p = base_dir / "vigia_root_ca_key.pem"
    crl_file_p = base_dir / CRL_FILENAME

    if not ca_cert_p.is_file() or not ca_key_p.is_file():
        raise FileNotFoundError(
            f"No se encontraron los archivos de la Root CA en '{base_dir}'. "
            "Se requiere vigia_root_ca.crt y vigia_root_ca_key.pem."
        )

    ca_cert = x509.load_pem_x509_certificate(ca_cert_p.read_bytes())
    ca_key = serialization.load_pem_private_key(ca_key_p.read_bytes(), password=None)

    current_state = load_crl_state(base_dir)

    if crl_number is not None:
        effective_num = int(crl_number)
    else:
        effective_num = int(current_state.get("crl_number", 0)) + 1

    if revoked_serials is not None:
        effective_revoked = list(revoked_serials)
    else:
        effective_revoked = list(current_state.get("revoked_serials", []))

    now = datetime.datetime.now(datetime.timezone.utc)
    this_update = now - datetime.timedelta(minutes=5)
    next_update = now + datetime.timedelta(days=max(1, valid_days))

    builder = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(ca_cert.subject)
        .last_update(this_update)
        .next_update(next_update)
    )

    # AuthorityKeyIdentifier extensión coincidente con el SKI de la Root CA
    aki = x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key())
    builder = builder.add_extension(aki, critical=False)

    # CRLNumber extensión monótona
    builder = builder.add_extension(x509.CRLNumber(effective_num), critical=False)

    reason_mapping = {
        "unspecified": x509.ReasonFlags.unspecified,
        "keycompromise": x509.ReasonFlags.key_compromise,
        "key_compromise": x509.ReasonFlags.key_compromise,
        "cacompromise": x509.ReasonFlags.ca_compromise,
        "ca_compromise": x509.ReasonFlags.ca_compromise,
        "affiliationchanged": x509.ReasonFlags.affiliation_changed,
        "affiliation_changed": x509.ReasonFlags.affiliation_changed,
        "superseded": x509.ReasonFlags.superseded,
        "cessationofoperation": x509.ReasonFlags.cessation_of_operation,
        "cessation_of_operation": x509.ReasonFlags.cessation_of_operation,
        "certificatehold": x509.ReasonFlags.certificate_hold,
        "certificate_hold": x509.ReasonFlags.certificate_hold,
        "privilegewithdrawn": x509.ReasonFlags.privilege_withdrawn,
        "privilege_withdrawn": x509.ReasonFlags.privilege_withdrawn,
        "aacompromise": x509.ReasonFlags.aa_compromise,
        "aa_compromise": x509.ReasonFlags.aa_compromise,
        "removefromcrl": x509.ReasonFlags.remove_from_crl,
        "remove_from_crl": x509.ReasonFlags.remove_from_crl,
    }

    for item in effective_revoked:
        s_num = int(item["serial_number"])
        rev_dt_raw = item.get("revocation_date")
        if isinstance(rev_dt_raw, str):
            rev_dt = datetime.datetime.fromisoformat(rev_dt_raw)
        elif isinstance(rev_dt_raw, datetime.datetime):
            rev_dt = rev_dt_raw
        else:
            rev_dt = now
        if rev_dt.tzinfo is None:
            rev_dt = rev_dt.replace(tzinfo=datetime.timezone.utc)

        raw_reason = str(item.get("reason", "key_compromise")).strip().lower()
        reason_flag = reason_mapping.get(raw_reason, x509.ReasonFlags.key_compromise)

        rev_builder = (
            x509.RevokedCertificateBuilder()
            .serial_number(s_num)
            .revocation_date(rev_dt)
            .add_extension(x509.CRLReason(reason_flag), critical=False)
        )
        builder = builder.add_revoked_certificate(rev_builder.build())

    crl = builder.sign(ca_key, hashes.SHA256())
    crl_der = crl.public_bytes(serialization.Encoding.DER)

    tmp_crl_p = base_dir / f".{CRL_FILENAME}.tmp.{uuid.uuid4().hex[:8]}"
    try:
        tmp_crl_p.write_bytes(crl_der)
        os.replace(tmp_crl_p, crl_file_p)
    finally:
        if tmp_crl_p.exists():
            tmp_crl_p.unlink(missing_ok=True)

    new_state = {
        "crl_number": effective_num,
        "last_updated": now.isoformat(),
        "this_update": this_update.isoformat(),
        "next_update": next_update.isoformat(),
        "revoked_serials": effective_revoked,
    }
    state_p = save_crl_state_atomic(base_dir, new_state)

    logger.info(
        "CRL X.509 emitida exitosamente: secuencia #%d, %d certificado(s) revocado(s), próxima actualización: %s",
        effective_num,
        len(effective_revoked),
        next_update.isoformat(),
    )
    return crl_file_p, state_p


def ensure_crl_is_valid(cert_dir: Union[str, Path], renew_window_days: int = 2) -> Path:
    """
    Comprueba si existe la CRL y si su validez temporal está dentro del umbral seguro.
    Si no existe o si restan menos de renew_window_days antes de nextUpdate, la regenera.
    """
    from cryptography import x509

    base_dir = Path(cert_dir).resolve()
    crl_path = base_dir / CRL_FILENAME

    needs_generation = False
    if not crl_path.is_file():
        needs_generation = True
    else:
        try:
            crl_bytes = crl_path.read_bytes()
            crl = x509.load_der_x509_crl(crl_bytes)
            nu = getattr(crl, "next_update_utc", None) or crl.next_update
            if nu.tzinfo is None:
                nu = nu.replace(tzinfo=datetime.timezone.utc)
            now = datetime.datetime.now(datetime.timezone.utc)
            if nu - now < datetime.timedelta(days=max(0, renew_window_days)):
                logger.info(
                    "CRL próxima a expirar o expirada (nextUpdate: %s). Regenerando...",
                    nu.isoformat(),
                )
                needs_generation = True
        except Exception as exc:
            logger.warning("Fallo al inspeccionar CRL existente (%s). Regenerando...", exc)
            needs_generation = True

    if needs_generation:
        crl_path, _ = generate_vigia_crl(base_dir)

    return crl_path


def revoke_certificate(
    cert_dir: Union[str, Path],
    serial_number: int,
    reason: str = "keyCompromise",
) -> Tuple[Path, Path]:
    """
    Registra un número de serie como revocado, incrementa monótonamente la secuencia
    y reemite de inmediato la CRL firmada por la Root CA.
    """
    base_dir = Path(cert_dir).resolve()
    state = load_crl_state(base_dir)
    revoked = list(state.get("revoked_serials", []))

    serial_int = int(serial_number)
    already_present = any(int(r.get("serial_number", -1)) == serial_int for r in revoked)
    if not already_present:
        now = datetime.datetime.now(datetime.timezone.utc)
        revoked.append(
            {
                "serial_number": serial_int,
                "revocation_date": now.isoformat(),
                "reason": reason,
            }
        )

    return generate_vigia_crl(base_dir, revoked_serials=revoked)


class CRLRequestHandler(http.server.BaseHTTPRequestHandler):
    """
    Manejador HTTP estricto y minimalista para publicación y distribución de CRL (RFC 5280).
    Acepta exclusivamente solicitudes GET y HEAD para /api/v1/tls/ca.crl y /api/v1/tls/ca.crt.
    Rechaza cualquier otro método con HTTP 405 y cualquier otra ruta con HTTP 404.
    Protege absolutamente contra divulgación de claves privadas o archivos del sistema.
    """
    server: "CRLHttpServer"

    def do_GET(self) -> None:
        self._serve_resource(send_body=True)

    def do_HEAD(self) -> None:
        self._serve_resource(send_body=False)

    def _serve_resource(self, send_body: bool) -> None:
        clean_path = self.path.split("?")[0].rstrip("/")
        if clean_path == "/api/v1/tls/ca.crl":
            crl_path = self.server.certs_dir / CRL_FILENAME
            if not crl_path.is_file():
                try:
                    crl_path = ensure_crl_is_valid(self.server.certs_dir)
                except Exception as exc:
                    logger.error("Error al asegurar CRL para cliente HTTP: %s", exc)
                    self.send_error(500, f"Error al generar CRL: {exc}")
                    return
            try:
                data = crl_path.read_bytes()
            except OSError as exc:
                self.send_error(500, f"Error al leer CRL: {exc}")
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/pkix-crl")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            self.end_headers()
            if send_body:
                self.wfile.write(data)

        elif clean_path == "/api/v1/tls/ca.crt":
            ca_path = self.server.certs_dir / "vigia_root_ca.crt"
            if not ca_path.is_file():
                self.send_error(404, "Certificado Root CA no encontrado")
                return
            try:
                data = ca_path.read_bytes()
            except OSError as exc:
                self.send_error(500, f"Error al leer Root CA: {exc}")
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/x-x509-ca-cert")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            self.end_headers()
            if send_body:
                self.wfile.write(data)
        else:
            self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD")
        self.end_headers()

    def do_PUT(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD")
        self.end_headers()

    def do_DELETE(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD")
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD")
        self.end_headers()

    def do_PATCH(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug("CRL-HTTP: " + format, *args)


class CRLHttpServer(http.server.ThreadingHTTPServer):
    """
    Servidor HTTP dedicado para distribución de CRL y Root CA sobre red local (RFC 5280).
    Se ejecuta como hilo demonio desacoplado de Werkzeug para evitar interdependencias circulares TLS.
    """
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: Tuple[str, int], certs_dir: Union[str, Path]):
        self.certs_dir = Path(certs_dir).resolve()
        super().__init__(server_address, CRLRequestHandler)
        self._thread: Optional[threading.Thread] = None

    def start_in_background(self) -> None:
        self._thread = threading.Thread(
            target=self.serve_forever,
            name="VigiaCRLHttpServerThread",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Servidor de distribución CRL iniciado en http://%s:%d/api/v1/tls/ca.crl",
            self.server_address[0],
            self.server_address[1],
        )

    def stop(self) -> None:
        self.shutdown()
        self.server_close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info("Servidor de distribución CRL detenido correctamente.")


def start_crl_http_server(
    certs_dir: Union[str, Path],
    host: str = "0.0.0.0",
    port: int = 5080,
) -> CRLHttpServer:
    server = CRLHttpServer((host, port), certs_dir)
    server.start_in_background()
    return server


def generate_vigia_local_ca_bundle(
    target_ip: str,
    cert_dir: Union[str, Path],
    valid_days: int = 90,
    crl_http_port: Optional[int] = None,
    overwrite: bool = False,
) -> Tuple[Path, Path, Path]:
    """
    Genera una jerarquía PKI local de dos niveles (Root CA + Certificado de Servidor)
    para permitir la instalación del certificado raíz de confianza en Android e iOS:
      1. ``vigia_root_ca.crt`` (CA:TRUE, KeyUsage=keyCertSign/cRLSign): instalable en el
         almacén de credenciales de Android e iOS.
      2. ``vigia_cert.pem`` y ``vigia_key.pem`` (CA:FALSE, ExtendedKeyUsage=serverAuth,
         SAN=[localhost, 127.0.0.1, target_ip]), firmados por la Root CA local y registrados
         atómicamente en ``active_generation.json``.

    Retorna ``(server_cert_path, server_key_path, ca_cert_path)``.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    base_dir = Path(cert_dir).resolve()
    base_dir.mkdir(parents=True, exist_ok=True)

    ca_cert_p = base_dir / "vigia_root_ca.crt"
    ca_key_p = base_dir / "vigia_root_ca_key.pem"
    cert_p = base_dir / "vigia_cert.pem"
    key_p = base_dir / "vigia_key.pem"
    manifest_p = base_dir / MANIFEST_FILENAME

    if not overwrite and (cert_p.exists() or key_p.exists()):
        raise FileExistsError(
            f"El par de certificados de servidor ya existe en '{base_dir}'. "
            "Use overwrite=True para regenerar."
        )

    now = datetime.datetime.now(datetime.timezone.utc)

    # 1. Cargar o generar la Autoridad Certificadora (Root CA) local
    if ca_cert_p.is_file() and ca_key_p.is_file():
        ca_cert = x509.load_pem_x509_certificate(ca_cert_p.read_bytes())
        ca_key = serialization.load_pem_private_key(ca_key_p.read_bytes(), password=None)
    else:
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ca_subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "MX"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "VIGIA Vision Systems"),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Seguridad e Infraestructura LAN"),
                x509.NameAttribute(NameOID.COMMON_NAME, "VIGIA Local Root CA"),
            ]
        )
        ca_ski = x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key())
        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(ca_subject)
            .issuer_name(ca_subject)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(ca_ski, critical=False)
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(ca_ski),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        ca_key_p.write_bytes(
            ca_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        ca_cert_p.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))

    # Asegurar existencia y validez de la Lista de Revocación de Certificados (CRL) privada (VIGIA-TLS-02D)
    ensure_crl_is_valid(base_dir)

    # 2. Generar certificado hoja de servidor en directorio versionado y firmarlo con la Root CA
    gen_id = f"gen_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    gen_dir = base_dir / "generations" / gen_id
    gen_dir.mkdir(parents=True, exist_ok=True)
    staged_cert_p = gen_dir / cert_p.name
    staged_key_p = gen_dir / key_p.name

    try:
        srv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        srv_subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "MX"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "VIGIA Vision Systems"),
                x509.NameAttribute(NameOID.COMMON_NAME, f"VIGIA LAN Server ({target_ip})"),
            ]
        )
        san_entries = [
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        ]
        try:
            parsed_ip = ipaddress.ip_address(target_ip.strip())
            if str(parsed_ip) != "127.0.0.1":
                san_entries.append(x509.IPAddress(parsed_ip))
        except ValueError:
            if target_ip.strip().lower() != "localhost":
                san_entries.append(x509.DNSName(target_ip.strip()))

        srv_ski = x509.SubjectKeyIdentifier.from_public_key(srv_key.public_key())
        ca_aki = x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key())
        effective_crl_port = crl_http_port or int(
            os.environ.get("VIGIA_CRL_HTTP_PORT", str(DEFAULT_CRL_HTTP_PORT))
        )
        cdp_uri = f"http://{target_ip.strip()}:{effective_crl_port}/api/v1/tls/ca.crl"
        cdp_ext = x509.CRLDistributionPoints([
            x509.DistributionPoint(
                full_name=[x509.UniformResourceIdentifier(cdp_uri)],
                relative_name=None,
                crl_issuer=None,
                reasons=None,
            )
        ])
        srv_cert = (
            x509.CertificateBuilder()
            .subject_name(srv_subject)
            .issuer_name(ca_cert.subject)
            .public_key(srv_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=min(valid_days, 397)))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=True,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(srv_ski, critical=False)
            .add_extension(ca_aki, critical=False)
            .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
            .add_extension(cdp_ext, critical=False)
            .sign(ca_key, hashes.SHA256())
        )

        # Guardar cadena completa (servidor + CA) en vigia_cert.pem y clave en vigia_key.pem
        staged_key_p.write_bytes(
            srv_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        chain_pem = (
            srv_cert.public_bytes(serialization.Encoding.PEM)
            + ca_cert.public_bytes(serialization.Encoding.PEM)
        )
        staged_cert_p.write_bytes(chain_pem)

        validate_tls_certificate_pair(
            cert_path=staged_cert_p,
            key_path=staged_key_p,
            target_ip=target_ip,
        )
    except Exception:
        shutil.rmtree(gen_dir, ignore_errors=True)
        raise

    tmp_manifest = base_dir / f".{MANIFEST_FILENAME}.tmp.{uuid.uuid4().hex[:8]}"
    manifest_data = {
        "generation_id": gen_id,
        "target_ip": target_ip,
        "ca_signed": True,
        "ca_cert_file": ca_cert_p.name,
        "cert_file": str(staged_cert_p.name),
        "key_file": str(staged_key_p.name),
        "cert_relpath": f"generations/{gen_id}/{staged_cert_p.name}",
        "key_relpath": f"generations/{gen_id}/{staged_key_p.name}",
        "cdp_url": cdp_uri,
        "crl_port": effective_crl_port,
        "created_at": now.isoformat(),
    }
    tmp_manifest.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    os.replace(tmp_manifest, manifest_p)

    tmp_cert = base_dir / f".{cert_p.name}.tmp.{uuid.uuid4().hex[:8]}"
    tmp_key = base_dir / f".{key_p.name}.tmp.{uuid.uuid4().hex[:8]}"
    try:
        tmp_cert.write_bytes(staged_cert_p.read_bytes())
        tmp_key.write_bytes(staged_key_p.read_bytes())
        os.replace(tmp_cert, cert_p)
        os.replace(tmp_key, key_p)
    finally:
        if tmp_cert.exists():
            tmp_cert.unlink(missing_ok=True)
        if tmp_key.exists():
            tmp_key.unlink(missing_ok=True)

    return cert_p, key_p, ca_cert_p


def validate_private_lan_or_loopback_ip(ip_str: str) -> str:
    """
    Valida que la IP de escucha pertenezca a una interfaz local activa del equipo y
    sea estrictamente una dirección privada de red local (RFC 1918) o loopback (127.0.0.1).
    Prohíbe exponer el backend a direcciones IP públicas de Internet.
    """
    cleaned = validate_listen_ip(ip_str)
    ip_obj = ipaddress.IPv4Address(cleaned)
    if ip_obj.is_link_local or ip_obj.is_unspecified or ip_obj.is_multicast:
        raise ValueError(
            f"La dirección IP '{cleaned}' (link-local/APIPA o comodín) no es apta para el servicio seguro."
        )
    if not (ip_obj.is_private or ip_obj.is_loopback):
        raise ValueError(
            f"Política de seguridad: se prohíbe enlazar el backend a la dirección IP pública '{cleaned}'."
        )
    return cleaned


# Utilidades de resolucion de LAN y URLs delegadas a VIGIA_Core.network.lan_detector (VIGIA-NET-02)
from VIGIA_Core.network.lan_detector import (
    NoLanAddressError,
    discover_all_lan_candidates,
    discover_lan_ipv4,
    get_default_route_ip,
    resolve_access_urls,
    validate_public_base_url,
)


def regenerate_vigia_tls_certificate(
    target_ip: str,
    cert_path: Union[str, Path],
    key_path: Union[str, Path],
    valid_days: int = 30,
) -> Tuple[Path, Path]:
    """
    Regenera explícitamente el certificado TLS de VIGÍA para una nueva IP (overwrite=True).

    Requiere invocación intencional y emite registro explícito de auditoría.
    """
    logger.warning(
        "Regenerando certificado TLS de VIGÍA para la nueva dirección IP objetivo: %s",
        target_ip,
    )
    return generate_vigia_tls_certificate(
        target_ip=target_ip,
        cert_path=cert_path,
        key_path=key_path,
        valid_days=valid_days,
        overwrite=True,
    )



class NonBlockingTLSThreadedServer(ThreadedWSGIServer):
    """
    Servidor WSGI multihilo con negociación TLS delegada a los hilos de trabajo (VIGIA-NET-03).

    Evita que el bucle de aceptación principal (accept) se bloquee de forma síncrona
    ante conexiones TCP sin TLS inmediato (como Test-NetConnection, inspecciones pasivas
    de red o conexiones especulativas de navegadores modernos).
    """

    def __init__(
        self,
        host: str,
        port: int,
        app: Any,
        ssl_context: Any = None,
        **kwargs: Any,
    ) -> None:
        raw_ctx = ssl_context
        if isinstance(raw_ctx, tuple):
            raw_ctx = load_ssl_context(*raw_ctx)
        super().__init__(host, port, app, ssl_context=None, **kwargs)
        self.ssl_context = raw_ctx

    def finish_request(self, request: Any, client_address: Any) -> None:
        if self.ssl_context is not None:
            request.settimeout(10.0)
            try:
                request = self.ssl_context.wrap_socket(request, server_side=True)
            except (ssl.SSLError, OSError):
                try:
                    request.close()
                except Exception:
                    pass
                return
            request.settimeout(None)
        super().finish_request(request, client_address)


def run_simple(
    hostname: str,
    port: int,
    application: Any,
    use_reloader: bool = False,
    use_debugger: bool = False,
    threaded: bool = True,
    ssl_context: Any = None,
    **kwargs: Any,
) -> None:
    """
    Arranca el servidor WSGI de VIGÍA. Si ssl_context está habilitado y threaded=True,
    utiliza NonBlockingTLSThreadedServer para aislar las negociaciones TLS en hilos de trabajo.
    """
    if threaded and ssl_context is not None:
        srv = NonBlockingTLSThreadedServer(
            host=hostname,
            port=port,
            app=application,
            ssl_context=ssl_context,
            **kwargs,
        )
        srv.log_startup()
        srv.serve_forever()
    else:
        _werkzeug_run_simple(
            hostname=hostname,
            port=port,
            application=application,
            use_reloader=use_reloader,
            use_debugger=use_debugger,
            threaded=threaded,
            ssl_context=ssl_context,
            **kwargs,
        )


def run_ingest_server(
    app: Flask,
    host: Optional[str] = None,
    port: int = 8443,
    ssl_cert: Optional[Union[str, Path]] = None,
    ssl_key: Optional[Union[str, Path]] = None,
    validate_host: bool = True,
    auto_discover_wifi: bool = False,
    preferred_interface: Optional[str] = None,
    target_ip: Optional[str] = None,
) -> None:
    """
    Inicia el servidor WSGI de VIGIA_API mediante Werkzeug con soporte nativo de TLS.

    Valida preventivamente la IP de escucha y la coherencia del par de certificados TLS
    antes de abrir sockets o iniciar el bucle del servidor.

    Si ``auto_discover_wifi`` es ``True`` o si ``host`` es ``None``, detecta automáticamente
    la interfaz Wi-Fi activa del PC y su IPv4 utilizable, sin recurrir a Ethernet.
    """
    resolved_if_name: Optional[str] = None
    if auto_discover_wifi or host is None:
        resolved_if_name, host = discover_wifi_ipv4(preferred_interface=preferred_interface)
        logger.info(
            "Selección dinámica de red Wi-Fi: interfaz '%s' con IPv4 %s",
            resolved_if_name,
            host,
        )

    if validate_host and host != "0.0.0.0":
        host = validate_listen_ip(host)

    ssl_context = None
    if ssl_cert:
        cert_target = target_ip or (host if host != "0.0.0.0" else None)
        resolved_cert, resolved_key = resolve_active_tls_pair(
            cert_dir_or_cert_path=ssl_cert,
            key_path=ssl_key,
            target_ip=cert_target,
        )
        ssl_context = (str(resolved_cert), str(resolved_key))

    proto = "https" if ssl_context is not None else "http"
    access_url = f"{proto}://{host}:{port}/mobile"
    if resolved_if_name:
        logger.info(
            "Servidor de ingesta VIGÍA escuchando en %s (interfaz Wi-Fi: %s)",
            access_url,
            resolved_if_name,
        )
    else:
        logger.info("Servidor de ingesta VIGÍA escuchando en %s", access_url)

    run_simple(
        hostname=host,
        port=port,
        application=app,
        ssl_context=ssl_context,
        threaded=True,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    # CFG-01: configuración centralizada en Software/.env (el entorno del proceso prevalece)
    from VIGIA_Core.config.env_loader import (
        MissingConfigurationError,
        load_project_env,
        require_settings,
    )

    load_project_env()
    try:
        require_settings(["POSTGRES_PASSWORD", "VIGIA_CAMERA_KEY"])
    except MissingConfigurationError as cfg_err:
        sys.stderr.write(f"ERROR DE CONFIGURACIÓN VIGÍA: {cfg_err}\n")
        sys.exit(1)

    raw_enable_engine = os.environ.get("VIGIA_ENABLE_VISION_ENGINE", "1").strip().lower()
    enable_engine = raw_enable_engine not in {"0", "false", "no", "off"}

    raw_tls = os.environ.get("VIGIA_ENABLE_TLS", "0").strip().lower()
    enable_tls = raw_tls in {"1", "true", "yes", "on"}

    try:
        dev_app = create_ingest_app(initialize_vision_engine=enable_engine)
    except (TopologyValidationError, DatabaseConnectionError, ModelLoadError, RuntimeError) as init_err:
        sys.stderr.write(
            f"ERROR CRÍTICO DE INICIALIZACIÓN DEL MOTOR DE VISIÓN VIGÍA: {init_err}\n"
        )
        sys.exit(1)

    if enable_tls:
        tls_port = int(os.environ.get("VIGIA_DEV_PORT", "8443"))
        raw_host = os.environ.get("VIGIA_DEV_HOST", "").strip()
        try:
            if raw_host and raw_host != "0.0.0.0":
                listen_ip = validate_private_lan_or_loopback_ip(raw_host)
                if_label = "configurada"
            else:
                if_label, candidate_ip = discover_lan_ipv4(
                    preferred_interface=os.environ.get("VIGIA_WIFI_INTERFACE")
                )
                listen_ip = validate_private_lan_or_loopback_ip(candidate_ip)

            certs_dir = Path(os.environ.get("VIGIA_CERTS_DIR", str(dev_app.config["CERTS_DIR"]))).resolve()
            cert_file = certs_dir / "vigia_cert.pem"
            key_file = certs_dir / "vigia_key.pem"
            regen = os.environ.get("VIGIA_REGENERATE_CERT", "").strip().lower() in {"1", "true", "yes"}

            # Verificar si el certificado activo cuenta con la extensión CDP requerida para CRL (VIGIA-TLS-02D)
            has_cdp = False
            if cert_file.exists():
                try:
                    from cryptography import x509
                    active_leaf = x509.load_pem_x509_certificate(cert_file.read_bytes())
                    active_leaf.extensions.get_extension_for_oid(x509.ExtensionOID.CRL_DISTRIBUTION_POINTS)
                    has_cdp = True
                except Exception:
                    has_cdp = False

            if not cert_file.exists() or not key_file.exists() or not has_cdp or regen:
                if not has_cdp and cert_file.exists():
                    logger.info("Certificado TLS no contiene CDP. Renovando par de servidor preservando Root CA...")
                else:
                    logger.info("Generando par de certificados TLS inicial para %s...", listen_ip)
                generate_vigia_local_ca_bundle(
                    target_ip=listen_ip,
                    cert_dir=certs_dir,
                    overwrite=True,
                )
            else:
                try:
                    resolve_active_tls_pair(cert_file, key_file, target_ip=listen_ip)
                except TLSConfigError as tls_err:
                    logger.warning(
                        "Certificado TLS no válido para la IP actual %s (%s). "
                        "Renovando certificado de servidor preservando la Root CA existente...",
                        listen_ip,
                        tls_err,
                    )
                    generate_vigia_local_ca_bundle(
                        target_ip=listen_ip,
                        cert_dir=certs_dir,
                        overwrite=True,
                    )

            # Iniciar servidor HTTP dedicado para distribución de CRL (RFC 5280)
            crl_port = int(os.environ.get("VIGIA_CRL_HTTP_PORT", str(DEFAULT_CRL_HTTP_PORT)))
            crl_server = None
            try:
                crl_server = start_crl_http_server(
                    certs_dir=certs_dir,
                    host="0.0.0.0",
                    port=crl_port,
                )
            except Exception as crl_err:
                logger.warning("No fue posible iniciar el servidor HTTP CRL en el puerto %d: %s", crl_port, crl_err)

            bind_host = raw_host if (raw_host and raw_host == "0.0.0.0") else listen_ip

            urls_info = resolve_access_urls(port=tls_port, tls_enabled=True, app_config=dev_app.config)
            sys.stdout.write("\n" + "=" * 70 + "\n")
            sys.stdout.write("VIGÍA Vision Systems — Servidor HTTPS LAN Seguro\n")
            sys.stdout.write(f"- Local:            {urls_info['local_url']}\n")
            if urls_info['recommended_lan_url']:
                sys.stdout.write(f"- LAN:              {urls_info['recommended_lan_url']}\n")
                sys.stdout.write(f"- Dashboard local:  {urls_info['local_url']}/app\n")
                sys.stdout.write(f"- Dashboard LAN:    {urls_info['recommended_lan_url']}/app\n")
                sys.stdout.write(f"- Enrolamiento QR:  {urls_info['effective_qr_base_url']}/mobile\n")
                sys.stdout.write(f"- Descarga Root CA: {urls_info['recommended_lan_url']}/api/v1/tls/ca.crt\n")
                sys.stdout.write(f"- Servidor CRL:     http://{listen_ip}:{crl_port}/api/v1/tls/ca.crl\n")
            else:
                sys.stdout.write("- LAN:              No disponible (sin interfaz física activa)\n")
                sys.stdout.write(f"- Dashboard local:  {urls_info['local_url']}/app\n")
                sys.stdout.write("- Enrolamiento QR:  Configure 'VIGIA_PUBLIC_BASE_URL' en Software/.env\n")
                sys.stdout.write(f"- Servidor CRL:     http://127.0.0.1:{crl_port}/api/v1/tls/ca.crl\n")
            sys.stdout.write("=" * 70 + "\n\n")
            sys.stdout.flush()

            try:
                run_ingest_server(
                    app=dev_app,
                    host=bind_host,
                    port=tls_port,
                    ssl_cert=cert_file,
                    ssl_key=key_file,
                    validate_host=True,
                    target_ip=listen_ip,
                )
            finally:
                if crl_server:
                    crl_server.stop()
        except (TLSConfigError, NetworkDiscoveryError, ValueError, FileNotFoundError) as tls_err:
            sys.stderr.write(f"ERROR DE CONFIGURACIÓN TLS / RED LOCAL: {tls_err}\n")
            sys.exit(1)
    else:
        dev_host = os.environ.get("VIGIA_DEV_HOST", "127.0.0.1").strip()
        if dev_host != "0.0.0.0":
            try:
                dev_host = validate_private_lan_or_loopback_ip(dev_host)
            except ValueError as ip_err:
                sys.stderr.write(f"ERROR DE SEGURIDAD DE RED: {ip_err}\n")
                sys.exit(1)
        dev_port = int(os.environ.get("VIGIA_DEV_PORT", "5000"))

        # Banner informativo de direcciones de acceso (VIGIA-NET-01)
        urls_info = resolve_access_urls(port=dev_port, tls_enabled=False)
        sys.stdout.write("\n" + "=" * 70 + "\n")
        sys.stdout.write("VIGÍA Vision Systems — Direcciones de acceso\n")
        sys.stdout.write(f"- Local:           {urls_info['local_url']}\n")
        if urls_info['recommended_lan_url']:
            sys.stdout.write(f"- LAN:             {urls_info['recommended_lan_url']}\n")
            sys.stdout.write(f"- Dashboard local: {urls_info['local_url']}/app\n")
            sys.stdout.write(f"- Dashboard LAN:   {urls_info['recommended_lan_url']}/app\n")
            sys.stdout.write(f"- Enrolamiento QR: {urls_info['effective_qr_base_url']}/mobile\n")
        else:
            sys.stdout.write("- LAN:             No disponible (sin interfaz física activa)\n")
            sys.stdout.write(f"- Dashboard local: {urls_info['local_url']}/app\n")
            sys.stdout.write("- Dashboard LAN:   No disponible\n")
            sys.stdout.write("- Enrolamiento QR: Configure 'VIGIA_PUBLIC_BASE_URL' en Software/.env\n")
        sys.stdout.write("=" * 70 + "\n\n")
        sys.stdout.flush()

        run_simple(
            hostname=dev_host,
            port=dev_port,
            application=dev_app,
            use_reloader=False,
            use_debugger=False,
            threaded=True,
        )


