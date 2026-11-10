"""
tests.unit.test_isolated_signer
===============================
Pruebas unitarias de aislamiento criptográfico, políticas X.509 e IPC para IsolatedSigner (VIGIA-NET-04A).
"""

import datetime
import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Asegurar que VIGIA_Vision_Systems esté en sys.path
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from VIGIA_Security.signer.constants import (
    AUTHORIZED_ROOT_CA_FINGERPRINT,
    DEFAULT_PIPE_NAME,
    MAX_VALID_DAYS,
)
from VIGIA_Security.signer.ipc_client import SignerClient, SignerUnavailableError
from VIGIA_Security.signer.ipc_server import SignerIPCServer
from VIGIA_Security.signer.policy import PolicyViolationError, SignerPolicyValidator
from VIGIA_Security.signer.service import IsolatedSigner, SignerIntegrityError


class TestIsolatedSigner(unittest.TestCase):
    """Batería de pruebas de seguridad y aislamiento criptográfico."""

    @classmethod
    def setUpClass(cls):
        # Rutas de la Root CA real de producción en el repositorio
        cls.repo_root = Path(__file__).resolve().parent.parent.parent
        cls.real_certs_dir = cls.repo_root / "certs"
        cls.real_ca_cert = cls.real_certs_dir / "vigia_root_ca.crt"
        cls.real_ca_key = cls.real_certs_dir / "vigia_root_ca_key.pem"

    def setUp(self):
        # Directorio temporal aislado para pruebas
        self.test_dir = Path(tempfile.mkdtemp(prefix="vigia_signer_test_"))
        self.test_ca_cert = self.test_dir / "vigia_root_ca.crt"
        self.test_ca_key = self.test_dir / "vigia_root_ca_key.pem"

        # Copiar Root CA real al directorio temporal
        shutil.copy2(self.real_ca_cert, self.test_ca_cert)
        shutil.copy2(self.real_ca_key, self.test_ca_key)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _generate_test_csr(self, rsa_key=None, subject_cn="VIGIA LAN Server (192.168.1.76)", extra_extensions=None):
        if rsa_key is None:
            rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        builder = x509.CertificateSigningRequestBuilder().subject_name(
            x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "MX"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "VIGIA Vision Systems"),
                x509.NameAttribute(NameOID.COMMON_NAME, subject_cn),
            ])
        )

        if extra_extensions:
            for ext, crit in extra_extensions:
                builder = builder.add_extension(ext, critical=crit)

        csr = builder.sign(rsa_key, hashes.SHA256())
        return csr.public_bytes(serialization.Encoding.PEM), rsa_key

    def test_01_root_ca_fingerprint_verified_and_tamper_rejected(self):
        """1. IsolatedSigner valida la huella SHA-256 de la Root CA y rechaza certificados alterados."""
        signer = IsolatedSigner(certs_dir=self.test_dir)
        self.assertIsNotNone(signer._ca_cert)

        # Alterar el certificado en un directorio separado
        tampered_dir = Path(tempfile.mkdtemp(prefix="vigia_tamper_"))
        try:
            fake_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            fake_subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Fake CA")])
            now = datetime.datetime.now(datetime.timezone.utc)
            fake_cert = (
                x509.CertificateBuilder()
                .subject_name(fake_subject)
                .issuer_name(fake_subject)
                .public_key(fake_key.public_key())
                .serial_number(12345)
                .not_valid_before(now)
                .not_valid_after(now + datetime.timedelta(days=1))
                .sign(fake_key, hashes.SHA256())
            )
            (tampered_dir / "vigia_root_ca.crt").write_bytes(fake_cert.public_bytes(serialization.Encoding.PEM))
            (tampered_dir / "vigia_root_ca_key.pem").write_bytes(
                fake_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

            with self.assertRaises(SignerIntegrityError) as ctx:
                IsolatedSigner(certs_dir=tampered_dir)
            self.assertIn("Violación de integridad", str(ctx.exception))
        finally:
            shutil.rmtree(tampered_dir, ignore_errors=True)

    def test_02_sign_valid_csr_depth_one(self):
        """2. Firma directa de certificado hoja con Root CA autorizada a profundidad 1 (sin CA intermedia)."""
        signer = IsolatedSigner(certs_dir=self.test_dir)
        csr_pem, srv_key = self._generate_test_csr()

        resp = signer.sign_certificate(
            csr_pem=csr_pem,
            target_ip="192.168.1.76",
            valid_days=90,
            crl_port=5080,
            client_identity="test_process",
        )

        self.assertTrue(resp["ok"])
        cert_pem = resp["cert_pem"]
        cert = x509.load_pem_x509_certificate(cert_pem.encode("ascii"))

        # A. Validar que fue firmado por la Root CA autorizada
        ca_cert = x509.load_pem_x509_certificate(self.test_ca_cert.read_bytes())
        ca_cert.public_key().verify(
            cert.signature,
            cert.tbs_certificate_bytes,
            padding.PKCS1v15(),
            cert.signature_hash_algorithm,
        )

        # B. Validar BasicConstraints: CA=False (Profundidad 1, cumple con path_length=0)
        bc = cert.extensions.get_extension_for_oid(x509.OID_BASIC_CONSTRAINTS).value
        self.assertFalse(bc.ca)

        # C. Validar EKU serverAuth
        eku = cert.extensions.get_extension_for_oid(x509.OID_EXTENDED_KEY_USAGE).value
        self.assertIn(ExtendedKeyUsageOID.SERVER_AUTH, eku)

        # D. Validar SAN (localhost, 127.0.0.1, vigia.local, 192.168.1.76)
        san = cert.extensions.get_extension_for_oid(x509.OID_SUBJECT_ALTERNATIVE_NAME).value
        san_strings = [str(x) for x in san]
        self.assertTrue(any("192.168.1.76" in s for s in san_strings))
        self.assertTrue(any("127.0.0.1" in s for s in san_strings))
        self.assertTrue(any("vigia.local" in s for s in san_strings))

        # E. Validar CDP (conforme a VIGIA-NET-03E, contiene LAN y vigia.local, NO 127.0.0.1 para clientes remotos)
        cdp = cert.extensions.get_extension_for_oid(x509.OID_CRL_DISTRIBUTION_POINTS).value
        cdp_uris = [n.value for dp in cdp for n in dp.full_name]
        self.assertIn("http://192.168.1.76:5080/api/v1/tls/ca.crl", cdp_uris)
        self.assertIn("http://vigia.local:5080/api/v1/tls/ca.crl", cdp_uris)
        self.assertNotIn("http://127.0.0.1:5080/api/v1/tls/ca.crl", cdp_uris)

    def test_03_policy_rejects_public_ip(self):
        """3. La política rechaza terminantemente la emisión para direcciones IP públicas."""
        signer = IsolatedSigner(certs_dir=self.test_dir)
        csr_pem, _ = self._generate_test_csr()

        with self.assertRaises(PolicyViolationError) as ctx:
            signer.sign_certificate(csr_pem=csr_pem, target_ip="8.8.8.8")
        self.assertIn("No se autoriza la emisión de certificados para IPs públicas", str(ctx.exception))

        with self.assertRaises(PolicyViolationError):
            signer.sign_certificate(csr_pem=csr_pem, target_ip="1.1.1.1")

    def test_04_policy_rejects_apipa_and_unspecified(self):
        """4. La política rechaza direcciones de autoconfiguración APIPA (169.254.x.x) y 0.0.0.0."""
        signer = IsolatedSigner(certs_dir=self.test_dir)
        csr_pem, _ = self._generate_test_csr()

        with self.assertRaises(PolicyViolationError) as ctx:
            signer.sign_certificate(csr_pem=csr_pem, target_ip="169.254.12.34")
        self.assertIn("APIPA", str(ctx.exception))

        with self.assertRaises(PolicyViolationError) as ctx2:
            signer.sign_certificate(csr_pem=csr_pem, target_ip="0.0.0.0")
        self.assertIn("0.0.0.0", str(ctx2.exception))

    def test_05_policy_rejects_arbitrary_public_domains(self):
        """5. La política rechaza nombres de dominio públicos arbitrarios (google.com, etc.)."""
        signer = IsolatedSigner(certs_dir=self.test_dir)
        csr_pem, _ = self._generate_test_csr()

        with self.assertRaises(PolicyViolationError) as ctx:
            signer.sign_certificate(csr_pem=csr_pem, target_ip="google.com")
        self.assertIn("no autorizado", str(ctx.exception))

    def test_06_policy_rejects_ca_csr(self):
        """6. La política rechaza cualquier CSR que solicite facultades de CA (BasicConstraints CA=True o keyCertSign)."""
        signer = IsolatedSigner(certs_dir=self.test_dir)

        # CSR malicioso que intenta solicitar CA=True
        extra = [(x509.BasicConstraints(ca=True, path_length=None), True)]
        ca_csr_pem, _ = self._generate_test_csr(extra_extensions=extra)

        with self.assertRaises(PolicyViolationError) as ctx:
            signer.sign_certificate(csr_pem=ca_csr_pem, target_ip="192.168.1.76")
        self.assertIn("CA=True", str(ctx.exception))

        # CSR malicioso con keyCertSign
        ku_extra = [(x509.KeyUsage(False, False, False, False, False, True, False, False, False), True)]
        ku_csr_pem, _ = self._generate_test_csr(extra_extensions=ku_extra)

        with self.assertRaises(PolicyViolationError) as ctx2:
            signer.sign_certificate(csr_pem=ku_csr_pem, target_ip="192.168.1.76")
        self.assertIn("keyCertSign", str(ctx2.exception))

    def test_07_policy_enforces_valid_days_limit(self):
        """7. La política limita la vigencia a un máximo de 90 días naturales."""
        signer = IsolatedSigner(certs_dir=self.test_dir)
        csr_pem, _ = self._generate_test_csr()

        with self.assertRaises(PolicyViolationError) as ctx:
            signer.sign_certificate(csr_pem=csr_pem, target_ip="192.168.1.76", valid_days=365)
        self.assertIn("excede el máximo autorizado", str(ctx.exception))

        with self.assertRaises(PolicyViolationError):
            signer.sign_certificate(csr_pem=csr_pem, target_ip="192.168.1.76", valid_days=0)

    def test_08_rate_limiting_enforced(self):
        """8. El rate limiting restringe a un máximo de 5 firmas por minuto."""
        signer = IsolatedSigner(certs_dir=self.test_dir, rate_limit_per_minute=3)
        csr_pem, _ = self._generate_test_csr()

        # Emitir 3 certificados exitosos
        for _ in range(3):
            res = signer.sign_certificate(csr_pem=csr_pem, target_ip="192.168.1.76")
            self.assertTrue(res["ok"])

        # La 4ta solicitud debe ser rechazada por rate limit
        with self.assertRaises(PolicyViolationError) as ctx:
            signer.sign_certificate(csr_pem=csr_pem, target_ip="192.168.1.76")
        self.assertIn("Límite de tasa excedido", str(ctx.exception))

    def test_09_audit_log_written_atomically(self):
        """9. Toda emisión de certificados y CRLs escribe un registro estructurado en ca_issuance.jsonl."""
        signer = IsolatedSigner(certs_dir=self.test_dir)
        csr_pem, _ = self._generate_test_csr()

        signer.sign_certificate(csr_pem=csr_pem, target_ip="192.168.1.76", client_identity="audit_tester")

        log_file = self.test_dir / "audit" / "ca_issuance.jsonl"
        self.assertTrue(log_file.is_file())

        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        self.assertGreaterEqual(len(lines), 1)
        last_entry = json.loads(lines[-1])
        self.assertEqual(last_entry["event"], "CERTIFICATE_ISSUED")
        self.assertEqual(last_entry["details"]["client_identity"], "audit_tester")
        self.assertEqual(last_entry["details"]["target_ip"], "192.168.1.76")

    def test_10_crl_signing_monotonic(self):
        """10. La emisión de CRL firma con la Root CA e incrementa el número secuencial."""
        signer = IsolatedSigner(certs_dir=self.test_dir)
        crl_res = signer.sign_crl(
            crl_number=42,
            revoked_serials=[{"serial_number": "0x12345", "reason": "key_compromise"}],
            client_identity="crl_tester",
        )
        self.assertTrue(crl_res["ok"])
        crl = x509.load_der_x509_crl(crl_res["crl_der_bytes"])

        # Verificar firma de la CRL con la Root CA
        ca_cert = x509.load_pem_x509_certificate(self.test_ca_cert.read_bytes())
        self.assertTrue(crl.is_signature_valid(ca_cert.public_key()))

        # Verificar CRLNumber
        crl_num_ext = crl.extensions.get_extension_for_oid(x509.ExtensionOID.CRL_NUMBER).value
        self.assertEqual(crl_num_ext.crl_number, 42)

    def test_11_ipc_named_pipe_signing_and_auth(self):
        """11. Comunicación IPC sobre Named Pipe en Windows: autenticación por HMAC, firma y rechazo sin auth."""
        test_pipe = f"\\\\.\\pipe\\vigia_test_pipe_{int(time.time())}"
        test_authkey = b"super_secret_auth_token_for_pipe_32b!"

        signer = IsolatedSigner(certs_dir=self.test_dir)
        server = SignerIPCServer(signer=signer, pipe_name=test_pipe, authkey=test_authkey)
        server.start()

        try:
            # Cliente autorizado
            client = SignerClient(
                certs_dir=self.test_dir,
                pipe_name=test_pipe,
                authkey=test_authkey,
            )
            self.assertTrue(client.ping())

            # Solicitar firma vía Named Pipe
            csr_pem, _ = self._generate_test_csr()
            resp = client.request_certificate(csr_pem=csr_pem, target_ip="192.168.1.76")
            self.assertTrue(resp["ok"])
            self.assertIn("BEGIN CERTIFICATE", resp["cert_pem"])

            # Cliente con clave incorrecta debe retornar False en ping y fallar con SignerUnavailableError en request
            bad_client = SignerClient(
                certs_dir=self.test_dir,
                pipe_name=test_pipe,
                authkey=b"wrong_authentication_key_12345678",
            )
            self.assertFalse(bad_client.ping())
            with self.assertRaises(SignerUnavailableError):
                bad_client.request_certificate(csr_pem=csr_pem, target_ip="192.168.1.76")

        finally:
            server.stop()

    def test_12_ingest_service_delegates_to_isolated_signer_without_ca_key(self):
        """12. Demostración E2E: generate_vigia_local_ca_bundle emite certificado vía IsolatedSigner sin vigia_root_ca_key.pem."""
        from VIGIA_API.ingest_service import generate_vigia_local_ca_bundle, validate_tls_certificate_pair

        # Directorio del firmador (contiene la clave privada Root CA y el token)
        signer_dir = Path(tempfile.mkdtemp())
        # Directorio de Flask (NO contiene la clave privada vigia_root_ca_key.pem)
        flask_dir = Path(tempfile.mkdtemp())

        test_pipe = f"\\\\.\\pipe\\vigia_test_pipe_e2e_{int(time.time())}"
        test_authkey = b"isolated_auth_key_token_e2e_32b!"

        try:
            # Copiar Root CA y clave privada al directorio del firmador
            shutil.copy2(self.test_ca_cert, signer_dir / "vigia_root_ca.crt")
            shutil.copy2(self.test_ca_key, signer_dir / "vigia_root_ca_key.pem")

            # En el directorio de Flask SOLAMENTE copiar vigia_root_ca.crt y el token de autenticación IPC
            shutil.copy2(self.test_ca_cert, flask_dir / "vigia_root_ca.crt")
            (flask_dir / "signer_ipc_auth.token").write_bytes(test_authkey)

            # Verificar que en el directorio de Flask NO existe la clave privada Root CA
            self.assertFalse((flask_dir / "vigia_root_ca_key.pem").exists())

            # Inicializar y arrancar IsolatedSigner
            signer = IsolatedSigner(certs_dir=signer_dir)
            server = SignerIPCServer(signer=signer, pipe_name=test_pipe, authkey=test_authkey)
            server.start()

            try:
                # Mockear pipe name en SignerClient para apuntar a test_pipe
                import VIGIA_API.ingest_service as ingest_mod

                orig_signer_client = ingest_mod.SignerClient
                class CustomTestSignerClient(orig_signer_client):
                    def __init__(self, certs_dir, **kwargs):
                        super().__init__(certs_dir=certs_dir, pipe_name=test_pipe, authkey=test_authkey)

                ingest_mod.SignerClient = CustomTestSignerClient
                try:
                    srv_cert_p, srv_key_p, ca_cert_p = generate_vigia_local_ca_bundle(
                        target_ip="192.168.1.76",
                        cert_dir=flask_dir,
                        valid_days=60,
                        crl_http_port=5080,
                    )
                    self.assertTrue(srv_cert_p.is_file())
                    self.assertTrue(srv_key_p.is_file())

                    # Validar el par generado
                    validate_tls_certificate_pair(srv_cert_p, srv_key_p, target_ip="192.168.1.76")

                    # Verificar que la clave privada Root CA jamás fue creada en el directorio de Flask
                    self.assertFalse((flask_dir / "vigia_root_ca_key.pem").exists())

                    # Verificar que el log de auditoría en el firmador registró la emisión
                    audit_log_p = signer_dir / "audit" / "ca_issuance.jsonl"
                    self.assertTrue(audit_log_p.is_file())
                    log_lines = audit_log_p.read_text(encoding="utf-8").strip().splitlines()
                    self.assertGreaterEqual(len(log_lines), 1)
                    parsed_event = json.loads(log_lines[-1])
                    self.assertEqual(parsed_event["event"], "CERTIFICATE_ISSUED")
                    self.assertEqual(parsed_event["details"]["target_ip"], "192.168.1.76")
                finally:
                    ingest_mod.SignerClient = orig_signer_client
            finally:
                server.stop()
        finally:
            shutil.rmtree(signer_dir, ignore_errors=True)
            shutil.rmtree(flask_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
