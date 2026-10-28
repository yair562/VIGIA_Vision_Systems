"""
VIGIA_Vision.config.topology_validator
======================================
Validador de Topología Operativa para VIGÍA Vision Systems V1.

Implementa la verificación técnica formal de las ocho reglas obligatorias
especificadas en DOC-03 y DOC-04 para bloquear de forma determinista (fail-fast)
el ciclo de captura e inferencia antes de que el motor empiece a procesar imágenes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Protocol
from uuid import UUID


# ==============================================================================
# Taxonomía de Códigos de Error (DOC-03, Sección 7 / DOC-05, Sección 6)
# ==============================================================================

class TopologyErrorCode:
    """Códigos formales de error de configuración topológica."""
    ERR_BD_CONEXION = "ERR_BD_CONEXION"
    ERR_CAM_ENTRADA_FALTANTE = "ERR_CAM_ENTRADA_FALTANTE"
    ERR_CAM_SALIDA_FALTANTE = "ERR_CAM_SALIDA_FALTANTE"
    ERR_CAM_INACTIVA = "ERR_CAM_INACTIVA"
    ERR_AREAS_TOTAL_INVALIDO = "ERR_AREAS_TOTAL_INVALIDO"
    ERR_ASOCIACION_AREA_CAMARA = "ERR_ASOCIACION_AREA_CAMARA"
    ERR_MOVIMIENTO_INVERTIDO = "ERR_MOVIMIENTO_INVERTIDO"
    ERR_ROI_DEGENERADA = "ERR_ROI_DEGENERADA"


class TopologyValidationError(Exception):
    """Excepción técnica levantada cuando la topología operativa es inválida."""

    def __init__(self, error_code: str, error_detail: str):
        super().__init__(f"[{error_code}] {error_detail}")
        self.error_code = error_code
        self.error_detail = error_detail


# ==============================================================================
# Contratos y DTOs de Configuración (DOC-04, Sección 3.1)
# ==============================================================================

@dataclass(frozen=True)
class CameraConfigDTO:
    """Configuración inmutable de cámara según esquema PostgreSQL 'camara'."""
    id_camara: UUID
    codigo: str
    nombre: str
    uri_stream: str
    activa: bool


@dataclass(frozen=True)
class AreaConfigDTO:
    """Configuración inmutable de área de visión según esquema PostgreSQL 'area_vision'."""
    id_area_vision: UUID
    id_camara: UUID
    codigo: str
    nombre: str
    tipo_movimiento: str  # 'ENTRADA' | 'SALIDA'
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    activa: bool


@dataclass(frozen=True)
class OperationalTopologyDTO:
    """Topología operativa validada de la caseta (Entrada y Salida)."""
    cam_entrada: CameraConfigDTO
    area_entrada: AreaConfigDTO
    cam_salida: CameraConfigDTO
    area_salida: AreaConfigDTO


@dataclass(frozen=True)
class TopologyValidationResult:
    """Resultado determinista de la validación de topología."""
    is_valid: bool
    topology: Optional[OperationalTopologyDTO] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None


class ITopologyConfigRepository(Protocol):
    """Interfaz de repositorio de solo lectura para consultar la topología de la base de datos."""

    def get_cameras(self) -> List[CameraConfigDTO]:
        """Retorna todas las cámaras registradas en el catálogo."""
        ...

    def get_areas(self) -> List[AreaConfigDTO]:
        """Retorna todas las áreas de visión registradas en el catálogo."""
        ...


# ==============================================================================
# Implementación del Validador de Topología
# ==============================================================================

class TopologyValidator:
    """
    Validador de reglas operativas de caseta para VIGÍA Vision Systems V1.

    Aplica de forma estricta las 8 reglas obligatorias de DOC-03 antes de que
    el servicio de visión adquiera recursos de captura o inicialice inferencia.
    """

    CODIGO_CAM_ENTRADA = "CAM-ENTRADA"
    CODIGO_CAM_SALIDA = "CAM-SALIDA"
    MOVIMIENTO_ENTRADA = "ENTRADA"
    MOVIMIENTO_SALIDA = "SALIDA"
    UMBRAL_AREA_ROI_MINIMA = 0.01  # DOC-03 Sección 7 (L145)

    def __init__(self, repository: Optional[ITopologyConfigRepository] = None):
        self._repository = repository

    def validate(
        self,
        cameras: Optional[List[CameraConfigDTO]] = None,
        areas: Optional[List[AreaConfigDTO]] = None,
    ) -> TopologyValidationResult:
        """
        Ejecuta la validación determinista de las 8 reglas de DOC-03.

        Puede recibir los datos directamente (para pruebas o memoria) o
        consultarlos a través del repositorio inyectado.
        """
        # 1. Obtención de datos desde el repositorio si no se suministran
        if cameras is None or areas is None:
            if self._repository is None:
                return TopologyValidationResult(
                    is_valid=False,
                    error_code=TopologyErrorCode.ERR_BD_CONEXION,
                    error_detail="No se proveyó repositorio de configuración ni datos para la validación.",
                )
            try:
                if cameras is None:
                    cameras = self._repository.get_cameras()
                if areas is None:
                    areas = self._repository.get_areas()
            except Exception as exc:
                return TopologyValidationResult(
                    is_valid=False,
                    error_code=TopologyErrorCode.ERR_BD_CONEXION,
                    error_detail=f"Fallo de conexión o consulta relacional a PostgreSQL: {exc}",
                )

        # Indexar cámaras por código
        cams_by_code = {cam.codigo: cam for cam in cameras}

        # Regla 1 (R1 - VAL-CAM-ENTRADA): Debe existir registrada 'CAM-ENTRADA'
        if self.CODIGO_CAM_ENTRADA not in cams_by_code:
            return TopologyValidationResult(
                is_valid=False,
                error_code=TopologyErrorCode.ERR_CAM_ENTRADA_FALTANTE,
                error_detail="No existe la cámara obligatoria con código 'CAM-ENTRADA' en la configuración.",
            )
        cam_entrada = cams_by_code[self.CODIGO_CAM_ENTRADA]

        # Regla 2 (R2 - VAL-CAM-SALIDA): Debe existir registrada 'CAM-SALIDA'
        if self.CODIGO_CAM_SALIDA not in cams_by_code:
            return TopologyValidationResult(
                is_valid=False,
                error_code=TopologyErrorCode.ERR_CAM_SALIDA_FALTANTE,
                error_detail="No existe la cámara obligatoria con código 'CAM-SALIDA' en la configuración.",
            )
        cam_salida = cams_by_code[self.CODIGO_CAM_SALIDA]

        # Regla 3 (R3 - VAL-CAM-INACTIVA): Ambas cámaras operativas deben estar activas administrativamente
        if not cam_entrada.activa:
            return TopologyValidationResult(
                is_valid=False,
                error_code=TopologyErrorCode.ERR_CAM_INACTIVA,
                error_detail=f"La cámara operativa '{self.CODIGO_CAM_ENTRADA}' existe pero está deshabilitada (activa=False).",
            )
        if not cam_salida.activa:
            return TopologyValidationResult(
                is_valid=False,
                error_code=TopologyErrorCode.ERR_CAM_INACTIVA,
                error_detail=f"La cámara operativa '{self.CODIGO_CAM_SALIDA}' existe pero está deshabilitada (activa=False).",
            )

        # Regla 4 (R4 - VAL-AREAS-TOTAL): Deben existir exactamente dos áreas activas en todo el sistema
        active_areas = [area for area in areas if area.activa]
        if len(active_areas) != 2:
            return TopologyValidationResult(
                is_valid=False,
                error_code=TopologyErrorCode.ERR_AREAS_TOTAL_INVALIDO,
                error_detail=(
                    f"Se esperaban exactamente 2 áreas de visión activas en el sistema, "
                    f"pero se encontraron {len(active_areas)}."
                ),
            )

        # Regla 5 (R5 - VAL-ASOC-1A1): Exactamente un área activa asociada a cada cámara operativa
        areas_entrada = [a for a in active_areas if a.id_camara == cam_entrada.id_camara]
        areas_salida = [a for a in active_areas if a.id_camara == cam_salida.id_camara]

        if len(areas_entrada) != 1:
            return TopologyValidationResult(
                is_valid=False,
                error_code=TopologyErrorCode.ERR_ASOCIACION_AREA_CAMARA,
                error_detail=(
                    f"La cámara '{self.CODIGO_CAM_ENTRADA}' tiene {len(areas_entrada)} áreas activas asociadas. "
                    f"Se requiere exactamente 1."
                ),
            )

        if len(areas_salida) != 1:
            return TopologyValidationResult(
                is_valid=False,
                error_code=TopologyErrorCode.ERR_ASOCIACION_AREA_CAMARA,
                error_detail=(
                    f"La cámara '{self.CODIGO_CAM_SALIDA}' tiene {len(areas_salida)} áreas activas asociadas. "
                    f"Se requiere exactamente 1."
                ),
            )

        area_entrada = areas_entrada[0]
        area_salida = areas_salida[0]

        # Regla 6 (R6 - VAL-MOV-ENTRADA): El área de CAM-ENTRADA debe ser 'ENTRADA'
        if area_entrada.tipo_movimiento != self.MOVIMIENTO_ENTRADA:
            return TopologyValidationResult(
                is_valid=False,
                error_code=TopologyErrorCode.ERR_MOVIMIENTO_INVERTIDO,
                error_detail=(
                    f"El área activa asociada a '{self.CODIGO_CAM_ENTRADA}' tiene tipo_movimiento='{area_entrada.tipo_movimiento}'. "
                    f"Se requiere obligatoriamente '{self.MOVIMIENTO_ENTRADA}'."
                ),
            )

        # Regla 7 (R7 - VAL-MOV-SALIDA): El área de CAM-SALIDA debe ser 'SALIDA'
        if area_salida.tipo_movimiento != self.MOVIMIENTO_SALIDA:
            return TopologyValidationResult(
                is_valid=False,
                error_code=TopologyErrorCode.ERR_MOVIMIENTO_INVERTIDO,
                error_detail=(
                    f"El área activa asociada a '{self.CODIGO_CAM_SALIDA}' tiene tipo_movimiento='{area_salida.tipo_movimiento}'. "
                    f"Se requiere obligatoriamente '{self.MOVIMIENTO_SALIDA}'."
                ),
            )

        # Regla 8 (R8 - VAL-ROI-GEOM): Validación geométrica de coordenadas ROI no degeneradas
        for area, cam_cod in ((area_entrada, self.CODIGO_CAM_ENTRADA), (area_salida, self.CODIGO_CAM_SALIDA)):
            roi_valid, roi_error = self._validate_roi_geometry(area)
            if not roi_valid:
                return TopologyValidationResult(
                    is_valid=False,
                    error_code=TopologyErrorCode.ERR_ROI_DEGENERADA,
                    error_detail=(
                        f"El área '{area.codigo}' de la cámara '{cam_cod}' tiene una ROI inválida: {roi_error}"
                    ),
                )

        # Topología válida y nominal completa
        topology_dto = OperationalTopologyDTO(
            cam_entrada=cam_entrada,
            area_entrada=area_entrada,
            cam_salida=cam_salida,
            area_salida=area_salida,
        )

        return TopologyValidationResult(
            is_valid=True,
            topology=topology_dto,
            error_code=None,
            error_detail=None,
        )

    def _validate_roi_geometry(self, area: AreaConfigDTO) -> tuple[bool, Optional[str]]:
        """Verifica que las coordenadas pertenezcan a [0.0, 1.0], sean consistentes y no degeneradas."""
        xmin, ymin, xmax, ymax = area.x_min, area.y_min, area.x_max, area.y_max

        # Comprobación de límites normalizados
        if not (0.0 <= xmin < xmax <= 1.0):
            return False, f"x_min ({xmin}) y x_max ({xmax}) deben cumplir 0.0 <= x_min < x_max <= 1.0."

        if not (0.0 <= ymin < ymax <= 1.0):
            return False, f"y_min ({ymin}) y y_max ({ymax}) deben cumplir 0.0 <= y_min < y_max <= 1.0."

        ancho = xmax - xmin
        alto = ymax - ymin
        area_calculada = ancho * alto

        if area_calculada < self.UMBRAL_AREA_ROI_MINIMA:
            return False, (
                f"El área de la ROI ({area_calculada:.4f}) es menor al umbral técnico mínimo "
                f"({self.UMBRAL_AREA_ROI_MINIMA}). Las dimensiones ({ancho:.3f} x {alto:.3f}) son degeneradas."
            )

        return True, None
