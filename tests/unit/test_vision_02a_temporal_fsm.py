"""
tests.unit.test_vision_02a_temporal_fsm
=====================================
Pruebas unitarias deterministas de la máquina de estados temporal (VIGIA-VISION-02A).

Utiliza exclusivamente un reloj monotónico falso inyectado (sin ``time.sleep``)
y no depende de YOLO, captura OpenCV, PostgreSQL ni red HTTP.
"""

from __future__ import annotations

import math
import sys
import threading
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Dict, List

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from VIGIA_Vision.config.engine_settings import VisionEngineSettings
from VIGIA_Vision.runtime.temporal_state import (
    CameraTemporalStateTracker,
    TemporalDetectionStatus,
    TemporalStateConfig,
    TemporalStateSnapshot,
)


class FakeMonotonicClock:
    """Reloj monotónico determinista controlable en memoria."""

    def __init__(self, initial: float = 100.0) -> None:
        self._now = float(initial)
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            return self._now

    def advance(self, seconds: float) -> float:
        if seconds < 0.0:
            raise ValueError("Un reloj monotónico no retrocede.")
        with self._lock:
            self._now += float(seconds)
            return self._now

    def set(self, value: float) -> float:
        with self._lock:
            if value < self._now:
                raise ValueError("Un reloj monotónico no retrocede.")
            self._now = float(value)
            return self._now


