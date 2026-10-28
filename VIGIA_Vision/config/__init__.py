"""
VIGIA_Vision.config
===================
Módulo de configuración y validación de topología operativa para V1.
"""

from VIGIA_Vision.config.topology_validator import (
    AreaConfigDTO,
    CameraConfigDTO,
    ITopologyConfigRepository,
    OperationalTopologyDTO,
    TopologyErrorCode,
    TopologyValidationError,
    TopologyValidationResult,
    TopologyValidator,
)

__all__ = [
    "AreaConfigDTO",
    "CameraConfigDTO",
    "ITopologyConfigRepository",
    "OperationalTopologyDTO",
    "TopologyErrorCode",
    "TopologyValidationError",
    "TopologyValidationResult",
    "TopologyValidator",
]
