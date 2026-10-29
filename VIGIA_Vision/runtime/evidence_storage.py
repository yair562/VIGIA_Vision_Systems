"""
VIGIA_Vision.runtime.evidence_storage
=====================================
Contrato y servicio local de almacenamiento de evidencias fotográficas para
VIGÍA Vision Systems (Etapa 1).

Política de almacenamiento y trazabilidad hacia PostgreSQL (Sección 5.7):
1. Cuando una detección vehicular se almacena como evidencia, el servicio
   escribe con nombres únicos (UUIDv4 + marca de tiempo UTC) bajo un directorio
   base controlado:
   - El **fotograma original sin anotaciones** (``*_orig.jpg``).
   - El **fotograma anotado con las cajas y el ROI** (``*_annot.jpg``), cuando
     se solicita o se provee un fotograma anotado.
2. **Convención determinista con el esquema protegido PostgreSQL (`deteccion.ruta_evidencia_foto`):**
   - La tabla ``deteccion`` en ``V001__baseline_schema.sql`` posee una única
     columna ``ruta_evidencia_foto TEXT``.
   - Se persiste en ``deteccion.ruta_evidencia_foto`` (y en ``VisionResult.evidence_path``)
     la ruta relativa POSIX del **fotograma original** (``<fecha>/<camara>/<ts>_<uuid>_orig.jpg``),
     preservando la imagen forense limpia sin alteraciones.
   - El fotograma anotado comparte exactamente el mismo directorio y prefijo
     base, cambiando únicamente el sufijo final ``_orig.jpg`` por ``_annot.jpg``
     (``<fecha>/<camara>/<ts>_<uuid>_annot.jpg``). Ambas rutas quedan registradas
     explícitamente en ``EvidenceSaveResult`` y en ``VisionObservationEnvelope``
     (``original_evidence_path`` y ``annotated_evidence_path``), manteniendo
     trazabilidad 1:1 sin introducir columnas SQL ni tablas paralelas.
3. **Prevención de traversal y sobrescritura:**
   - El identificador de cámara se sanea estrictamente a ``[A-Za-z0-9_-]``.
   - Todas las rutas generadas se resuelven y verifican con ``Path.is_relative_to(base_dir)``.
   - Los archivos se abren en modo exclusivo (``'xb'``) para prohibir cualquier
     sobrescritura accidental de evidencia previa.
4. **Tolerancia a fallos y limpieza compensatoria:**
   - Si la escritura en disco falla, el servicio limpia cualquier archivo parcial
     de esa misma operación y retorna ``EvidenceSaveResult(saved=False,
     original_rel_path=None, annotated_rel_path=None)`` para que el coordinador
     continúe persistiendo la detección con ``ruta_evidencia_foto=None`` (DOC-04).
   - Si posteriormente falla el ``INSERT`` en PostgreSQL, ``rollback_evidence()``
     elimina **exclusivamente** los archivos creados por esa operación fallida.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Protocol, Sequence, Tuple, runtime_checkable
from uuid import uuid4

import numpy as np

from VIGIA_Vision.detection.models import RawVehicleDetection
from VIGIA_Vision.detection.roi_and_preprocess import PixelROI, validate_bgr_frame

logger = logging.getLogger(__name__)

_SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


class StorageWriteError(OSError):
    """Error al codificar o escribir una evidencia fotográfica en el almacenamiento local."""


@dataclass(frozen=True)
class EvidenceSaveResult:
    """
    Resultado inmutable de una operación de guardado de evidencia.

    Atributos
    ---------
    saved : bool
        ``True`` si al menos el fotograma original se guardó íntegramente.
    original_rel_path : Optional[str]
        Ruta relativa POSIX al fotograma original limpio (``*_orig.jpg``).
        Esta es la ruta canónica que se asigna a ``VisionResult.evidence_path``
        y a ``DetectionInsertDTO.ruta_evidencia_foto``.
    annotated_rel_path : Optional[str]
        Ruta relativa POSIX al fotograma anotado (``*_annot.jpg``), si se generó.
    created_files : Tuple[Path, ...]
        Rutas absolutas exactas creadas en esta operación, utilizadas
        exclusivamente si se requiere limpieza compensatoria tras fallo SQL.
    error_message : Optional[str]
        Detalle técnico del error cuando ``saved=False``.
    """

    saved: bool
    original_rel_path: Optional[str] = None
    annotated_rel_path: Optional[str] = None
    created_files: Tuple[Path, ...] = ()
    error_message: Optional[str] = None

    @property
    def primary_db_path(self) -> Optional[str]:
        """Ruta relativa destinada a ``deteccion.ruta_evidencia_foto`` y ``VisionResult.evidence_path``."""
        return self.original_rel_path if self.saved else None


@runtime_checkable
class IEvidenceStorageService(Protocol):
    """Contrato de almacenamiento de evidencias fotográficas (original y anotada)."""

    def save_evidence(
        self,
        original_frame: Any,
        codigo_camara: str,
        timestamp: datetime,
        annotated_frame: Optional[Any] = None,
    ) -> EvidenceSaveResult:
        """Guarda la evidencia original y, si está presente, la evidencia anotada."""
        ...  # pragma: no cover

    def rollback_evidence(self, save_result: EvidenceSaveResult) -> int:
        """
        Elimina exclusivamente los archivos creados en ``save_result`` ante un
        fallo posterior de persistencia en PostgreSQL. Retorna el número de
        archivos eliminados.
        """
        ...  # pragma: no cover


def render_annotated_frame(
    frame: np.ndarray,
    detections_in_roi: Sequence[RawVehicleDetection],
    pixel_roi: Optional[PixelROI] = None,
) -> np.ndarray:
    """
    Genera una copia del fotograma BGR dibujando los bordes del ROI y las cajas
    delimitadoras de los vehículos detectados sin mutar el arreglo original.

    No requiere OpenCV para dibujar los bordes rectangulares (opera directamente
    sobre slices NumPy BGR), por lo que es determinista y libre de dependencias
    gráficas externas.
    """
    validate_bgr_frame(frame)
    canvas = frame.copy()
    h, w, _ = canvas.shape
    thickness = 2

    def _draw_rect(
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        bgr_color: Tuple[int, int, int],
    ) -> None:
        ix1 = max(0, min(w - 1, x1))
        iy1 = max(0, min(h - 1, y1))
        ix2 = max(0, min(w, x2))
        iy2 = max(0, min(h, y2))
        if ix2 <= ix1 or iy2 <= iy1:
            return
        t = min(thickness, ix2 - ix1, iy2 - iy1)
        canvas[iy1 : iy1 + t, ix1:ix2] = bgr_color
        canvas[iy2 - t : iy2, ix1:ix2] = bgr_color
        canvas[iy1:iy2, ix1 : ix1 + t] = bgr_color
        canvas[iy1:iy2, ix2 - t : ix2] = bgr_color

    # 1. Dibujar el ROI en color cian/amarillo BGR (0, 215, 255)
    if pixel_roi is not None:
        rx1, ry1, rx2, ry2 = pixel_roi.to_int_tuple()
        _draw_rect(rx1, ry1, rx2, ry2, (0, 215, 255))

    # 2. Dibujar cada vehículo detectado dentro del ROI en verde BGR (0, 220, 0)
    for det in detections_in_roi:
        _draw_rect(
            det.bbox.x_min,
            det.bbox.y_min,
            det.bbox.x_max,
            det.bbox.y_max,
            (0, 220, 0),
        )

    return canvas


def derive_annotated_evidence_path(original_path: str) -> str:
    """
    Retorna la ruta determinista del fotograma anotado (*_annot.jpg) a partir
    de la ruta del fotograma original (*_orig.jpg) persistida en PostgreSQL.

    Garantiza compatibilidad 1:1 con la columna única ``deteccion.ruta_evidencia_foto``
    del esquema DDL V1 sin alterar tablas relacionales ni contratos.
    """
    if not isinstance(original_path, str) or not original_path.strip():
        raise ValueError("original_path debe ser una cadena no vacía.")
    cleaned = original_path.strip()
    if not cleaned.endswith("_orig.jpg"):
        raise ValueError(
            f"original_path='{cleaned}' no cumple con la convención '_orig.jpg'."
        )
    return cleaned[:-9] + "_annot.jpg"


def derive_original_evidence_path(annotated_path: str) -> str:
    """
    Retorna la ruta determinista del fotograma original (*_orig.jpg) a partir
    de la ruta del fotograma anotado (*_annot.jpg).
    """
    if not isinstance(annotated_path, str) or not annotated_path.strip():
        raise ValueError("annotated_path debe ser una cadena no vacía.")
    cleaned = annotated_path.strip()
    if not cleaned.endswith("_annot.jpg"):
        raise ValueError(
            f"annotated_path='{cleaned}' no cumple con la convención '_annot.jpg'."
        )
    return cleaned[:-10] + "_orig.jpg"


def _default_jpeg_encoder(frame: np.ndarray, quality: int) -> bytes:
    """Codifica un arreglo BGR uint8 a bytes JPEG mediante ``cv2.imencode``."""
    import cv2

    params = [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
    ok, buf = cv2.imencode(".jpg", frame, params)
    if not ok or buf is None:
        raise StorageWriteError("cv2.imencode no pudo codificar el fotograma en JPEG.")
    return bytes(buf.tobytes())


class LocalDiskEvidenceStorage(IEvidenceStorageService):
    """
    Implementación local y segura de ``IEvidenceStorageService``.

    Parámetros
    ----------
    base_directory : Path | str
        Directorio raíz controlado donde se almacenan las evidencias.
    jpeg_quality : int
        Calidad de compresión JPEG en [1, 100].
    encoder : Optional[Callable[[np.ndarray, int], bytes]]
        Codificador de imagen a bytes JPEG (inyectable para pruebas unitarias).
    """

    def __init__(
        self,
        base_directory: Path | str,
        jpeg_quality: int = 90,
        encoder: Optional[Callable[[np.ndarray, int], bytes]] = None,
    ) -> None:
        if base_directory is None or not str(base_directory).strip():
            raise ValueError("base_directory no puede ser vacío.")
        if isinstance(jpeg_quality, bool) or not isinstance(jpeg_quality, int) or not (1 <= jpeg_quality <= 100):
            raise ValueError("jpeg_quality debe ser un entero en [1, 100].")

        self._base_dir = Path(str(base_directory).strip()).resolve()
        self._jpeg_quality = jpeg_quality
        self._encoder = encoder or _default_jpeg_encoder

    @property
    def base_directory(self) -> Path:
        return self._base_dir

    @staticmethod
    def _sanitize_camera_code(codigo_camara: str) -> str:
        if not isinstance(codigo_camara, str):
            raise StorageWriteError("codigo_camara inválido.")
        cleaned = codigo_camara.strip()
        if not _SAFE_CODE_RE.match(cleaned):
            raise StorageWriteError(
                f"codigo_camara={codigo_camara!r} contiene caracteres no permitidos para rutas."
            )
        return cleaned

    def _ensure_within_base(self, target_path: Path) -> Path:
        resolved = target_path.resolve()
        if not resolved.is_relative_to(self._base_dir):
            raise StorageWriteError(
                f"Intento de escritura fuera del directorio de evidencias permitido: {resolved}"
            )
        return resolved

    @staticmethod
    def _write_exclusive_bytes(file_path: Path, payload: bytes) -> None:
        if not payload:
            raise StorageWriteError("El contenido codificado de la imagen está vacío.")
        with open(file_path, "xb") as fh:
            fh.write(payload)

    def save_evidence(
        self,
        original_frame: Any,
        codigo_camara: str,
        timestamp: datetime,
        annotated_frame: Optional[Any] = None,
    ) -> EvidenceSaveResult:
        """
        Escribe en disco la evidencia original (``*_orig.jpg``) y, si se provee
        ``annotated_frame``, la evidencia anotada (``*_annot.jpg``).

        En caso de cualquier fallo de validación, codificación o E/S, elimina
        los archivos parciales creados en esta invocación y retorna
        ``EvidenceSaveResult(saved=False)`` sin propagar la excepción hacia el
        coordinador.
        """
        created: list[Path] = []
        try:
            validate_bgr_frame(original_frame)
            if annotated_frame is not None:
                validate_bgr_frame(annotated_frame)

            safe_cam = self._sanitize_camera_code(codigo_camara)
            ts_utc = (
                timestamp.astimezone(timezone.utc)
                if timestamp.tzinfo is not None
                else timestamp.replace(tzinfo=timezone.utc)
            )
            date_folder = ts_utc.strftime("%Y%m%d")
            ts_prefix = ts_utc.strftime("%Y%m%dT%H%M%S_%fZ")
            unique_token = uuid4().hex[:12]

            target_dir = self._ensure_within_base(self._base_dir / date_folder / safe_cam)
            target_dir.mkdir(parents=True, exist_ok=True)

            orig_filename = f"{ts_prefix}_{unique_token}_orig.jpg"
            orig_abs = self._ensure_within_base(target_dir / orig_filename)
            orig_bytes = self._encoder(original_frame, self._jpeg_quality)
            self._write_exclusive_bytes(orig_abs, orig_bytes)
            created.append(orig_abs)
            orig_rel = orig_abs.relative_to(self._base_dir).as_posix()

            annot_rel: Optional[str] = None
            if annotated_frame is not None:
                annot_filename = f"{ts_prefix}_{unique_token}_annot.jpg"
                annot_abs = self._ensure_within_base(target_dir / annot_filename)
                annot_bytes = self._encoder(annotated_frame, self._jpeg_quality)
                self._write_exclusive_bytes(annot_abs, annot_bytes)
                created.append(annot_abs)
                annot_rel = annot_abs.relative_to(self._base_dir).as_posix()

            return EvidenceSaveResult(
                saved=True,
                original_rel_path=orig_rel,
                annotated_rel_path=annot_rel,
                created_files=tuple(created),
                error_message=None,
            )

        except Exception as exc:
            # Limpiar cualquier archivo parcial escrito durante esta operación fallida
            for partial in created:
                try:
                    if partial.exists() and partial.is_relative_to(self._base_dir):
                        partial.unlink()
                except Exception:
                    pass
            logger.error(
                "Fallo al almacenar evidencia fotográfica para cámara '%s': %s",
                codigo_camara,
                exc,
            )
            return EvidenceSaveResult(
                saved=False,
                original_rel_path=None,
                annotated_rel_path=None,
                created_files=(),
                error_message=str(exc),
            )

    def rollback_evidence(self, save_result: EvidenceSaveResult) -> int:
        """
        Elimina exclusivamente los archivos registrados en ``save_result.created_files``
        cuando la inserción posterior en PostgreSQL falla (compensación de huérfanos).
        """
        removed = 0
        for file_path in save_result.created_files:
            try:
                resolved = file_path.resolve()
                if resolved.is_relative_to(self._base_dir) and resolved.is_file():
                    resolved.unlink()
                    removed += 1
            except Exception as exc:
                logger.warning(
                    "No se pudo eliminar archivo huérfano en rollback compensatorio (%s): %s",
                    file_path,
                    exc,
                )
        return removed

    def resolve_annotated_file(self, original_rel_path: str) -> Optional[Path]:
        """
        Retorna la ruta absoluta del fotograma anotado (*_annot.jpg) si existe en disco,
        o None si no existe o si la ruta original no es válida.
        """
        try:
            annot_rel = derive_annotated_evidence_path(original_rel_path)
            candidate = self._ensure_within_base(self._base_dir / annot_rel)
            if candidate.is_file():
                return candidate
        except Exception:
            pass
        return None

    def resolve_original_file(self, original_rel_path: str) -> Optional[Path]:
        """
        Retorna la ruta absoluta del fotograma original (*_orig.jpg) si existe en disco.
        """
        try:
            candidate = self._ensure_within_base(self._base_dir / original_rel_path)
            if candidate.is_file():
                return candidate
        except Exception:
            pass
        return None
