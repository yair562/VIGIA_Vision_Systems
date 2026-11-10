"""
VIGIA_Vision.async_persistence.evidence_writer
==============================================
Escritura atómica de evidencias fotográficas en almacenamiento NVMe
con soporte para sistemas de archivos NTFS (Windows) y POSIX.

Implementa:
- Escritura en dos fases (.tmp -> flush() -> fsync() -> os.replace()).
- Mitigación de contención de descriptores NTFS (safe_replace_ntfs).
- Compensación inmediata y eliminación de huérfanos ante fallos parciales o SQL.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import List, Optional, Sequence, Tuple
from uuid import uuid4

import cv2
import numpy as np

from VIGIA_Vision.async_persistence.models import PersistenceTaskDTO
from VIGIA_Vision.detection.roi_and_preprocess import validate_bgr_frame
from VIGIA_Vision.runtime.evidence_storage import render_annotated_frame

logger = logging.getLogger(__name__)


class EvidenceWriteError(Exception):
    """Error al codificar o escribir evidencias fotográficas en disco."""


def safe_replace_ntfs(src: Path, dst: Path, max_attempts: int = 3) -> None:
    """
    Ejecuta os.replace con micro-reintentos exponenciales para tolerar
    bloqueos transitorios por Windows Defender o Windows Search Indexer en NTFS.
    """
    for attempt in range(max_attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError as exc:
            if attempt == max_attempts - 1:
                raise EvidenceWriteError(
                    f"Fallo persistente de acceso en NTFS al renombrar {src} -> {dst}: {exc}"
                ) from exc
            time.sleep(0.002 * (2 ** attempt))  # 2ms, 4ms


class AtomicEvidenceWriter:
    """
    Codificador y escritor atómico de evidencias en disco local.
    """

    def __init__(self, evidence_base_dir: Path, jpeg_quality: int = 90) -> None:
        self._base_dir = Path(evidence_base_dir).resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)
        if not (1 <= jpeg_quality <= 100):
            raise ValueError("jpeg_quality debe estar en [1, 100].")
        self._jpeg_quality = jpeg_quality

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def _get_target_dir(self, codigo_camara: str, ts_utc: str) -> Path:
        safe_cam = "".join(c for c in codigo_camara if c.isalnum() or c in ("-", "_")).strip()
        date_folder = ts_utc[:8]  # YYYYMMDD
        target = self._base_dir / date_folder / safe_cam
        target.mkdir(parents=True, exist_ok=True)
        return target

    def write_evidence(
        self,
        task: PersistenceTaskDTO,
        force_fail_annotated: bool = False,
    ) -> Tuple[Path, Optional[Path]]:
        """
        Escribe atómicamente la evidencia original (*_orig.jpg) y anotada (*_annot.jpg).
        
        Si la escritura de la evidencia anotada falla (o si force_fail_annotated=True),
        ejecuta limpieza atómica inmediata eliminando la evidencia original creada,
        garantizando que no queden archivos huérfanos o asimétricos en disco.
        """
        created: List[Path] = []
        ts_utc = task.timestamp_captura.strftime("%Y%m%dT%H%M%S_%fZ")
        date_str = task.timestamp_captura.strftime("%Y%m%d")
        target_dir = self._get_target_dir(task.codigo_camara, date_str)

        token = uuid4().hex[:12]
        orig_filename = f"{ts_utc}_{token}_orig.jpg"
        orig_final = target_dir / orig_filename
        orig_tmp = target_dir / f".{orig_filename}.tmp.{uuid4().hex[:6]}"

        annot_final: Optional[Path] = None
        annot_tmp: Optional[Path] = None

        try:
            # 1. Escritura de fotograma original
            with open(orig_tmp, "xb") as fh:
                fh.write(task.raw_jpeg_bytes)
                fh.flush()
                os.fsync(fh.fileno())

            safe_replace_ntfs(orig_tmp, orig_final)
            created.append(orig_final)

            # 2. Renderizado y escritura de fotograma anotado si hay detecciones
            if task.detections or task.pixel_roi:
                # Decodificar BGR para renderizar cajas
                np_arr = np.frombuffer(task.raw_jpeg_bytes, np.uint8)
                bgr_frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                if bgr_frame is None:
                    raise EvidenceWriteError("No se pudo decodificar el JPEG para generar imagen anotada.")

                validate_bgr_frame(bgr_frame)
                annotated_bgr = render_annotated_frame(
                    bgr_frame,
                    task.detections,
                    task.pixel_roi,
                )

                ok, annot_jpeg_bytes = cv2.imencode(
                    ".jpg",
                    annotated_bgr,
                    [int(cv2.IMWRITE_JPEG_QUALITY), self._jpeg_quality],
                )
                if not ok or annot_jpeg_bytes is None:
                    raise EvidenceWriteError("Fallo al codificar imagen anotada en JPEG.")

                # Simulación de inyección de fallo controlada para pruebas de falla (Escenario 4)
                if force_fail_annotated:
                    raise OSError("Inyección de fallo simulada durante la escritura de evidencia anotada.")

                annot_filename = f"{ts_utc}_{token}_annot.jpg"
                annot_final = target_dir / annot_filename
                annot_tmp = target_dir / f".{annot_filename}.tmp.{uuid4().hex[:6]}"

                with open(annot_tmp, "xb") as fh:
                    fh.write(annot_jpeg_bytes.tobytes())
                    fh.flush()
                    os.fsync(fh.fileno())

                safe_replace_ntfs(annot_tmp, annot_final)
                created.append(annot_final)

            return orig_final, annot_final

        except Exception as exc:
            # Limpieza inmediata de cualquier archivo parcial o definitivo creado en esta invocación
            for p in (orig_tmp, annot_tmp):
                if p and p.exists():
                    try:
                        p.unlink()
                    except Exception:
                        pass
            self.rollback_evidence(created)
            raise EvidenceWriteError(f"Fallo al escribir evidencias fotográficas: {exc}") from exc

    def rollback_evidence(self, created_files: Sequence[Path]) -> int:
        """
        Elimina físicamente los archivos provistos ante un fallo posterior
        en la transacción de base de datos (compensación de huérfanos).
        """
        removed = 0
        for p in created_files:
            try:
                resolved = p.resolve()
                if resolved.is_file() and resolved.is_relative_to(self._base_dir):
                    resolved.unlink()
                    removed += 1
            except Exception as exc:
                logger.warning("No se pudo eliminar archivo en rollback (%s): %s", p, exc)
        return removed
