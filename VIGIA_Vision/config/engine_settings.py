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

from dataclasses import dataclass
from pathlib import Path
from typing import Union


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
    """

    vehicle_confidence_threshold: float = 0.70
    mobile_frame_ttl_seconds: float = 3.0
    evidence_directory: Union[Path, str] = Path("evidencias_vigia")
    save_annotated_evidence: bool = True
    jpeg_quality: int = 90
    fail_fast_on_invalid_topology: bool = True

    def __post_init__(self) -> None:
        if (
            isinstance(self.vehicle_confidence_threshold, bool)
            or not isinstance(self.vehicle_confidence_threshold, (int, float))
            or not (0.0 < float(self.vehicle_confidence_threshold) <= 1.0)
        ):
            raise ValueError(
                f"vehicle_confidence_threshold={self.vehicle_confidence_threshold!r} "
                "debe ser un número en el rango (0.0, 1.0]."
            )

        if (
            isinstance(self.mobile_frame_ttl_seconds, bool)
            or not isinstance(self.mobile_frame_ttl_seconds, (int, float))
            or float(self.mobile_frame_ttl_seconds) <= 0.0
        ):
            raise ValueError(
                f"mobile_frame_ttl_seconds={self.mobile_frame_ttl_seconds!r} "
                "debe ser un número estrictamente mayor que 0."
            )

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

        object.__setattr__(self, "vehicle_confidence_threshold", float(self.vehicle_confidence_threshold))
        object.__setattr__(self, "mobile_frame_ttl_seconds", float(self.mobile_frame_ttl_seconds))
        object.__setattr__(self, "evidence_directory", Path(raw_dir))
