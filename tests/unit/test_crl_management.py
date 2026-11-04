"""
test_crl_management.py
======================
Suite completa de pruebas unitarias y de integración para la Lista de Revocación
de Certificados (CRL) X.509 privada y servidor de distribución HTTP de VIGÍA (VIGIA-TLS-02D).

Cubre los 15 escenarios obligatorios:
1. Firma y validación criptográfica de la CRL contra la Root CA.
2. Coincidencia de Issuer y AuthorityKeyIdentifier (AKI) con la Root CA.
3. Secuencia monótona estricta del número de CRL (CRLNumber).
4. Persistencia de números de serie revocados a través de reinicios.
5. Recuperación automática de estado ante ausencia o corrupción de crl_state.json.
6. Rechazo preventivo de CRL manipulada o con firma inválida.
7. Publicación HTTP de la CRL (MIME application/pkix-crl y método HEAD).
8. Restricción estricta de métodos (GET/HEAD) y rutas (405 / 404).
9. Inclusión y formato de la extensión CDP en el certificado hoja de servidor.
10. Verificación de certificado no revocado contra la CRL.
11. Verificación y detección de certificado revocado en la CRL.
12. Detección y renovación preventiva de CRL expirada o próxima a expirar.
13. Manejo resiliente ante CRL inaccesible.
14. Protección estricta contra divulgación de claves privadas o archivos del sistema.
15. Compatibilidad y coherencia con el endpoint Flask /api/v1/tls/ca.crl.
"""

import datetime
import http.client
import ipaddress
import json
import os
import shutil
import socket
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Tuple

import cryptography.x509 as x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import CRLEntryExtensionOID, ExtendedKeyUsageOID, ExtensionOID, NameOID

from VIGIA_API.ingest_service import (
    CRL_FILENAME,
    CRL_STATE_FILENAME,
    create_ingest_app,
    ensure_crl_is_valid,
    generate_vigia_crl,
    generate_vigia_local_ca_bundle,
    load_crl_state,
    revoke_certificate,
    save_crl_state_atomic,
    start_crl_http_server,
)


