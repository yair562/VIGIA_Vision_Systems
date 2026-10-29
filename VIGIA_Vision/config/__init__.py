"""
VIGIA_Vision.config
===================
Módulo de configuración y validación de topología operativa para V1.
"""

from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.config.psycopg_topology_repository import PsycopgTopologyConfigRepository
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
    "PsycopgTopologyConfigRepository",
    "TopologyErrorCode",
    "TopologyValidationError",
    "TopologyValidationResult",
    "TopologyValidator",
    "VisionEngineSettings",
]
