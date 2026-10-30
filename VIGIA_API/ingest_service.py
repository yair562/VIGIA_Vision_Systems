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
import hmac
import ipaddress
import json
import logging
import os
import shutil
import socket
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple, Union

import cv2
import numpy as np
from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.serving import run_simple

from VIGIA_API.security.auth_service import AuthService
from VIGIA_API.security.session_manager import SessionManager, UserSession
from VIGIA_Core.domain.user import UserDTO
from VIGIA_Core.repository.user_repository import IUserRepository, InMemoryUserRepository
from VIGIA_Core.security.password_hasher import hash_password
from VIGIA_Vision.capture.registry import UnregisteredCameraError
from VIGIA_Vision.capture.sources import MobilePushFrameBuffer
from VIGIA_Vision.detection.roi_and_preprocess import (
    FrameValidationError,
    validate_bgr_frame,
)
from VIGIA_Vision.runtime.coordinator import VisionEngineCoordinator

logger = logging.getLogger(__name__)

# Límites operativos canónicos de seguridad
DEFAULT_MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MiB
DEFAULT_MAX_WIDTH = 3840                     # 4K UHD horizontal
DEFAULT_MAX_HEIGHT = 2160                    # 4K UHD vertical

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
    "js/components/admin-navbar.js",
    "js/components/devices-table.js",
    "js/views/login-view.js",
    "js/views/devices-view.js",
}


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
        Repositorio de usuarios para autenticación y RBAC.
    session_manager : Optional[SessionManager]
        Gestor de sesiones activas del servidor.
    auth_service : Optional[AuthService]
        Servicio de autenticación para verificación Argon2id y emisión de sesiones.

    Retorna
    -------
    Flask
        Instancia configurada de la aplicación WSGI.
    """
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = max_content_length
    app.config["COORDINATOR"] = coordinator
    
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

    # Configuración de Autenticación y Sesiones RBAC (ENR-02A)
    resolved_session_mgr = session_manager or SessionManager()
    resolved_user_repo = user_repository or InMemoryUserRepository()
    resolved_auth_svc = auth_service or AuthService(
        user_repository=resolved_user_repo,
        session_manager=resolved_session_mgr,
    )
    app.config["SESSION_MANAGER"] = resolved_session_mgr
    app.config["USER_REPOSITORY"] = resolved_user_repo
    app.config["AUTH_SERVICE"] = resolved_auth_svc

    # Ruta a la interfaz móvil y al Dashboard web en VIGIA_Dashboard
    repo_root = Path(__file__).resolve().parent.parent
    default_html = repo_root / "VIGIA_Dashboard" / "mobile" / "index.html"
    html_target = Path(mobile_html_path) if mobile_html_path else default_html
    app.config["MOBILE_HTML_PATH"] = html_target
    app.config["DASHBOARD_WEB_DIR"] = (repo_root / "VIGIA_Dashboard" / "web").resolve()
    app.config["BRAND_SVG_DIR"] = (
        repo_root / "Docs" / "GEST_PROY_SOFT" / "02_Logos_accesibilidad" / "svg"
    ).resolve()

    # Lock para serializar atómicamente push_frame + process_camera_step
    process_lock = threading.RLock()

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

    @app.after_request
    def apply_security_headers(response):  # type: ignore
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        origin = request.headers.get("Origin")
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, DELETE"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Camera-Key, Authorization, X-Session-Token"
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
        auth_hdr = request.headers.get("Authorization", "")
        if auth_hdr.startswith("Bearer "):
            tok = auth_hdr[7:].strip()
            if tok:
                return tok
        x_tok = request.headers.get("X-Session-Token", "").strip()
        if x_tok:
            return x_tok
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

        response = jsonify(
            {
                "ok": True,
                "token": sess.token,
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
            secure=request.is_secure,
        )
        return response, 200

    @app.route("/api/v1/auth/logout", methods=["POST"])
    def auth_logout():
        """
        Revoca inmediatamente la sesión activa actual en el servidor.
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
        response.delete_cookie("vigia_session")
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

    @app.route("/api/v1/cameras/<codigo_camara>/push", methods=["POST", "OPTIONS"])
    def push_camera_frame(codigo_camara: str):  # type: ignore
        """
        Recibe un fotograma capturado por un dispositivo móvil para la cámara indicada.
        """
        if request.method == "OPTIONS":
            return "", 204

        # 1. Validación de Autorización Obligatoria (Fail-Closed)
        configured_token: Optional[str] = app.config.get("AUTH_TOKEN")
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

        provided_key = request.headers.get("X-Camera-Key") or request.headers.get("X-API-Key")
        if not provided_key:
            auth_hdr = request.headers.get("Authorization", "")
            if auth_hdr.startswith("Bearer "):
                provided_key = auth_hdr[7:].strip()

        if not provided_key or not hmac.compare_digest(provided_key, configured_token):
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

        # 7 y 8. Entrega e Inferencia Atómica Protegida por Bloqueo
        # Garantiza que ninguna otra solicitud concurrente pueda sobrescribir el buffer
        # antes de que esta solicitud complete su ciclo de procesamiento.
        with process_lock:
            if not slot.source.is_opened():
                slot.source.open()

            seq = slot.source.push_frame(frame_bgr)

            try:
                envelope = engine_coordinator.process_camera_step(
                    codigo_camara,
                    persist_as_new_event=False,
                )
            except Exception as proc_err:
                logger.error("Error durante process_camera_step: %s", proc_err, exc_info=True)
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": "PROCESSING_ERROR",
                            "message": "Fallo durante la inferencia y procesamiento del fotograma.",
                        }
                    ),
                    500,
                )

        # 9. Respuesta estructurada al dispositivo móvil
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
                }
            )

        vr = envelope.vision_result
        return jsonify(
            {
                "ok": True,
                "codigo_camara": codigo_camara,
                "frame_sequence": envelope.frame_sequence or seq,
                "status": vr.status.value,
                "vehicle_detected": vr.vehicle_detected,
                "tipo_vehiculo": vr.vehicle_type_pred,
                "confianza": vr.vehicle_confidence,
                "detections_count": len(envelope.detections_in_roi),
                "in_roi_now": envelope.metrics.in_roi_now,
                "total_detected_in_frame": envelope.metrics.total_detected_in_frame,
                "timestamp": vr.timestamp.isoformat() if vr.timestamp else None,
            }
        )

    return app


