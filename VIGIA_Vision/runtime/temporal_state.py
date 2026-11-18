"""
VIGIA_Vision.runtime.temporal_state
===================================
Máquina de estados temporal determinista por cámara para VIGIA-VISION-02A.

Desacoplada del pipeline de inferencia YOLO, de la persistencia SQL y de los
endpoints HTTP. Opera exclusivamente sobre tiempo monotónico inyectable para
evitar parpadeos por detecciones aisladas, negativos transitorios o congelamiento
de streams sin depender del reloj de pared.

Estados canónicos
-----------------
- ``NO_VEHICLE_DETECTED``: reposo sin presencia ni candidato activo.
- ``VEHICLE_CANDIDATE``: detección positiva inicial en ROI esperando confirmación.
- ``VEHICLE_PRESENT``: presencia vehicular confirmada y sostenida en ROI.
- ``VEHICLE_LOST``: salida o expiración temporal tras presencia activa previa.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Deque, Dict, Optional, Set, Union

from VIGIA_Vision.config.engine_settings import (
    VisionEngineSettings,
    _validate_positive_float,
    _validate_positive_int,
)

_MAX_SEEN_FRAME_IDS = 512
# Margen sub-nanosegundo para absorber error de redondeo IEEE-754 en restas monotónicas.
_TIME_EPSILON = 1e-9


def _elapsed_reached(elapsed: float, threshold: float) -> bool:
    """Retorna ``True`` cuando ``elapsed >= threshold`` tolerando redondeo IEEE-754."""
    return (elapsed + _TIME_EPSILON) >= threshold


def _elapsed_within(elapsed: float, window: float) -> bool:
    """Retorna ``True`` cuando ``elapsed <= window`` tolerando redondeo IEEE-754."""
    return elapsed <= (window + _TIME_EPSILON)


class TemporalDetectionStatus(str, Enum):
    """Estados temporales canónicos de presencia vehicular por cámara."""

    NO_VEHICLE_DETECTED = "NO_VEHICLE_DETECTED"
    VEHICLE_CANDIDATE = "VEHICLE_CANDIDATE"
    VEHICLE_PRESENT = "VEHICLE_PRESENT"
    VEHICLE_LOST = "VEHICLE_LOST"


@dataclass(frozen=True)
class TemporalStateConfig:
    """
    Parámetros inmutables validados para la máquina de estados temporal.

    Atributos
    ---------
    min_confirm_frames : int
        Número mínimo de frames positivos en ROI consecutivos dentro de
        ``confirm_window_seconds`` para confirmar ``VEHICLE_PRESENT`` (default: 2).
    confirm_window_seconds : float
        Ventana temporal máxima en segundos monotónicos para confirmar presencia
        desde el primer frame candidato (default: 1.5).
    max_missed_frames : int
        Presupuesto máximo de frames negativos consecutivos en ``VEHICLE_PRESENT``
        antes de requerir salida junto con ``missed_grace_seconds`` (default: 4).
    missed_grace_seconds : float
        Tiempo mínimo de gracia en segundos monotónicos en ``VEHICLE_PRESENT`` antes
        de perder presencia por negativos consecutivos (default: 1.2).
    lost_hold_seconds : float
        Duración de retención del estado explícito ``VEHICLE_LOST`` antes de volver
        a ``NO_VEHICLE_DETECTED`` (default: 0.8).
    presence_expiry_seconds : float
        Límite duro absoluto en segundos monotónicos sin confirmación positiva tras
        el cual la presencia expira hacia ``VEHICLE_LOST`` (default: 6.0).
    """

    min_confirm_frames: int = 2
    confirm_window_seconds: float = 1.5
    max_missed_frames: int = 4
    missed_grace_seconds: float = 1.2
    lost_hold_seconds: float = 0.8
    presence_expiry_seconds: float = 6.0

    def __post_init__(self) -> None:
        min_confirm = _validate_positive_int("min_confirm_frames", self.min_confirm_frames)
        confirm_window = _validate_positive_float("confirm_window_seconds", self.confirm_window_seconds)
        max_missed = _validate_positive_int("max_missed_frames", self.max_missed_frames)
        missed_grace = _validate_positive_float("missed_grace_seconds", self.missed_grace_seconds)
        lost_hold = _validate_positive_float("lost_hold_seconds", self.lost_hold_seconds)
        presence_expiry = _validate_positive_float("presence_expiry_seconds", self.presence_expiry_seconds)

        if presence_expiry < missed_grace:
            raise ValueError(
                f"presence_expiry_seconds={presence_expiry!r} debe ser >= "
                f"missed_grace_seconds={missed_grace!r}."
            )

        object.__setattr__(self, "min_confirm_frames", min_confirm)
        object.__setattr__(self, "confirm_window_seconds", confirm_window)
        object.__setattr__(self, "max_missed_frames", max_missed)
        object.__setattr__(self, "missed_grace_seconds", missed_grace)
        object.__setattr__(self, "lost_hold_seconds", lost_hold)
        object.__setattr__(self, "presence_expiry_seconds", presence_expiry)

    @classmethod
    def from_engine_settings(cls, settings: VisionEngineSettings) -> "TemporalStateConfig":
        """Construye ``TemporalStateConfig`` desde ``VisionEngineSettings``."""
        if not isinstance(settings, VisionEngineSettings):
            raise TypeError("settings debe ser una instancia de VisionEngineSettings.")
        return cls(
            min_confirm_frames=settings.temporal_min_confirm_frames,
            confirm_window_seconds=settings.temporal_confirm_window_seconds,
            max_missed_frames=settings.temporal_max_missed_frames,
            missed_grace_seconds=settings.temporal_missed_grace_seconds,
            lost_hold_seconds=settings.temporal_lost_hold_seconds,
            presence_expiry_seconds=settings.temporal_presence_expiry_seconds,
        )


@dataclass(frozen=True)
class TemporalStateSnapshot:
    """Instantánea inmutable del estado temporal de una cámara."""

    camera_id: str
    detection_status: TemporalDetectionStatus
    vehicle_present: bool
    raw_vehicle_detected: bool
    roi_vehicle_detected: bool
    frame_id: Optional[str]
    frame_sequence: Optional[int]
    frame_accepted: bool
    rejection_reason: Optional[str]
    consecutive_positive_frames: int
    consecutive_missed_frames: int
    total_frames_processed: int
    last_frame_monotonic: Optional[float]
    last_positive_monotonic: Optional[float]
    candidate_started_monotonic: Optional[float]
    lost_started_monotonic: Optional[float]
    evaluated_at_monotonic: float
    wall_timestamp: Optional[float]
    vehicle_type: Optional[str]
    vehicle_confidence: Optional[float]
    transition_reason: str
    hold_reason: Optional[str]
    is_stale: bool
    last_reset_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializa el snapshot a un diccionario plano compatible con JSON."""
        return {
            "camera_id": self.camera_id,
            "detection_status": self.detection_status.value,
            "vehicle_present": self.vehicle_present,
            "raw_vehicle_detected": self.raw_vehicle_detected,
            "roi_vehicle_detected": self.roi_vehicle_detected,
            "frame_id": self.frame_id,
            "frame_sequence": self.frame_sequence,
            "frame_accepted": self.frame_accepted,
            "rejection_reason": self.rejection_reason,
            "consecutive_positive_frames": self.consecutive_positive_frames,
            "consecutive_missed_frames": self.consecutive_missed_frames,
            "total_frames_processed": self.total_frames_processed,
            "last_frame_monotonic": self.last_frame_monotonic,
            "last_positive_monotonic": self.last_positive_monotonic,
            "candidate_started_monotonic": self.candidate_started_monotonic,
            "lost_started_monotonic": self.lost_started_monotonic,
            "evaluated_at_monotonic": self.evaluated_at_monotonic,
            "wall_timestamp": self.wall_timestamp,
            "vehicle_type": self.vehicle_type,
            "vehicle_confidence": self.vehicle_confidence,
            "transition_reason": self.transition_reason,
            "hold_reason": self.hold_reason,
            "is_stale": self.is_stale,
            "last_reset_reason": self.last_reset_reason,
        }


