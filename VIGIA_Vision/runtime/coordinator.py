"""
VIGIA_Vision.runtime.coordinator
================================
Coordinador base del motor propio de visión artificial de VIGÍA Vision Systems (Etapa 1).

Integra de manera desacoplada y verificable:
1. Validación fail-fast de topología operativa (``TopologyValidator``, Reglas R1-R8).
2. Registro y lectura de fuentes por cámara identificada (``CameraSourceRegistry``).
3. Validación del fotograma BGR y proyección geométrica del ROI (``roi_and_preprocess``).
4. Detector vehicular inyectable (``IVehicleDetector``). La integración concreta con
   YOLOv11 corresponde a la Etapa 2; este módulo nunca carga modelos al importarse.
5. Construcción de ``VisionResult`` respetando todas las invariantes de ``VIGIA_Core``.
6. Almacenamiento de evidencia original y anotada (``IEvidenceStorageService``).
7. Persistencia relacional mediante ``IDetectionRepository`` (con mapeo de tipos
   ``map_tipo_vehiculo_ddl_v1`` y limpieza compensatoria de archivos huérfanos
   ante fallos SQL).
8. Construcción y entrega del sobre inmutable ``VisionObservationEnvelope`` a
   consumidores registrados (``IObservationConsumer``).

Política de persistencia en la Etapa 1 (Sección 5.8):
- Jamás se persisten los estados ``NO_VEHICLE_DETECTED``, ``CAMERA_ERROR`` ni
  ``VISION_ERROR``.
- Jamás se persiste una fila por fotograma de manera continua e indiscriminada:
  dado que el seguimiento temporal (tracking) y la deduplicación pertenecen a la
  Etapa 3, en la Etapa 1 la persistencia solo se ejecuta cuando el llamador o la
  política de decisión de evento indica explícitamente ``persist_as_new_event=True``
  (o mediante ``new_event_predicate``). Por omisión, ``process_camera_step()``
  tiene ``persist_as_new_event=False`` para impedir inundar PostgreSQL con
  detecciones repetidas del mismo vehículo antes de que exista la Etapa 3.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence, runtime_checkable
from uuid import UUID

from VIGIA_Core.domain.vision_result import VisionResult, VisionStatus
from VIGIA_Core.repository.detection_repository import (
    DetectionInsertDTO,
    IDetectionRepository,
    map_tipo_vehiculo_ddl_v1,
)
from VIGIA_Vision.capture.registry import BoundCameraSlot, CameraSourceRegistry
from VIGIA_Vision.capture.sources import IFrameCaptureSource
from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.config.topology_validator import (
    OperationalTopologyDTO,
    TopologyErrorCode,
    TopologyValidationError,
    TopologyValidator,
)
from VIGIA_Vision.detection.models import (
    ObservationMetrics,
    RawVehicleDetection,
    VisionObservationEnvelope,
)
from VIGIA_Vision.detection.roi_and_preprocess import (
    FrameValidationError,
    filter_detections_by_roi,
    project_normalized_roi,
    validate_bgr_frame,
)
from VIGIA_Vision.runtime.evidence_storage import (
    EvidenceSaveResult,
    IEvidenceStorageService,
    LocalDiskEvidenceStorage,
    render_annotated_frame,
)

logger = logging.getLogger(__name__)

# Mapeo oficial de clases vehiculares del detector hacia el dominio VIGÍA (Sección 5.8)
_RAW_LABEL_TO_DOMAIN_VEHICLE_TYPE: Dict[str, str] = {
    "car": "AUTOMOVIL",
    "automovil": "AUTOMOVIL",
    "automobile": "AUTOMOVIL",
    "2": "AUTOMOVIL",
    "motorcycle": "MOTOCICLETA",
    "motorbike": "MOTOCICLETA",
    "motocicleta": "MOTOCICLETA",
    "3": "MOTOCICLETA",
    "bus": "AUTOBUS",
    "autobus": "AUTOBUS",
    "5": "AUTOBUS",
    "truck": "CAMION",
    "camion": "CAMION",
    "7": "CAMION",
    "pickup": "CAMIONETA",
    "suv": "CAMIONETA",
    "van": "CAMIONETA",
    "camioneta": "CAMIONETA",
}


def map_raw_label_to_domain_vehicle_type(raw_label: Optional[str]) -> Optional[str]:
    """
    Traduce la etiqueta de clase emitida por el detector al vocabulario del
    dominio de ``VisionResult``:
      - ``'car'``        -> ``'AUTOMOVIL'``
      - ``'motorcycle'`` -> ``'MOTOCICLETA'``
      - ``'truck'``      -> ``'CAMION'``
      - ``'bus'``        -> ``'AUTOBUS'``
      - ``'camioneta'``  -> ``'CAMIONETA'``

    Retorna ``None`` si la etiqueta es nula o no pertenece al catálogo vehicular.
    """
    if raw_label is None:
        return None
    normalized = raw_label.strip().lower()
    if not normalized:
        return None
    return _RAW_LABEL_TO_DOMAIN_VEHICLE_TYPE.get(normalized)


@runtime_checkable
class IVehicleDetector(Protocol):
    """
    Contrato para el detector de vehículos inyectable en ``VisionEngineCoordinator``.
    La implementación concreta con YOLOv11 se incorpora en la Etapa 2.
    """

    def detect(self, frame: Any) -> Sequence[RawVehicleDetection]:
        """Ejecuta inferencia sobre un fotograma BGR uint8 y retorna candidatos."""
        ...  # pragma: no cover


@runtime_checkable
class IObservationConsumer(Protocol):
    """Contrato explícito para componentes que consumen ``VisionObservationEnvelope``."""

    def on_observation(self, envelope: VisionObservationEnvelope) -> None:
        """Recibe el sobre inmutable de observación producido tras evaluar un cuadro."""
        ...  # pragma: no cover


class NullVehicleDetector:
    """Detector nulo por omisión para inicializaciones sin modelo cargado."""

    def detect(self, frame: Any) -> Sequence[RawVehicleDetection]:
        return ()


class VisionEngineCoordinator:
    """
    Coordinador síncrono del motor de visión artificial de VIGÍA (Etapa 1).

    Garantías de ciclo de vida:
    - Instanciar ``VisionEngineCoordinator`` no abre cámaras, no consulta la base
      de datos ni ejecuta inferencia.
    - ``initialize()`` valida la topología operativa mediante ``TopologyValidator``
      antes de crear ``CameraSourceRegistry`` o abrir cualquier fuente de captura.
    - Si la topología es inválida, lanza ``TopologyValidationError`` y garantiza
      que ninguna fuente sea abierta ni ningún detector invocado.
    """

    def __init__(
        self,
        topology_validator: TopologyValidator,
        settings: Optional[VisionEngineSettings] = None,
        detector: Optional[IVehicleDetector] = None,
        detection_repository: Optional[IDetectionRepository] = None,
        evidence_storage: Optional[IEvidenceStorageService] = None,
        sources: Optional[Mapping[str, IFrameCaptureSource]] = None,
        source_factory: Optional[Callable[[Any], IFrameCaptureSource]] = None,
        consumers: Optional[Sequence[IObservationConsumer]] = None,
        new_event_predicate: Optional[Callable[[str, Sequence[RawVehicleDetection]], bool]] = None,
    ) -> None:
        if not isinstance(topology_validator, TopologyValidator):
            raise TypeError("topology_validator debe ser una instancia de TopologyValidator.")

        self._validator = topology_validator
        self._settings = settings or VisionEngineSettings()
        self._detector: IVehicleDetector = detector or NullVehicleDetector()
        self._detection_repository = detection_repository
        self._evidence_storage: IEvidenceStorageService = evidence_storage or LocalDiskEvidenceStorage(
            base_directory=self._settings.evidence_directory,
            jpeg_quality=self._settings.jpeg_quality,
        )
        self._injected_sources = dict(sources) if sources is not None else None
        self._source_factory = source_factory
        self._consumers: List[IObservationConsumer] = list(consumers) if consumers is not None else []
        self._new_event_predicate = new_event_predicate

        self._topology: Optional[OperationalTopologyDTO] = None
        self._registry: Optional[CameraSourceRegistry] = None
        self._initialized: bool = False

    @property
    def settings(self) -> VisionEngineSettings:
        return self._settings

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def active_topology(self) -> Optional[OperationalTopologyDTO]:
        return self._topology

    @property
    def registry(self) -> Optional[CameraSourceRegistry]:
        return self._registry

    def register_consumer(self, consumer: IObservationConsumer) -> None:
        """Registra un consumidor para recibir cada ``VisionObservationEnvelope`` emitido."""
        if not isinstance(consumer, IObservationConsumer):
            raise TypeError("consumer debe implementar IObservationConsumer.")
        self._consumers.append(consumer)

    def initialize(self, open_sources: bool = True) -> OperationalTopologyDTO:
        """
        Valida la topología operativa (Reglas R1–R8 de DOC-03) y, únicamente si
        es válida, construye el ``CameraSourceRegistry`` y opcionalmente abre las
        fuentes de captura.

        Lanza
        -----
        TopologyValidationError
            Si cualquiera de las 8 reglas de topología falla. Garantiza que no
            se abre ninguna fuente de hardware.
        """
        validation = self._validator.validate()
        if not validation.is_valid or validation.topology is None:
            self._topology = None
            self._registry = None
            self._initialized = False
            raise TopologyValidationError(
                validation.error_code or TopologyErrorCode.ERR_BD_CONEXION,
                validation.error_detail or "Topología operativa inválida.",
            )

        self._topology = validation.topology
        self._registry = CameraSourceRegistry(
            topology=self._topology,
            sources=self._injected_sources,
            default_source_factory=self._source_factory,
            mobile_ttl_seconds=self._settings.mobile_frame_ttl_seconds,
        )
        self._initialized = True

        if open_sources:
            self._registry.open_all()

        return self._topology

    def shutdown(self) -> None:
        """Cierra de manera idempotente todas las fuentes registradas."""
        if self._registry is not None:
            self._registry.release_all()
        self._initialized = False

    def __enter__(self) -> "VisionEngineCoordinator":
        if not self._initialized:
            self.initialize(open_sources=True)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.shutdown()

    def process_camera_step(
        self,
        codigo_camara: str,
        persist_as_new_event: Optional[bool] = None,
    ) -> Optional[VisionObservationEnvelope]:
        """
        Ejecuta un ciclo síncrono de observación para la cámara identificada por
        ``codigo_camara`` (``'CAM-ENTRADA'`` o ``'CAM-SALIDA'``).

        Parámetros
        ----------
        codigo_camara : str
            Código de la cámara dentro de la topología validada.
        persist_as_new_event : Optional[bool]
            Indica explícitamente si, en caso de existir una detección vehicular
            válida dentro del ROI, esta corresponde a un evento nuevo que debe
            almacenar evidencia e insertarse en PostgreSQL.
            - Si es ``None``, se consulta ``new_event_predicate`` si fue inyectado;
              de lo contrario, por seguridad en la Etapa 1 (sin tracking) se
              evalúa como ``False`` para impedir persistir una fila por fotograma.

        Retorna
        -------
        Optional[VisionObservationEnvelope]
            El sobre inmutable con ``VisionResult`` y metadatos, o ``None``
            únicamente cuando un buffer push móvil informa ``is_already_processed=True``
            (no hay una secuencia de fotograma nueva que procesar).
        """
        if not self._initialized or self._registry is None:
            raise TopologyValidationError(
                TopologyErrorCode.ERR_BD_CONEXION,
                "El coordinador de visión no ha sido inicializado con una topología válida.",
            )

        slot: BoundCameraSlot = self._registry.get_slot(codigo_camara)
        read_res = slot.source.read_frame()

        # 1. Si un buffer push móvil indica que la secuencia vigente ya fue procesada,
        # omitir reprocesamiento sin declarar error técnico.
        if not read_res.ok and read_res.is_already_processed:
            return None

        # 2. Fallo de captura o fotograma vencido (TTL) -> CAMERA_ERROR
        if not read_res.ok or read_res.frame is None:
            vision_res = VisionResult(
                status=VisionStatus.CAMERA_ERROR,
                timestamp=read_res.captured_at,
                vehicle_detected=False,
                error_message=read_res.error_reason or "Fallo de captura de fotograma.",
            )
            envelope = self._build_envelope(
                slot=slot,
                vision_result=vision_res,
                detections_in_roi=(),
                metrics=ObservationMetrics(
                    in_roi_now=0,
                    total_detected_in_frame=0,
                    excluded_outside_roi=0,
                    unique_vehicles_total=None,
                ),
                frame_sequence=read_res.frame_sequence,
            )
            self._notify_consumers(envelope)
            return envelope

        frame = read_res.frame

        # 3. Validación de matriz BGR y proyección geométrica del ROI
        try:
            frame_w, frame_h = validate_bgr_frame(frame)
            pixel_roi = project_normalized_roi(slot.area, frame_w, frame_h)
        except (FrameValidationError, ValueError) as exc:
            vision_res = VisionResult(
                status=VisionStatus.CAMERA_ERROR,
                timestamp=read_res.captured_at,
                vehicle_detected=False,
                error_message=f"Fotograma o ROI inválido: {exc}",
            )
            envelope = self._build_envelope(
                slot=slot,
                vision_result=vision_res,
                detections_in_roi=(),
                metrics=ObservationMetrics(),
                frame_sequence=read_res.frame_sequence,
            )
            self._notify_consumers(envelope)
            return envelope

        # 4. Ejecución aislada del detector de vehículos
        try:
            raw_candidates = tuple(self._detector.detect(frame) or ())
        except Exception as exc:
            logger.error(
                "Error técnico de inferencia en cámara '%s': %s",
                slot.camera.codigo,
                exc,
            )
            vision_res = VisionResult(
                status=VisionStatus.VISION_ERROR,
                timestamp=read_res.captured_at,
                vehicle_detected=False,
                error_message=f"Fallo en inferencia vehicular: {exc}",
            )
            envelope = self._build_envelope(
                slot=slot,
                vision_result=vision_res,
                detections_in_roi=(),
                metrics=ObservationMetrics(),
                frame_sequence=read_res.frame_sequence,
            )
            self._notify_consumers(envelope)
            return envelope

        # 5. Filtrado por umbral de confianza y pertenencia del centroide al ROI (RF-03)
        detections_in_roi, excluded_outside_roi = filter_detections_by_roi(
            detections=raw_candidates,
            pixel_roi=pixel_roi,
            min_confidence=self._settings.vehicle_confidence_threshold,
        )

        metrics = ObservationMetrics(
            in_roi_now=len(detections_in_roi),
            total_detected_in_frame=len(raw_candidates),
            excluded_outside_roi=excluded_outside_roi,
            unique_vehicles_total=None,  # Reservado para Etapa 3 (tracking)
        )

        # 6. Ausencia de vehículos dentro del ROI -> NO_VEHICLE_DETECTED (no se persiste)
        if not detections_in_roi:
            vision_res = VisionResult(
                status=VisionStatus.NO_VEHICLE_DETECTED,
                timestamp=read_res.captured_at,
                vehicle_detected=False,
                vehicle_confidence=None,
                vehicle_type_pred=None,
                plate_located=False,
                plate_text=None,
                plate_confidence=None,
                evidence_path=None,
                error_message=None,
            )
            envelope = self._build_envelope(
                slot=slot,
                vision_result=vision_res,
                detections_in_roi=(),
                metrics=metrics,
                frame_sequence=read_res.frame_sequence,
            )
            self._notify_consumers(envelope)
            return envelope

        # 7. Selección determinista del vehículo primario dentro del ROI
        primary = detections_in_roi[0]
        domain_vehicle_type = map_raw_label_to_domain_vehicle_type(primary.raw_label)

        should_persist = (
            persist_as_new_event
            if persist_as_new_event is not None
            else (
                bool(self._new_event_predicate(slot.camera.codigo, detections_in_roi))
                if self._new_event_predicate is not None
                else False
            )
        )

        orig_rel_path: Optional[str] = None
        annot_rel_path: Optional[str] = None
        id_deteccion: Optional[UUID] = None
        evidence_save_res: Optional[EvidenceSaveResult] = None

        if should_persist:
            annotated_img = (
                render_annotated_frame(frame, detections_in_roi, pixel_roi)
                if self._settings.save_annotated_evidence
                else None
            )
            evidence_save_res = self._evidence_storage.save_evidence(
                original_frame=frame,
                codigo_camara=slot.camera.codigo,
                timestamp=read_res.captured_at,
                annotated_frame=annotated_img,
            )
            orig_rel_path = evidence_save_res.primary_db_path
            annot_rel_path = evidence_save_res.annotated_rel_path

        # En la Etapa 1 (sin OCR/ANPR), toda detección vehicular válida en el ROI
        # produce VEHICLE_DETECTED_NO_PLATE.
        vision_res = VisionResult(
            status=VisionStatus.VEHICLE_DETECTED_NO_PLATE,
            timestamp=read_res.captured_at,
            vehicle_detected=True,
            vehicle_confidence=primary.confidence,
            vehicle_type_pred=domain_vehicle_type,
            plate_located=False,
            plate_text=None,
            plate_confidence=None,
            evidence_path=orig_rel_path,
            error_message=None,
        )

        # 8. Persistencia relacional con limpieza compensatoria ante fallo SQL
        if should_persist and self._detection_repository is not None:
            ddl_safe_type = map_tipo_vehiculo_ddl_v1(domain_vehicle_type)
            dto = DetectionInsertDTO(
                id_area_vision=slot.area.id_area_vision,
                placa_detectada=vision_res.plate_text,
                confianza_placa=vision_res.plate_confidence,
                confianza_vehiculo=vision_res.vehicle_confidence,
                tipo_vehiculo_pred=ddl_safe_type,
                ruta_evidencia_foto=orig_rel_path,
                fecha_hora=vision_res.timestamp,
            )
            try:
                id_deteccion = self._detection_repository.persist_detection(dto)
            except Exception as exc:
                logger.error(
                    "Fallo al persistir detección en PostgreSQL para cámara '%s'; "
                    "ejecutando limpieza compensatoria de evidencia: %s",
                    slot.camera.codigo,
                    exc,
                )
                if evidence_save_res is not None and evidence_save_res.saved:
                    self._evidence_storage.rollback_evidence(evidence_save_res)
                raise

        envelope = self._build_envelope(
            slot=slot,
            vision_result=vision_res,
            detections_in_roi=detections_in_roi,
            metrics=metrics,
            id_deteccion=id_deteccion,
            frame_sequence=read_res.frame_sequence,
            original_evidence_path=orig_rel_path,
            annotated_evidence_path=annot_rel_path,
        )
        self._notify_consumers(envelope)
        return envelope

    def step_all_cameras(
        self,
        persist_as_new_event: Optional[bool] = None,
    ) -> Dict[str, Optional[VisionObservationEnvelope]]:
        """
        Ejecuta ``process_camera_step`` sobre todas las cámaras registradas en la
        topología validada, aislando los errores para que un fallo en una cámara
        jamás detenga el procesamiento de la otra.
        """
        if not self._initialized or self._registry is None:
            raise TopologyValidationError(
                TopologyErrorCode.ERR_BD_CONEXION,
                "El coordinador de visión no ha sido inicializado con una topología válida.",
            )

        results: Dict[str, Optional[VisionObservationEnvelope]] = {}
        for code in self._registry.registered_camera_codes:
            slot = self._registry.get_slot(code)
            try:
                results[code] = self.process_camera_step(
                    codigo_camara=code,
                    persist_as_new_event=persist_as_new_event,
                )
            except Exception as exc:
                logger.error(
                    "Excepción aislada en ciclo de cámara '%s': %s",
                    code,
                    exc,
                )
                fallback_res = VisionResult(
                    status=VisionStatus.VISION_ERROR,
                    vehicle_detected=False,
                    error_message=f"Fallo aislado en ciclo de coordinación: {exc}",
                )
                env = self._build_envelope(
                    slot=slot,
                    vision_result=fallback_res,
                    detections_in_roi=(),
                    metrics=ObservationMetrics(),
                )
                self._notify_consumers(env)
                results[code] = env

        return results

    @staticmethod
    def _build_envelope(
        slot: BoundCameraSlot,
        vision_result: VisionResult,
        detections_in_roi: Sequence[RawVehicleDetection],
        metrics: ObservationMetrics,
        id_deteccion: Optional[UUID] = None,
        frame_sequence: Optional[int] = None,
        original_evidence_path: Optional[str] = None,
        annotated_evidence_path: Optional[str] = None,
    ) -> VisionObservationEnvelope:
        return VisionObservationEnvelope(
            vision_result=vision_result,
            id_camara=slot.camera.id_camara,
            codigo_camara=slot.camera.codigo,
            id_area_vision=slot.area.id_area_vision,
            codigo_area=slot.area.codigo,
            tipo_movimiento=slot.area.tipo_movimiento,
            detections_in_roi=tuple(detections_in_roi),
            metrics=metrics,
            id_deteccion=id_deteccion,
            frame_sequence=frame_sequence,
            original_evidence_path=original_evidence_path,
            annotated_evidence_path=annotated_evidence_path,
        )

    def _notify_consumers(self, envelope: VisionObservationEnvelope) -> None:
        for consumer in self._consumers:
            try:
                consumer.on_observation(envelope)
            except Exception as exc:
                logger.warning(
                    "Consumidor de observación lanzó excepción no fatal: %s",
                    exc,
                )
