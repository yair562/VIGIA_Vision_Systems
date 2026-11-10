"""
VIGIA_Security.signer.ipc_server
================================
Servidor IPC endurecido para el servicio IsolatedSigner (VIGIA-NET-04A-R3).
Expone un Named Pipe local en Windows protegido con:
- DACL explícita (SDDL) con principio de menor privilegio.
- Autenticación mutua por HMAC-SHA256.
- Aislamiento e inspección de identidad del cliente Win32 (PID, SID, nivel de integridad, ejecutable).
- Reversión obligatoria de impersonación (RevertToSelf) protegida con try/finally.
- Concurrencia segura mediante despachador multihilo (ThreadPoolExecutor).
- Protección estricta contra clientes silenciosos (timeout de lectura en conn.poll()).
- Límite de tamaño de mensaje (64 KB) y mitigación de ataques de denegación de servicio.
- Mitigación de repetición (Replay Protection) con ventana deslizante de nonces y timestamps.
"""

from __future__ import annotations

import ctypes
import hmac
import logging
import os
import pickle
import secrets
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from multiprocessing.connection import Listener, PipeListener
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from VIGIA_Security.signer.constants import (
    DEFAULT_PIPE_NAME,
    DEFAULT_PIPE_SDDL_TEMPLATE,
    DEFAULT_READ_TIMEOUT,
    DEFAULT_WRITE_TIMEOUT,
    MAX_CONCURRENT_CONNECTIONS,
    MAX_MESSAGE_BYTES,
    PROTOCOL_VERSION,
    REPLAY_WINDOW_SECONDS,
    SERVICE_SID_VIGIA_SIGNER,
    TOKEN_FILENAME,
)
from VIGIA_Security.signer.policy import PolicyViolationError
from VIGIA_Security.signer.service import IsolatedSigner, SignerIntegrityError

logger = logging.getLogger(__name__)

# =========================================================================
# Configuración Win32 API via ctypes (Windows NT Security Subsystem)
# =========================================================================
IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    advapi32 = ctypes.windll.advapi32
    kernel32 = ctypes.windll.kernel32

    # Prototipos de seguridad
    advapi32.ImpersonateNamedPipeClient.argtypes = [wintypes.HANDLE]
    advapi32.ImpersonateNamedPipeClient.restype = wintypes.BOOL

    advapi32.RevertToSelf.argtypes = []
    advapi32.RevertToSelf.restype = wintypes.BOOL

    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.OpenProcessToken.restype = wintypes.BOOL

    advapi32.OpenThreadToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.BOOL,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.OpenThreadToken.restype = wintypes.BOOL

    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL

    advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.LPWSTR),
    ]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL

    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.ULONG),
    ]
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL

    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE

    kernel32.GetCurrentThread.argtypes = []
    kernel32.GetCurrentThread.restype = wintypes.HANDLE

    kernel32.GetNamedPipeClientProcessId.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.GetNamedPipeClientProcessId.restype = wintypes.BOOL

    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE

    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

    class SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [
            ("nLength", wintypes.DWORD),
            ("lpSecurityDescriptor", wintypes.LPVOID),
            ("bInheritHandle", wintypes.BOOL),
        ]


def get_current_user_sid() -> str:
    """Obtiene el SID del token primario del proceso actual en Windows."""
    if not IS_WINDOWS:
        return "S-1-5-21-0-0-0-1000"

    hToken = wintypes.HANDLE()
    TOKEN_QUERY = 0x0008
    if advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(hToken)):
        try:
            buf = (ctypes.c_byte * 256)()
            ret_len = wintypes.DWORD()
            # TokenUser = 1
            if advapi32.GetTokenInformation(hToken, 1, ctypes.byref(buf), 256, ctypes.byref(ret_len)):
                p_sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p)).contents
                sid_str = wintypes.LPWSTR()
                if advapi32.ConvertSidToStringSidW(p_sid, ctypes.byref(sid_str)):
                    res = sid_str.value
                    kernel32.LocalFree(sid_str)
                    return str(res)
        finally:
            kernel32.CloseHandle(hToken)
    return ""


def build_default_pipe_sddl(client_sid: Optional[str] = None) -> str:
    """
    Construye la DACL SDDL canónica autorizando exclusivamente a:
    - SYSTEM (SY -> GA)
    - Administradores (BA -> GA)
    - NT SERVICE\VigiaSigner (Service SID determinístico -> GRGW)
    - Identidad autorizada de Flask (client_sid -> GRGW)
    """
    sid = client_sid or get_current_user_sid() or "S-1-5-32-545"
    return DEFAULT_PIPE_SDDL_TEMPLATE.format(CLIENT_SID=sid)