@dataclass
class _CameraSlotState:
    """Estado mutable interno aislado por cámara."""

    camera_id: str
    status: TemporalDetectionStatus = TemporalDetectionStatus.NO_VEHICLE_DETECTED
    raw_vehicle_detected: bool = False
    roi_vehicle_detected: bool = False
    last_frame_id: Optional[str] = None
    last_sequence: Optional[int] = None
    seen_frame_order: Deque[str] = field(default_factory=deque)
    seen_frame_set: Set[str] = field(default_factory=set)
    consecutive_positive_frames: int = 0
    consecutive_missed_frames: int = 0
    total_frames_processed: int = 0
    last_frame_monotonic: Optional[float] = None
    last_positive_monotonic: Optional[float] = None
    candidate_started_monotonic: Optional[float] = None
    lost_started_monotonic: Optional[float] = None
    last_wall_timestamp: Optional[float] = None
    vehicle_type: Optional[str] = None
    vehicle_confidence: Optional[float] = None
    transition_reason: str = "IDLE_UNINITIALIZED"
    hold_reason: Optional[str] = None
    is_stale: bool = False
    last_reset_reason: Optional[str] = None

    def record_frame_identity(self, frame_id: Optional[str], frame_sequence: int) -> None:
        self.last_frame_id = frame_id
        self.last_sequence = frame_sequence
        if frame_id is None:
            return
        if frame_id not in self.seen_frame_set:
            if len(self.seen_frame_order) >= _MAX_SEEN_FRAME_IDS:
                evicted = self.seen_frame_order.popleft()
                self.seen_frame_set.discard(evicted)
            self.seen_frame_order.append(frame_id)
            self.seen_frame_set.add(frame_id)

    def clear_all(self, reset_reason: Optional[str]) -> None:
        self.status = TemporalDetectionStatus.NO_VEHICLE_DETECTED
        self.raw_vehicle_detected = False
        self.roi_vehicle_detected = False
        self.last_frame_id = None
        self.last_sequence = None
        self.seen_frame_order.clear()
        self.seen_frame_set.clear()
        self.consecutive_positive_frames = 0
        self.consecutive_missed_frames = 0
        self.total_frames_processed = 0
        self.last_frame_monotonic = None
        self.last_positive_monotonic = None
        self.candidate_started_monotonic = None
        self.lost_started_monotonic = None
        self.last_wall_timestamp = None
        self.vehicle_type = None
        self.vehicle_confidence = None
        self.hold_reason = None
        self.is_stale = False
        self.last_reset_reason = reset_reason
        self.transition_reason = f"CAMERA_RESET:{reset_reason}" if reset_reason else "IDLE_UNINITIALIZED"


