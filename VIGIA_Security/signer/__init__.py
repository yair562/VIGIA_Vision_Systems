"""
VIGIA_Security.signer
=====================
Subsistema de firma criptográfica aislada (VIGIA-NET-04A).
"""

from VIGIA_Security.signer.constants import (
    DEFAULT_PIPE_NAME,
    AUTHORIZED_ROOT_CA_FINGERPRINT,
    MAX_VALID_DAYS,
)
from VIGIA_Security.signer.policy import SignerPolicyValidator, PolicyViolationError
from VIGIA_Security.signer.service import IsolatedSigner
from VIGIA_Security.signer.ipc_client import SignerClient, SignerUnavailableError

__all__ = [
    "DEFAULT_PIPE_NAME",
    "AUTHORIZED_ROOT_CA_FINGERPRINT",
    "MAX_VALID_DAYS",
    "SignerPolicyValidator",
    "PolicyViolationError",
    "IsolatedSigner",
    "SignerClient",
    "SignerUnavailableError",
]
