"""
VIGIA_Vision.config.engine_settings
===================================
Configuración validada e inmutable para el motor propio de visión artificial
de VIGÍA Vision Systems (Etapa 1).

Reglas de diseño:
- Inmutable (frozen dataclass).
- Umbral inicial de confianza vehicular por omisión: 0.70 (parámetro de
  configuración inicial, no una afirmación de exactitud del modelo).
- Valida rangos numéricos y rutas requeridas en ``__post_init__``.
- No almacena credenciales ni secretos en código ni los expone en representaciones.
- No realiza operaciones de entrada/salida ni abre hardware al importarse.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union


def _validate_positive_int(name: str, value: Any, *, minimum: int = 1) -> int:
    """Valida que ``value`` sea un entero estricto mayor o igual que ``minimum``."""
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name}={value!r} debe ser un entero >= {minimum}.")
    return int(value)


def _validate_positive_float(name: str, value: Any) -> float:
    """Valida que ``value`` sea un número finito estrictamente mayor que cero."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}={value!r} debe ser un número finito estrictamente mayor que 0.")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0.0:
        raise ValueError(f"{name}={value!r} debe ser un número finito estrictamente mayor que 0.")
    return numeric


@dataclass(frozen=True)
class VisionEngineSettings:
    """
    Parámetros operativos validados para inicializar y ejecutar el coordinador
    del motor de visión de VIGÍA (Etapa 1).

    Atributos
    ---------
    vehicle_confidence_threshold : float
        Umbral mínimo de confianza [0.0, 1.0] para considerar válida una
        detección vehicular dentro del ROI. Valor inicial por omisión: ``0.70``
        (configuración inicial; no representa una afirmación de exactitud del modelo).
    mobile_frame_ttl_seconds : float
        Tiempo máximo de vigencia (segundos > 0) de un fotograma depositado en
        el buffer push móvil antes de declararlo obsoleto (``CAMERA_ERROR``).
    evidence_directory : Path
        Directorio base controlado donde el servicio de almacenamiento guarda
        las evidencias fotográficas (original y anotada).
    save_annotated_evidence : bool
        Si es ``True``, solicita almacenar también el fotograma anotado con las
        cajas detectadas cuando esté disponible, además del fotograma original.
    jpeg_quality : int
        Calidad de compresión JPEG en el rango [1, 100] para las evidencias.
    fail_fast_on_invalid_topology : bool
        Si es ``True``, el coordinador bloquea de forma determinista su
        inicialización ante cualquier incumplimiento de las 8 reglas de DOC-03.
    temporal_min_confirm_frames : int
        Número mínimo de frames positivos en ROI necesarios para confirmar presencia
        vehicular (por omisión: ``2``).
    temporal_confirm_window_seconds : float
        Ventana temporal máxima (segundos monotónicos > 0) para acumular la
        confirmación de presencia vehicular (por omisión: ``1.5``).
    temporal_max_missed_frames : int
        Presupuesto de frames negativos consecutivos durante presencia activa antes
        de habilitar salida junto con la ventana temporal (por omisión: ``4``).
    temporal_missed_grace_seconds : float
        Ventana temporal mínima (segundos monotónicos > 0) tolerada antes de perder
        presencia por negativos consecutivos (por omisión: ``1.2``).
    temporal_lost_hold_seconds : float
        Tiempo (segundos monotónicos > 0) que se retiene el estado ``VEHICLE_LOST``
        antes de regresar a ``NO_VEHICLE_DETECTED`` (por omisión: ``0.8``).
    temporal_presence_expiry_seconds : float
        Límite absoluto (segundos monotónicos >= ``temporal_missed_grace_seconds``)
        sin confirmación positiva tras el cual la presencia expira (por omisión: ``6.0``).
    """

    vehicle_confidence_threshold: float = 0.70
    mobile_frame_ttl_seconds: float = 3.0
    evidence_directory: Union[Path, str] = Path("evidencias_vigia")
    save_annotated_evidence: bool = True
    jpeg_quality: int = 90
    fail_fast_on_invalid_topology: bool = True
    temporal_min_confirm_frames: int = 2
    temporal_confirm_window_seconds: float = 1.5
    temporal_max_missed_frames: int = 4
    temporal_missed_grace_seconds: float = 1.2
    temporal_lost_hold_seconds: float = 0.8
    temporal_presence_expiry_seconds: float = 6.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.vehicle_confidence_threshold, bool)
            or not isinstance(self.vehicle_confidence_threshold, (int, float))
            or not math.isfinite(float(self.vehicle_confidence_threshold))
            or not (0.0 < float(self.vehicle_confidence_threshold) <= 1.0)
        ):
            raise ValueError(
                f"vehicle_confidence_threshold={self.vehicle_confidence_threshold!r} "
                "debe ser un número en el rango (0.0, 1.0]."
            )

        mobile_ttl = _validate_positive_float("mobile_frame_ttl_seconds", self.mobile_frame_ttl_seconds)

        if (
            isinstance(self.jpeg_quality, bool)
            or not isinstance(self.jpeg_quality, int)
            or not (1 <= self.jpeg_quality <= 100)
        ):
            raise ValueError(
                f"jpeg_quality={self.jpeg_quality!r} debe ser un entero entre 1 y 100."
            )

        if self.evidence_directory is None:
            raise ValueError("evidence_directory no puede ser None.")

        raw_dir = str(self.evidence_directory).strip()
        if not raw_dir:
            raise ValueError("evidence_directory no puede ser una cadena vacía.")

        min_confirm = _validate_positive_int("temporal_min_confirm_frames", self.temporal_min_confirm_frames)
        confirm_window = _validate_positive_float("temporal_confirm_window_seconds", self.temporal_confirm_window_seconds)
        max_missed = _validate_positive_int("temporal_max_missed_frames", self.temporal_max_missed_frames)
        missed_grace = _validate_positive_float("temporal_missed_grace_seconds", self.temporal_missed_grace_seconds)
        lost_hold = _validate_positive_float("temporal_lost_hold_seconds", self.temporal_lost_hold_seconds)
        presence_expiry = _validate_positive_float("temporal_presence_expiry_seconds", self.temporal_presence_expiry_seconds)

        if presence_expiry < missed_grace:
            raise ValueError(
                f"temporal_presence_expiry_seconds={presence_expiry!r} debe ser >= "
                f"temporal_missed_grace_seconds={missed_grace!r}."
            )

        object.__setattr__(self, "vehicle_confidence_threshold", float(self.vehicle_confidence_threshold))
        object.__setattr__(self, "mobile_frame_ttl_seconds", mobile_ttl)
        object.__setattr__(self, "evidence_directory", Path(raw_dir))
        object.__setattr__(self, "temporal_min_confirm_frames", min_confirm)
        object.__setattr__(self, "temporal_confirm_window_seconds", confirm_window)
        object.__setattr__(self, "temporal_max_missed_frames", max_missed)
        object.__setattr__(self, "temporal_missed_grace_seconds", missed_grace)
        object.__setattr__(self, "temporal_lost_hold_seconds", lost_hold)
        object.__setattr__(self, "temporal_presence_expiry_seconds", presence_expiry)
