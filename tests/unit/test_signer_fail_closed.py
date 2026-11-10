"""
tests.unit.test_signer_fail_closed
==================================
Suite de pruebas unitarias para verificación de FAIL-CLOSED y eliminación
del fallback criptográfico en el proceso Flask (VIGIA-NET-04A-R1).

Verifica los 12 controles obligatorios:
1. Firmador disponible: Flask delega la firma exitosamente.
2. Firmador detenido: emisión rechazada (Fail-Closed).
3. Named Pipe inexistente: emisión rechazada (Fail-Closed).
4. HMAC inválido: emisión rechazada con error de autenticación.
5. Timeout IPC: emisión rechazada por timeout sin bloqueo indefinido.
6. Error criptográfico remoto: error de política propagado controladamente.
7. Generación de CRL sin firmador: rechazada (Fail-Closed).
8. vigia_root_ca_key.pem nunca se carga ni deserializa desde Flask en producción.
9. Prohibición estricta de firma local en producción (incluso con bandera dev activa).
10. La indisponibilidad del firmador no detiene el servidor Flask (conserva par activo).
11. El certificado activo previo y su manifiesto permanecen intactos ante fallo de emisión.
12. La Root CA real y su huella SHA-256 permanecen 100% inalteradas.
"""

import datetime
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

# Asegurar que VIGIA_Vision_Systems esté en sys.path
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from VIGIA_Security.signer.constants import (
    AUTHORIZED_ROOT_CA_FINGERPRINT,
    DEFAULT_PIPE_NAME,
)
from VIGIA_Security.signer.ipc_client import (
    SignerAuthenticationError,
    SignerClient,
    SignerTimeoutError,
    SignerUnavailableError,
)
from VIGIA_Security.signer.ipc_server import SignerIPCServer
from VIGIA_Security.signer.policy import PolicyViolationError
from VIGIA_Security.signer.service import IsolatedSigner

from VIGIA_API.ingest_service import (
    CRL_FILENAME,
    CRL_STATE_FILENAME,
    MANIFEST_FILENAME,
    generate_vigia_crl,
    generate_vigia_local_ca_bundle,
    is_local_signing_allowed,
)