def _normalize_camera_id(camera_id: str) -> str:
    if not isinstance(camera_id, str) or not camera_id.strip():
        raise ValueError("camera_id debe ser una cadena no vacía.")
    return camera_id.strip().upper()


def _validate_monotonic_value(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"now_monotonic={value!r} debe ser un número finito.")
    mono = float(value)
    if not math.isfinite(mono):
        raise ValueError(f"now_monotonic={value!r} debe ser finito.")
    return mono


def _resolve_frame_identity(
    slot: _CameraSlotState,
    frame_id: Optional[Union[int, str]],
    frame_sequence: Optional[int],
) -> tuple[Optional[str], int, Optional[int]]:
    """
    Valida y normaliza la identidad/secuencia del frame entrante.

    Retorna ``(effective_frame_id, effective_sequence, explicit_sequence_or_none)``.
    """
    explicit_seq: Optional[int] = None
    if frame_sequence is not None:
        if isinstance(frame_sequence, bool) or not isinstance(frame_sequence, int) or frame_sequence < 0:
            raise ValueError(f"frame_sequence={frame_sequence!r} debe ser un entero >= 0.")
        explicit_seq = int(frame_sequence)

    explicit_fid: Optional[str] = None
    if frame_id is not None:
        if isinstance(frame_id, bool):
            raise ValueError("frame_id no puede ser bool.")
        if isinstance(frame_id, int):
            if frame_id < 0:
                raise ValueError(f"frame_id={frame_id!r} entero debe ser >= 0.")
            if explicit_seq is None:
                explicit_seq = int(frame_id)
            explicit_fid = str(frame_id)
        elif isinstance(frame_id, str):
            stripped = frame_id.strip()
            if not stripped:
                raise ValueError("frame_id no puede ser una cadena vacía.")
            explicit_fid = stripped
        else:
            raise ValueError(f"frame_id={frame_id!r} debe ser str o int.")

    effective_seq = (
        explicit_seq
        if explicit_seq is not None
        else (1 if slot.last_sequence is None else slot.last_sequence + 1)
    )
    effective_fid = explicit_fid if explicit_fid is not None else f"{slot.camera_id}:seq:{effective_seq}"
    return effective_fid, effective_seq, explicit_seq


