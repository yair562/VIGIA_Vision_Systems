"""
VIGIA_Vision.capture.registry
=============================
Registro de fuentes de captura vinculado exclusivamente a ``OperationalTopologyDTO``.

Garantías arquitectónicas:
- Asocia de manera biunívoca e inmutable cada ``codigo_camara`` operativo
  (``'CAM-ENTRADA'`` y ``'CAM-SALIDA'``) con su ``CameraConfigDTO``, su única
  ``AreaConfigDTO`` activa y su instancia de ``IFrameCaptureSource``.
- Rechaza de forma determinista cualquier operación sobre un código de cámara
  que no pertenezca a la topología validada (ningún teléfono ni fuente externa
  puede registrar cámaras nuevas ni modificar las posiciones lógicas).
- Aísla el estado y las fuentes de ``CAM-ENTRADA`` y ``CAM-SALIDA``.
- No abre descriptores de hardware durante la construcción del registro
  (``__init__``); la apertura ocurre únicamente cuando se invoca ``open_all()``
  o ``open_camera(codigo_camara)``.
- ``release_all()`` es idempotente y aísla excepciones para garantizar que el
  fallo al liberar una cámara no impida liberar la otra.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Dict, Mapping, Optional, Tuple

from VIGIA_Vision.capture.sources import (
    IFrameCaptureSource,
    MobilePushFrameBuffer,
    OpenCVCaptureSource,
)
from VIGIA_Vision.config.topology_validator import (
    AreaConfigDTO,
    CameraConfigDTO,
    OperationalTopologyDTO,
)


class UnregisteredCameraError(KeyError):
    """Se intentó operar sobre un código de cámara no perteneciente a la topología validada."""


@dataclass(frozen=True)
class BoundCameraSlot:
    """
    Contexto inmutable que enlaza una posición operativa validada con su fuente.
    """

    camera: CameraConfigDTO
    area: AreaConfigDTO
    source: IFrameCaptureSource


class CameraSourceRegistry:
    """
    Registro de fuentes de video gobernado por una ``OperationalTopologyDTO``
    previamente validada.

    Parámetros
    ----------
    topology : OperationalTopologyDTO
        Topología operativa validada de la caseta (Entrada y Salida).
    sources : Optional[Mapping[str, IFrameCaptureSource]]
        Mapa opcional ``{codigo_camara: source}`` para inyectar fuentes ya
        instanciadas (por ejemplo, dobles de prueba o ``MobilePushFrameBuffer``).
    default_source_factory : Optional[Callable[[CameraConfigDTO], IFrameCaptureSource]]
        Fábrica para construir la fuente de cualquier cámara de la topología
        que no haya sido provista en ``sources``. Si no se especifica, instancia
        ``MobilePushFrameBuffer`` cuando ``uri_stream`` comienza con ``push://``
        o ``mobile://``, y ``OpenCVCaptureSource(camera.uri_stream)`` en los
        demás casos, **sin abrir hardware**.
    mobile_ttl_seconds : float
        TTL por omisión al construir ``MobilePushFrameBuffer``.
    """

    def __init__(
        self,
        topology: OperationalTopologyDTO,
        sources: Optional[Mapping[str, IFrameCaptureSource]] = None,
        default_source_factory: Optional[Callable[[CameraConfigDTO], IFrameCaptureSource]] = None,
        mobile_ttl_seconds: float = 3.0,
    ) -> None:
        if not isinstance(topology, OperationalTopologyDTO):
            raise ValueError("topology debe ser una instancia válida de OperationalTopologyDTO.")

        self._topology = topology
        self._mobile_ttl_seconds = float(mobile_ttl_seconds)
        self._lock = threading.RLock()

        allowed_pairs: Tuple[Tuple[CameraConfigDTO, AreaConfigDTO], ...] = (
            (topology.cam_entrada, topology.area_entrada),
            (topology.cam_salida, topology.area_salida),
        )
        allowed_codes = {cam.codigo for cam, _ in allowed_pairs}

        if sources is not None:
            for provided_code in sources.keys():
                if provided_code not in allowed_codes:
                    raise UnregisteredCameraError(
                        f"La cámara '{provided_code}' no pertenece a la topología operativa "
                        f"validada ({sorted(allowed_codes)})."
                    )

        factory = default_source_factory or self._build_default_source
        slots: Dict[str, BoundCameraSlot] = {}

        for cam_dto, area_dto in allowed_pairs:
            if area_dto.id_camara != cam_dto.id_camara:
                raise ValueError(
                    f"Inconsistencia en OperationalTopologyDTO: el área '{area_dto.codigo}' "
                    f"no pertenece a la cámara '{cam_dto.codigo}'."
                )
            src = (
                sources[cam_dto.codigo]
                if (sources is not None and cam_dto.codigo in sources)
                else factory(cam_dto)
            )
            if not isinstance(src, IFrameCaptureSource):
                raise TypeError(
                    f"La fuente para '{cam_dto.codigo}' no implementa IFrameCaptureSource."
                )
            slots[cam_dto.codigo] = BoundCameraSlot(
                camera=cam_dto,
                area=area_dto,
                source=src,
            )

        self._slots: Dict[str, BoundCameraSlot] = slots

    def _build_default_source(self, camera: CameraConfigDTO) -> IFrameCaptureSource:
        uri = camera.uri_stream.strip()
        if uri.lower().startswith(("push://", "mobile://")):
            return MobilePushFrameBuffer(
                codigo_camara=camera.codigo,
                ttl_seconds=self._mobile_ttl_seconds,
            )
        return OpenCVCaptureSource(source_uri=uri)

    @property
    def topology(self) -> OperationalTopologyDTO:
        return self._topology

    @property
    def registered_camera_codes(self) -> Tuple[str, ...]:
        """Códigos de cámara registrados en orden determinista (Entrada, Salida)."""
        return tuple(self._slots.keys())

    def get_slot(self, codigo_camara: str) -> BoundCameraSlot:
        """
        Obtiene el ``BoundCameraSlot`` asociado a ``codigo_camara``.
        Lanza ``UnregisteredCameraError`` si el código no pertenece a la topología.
        """
        with self._lock:
            if codigo_camara not in self._slots:
                raise UnregisteredCameraError(
                    f"Código de cámara '{codigo_camara}' rechazado: no forma parte de la "
                    f"topología validada ({list(self._slots.keys())})."
                )
            return self._slots[codigo_camara]

    def open_camera(self, codigo_camara: str) -> bool:
        """Abre explícitamente la fuente de una cámara registrada."""
        slot = self.get_slot(codigo_camara)
        return bool(slot.source.open())

    def open_all(self) -> Dict[str, bool]:
        """
        Intenta abrir todas las fuentes registradas de manera aislada.
        El fallo al abrir una cámara no impide abrir la otra.
        """
        results: Dict[str, bool] = {}
        for code, slot in self._slots.items():
            try:
                results[code] = bool(slot.source.open())
            except Exception:
                results[code] = False
        return results

    def release_camera(self, codigo_camara: str) -> None:
        """Libera de forma idempotente la fuente de una cámara registrada."""
        slot = self.get_slot(codigo_camara)
        try:
            slot.source.release()
        except Exception:
            pass

    def release_all(self) -> None:
        """Libera de forma idempotente todas las fuentes registradas."""
        with self._lock:
            for slot in self._slots.values():
                try:
                    slot.source.release()
                except Exception:
                    pass