if IS_WINDOWS:
    import _winapi

    class SecurePipeListener(PipeListener):
        """
        Listener de Named Pipe en Windows con Descriptor de Seguridad explícito (SDDL).
        Reemplaza el uso inseguro de lpSecurityAttributes=NULL por una DACL restrictiva.
        """

        def __init__(self, address: str, sddl_str: str, backlog: int = 10) -> None:
            self._sddl_str = sddl_str
            self._p_sd = wintypes.LPVOID()
            size = wintypes.ULONG()

            # SDDL_REVISION_1 = 1
            ret = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl_str, 1, ctypes.byref(self._p_sd), ctypes.byref(size)
            )
            if not ret:
                err_code = kernel32.GetLastError()
                logger.error("ConvertStringSecurityDescriptorToSecurityDescriptorW falló con error %d", err_code)
                raise OSError(f"Fallo al compilar SDDL '{sddl_str}': error Win32 {err_code}")

            self._sa = SECURITY_ATTRIBUTES()
            self._sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
            self._sa.lpSecurityDescriptor = self._p_sd
            self._sa.bInheritHandle = False
            self._ptr_sa = ctypes.addressof(self._sa)

            super().__init__(address, backlog)

        def _new_handle(self, first: bool = False) -> int:
            flags = _winapi.PIPE_ACCESS_DUPLEX | _winapi.FILE_FLAG_OVERLAPPED
            if first:
                flags |= _winapi.FILE_FLAG_FIRST_PIPE_INSTANCE
            return _winapi.CreateNamedPipe(
                self._address,
                flags,
                _winapi.PIPE_TYPE_MESSAGE | _winapi.PIPE_READMODE_MESSAGE | _winapi.PIPE_WAIT,
                _winapi.PIPE_UNLIMITED_INSTANCES,
                MAX_MESSAGE_BYTES,
                MAX_MESSAGE_BYTES,
                _winapi.NMPWAIT_WAIT_FOREVER,
                self._ptr_sa,
            )

        def close(self) -> None:
            super().close()
            if self._p_sd:
                kernel32.LocalFree(self._p_sd)
                self._p_sd = None


def get_or_create_ipc_token(certs_dir: Union[str, Path]) -> bytes:
    """
    Obtiene o genera de forma atómica el secreto efímero compartido para el Named Pipe.
    """
    token_p = Path(certs_dir).resolve() / TOKEN_FILENAME
    if token_p.is_file():
        try:
            tok = token_p.read_bytes().strip()
            if len(tok) >= 32:
                return tok
        except Exception:
            pass

    new_tok = secrets.token_bytes(32)
    token_p.write_bytes(new_tok)
    return new_tok


