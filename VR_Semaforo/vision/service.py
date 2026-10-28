from typing import Optional
from pathlib import Path
import sys

# Asegurar resolución de VIGIA_Vision
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from vision.camera import capture_pc
from vision.pipeline import VisionPipeline
from traffic.analyzer import TrafficAnalyzer
from VIGIA_Vision.config.topology_validator import (
    TopologyValidator,
    TopologyValidationResult,
    TopologyValidationError,
    OperationalTopologyDTO,
)


_pipeline = VisionPipeline()
_validator: Optional[TopologyValidator] = None
_active_topology: Optional[OperationalTopologyDTO] = None


def set_topology_validator(validator: Optional[TopologyValidator]) -> None:
    """Configura el validador de topología para el servicio."""
    global _validator, _active_topology
    _validator = validator
    _active_topology = None


def get_active_topology() -> Optional[OperationalTopologyDTO]:
    """Retorna la topología validada activa, o None si no ha sido inicializada."""
    return _active_topology


def initialize_vision_service(
    validator: Optional[TopologyValidator] = None,
    fail_fast: bool = True,
) -> TopologyValidationResult:
    """
    Inicializa el servicio de visión validando la topología operativa según DOC-03.
    Bloquea el arranque si la configuración es inválida.
    """
    global _validator, _active_topology
    val = validator or _validator
    if val is None:
        val = TopologyValidator()

    _validator = val
    result = val.validate()

    if result.is_valid:
        _active_topology = result.topology
    else:
        _active_topology = None
        if fail_fast:
            raise TopologyValidationError(
                result.error_code or "ERR_TOPOLOGY",
                result.error_detail or "Topología operativa inválida.",
            )

    return result


def process_pc_capture(
    pipeline: Optional[VisionPipeline] = None,
    validator: Optional[TopologyValidator] = None,
):
    """
    Captura y procesa un fotograma desde la cámara local de la PC.
    Verifica que la topología sea válida antes de adquirir hardware o ejecutar inferencia.
    """
    # 1. Verificación previa de topología operativa (DOC-03, Regla 8 - VAL-BLOCK-START)
    val = validator or _validator
    if val is not None:
        top_result = val.validate()
        if not top_result.is_valid:
            # Bloqueo: NO capturar frame, NO inferir, producir error explícito
            raise TopologyValidationError(
                top_result.error_code or "ERR_TOPOLOGY",
                top_result.error_detail or "Topología inválida. Captura bloqueada.",
            )

    # 2. Captura de frame
    p = pipeline or _pipeline
    frame = capture_pc()

    if frame is None:
        vision = {
            "status": "TECHNICAL_ERROR",
            "vehicle_detected": False,
            "vehicle_count": 0,
            "vehicles": [],
            "error": "Camera frame could not be captured.",
        }
        cantidad = 0
    else:
        vision_result = p.process(frame)
        vision = vision_result.to_dict()
        cantidad = vision_result.vehicle_count

    result = TrafficAnalyzer().analizar(cantidad)
    result["vision"] = vision
    return result