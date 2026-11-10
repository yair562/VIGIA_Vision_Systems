"""
VIGIA_Security.signer.constants
===============================
Constantes y configuraciones base para el subsistema IsolatedSigner (VIGIA-NET-04A).
"""

from pathlib import Path

# Nombre canónico del Named Pipe en Windows
DEFAULT_PIPE_NAME = r"\\.\pipe\vigia_ca_signer"

# Archivo de secreto efímero compartido para autenticación IPC
TOKEN_FILENAME = "signer_ipc_auth.token"

# Log de auditoría estructurado e inmutable
AUDIT_LOG_FILENAME = "ca_issuance.jsonl"

# Huella digital SHA-256 inmutable de la Root CA autorizada
AUTHORIZED_ROOT_CA_FINGERPRINT = (
    "E593B2D0B808BD8F8E97582ECDEBEAD29AEBC0F9F4BA9EF6ADB2D8E4362E4F4D"
)

# Límites de política
MAX_VALID_DAYS = 90
DEFAULT_VALID_DAYS = 90
MAX_REQUESTS_PER_MINUTE = 5
RATE_LIMIT_WINDOW_SECONDS = 60.0
DEFAULT_CRL_PORT = 5080
DEFAULT_LOCAL_HOSTNAME = "vigia.local"
RSA_MIN_KEY_SIZE = 2048

# =========================================================================
# Constantes de endurecimiento IPC y Named Pipes (VIGIA-NET-04A-R3)
# =========================================================================
PROTOCOL_VERSION = "2.0"
MAX_MESSAGE_BYTES = 65536  # Límite estricto de 64 KB por mensaje IPC
DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_READ_TIMEOUT = 5.0
DEFAULT_WRITE_TIMEOUT = 5.0
MAX_CONCURRENT_CONNECTIONS = 10
REPLAY_WINDOW_SECONDS = 300.0  # Ventana de 5 minutos para mitigación de repetición

# Service SID determinístico de VigiaSigner en Windows SCM
SERVICE_SID_VIGIA_SIGNER = "S-1-5-80-2989649446-3771946195-3416046217-2123186497-1198526073"

# Plantilla SDDL para Named Pipe:
# SY = SYSTEM (GA), BA = Administradores (GA), Service SID = Generic Read/Write, Client SID = Generic Read/Write
DEFAULT_PIPE_SDDL_TEMPLATE = (
    "D:(A;;GA;;;SY)(A;;GA;;;BA)"
    "(A;;GRGW;;;" + SERVICE_SID_VIGIA_SIGNER + ")"
    "(A;;GRGW;;;{CLIENT_SID})"
)

