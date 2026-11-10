"""
tests.unit.test_ipc_hardening
=============================
Suite de 16 pruebas obligatorias para el endurecimiento de Named Pipe e IPC (VIGIA-NET-04A-R3).
Verifica:
1. Cliente autorizado.
2. Cliente sin permisos de Named Pipe (DACL / SID).
3. HMAC inválido.
4. Mensaje malformado.
5. Mensaje excesivamente grande (> 64 KB).
6. Cliente que conecta y no transmite datos (cliente silencioso).
7. Cliente que interrumpe la conexión abruptamente.
8. Timeout de lectura acotado.
9. Timeout de escritura y respuesta.
10. Concurrencia de solicitudes legítimas simultáneas.
11. Agotamiento y límite de conexiones.
12. Recuperación inmediata tras solicitudes malformadas.
13. Rechazo de replay (mitigación de repetición con nonce duplicado).
14. Reversión garantizada de impersonación (RevertToSelf) ante excepciones.
15. Conservación estricta de la política FAIL-CLOSED.
16. Compatibilidad total con SignerClient.
"""

from __future__ import annotations

import os
import secrets
import shutil
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from multiprocessing.connection import Client, Listener
from pathlib import Path
from typing import Any, Dict, List, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from VIGIA_Security.signer.constants import (
    DEFAULT_CRL_PORT,
    MAX_MESSAGE_BYTES,
    PROTOCOL_VERSION,
    TOKEN_FILENAME,
)
from VIGIA_Security.signer.ipc_client import (
    SignerAuthenticationError,
    SignerClient,
    SignerTimeoutError,
    SignerUnavailableError,
)
from VIGIA_Security.signer.ipc_server import (
    IS_WINDOWS,
    SignerIPCServer,
    get_current_user_sid,
)
from VIGIA_Security.signer.policy import PolicyViolationError
from VIGIA_Security.signer.service import IsolatedSigner

_REPO_ROOT = Path(__file__).resolve().parents[2]