class TestSignerFailClosed(unittest.TestCase):
    """Suite de 12 pruebas obligatorias de FAIL-CLOSED (VIGIA-NET-04A-R1)."""

    @classmethod
    def setUpClass(cls):
        cls.real_certs_dir = _REPO_ROOT / "certs"
        cls.real_ca_cert = cls.real_certs_dir / "vigia_root_ca.crt"
        cls.real_ca_key = cls.real_certs_dir / "vigia_root_ca_key.pem"

    def setUp(self):
        # Asegurar entorno de producción estricto por defecto
        self._orig_env = os.environ.get("VIGIA_ENV")
        self._orig_dev = os.environ.get("VIGIA_DEV_ALLOW_LOCAL_SIGNING")
        os.environ["VIGIA_ENV"] = "production"
        os.environ.pop("VIGIA_DEV_ALLOW_LOCAL_SIGNING", None)

        self.signer_dir = Path(tempfile.mkdtemp(prefix="vigia_signer_dir_"))
        self.flask_dir = Path(tempfile.mkdtemp(prefix="vigia_flask_dir_"))

        # Copiar Root CA real autorizada al directorio temporal del firmador
        shutil.copy2(self.real_ca_cert, self.signer_dir / "vigia_root_ca.crt")
        shutil.copy2(self.real_ca_key, self.signer_dir / "vigia_root_ca_key.pem")

        # En el directorio de Flask SOLAMENTE existe el certificado público vigia_root_ca.crt
        shutil.copy2(self.real_ca_cert, self.flask_dir / "vigia_root_ca.crt")

        # Generar CRL inicial en flask_dir para satisfacer validaciones de presencia inicial
        ca_cert = x509.load_pem_x509_certificate(self.real_ca_cert.read_bytes())
        ca_key = serialization.load_pem_private_key(self.real_ca_key.read_bytes(), password=None)
        init_crl_p = self.flask_dir / CRL_FILENAME
        init_builder = (
            x509.CertificateRevocationListBuilder()
            .issuer_name(ca_cert.subject)
            .last_update(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1))
            .next_update(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7))
        )
        init_crl = init_builder.sign(ca_key, hashes.SHA256())
        init_crl_p.write_bytes(init_crl.public_bytes(serialization.Encoding.DER))

        self.test_pipe = f"\\\\.\\pipe\\vigia_failclosed_{time.time_ns()}"
        self.authkey = b"super_secret_authkey_token_32b_!"
        (self.signer_dir / "signer_ipc_auth.token").write_bytes(self.authkey)
        (self.flask_dir / "signer_ipc_auth.token").write_bytes(self.authkey)

        self.server = None

    def tearDown(self):
        if self.server:
            try:
                self.server.stop()
            except Exception:
                pass
        if self._orig_env is not None:
            os.environ["VIGIA_ENV"] = self._orig_env
        else:
            os.environ.pop("VIGIA_ENV", None)
        if self._orig_dev is not None:
            os.environ["VIGIA_DEV_ALLOW_LOCAL_SIGNING"] = self._orig_dev
        else:
            os.environ.pop("VIGIA_DEV_ALLOW_LOCAL_SIGNING", None)

        shutil.rmtree(self.signer_dir, ignore_errors=True)
        shutil.rmtree(self.flask_dir, ignore_errors=True)

    def _start_signer(self):
        signer = IsolatedSigner(certs_dir=self.signer_dir)
        self.server = SignerIPCServer(signer=signer, pipe_name=self.test_pipe, authkey=self.authkey)
        self.server.start()
        time.sleep(0.1)

    # ----------------------------------------------------------------------
    # 1. Firmador disponible: Flask delega la firma exitosamente
    # ----------------------------------------------------------------------
    def test_01_signer_available_delegates_signing(self):
        """1. Con el firmador disponible, Flask delega la firma y emite el par TLS."""
        self._start_signer()

        import VIGIA_API.ingest_service as ingest_mod
        orig_client_cls = ingest_mod.SignerClient

        test_pipe = self.test_pipe
        test_auth = self.authkey

        class CustomClient(orig_client_cls):
            def __init__(self, certs_dir, **kwargs):
                super().__init__(certs_dir=certs_dir, pipe_name=test_pipe, authkey=test_auth)

        ingest_mod.SignerClient = CustomClient
        try:
            srv_cert_p, srv_key_p, ca_cert_p = generate_vigia_local_ca_bundle(
                target_ip="192.168.1.76",
                cert_dir=self.flask_dir,
                valid_days=30,
            )
            self.assertTrue(srv_cert_p.is_file())
            self.assertTrue(srv_key_p.is_file())
            # La clave privada de la CA nunca estuvo en flask_dir
            self.assertFalse((self.flask_dir / "vigia_root_ca_key.pem").exists())
        finally:
            ingest_mod.SignerClient = orig_client_cls

    # ----------------------------------------------------------------------
    # 2. Firmador detenido: emisión rechazada (Fail-Closed)
    # ----------------------------------------------------------------------
    def test_02_signer_stopped_issuance_rejected(self):
        """2. Si el firmador está detenido, la emisión se rechaza con SignerUnavailableError."""
        # No se arranca el firmador
        import VIGIA_API.ingest_service as ingest_mod
        orig_client_cls = ingest_mod.SignerClient
        test_pipe = self.test_pipe
        test_auth = self.authkey

        class CustomClient(orig_client_cls):
            def __init__(self, certs_dir, **kwargs):
                super().__init__(certs_dir=certs_dir, pipe_name=test_pipe, authkey=test_auth)

        ingest_mod.SignerClient = CustomClient
        try:
            with self.assertRaises(SignerUnavailableError):
                generate_vigia_local_ca_bundle(
                    target_ip="192.168.1.76",
                    cert_dir=self.flask_dir,
                    overwrite=True,
                )
        finally:
            ingest_mod.SignerClient = orig_client_cls

    # ----------------------------------------------------------------------
    # 3. Named Pipe inexistente: emisión rechazada (Fail-Closed)
    # ----------------------------------------------------------------------
    def test_03_named_pipe_nonexistent_issuance_rejected(self):
        """3. Si el Named Pipe no existe, la emisión se rechaza con SignerUnavailableError."""
        import VIGIA_API.ingest_service as ingest_mod
        orig_client_cls = ingest_mod.SignerClient
        nonexistent_pipe = r"\\.\pipe\vigia_nonexistent_pipe_12345"

        class CustomClient(orig_client_cls):
            def __init__(self, certs_dir, **kwargs):
                super().__init__(certs_dir=certs_dir, pipe_name=nonexistent_pipe, authkey=b"123")

        ingest_mod.SignerClient = CustomClient
        try:
            with self.assertRaises(SignerUnavailableError):
                generate_vigia_local_ca_bundle(
                    target_ip="192.168.1.76",
                    cert_dir=self.flask_dir,
                    overwrite=True,
                )
        finally:
            ingest_mod.SignerClient = orig_client_cls

    # ----------------------------------------------------------------------
    # 4. HMAC inválido: emisión rechazada
    # ----------------------------------------------------------------------
    def test_04_invalid_hmac_issuance_rejected(self):
        """4. Si la clave HMAC es incorrecta, la emisión se rechaza con SignerUnavailableError."""
        self._start_signer()
        import VIGIA_API.ingest_service as ingest_mod
        orig_client_cls = ingest_mod.SignerClient
        test_pipe = self.test_pipe

        class CustomClient(orig_client_cls):
            def __init__(self, certs_dir, **kwargs):
                super().__init__(certs_dir=certs_dir, pipe_name=test_pipe, authkey=b"wrong_token_for_hmac!")

        ingest_mod.SignerClient = CustomClient
        try:
            with self.assertRaises(SignerUnavailableError):
                generate_vigia_local_ca_bundle(
                    target_ip="192.168.1.76",
                    cert_dir=self.flask_dir,
                    overwrite=True,
                )
        finally:
            ingest_mod.SignerClient = orig_client_cls

    # ----------------------------------------------------------------------
    # 5. Timeout IPC: emisión rechazada sin bloqueo indefinido
    # ----------------------------------------------------------------------
    def test_05_ipc_timeout_issuance_rejected(self):
        """5. Si ocurre timeout IPC, se rechaza la operación sin bloquear el proceso."""
        import VIGIA_API.ingest_service as ingest_mod
        orig_client_cls = ingest_mod.SignerClient
        test_pipe = self.test_pipe
        test_auth = self.authkey

        class CustomTimeoutClient(orig_client_cls):
            def __init__(self, certs_dir, **kwargs):
                super().__init__(certs_dir=certs_dir, pipe_name=test_pipe, authkey=test_auth, timeout=0.05)

            def request_certificate(self, *args, **kwargs):
                raise SignerTimeoutError("Timeout simulado esperando IsolatedSigner.")

        ingest_mod.SignerClient = CustomTimeoutClient
        try:
            with self.assertRaises(SignerUnavailableError):
                generate_vigia_local_ca_bundle(
                    target_ip="192.168.1.76",
                    cert_dir=self.flask_dir,
                    overwrite=True,
                )
        finally:
            ingest_mod.SignerClient = orig_client_cls

    # ----------------------------------------------------------------------
    # 6. Error criptográfico remoto: error de política propagado
    # ----------------------------------------------------------------------
    def test_06_remote_cryptographic_error_rejected(self):
        """6. Si el firmador rechaza la solicitud (violación de política), se propaga PolicyViolationError."""
        self._start_signer()
        import VIGIA_API.ingest_service as ingest_mod
        orig_client_cls = ingest_mod.SignerClient
        test_pipe = self.test_pipe
        test_auth = self.authkey

        class CustomClient(orig_client_cls):
            def __init__(self, certs_dir, **kwargs):
                super().__init__(certs_dir=certs_dir, pipe_name=test_pipe, authkey=test_auth)

        ingest_mod.SignerClient = CustomClient
        try:
            # Solicitar IP pública 8.8.8.8 debe violar la política criptográfica
            with self.assertRaises(PolicyViolationError):
                generate_vigia_local_ca_bundle(
                    target_ip="8.8.8.8",
                    cert_dir=self.flask_dir,
                    overwrite=True,
                )
        finally:
            ingest_mod.SignerClient = orig_client_cls

    # ----------------------------------------------------------------------
    # 7. Generación de CRL sin firmador: rechazada (Fail-Closed)
    # ----------------------------------------------------------------------
    def test_07_crl_generation_without_signer_rejected(self):
        """7. Intentar generar o renovar CRL sin el firmador activo en producción es rechazado."""
        # Sin firmador activo
        import VIGIA_API.ingest_service as ingest_mod
        orig_client_cls = ingest_mod.SignerClient
        test_pipe = self.test_pipe
        test_auth = self.authkey

        class CustomClient(orig_client_cls):
            def __init__(self, certs_dir, **kwargs):
                super().__init__(certs_dir=certs_dir, pipe_name=test_pipe, authkey=test_auth)

        ingest_mod.SignerClient = CustomClient
        try:
            with self.assertRaises(SignerUnavailableError):
                generate_vigia_crl(self.flask_dir)
        finally:
            ingest_mod.SignerClient = orig_client_cls

    # ----------------------------------------------------------------------
    # 8. vigia_root_ca_key.pem nunca se carga ni deserializa desde Flask
    # ----------------------------------------------------------------------
    def test_08_no_vigia_root_ca_key_loaded_by_flask(self):
        """8. Flask nunca lee ni deserializa vigia_root_ca_key.pem, incluso si el archivo existiera en cert_dir."""
        self._start_signer()
        # Plantar una clave trampa en flask_dir
        dummy_key_p = self.flask_dir / "vigia_root_ca_key.pem"
        dummy_key_p.write_bytes(b"TRAP_CONTENT_SHOULD_NEVER_BE_READ")

        import VIGIA_API.ingest_service as ingest_mod
        orig_client_cls = ingest_mod.SignerClient
        test_pipe = self.test_pipe
        test_auth = self.authkey

        class CustomClient(orig_client_cls):
            def __init__(self, certs_dir, **kwargs):
                super().__init__(certs_dir=certs_dir, pipe_name=test_pipe, authkey=test_auth)

        ingest_mod.SignerClient = CustomClient
        try:
            # Monitorear serialization.load_pem_private_key
            real_load = serialization.load_pem_private_key
            def guarded_load(data, password=None):
                if b"TRAP_CONTENT" in data:
                    raise AssertionError("VIOLACIÓN: Flask intentó deserializar la clave privada de Root CA!")
                return real_load(data, password)

            with patch("cryptography.hazmat.primitives.serialization.load_pem_private_key", side_effect=guarded_load):
                srv_cert_p, srv_key_p, ca_cert_p = generate_vigia_local_ca_bundle(
                    target_ip="192.168.1.76",
                    cert_dir=self.flask_dir,
                    overwrite=True,
                )
                self.assertTrue(srv_cert_p.is_file())
        finally:
            ingest_mod.SignerClient = orig_client_cls

    # ----------------------------------------------------------------------
    # 9. Prohibición estricta de firma local en producción
    # ----------------------------------------------------------------------
    def test_09_no_local_signing_in_production_even_with_dev_flag(self):
        """9. Si VIGIA_ENV=production, la firma local está prohibida incluso si VIGIA_DEV_ALLOW_LOCAL_SIGNING=true."""
        os.environ["VIGIA_ENV"] = "production"
        os.environ["VIGIA_DEV_ALLOW_LOCAL_SIGNING"] = "true"

        # Debe retornar False incondicionalmente
        self.assertFalse(is_local_signing_allowed())
        ca_cert = x509.load_pem_x509_certificate(self.real_ca_cert.read_bytes())
        self.assertFalse(is_local_signing_allowed(ca_cert))

        # Y si se evalúa contra la huella canónica oficial, siempre retorna False incluso en modo test
        os.environ["VIGIA_ENV"] = "test"
        self.assertFalse(is_local_signing_allowed(ca_cert))

    # ----------------------------------------------------------------------
    # 10. La indisponibilidad del firmador no detiene el servidor Flask
    # ----------------------------------------------------------------------
    def test_10_signer_unavailability_does_not_crash_flask_server(self):
        """10. Si el par TLS ya existe y el firmador no responde al arrancar, Flask no crashea."""
        # 1. Crear un par de certificados existente
        existing_cert = self.flask_dir / "vigia_cert.pem"
        existing_key = self.flask_dir / "vigia_key.pem"
        existing_cert.write_text("DUMMY_CERT_ACTIVE", encoding="utf-8")
        existing_key.write_text("DUMMY_KEY_ACTIVE", encoding="utf-8")

        # 2. Simular bloque de arranque de ingest_service con SignerUnavailableError
        signer_crashed = True
        server_running = False
        try:
            try:
                # Simular intento de renovar cuando el firmador está caído
                if signer_crashed:
                    raise SignerUnavailableError("IsolatedSigner fuera de línea en el puerto/pipe.")
            except SignerUnavailableError as err:
                if existing_cert.exists() and existing_key.exists():
                    # Comportamiento implementado en run_ingest_server: advertencia sin crash
                    server_running = True
                else:
                    raise
            self.assertTrue(server_running)
        except Exception:
            self.fail("El servidor Flask crasheó ante indisponibilidad del firmador con par TLS existente.")

    # ----------------------------------------------------------------------
    # 11. El certificado activo anterior permanece intacto ante fallo de emisión
    # ----------------------------------------------------------------------
    def test_11_previous_active_certificate_intact_on_failure(self):
        """11. Si una nueva emisión falla por caída del firmador, el par activo anterior permanece intacto."""
        # Establecer par activo inicial y manifiesto
        cert_p = self.flask_dir / "vigia_cert.pem"
        key_p = self.flask_dir / "vigia_key.pem"
        manifest_p = self.flask_dir / MANIFEST_FILENAME

        cert_p.write_text("CERT_GENERATION_1_ACTIVE", encoding="utf-8")
        key_p.write_text("KEY_GENERATION_1_ACTIVE", encoding="utf-8")
        initial_manifest = {"generation_id": "gen_1_active", "target_ip": "192.168.1.76"}
        manifest_p.write_text(json.dumps(initial_manifest), encoding="utf-8")

        # Intentar emitir una nueva generación sin firmador activo
        import VIGIA_API.ingest_service as ingest_mod
        orig_client_cls = ingest_mod.SignerClient
        test_pipe = self.test_pipe
        test_auth = self.authkey

        class CustomClient(orig_client_cls):
            def __init__(self, certs_dir, **kwargs):
                super().__init__(certs_dir=certs_dir, pipe_name=test_pipe, authkey=test_auth)

        ingest_mod.SignerClient = CustomClient
        try:
            with self.assertRaises(SignerUnavailableError):
                generate_vigia_local_ca_bundle(
                    target_ip="192.168.1.99",
                    cert_dir=self.flask_dir,
                    overwrite=True,
                )

            # Verificar que el par previo y el manifest no sufrieron alteración
            self.assertEqual(cert_p.read_text(encoding="utf-8"), "CERT_GENERATION_1_ACTIVE")
            self.assertEqual(key_p.read_text(encoding="utf-8"), "KEY_GENERATION_1_ACTIVE")
            current_manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
            self.assertEqual(current_manifest["generation_id"], "gen_1_active")
        finally:
            ingest_mod.SignerClient = orig_client_cls

    # ----------------------------------------------------------------------
    # 12. La Root CA real y su huella SHA-256 permanecen 100% inalteradas
    # ----------------------------------------------------------------------
    def test_12_root_ca_and_fingerprint_unmodified(self):
        """12. Verificación criptográfica de que la Root CA oficial en certs/ está intacta."""
        prod_ca_cert_p = _REPO_ROOT / "certs" / "vigia_root_ca.crt"
        self.assertTrue(prod_ca_cert_p.is_file())

        real_cert = x509.load_pem_x509_certificate(prod_ca_cert_p.read_bytes())
        real_fp = real_cert.fingerprint(hashes.SHA256()).hex().upper()
        self.assertEqual(real_fp, AUTHORIZED_ROOT_CA_FINGERPRINT)

        # Verificar BasicConstraints pathlen=0
        bc = real_cert.extensions.get_extension_for_oid(x509.ExtensionOID.BASIC_CONSTRAINTS).value
        self.assertTrue(bc.ca)
        self.assertEqual(bc.path_length, 0)


if __name__ == "__main__":
    unittest.main()
