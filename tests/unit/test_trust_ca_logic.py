"""
Pruebas unitarias para VIGIA-TLS-02B: Aprovisionamiento y Verificación de Confianza TLS.

Verifica:
1. Cálculo y coincidencia de huella SHA-256 de certificados X.509.
2. Detección y rechazo de discrepancia de huella (fail-closed).
3. Detección de archivo de certificado inexistente.
4. Estructura JSON y campos requeridos del diagnóstico de verificación.
5. Detección de certificado ya instalado e idempotencia.
6. Aislamiento absoluto: las pruebas NO modifican Cert:\CurrentUser\Root del usuario.
7. Comprobación estricta de HTTPS contra certificados temporales/inválidos.
"""

import datetime
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
import unittest

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from scripts.check_https_strict import run_strict_check


class TestTrustCALogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="vigia_trust_ca_test_"))
        cls.repo_root = Path(__file__).resolve().parent.parent.parent
        cls.scripts_dir = cls.repo_root / "scripts"
        cls.trust_script = cls.scripts_dir / "trust_ca.ps1"

        # Generar un certificado de prueba efímero (NO es la CA real)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "Dummy Test CA for Unit Tests"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Org"),
        ])
        now = datetime.datetime.now(datetime.timezone.utc)
        cls.dummy_cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=10))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )
        cls.dummy_cert_path = cls.temp_dir / "dummy_test_ca.crt"
        cls.dummy_cert_path.write_bytes(cls.dummy_cert.public_bytes(serialization.Encoding.PEM))

        # Calcular huella SHA-256 exacta del cert de prueba
        cls.dummy_fp = hashlib.sha256(
            cls.dummy_cert.public_bytes(serialization.Encoding.DER)
        ).hexdigest().upper()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_dummy_cert_fingerprint_matches(self):
        """1. La huella SHA-256 DER calculada en Python coincide con la esperada."""
        self.assertEqual(len(self.dummy_fp), 64)
        raw_der = self.dummy_cert.public_bytes(serialization.Encoding.DER)
        calc_fp = hashlib.sha256(raw_der).hexdigest().upper()
        self.assertEqual(calc_fp, self.dummy_fp)

    def test_02_trust_ca_script_exists(self):
        """2. El script trust_ca.ps1 existe y es accesible."""
        self.assertTrue(self.trust_script.is_file(), f"No existe {self.trust_script}")

    def test_03_non_existent_file_returns_error(self):
        """3. trust_ca.ps1 falla limpiamente con código 1 si el archivo no existe."""
        fake_path = self.temp_dir / "non_existent_cert.crt"
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.trust_script),
            "-Action",
            "verify",
            "-CertPath",
            str(fake_path),
            "-Json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data.get("status"), "ERROR")
        self.assertFalse(data.get("file_exists"))

    def test_04_fingerprint_mismatch_aborts_immediately(self):
        """4. trust_ca.ps1 aborta inmediatamente si la huella SHA-256 no coincide."""
        wrong_fp = "00112233445566778899AABBCCDDEEFF00112233445566778899AABBCCDDEEFF"
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.trust_script),
            "-Action",
            "verify",
            "-CertPath",
            str(self.dummy_cert_path),
            "-ExpectedThumbprint",
            wrong_fp,
            "-Json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data.get("status"), "FINGERPRINT_MISMATCH")
        self.assertEqual(data.get("actual_fingerprint"), self.dummy_fp)
        self.assertEqual(data.get("expected_fingerprint"), wrong_fp)

    def test_05_verify_ca_with_matching_fingerprint(self):
        """5. verify diagnostica correctamente un certificado válido y con huella coincidente."""
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.trust_script),
            "-Action",
            "verify",
            "-CertPath",
            str(self.dummy_cert_path),
            "-ExpectedThumbprint",
            self.dummy_fp,
            "-Json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertTrue(data.get("fingerprint_matches"))
        self.assertEqual(data.get("sha256_fingerprint"), self.dummy_fp)
        self.assertIn("Dummy Test CA for Unit Tests", data.get("subject"))

    def test_06_real_root_ca_matches_authorized_fingerprint(self):
        """6. La Root CA real de VIGIA coincide exactamente con la huella autorizada."""
        real_ca_path = self.repo_root / "certs" / "vigia_root_ca.crt"
        self.assertTrue(real_ca_path.is_file())
        expected_authorized = "E593B2D0B808BD8F8E97582ECDEBEAD29AEBC0F9F4BA9EF6ADB2D8E4362E4F4D"
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.trust_script),
            "-Action",
            "verify",
            "-CertPath",
            str(real_ca_path),
            "-ExpectedThumbprint",
            expected_authorized,
            "-Json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertTrue(data.get("fingerprint_matches"))
        self.assertEqual(data.get("sha256_fingerprint"), expected_authorized)

    def test_07_strict_https_check_missing_ca_fails_cleanly(self):
        """7. check_https_strict reporta error si la CA no existe."""
        fake_ca = self.temp_dir / "nonexistent_root_ca.crt"
        report = run_strict_check(root_ca_path=fake_ca, port=5000)
        self.assertFalse(report["root_ca_exists"])
        self.assertFalse(report["overall_success"])
        self.assertIn("Root CA no encontrada", report["error"])

    def test_08_already_installed_idempotency_without_touching_real_store(self):
        """8. Si el certificado ya está en el almacén (mockeado), trust-ca reporta ALREADY_INSTALLED sin reimportar."""
        mock_store = self.temp_dir / "mock_store_installed"
        mock_store.mkdir(parents=True, exist_ok=True)
        # Colocar copia del cert de prueba en el almacén mockeado
        (mock_store / "dummy_in_store.crt").write_bytes(self.dummy_cert_path.read_bytes())

        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.trust_script),
            "-Action",
            "trust",
            "-CertPath",
            str(self.dummy_cert_path),
            "-ExpectedThumbprint",
            self.dummy_fp,
            "-StorePath",
            str(mock_store),
            "-Force",
            "-Json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"Error: {proc.stderr}")
        data = json.loads(proc.stdout)
        self.assertEqual(data.get("status"), "ALREADY_INSTALLED")
        self.assertEqual(data.get("sha256_fingerprint"), self.dummy_fp)

    def test_09_verify_reports_installed_status_when_in_mock_store(self):
        """9. verify detecta y reporta INSTALLED cuando el certificado está en el almacén."""
        mock_store = self.temp_dir / "mock_store_installed"
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.trust_script),
            "-Action",
            "verify",
            "-CertPath",
            str(self.dummy_cert_path),
            "-ExpectedThumbprint",
            self.dummy_fp,
            "-StorePath",
            str(mock_store),
            "-Json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data.get("status"), "INSTALLED")
        self.assertTrue(data.get("is_installed"))

    def test_10_invalid_or_corrupted_cert_file_fails_cleanly(self):
        """10. Un archivo de certificado corrupto produce error estructurado."""
        corrupt_file = self.temp_dir / "corrupt.crt"
        corrupt_file.write_bytes(b"NOT A VALID X509 CERTIFICATE DATA GARBAGE")
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.trust_script),
            "-Action",
            "verify",
            "-CertPath",
            str(corrupt_file),
            "-Json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data.get("status"), "ERROR")
        self.assertTrue(data.get("file_exists"))
        self.assertIn("Fallo al analizar", data.get("error", ""))

    def test_11_inaccessible_store_handled_gracefully(self):
        """11. Un almacén inexistente o inaccesible se maneja sin excepciones no controladas."""
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.trust_script),
            "-Action",
            "verify",
            "-CertPath",
            str(self.dummy_cert_path),
            "-ExpectedThumbprint",
            self.dummy_fp,
            "-StorePath",
            "Cert:\\CurrentUser\\NonExistentStore_Vigia_99999",
            "-Json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertFalse(data.get("is_installed"))
        self.assertEqual(data.get("status"), "NOT_INSTALLED")

    def test_12_untrust_when_not_installed_reports_cleanly(self):
        """12. untrust en un almacén donde la CA no está instalada reporta NOT_INSTALLED y sale con 0."""
        empty_store = self.temp_dir / "empty_store"
        empty_store.mkdir(parents=True, exist_ok=True)
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.trust_script),
            "-Action",
            "untrust",
            "-CertPath",
            str(self.dummy_cert_path),
            "-ExpectedThumbprint",
            self.dummy_fp,
            "-StorePath",
            str(empty_store),
            "-Json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data.get("status"), "NOT_INSTALLED")
        self.assertIn("No hay nada que revertir", data.get("message", ""))

    def test_13_untrust_removes_exact_cert_from_mock_store(self):
        """13. untrust elimina estrictamente el certificado con la huella SHA-256 autorizada del almacén."""
        mock_store = self.temp_dir / "store_for_untrust"
        mock_store.mkdir(parents=True, exist_ok=True)
        target_file = mock_store / "dummy_ca_installed.crt"
        target_file.write_bytes(self.dummy_cert_path.read_bytes())
        self.assertTrue(target_file.exists())

        env = dict(os.environ)
        env["VIGIA_ALLOW_IN_MEMORY"] = "1"

        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.trust_script),
            "-Action",
            "untrust",
            "-CertPath",
            str(self.dummy_cert_path),
            "-ExpectedThumbprint",
            self.dummy_fp,
            "-StorePath",
            str(mock_store),
            "-Json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, f"Error: {proc.stderr}")
        data = json.loads(proc.stdout)
        self.assertEqual(data.get("status"), "SUCCESS")
        self.assertFalse(target_file.exists(), "El certificado no fue eliminado del almacén mockeado")

    def test_14_untrust_never_removes_by_subject_matching_only_sha256(self):
        """14. untrust NUNCA elimina certificados por coincidencia de Subject; solo por huella exacta."""
        mock_store = self.temp_dir / "store_for_subject_safety"
        mock_store.mkdir(parents=True, exist_ok=True)

        # Generar un certificado de terceros con 'VIGIA' en el Subject pero distinta clave/huella
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "VIGIA Third Party Vendor CA"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "VIGIA Partner"),
        ])
        now = datetime.datetime.now(datetime.timezone.utc)
        other_cert = (
            x509.CertificateBuilder()
            .subject_name(other_subject)
            .issuer_name(other_subject)
            .public_key(other_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=5))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(other_key, hashes.SHA256())
        )
        other_cert_file = mock_store / "other_vigia_vendor.crt"
        other_cert_file.write_bytes(other_cert.public_bytes(serialization.Encoding.PEM))

        # Colocar también el cert objetivo
        target_file = mock_store / "dummy_ca.crt"
        target_file.write_bytes(self.dummy_cert_path.read_bytes())

        env = dict(os.environ)
        env["VIGIA_ALLOW_IN_MEMORY"] = "1"

        # Revertir dummy cert
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.trust_script),
            "-Action",
            "untrust",
            "-CertPath",
            str(self.dummy_cert_path),
            "-ExpectedThumbprint",
            self.dummy_fp,
            "-StorePath",
            str(mock_store),
            "-Json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data.get("status"), "SUCCESS")

        # Verificar que el target fue eliminado, pero el certificado de terceros sigue intacto
        self.assertFalse(target_file.exists())
        self.assertTrue(other_cert_file.exists(), "El certificado de terceros con 'VIGIA' en Subject fue erróneamente eliminado!")

    def test_15_force_never_bypasses_fingerprint_check(self):
        """15. El parámetro -Force NUNCA permite omitir la validación de la huella SHA-256 autorizada."""
        wrong_fp = "DEADBEEF00112233445566778899AABBCCDDEEFF00112233445566778899AABB"
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.trust_script),
            "-Action",
            "trust",
            "-CertPath",
            str(self.dummy_cert_path),
            "-ExpectedThumbprint",
            wrong_fp,
            "-Force",
            "-Json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data.get("status"), "FINGERPRINT_MISMATCH")

    def test_16_strict_check_reports_modalidad_a_and_b(self):
        """16. check_https_strict reporta estructuradamente Modalidad A y Modalidad B."""
        real_ca_path = self.repo_root / "certs" / "vigia_root_ca.crt"
        report = run_strict_check(root_ca_path=real_ca_path, port=5000)
        self.assertIn("modalidad_a_pki_targets", report)
        self.assertIn("modalidad_b_os_trust", report)
        self.assertIn("modalidad_a_passed", report)
        self.assertIn("modalidad_b_trusted", report)
        # Modalidad A pasa porque la PKI interna está activa
        self.assertTrue(report["modalidad_a_passed"])
        # Modalidad B reporta el estado booleano de confianza del almacén nativo de Windows
        self.assertIsInstance(report["modalidad_b_trusted"], bool)

    def test_17_force_does_not_bypass_interactive_confirmation_on_real_store(self):
        """17. -Force NUNCA omite la confirmación interactiva en Cert:\\CurrentUser\\Root; cancela si no se introduce CONFIRMAR."""
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.trust_script),
            "-Action",
            "trust",
            "-CertPath",
            str(self.dummy_cert_path),
            "-ExpectedThumbprint",
            self.dummy_fp,
            "-StorePath",
            "Cert:\\CurrentUser\\Root",
            "-Force",
            "-Json",
        ]
        # Enviar entrada vacía en stdin para simular que no se introduce la palabra requerida
        proc = subprocess.run(cmd, input="", capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data.get("status"), "CANCELLED")
        self.assertIn("cancelada por el usuario", data.get("message", ""))

    def test_18_json_does_not_bypass_interactive_confirmation_on_real_store(self):
        """18. -Json NUNCA habilita instalaciones desatendidas en Cert:\\CurrentUser\\Root."""
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.trust_script),
            "-Action",
            "trust",
            "-CertPath",
            str(self.dummy_cert_path),
            "-ExpectedThumbprint",
            self.dummy_fp,
            "-StorePath",
            "Cert:\\CurrentUser\\Root",
            "-Json",
        ]
        proc = subprocess.run(cmd, input="", capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data.get("status"), "CANCELLED")

    def test_19_in_memory_env_cannot_bypass_confirmation_on_real_store(self):
        """19. VIGIA_ALLOW_IN_MEMORY=1 NO permite bypass en Cert:\\CurrentUser\\Root (solo en mocks aislados)."""
        env = dict(os.environ)
        env["VIGIA_ALLOW_IN_MEMORY"] = "1"
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.trust_script),
            "-Action",
            "trust",
            "-CertPath",
            str(self.dummy_cert_path),
            "-ExpectedThumbprint",
            self.dummy_fp,
            "-StorePath",
            "Cert:\\CurrentUser\\Root",
            "-Force",
            "-Json",
        ]
        proc = subprocess.run(cmd, input="", capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data.get("status"), "CANCELLED")

    def test_20_forbidden_local_machine_store_rejected(self):
        """20. Intentar operar sobre Cert:\\LocalMachine\\Root es denegado de forma inmediata y segura."""
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.trust_script),
            "-Action",
            "trust",
            "-CertPath",
            str(self.dummy_cert_path),
            "-ExpectedThumbprint",
            self.dummy_fp,
            "-StorePath",
            "Cert:\\LocalMachine\\Root",
            "-Json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data.get("status"), "FORBIDDEN_STORE")
        self.assertIn("LocalMachine", data.get("error", ""))

    def test_21_incorrect_confirmation_word_cancels_operation(self):
        """21. Escribir una palabra distinta a 'CONFIRMAR' (ej. 'si', 'y', 'ok') cancela la operación."""
        for wrong_input in ["si", "y", "yes", "OK", "confirmar_incorrecto", "1"]:
            cmd = [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.trust_script),
                "-Action",
                "trust",
                "-CertPath",
                str(self.dummy_cert_path),
                "-ExpectedThumbprint",
                self.dummy_fp,
                "-StorePath",
                "Cert:\\CurrentUser\\Root",
                "-Json",
            ]
            proc = subprocess.run(cmd, input=wrong_input, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            json_start = proc.stdout.find("{")
            self.assertGreaterEqual(json_start, 0, f"No se encontró JSON en stdout: {proc.stdout}")
            data = json.loads(proc.stdout[json_start:])
            self.assertEqual(data.get("status"), "CANCELLED", f"Fallo con input: {wrong_input}")




if __name__ == "__main__":
    unittest.main()