class TLSConfigError(ValueError):
    """Excepción para errores de configuración, formato o coherencia de certificados TLS."""


class NetworkDiscoveryError(Exception):
    """Excepción para errores en la identificación o resolución de interfaces de red."""


def is_usable_ipv4(ip_str: str) -> bool:
    """
    Verifica si una cadena es una IPv4 utilizable para comunicación de red local.
    Excluye loopback (127.0.0.0/8), APIPA/link-local (169.254.0.0/16), 0.0.0.0 y multicast.
    """
    if not ip_str or not isinstance(ip_str, str):
        return False
    try:
        ip_obj = ipaddress.IPv4Address(ip_str.strip())
        return not (
            ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_unspecified
            or ip_obj.is_multicast
        )
    except (ipaddress.AddressValueError, ValueError):
        return False


def get_windows_wlan_interfaces() -> Dict[str, str]:
    """
    Consulta las interfaces inalámbricas 802.11 registradas en Windows mediante netsh wlan.
    Retorna un diccionario {nombre_interfaz: estado} (ej. {'Wi-Fi': 'connected'}).
    """
    try:
        res = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        if res.returncode != 0:
            return {}
        interfaces: Dict[str, str] = {}
        current_name: Optional[str] = None
        for line in res.stdout.splitlines():
            line_str = line.strip()
            if line_str.startswith("Name") or line_str.startswith("Nombre"):
                parts = line_str.split(":", 1)
                if len(parts) == 2:
                    current_name = parts[1].strip()
            elif line_str.startswith("State") or line_str.startswith("Estado"):
                parts = line_str.split(":", 1)
                if len(parts) == 2 and current_name:
                    interfaces[current_name] = parts[1].strip().lower()
        return interfaces
    except Exception as exc:
        logger.debug("Error al ejecutar netsh wlan show interfaces: %s", exc)
        return {}


