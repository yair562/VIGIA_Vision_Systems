"""
VIGIA_Vision.detection.roi_and_preprocess
=========================================
Validación de fotogramas BGR, proyección de coordenadas normalizadas del área de
visión (ROI) a coordenadas de píxeles y evaluación geométrica determinista de
pertenencia al ROI (RF-03).

Criterio geométrico de inclusión (Etapa 1):
- Una detección vehicular pertenece al ROI si y solo si el centroide ``(cx, cy)``
  de su caja delimitadora ``BoundingBox`` cae dentro de los límites proyectados
  del ``AreaConfigDTO`` con límites cerrados (inclusivos):
  ``roi_x_min <= cx <= roi_x_max`` y ``roi_y_min <= cy <= roi_y_max``.

Reglas de diseño:
- No importa ni carga modelos de inteligencia artificial (sin PyTorch ni YOLO).
- No implementa seguimiento temporal (tracking) ni conteo acumulado.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence, Tuple

import numpy as np

from VIGIA_Vision.config.topology_validator import AreaConfigDTO
from VIGIA_Vision.detection.models import BoundingBox, RawVehicleDetection


class FrameValidationError(ValueError):
    """El fotograma recibido es nulo, vacío o no cumple el formato BGR uint8 3D."""


@dataclass(frozen=True)
class PixelROI:
    """
    Rectángulo de región de interés proyectado a coordenadas de píxeles sobre un
    fotograma de dimensiones ``(frame_width, frame_height)``.

    Los límites ``(x_min, y_min, x_max, y_max)`` son inclusivos para la prueba
    de pertenencia del centroide: ``x_min <= cx <= x_max`` y ``y_min <= cy <= y_max``.
    """

    x_min: float
    y_min: float
    x_max: float
    y_max: float
    frame_width: int
    frame_height: int

    def __post_init__(self) -> None:
        if self.frame_width <= 0 or self.frame_height <= 0:
            raise ValueError(
                f"Dimensiones de fotograma inválidas: {self.frame_width}x{self.frame_height}."
            )
        if not (0.0 <= self.x_min < self.x_max <= float(self.frame_width)):
            raise ValueError(
                f"Límites horizontales de PixelROI inválidos: [{self.x_min}, {self.x_max}] "
                f"para ancho={self.frame_width}."
            )
        if not (0.0 <= self.y_min < self.y_max <= float(self.frame_height)):
            raise ValueError(
                f"Límites verticales de PixelROI inválidos: [{self.y_min}, {self.y_max}] "
                f"para alto={self.frame_height}."
            )

    def contains_point(self, x: float, y: float) -> bool:
        """
        Evalúa de forma determinista e inclusiva en los bordes si el punto ``(x, y)``
        pertenece al rectángulo proyectado del ROI.
        """
        return (self.x_min <= x <= self.x_max) and (self.y_min <= y <= self.y_max)

    def contains_bbox_centroid(self, bbox: BoundingBox) -> bool:
        """
        Retorna ``True`` si el centroide ``(cx, cy)`` de ``bbox`` cae dentro del ROI
        (bordes incluidos).
        """
        cx, cy = bbox.centroid
        return self.contains_point(cx, cy)

    def to_int_tuple(self) -> Tuple[int, int, int, int]:
        """Coordenadas enteras ``(x1, y1, x2, y2)`` aptas para dibujo en imagen."""
        return (
            int(round(self.x_min)),
            int(round(self.y_min)),
            int(round(self.x_max)),
            int(round(self.y_max)),
        )


def validate_bgr_frame(frame: Any) -> Tuple[int, int]:
    """
    Verifica que ``frame`` sea un arreglo ``numpy.ndarray`` tridimensional no vacío
    con 3 canales (BGR) y tipo ``uint8``.

    Retorna
    -------
    Tuple[int, int]
        ``(width, height)`` en píxeles.

    Lanza
    -----
    FrameValidationError
        Si el fotograma es ``None``, no es ``np.ndarray``, tiene dimensiones
        inválidas, número de canales distinto de 3 o tipo de dato distinto de ``uint8``.
    """
    if frame is None:
        raise FrameValidationError("El fotograma es None.")
    if not isinstance(frame, np.ndarray):
        raise FrameValidationError(
            f"Se esperaba un numpy.ndarray BGR, pero se recibió {type(frame).__name__}."
        )
    if frame.ndim != 3:
        raise FrameValidationError(
            f"El fotograma debe tener 3 dimensiones (H, W, C); ndim={frame.ndim}."
        )
    height, width, channels = frame.shape
    if height <= 0 or width <= 0:
        raise FrameValidationError(
            f"Las dimensiones del fotograma deben ser positivas; shape={frame.shape}."
        )
    if channels != 3:
        raise FrameValidationError(
            f"El fotograma BGR debe tener exactamente 3 canales; canales={channels}."
        )
    if frame.dtype != np.uint8:
        raise FrameValidationError(
            f"El fotograma BGR debe tener dtype=uint8; dtype={frame.dtype}."
        )
    return int(width), int(height)


def project_normalized_roi(
    area: AreaConfigDTO,
    frame_width: int,
    frame_height: int,
) -> PixelROI:
    """
    Proyecta las coordenadas normalizadas ``[x_min, y_min, x_max, y_max]`` en
    ``[0.0, 1.0]`` de ``AreaConfigDTO`` a coordenadas de píxeles sobre un
    fotograma de tamaño ``(frame_width, frame_height)``.
    """
    if not isinstance(area, AreaConfigDTO):
        raise ValueError("area debe ser una instancia de AreaConfigDTO.")
    if frame_width <= 0 or frame_height <= 0:
        raise ValueError(
            f"frame_width y frame_height deben ser > 0; recibidos ({frame_width}, {frame_height})."
        )
    if not (0.0 <= area.x_min < area.x_max <= 1.0) or not (0.0 <= area.y_min < area.y_max <= 1.0):
        raise ValueError(
            f"Coordenadas normalizadas de AreaConfigDTO fuera de [0.0, 1.0] o invertidas: "
            f"({area.x_min}, {area.y_min}, {area.x_max}, {area.y_max})."
        )

    px_min = float(area.x_min) * float(frame_width)
    py_min = float(area.y_min) * float(frame_height)
    px_max = float(area.x_max) * float(frame_width)
    py_max = float(area.y_max) * float(frame_height)

    if (px_max - px_min) < 1.0 or (py_max - py_min) < 1.0:
        raise ValueError(
            f"El ROI proyectado ({px_max - px_min:.2f}x{py_max - py_min:.2f} px) "
            "es menor a 1 píxel útil."
        )

    return PixelROI(
        x_min=px_min,
        y_min=py_min,
        x_max=px_max,
        y_max=py_max,
        frame_width=frame_width,
        frame_height=frame_height,
    )


def filter_detections_by_roi(
    detections: Sequence[RawVehicleDetection],
    pixel_roi: PixelROI,
    min_confidence: float,
) -> Tuple[Tuple[RawVehicleDetection, ...], int]:
    """
    Filtra las detecciones vehiculares conservando únicamente aquellas que:
    1. Tienen ``confidence >= min_confidence``.
    2. Tienen el centroide de su ``BoundingBox`` dentro de ``pixel_roi`` (bordes inclusivos).

    Las detecciones válidas se retornan ordenadas de mayor a menor confianza
    (y por mayor área en caso de empate) para una selección determinista del
    vehículo primario.

    Retorna
    -------
    Tuple[Tuple[RawVehicleDetection, ...], int]
        ``(detecciones_dentro_del_roi, conteo_excluidas_fuera_del_roi)``
        donde ``conteo_excluidas_fuera_del_roi`` contabiliza las detecciones que
        superaron ``min_confidence`` pero cuyo centroide cayó fuera del ROI.
    """
    if not (0.0 < min_confidence <= 1.0):
        raise ValueError(f"min_confidence={min_confidence!r} debe pertenecer a (0.0, 1.0].")

    inside: list[RawVehicleDetection] = []
    excluded_outside_roi = 0

    for det in detections:
        if det.confidence < min_confidence:
            continue
        if pixel_roi.contains_bbox_centroid(det.bbox):
            inside.append(det)
        else:
            excluded_outside_roi += 1

    inside.sort(key=lambda d: (d.confidence, d.bbox.area), reverse=True)
    return tuple(inside), excluded_outside_roi