def _snapshot_from_slot(
    slot: _CameraSlotState,
    *,
    evaluated_at_monotonic: float,
    frame_accepted: bool = True,
    rejection_reason: Optional[str] = None,
) -> TemporalStateSnapshot:
    return TemporalStateSnapshot(
        camera_id=slot.camera_id,
        detection_status=slot.status,
        vehicle_present=(slot.status == TemporalDetectionStatus.VEHICLE_PRESENT),
        raw_vehicle_detected=slot.raw_vehicle_detected,
        roi_vehicle_detected=slot.roi_vehicle_detected,
        frame_id=slot.last_frame_id,
        frame_sequence=slot.last_sequence,
        frame_accepted=frame_accepted,
        rejection_reason=rejection_reason,
        consecutive_positive_frames=slot.consecutive_positive_frames,
        consecutive_missed_frames=slot.consecutive_missed_frames,
        total_frames_processed=slot.total_frames_processed,
        last_frame_monotonic=slot.last_frame_monotonic,
        last_positive_monotonic=slot.last_positive_monotonic,
        candidate_started_monotonic=slot.candidate_started_monotonic,
        lost_started_monotonic=slot.lost_started_monotonic,
        evaluated_at_monotonic=evaluated_at_monotonic,
        wall_timestamp=slot.last_wall_timestamp,
        vehicle_type=slot.vehicle_type,
        vehicle_confidence=slot.vehicle_confidence,
        transition_reason=slot.transition_reason,
        hold_reason=slot.hold_reason,
        is_stale=slot.is_stale,
        last_reset_reason=slot.last_reset_reason,
    )