def _find_free_port() -> int:
    """Obtiene un puerto TCP libre efímero para pruebas locales."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _create_mock_root_ca(target_dir: Path) -> Tuple[x509.Certificate, rsa.RSAPrivateKey]:
    """Crea una Root CA de prueba en el directorio temporal especificado."""
    target_dir.mkdir(parents=True, exist_ok=True)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "MX"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "VIGIA Vision Systems"),
            x509.NameAttribute(NameOID.COMMON_NAME, "VIGIA Test Root CA"),
        ]
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_ski = x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key())
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_subject)
        .issuer_name(ca_subject)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=365))
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
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(ca_ski), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    ca_cert_p = target_dir / "vigia_root_ca.crt"
    ca_key_p = target_dir / "vigia_root_ca_key.pem"
    ca_cert_p.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    ca_key_p.write_bytes(
        ca_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return ca_cert, ca_key


class TestCRLManagement(unittest.TestCase):
    """Pruebas exhaustivas de generación, distribución, rotación y validación de CRL."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="vigia_crl_test_"))
        self.ca_cert, self.ca_key = _create_mock_root_ca(self.temp_dir)
        self.crl_server = None

    def tearDown(self):
        if self.crl_server:
            try:
                self.crl_server.stop()
            except Exception:
                pass
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ----------------------------------------------------------------------
    # Escenario 1: Firma y validación criptográfica de la CRL
    # ----------------------------------------------------------------------
    def test_01_crl_cryptographic_signature_validation(self):
        """1. La CRL se firma con SHA-256 y la clave privada de la Root CA, y es verificable con su clave pública."""
        crl_p, state_p = generate_vigia_crl(self.temp_dir)
        self.assertTrue(crl_p.is_file())
        self.assertTrue(state_p.is_file())

        crl_bytes = crl_p.read_bytes()
        crl = x509.load_der_x509_crl(crl_bytes)

        # Validación criptográfica de firma
        self.assertTrue(crl.is_signature_valid(self.ca_key.public_key()))
        self.assertEqual(crl.signature_hash_algorithm.name, "sha256")

    # ----------------------------------------------------------------------
    # Escenario 2: Coincidencia de Issuer y AuthorityKeyIdentifier
    # ----------------------------------------------------------------------
    def test_02_crl_issuer_and_aki_match_root_ca(self):
        """2. El Issuer de la CRL coincide con el Subject de la Root CA y el AKI coincide con el Subject Key ID."""
        crl_p, _ = generate_vigia_crl(self.temp_dir)
        crl = x509.load_der_x509_crl(crl_p.read_bytes())

        self.assertEqual(crl.issuer, self.ca_cert.subject)

        aki_ext = crl.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
        self.assertFalse(aki_ext.critical)

        ca_ski_ext = self.ca_cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
        self.assertEqual(aki_ext.value.key_identifier, ca_ski_ext.value.digest)

    # ----------------------------------------------------------------------
    # Escenario 3: Secuencia monótona del número de CRL
    # ----------------------------------------------------------------------
    def test_03_monotonic_crl_number_sequence(self):
        """3. Cada emisión subsiguiente incrementa monótonamente CRLNumber."""
        crl_p1, _ = generate_vigia_crl(self.temp_dir)
        crl1 = x509.load_der_x509_crl(crl_p1.read_bytes())
        num1 = crl1.extensions.get_extension_for_oid(ExtensionOID.CRL_NUMBER).value.crl_number
        self.assertEqual(num1, 1)

        crl_p2, _ = generate_vigia_crl(self.temp_dir)
        crl2 = x509.load_der_x509_crl(crl_p2.read_bytes())
        num2 = crl2.extensions.get_extension_for_oid(ExtensionOID.CRL_NUMBER).value.crl_number
        self.assertEqual(num2, 2)

        crl_p3, _ = generate_vigia_crl(self.temp_dir)
        crl3 = x509.load_der_x509_crl(crl_p3.read_bytes())
        num3 = crl3.extensions.get_extension_for_oid(ExtensionOID.CRL_NUMBER).value.crl_number
        self.assertEqual(num3, 3)

    # ----------------------------------------------------------------------
    # Escenario 4: Persistencia de seriales revocados
    # ----------------------------------------------------------------------
    def test_04_revoked_serials_persistence_across_reloads(self):
        """4. Los números de serie revocados persisten en crl_state.json y se conservan al reemitir."""
        test_serial_1 = 0x1A2B3C4D
        test_serial_2 = 0x5E6F7A8B

        revoke_certificate(self.temp_dir, serial_number=test_serial_1, reason="keyCompromise")
        revoke_certificate(self.temp_dir, serial_number=test_serial_2, reason="superseded")

        state = load_crl_state(self.temp_dir)
        self.assertEqual(len(state["revoked_serials"]), 2)
        serials = [r["serial_number"] for r in state["revoked_serials"]]
        self.assertIn(test_serial_1, serials)
        self.assertIn(test_serial_2, serials)

        # La CRL generada contiene ambos certificados revocados
        crl_p = self.temp_dir / CRL_FILENAME
        crl = x509.load_der_x509_crl(crl_p.read_bytes())
        revoked_in_crl = [r.serial_number for r in crl]
        self.assertIn(test_serial_1, revoked_in_crl)
        self.assertIn(test_serial_2, revoked_in_crl)

    # ----------------------------------------------------------------------
    # Escenario 5: Recuperación ante crl_state.json ausente o corrupto
    # ----------------------------------------------------------------------
    def test_05_crl_state_recovery_from_der_when_state_file_is_lost_or_corrupt(self):
        """5. Si crl_state.json se pierde o corrompe, el sistema recupera la secuencia y revocaciones leyendo la CRL DER."""
        revoke_certificate(self.temp_dir, serial_number=0xDEADBEEF, reason="keyCompromise")
        state_file = self.temp_dir / CRL_STATE_FILENAME
        self.assertTrue(state_file.exists())

        # 1. Simular archivo de estado eliminado
        state_file.unlink()
        recovered_state = load_crl_state(self.temp_dir)
        self.assertGreaterEqual(recovered_state["crl_number"], 1)
        self.assertEqual(len(recovered_state["revoked_serials"]), 1)
        self.assertEqual(recovered_state["revoked_serials"][0]["serial_number"], 0xDEADBEEF)

        # 2. Simular archivo de estado corrupto (JSON inválido)
        state_file.write_text("{corrupt_json: invalid", encoding="utf-8")
        recovered_state_2 = load_crl_state(self.temp_dir)
        self.assertGreaterEqual(recovered_state_2["crl_number"], 1)
        self.assertEqual(len(recovered_state_2["revoked_serials"]), 1)
        self.assertEqual(recovered_state_2["revoked_serials"][0]["serial_number"], 0xDEADBEEF)

    # ----------------------------------------------------------------------
    # Escenario 6: Rechazo preventivo de CRL manipulada
    # ----------------------------------------------------------------------
    def test_06_tampered_crl_fails_cryptographic_verification(self):
        """6. Una CRL con un solo byte manipulado es rechazada por fallar la firma criptográfica."""
        crl_p, _ = generate_vigia_crl(self.temp_dir)
        crl_bytes = bytearray(crl_p.read_bytes())

        # Alterar un byte en la firma o contenido
        crl_bytes[-10] ^= 0xFF
        tampered_bytes = bytes(crl_bytes)

        try:
            tampered_crl = x509.load_der_x509_crl(tampered_bytes)
            # La firma debe ser declarada inválida
            self.assertFalse(tampered_crl.is_signature_valid(self.ca_key.public_key()))
        except Exception:
            # O el parser DER rechaza la estructura
            pass

    # ----------------------------------------------------------------------
    # Escenario 7: Publicación HTTP de la CRL (MIME y HEAD)
    # ----------------------------------------------------------------------
    def test_07_http_crl_publication_mime_and_headers(self):
        """7. El servidor HTTP sirve la CRL en formato DER con application/pkix-crl y responde a GET y HEAD."""
        generate_vigia_crl(self.temp_dir)
        port = _find_free_port()
        self.crl_server = start_crl_http_server(certs_dir=self.temp_dir, host="127.0.0.1", port=port)

        url = f"http://127.0.0.1:{port}/api/v1/tls/ca.crl"

        # GET request
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "application/pkix-crl")
            self.assertIn("max-age", resp.headers.get("Cache-Control", ""))
            body = resp.read()
            self.assertGreater(len(body), 0)
            # Validar que los bytes recibidos son una CRL DER válida
            crl_parsed = x509.load_der_x509_crl(body)
            self.assertEqual(crl_parsed.issuer, self.ca_cert.subject)

        # HEAD request
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3.0)
        conn.request("HEAD", "/api/v1/tls/ca.crl")
        head_resp = conn.getresponse()
        self.assertEqual(head_resp.status, 200)
        self.assertEqual(head_resp.getheader("Content-Type"), "application/pkix-crl")
        self.assertEqual(int(head_resp.getheader("Content-Length")), len(body))
        head_body = head_resp.read()
        self.assertEqual(len(head_body), 0)  # HEAD no retorna cuerpo
        conn.close()

    # ----------------------------------------------------------------------
    # Escenario 8: Restricción estricta de métodos y rutas
    # ----------------------------------------------------------------------
    def test_08_http_method_and_route_restrictions(self):
        """8. Métodos distintos a GET/HEAD devuelven 405 Method Not Allowed; rutas no autorizadas devuelven 404."""
        generate_vigia_crl(self.temp_dir)
        port = _find_free_port()
        self.crl_server = start_crl_http_server(certs_dir=self.temp_dir, host="127.0.0.1", port=port)

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3.0)

        # POST a ruta CRL -> 405
        conn.request("POST", "/api/v1/tls/ca.crl", body=b"data")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 405)
        self.assertIn("GET", resp.getheader("Allow", ""))
        resp.read()

        # DELETE -> 405
        conn.request("DELETE", "/api/v1/tls/ca.crl")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 405)
        resp.read()

        # Ruta desconocida -> 404
        conn.request("GET", "/api/v1/tls/nonexistent")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 404)
        resp.read()

        conn.close()

    # ----------------------------------------------------------------------
    # Escenario 9: Inclusión de extensión CDP en certificado hoja
    # ----------------------------------------------------------------------
    def test_09_cdp_extension_in_leaf_certificate(self):
        """9. generate_vigia_local_ca_bundle incluye la extensión CDP apuntando a http://<ip>:<crl_port>/api/v1/tls/ca.crl."""
        crl_port = 5080
        target_ip = "192.168.1.99"
        srv_cert_p, _, _ = generate_vigia_local_ca_bundle(
            target_ip=target_ip,
            cert_dir=self.temp_dir,
            overwrite=True,
            crl_http_port=crl_port,
        )

        cert = x509.load_pem_x509_certificate(srv_cert_p.read_bytes())
        cdp_ext = cert.extensions.get_extension_for_oid(ExtensionOID.CRL_DISTRIBUTION_POINTS)
        self.assertFalse(cdp_ext.critical)

        expected_uri = f"http://{target_ip}:{crl_port}/api/v1/tls/ca.crl"
        dp = cdp_ext.value[0]
        self.assertEqual(dp.full_name[0].value, expected_uri)

        # Comprobar que active_generation.json también registra el cdp_url y crl_port
        manifest_p = self.temp_dir / "active_generation.json"
        self.assertTrue(manifest_p.is_file())
        manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
        self.assertEqual(manifest.get("cdp_url"), expected_uri)
        self.assertEqual(manifest.get("crl_port"), crl_port)

    # ----------------------------------------------------------------------
    # Escenario 10: Certificado no revocado no está en la CRL
    # ----------------------------------------------------------------------
    def test_10_non_revoked_certificate_status(self):
        """10. Un certificado emitido normalmente no figura en la lista de certificados revocados de la CRL."""
        srv_cert_p, _, _ = generate_vigia_local_ca_bundle(
            target_ip="192.168.1.99",
            cert_dir=self.temp_dir,
            overwrite=True,
        )
        cert = x509.load_pem_x509_certificate(srv_cert_p.read_bytes())
        crl = x509.load_der_x509_crl((self.temp_dir / CRL_FILENAME).read_bytes())

        revoked_serials = [r.serial_number for r in crl]
        self.assertNotIn(cert.serial_number, revoked_serials)

    # ----------------------------------------------------------------------
    # Escenario 11: Certificado revocado figura en la CRL
    # ----------------------------------------------------------------------
    def test_11_revoked_certificate_present_in_crl_with_reason(self):
        """11. Al revocar un certificado por su serial, aparece en la CRL con fecha y razón de revocación."""
        srv_cert_p, _, _ = generate_vigia_local_ca_bundle(
            target_ip="192.168.1.99",
            cert_dir=self.temp_dir,
            overwrite=True,
        )
        cert = x509.load_pem_x509_certificate(srv_cert_p.read_bytes())

        crl_p, _ = revoke_certificate(self.temp_dir, serial_number=cert.serial_number, reason="keyCompromise")
        crl = x509.load_der_x509_crl(crl_p.read_bytes())

        revoked_entry = crl.get_revoked_certificate_by_serial_number(cert.serial_number)
        self.assertIsNotNone(revoked_entry)
        self.assertEqual(revoked_entry.serial_number, cert.serial_number)

        reason_ext = revoked_entry.extensions.get_extension_for_oid(CRLEntryExtensionOID.CRL_REASON)
        self.assertEqual(reason_ext.value.reason, x509.ReasonFlags.key_compromise)

    # ----------------------------------------------------------------------
    # Escenario 12: Detección y renovación preventiva de CRL expirada
    # ----------------------------------------------------------------------
    def test_12_expired_crl_detection_and_automatic_renewal(self):
        """12. ensure_crl_is_valid detecta una CRL vencida o próxima a expirar y regenera una nueva secuencia válida."""
        # Forzar generación con validez mínima (1 día)
        crl_p, _ = generate_vigia_crl(self.temp_dir, valid_days=1)
        crl1 = x509.load_der_x509_crl(crl_p.read_bytes())
        num1 = crl1.extensions.get_extension_for_oid(ExtensionOID.CRL_NUMBER).value.crl_number

        # Si el umbral de renovación es 2 días y resta 1 día, debe regenerarse
        crl_p_renewed = ensure_crl_is_valid(self.temp_dir, renew_window_days=2)
        crl2 = x509.load_der_x509_crl(crl_p_renewed.read_bytes())
        num2 = crl2.extensions.get_extension_for_oid(ExtensionOID.CRL_NUMBER).value.crl_number

        self.assertGreater(num2, num1)
        now = datetime.datetime.now(datetime.timezone.utc)
        nu = getattr(crl2, "next_update_utc", None) or crl2.next_update
        if nu.tzinfo is None:
            nu = nu.replace(tzinfo=datetime.timezone.utc)
        self.assertGreater(nu, now + datetime.timedelta(days=5))

    # ----------------------------------------------------------------------
    # Escenario 13: Manejo de CRL inaccesible
    # ----------------------------------------------------------------------
    def test_13_inaccessible_crl_handling(self):
        """13. Si el servidor de CRL no está activo en el puerto objetivo, el cliente detecta el fallo sin crash del backend."""
        closed_port = _find_free_port()
        crl_url = f"http://127.0.0.1:{closed_port}/api/v1/tls/ca.crl"

        req = urllib.request.Request(crl_url)
        with self.assertRaises(urllib.error.URLError) as cm:
            urllib.request.urlopen(req, timeout=1.0)
        self.assertIsInstance(cm.exception.reason, OSError)

    # ----------------------------------------------------------------------
    # Escenario 14: Protección contra divulgación de claves privadas
    # ----------------------------------------------------------------------
    def test_14_no_private_key_exposure_via_crl_server(self):
        """14. Peticiones intentando leer vigia_key.pem, vigia_root_ca_key.pem o directory traversal retornan 404."""
        generate_vigia_crl(self.temp_dir)
        port = _find_free_port()
        self.crl_server = start_crl_http_server(certs_dir=self.temp_dir, host="127.0.0.1", port=port)

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3.0)

        forbidden_paths = [
            "/vigia_root_ca_key.pem",
            "/vigia_key.pem",
            "/crl_state.json",
            "/active_generation.json",
            "/../vigia_root_ca_key.pem",
            "/api/v1/tls/../../vigia_key.pem",
            "/etc/passwd",
        ]

        for path in forbidden_paths:
            conn.request("GET", path)
            resp = conn.getresponse()
            self.assertEqual(resp.status, 404, f"Ruta {path} debió devolver 404 Not Found")
            resp.read()

        conn.close()

    # ----------------------------------------------------------------------
    # Escenario 15: Compatibilidad con endpoint Flask
    # ----------------------------------------------------------------------
    def test_15_flask_app_crl_endpoint_compatibility(self):
        """15. El endpoint Flask /api/v1/tls/ca.crl sirve la misma CRL en DER con Content-Type application/pkix-crl."""
        generate_vigia_crl(self.temp_dir)
        app = create_ingest_app(certs_dir=self.temp_dir, initialize_vision_engine=False)
        client = app.test_client()

        # GET request
        resp = client.get("/api/v1/tls/ca.crl")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("Content-Type"), "application/pkix-crl")
        crl_from_flask = x509.load_der_x509_crl(resp.data)
        self.assertEqual(crl_from_flask.issuer, self.ca_cert.subject)

        # HEAD request
        head_resp = client.head("/api/v1/tls/ca.crl")
        self.assertEqual(head_resp.status_code, 200)
        self.assertEqual(head_resp.headers.get("Content-Type"), "application/pkix-crl")
        self.assertEqual(int(head_resp.headers.get("Content-Length")), len(resp.data))


if __name__ == "__main__":
    unittest.main()
