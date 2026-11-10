"""
VIGIA_Vision.async_persistence.spool
====================================
Implementación de almacenamiento duradero en disco NVMe (NVME_SPOOL)
con formato binario atómico, verificación de integridad SHA-256 y
cuarentena de archivos corruptos.

Formato binario VGSP v1:
+-------------------+--------------------+--------------------+--------------------+
| Magic: "VGSP" (4B)| Version: 0x0001 (2B| L_hdr: uint32 (4B) | Header JSON (L_hdr)|
+-------------------+--------------------+--------------------+--------------------+
| L_jpg: uint32 (4B)| Raw JPEG (L_jpg B) | Trailer SHA-256 (32 Bytes binarios)     |
+-------------------+--------------------+--------------------+--------------------+
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import struct
import time
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import UUID, uuid4

from VIGIA_Vision.async_persistence.models import (
    PersistenceTaskDTO,
    compute_content_hash,
)

logger = logging.getLogger(__name__)

_SPOOL_MAGIC = b"VGSP"
_SPOOL_VERSION = 1
_MIN_SPOOL_LEN = 4 + 2 + 4 + 4 + 32  # 46 bytes mínimos


class SpoolError(Exception):
    """Error base del subsistema de spooling en disco."""


class SpoolCorruptionError(SpoolError):
    """El archivo de spool presenta corrupción de cabecera, truncamiento o fallo de SHA-256."""


class SpoolIOError(SpoolError):
    """Fallo de entrada/salida (disco lleno, permisos denegados)."""


class BinarySpoolStorage:
    """
    Gestiona la persistencia atómica en disco NVMe de tareas de persistencia asíncrona.
    """

    def __init__(self, spool_base_dir: Path) -> None:
        self._base_dir = Path(spool_base_dir).resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._corrupt_dir = self._base_dir / ".corrupt"
        self._corrupt_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @property
    def corrupt_dir(self) -> Path:
        return self._corrupt_dir

    def _get_camera_dir(self, codigo_camara: str) -> Path:
        safe_cam = "".join(c for c in codigo_camara if c.isalnum() or c in ("-", "_")).strip()
        cam_dir = self._base_dir / safe_cam
        cam_dir.mkdir(parents=True, exist_ok=True)
        return cam_dir

    def serialize_task(self, task: PersistenceTaskDTO) -> bytes:
        """Serializa la tarea en el formato binario autocontenido VGSP v1."""
        meta_dict = task.to_metadata_dict()
        hdr_json_bytes = json.dumps(meta_dict, ensure_ascii=False).encode("utf-8")
        raw_jpeg = task.raw_jpeg_bytes

        len_hdr = len(hdr_json_bytes)
        len_jpg = len(raw_jpeg)

        # Empaquetar cabecera fija: Magic (4s), Version (H = uint16), Len_Hdr (I = uint32)
        preamble = struct.pack(">4sHI", _SPOOL_MAGIC, _SPOOL_VERSION, len_hdr)
        jpeg_prefix = struct.pack(">I", len_jpg)

        payload_to_hash = preamble + hdr_json_bytes + jpeg_prefix + raw_jpeg
        trailer_sha256 = hashlib.sha256(payload_to_hash).digest()

        return payload_to_hash + trailer_sha256

    def deserialize_task(self, raw_data: bytes) -> PersistenceTaskDTO:
        """Deserializa y valida exhaustivamente un bloque binario VGSP v1."""
        if len(raw_data) < _MIN_SPOOL_LEN:
            raise SpoolCorruptionError(
                f"Archivo de spool truncado: longitud={len(raw_data)} < {_MIN_SPOOL_LEN}"
            )

        payload_to_hash = raw_data[:-32]
        expected_trailer = raw_data[-32:]
        actual_trailer = hashlib.sha256(payload_to_hash).digest()

        if expected_trailer != actual_trailer:
            raise SpoolCorruptionError(
                "Fallo de integridad: Trailer SHA-256 no coincide con el payload del archivo."
            )

        magic, version, len_hdr = struct.unpack_from(">4sHI", payload_to_hash, 0)
        if magic != _SPOOL_MAGIC:
            raise SpoolCorruptionError(f"Magic header inválido: {magic!r} != {_SPOOL_MAGIC!r}")
        if version != _SPOOL_VERSION:
            raise SpoolCorruptionError(f"Versión de spool no soportada: {version}")

        offset = 10
        if len(payload_to_hash) < offset + len_hdr + 4:
            raise SpoolCorruptionError("Archivo truncado en segmento de metadatos JSON.")

        hdr_bytes = payload_to_hash[offset : offset + len_hdr]
        try:
            meta_dict = json.loads(hdr_bytes.decode("utf-8"))
        except Exception as exc:
            raise SpoolCorruptionError(f"Metadatos JSON corruptos o no parseables: {exc}") from exc

        offset += len_hdr
        len_jpg = struct.unpack_from(">I", payload_to_hash, offset)[0]
        offset += 4

        raw_jpeg = payload_to_hash[offset : offset + len_jpg]
        if len(raw_jpeg) != len_jpg:
            raise SpoolCorruptionError(
                f"Longitud de imagen inconsistente: declarada={len_jpg}, extraída={len(raw_jpeg)}"
            )

        try:
            return PersistenceTaskDTO.from_metadata_dict(meta_dict, raw_jpeg)
        except Exception as exc:
            raise SpoolCorruptionError(f"Error al reconstruir PersistenceTaskDTO: {exc}") from exc

    def write_spool(self, task: PersistenceTaskDTO) -> Path:
        """
        Escribe atómicamente el archivo .spool en disco NVMe con fsync.
        Garantiza que ningún lector pueda observar archivos incompletos.
        """
        cam_dir = self._get_camera_dir(task.codigo_camara)
        final_filename = f"{task.camera_sequence:012d}_{task.task_id.hex}.spool"
        final_path = cam_dir / final_filename

        tmp_filename = f".{final_filename}.tmp.{uuid4().hex[:8]}"
        tmp_path = cam_dir / tmp_filename

        raw_bytes = self.serialize_task(task)

        try:
            with open(tmp_path, "xb") as fh:
                fh.write(raw_bytes)
                fh.flush()
                os.fsync(fh.fileno())

            # Renombrado atómico
            os.replace(tmp_path, final_path)
            return final_path
        except OSError as exc:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            raise SpoolIOError(f"Fallo al escribir spool en disco: {exc}") from exc

    def read_spool(self, spool_path: Path) -> PersistenceTaskDTO:
        """Lee y deserializa un archivo .spool existente."""
        resolved = spool_path.resolve()
        if not resolved.is_file():
            raise SpoolIOError(f"Archivo de spool inexistente: {resolved}")

        try:
            with open(resolved, "rb") as fh:
                raw_bytes = fh.read()
        except OSError as exc:
            raise SpoolIOError(f"Fallo al leer archivo de spool: {exc}") from exc

        return self.deserialize_task(raw_bytes)

    def quarantine_corrupt(self, spool_path: Path, reason: str = "checksum_mismatch") -> Path:
        """Mueve un archivo de spool corrupto al directorio de aislamiento .corrupt."""
        resolved = spool_path.resolve()
        safe_reason = "".join(c for c in reason if c.isalnum() or c in ("-", "_"))
        target_name = f"{resolved.name}.{safe_reason}_{int(time.time())}"
        target_path = self._corrupt_dir / target_name

        try:
            os.replace(resolved, target_path)
            logger.warning("Spool corrupto aislado en cuarentena: %s -> %s", resolved, target_path)
            return target_path
        except Exception as exc:
            logger.error("No se pudo aislar archivo corrupto %s: %exc", resolved, exc)
            return resolved

    def purge_spool(self, spool_path: Path) -> bool:
        """Elimina de forma segura un archivo .spool tras confirmarse su commit en PostgreSQL."""
        try:
            resolved = spool_path.resolve()
            if resolved.exists():
                resolved.unlink()
                return True
        except Exception as exc:
            logger.warning("No se pudo eliminar archivo spool procesado (%s): %s", spool_path, exc)
        return False

    def purge_stale_temps(self, max_age_seconds: float = 600.0) -> int:
        """Purga archivos .tmp con antigüedad mayor al umbral especificado."""
        purged = 0
        now = time.time()
        for root, _, files in os.walk(self._base_dir):
            for file in files:
                if file.startswith(".") and ".tmp." in file:
                    p = Path(root) / file
                    try:
                        mtime = p.stat().st_mtime
                        if (now - mtime) > max_age_seconds:
                            p.unlink()
                            purged += 1
                    except Exception:
                        pass
        return purged
