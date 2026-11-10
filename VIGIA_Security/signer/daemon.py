"""
VIGIA_Security.signer.daemon
============================
Punto de entrada CLI para ejecutar el demonio IsolatedSigner en segundo plano (VIGIA-NET-04A).
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

from VIGIA_Security.signer.constants import DEFAULT_PIPE_NAME
from VIGIA_Security.signer.ipc_server import SignerIPCServer, get_or_create_ipc_token
from VIGIA_Security.signer.service import IsolatedSigner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [IsolatedSigner] %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Demonio de firma criptográfica aislada VIGIA (VIGIA-NET-04A)."
    )
    parser.add_argument(
        "--certs-dir",
        type=str,
        default="",
        help="Ruta al directorio de certificados donde reside vigia_root_ca.crt y vigia_root_ca_key.pem",
    )
    parser.add_argument(
        "--pipe-name",
        type=str,
        default=DEFAULT_PIPE_NAME,
        help="Nombre del Named Pipe en Windows",
    )
    args = parser.parse_args()

    if args.certs_dir:
        certs_dir = Path(args.certs_dir).resolve()
    else:
        # Resolver automáticamente respecto al repositorio
        script_dir = Path(__file__).resolve().parent
        certs_dir = (script_dir.parent.parent / "certs").resolve()

    logger.info("Iniciando IsolatedSigner con directorio de certificados: %s", certs_dir)

    try:
        signer = IsolatedSigner(certs_dir=certs_dir)
        token = get_or_create_ipc_token(certs_dir)
        server = SignerIPCServer(signer=signer, pipe_name=args.pipe_name, authkey=token)
        server.start()
    except Exception as exc:
        logger.error("Fallo crítico al iniciar IsolatedSigner: %s", exc)
        return 1

    def handle_exit(signum: int, frame: Any) -> None:
        logger.info("Señal de terminación recibida. Deteniendo IsolatedSigner...")
        server.stop()
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, handle_exit)
        signal.signal(signal.SIGTERM, handle_exit)
    except Exception:
        pass

    logger.info("IsolatedSigner en ejecución. Presione Ctrl+C para finalizar.")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        handle_exit(0, None)

    return 0


if __name__ == "__main__":
    sys.exit(main())
