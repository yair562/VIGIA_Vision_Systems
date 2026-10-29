"""
VIGIA_Vision.capture
====================
Fuentes de captura desacopladas (Pull OpenCV y Push Móvil con TTL) y registro
de cámaras vinculado a la topología operativa validada.
"""

from VIGIA_Vision.capture.registry import (
    BoundCameraSlot,
    CameraSourceRegistry,
    UnregisteredCameraError,
)
from VIGIA_Vision.capture.sources import (
    IFrameCaptureSource,
    MobilePushFrameBuffer,
    OpenCVCaptureSource,
)

__all__ = [
    "BoundCameraSlot",
    "CameraSourceRegistry",
    "IFrameCaptureSource",
    "MobilePushFrameBuffer",
    "OpenCVCaptureSource",
    "UnregisteredCameraError",
]
