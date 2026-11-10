"""
VIGIA_Security.signer.service
=============================
Servicio de firma criptográfica aislada (VIGIA-NET-04A).
Mantiene en memoria protegida la clave privada de la Root CA, valida políticas
estrictas de emisión, aplica rate limiting y emite registros de auditoría estructurados.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from VIGIA_Security.signer.constants import (
    AUTHORIZED_ROOT_CA_FINGERPRINT,
    AUDIT_LOG_FILENAME,
    DEFAULT_CRL_PORT,
    DEFAULT_LOCAL_HOSTNAME,
    DEFAULT_VALID_DAYS,
    MAX_REQUESTS_PER_MINUTE,
    RATE_LIMIT_WINDOW_SECONDS,
)
from VIGIA_Security.signer.policy import SignerPolicyValidator, PolicyViolationError

logger = logging.getLogger(__name__)


class SignerIntegrityError(RuntimeError):
    """Lanzada cuando la integridad de la Root CA o sus archivos está comprometida."""
    pass


class IsolatedSigner:
    """
    Motor criptográfico de firma que opera como autoridad de emisión local de menor privilegio.
    Aísla 'vigia_root_ca_key.pem' y garantiza que solo se emitan certificados autorizados.
    """

    def __init__(
        self,
        certs_dir: Union[str, Path],
        ca_cert_name: str = "vigia_root_ca.crt",
        ca_key_name: str = "vigia_root_ca_key.pem",
        rate_limit_per_minute: int = MAX_REQUESTS_PER_MINUTE,
    ) -> None:
        self.certs_dir = Path(certs_dir).resolve()
        self.ca_cert_path = self.certs_dir / ca_cert_name
        self.ca_key_path = self.certs_dir / ca_key_name
        self.audit_dir = self.certs_dir / "audit"
        self.audit_log_path = self.audit_dir / AUDIT_LOG_FILENAME

        self.rate_limit = rate_limit_per_minute
        self._request_timestamps: List[float] = []
        self._lock = threading.Lock()

        self._last_audit_hash: str = "GENESIS"
        self._last_seq_num: int = 0

        self._ca_cert: Optional[x509.Certificate] = None
        self._ca_key: Optional[rsa.RSAPrivateKey] = None

        self._load_and_verify_root_ca()
        self._init_audit_chain()

    def _load_and_verify_root_ca(self) -> None:
        """Carga y valida estrictamente la Root CA autorizada y su clave privada."""
        if not self.ca_cert_path.is_file():
            raise FileNotFoundError(f"Certificado Root CA no encontrado en: {self.ca_cert_path}")
        if not self.ca_key_path.is_file():
            raise FileNotFoundError(f"Clave privada Root CA no encontrada en: {self.ca_key_path}")

        ca_bytes = self.ca_cert_path.read_bytes()
        self._ca_cert = x509.load_pem_x509_certificate(ca_bytes)

        # 1. Verificar huella SHA-256 autorizada
        actual_fp = self._ca_cert.fingerprint(hashes.SHA256()).hex().upper()
        if actual_fp != AUTHORIZED_ROOT_CA_FINGERPRINT:
            raise SignerIntegrityError(
                f"Violación de integridad: La huella de la Root CA ({actual_fp}) "
                f"no coincide con la huella maestra autorizada ({AUTHORIZED_ROOT_CA_FINGERPRINT})."
            )

        # 2. Cargar clave privada
        key_bytes = self.ca_key_path.read_bytes()
        loaded_key = serialization.load_pem_private_key(key_bytes, password=None)
        if not isinstance(loaded_key, rsa.RSAPrivateKey):
            raise SignerIntegrityError("La clave de la Root CA debe ser una clave asimétrica RSA.")
        self._ca_key = loaded_key

        # 3. Comprobar correspondencia matemática entre clave pública y privada
        if self._ca_key.public_key().public_numbers() != self._ca_cert.public_key().public_numbers():
            raise SignerIntegrityError("La clave privada no corresponde matemáticamente a vigia_root_ca.crt.")

        # 4. Asegurar existencia de directorio de auditoría
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "IsolatedSigner inicializado con éxito. Root CA huella: %s...%s",
            actual_fp[:8], actual_fp[-8:]
        )

    def _check_rate_limit(self) -> None:
        """Aplica rate limiting mediante ventana deslizante para mitigar saturación de CPU."""
        now = time.time()
        with self._lock:
            # Purgar timestamps anteriores a la ventana
            cutoff = now - RATE_LIMIT_WINDOW_SECONDS
            self._request_timestamps = [t for t in self._request_timestamps if t > cutoff]

            if len(self._request_timestamps) >= self.rate_limit:
                raise PolicyViolationError(
                    f"Límite de tasa excedido: Máximo {self.rate_limit} firmas por minuto. "
                    "Reintente en unos segundos."
                )
            self._request_timestamps.append(now)

    def _init_audit_chain(self) -> None:
        """Lee el último registro del log de auditoría para inicializar la cadena criptográfica."""
        if self.audit_log_path.is_file():
            try:
                with open(self.audit_log_path, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f if line.strip()]
                    if lines:
                        last_obj = json.loads(lines[-1])
                        self._last_audit_hash = last_obj.get("entry_hash") or hashlib.sha256(lines[-1].encode("utf-8")).hexdigest()
                        self._last_seq_num = int(last_obj.get("seq_num", len(lines)))
            except Exception as e:
                logger.warning("No fue posible leer la cabecera de auditoría previa: %s", e)

    def _append_audit_log(self, event_type: str, details: Dict[str, Any]) -> None:
        """
        Registra un evento de firma estructurado con encadenamiento criptográfico (Hash Chaining).
        Garantiza que cualquier modificación, eliminación o inserción altere la integridad verificable.
        """
        with self._lock:
            self._last_seq_num += 1
            entry = {
                "seq_num": self._last_seq_num,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "event": event_type,
                "details": details,
                "prev_hash": self._last_audit_hash,
            }
            canonical_json = json.dumps(entry, sort_keys=True, ensure_ascii=False)
            entry_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
            entry["entry_hash"] = entry_hash
            self._last_audit_hash = entry_hash

            try:
                with open(self.audit_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception as err:
                logger.error("Fallo al escribir en el log de auditoría criptográfica: %s", err)

    def sign_certificate(
        self,
        csr_pem: Union[str, bytes],
        target_ip: str,
        valid_days: int = DEFAULT_VALID_DAYS,
        crl_port: int = DEFAULT_CRL_PORT,
        client_identity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Valida la política, procesa un CSR y firma un certificado hoja de servidor (profundidad 1).
        Retorna un diccionario con 'cert_pem', 'fullchain_pem', 'ca_pem' y 'serial_hex'.
        """
        self._check_rate_limit()

        if isinstance(csr_pem, str):
            csr_bytes = csr_pem.encode("utf-8")
        else:
            csr_bytes = csr_pem

        csr = x509.load_pem_x509_csr(csr_bytes)

        # 1. Validación estricta de políticas
        SignerPolicyValidator.validate_csr(csr, target_ip=target_ip)
        effective_days = SignerPolicyValidator.validate_valid_days(valid_days)
        validated_ip = SignerPolicyValidator.validate_target_ip(target_ip)

        now = datetime.datetime.now(datetime.timezone.utc)
        not_before = now - datetime.timedelta(minutes=5)
        not_after = now + datetime.timedelta(days=effective_days)

        # 2. Construir Subject unificado
        srv_subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "MX"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "VIGIA Vision Systems"),
            x509.NameAttribute(NameOID.COMMON_NAME, f"VIGIA LAN Server ({validated_ip})"),
        ])

        # 3. Construir SAN autorizados
        san_entries = SignerPolicyValidator.build_authorized_san_entries(validated_ip)

        # 4. Construir extensiones CDP definitivas (conforme a VIGIA-NET-03E)
        # Excluye 127.0.0.1 para clientes de red para evitar fallos locales en el móvil
        cdp_uris = [
            x509.UniformResourceIdentifier(f"http://{validated_ip}:{crl_port}/api/v1/tls/ca.crl"),
            x509.UniformResourceIdentifier(f"http://{DEFAULT_LOCAL_HOSTNAME}:{crl_port}/api/v1/tls/ca.crl"),
        ]
        # Si el certificado es puramente local (127.0.0.1/localhost), sí se incluye 127.0.0.1
        if validated_ip in ("127.0.0.1", "localhost"):
            cdp_uris = [
                x509.UniformResourceIdentifier(f"http://127.0.0.1:{crl_port}/api/v1/tls/ca.crl")
            ]

        cdp_ext = x509.CRLDistributionPoints([
            x509.DistributionPoint(
                full_name=cdp_uris,
                relative_name=None,
                crl_issuer=None,
                reasons=None,
            )
        ])

        srv_pub = csr.public_key()
        srv_ski = x509.SubjectKeyIdentifier.from_public_key(srv_pub)
        ca_aki = x509.AuthorityKeyIdentifier.from_issuer_public_key(self._ca_key.public_key())
        serial_num = x509.random_serial_number()

        # 5. Ensamblar certificado hoja (Profundidad 1, CA=False)
        builder = (
            x509.CertificateBuilder()
            .subject_name(srv_subject)
            .issuer_name(self._ca_cert.subject)
            .public_key(srv_pub)
            .serial_number(serial_num)
            .not_valid_before(not_before)
            .not_valid_after(not_after)
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
        )

        signed_cert = builder.sign(self._ca_key, hashes.SHA256())

        cert_pem = signed_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
        ca_pem = self._ca_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
        fullchain_pem = f"{cert_pem.strip()}\n{ca_pem.strip()}\n"
        serial_hex = hex(serial_num)
        fingerprint_sha256 = signed_cert.fingerprint(hashes.SHA256()).hex().upper()

        # 6. Registrar en auditoría
        self._append_audit_log(
            event_type="CERTIFICATE_ISSUED",
            details={
                "client_identity": client_identity or "unknown",
                "serial_hex": serial_hex,
                "target_ip": validated_ip,
                "san": [str(s) for s in san_entries],
                "fingerprint_sha256": fingerprint_sha256,
                "valid_days": effective_days,
                "not_after": not_after.isoformat(),
            },
        )

        return {
            "ok": True,
            "cert_pem": cert_pem,
            "ca_pem": ca_pem,
            "fullchain_pem": fullchain_pem,
            "serial_hex": serial_hex,
            "fingerprint_sha256": fingerprint_sha256,
            "target_ip": validated_ip,
        }

    def sign_crl(
        self,
        crl_number: int,
        revoked_serials: Optional[List[Dict[str, Any]]] = None,
        valid_days: int = 7,
        client_identity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Firma una Lista de Revocación de Certificados (CRL) X.509 v2 con la Root CA."""
        self._check_rate_limit()

        now = datetime.datetime.now(datetime.timezone.utc)
        last_update = now - datetime.timedelta(minutes=5)
        next_update = now + datetime.timedelta(days=max(1, valid_days))

        builder = (
            x509.CertificateRevocationListBuilder()
            .issuer_name(self._ca_cert.subject)
            .last_update(last_update)
            .next_update(next_update)
        )

        ca_aki = x509.AuthorityKeyIdentifier.from_issuer_public_key(self._ca_key.public_key())
        builder = builder.add_extension(ca_aki, critical=False)
        builder = builder.add_extension(x509.CRLNumber(crl_number), critical=False)

        reason_mapping = {
            "unspecified": x509.ReasonFlags.unspecified,
            "key_compromise": x509.ReasonFlags.key_compromise,
            "ca_compromise": x509.ReasonFlags.ca_compromise,
            "affiliation_changed": x509.ReasonFlags.affiliation_changed,
            "superseded": x509.ReasonFlags.superseded,
            "cessation_of_operation": x509.ReasonFlags.cessation_of_operation,
        }

        if revoked_serials:
            for item in revoked_serials:
                raw_serial = item.get("serial_number")
                if isinstance(raw_serial, str):
                    s_int = int(raw_serial, 16) if raw_serial.startswith("0x") else int(raw_serial)
                else:
                    s_int = int(raw_serial)

                rev_builder = x509.RevokedCertificateBuilder().serial_number(s_int)
                rev_date_str = item.get("revocation_date")
                if rev_date_str:
                    rev_date = datetime.datetime.fromisoformat(rev_date_str)
                    if rev_date.tzinfo is None:
                        rev_date = rev_date.replace(tzinfo=datetime.timezone.utc)
                else:
                    rev_date = now

                rev_builder = rev_builder.revocation_date(rev_date)
                reason_code = str(item.get("reason", "unspecified")).lower()
                flag = reason_mapping.get(reason_code, x509.ReasonFlags.unspecified)
                rev_builder = rev_builder.add_extension(
                    x509.CRLReason(flag), critical=False
                )
                builder = builder.add_revoked_certificate(rev_builder.build())

        crl = builder.sign(self._ca_key, hashes.SHA256())
        crl_der = crl.public_bytes(serialization.Encoding.DER)
        crl_pem = crl.public_bytes(serialization.Encoding.PEM).decode("ascii")

        self._append_audit_log(
            event_type="CRL_ISSUED",
            details={
                "client_identity": client_identity or "unknown",
                "crl_number": crl_number,
                "revoked_count": len(revoked_serials or []),
                "next_update": next_update.isoformat(),
            },
        )

        return {
            "ok": True,
            "crl_der_bytes": crl_der,
            "crl_pem": crl_pem,
            "crl_number": crl_number,
            "next_update": next_update.isoformat(),
        }