class TestVision02ATemporalFSM(unittest.TestCase):
    """Suite unitaria aislada para CameraTemporalStateTracker y TemporalStateConfig."""

    def setUp(self) -> None:
        self.clock = FakeMonotonicClock(1000.0)
        self.tracker = CameraTemporalStateTracker(
            config=TemporalStateConfig(),
            clock_fn=self.clock,
        )

    def _confirm_vehicle(self, camera_id: str = "CAM-ENTRADA", seq_start: int = 1) -> TemporalStateSnapshot:
        """Lleva una cámara en reposo a VEHICLE_PRESENT en 2 frames dentro de ventana."""
        s1 = self.tracker.update(
            camera_id,
            True,
            raw_vehicle_detected=True,
            frame_sequence=seq_start,
            vehicle_type="AUTOMOVIL",
            vehicle_confidence=0.91,
        )
        self.assertEqual(s1.detection_status, TemporalDetectionStatus.VEHICLE_CANDIDATE)
        self.clock.advance(0.1)
        s2 = self.tracker.update(
            camera_id,
            True,
            raw_vehicle_detected=True,
            frame_sequence=seq_start + 1,
            vehicle_type="AUTOMOVIL",
            vehicle_confidence=0.93,
        )
        self.assertEqual(s2.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
        self.assertTrue(s2.vehicle_present)
        return s2

    def test_01_default_config_and_engine_settings_compatibility(self) -> None:
        """Verifica defaults obligatorios, inmutabilidad y validaciones en ambos DTOs."""
        settings = VisionEngineSettings()
        self.assertEqual(settings.vehicle_confidence_threshold, 0.70)
        self.assertEqual(settings.temporal_min_confirm_frames, 2)
        self.assertAlmostEqual(settings.temporal_confirm_window_seconds, 1.5)
        self.assertEqual(settings.temporal_max_missed_frames, 4)
        self.assertAlmostEqual(settings.temporal_missed_grace_seconds, 1.2)
        self.assertAlmostEqual(settings.temporal_lost_hold_seconds, 0.8)
        self.assertAlmostEqual(settings.temporal_presence_expiry_seconds, 6.0)

        cfg = TemporalStateConfig.from_engine_settings(settings)
        self.assertEqual(cfg.min_confirm_frames, 2)
        self.assertAlmostEqual(cfg.confirm_window_seconds, 1.5)
        self.assertEqual(cfg.max_missed_frames, 4)
        self.assertAlmostEqual(cfg.missed_grace_seconds, 1.2)
        self.assertAlmostEqual(cfg.lost_hold_seconds, 0.8)
        self.assertAlmostEqual(cfg.presence_expiry_seconds, 6.0)

        with self.assertRaises(FrozenInstanceError):
            cfg.min_confirm_frames = 5  # type: ignore[misc]

        for bad_kwargs in (
            {"min_confirm_frames": 0},
            {"min_confirm_frames": True},
            {"confirm_window_seconds": 0.0},
            {"confirm_window_seconds": float("nan")},
            {"confirm_window_seconds": float("inf")},
            {"max_missed_frames": 0},
            {"missed_grace_seconds": -0.5},
            {"lost_hold_seconds": 0.0},
            {"missed_grace_seconds": 5.0, "presence_expiry_seconds": 4.0},
        ):
            with self.assertRaises(ValueError):
                TemporalStateConfig(**bad_kwargs)

        with self.assertRaises(ValueError):
            VisionEngineSettings(temporal_presence_expiry_seconds=1.0, temporal_missed_grace_seconds=2.0)

    def test_02_full_state_lifecycle_transitions(self) -> None:
        """Recorre NO_VEHICLE_DETECTED -> CANDIDATE -> PRESENT -> LOST -> NO_VEHICLE_DETECTED."""
        s0 = self.tracker.get_snapshot("CAM-ENTRADA")
        self.assertEqual(s0.detection_status, TemporalDetectionStatus.NO_VEHICLE_DETECTED)
        self.assertFalse(s0.vehicle_present)

        s1 = self.tracker.update(
            "CAM-ENTRADA",
            True,
            frame_sequence=1,
            vehicle_type="CAMIONETA",
            vehicle_confidence=0.88,
        )
        self.assertEqual(s1.detection_status, TemporalDetectionStatus.VEHICLE_CANDIDATE)
        self.assertFalse(s1.vehicle_present)

        self.clock.advance(0.1)
        s2 = self.tracker.update(
            "CAM-ENTRADA",
            True,
            frame_sequence=2,
            vehicle_type="CAMIONETA",
            vehicle_confidence=0.90,
        )
        self.assertEqual(s2.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
        self.assertTrue(s2.vehicle_present)
        self.assertEqual(s2.vehicle_type, "CAMIONETA")

        # 4 negativos superando 1.2s -> VEHICLE_LOST
        for seq, dt in ((3, 0.4), (4, 0.4), (5, 0.4), (6, 0.1)):
            self.clock.advance(dt)
            snap = self.tracker.update("CAM-ENTRADA", False, frame_sequence=seq)

        self.assertEqual(snap.detection_status, TemporalDetectionStatus.VEHICLE_LOST)
        self.assertFalse(snap.vehicle_present)

        # Durante lost_hold_seconds (0.8s) permanece VEHICLE_LOST
        self.clock.advance(0.4)
        snap_hold = self.tracker.update("CAM-ENTRADA", False, frame_sequence=7)
        self.assertEqual(snap_hold.detection_status, TemporalDetectionStatus.VEHICLE_LOST)
        self.assertFalse(snap_hold.vehicle_present)

        # Tras cumplir >= 0.8s desde inicio de VEHICLE_LOST pasa a NO_VEHICLE_DETECTED
        self.clock.advance(0.4)
        snap_idle = self.tracker.update("CAM-ENTRADA", False, frame_sequence=8)
        self.assertEqual(snap_idle.detection_status, TemporalDetectionStatus.NO_VEHICLE_DETECTED)
        self.assertFalse(snap_idle.vehicle_present)
        self.assertIsNone(snap_idle.vehicle_type)
        self.assertIsNone(snap_idle.vehicle_confidence)

    def test_03_single_isolated_positive_does_not_confirm_and_raw_outside_roi_stays_idle(self) -> None:
        """Un positivo aislado solo pasa a CANDIDATE; detección fuera de ROI no abre candidato."""
        raw_only = self.tracker.update(
            "CAM-ENTRADA",
            False,
            raw_vehicle_detected=True,
            frame_sequence=1,
        )
        self.assertEqual(raw_only.detection_status, TemporalDetectionStatus.NO_VEHICLE_DETECTED)
        self.assertTrue(raw_only.raw_vehicle_detected)
        self.assertFalse(raw_only.roi_vehicle_detected)
        self.assertFalse(raw_only.vehicle_present)

        cand = self.tracker.update("CAM-ENTRADA", True, frame_sequence=2, vehicle_type="AUTOMOVIL")
        self.assertEqual(cand.detection_status, TemporalDetectionStatus.VEHICLE_CANDIDATE)
        self.assertFalse(cand.vehicle_present)
        self.assertEqual(cand.consecutive_positive_frames, 1)

        self.clock.advance(0.067)
        neg = self.tracker.update("CAM-ENTRADA", False, frame_sequence=3)
        self.assertEqual(neg.detection_status, TemporalDetectionStatus.NO_VEHICLE_DETECTED)
        self.assertFalse(neg.vehicle_present)
        self.assertEqual(neg.consecutive_positive_frames, 0)
        self.assertEqual(neg.transition_reason, "CANDIDATE_EXPIRED_NEGATIVE")

    def test_04_two_positives_within_confirm_window_boundary_inclusive(self) -> None:
        """Dos positivos en dt == 1.5s exactos confirman VEHICLE_PRESENT."""
        s1 = self.tracker.update("CAM-ENTRADA", True, frame_sequence=1, vehicle_type="CAMION")
        self.assertEqual(s1.detection_status, TemporalDetectionStatus.VEHICLE_CANDIDATE)

        self.clock.advance(1.5)
        s2 = self.tracker.update("CAM-ENTRADA", True, frame_sequence=2, vehicle_type="CAMION")
        self.assertEqual(s2.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
        self.assertTrue(s2.vehicle_present)
        self.assertEqual(s2.consecutive_positive_frames, 2)
        self.assertEqual(s2.transition_reason, "CONFIRMED_PRESENCE")

    def test_05_positives_outside_confirm_window_reset_window(self) -> None:
        """Positivos separados por > 1.5s reinician la ventana y no confirman presencia prematura."""
        s1 = self.tracker.update("CAM-ENTRADA", True, frame_sequence=1, vehicle_type="AUTOMOVIL")
        self.assertEqual(s1.detection_status, TemporalDetectionStatus.VEHICLE_CANDIDATE)
        first_cand_ts = s1.candidate_started_monotonic

        # 1.6s > 1.5s: fuera de ventana -> reinicia candidato
        self.clock.advance(1.6)
        s2 = self.tracker.update("CAM-ENTRADA", True, frame_sequence=2, vehicle_type="AUTOMOVIL")
        self.assertEqual(s2.detection_status, TemporalDetectionStatus.VEHICLE_CANDIDATE)
        self.assertFalse(s2.vehicle_present)
        self.assertEqual(s2.consecutive_positive_frames, 1)
        self.assertEqual(s2.transition_reason, "CANDIDATE_WINDOW_RESET")
        self.assertGreater(s2.candidate_started_monotonic, first_cand_ts)

        # Un segundo positivo dentro de la nueva ventana sí confirma
        self.clock.advance(0.4)
        s3 = self.tracker.update("CAM-ENTRADA", True, frame_sequence=3, vehicle_type="AUTOMOVIL")
        self.assertEqual(s3.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
        self.assertTrue(s3.vehicle_present)
        self.assertEqual(s3.consecutive_positive_frames, 2)

    def test_06_one_two_three_four_negatives_and_recovery_counter_reset(self) -> None:
        """Verifica conteo exacto de 1, 2, 3 y 4 negativos y reseteo al reaparecer el vehículo."""
        self._confirm_vehicle("CAM-ENTRADA", seq_start=1)  # último positivo en 1000.1

        for expected_miss in (1, 2, 3):
            self.clock.advance(0.1)
            snap = self.tracker.update("CAM-ENTRADA", False, frame_sequence=2 + expected_miss)
            self.assertEqual(snap.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
            self.assertTrue(snap.vehicle_present)
            self.assertEqual(snap.consecutive_missed_frames, expected_miss)
            self.assertEqual(snap.hold_reason, "WITHIN_BOTH_BOUNDS")

        # 4to negativo en dt total = 0.4s < 1.2s: alcanza presupuesto de frames pero NO tiempo
        self.clock.advance(0.1)
        snap4 = self.tracker.update("CAM-ENTRADA", False, frame_sequence=6)
        self.assertEqual(snap4.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
        self.assertTrue(snap4.vehicle_present)
        self.assertEqual(snap4.consecutive_missed_frames, 4)

        # Nuevo positivo resetea consecutive_missed_frames a 0
        self.clock.advance(0.1)
        recovered = self.tracker.update("CAM-ENTRADA", True, frame_sequence=7)
        self.assertEqual(recovered.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
        self.assertEqual(recovered.consecutive_missed_frames, 0)
        self.assertIsNone(recovered.hold_reason)
        self.assertEqual(recovered.transition_reason, "PRESENCE_SUSTAINED")

    def test_07_only_frame_limit_reached_holds_presence_by_time_grace(self) -> None:
        """Alcanzar solo max_missed_frames (4, 5, 6 misses < 1.2s) retiene VEHICLE_PRESENT."""
        self._confirm_vehicle("CAM-ENTRADA", seq_start=1)  # último positivo t=1000.1

        # 6 frames negativos a 15 FPS (~0.067s cada uno, total ~0.40s < 1.2s)
        snapshots: List[TemporalStateSnapshot] = []
        for i in range(6):
            self.clock.advance(0.067)
            snapshots.append(self.tracker.update("CAM-ENTRADA", False, frame_sequence=3 + i))

        self.assertEqual(snapshots[3].consecutive_missed_frames, 4)
        self.assertEqual(snapshots[3].detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
        self.assertTrue(snapshots[3].vehicle_present)
        self.assertEqual(snapshots[3].hold_reason, "HOLD_BY_TIME_GRACE")

        self.assertEqual(snapshots[5].consecutive_missed_frames, 6)
        self.assertEqual(snapshots[5].detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
        self.assertTrue(snapshots[5].vehicle_present)
        self.assertEqual(snapshots[5].hold_reason, "HOLD_BY_TIME_GRACE")

    def test_08_only_time_limit_reached_holds_presence_by_frame_budget(self) -> None:
        """Alcanzar solo missed_grace_seconds (1.2s <= dt < 6.0s, <4 misses) retiene VEHICLE_PRESENT."""
        self._confirm_vehicle("CAM-ENTRADA", seq_start=1)  # último positivo t=1000.1

        for idx, dt in enumerate((1.5, 1.5, 1.5), start=1):  # elapsed: 1.5, 3.0, 4.5s (< 6.0s)
            self.clock.advance(dt)
            snap = self.tracker.update("CAM-ENTRADA", False, frame_sequence=2 + idx)
            self.assertEqual(snap.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
            self.assertTrue(snap.vehicle_present)
            self.assertEqual(snap.consecutive_missed_frames, idx)
            self.assertEqual(snap.hold_reason, "HOLD_BY_FRAME_BUDGET")

    def test_09_both_miss_limits_reached_transitions_to_vehicle_lost(self) -> None:
        """Cuando se alcanzan >= 4 misses Y >= 1.2s transiciona a VEHICLE_LOST."""
        self._confirm_vehicle("CAM-ENTRADA", seq_start=1)  # último positivo t=1000.1

        for seq, dt in ((3, 0.35), (4, 0.35), (5, 0.35)):  # 1.05s, 3 misses
            self.clock.advance(dt)
            s = self.tracker.update("CAM-ENTRADA", False, frame_sequence=seq)
            self.assertEqual(s.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)

        # 4to miss en 1.40s (>= 1.2s y >= 4 misses)
        self.clock.advance(0.35)
        lost = self.tracker.update("CAM-ENTRADA", False, frame_sequence=6)
        self.assertEqual(lost.detection_status, TemporalDetectionStatus.VEHICLE_LOST)
        self.assertFalse(lost.vehicle_present)
        self.assertEqual(lost.consecutive_missed_frames, 4)
        self.assertIsNone(lost.hold_reason)
        self.assertEqual(lost.transition_reason, "LOST_MISS_BUDGET_EXHAUSTED")

    def test_10_absolute_expiry_at_six_seconds_even_with_single_negative_or_stationary_car(self) -> None:
        """A los 6.0s sin positivos expira aunque solo llegue 1 negativo; vehículo activo >6s sobrevive."""
        # Vehículo estacionado con positivos continuos sobrevive > 6.0s sin expirar
        self._confirm_vehicle("CAM-ENTRADA", seq_start=1)  # t=1000.1
        for i in range(1, 9):
            self.clock.advance(1.0)
            s = self.tracker.update("CAM-ENTRADA", True, frame_sequence=2 + i)
            self.assertEqual(s.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
            self.assertTrue(s.vehicle_present)

        # Ahora t=1008.1 fue el último positivo; avanzar exactamente 6.0s y recibir 1 negativo
        self.clock.advance(6.0)
        expired = self.tracker.update("CAM-ENTRADA", False, frame_sequence=20)
        self.assertEqual(expired.detection_status, TemporalDetectionStatus.VEHICLE_LOST)
        self.assertFalse(expired.vehicle_present)
        self.assertEqual(expired.consecutive_missed_frames, 1)
        self.assertEqual(expired.transition_reason, "LOST_ABSOLUTE_EXPIRY")

    def test_11_camera_without_new_frames_expires_via_expire_if_stale(self) -> None:
        """Sin recibir frames nuevos, expire_if_stale expira presencia a los 6.0s y limpia a los 6.8s."""
        self._confirm_vehicle("CAM-ENTRADA", seq_start=1)  # t=1000.1

        self.clock.advance(5.9)
        before_expiry = self.tracker.expire_if_stale("CAM-ENTRADA")
        self.assertEqual(before_expiry.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
        self.assertTrue(before_expiry.vehicle_present)
        self.assertFalse(before_expiry.is_stale)

        # Exactamente en t = 1000.1 + 6.0 = 1006.1 -> VEHICLE_LOST y is_stale=True
        self.clock.advance(0.1)
        at_expiry = self.tracker.expire_if_stale("CAM-ENTRADA")
        self.assertEqual(at_expiry.detection_status, TemporalDetectionStatus.VEHICLE_LOST)
        self.assertFalse(at_expiry.vehicle_present)
        self.assertTrue(at_expiry.is_stale)
        self.assertEqual(at_expiry.transition_reason, "LOST_STALE_NO_FRAMES")

        # Exactamente tras lost_hold_seconds (0.8s) -> NO_VEHICLE_DETECTED sin metadatos obsoletos
        self.clock.advance(0.8)
        after_hold = self.tracker.expire_if_stale("CAM-ENTRADA")
        self.assertEqual(after_hold.detection_status, TemporalDetectionStatus.NO_VEHICLE_DETECTED)
        self.assertFalse(after_hold.vehicle_present)
        self.assertTrue(after_hold.is_stale)
        self.assertEqual(after_hold.transition_reason, "LOST_HOLD_EXPIRED_TO_IDLE")
        self.assertIsNone(after_hold.vehicle_type)
        self.assertIsNone(after_hold.vehicle_confidence)

    def test_12_recovery_during_vehicle_lost_and_expiry_after_hold(self) -> None:
        """Durante lost_hold_seconds (0.8s) un positivo recupera VEHICLE_PRESENT; pasado 0.8s inicia CANDIDATE."""
        self._confirm_vehicle("CAM-ENTRADA", seq_start=1)
        for seq, dt in ((3, 0.4), (4, 0.4), (5, 0.4), (6, 0.1)):
            self.clock.advance(dt)
            self.tracker.update("CAM-ENTRADA", False, frame_sequence=seq)

        self.assertEqual(self.tracker.get_snapshot("CAM-ENTRADA").detection_status, TemporalDetectionStatus.VEHICLE_LOST)

        # Dentro de 0.8s (dt = 0.5s): recuperación directa
        self.clock.advance(0.5)
        rec = self.tracker.update("CAM-ENTRADA", True, frame_sequence=7, vehicle_type="AUTOBUS", vehicle_confidence=0.95)
        self.assertEqual(rec.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
        self.assertTrue(rec.vehicle_present)
        self.assertEqual(rec.consecutive_missed_frames, 0)
        self.assertEqual(rec.vehicle_type, "AUTOBUS")
        self.assertEqual(rec.transition_reason, "RECOVERED_FROM_LOST")

        # Volver a VEHICLE_LOST y dejar expirar 0.8s completos antes del próximo positivo
        for seq, dt in ((8, 0.4), (9, 0.4), (10, 0.4), (11, 0.1)):
            self.clock.advance(dt)
            self.tracker.update("CAM-ENTRADA", False, frame_sequence=seq)
        self.clock.advance(0.8)
        late_pos = self.tracker.update("CAM-ENTRADA", True, frame_sequence=12, vehicle_type="AUTOMOVIL")
        self.assertEqual(late_pos.detection_status, TemporalDetectionStatus.VEHICLE_CANDIDATE)
        self.assertFalse(late_pos.vehicle_present)
        self.assertEqual(late_pos.consecutive_positive_frames, 1)

    def test_13_explicit_reset_wipes_all_state_and_allows_sequence_restart(self) -> None:
        """reset_camera elimina contadores, timestamps, metadatos e historial de secuencia."""
        self._confirm_vehicle("CAM-ENTRADA", seq_start=10)
        self.clock.advance(0.2)
        self.tracker.update("CAM-ENTRADA", False, frame_sequence=12)

        for reason in ("CREDENTIAL_REVOKED", "CREDENTIAL_REPLACED", "CAMERA_RECONNECTED"):
            reset_snap = self.tracker.reset_camera("CAM-ENTRADA", reason=reason)
            self.assertEqual(reset_snap.detection_status, TemporalDetectionStatus.NO_VEHICLE_DETECTED)
            self.assertFalse(reset_snap.vehicle_present)
            self.assertEqual(reset_snap.consecutive_positive_frames, 0)
            self.assertEqual(reset_snap.consecutive_missed_frames, 0)
            self.assertEqual(reset_snap.total_frames_processed, 0)
            self.assertIsNone(reset_snap.last_frame_monotonic)
            self.assertIsNone(reset_snap.last_positive_monotonic)
            self.assertIsNone(reset_snap.candidate_started_monotonic)
            self.assertIsNone(reset_snap.lost_started_monotonic)
            self.assertIsNone(reset_snap.frame_sequence)
            self.assertIsNone(reset_snap.frame_id)
            self.assertIsNone(reset_snap.vehicle_type)
            self.assertIsNone(reset_snap.vehicle_confidence)
            self.assertEqual(reset_snap.last_reset_reason, reason)

            # Secuencia reiniciada en frame_sequence=1 tras reconexión/reemplazo debe aceptarse
            self.clock.advance(0.1)
            first_after = self.tracker.update(
                "CAM-ENTRADA",
                True,
                frame_id="restarted-1",
                frame_sequence=1,
                vehicle_type="MOTOCICLETA",
            )
            self.assertTrue(first_after.frame_accepted)
            self.assertEqual(first_after.detection_status, TemporalDetectionStatus.VEHICLE_CANDIDATE)
            self.assertEqual(first_after.frame_sequence, 1)

    def test_14_strict_isolation_between_cameras(self) -> None:
        """Estados, resets, expiraciones y secuencias de dos cámaras nunca interfieren entre sí."""
        self._confirm_vehicle("CAM-ENTRADA", seq_start=1)
        self.tracker.update("CAM-SALIDA", True, frame_sequence=1, vehicle_type="MOTOCICLETA")

        self.clock.advance(6.2)
        self.tracker.expire_if_stale("CAM-SALIDA")
        in_before = self.tracker.get_snapshot("CAM-ENTRADA")
        out_snap = self.tracker.get_snapshot("CAM-SALIDA")
        self.assertEqual(out_snap.detection_status, TemporalDetectionStatus.NO_VEHICLE_DETECTED)
        self.assertEqual(in_before.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)

        self.tracker.reset_camera("CAM-SALIDA", reason="CREDENTIAL_REVOKED")
        self.assertEqual(
            self.tracker.get_snapshot("CAM-ENTRADA").detection_status,
            TemporalDetectionStatus.VEHICLE_PRESENT,
        )

    def test_15_duplicate_and_out_of_order_frames_and_wall_timestamp_independence(self) -> None:
        """Rechaza duplicados y secuencias regresivas sin mutar estado; ignora desorden de reloj de pared."""
        # Wall timestamps decrecientes (p. ej. ajuste NTP) NO afectan si frame_sequence crece
        s1 = self.tracker.update(
            "CAM-ENTRADA",
            True,
            frame_id="uuid-1",
            frame_sequence=10,
            wall_timestamp=2000.0,
        )
        self.assertTrue(s1.frame_accepted)
        self.clock.advance(0.1)
        s2 = self.tracker.update(
            "CAM-ENTRADA",
            True,
            frame_id="uuid-2",
            frame_sequence=11,
            wall_timestamp=1900.0,  # Menor que el anterior
        )
        self.assertTrue(s2.frame_accepted)
        self.assertEqual(s2.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
        self.assertEqual(s2.total_frames_processed, 2)

        # Duplicado por frame_id incluso con secuencia mayor -> rechazado
        dup_id = self.tracker.update("CAM-ENTRADA", False, frame_id="uuid-1", frame_sequence=12)
        self.assertFalse(dup_id.frame_accepted)
        self.assertEqual(dup_id.rejection_reason, "DUPLICATE_FRAME")
        self.assertEqual(dup_id.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
        self.assertEqual(dup_id.total_frames_processed, 2)

        # Duplicado por secuencia igual -> rechazado
        dup_seq = self.tracker.update("CAM-ENTRADA", False, frame_id="uuid-new", frame_sequence=11)
        self.assertFalse(dup_seq.frame_accepted)
        self.assertEqual(dup_seq.rejection_reason, "DUPLICATE_FRAME")
        self.assertEqual(dup_seq.total_frames_processed, 2)

        # Fuera de orden (frame_sequence < last_sequence) -> rechazado
        ooo = self.tracker.update("CAM-ENTRADA", False, frame_id="uuid-old", frame_sequence=9)
        self.assertFalse(ooo.frame_accepted)
        self.assertEqual(ooo.rejection_reason, "OUT_OF_ORDER_FRAME")
        self.assertEqual(ooo.total_frames_processed, 2)
        self.assertEqual(ooo.consecutive_missed_frames, 0)

    def test_16_get_snapshot_and_repeated_expire_if_stale_have_no_counter_side_effects(self) -> None:
        """Consultas repetidas a get_snapshot y expire_if_stale nunca alteran contadores ni secuencias."""
        # Cámara desconocida: solo lectura limpia
        unknown = self.tracker.get_snapshot("CAM-NUEVA")
        self.assertEqual(unknown.detection_status, TemporalDetectionStatus.NO_VEHICLE_DETECTED)
        self.assertEqual(unknown.total_frames_processed, 0)

        self._confirm_vehicle("CAM-ENTRADA", seq_start=1)
        self.clock.advance(0.2)
        base = self.tracker.update("CAM-ENTRADA", False, frame_sequence=3)
        self.assertEqual(base.total_frames_processed, 3)
        self.assertEqual(base.consecutive_missed_frames, 1)

        for _ in range(10):
            s = self.tracker.get_snapshot("CAM-ENTRADA")
            self.assertEqual(s.total_frames_processed, 3)
            self.assertEqual(s.consecutive_missed_frames, 1)
            self.assertEqual(s.consecutive_positive_frames, 0)
            self.assertEqual(s.frame_sequence, 3)

        self.clock.advance(6.1)
        e1 = self.tracker.expire_if_stale("CAM-ENTRADA")
        e2 = self.tracker.expire_if_stale("CAM-ENTRADA")
        e3 = self.tracker.expire_if_stale("CAM-ENTRADA")
        for snap in (e1, e2, e3):
            self.assertEqual(snap.total_frames_processed, 3)
            self.assertEqual(snap.consecutive_missed_frames, 1)
            self.assertEqual(snap.consecutive_positive_frames, 0)
            self.assertEqual(snap.frame_sequence, 3)
            self.assertEqual(snap.detection_status, TemporalDetectionStatus.VEHICLE_LOST)

    def test_17_concurrency_across_independent_and_shared_cameras(self) -> None:
        """Ejecuta actualizaciones y lecturas concurrentes sin excepciones ni mezcla entre cámaras."""
        errors: List[BaseException] = []
        cameras = [f"CAM-{idx}" for idx in range(4)]
        frames_per_cam = 50
        start_barrier = threading.Barrier(len(cameras) + 2)

        def worker(cam_idx: int) -> None:
            cam_id = cameras[cam_idx]
            try:
                start_barrier.wait(timeout=2.0)
                for seq in range(1, frames_per_cam + 1):
                    # CAM-0 y CAM-2 positivos constantes; CAM-1 y CAM-3 siempre negativos
                    roi_pos = cam_idx % 2 == 0
                    snap = self.tracker.update(
                        cam_id,
                        roi_pos,
                        frame_sequence=seq,
                        now_monotonic=1000.0 + seq * 0.05,
                    )
                    if math.isnan(snap.evaluated_at_monotonic):
                        raise AssertionError("Timestamp NaN")
            except BaseException as exc:  # pragma: no cover - captura fallo en hilo
                errors.append(exc)

        def reader() -> None:
            try:
                start_barrier.wait(timeout=2.0)
                for _ in range(100):
                    for cam_id in cameras:
                        _ = self.tracker.get_snapshot(cam_id, now_monotonic=1005.0)
            except BaseException as exc:  # pragma: no cover - captura fallo en hilo
                errors.append(exc)

        threads: Dict[str, threading.Thread] = {}
        for idx, cam in enumerate(cameras):
            t = threading.Thread(target=worker, args=(idx,), name=f"worker-{cam}")
            threads[cam] = t
            t.start()
        for r_idx in range(2):
            rt = threading.Thread(target=reader, name=f"reader-{r_idx}")
            threads[f"reader-{r_idx}"] = rt
            rt.start()

        for t in threads.values():
            t.join(timeout=5.0)
            self.assertFalse(t.is_alive())

        self.assertEqual(errors, [])
        self.assertEqual(self.tracker.get_snapshot("CAM-0").detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
        self.assertEqual(self.tracker.get_snapshot("CAM-1").detection_status, TemporalDetectionStatus.NO_VEHICLE_DETECTED)
        self.assertEqual(self.tracker.get_snapshot("CAM-2").detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
        self.assertEqual(self.tracker.get_snapshot("CAM-3").detection_status, TemporalDetectionStatus.NO_VEHICLE_DETECTED)
        for cam in cameras:
            self.assertEqual(self.tracker.get_snapshot(cam).total_frames_processed, frames_per_cam)

    def test_18_t01_recent_negative_frames_prevent_stale_expiration(self) -> None:
        """T-01: Frames negativos recientes impiden expiración stale aun >6s sin positivos."""
        confirmed = self._confirm_vehicle("CAM-ENTRADA", seq_start=1)  # t=1000.1
        last_pos = confirmed.last_positive_monotonic

        # 3 misses (< max_missed_frames=4) distribuidos dentro de 6s
        for seq, dt in ((3, 1.8), (4, 1.8), (5, 1.8)):  # t=1001.9, 1003.7, 1005.5
            self.clock.advance(dt)
            snap = self.tracker.update("CAM-ENTRADA", False, frame_sequence=seq)
            self.assertEqual(snap.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
            self.assertEqual(snap.hold_reason, "HOLD_BY_FRAME_BUDGET")

        # Avanzar a t=1006.5: >6.0s desde último positivo (6.4s), pero último frame hace 1.0s
        self.clock.advance(1.0)
        now = self.clock()
        self.assertGreater(now - last_pos, 6.0)
        pre_snap = self.tracker.get_snapshot("CAM-ENTRADA")
        self.assertLess(now - pre_snap.last_frame_monotonic, 6.0)

        stale_check = self.tracker.expire_if_stale("CAM-ENTRADA")
        self.assertFalse(stale_check.is_stale)
        self.assertNotEqual(stale_check.transition_reason, "LOST_STALE_NO_FRAMES")
        self.assertEqual(stale_check.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
        self.assertTrue(stale_check.vehicle_present)
        self.assertEqual(stale_check.consecutive_missed_frames, 3)
        self.assertEqual(stale_check.hold_reason, "HOLD_BY_FRAME_BUDGET")

    def test_19_t02_counter_preservation_across_expiry_transitions_and_subsequent_update(self) -> None:
        """T-02: expire_if_stale conserva ambos contadores al expirar y update posterior los normaliza."""
        # Caso A: VEHICLE_PRESENT (pos=3, miss=0) -> VEHICLE_LOST -> NO_VEHICLE_DETECTED
        self._confirm_vehicle("CAM-A", seq_start=1)
        self.clock.advance(0.1)
        s_pos3 = self.tracker.update("CAM-A", True, frame_sequence=3)
        self.assertEqual(s_pos3.consecutive_positive_frames, 3)
        self.assertEqual(s_pos3.consecutive_missed_frames, 0)

        self.clock.advance(6.0)
        lost_a = self.tracker.expire_if_stale("CAM-A")
        self.assertEqual(lost_a.detection_status, TemporalDetectionStatus.VEHICLE_LOST)
        self.assertEqual(lost_a.consecutive_positive_frames, 3)
        self.assertEqual(lost_a.consecutive_missed_frames, 0)

        self.clock.advance(0.8)
        idle_a = self.tracker.expire_if_stale("CAM-A")
        self.assertEqual(idle_a.detection_status, TemporalDetectionStatus.NO_VEHICLE_DETECTED)
        self.assertEqual(idle_a.consecutive_positive_frames, 3)
        self.assertEqual(idle_a.consecutive_missed_frames, 0)

        # Frame negativo posterior en IDLE normaliza contadores con las reglas normales
        self.clock.advance(0.1)
        after_neg_a = self.tracker.update("CAM-A", False, frame_sequence=4)
        self.assertEqual(after_neg_a.detection_status, TemporalDetectionStatus.NO_VEHICLE_DETECTED)
        self.assertEqual(after_neg_a.consecutive_positive_frames, 0)
        self.assertEqual(after_neg_a.consecutive_missed_frames, 0)

        # Caso B: VEHICLE_PRESENT (pos=0, miss=2) -> VEHICLE_LOST -> NO_VEHICLE_DETECTED
        self._confirm_vehicle("CAM-B", seq_start=1)
        for seq in (3, 4):
            self.clock.advance(0.2)
            self.tracker.update("CAM-B", False, frame_sequence=seq)
        pre_b = self.tracker.get_snapshot("CAM-B")
        self.assertEqual((pre_b.consecutive_positive_frames, pre_b.consecutive_missed_frames), (0, 2))

        self.clock.advance(6.0)
        lost_b = self.tracker.expire_if_stale("CAM-B")
        self.assertEqual(lost_b.detection_status, TemporalDetectionStatus.VEHICLE_LOST)
        self.assertEqual((lost_b.consecutive_positive_frames, lost_b.consecutive_missed_frames), (0, 2))

        self.clock.advance(0.8)
        idle_b = self.tracker.expire_if_stale("CAM-B")
        self.assertEqual(idle_b.detection_status, TemporalDetectionStatus.NO_VEHICLE_DETECTED)
        self.assertEqual((idle_b.consecutive_positive_frames, idle_b.consecutive_missed_frames), (0, 2))

        # Caso C: update(False) durante VEHICLE_LOST tras expiración stale normaliza pos=0, miss+=1
        self._confirm_vehicle("CAM-C", seq_start=1)
        self.clock.advance(6.0)
        lost_c = self.tracker.expire_if_stale("CAM-C")
        self.assertEqual((lost_c.consecutive_positive_frames, lost_c.consecutive_missed_frames), (2, 0))
        self.clock.advance(0.2)
        upd_c = self.tracker.update("CAM-C", False, frame_sequence=3)
        self.assertEqual(upd_c.detection_status, TemporalDetectionStatus.VEHICLE_LOST)
        self.assertEqual(upd_c.consecutive_positive_frames, 0)
        self.assertEqual(upd_c.consecutive_missed_frames, 1)

        # Caso D: VEHICLE_CANDIDATE (pos=1, miss=0) -> NO_VEHICLE_DETECTED y reentrada posterior
        cand_d = self.tracker.update("CAM-D", True, frame_sequence=1, vehicle_type="AUTOMOVIL")
        self.assertEqual(cand_d.detection_status, TemporalDetectionStatus.VEHICLE_CANDIDATE)
        self.assertEqual((cand_d.consecutive_positive_frames, cand_d.consecutive_missed_frames), (1, 0))
        self.clock.advance(1.6)
        expired_d = self.tracker.expire_if_stale("CAM-D")
        self.assertEqual(expired_d.detection_status, TemporalDetectionStatus.NO_VEHICLE_DETECTED)
        self.assertEqual((expired_d.consecutive_positive_frames, expired_d.consecutive_missed_frames), (1, 0))
        self.clock.advance(0.1)
        reopen_d = self.tracker.update("CAM-D", True, frame_sequence=2, vehicle_type="AUTOMOVIL")
        self.assertEqual(reopen_d.detection_status, TemporalDetectionStatus.VEHICLE_CANDIDATE)
        self.assertEqual(reopen_d.consecutive_positive_frames, 1)
        self.clock.advance(0.1)
        confirmed_d = self.tracker.update("CAM-D", True, frame_sequence=3, vehicle_type="AUTOMOVIL")
        self.assertEqual(confirmed_d.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
        self.assertEqual(confirmed_d.consecutive_positive_frames, 2)

    def test_20_t03_camera_isolation_when_both_confirmed_and_one_becomes_stale(self) -> None:
        """T-03: Dos cámaras en VEHICLE_PRESENT; expirar CAM-SALIDA no altera a CAM-ENTRADA."""
        self._confirm_vehicle("CAM-ENTRADA", seq_start=1)  # t=1000.1
        self._confirm_vehicle("CAM-SALIDA", seq_start=1)   # t=1000.2

        # Mantener viva CAM-ENTRADA en t=1003.2
        self.clock.advance(3.0)
        in_live = self.tracker.update("CAM-ENTRADA", True, frame_sequence=3, vehicle_type="AUTOMOVIL")
        self.assertEqual(in_live.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)

        # Avanzar a t=1006.3: CAM-SALIDA supera 6.0s de silencio; CAM-ENTRADA solo 3.1s
        self.clock.advance(3.1)
        in_before = self.tracker.get_snapshot("CAM-ENTRADA")

        out_expired = self.tracker.expire_if_stale("CAM-SALIDA")
        self.assertEqual(out_expired.detection_status, TemporalDetectionStatus.VEHICLE_LOST)
        self.assertTrue(out_expired.is_stale)

        in_after = self.tracker.get_snapshot("CAM-ENTRADA")
        self.assertEqual(in_after.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
        self.assertEqual(in_after.detection_status, in_before.detection_status)
        self.assertFalse(in_after.is_stale)
        self.assertEqual(in_after.last_frame_monotonic, in_before.last_frame_monotonic)
        self.assertEqual(in_after.last_positive_monotonic, in_before.last_positive_monotonic)
        self.assertEqual(in_after.consecutive_positive_frames, in_before.consecutive_positive_frames)
        self.assertEqual(in_after.consecutive_missed_frames, in_before.consecutive_missed_frames)
        self.assertEqual(in_after.total_frames_processed, in_before.total_frames_processed)

    def test_21_t04_late_first_expiry_query_starts_lost_hold_at_query_time(self) -> None:
        """T-04: Primera consulta tardía inicia lost_hold_seconds en now_mono (t=1010.0 -> 1010.8)."""
        self.tracker.update("CAM-ENTRADA", True, frame_sequence=1, now_monotonic=999.9)
        confirmed = self.tracker.update("CAM-ENTRADA", True, frame_sequence=2, now_monotonic=1000.0)
        self.assertEqual(confirmed.detection_status, TemporalDetectionStatus.VEHICLE_PRESENT)
        self.assertEqual(confirmed.last_frame_monotonic, 1000.0)

        # Primera consulta en t=1010.0 (> 6.0s y > 6.8s sin frames) -> VEHICLE_LOST en 1010.0
        self.clock.set(1010.0)
        first_query = self.tracker.expire_if_stale("CAM-ENTRADA")
        self.assertEqual(first_query.detection_status, TemporalDetectionStatus.VEHICLE_LOST)
        self.assertFalse(first_query.vehicle_present)
        self.assertTrue(first_query.is_stale)
        self.assertEqual(first_query.lost_started_monotonic, 1010.0)
        self.assertEqual(first_query.transition_reason, "LOST_STALE_NO_FRAMES")

        # Antes de completar lost_hold_seconds (0.8s) permanece en VEHICLE_LOST
        for t in (1010.5, 1010.79):
            self.clock.set(t)
            held = self.tracker.expire_if_stale("CAM-ENTRADA")
            self.assertEqual(held.detection_status, TemporalDetectionStatus.VEHICLE_LOST)
            self.assertEqual(held.lost_started_monotonic, 1010.0)

        # Al completar 0.8s desde t=1010.0 -> NO_VEHICLE_DETECTED en t=1010.8
        self.clock.set(1010.8)
        to_idle = self.tracker.expire_if_stale("CAM-ENTRADA")
        self.assertEqual(to_idle.detection_status, TemporalDetectionStatus.NO_VEHICLE_DETECTED)
        self.assertFalse(to_idle.vehicle_present)
        self.assertIsNone(to_idle.lost_started_monotonic)
        self.assertEqual(to_idle.transition_reason, "LOST_HOLD_EXPIRED_TO_IDLE")

    def test_22_t05_repeated_queries_preserve_transition_instant_and_do_not_repeat_events(self) -> None:
        """T-05: Múltiples expire_if_stale y get_snapshot no reinician tiempos ni contadores ni repiten transiciones."""
        self.tracker.update("CAM-ENTRADA", True, frame_sequence=1, now_monotonic=999.9)
        self.tracker.update("CAM-ENTRADA", True, frame_sequence=2, now_monotonic=1000.0)

        self.clock.set(1010.0)
        first_lost = self.tracker.expire_if_stale("CAM-ENTRADA")
        self.assertEqual(first_lost.detection_status, TemporalDetectionStatus.VEHICLE_LOST)
        self.assertEqual(first_lost.lost_started_monotonic, 1010.0)

        for t in (1010.0, 1010.2, 1010.5, 1010.7):
            self.clock.set(t)
            for queried in (
                self.tracker.expire_if_stale("CAM-ENTRADA"),
                self.tracker.get_snapshot("CAM-ENTRADA"),
            ):
                self.assertEqual(queried.detection_status, TemporalDetectionStatus.VEHICLE_LOST)
                self.assertEqual(queried.lost_started_monotonic, 1010.0)
                self.assertEqual(queried.last_frame_monotonic, 1000.0)
                self.assertEqual(queried.consecutive_positive_frames, 2)
                self.assertEqual(queried.consecutive_missed_frames, 0)
                self.assertEqual(queried.total_frames_processed, 2)
                self.assertEqual(queried.transition_reason, "LOST_STALE_NO_FRAMES")

        # En 1010.8 transiciona puntualmente a NO_VEHICLE_DETECTED (prueba de que no se reinició lost_started_monotonic)
        self.clock.set(1010.8)
        idle = self.tracker.expire_if_stale("CAM-ENTRADA")
        self.assertEqual(idle.detection_status, TemporalDetectionStatus.NO_VEHICLE_DETECTED)
        self.assertEqual(idle.transition_reason, "LOST_HOLD_EXPIRED_TO_IDLE")
        self.assertIsNone(idle.lost_started_monotonic)

        for t in (1010.8, 1011.5, 1015.0):
            self.clock.set(t)
            for queried in (
                self.tracker.expire_if_stale("CAM-ENTRADA"),
                self.tracker.get_snapshot("CAM-ENTRADA"),
            ):
                self.assertEqual(queried.detection_status, TemporalDetectionStatus.NO_VEHICLE_DETECTED)
                self.assertIsNone(queried.lost_started_monotonic)
                self.assertEqual(queried.last_frame_monotonic, 1000.0)
                self.assertEqual(queried.consecutive_positive_frames, 2)
                self.assertEqual(queried.consecutive_missed_frames, 0)
                self.assertEqual(queried.total_frames_processed, 2)
                self.assertEqual(queried.transition_reason, "LOST_HOLD_EXPIRED_TO_IDLE")


if __name__ == "__main__":
    unittest.main()