def discover_wifi_ipv4(preferred_interface: Optional[str] = None) -> Tuple[str, str]:
    """
    Identifica de manera fiable la interfaz Wi-Fi física activa y su dirección IPv4 utilizable en Windows.

    Excluye:
    - Direcciones de loopback (127.0.0.0/8).
    - Direcciones APIPA / link-local (169.254.0.0/16).
    - Direcciones no asignadas o 0.0.0.0.
    - Adaptadores Ethernet, virtuales (WSL, VMware, VirtualBox), VPN o Bluetooth.

    Reglas estrictas:
    - No sustituye automáticamente por Ethernet si no hay Wi-Fi utilizable.
    - Si existen múltiples interfaces Wi-Fi con IPv4 válida y no se indica una preferida,
      detiene el arranque solicitando selección explícita.
    - Si la Wi-Fi está desconectada o no tiene IPv4 utilizable, lanza NetworkDiscoveryError.

    Retorna
    -------
    Tuple[str, str]
        (nombre_interfaz, direccion_ipv4)
    """
    import psutil

    # 1. Resolver interfaz preferida (argumento o variable de entorno)
    target_pref = preferred_interface or os.environ.get("VIGIA_WIFI_INTERFACE")
    if target_pref:
        target_pref = target_pref.strip()

    # 2. Consultar interfaces de red mediante psutil
    all_addrs = psutil.net_if_addrs()
    all_stats = psutil.net_if_stats()

    # 3. Consultar interfaces registradas en Windows WLAN Service
    wlan_states = get_windows_wlan_interfaces()

    # 4. Identificar adaptadores candidatos que sean genuinamente Wi-Fi
    wifi_candidates: Dict[str, str] = {}

    for if_name, addr_list in all_addrs.items():
        lower_name = if_name.lower()

        # Filtrar exclusiones de adaptadores que NO son Wi-Fi
        if any(
            exc in lower_name
            for exc in [
                "ethernet",
                "vethernet",
                "vmware",
                "virtualbox",
                "bluetooth",
                "loopback",
                "pseudo",
                "tap",
                "tun",
                "vpn",
            ]
        ):
            continue

        # Debe ser reconocida por netsh wlan o tener patrón de nombre Wi-Fi
        is_wlan = if_name in wlan_states or any(
            pattern in lower_name
            for pattern in ["wi-fi", "wifi", "wlan", "wireless", "inalámbric"]
        )
        if not is_wlan:
            continue

        # Comprobar si la interfaz está activa/conectada
        st = all_stats.get(if_name)
        is_up = st.isup if st else False
        netsh_state = wlan_states.get(if_name, "")
        if netsh_state in ["disconnected", "desconectado"]:
            is_up = False

        if not is_up:
            continue

        # Buscar dirección IPv4 utilizable
        for addr in addr_list:
            if getattr(addr.family, "name", "") == "AF_INET" or addr.family == socket.AF_INET:
                if is_usable_ipv4(addr.address):
                    wifi_candidates[if_name] = addr.address
                    break

    # 5. Aplicar reglas de resolución
    if target_pref:
        if target_pref in wifi_candidates:
            return target_pref, wifi_candidates[target_pref]
        raise NetworkDiscoveryError(
            f"La interfaz Wi-Fi preferida '{target_pref}' no está disponible, conectada o no "
            f"posee una dirección IPv4 utilizable. Interfaces Wi-Fi detectadas: {list(wifi_candidates.keys())}."
        )

    if not wifi_candidates:
        raise NetworkDiscoveryError(
            "No se encontró ninguna interfaz Wi-Fi activa con dirección IPv4 utilizable. "
            "Asegúrese de que el adaptador Wi-Fi esté encendido y conectado a la red local. "
            "Por política de seguridad no se permite la sustitución automática por Ethernet."
        )

    if len(wifi_candidates) > 1:
        candidates_str = ", ".join(f"'{k}' ({v})" for k, v in wifi_candidates.items())
        raise NetworkDiscoveryError(
            f"Se detectaron múltiples interfaces Wi-Fi candidatas con IPv4 activa: {candidates_str}. "
            "Detención de seguridad: especifique la interfaz requerida mediante el parámetro "
            "'preferred_interface' o la variable de entorno 'VIGIA_WIFI_INTERFACE'."
        )

    selected_name, selected_ip = next(iter(wifi_candidates.items()))
    return selected_name, selected_ip


def get_local_ipv4_addresses() -> Set[str]:
    """
    Retorna el conjunto de direcciones IPv4 locales asignadas a interfaces de red activas.
    Incluye siempre '127.0.0.1' (loopback local).
    Combina la API de adaptadores del sistema (psutil/IP Helper) con la resolución de host.
    """
    addresses: Set[str] = {"127.0.0.1"}
    # 1. Consultar adaptadores mediante psutil (IP Helper API de Windows)
    try:
        import psutil
        for if_name, addr_list in psutil.net_if_addrs().items():
            for addr in addr_list:
                if getattr(addr.family, "name", "") == "AF_INET" or addr.family == socket.AF_INET:
                    if addr.address:
                        addresses.add(addr.address)
    except Exception as exc:
        logger.debug("Error al consultar adaptadores mediante psutil: %s", exc)

    # 2. Complementar con socket.getaddrinfo para resolución de nombres locales
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, family=socket.AF_INET):
            ip_val = info[4][0]
            if ip_val:
                addresses.add(ip_val)
    except Exception as exc:
        logger.debug("Error al consultar adaptadores locales mediante getaddrinfo: %s", exc)

    return addresses


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
    from cryptography.x509.oid import NameOID

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
            san_entries.append(x509.IPAddress(parsed_ip))
        except ValueError:
            san_entries.append(x509.DNSName(target_ip.strip()))

        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=valid_days))
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


def run_ingest_server(
    app: Flask,
    host: Optional[str] = None,
    port: int = 8443,
    ssl_cert: Optional[Union[str, Path]] = None,
    ssl_key: Optional[Union[str, Path]] = None,
    validate_host: bool = True,
    auto_discover_wifi: bool = False,
    preferred_interface: Optional[str] = None,
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

    if validate_host:
        host = validate_listen_ip(host)

    ssl_context = None
    if ssl_cert:
        resolved_cert, resolved_key = resolve_active_tls_pair(
            cert_dir_or_cert_path=ssl_cert,
            key_path=ssl_key,
            target_ip=host,
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
    dev_host = os.environ.get("VIGIA_DEV_HOST", "0.0.0.0")
    dev_port = int(os.environ.get("VIGIA_DEV_PORT", "5000"))
    dev_app = create_ingest_app()
    run_simple(
        hostname=dev_host,
        port=dev_port,
        application=dev_app,
        use_reloader=False,
        use_debugger=False,
        threaded=True,
    )