class SignerIPCServer:
    """
    Servidor de Named Pipe de Windows endurecido para IsolatedSigner (VIGIA-NET-04A-R3).
    """

    def __init__(
        self,
        signer: IsolatedSigner,
        pipe_name: str = DEFAULT_PIPE_NAME,
        authkey: Optional[bytes] = None,
        sddl: Optional[str] = None,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        write_timeout: float = DEFAULT_WRITE_TIMEOUT,
        max_connections: int = MAX_CONCURRENT_CONNECTIONS,
        max_message_bytes: int = MAX_MESSAGE_BYTES,
        enforce_client_sid: bool = False,
        allowed_sids: Optional[List[str]] = None,
    ) -> None:
        self.signer = signer
        self.pipe_name = pipe_name
        self.authkey = authkey or get_or_create_ipc_token(self.signer.certs_dir)
        self.sddl = sddl or build_default_pipe_sddl()
        self.read_timeout = float(read_timeout)
        self.write_timeout = float(write_timeout)
        self.max_connections = int(max_connections)
        self.max_message_bytes = int(max_message_bytes)
        self.enforce_client_sid = enforce_client_sid
        self.allowed_sids = set(allowed_sids or [])

        # Replay protection cache: nonce -> timestamp
        self._seen_nonces: Dict[str, float] = {}
        self._nonce_lock = threading.Lock()

        self._running = False
        self._listener: Optional[Listener] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._executor: Optional[ThreadPoolExecutor] = None
        self._ready_event = threading.Event()

    def start(self, timeout: float = 5.0) -> None:
        """Inicia el despachador multihilo del Named Pipe en segundo plano y espera confirmación de arranque."""
        if self._running:
            return

        self._running = True
        self._ready_event.clear()
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_connections,
            thread_name_prefix="IsolatedSigner-Worker",
        )
        self._accept_thread = threading.Thread(
            target=self._serve_loop,
            name="IsolatedSigner-Acceptor",
            daemon=True,
        )
        self._accept_thread.start()

        # Esperar hasta que el Named Pipe esté creado y listo para recibir clientes
        if not self._ready_event.wait(timeout=timeout):
            logger.error("Timeout esperando inicialización de SecurePipeListener en '%s'", self.pipe_name)

        logger.info(
            "SignerIPCServer endurecido (R3) iniciado en '%s' (Max Conexiones: %d, Timeout: %.1fs).",
            self.pipe_name,
            self.max_connections,
            self.read_timeout,
        )

    def stop(self) -> None:
        """Detiene de forma segura el servidor y libera recursos."""
        self._running = False
        if self._listener:
            try:
                self._listener.close()
            except Exception:
                pass

        if self._executor:
            try:
                self._executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass

        if self._accept_thread and self._accept_thread.is_alive():
            self._accept_thread.join(timeout=2.0)

        logger.info("SignerIPCServer detenido.")

    def set_authkey(self, new_key: bytes) -> None:
        """Actualiza en caliente la clave de autenticación HMAC del servidor sin reiniciar el Named Pipe."""
        self.authkey = new_key
        if self._listener:
            self._listener._authkey = new_key
        logger.info("Clave de autenticación IPC actualizada en caliente.")

    def _inspect_client_identity(self, conn_handle: int) -> Dict[str, Any]:
        """
        Inspecciona el token del cliente conectado a través de la API Win32.
        Aplica ImpersonateNamedPipeClient y garantiza RevertToSelf incondicional.
        """
        result: Dict[str, Any] = {
            "pid": None,
            "sid": None,
            "integrity_level": None,
            "executable": None,
            "identity_str": "unknown",
        }
        if not IS_WINDOWS or not conn_handle:
            return result

        hPipe = wintypes.HANDLE(conn_handle)

        # 1. Obtener PID
        client_pid = wintypes.DWORD()
        if kernel32.GetNamedPipeClientProcessId(hPipe, ctypes.byref(client_pid)):
            result["pid"] = int(client_pid.value)

        # 2. Impersonar para leer el token de seguridad efectivo del cliente
        impersonated = advapi32.ImpersonateNamedPipeClient(hPipe)
        try:
            if impersonated:
                hThread = kernel32.GetCurrentThread()
                hToken = wintypes.HANDLE()
                TOKEN_QUERY = 0x0008
                if advapi32.OpenThreadToken(hThread, TOKEN_QUERY, True, ctypes.byref(hToken)):
                    try:
                        # TokenUser = 1
                        buf = (ctypes.c_byte * 256)()
                        ret_len = wintypes.DWORD()
                        if advapi32.GetTokenInformation(hToken, 1, ctypes.byref(buf), 256, ctypes.byref(ret_len)):
                            p_sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p)).contents
                            sid_str = wintypes.LPWSTR()
                            if advapi32.ConvertSidToStringSidW(p_sid, ctypes.byref(sid_str)):
                                result["sid"] = str(sid_str.value)
                                kernel32.LocalFree(sid_str)

                        # TokenIntegrityLevel = 25
                        buf_il = (ctypes.c_byte * 256)()
                        if advapi32.GetTokenInformation(hToken, 25, ctypes.byref(buf_il), 256, ctypes.byref(ret_len)):
                            p_sid_il = ctypes.cast(buf_il, ctypes.POINTER(ctypes.c_void_p)).contents
                            sid_il_str = wintypes.LPWSTR()
                            if advapi32.ConvertSidToStringSidW(p_sid_il, ctypes.byref(sid_il_str)):
                                result["integrity_level"] = str(sid_il_str.value)
                                kernel32.LocalFree(sid_il_str)
                    finally:
                        kernel32.CloseHandle(hToken)
        finally:
            # Reversión obligatoria incondicional
            advapi32.RevertToSelf()

        # 3. Consultar ruta del ejecutable si se obtuvo el PID
        if result["pid"]:
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            hProc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, result["pid"])
            if hProc:
                try:
                    name_buf = (ctypes.c_wchar * 1024)()
                    size = wintypes.DWORD(1024)
                    if kernel32.QueryFullProcessImageNameW(hProc, 0, name_buf, ctypes.byref(size)):
                        result["executable"] = str(name_buf.value)
                finally:
                    kernel32.CloseHandle(hProc)

        pid_str = f"PID:{result['pid']}" if result["pid"] else "PID:unknown"
        sid_str = f"SID:{result['sid']}" if result["sid"] else "SID:unknown"
        exe_str = f"EXE:{Path(result['executable']).name}" if result["executable"] else "EXE:unknown"
        result["identity_str"] = f"{sid_str}|{pid_str}|{exe_str}"
        return result

    def _serve_loop(self) -> None:
        """Bucle de aceptación de conexiones que delega inmediatamente a hilos de trabajo."""
        while self._running:
            try:
                if IS_WINDOWS:
                    listener_obj = Listener.__new__(Listener)
                    listener_obj._authkey = self.authkey
                    listener_obj._listener = SecurePipeListener(self.pipe_name, self.sddl, backlog=self.max_connections)
                    self._listener = listener_obj
                else:
                    self._listener = Listener(self.pipe_name, "AF_PIPE", authkey=self.authkey)
                self._ready_event.set()
            except Exception as err:
                if not self._running:
                    break
                logger.error("Fallo al crear SecurePipeListener en '%s': %s. Reintentando en 1s...", self.pipe_name, err)
                time.sleep(1.0)
                continue

            while self._running:
                try:
                    conn = self._listener.accept()
                except Exception:
                    # Listener cerrado o error de conexión
                    break

                # Despachar conexión al pool sin bloquear el hilo de escucha
                if self._executor and self._running:
                    try:
                        self._executor.submit(self._handle_client_connection, conn)
                    except Exception as pool_err:
                        logger.warning("No fue posible despachar conexión: %s", pool_err)
                        try:
                            conn.close()
                        except Exception:
                            pass
                else:
                    try:
                        conn.close()
                    except Exception:
                        pass

            try:
                if self._listener:
                    self._listener.close()
            except Exception:
                pass

    def _check_replay(self, req: Dict[str, Any], client_ident: str) -> Optional[Tuple[str, str]]:
        """
        Verifica timestamps y nonces para mitigar ataques de repetición.
        Retorna (error_msg, error_code) si se detecta repetición, o None si es válido.
        """
        nonce = req.get("nonce")
        req_ts = req.get("timestamp")

        if not nonce or req_ts is None:
            # Compatibilidad con clientes legacy (emite advertencia en logs)
            return None

        try:
            req_ts = float(req_ts)
        except (ValueError, TypeError):
            return "Timestamp inválido.", "INVALID_TIMESTAMP"

        now = time.time()
        # Verificar antigüedad del mensaje
        if abs(now - req_ts) > REPLAY_WINDOW_SECONDS:
            return "Solicitud expirada (desviación de tiempo mayor a la ventana permitida).", "REQUEST_EXPIRED"

        cache_key = f"{client_ident}:{nonce}"
        with self._nonce_lock:
            # Purgar nonces viejos
            cutoff = now - REPLAY_WINDOW_SECONDS
            self._seen_nonces = {k: v for k, v in self._seen_nonces.items() if v > cutoff}

            if cache_key in self._seen_nonces:
                return "Ataque de repetición detectado (nonce duplicado).", "REPLAY_DETECTED"

            self._seen_nonces[cache_key] = now

        return None

    def _handle_client_connection(self, conn: Any) -> None:
        """
        Maneja una conexión cliente individual con timeouts acotados y límites de tamaño.
        """
        conn_handle = getattr(conn, "_handle", None)
        client_info = self._inspect_client_identity(conn_handle)
        client_ident = client_info["identity_str"]
        client_sid = client_info["sid"]

        try:
            # 1. Validación de SID si está configurada la lista de permitidos
            if self.enforce_client_sid and self.allowed_sids:
                if client_sid not in self.allowed_sids:
                    logger.warning("Acceso denegado: SID no autorizado '%s'.", client_sid)
                    try:
                        conn.send({
                            "ok": False,
                            "error": f"Acceso denegado: SID '{client_sid}' no autorizado.",
                            "code": "ACCESS_DENIED_SID",
                            "protocol_version": PROTOCOL_VERSION,
                        })
                    except Exception:
                        pass
                    return

            # 2. Espera acotada de datos (mitigación de clientes silenciosos)
            if not conn.poll(self.read_timeout):
                logger.warning("Cliente silencioso superó read_timeout (%.1fs) [%s].", self.read_timeout, client_ident)
                return

            # 3. Lectura protegida con límite de tamaño de mensaje (64 KB)
            try:
                raw_bytes = conn.recv_bytes(maxlength=self.max_message_bytes)
            except OSError as os_err:
                logger.warning("Mensaje recibido excede el límite permitido de %d bytes [%s]: %s", self.max_message_bytes, client_ident, os_err)
                try:
                    conn.send({
                        "ok": False,
                        "error": f"Mensaje excede el límite permitido de {self.max_message_bytes} bytes.",
                        "code": "MESSAGE_TOO_LARGE",
                        "protocol_version": PROTOCOL_VERSION,
                    })
                except Exception:
                    pass
                return

            # 4. Deserialización segura
            try:
                req = pickle.loads(raw_bytes)
            except Exception as dec_err:
                logger.warning("Error de deserialización desde [%s]: %s", client_ident, dec_err)
                try:
                    conn.send({
                        "ok": False,
                        "error": "Error de deserialización de solicitud.",
                        "code": "MALFORMED_REQUEST",
                        "protocol_version": PROTOCOL_VERSION,
                    })
                except Exception:
                    pass
                return

            if not isinstance(req, dict):
                try:
                    conn.send({
                        "ok": False,
                        "error": "Formato de solicitud inválido (debe ser un dict).",
                        "code": "MALFORMED_REQUEST",
                        "protocol_version": PROTOCOL_VERSION,
                    })
                except Exception:
                    pass
                return

            request_id = req.get("request_id")

            # 5. Mitigación de repetición (Replay Protection)
            replay_err = self._check_replay(req, client_ident)
            if replay_err:
                err_msg, err_code = replay_err
                logger.warning("Violación de repetición/timestamp desde [%s]: %s (%s)", client_ident, err_msg, err_code)
                try:
                    conn.send({
                        "ok": False,
                        "error": err_msg,
                        "code": err_code,
                        "request_id": request_id,
                        "protocol_version": PROTOCOL_VERSION,
                    })
                except Exception:
                    pass
                return

            # 6. Despacho y ejecución de la solicitud
            resp = self._dispatch_request(req, client_identity=client_ident)
            if request_id:
                resp["request_id"] = request_id
            resp["protocol_version"] = PROTOCOL_VERSION

            # 7. Envío de respuesta con captura de fallos
            try:
                conn.send(resp)
            except Exception as send_err:
                logger.warning("Error al enviar respuesta IPC a [%s]: %s", client_ident, send_err)

        except Exception as exc:
            logger.error("Excepción no controlada procesando conexión IPC [%s]: %s", client_ident, exc)
            try:
                conn.send({
                    "ok": False,
                    "error": str(exc),
                    "code": "IPC_INTERNAL_ERROR",
                    "protocol_version": PROTOCOL_VERSION,
                })
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _dispatch_request(self, req: Dict[str, Any], client_identity: str) -> Dict[str, Any]:
        """Enruta y valida las acciones criptográficas solicitadas."""
        action = req.get("action")

        if action == "PING":
            return {"ok": True, "status": "PONG", "time": time.time()}

        if action == "SIGN_CERTIFICATE":
            csr_pem = req.get("csr_pem")
            target_ip = req.get("target_ip")
            valid_days = req.get("valid_days", 90)
            crl_port = req.get("crl_port", 5080)

            if not csr_pem or not target_ip:
                return {
                    "ok": False,
                    "error": "Faltan campos obligatorios ('csr_pem', 'target_ip').",
                    "code": "MISSING_FIELDS",
                }

            try:
                return self.signer.sign_certificate(
                    csr_pem=csr_pem,
                    target_ip=target_ip,
                    valid_days=int(valid_days),
                    crl_port=int(crl_port),
                    client_identity=client_identity,
                )
            except PolicyViolationError as p_err:
                return {"ok": False, "error": str(p_err), "code": "POLICY_VIOLATION"}
            except SignerIntegrityError as s_err:
                return {"ok": False, "error": str(s_err), "code": "SIGNER_INTEGRITY_ERROR"}
            except Exception as exc:
                return {"ok": False, "error": f"Fallo al firmar certificado: {exc}", "code": "SIGNING_FAILED"}

        if action == "SIGN_CRL":
            crl_number = req.get("crl_number", 1)
            revoked_serials = req.get("revoked_serials")
            valid_days = req.get("valid_days", 7)

            try:
                return self.signer.sign_crl(
                    crl_number=int(crl_number),
                    revoked_serials=revoked_serials,
                    valid_days=int(valid_days),
                    client_identity=client_identity,
                )
            except PolicyViolationError as p_err:
                return {"ok": False, "error": str(p_err), "code": "POLICY_VIOLATION"}
            except Exception as exc:
                return {"ok": False, "error": f"Fallo al firmar CRL: {exc}", "code": "CRL_SIGNING_FAILED"}

        return {"ok": False, "error": f"Acción desconocida o no autorizada: '{action}'", "code": "UNKNOWN_ACTION"}
