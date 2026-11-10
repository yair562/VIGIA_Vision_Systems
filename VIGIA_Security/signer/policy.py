"""
VIGIA_Security.signer.policy
============================
Motor de políticas de emisión criptográfica para IsolatedSigner (VIGIA-NET-04A).
Aplica el principio de menor privilegio y rechaza cualquier solicitud que no
cumpla estrictamente las restricciones de seguridad aprobadas.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Any, List, Optional, Set, Union
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa

from VIGIA_Security.signer.constants import (
    MAX_VALID_DAYS,
    RSA_MIN_KEY_SIZE,
    DEFAULT_LOCAL_HOSTNAME,
)

logger = logging.getLogger(__name__)


class PolicyViolationError(ValueError):
    """Excepción lanzada cuando una solicitud de firma viola la política de emisión autorizada."""
    pass


class SignerPolicyValidator:
    """Validador determinista de políticas de emisión para certificados de servidor VIGÍA."""

    ALLOWED_DNS_NAMES: Set[str] = {"localhost", DEFAULT_LOCAL_HOSTNAME}

    @classmethod
    def validate_target_ip(cls, target_ip: str) -> str:
        """
        Valida que la dirección IP objetivo sea una dirección privada RFC 1918 o loopback.
        Rechaza terminantemente IPs públicas, APIPA (169.254.0.0/16), multicast y 0.0.0.0.
        """
        if not target_ip or not isinstance(target_ip, str):
            raise PolicyViolationError("La dirección IP objetivo no puede estar vacía.")

        cleaned_ip = target_ip.strip()

        # Permitir nombres DNS locales autorizados como target_ip
        if cleaned_ip.lower() in cls.ALLOWED_DNS_NAMES:
            return cleaned_ip.lower()

        try:
            ip_obj = ipaddress.ip_address(cleaned_ip)
        except ValueError as err:
            raise PolicyViolationError(
                f"Dirección IP no válida o nombre de host no autorizado: '{cleaned_ip}'"
            ) from err

        if ip_obj.is_unspecified:
            raise PolicyViolationError("No se permite emitir certificados para '0.0.0.0' ni '::'.")

        if ip_obj.is_link_local:
            raise PolicyViolationError(
                f"Dirección de autoconfiguración APIPA/link-local no permitida: '{cleaned_ip}'."
            )

        if ip_obj.is_multicast:
            raise PolicyViolationError(f"Dirección multicast no permitida: '{cleaned_ip}'.")

        # Debe ser privada (RFC 1918) o loopback
        if not (ip_obj.is_private or ip_obj.is_loopback):
            raise PolicyViolationError(
                f"Violación de seguridad: No se autoriza la emisión de certificados para IPs públicas: '{cleaned_ip}'."
            )

        return str(ip_obj)

    @classmethod
    def validate_valid_days(cls, valid_days: int) -> int:
        """Valida que la vigencia solicitada no exceda el límite máximo de 90 días."""
        if not isinstance(valid_days, int) or valid_days < 1:
            raise PolicyViolationError("El periodo de validez debe ser un entero positivo (días >= 1).")
        if valid_days > MAX_VALID_DAYS:
            raise PolicyViolationError(
                f"La vigencia solicitada ({valid_days} días) excede el máximo autorizado ({MAX_VALID_DAYS} días)."
            )
        return valid_days

    @classmethod
    def validate_public_key(cls, public_key: Any) -> None:
        """Valida que la clave pública sea RSA con longitud mínima de 2048 bits."""
        if not isinstance(public_key, rsa.RSAPublicKey):
            raise PolicyViolationError("Solo se admiten claves públicas asimétricas RSA.")
        if public_key.key_size < RSA_MIN_KEY_SIZE:
            raise PolicyViolationError(
                f"Longitud de clave insuficiente ({public_key.key_size} bits). Mínimo requerido: {RSA_MIN_KEY_SIZE} bits."
            )

    @classmethod
    def validate_csr(cls, csr: x509.CertificateSigningRequest, target_ip: str) -> None:
        """
        Inspecciona exhaustivamente una solicitud de firma de certificado (CSR).
        Valida firma del CSR, clave pública, SAN solicitados y rechaza extensiones CA.
        """
        if not csr.is_signature_valid:
            raise PolicyViolationError("La firma criptográfica del CSR es inválida.")

        cls.validate_public_key(csr.public_key())
        validated_ip = cls.validate_target_ip(target_ip)

        # Inspeccionar extensiones solicitadas en el CSR
        for ext in csr.extensions:
            # Prohibir terminantemente que un CSR solicite BasicConstraints CA=True
            if ext.oid == x509.OID_BASIC_CONSTRAINTS:
                bc: x509.BasicConstraints = ext.value  # type: ignore
                if bc.ca:
                    raise PolicyViolationError(
                        "Violación de política X.509: Un CSR de servidor no puede solicitar BasicConstraints CA=True."
                    )

            # Prohibir facultades de firma de certificados en KeyUsage
            if ext.oid == x509.OID_KEY_USAGE:
                ku: x509.KeyUsage = ext.value  # type: ignore
                if ku.key_cert_sign or ku.crl_sign:
                    raise PolicyViolationError(
                        "Violación de política X.509: No se autoriza keyCertSign ni crlSign en certificados hoja."
                    )

            # Validar SAN si fue incluido en el CSR
            if ext.oid == x509.OID_SUBJECT_ALTERNATIVE_NAME:
                san_val: x509.SubjectAlternativeName = ext.value  # type: ignore
                for name in san_val:
                    if isinstance(name, x509.DNSName):
                        val = name.value.lower()
                        if val not in cls.ALLOWED_DNS_NAMES and val != validated_ip:
                            raise PolicyViolationError(
                                f"Nombre DNS no autorizado en SAN del CSR: '{val}'"
                            )
                    elif isinstance(name, x509.IPAddress):
                        ip_str = str(name.value)
                        cls.validate_target_ip(ip_str)

    @classmethod
    def build_authorized_san_entries(cls, target_ip: str) -> List[x509.GeneralName]:
        """
        Construye la lista determinista de Subject Alternative Names autorizados.
        Incluye siempre localhost, 127.0.0.1 y la IP LAN / host validada.
        """
        validated_ip = cls.validate_target_ip(target_ip)
        san_entries: List[x509.GeneralName] = [
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            x509.DNSName(DEFAULT_LOCAL_HOSTNAME),
        ]

        try:
            parsed_ip = ipaddress.ip_address(validated_ip)
            if str(parsed_ip) != "127.0.0.1":
                san_entries.append(x509.IPAddress(parsed_ip))
        except ValueError:
            if validated_ip.lower() not in ("localhost", DEFAULT_LOCAL_HOSTNAME):
                san_entries.append(x509.DNSName(validated_ip.lower()))

        return san_entries