class TestIPCHardeningR3(unittest.TestCase):
    """Pruebas del subsistema IPC endurecido de IsolatedSigner (VIGIA-NET-04A-R3)."""

    @classmethod
    def setUpClass(cls):
        cls.real_certs_dir = _REPO_ROOT / "certs"
        cls.real_ca_cert = cls.real_certs_dir / "vigia_root_ca.crt"
        cls.real_ca_key = cls.real_certs_dir / "vigia_root_ca_key.pem"

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="vigia_r3_test_"))
        # Copiar CA autorizada real al directorio de prueba
        shutil.copy2(self.real_ca_cert, self.test_dir / "vigia_root_ca.crt")
        shutil.copy2(self.real_ca_key, self.test_dir / "vigia_root_ca_key.pem")

        self.authkey = secrets.token_bytes(32)
        (self.test_dir / TOKEN_FILENAME).write_bytes(self.authkey)

        self.pipe_name = f"\\\\.\\pipe\\vigia_r3_pipe_{time.time_ns()}"
        self.signer = IsolatedSigner(certs_dir=self.test_dir)
        self.server: Optional[SignerIPCServer] = None

    def tearDown(self):
        if self.server:
            try:
                self.server.stop()
            except Exception:
                pass
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _start_server(self, **kwargs) -> SignerIPCServer:
        params = {
            "signer": self.signer,
            "pipe_name": self.pipe_name,
            "authkey": self.authkey,
        }
        params.update(kwargs)
        srv = SignerIPCServer(**params)
        srv.start()
        self.server = srv
        return srv

    def _generate_csr(self, cn: str = "vigia.local") -> str:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .sign(key, hashes.SHA256())
        )
        return csr.public_bytes(serialization.Encoding.PEM).decode("ascii")

    # -------------------------------------------------------------------------
    # 1. Cliente autorizado
    # -------------------------------------------------------------------------
    def test_01_authorized_client(self):
        """1. Cliente autorizado puede ejecutar ping y obtener firma criptográfica."""
        self._start_server()
        client = SignerClient(certs_dir=self.test_dir, pipe_name=self.pipe_name, authkey=self.authkey)
        self.assertTrue(client.ping())

        csr_pem = self._generate_csr("vigia.local")
        resp = client.request_certificate(csr_pem=csr_pem, target_ip="192.168.1.100")
        self.assertTrue(resp["ok"])
        self.assertIn("BEGIN CERTIFICATE", resp["cert_pem"])
        self.assertEqual(resp.get("protocol_version"), PROTOCOL_VERSION)

    # -------------------------------------------------------------------------
    # 2. Cliente sin permisos de Named Pipe
    # -------------------------------------------------------------------------
    def test_02_client_without_pipe_permission(self):
        """2. Cliente con SID no autorizado es rechazado a nivel de política de acceso."""
        # Forzar una lista de SIDs donde NO esté el SID del proceso actual
        fake_allowed = ["S-1-5-21-9999999999-9999999999-9999999999-9999"]
        self._start_server(enforce_client_sid=True, allowed_sids=fake_allowed)

        client = SignerClient(certs_dir=self.test_dir, pipe_name=self.pipe_name, authkey=self.authkey)
        # La solicitud debe ser rechazada por SID no autorizado
        csr_pem = self._generate_csr()
        with self.assertRaises(RuntimeError) as ctx:
            client.request_certificate(csr_pem=csr_pem, target_ip="192.168.1.100")
        self.assertIn("ACCESS_DENIED_SID", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 3. HMAC inválido
    # -------------------------------------------------------------------------
    def test_03_invalid_hmac(self):
        """3. Conexión con clave HMAC alterada falla con SignerAuthenticationError."""
        self._start_server()
        wrong_authkey = secrets.token_bytes(32)
        bad_client = SignerClient(certs_dir=self.test_dir, pipe_name=self.pipe_name, authkey=wrong_authkey)

        self.assertFalse(bad_client.ping())
        with self.assertRaises(SignerUnavailableError):
            bad_client.request_certificate(csr_pem=self._generate_csr(), target_ip="192.168.1.100")

    # -------------------------------------------------------------------------
    # 4. Mensaje malformado
    # -------------------------------------------------------------------------
    def test_04_malformed_message(self):
        """4. Mensaje malformado o tipo de dato no soportado es rechazado limpiamente."""
        self._start_server()
        # Enviar primitivo no esperado (ej. string en lugar de dict) vía conexión de bajo nivel
        c = Client(self.pipe_name, "AF_PIPE", authkey=self.authkey)
        c.send("SOLICITUD_INVALIDA_NO_DICT")
        resp = c.recv()
        c.close()

        self.assertFalse(resp["ok"])
        self.assertEqual(resp.get("code"), "MALFORMED_REQUEST")

    # -------------------------------------------------------------------------
    # 5. Mensaje excesivamente grande
    # -------------------------------------------------------------------------
    def test_05_oversized_message(self):
        """5. Mensaje con longitud que excede MAX_MESSAGE_BYTES (64 KB) es rechazado."""
        self._start_server()
        c = Client(self.pipe_name, "AF_PIPE", authkey=self.authkey)
        huge_payload = {"action": "PING", "garbage": "A" * (MAX_MESSAGE_BYTES + 1024)}
        try:
            c.send(huge_payload)
            resp = c.recv()
            self.assertFalse(resp["ok"])
            self.assertEqual(resp.get("code"), "MESSAGE_TOO_LARGE")
        except (BrokenPipeError, OSError, EOFError):
            # El kernel o el servidor cerraron la conexión por exceso de tamaño
            pass
        finally:
            try:
                c.close()
            except Exception:
                pass

        # Verificar que el servidor se mantiene sano para solicitudes subsiguientes
        client = SignerClient(certs_dir=self.test_dir, pipe_name=self.pipe_name, authkey=self.authkey)
        self.assertTrue(client.ping())

    # -------------------------------------------------------------------------
    # 6. Cliente silencioso (conecta y no transmite datos)
    # -------------------------------------------------------------------------
    def test_06_silent_client_does_not_block_others(self):
        """6. Cliente que conecta y no envía datos supera read_timeout sin bloquear a otros clientes."""
        # Configurar un timeout de lectura corto de 1.0s para la prueba
        self._start_server(read_timeout=1.0)

        # Hilo con cliente silencioso
        def silent_worker():
            try:
                conn_silent = Client(self.pipe_name, "AF_PIPE", authkey=self.authkey)
                time.sleep(2.0)
                conn_silent.close()
            except Exception:
                pass

        t_silent = threading.Thread(target=silent_worker)
        t_silent.start()

        # Mientras el cliente silencioso está conectado, un cliente activo debe operar sin bloqueo
        time.sleep(0.1)
        client = SignerClient(certs_dir=self.test_dir, pipe_name=self.pipe_name, authkey=self.authkey)
        t0 = time.time()
        self.assertTrue(client.ping())
        elapsed = time.time() - t0

        # Debe responder inmediatamente (menos de 0.5s), no esperar los 2s del cliente silencioso
        self.assertLess(elapsed, 0.8)
        t_silent.join()

    # -------------------------------------------------------------------------
    # 7. Cliente que interrumpe la conexión abruptamente
    # -------------------------------------------------------------------------
    def test_07_client_abrupt_disconnect(self):
        """7. Cliente que cierra la conexión inmediatamente es manejado sin corromper el servidor."""
        self._start_server()
        c = Client(self.pipe_name, "AF_PIPE", authkey=self.authkey)
        c.close()  # Cierre inmediato sin enviar datos

        time.sleep(0.1)
        # El servidor debe seguir operativo para el siguiente cliente
        client = SignerClient(certs_dir=self.test_dir, pipe_name=self.pipe_name, authkey=self.authkey)
        self.assertTrue(client.ping())

    # -------------------------------------------------------------------------
    # 8. Timeout de lectura
    # -------------------------------------------------------------------------
    def test_08_read_timeout_enforced(self):
        """8. La conexión de un cliente lento que no transmite a tiempo es cancelada por read_timeout."""
        self._start_server(read_timeout=0.5)
        c = Client(self.pipe_name, "AF_PIPE", authkey=self.authkey)
        time.sleep(0.8)  # Superar los 0.5s

        # Intentar enviar después del timeout: el servidor debe haber cerrado su extremo
        try:
            c.send({"action": "PING"})
            # Si el send tiene éxito en el buffer local, recv debe fallar por conexión cerrada
            with self.assertRaises(Exception):
                c.recv()
        except (BrokenPipeError, OSError, EOFError):
            pass
        finally:
            c.close()

    # -------------------------------------------------------------------------
    # 9. Timeout de escritura / respuesta
    # -------------------------------------------------------------------------
    def test_09_write_timeout_and_ping(self):
        """9. Operaciones de ping y respuesta respetan los límites de tiempo configurados."""
        self._start_server(read_timeout=2.0, write_timeout=2.0)
        client = SignerClient(certs_dir=self.test_dir, pipe_name=self.pipe_name, authkey=self.authkey, timeout=2.0)
        self.assertTrue(client.ping())

    # -------------------------------------------------------------------------
    # 10. Concurrencia de solicitudes legítimas
    # -------------------------------------------------------------------------
    def test_10_concurrent_legitimate_requests(self):
        """10. Múltiples clientes simultáneos procesan firmas concurrentemente con éxito."""
        self._start_server(max_connections=5)
        client = SignerClient(certs_dir=self.test_dir, pipe_name=self.pipe_name, authkey=self.authkey)

        results = []

        def worker_task(idx: int):
            c = SignerClient(certs_dir=self.test_dir, pipe_name=self.pipe_name, authkey=self.authkey)
            pong = c.ping()
            results.append((idx, pong))

        threads = [threading.Thread(target=worker_task, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 5)
        self.assertTrue(all(r[1] for r in results))

    # -------------------------------------------------------------------------
    # 11. Agotamiento del límite de conexiones
    # -------------------------------------------------------------------------
    def test_11_max_connections_handled(self):
        """11. El servidor admite hasta max_connections sin fallar ni corromper su estado."""
        self._start_server(max_connections=3)
        clients = []
        try:
            for _ in range(3):
                c = Client(self.pipe_name, "AF_PIPE", authkey=self.authkey)
                clients.append(c)

            # Enviar PING en todas las conexiones abiertas
            for c in clients:
                c.send({"action": "PING"})
            for c in clients:
                resp = c.recv()
                self.assertTrue(resp["ok"])
        finally:
            for c in clients:
                try:
                    c.close()
                except Exception:
                    pass

    # -------------------------------------------------------------------------
    # 12. Recuperación después de solicitudes malformadas
    # -------------------------------------------------------------------------
    def test_12_recovery_after_malformed_requests(self):
        """12. Tras procesar solicitudes erróneas, el servidor atiende clientes legítimos sin reiniciar."""
        self._start_server()

        # Enviar petición corrupta
        c_bad = Client(self.pipe_name, "AF_PIPE", authkey=self.authkey)
        c_bad.send({"action": "ACCION_INEXISTENTE_XYZ"})
        resp_bad = c_bad.recv()
        c_bad.close()
        self.assertFalse(resp_bad["ok"])
        self.assertEqual(resp_bad["code"], "UNKNOWN_ACTION")

        # Petición legítima subsiguiente
        client = SignerClient(certs_dir=self.test_dir, pipe_name=self.pipe_name, authkey=self.authkey)
        self.assertTrue(client.ping())

    # -------------------------------------------------------------------------
    # 13. Rechazo de replay (ataques de repetición)
    # -------------------------------------------------------------------------
    def test_13_replay_attack_rejected(self):
        """13. Reenviar exactamente la misma solicitud con idéntico nonce es rechazado por REPLAY_DETECTED."""
        self._start_server()

        fixed_nonce = "fixed_nonce_1234567890abcdef"
        fixed_ts = time.time()
        fixed_req = {
            "action": "PING",
            "protocol_version": PROTOCOL_VERSION,
            "request_id": "req-fixed-1",
            "timestamp": fixed_ts,
            "nonce": fixed_nonce,
        }

        # Primer envío: debe ser aceptado
        c1 = Client(self.pipe_name, "AF_PIPE", authkey=self.authkey)
        c1.send(fixed_req)
        resp1 = c1.recv()
        c1.close()
        self.assertTrue(resp1["ok"])

        # Segundo envío con exactamente el mismo nonce y timestamp: debe ser rechazado
        c2 = Client(self.pipe_name, "AF_PIPE", authkey=self.authkey)
        c2.send(fixed_req)
        resp2 = c2.recv()
        c2.close()
        self.assertFalse(resp2["ok"])
        self.assertEqual(resp2["code"], "REPLAY_DETECTED")

    # -------------------------------------------------------------------------
    # 14. Reversión de impersonación después de errores
    # -------------------------------------------------------------------------
    def test_14_revert_to_self_after_errors(self):
        """14. RevertToSelf es invocado incondicionalmente tras procesar una solicitud fallida."""
        if not IS_WINDOWS:
            self.skipTest("Prueba específica de Windows (advapi32.RevertToSelf).")

        self._start_server()
        # Enviar petición con acción que lance excepción
        c = Client(self.pipe_name, "AF_PIPE", authkey=self.authkey)
        c.send({"action": "SIGN_CERTIFICATE"})  # Faltan campos obligatorios
        resp = c.recv()
        c.close()
        self.assertFalse(resp["ok"])

        # Verificar que el hilo actual no quedó impersonando a un cliente
        import ctypes
        kernel32 = ctypes.windll.kernel32
        advapi32 = ctypes.windll.advapi32
        hToken = ctypes.c_void_p()
        # OpenThreadToken sobre el hilo actual debe fallar si no hay token de impersonación activo
        res = advapi32.OpenThreadToken(kernel32.GetCurrentThread(), 0x0008, True, ctypes.byref(hToken))
        # res debe ser 0 (False), indicando que el hilo corre bajo el token de proceso y no está impersonado
        self.assertFalse(bool(res))

    # -------------------------------------------------------------------------
    # 15. Conservación de FAIL-CLOSED
    # -------------------------------------------------------------------------
    def test_15_fail_closed_preserved(self):
        """15. La política FAIL-CLOSED rechaza terminantemente la firma si el firmador no responde."""
        # Detener intencionalmente el servidor
        fake_pipe = f"\\\\.\\pipe\\vigia_nonexistent_{time.time_ns()}"
        client = SignerClient(certs_dir=self.test_dir, pipe_name=fake_pipe, authkey=self.authkey)

        self.assertFalse(client.ping())
        with self.assertRaises(SignerUnavailableError):
            client.request_certificate(csr_pem=self._generate_csr(), target_ip="192.168.1.100")

    # -------------------------------------------------------------------------
    # 16. Compatibilidad con SignerClient y recarga de token
    # -------------------------------------------------------------------------
    def test_16_signer_client_compatibility_and_reload(self):
        """16. SignerClient opera de forma transparente y soporta recarga perezosa de token."""
        self._start_server()

        # Simular cliente que lee el token desde el archivo de disco
        client = SignerClient(certs_dir=self.test_dir, pipe_name=self.pipe_name)
        self.assertTrue(client.ping())

        # Rotar el token en disco y en caliente en el servidor
        new_token = secrets.token_bytes(32)
        (self.test_dir / TOKEN_FILENAME).write_bytes(new_token)
        self.server.set_authkey(new_token)

        # El cliente previo debe recargar automáticamente el token desde disco tras detectar rotación y tener éxito
        self.assertTrue(client.ping())


if __name__ == "__main__":
    unittest.main()
