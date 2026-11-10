"""
VIGIA_Security.signer.ipc_client
================================
Cliente IPC para que el proceso Flask/WSGI solicite firmas criptográficas
al servicio IsolatedSigner a través del Named Pipe autenticado (VIGIA-NET-04A-R3).
Implementa contrato versionado, nonces anti-repetición y recarga perezosa de secretos.
"""

from __future__ import annotations

import logging
import secrets
import time
import uuid
from multiprocessing.connection import Client, wait
from multiprocessing.context import AuthenticationError
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from VIGIA_Security.signer.constants import (
    DEFAULT_CRL_PORT,
    DEFAULT_PIPE_NAME,
    DEFAULT_VALID_DAYS,
    PROTOCOL_VERSION,
    TOKEN_FILENAME,
)
from VIGIA_Security.signer.policy import PolicyViolationError

logger = logging.getLogger(__name__)


class SignerUnavailableError(RuntimeError):
    """Lanzada cuando el servicio IsolatedSigner no está en ejecución o no responde."""
    pass


class SignerAuthenticationError(SignerUnavailableError):
    """Lanzada cuando la autenticación mutua HMAC sobre el Named Pipe falla."""
    pass


class SignerTimeoutError(SignerUnavailableError):
    """Lanzada cuando la conexión o respuesta del Named Pipe excede el timeout."""
    pass


class SignerClient:
    """Cliente para interactuar con el IsolatedSigner mediante Named Pipe en Windows."""

    def __init__(
        self,
        certs_dir: Optional[Union[str, Path]] = None,
        pipe_name: str = DEFAULT_PIPE_NAME,
        authkey: Optional[bytes] = None,
        timeout: float = 5.0,
    ) -> None:
        if certs_dir is not None:
            self.certs_dir = Path(certs_dir).resolve()
        else:
            self.certs_dir = Path(__file__).resolve().parents[2] / "certs"

        self.pipe_name = pipe_name
        self.timeout = float(timeout)
        self._custom_authkey = authkey is not None

        if authkey is not None:
            self.authkey = authkey
        else:
            self.authkey = self._load_token_from_disk()

    def _load_token_from_disk(self) -> bytes:
        """Carga el token compartido desde el archivo en disco."""
        token_p = self.certs_dir / TOKEN_FILENAME
        if not token_p.is_file():
            raise SignerUnavailableError(
                f"Falta el archivo de token de autenticación IPC en '{token_p}'. "
                "Asegúrese de que IsolatedSigner haya sido inicializado."
            )
        return token_p.read_bytes().strip()

    def _send_request(self, payload: Dict[str, Any], allow_token_reload: bool = True) -> Dict[str, Any]:
        """Envía una solicitud al Named Pipe y recibe la respuesta estructurada."""
        # 1. Enriquecer con contrato versionado y nonces anti-repetición
        req = dict(payload)
        req.setdefault("protocol_version", PROTOCOL_VERSION)
        req.setdefault("request_id", f"req-{uuid.uuid4().hex[:12]}")
        req.setdefault("timestamp", time.time())
        req.setdefault("nonce", secrets.token_hex(16))

        try:
            conn = Client(self.pipe_name, "AF_PIPE", authkey=self.authkey)
        except AuthenticationError as auth_err:
            if allow_token_reload and not self._custom_authkey:
                logger.warning("Fallo de autenticación HMAC. Reintentando tras recarga de token desde disco...")
                try:
                    self.authkey = self._load_token_from_disk()
                    return self._send_request(req, allow_token_reload=False)
                except Exception:
                    pass
            raise SignerAuthenticationError(
                f"Fallo de autenticación HMAC contra el IsolatedSigner: {auth_err}"
            ) from auth_err
        except TimeoutError as timeout_err:
            raise SignerTimeoutError(
                f"Timeout al conectar con el Named Pipe '{self.pipe_name}': {timeout_err}"
            ) from timeout_err
        except Exception as conn_err:
            raise SignerUnavailableError(
                f"No fue posible conectar al Named Pipe '{self.pipe_name}': {conn_err}. "
                "Verifique que el servicio IsolatedSigner esté en ejecución."
            ) from conn_err

        try:
            conn.send(req)
            ready = wait([conn], timeout=self.timeout)
            if not ready:
                raise SignerTimeoutError(
                    f"Timeout ({self.timeout}s) esperando respuesta del IsolatedSigner."
                )
            resp = conn.recv()
            if not isinstance(resp, dict):
                raise SignerUnavailableError(f"Respuesta inesperada del firmador: {resp}")

            if not resp.get("ok"):
                code = resp.get("code")
                err_msg = resp.get("error", "Error desconocido del firmador.")
                if code == "POLICY_VIOLATION":
                    raise PolicyViolationError(err_msg)
                raise RuntimeError(f"Fallo del firmador [{code}]: {err_msg}")

            return resp
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def ping(self) -> bool:
        """Comprueba de forma pasiva si el servicio IsolatedSigner responde en el Named Pipe."""
        try:
            resp = self._send_request({"action": "PING"})
            return bool(resp.get("status") == "PONG")
        except Exception:
            return False

    def request_certificate(
        self,
        csr_pem: Union[str, bytes],
        target_ip: str,
        valid_days: int = DEFAULT_VALID_DAYS,
        crl_port: int = DEFAULT_CRL_PORT,
    ) -> Dict[str, Any]:
        """Solicita la firma de un certificado hoja a partir de un CSR."""
        if isinstance(csr_pem, bytes):
            csr_str = csr_pem.decode("ascii", errors="replace")
        else:
            csr_str = csr_pem

        payload = {
            "action": "SIGN_CERTIFICATE",
            "csr_pem": csr_str,
            "target_ip": target_ip,
            "valid_days": valid_days,
            "crl_port": crl_port,
        }
        return self._send_request(payload)

    def request_crl(
        self,
        crl_number: int,
        revoked_serials: Optional[List[Dict[str, Any]]] = None,
        valid_days: int = 7,
    ) -> Dict[str, Any]:
        """Solicita la emisión y firma de una Lista de Revocación de Certificados (CRL)."""
        payload = {
            "action": "SIGN_CRL",
            "crl_number": crl_number,
            "revoked_serials": revoked_serials or [],
            "valid_days": valid_days,
        }
        return self._send_request(payload)