class CameraTemporalStateTracker:
    """
    Gestor thread-safe de estados temporales aislados por cámara.

    Garantiza:
    - Reloj monotónico inyectable (inmune a saltos del reloj de pared).
    - Bloqueo reentrante (``RLock``) con aislamiento estricto por cámara.
    - Rechazo de frames duplicados o fuera de orden sin mutar estado.
    - Consulta (``get_snapshot``) y verificación de expiración (``expire_if_stale``)
      sin efectos secundarios en los contadores de frames ni de misses.
    """

    def __init__(
        self,
        config: Optional[TemporalStateConfig] = None,
        clock_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config or TemporalStateConfig()
        self._clock_fn = clock_fn
        self._lock = threading.RLock()
        self._slots: Dict[str, _CameraSlotState] = {}

    @property
    def config(self) -> TemporalStateConfig:
        """Retorna la configuración temporal inmutable activa."""
        return self._config

    def _now(self, now_monotonic: Optional[float]) -> float:
        raw = self._clock_fn() if now_monotonic is None else now_monotonic
        return _validate_monotonic_value(raw)

    def _apply_elapsed_expiry_locked(
        self,
        slot: _CameraSlotState,
        now_mono: float,
        *,
        mark_stale_on_silence: bool,
    ) -> None:
        """
        Evalúa expiraciones puramente temporales sobre ``slot`` basadas en la
        ausencia real de frames nuevos (``now_mono - last_frame_monotonic``),
        sin alterar ``consecutive_positive_frames``, ``consecutive_missed_frames``
        ni ``total_frames_processed``.
        """
        cfg = self._config
        elapsed_no_frames: Optional[float] = (
            max(0.0, now_mono - slot.last_frame_monotonic)
            if slot.last_frame_monotonic is not None
            else None
        )
        if elapsed_no_frames is not None and mark_stale_on_silence:
            if _elapsed_reached(elapsed_no_frames, cfg.presence_expiry_seconds):
                slot.is_stale = True

        if slot.status == TemporalDetectionStatus.VEHICLE_PRESENT:
            if elapsed_no_frames is not None and _elapsed_reached(
                elapsed_no_frames,
                cfg.presence_expiry_seconds,
            ):
                slot.hold_reason = None
                if mark_stale_on_silence:
                    slot.is_stale = True
                slot.status = TemporalDetectionStatus.VEHICLE_LOST
                slot.lost_started_monotonic = now_mono
                slot.transition_reason = "LOST_STALE_NO_FRAMES"
            return

        if slot.status == TemporalDetectionStatus.VEHICLE_LOST:
            if (
                slot.lost_started_monotonic is not None
                and _elapsed_reached(
                    max(0.0, now_mono - slot.lost_started_monotonic),
                    cfg.lost_hold_seconds,
                )
            ):
                self._transition_lost_to_idle_locked(slot, "LOST_HOLD_EXPIRED_TO_IDLE")
            return

        if slot.status == TemporalDetectionStatus.VEHICLE_CANDIDATE:
            if (
                slot.candidate_started_monotonic is not None
                and not _elapsed_within(
                    max(0.0, now_mono - slot.candidate_started_monotonic),
                    cfg.confirm_window_seconds,
                )
            ):
                slot.status = TemporalDetectionStatus.NO_VEHICLE_DETECTED
                slot.candidate_started_monotonic = None
                slot.vehicle_type = None
                slot.vehicle_confidence = None
                slot.hold_reason = None
                slot.transition_reason = "CANDIDATE_EXPIRED_STALE"

    def _transition_lost_to_idle_locked(self, slot: _CameraSlotState, reason: str) -> None:
        slot.status = TemporalDetectionStatus.NO_VEHICLE_DETECTED
        slot.candidate_started_monotonic = None
        slot.lost_started_monotonic = None
        slot.hold_reason = None
        slot.vehicle_type = None
        slot.vehicle_confidence = None
        slot.transition_reason = reason

    def update(
        self,
        camera_id: str,
        roi_vehicle_detected: bool,
        *,
        raw_vehicle_detected: Optional[bool] = None,
        frame_id: Optional[Union[int, str]] = None,
        frame_sequence: Optional[int] = None,
        vehicle_type: Optional[str] = None,
        vehicle_confidence: Optional[float] = None,
        wall_timestamp: Optional[float] = None,
        now_monotonic: Optional[float] = None,
    ) -> TemporalStateSnapshot:
        """
        Procesa la evaluación de un nuevo frame de ``camera_id`` y actualiza su FSM.

        Rechaza frames duplicados o con secuencia regresiva sin modificar contadores.
        """
        norm_cam = _normalize_camera_id(camera_id)
        now_mono = self._now(now_monotonic)
        roi_detected = bool(roi_vehicle_detected)
        raw_detected = roi_detected if raw_vehicle_detected is None else bool(raw_vehicle_detected)

        with self._lock:
            slot = self._slots.get(norm_cam)
            if slot is None:
                slot = _CameraSlotState(camera_id=norm_cam)
                self._slots[norm_cam] = slot

            eff_fid, eff_seq, explicit_seq = _resolve_frame_identity(slot, frame_id, frame_sequence)

            # Verificar identidad y orden monotónico de secuencia antes de mutar estado.
            if (
                (frame_id is not None and eff_fid in slot.seen_frame_set)
                or (
                    explicit_seq is not None
                    and slot.last_sequence is not None
                    and explicit_seq == slot.last_sequence
                )
            ):
                return TemporalStateSnapshot(
                    camera_id=norm_cam,
                    detection_status=slot.status,
                    vehicle_present=(slot.status == TemporalDetectionStatus.VEHICLE_PRESENT),
                    raw_vehicle_detected=raw_detected,
                    roi_vehicle_detected=roi_detected,
                    frame_id=eff_fid,
                    frame_sequence=explicit_seq if explicit_seq is not None else slot.last_sequence,
                    frame_accepted=False,
                    rejection_reason="DUPLICATE_FRAME",
                    consecutive_positive_frames=slot.consecutive_positive_frames,
                    consecutive_missed_frames=slot.consecutive_missed_frames,
                    total_frames_processed=slot.total_frames_processed,
                    last_frame_monotonic=slot.last_frame_monotonic,
                    last_positive_monotonic=slot.last_positive_monotonic,
                    candidate_started_monotonic=slot.candidate_started_monotonic,
                    lost_started_monotonic=slot.lost_started_monotonic,
                    evaluated_at_monotonic=now_mono,
                    wall_timestamp=slot.last_wall_timestamp,
                    vehicle_type=slot.vehicle_type,
                    vehicle_confidence=slot.vehicle_confidence,
                    transition_reason="REJECTED_DUPLICATE_FRAME",
                    hold_reason=slot.hold_reason,
                    is_stale=slot.is_stale,
                    last_reset_reason=slot.last_reset_reason,
                )

            if (
                explicit_seq is not None
                and slot.last_sequence is not None
                and explicit_seq < slot.last_sequence
            ):
                return TemporalStateSnapshot(
                    camera_id=norm_cam,
                    detection_status=slot.status,
                    vehicle_present=(slot.status == TemporalDetectionStatus.VEHICLE_PRESENT),
                    raw_vehicle_detected=raw_detected,
                    roi_vehicle_detected=roi_detected,
                    frame_id=eff_fid,
                    frame_sequence=explicit_seq,
                    frame_accepted=False,
                    rejection_reason="OUT_OF_ORDER_FRAME",
                    consecutive_positive_frames=slot.consecutive_positive_frames,
                    consecutive_missed_frames=slot.consecutive_missed_frames,
                    total_frames_processed=slot.total_frames_processed,
                    last_frame_monotonic=slot.last_frame_monotonic,
                    last_positive_monotonic=slot.last_positive_monotonic,
                    candidate_started_monotonic=slot.candidate_started_monotonic,
                    lost_started_monotonic=slot.lost_started_monotonic,
                    evaluated_at_monotonic=now_mono,
                    wall_timestamp=slot.last_wall_timestamp,
                    vehicle_type=slot.vehicle_type,
                    vehicle_confidence=slot.vehicle_confidence,
                    transition_reason="REJECTED_OUT_OF_ORDER_FRAME",
                    hold_reason=slot.hold_reason,
                    is_stale=slot.is_stale,
                    last_reset_reason=slot.last_reset_reason,
                )

            # Frame aceptado: cerrar expiraciones previas de ventana/hold antes de evaluar.
            cfg = self._config
            expired_lost_on_arrival = False
            if slot.status == TemporalDetectionStatus.VEHICLE_LOST:
                self._apply_elapsed_expiry_locked(slot, now_mono, mark_stale_on_silence=False)
                expired_lost_on_arrival = slot.status == TemporalDetectionStatus.NO_VEHICLE_DETECTED
            elif (
                slot.status == TemporalDetectionStatus.VEHICLE_PRESENT
                and slot.last_positive_monotonic is not None
            ):
                ref_pos = slot.last_positive_monotonic
                elapsed_from_pos = max(0.0, now_mono - ref_pos)
                if _elapsed_reached(elapsed_from_pos, cfg.presence_expiry_seconds + cfg.lost_hold_seconds):
                    # Silencio total que consumió tanto la expiración absoluta como el hold de LOST.
                    self._transition_lost_to_idle_locked(slot, "LOST_HOLD_EXPIRED_TO_IDLE")
                    expired_lost_on_arrival = True
                elif roi_detected and _elapsed_reached(elapsed_from_pos, cfg.presence_expiry_seconds):
                    # Expiró por límite absoluto antes de la llegada tardía de un positivo en ventana LOST.
                    self._apply_elapsed_expiry_locked(slot, now_mono, mark_stale_on_silence=False)

            slot.record_frame_identity(eff_fid, eff_seq)
            slot.total_frames_processed += 1
            slot.last_frame_monotonic = now_mono
            slot.is_stale = False
            slot.raw_vehicle_detected = raw_detected
            slot.roi_vehicle_detected = roi_detected
            if wall_timestamp is not None:
                slot.last_wall_timestamp = float(wall_timestamp)

            self._advance_state_locked(
                slot,
                roi_detected=roi_detected,
                now_mono=now_mono,
                vehicle_type=vehicle_type,
                vehicle_confidence=vehicle_confidence,
            )
            if expired_lost_on_arrival and not roi_detected:
                slot.transition_reason = "LOST_HOLD_EXPIRED_TO_IDLE"
            return _snapshot_from_slot(slot, evaluated_at_monotonic=now_mono)

    def _advance_state_locked(
        self,
        slot: _CameraSlotState,
        *,
        roi_detected: bool,
        now_mono: float,
        vehicle_type: Optional[str],
        vehicle_confidence: Optional[float],
    ) -> None:
        cfg = self._config

        if slot.status == TemporalDetectionStatus.NO_VEHICLE_DETECTED:
            if not roi_detected:
                slot.consecutive_positive_frames = 0
                slot.consecutive_missed_frames = 0
                slot.hold_reason = None
                slot.vehicle_type = None
                slot.vehicle_confidence = None
                slot.transition_reason = "IDLE_NO_DETECTION"
                return

            slot.candidate_started_monotonic = now_mono
            slot.last_positive_monotonic = now_mono
            slot.consecutive_positive_frames = 1
            slot.consecutive_missed_frames = 0
            slot.hold_reason = None
            slot.vehicle_type = vehicle_type
            slot.vehicle_confidence = vehicle_confidence
            if 1 >= cfg.min_confirm_frames:
                slot.status = TemporalDetectionStatus.VEHICLE_PRESENT
                slot.transition_reason = "CONFIRMED_PRESENCE"
            else:
                slot.status = TemporalDetectionStatus.VEHICLE_CANDIDATE
                slot.transition_reason = "CANDIDATE_STARTED"
            return

        if slot.status == TemporalDetectionStatus.VEHICLE_CANDIDATE:
            if not roi_detected:
                slot.status = TemporalDetectionStatus.NO_VEHICLE_DETECTED
                slot.consecutive_positive_frames = 0
                slot.consecutive_missed_frames = 0
                slot.candidate_started_monotonic = None
                slot.vehicle_type = None
                slot.vehicle_confidence = None
                slot.hold_reason = None
                slot.transition_reason = "CANDIDATE_EXPIRED_NEGATIVE"
                return

            start_mono = (
                slot.candidate_started_monotonic
                if slot.candidate_started_monotonic is not None
                else now_mono
            )
            elapsed_cand = max(0.0, now_mono - start_mono)
            slot.vehicle_type = vehicle_type if vehicle_type is not None else slot.vehicle_type
            slot.vehicle_confidence = (
                float(vehicle_confidence)
                if vehicle_confidence is not None
                else slot.vehicle_confidence
            )
            if _elapsed_within(elapsed_cand, cfg.confirm_window_seconds):
                slot.consecutive_positive_frames += 1
                slot.last_positive_monotonic = now_mono
                slot.consecutive_missed_frames = 0
                if slot.consecutive_positive_frames >= cfg.min_confirm_frames:
                    slot.status = TemporalDetectionStatus.VEHICLE_PRESENT
                    slot.lost_started_monotonic = None
                    slot.hold_reason = None
                    slot.transition_reason = "CONFIRMED_PRESENCE"
                else:
                    slot.transition_reason = "CANDIDATE_ACCUMULATING"
            else:
                slot.candidate_started_monotonic = now_mono
                slot.last_positive_monotonic = now_mono
                slot.consecutive_positive_frames = 1
                slot.consecutive_missed_frames = 0
                if 1 >= cfg.min_confirm_frames:
                    slot.status = TemporalDetectionStatus.VEHICLE_PRESENT
                    slot.transition_reason = "CONFIRMED_PRESENCE"
                else:
                    slot.transition_reason = "CANDIDATE_WINDOW_RESET"
            return

        if slot.status == TemporalDetectionStatus.VEHICLE_PRESENT:
            if roi_detected:
                slot.consecutive_positive_frames += 1
                slot.consecutive_missed_frames = 0
                slot.last_positive_monotonic = now_mono
                slot.hold_reason = None
                if vehicle_type is not None:
                    slot.vehicle_type = vehicle_type
                if vehicle_confidence is not None:
                    slot.vehicle_confidence = float(vehicle_confidence)
                slot.transition_reason = "PRESENCE_SUSTAINED"
                return

            slot.consecutive_positive_frames = 0
            slot.consecutive_missed_frames += 1
            ref_pos = slot.last_positive_monotonic if slot.last_positive_monotonic is not None else now_mono
            elapsed_miss = max(0.0, now_mono - ref_pos)

            if _elapsed_reached(elapsed_miss, cfg.presence_expiry_seconds):
                slot.status = TemporalDetectionStatus.VEHICLE_LOST
                slot.lost_started_monotonic = now_mono
                slot.hold_reason = None
                slot.transition_reason = "LOST_ABSOLUTE_EXPIRY"
                return

            frames_exhausted = slot.consecutive_missed_frames >= cfg.max_missed_frames
            time_exhausted = _elapsed_reached(elapsed_miss, cfg.missed_grace_seconds)

            if frames_exhausted and time_exhausted:
                slot.status = TemporalDetectionStatus.VEHICLE_LOST
                slot.lost_started_monotonic = now_mono
                slot.hold_reason = None
                slot.transition_reason = "LOST_MISS_BUDGET_EXHAUSTED"
            elif frames_exhausted and not time_exhausted:
                slot.hold_reason = "HOLD_BY_TIME_GRACE"
                slot.transition_reason = "HOLD_BY_TIME_GRACE"
            elif not frames_exhausted and time_exhausted:
                slot.hold_reason = "HOLD_BY_FRAME_BUDGET"
                slot.transition_reason = "HOLD_BY_FRAME_BUDGET"
            else:
                slot.hold_reason = "WITHIN_BOTH_BOUNDS"
                slot.transition_reason = "HOLD_WITHIN_BOTH_BOUNDS"
            return

        if slot.status == TemporalDetectionStatus.VEHICLE_LOST:
            if roi_detected:
                slot.status = TemporalDetectionStatus.VEHICLE_PRESENT
                slot.consecutive_positive_frames = 1
                slot.consecutive_missed_frames = 0
                slot.last_positive_monotonic = now_mono
                slot.lost_started_monotonic = None
                slot.hold_reason = None
                if vehicle_type is not None:
                    slot.vehicle_type = vehicle_type
                if vehicle_confidence is not None:
                    slot.vehicle_confidence = float(vehicle_confidence)
                slot.transition_reason = "RECOVERED_FROM_LOST"
            else:
                slot.consecutive_positive_frames = 0
                slot.consecutive_missed_frames += 1
                slot.hold_reason = None
                slot.transition_reason = "LOST_HOLD_ACTIVE"

    def expire_if_stale(
        self,
        camera_id: str,
        *,
        now_monotonic: Optional[float] = None,
    ) -> TemporalStateSnapshot:
        """
        Evalúa expiraciones por ausencia de frames nuevos en ``camera_id``.

        Nunca incrementa ni reinicia ``total_frames_processed``,
        ``consecutive_missed_frames`` ni ``consecutive_positive_frames``.
        """
        norm_cam = _normalize_camera_id(camera_id)
        now_mono = self._now(now_monotonic)

        with self._lock:
            slot = self._slots.get(norm_cam)
            if slot is None:
                return _snapshot_from_slot(_CameraSlotState(camera_id=norm_cam), evaluated_at_monotonic=now_mono)
            self._apply_elapsed_expiry_locked(slot, now_mono, mark_stale_on_silence=True)
            return _snapshot_from_slot(slot, evaluated_at_monotonic=now_mono)

    def get_snapshot(
        self,
        camera_id: str,
        *,
        now_monotonic: Optional[float] = None,
    ) -> TemporalStateSnapshot:
        """
        Consulta de solo lectura del estado actual de ``camera_id``.

        No modifica estados, contadores, timestamps ni secuencias.
        """
        norm_cam = _normalize_camera_id(camera_id)
        now_mono = self._now(now_monotonic)

        with self._lock:
            slot = self._slots.get(norm_cam)
            if slot is None:
                return _snapshot_from_slot(_CameraSlotState(camera_id=norm_cam), evaluated_at_monotonic=now_mono)
            return _snapshot_from_slot(slot, evaluated_at_monotonic=now_mono)

    def reset_camera(
        self,
        camera_id: str,
        reason: str = "MANUAL_RESET",
        *,
        now_monotonic: Optional[float] = None,
    ) -> TemporalStateSnapshot:
        """
        Elimina todos los contadores, historial de secuencia y metadatos temporales
        de ``camera_id``, devolviendo la cámara a ``NO_VEHICLE_DETECTED``.
        """
        norm_cam = _normalize_camera_id(camera_id)
        now_mono = self._now(now_monotonic)
        clean_reason = str(reason or "MANUAL_RESET").strip() or "MANUAL_RESET"

        with self._lock:
            slot = self._slots.get(norm_cam)
            if slot is None:
                slot = _CameraSlotState(camera_id=norm_cam)
                self._slots[norm_cam] = slot
            slot.clear_all(clean_reason)
            return _snapshot_from_slot(slot, evaluated_at_monotonic=now_mono)


__all__ = [
    "CameraTemporalStateTracker",
    "TemporalDetectionStatus",
    "TemporalStateConfig",
    "TemporalStateSnapshot",
]
