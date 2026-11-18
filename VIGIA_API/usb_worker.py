"""
VIGIA_API.usb_worker
====================
Gestor de hilos en segundo plano para cámaras Pull locales (USB / OpenCVCaptureSource).

Garantías arquitectónicas (VIGIA-USB-02):
- Reutiliza íntegramente `VisionEngineCoordinator.process_camera_step()` sin duplicar
  inferencia YOLO, proyección ROI ni persistencia PostgreSQL.
- Previene workers duplicados por carril y aperturas simultáneas del mismo índice físico.
- Maneja desconexiones físicas en caliente liberando el descriptor e intentando
  reconexión controlada con espera interrumpible.
- Libera deterministamente los recursos físicos de OpenCV al detenerse o revocarse y
  purga `_latest_camera_frames` para no exponer vídeo obsoleto.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Optional

import cv2

from VIGIA_Core.domain.vision_result import VisionStatus
from VIGIA_Vision.capture.sources import OpenCVCaptureSource
from VIGIA_Vision.detection.roi_and_preprocess import project_normalized_roi
from VIGIA_Vision.runtime.coordinator import VisionEngineCoordinator
from VIGIA_Vision.runtime.evidence_storage import render_annotated_frame

logger = logging.getLogger(__name__)


class CameraPullWorker:
    """Worker dedicado en hilo demonio para una cámara lógica configurada en modo Pull."""

    def __init__(
        self,
        *,
        codigo_camara: str,
        device_index: Optional[int],
        coordinator: VisionEngineCoordinator,
        latest_frames_store: Dict[str, Dict[str, Any]],
        get_condition_fn: Callable[[str], threading.Condition],
        get_process_lock_fn: Callable[[str], threading.RLock],
        camera_persist_states: Dict[str, Dict[str, Any]],
        last_persist_timestamps: Dict[str, float],
        get_debounce_ttl_fn: Callable[[], float],
        target_fps: float = 15.0,
        reconnect_interval_seconds: float = 2.0,
        disconnect_threshold: int = 5,
    ) -> None:
        self.codigo_camara = codigo_camara.strip().upper()
        self.device_index = device_index
        self._coordinator = coordinator
        self._latest_frames_store = latest_frames_store
        self._get_condition = get_condition_fn
        self._get_process_lock = get_process_lock_fn
        self._camera_persist_states = camera_persist_states
        self._last_persist_timestamps = last_persist_timestamps
        self._get_debounce_ttl = get_debounce_ttl_fn

        self.target_fps = max(1.0, min(60.0, float(target_fps)))
        self.reconnect_interval_seconds = max(0.2, float(reconnect_interval_seconds))
        self.disconnect_threshold = max(1, int(disconnect_threshold))

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._state_lock = threading.RLock()
        self._consecutive_errors = 0
        self._last_resolution: Optional[str] = None
        self._backend_name: Optional[str] = None
        self._started_at: Optional[float] = None

    @property
    def is_running(self) -> bool:
        with self._state_lock:
            return (
                self._thread is not None
                and self._thread.is_alive()
                and not self._stop_event.is_set()
            )

    @property
    def is_thread_alive(self) -> bool:
        with self._state_lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._state_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._consecutive_errors = 0
            self._started_at = time.time()
            self._thread = threading.Thread(
                target=self._run_loop,
                name=f"VigiaPullWorker-{self.codigo_camara}",
                daemon=True,
            )
            self._thread.start()
            logger.info(
                "CameraPullWorker iniciado para '%s' (device_index=%s, fps=%.1f).",
                self.codigo_camara,
                self.device_index,
                self.target_fps,
            )

    def stop(self, *, clear_frames: bool = True, timeout: float = 5.0) -> bool:
        """
        Señaliza la detención del worker, espera su terminación hasta `timeout`
        segundos, libera el descriptor de hardware y purga frames obsoletos.
        """
        self._stop_event.set()
        thread_ref: Optional[threading.Thread]
        with self._state_lock:
            thread_ref = self._thread

        stopped_cleanly = True
        if thread_ref is not None and thread_ref.is_alive() and thread_ref is not threading.current_thread():
            thread_ref.join(timeout=max(0.1, float(timeout)))
            stopped_cleanly = not thread_ref.is_alive()

        # Garantizar liberación idempotente de recursos físicos incluso si el hilo terminó
        self._release_slot_source()

        if clear_frames:
            self._clear_live_frame()

        logger.info(
            "CameraPullWorker detenido para '%s' (clean=%s, clear_frames=%s).",
            self.codigo_camara,
            stopped_cleanly,
            clear_frames,
        )
        return stopped_cleanly

    def get_metadata(self) -> Dict[str, Any]:
        with self._state_lock:
            return {
                "codigo_camara": self.codigo_camara,
                "device_index": self.device_index,
                "running": self.is_running,
                "consecutive_errors": self._consecutive_errors,
                "resolution": self._last_resolution,
                "backend": self._backend_name,
            }

    def _release_slot_source(self) -> None:
        try:
            if self._coordinator.registry is not None:
                slot = self._coordinator.registry.get_slot(self.codigo_camara)
                slot.source.release()
        except Exception:
            pass

    def _clear_live_frame(self) -> None:
        try:
            cond = self._get_condition(self.codigo_camara)
            with cond:
                self._latest_frames_store.pop(self.codigo_camara, None)
                cond.notify_all()
        except Exception:
            pass

    def _run_loop(self) -> None:
        frame_interval = 1.0 / self.target_fps
        last_error_log_ts = 0.0

        try:
            while not self._stop_event.is_set():
                tick_start = time.perf_counter()

                if self._coordinator.registry is None:
                    self._stop_event.wait(self.reconnect_interval_seconds)
                    continue

                try:
                    slot = self._coordinator.registry.get_slot(self.codigo_camara)
                except Exception:
                    self._stop_event.wait(self.reconnect_interval_seconds)
                    continue

                # Verificar si la fuente fue reemplazada externamente por push móvil
                if not isinstance(slot.source, OpenCVCaptureSource):
                    logger.info(
                        "La fuente de '%s' ya no es Pull OpenCV. Finalizando CameraPullWorker.",
                        self.codigo_camara,
                    )
                    break

                # Recuperación o apertura inicial de hardware
                if not slot.source.is_opened():
                    opened = False
                    try:
                        opened = bool(slot.source.open())
                    except Exception as open_exc:
                        now_log = time.monotonic()
                        if now_log - last_error_log_ts >= 5.0:
                            logger.warning(
                                "Error al abrir cámara USB '%s' (idx=%s): %s",
                                self.codigo_camara,
                                self.device_index,
                                open_exc,
                            )
                            last_error_log_ts = now_log

                    if not opened:
                        self._consecutive_errors += 1
                        if self._consecutive_errors >= 3:
                            self._clear_live_frame()
                        self._stop_event.wait(self.reconnect_interval_seconds)
                        continue

                if slot.source.resolved_backend:
                    self._backend_name = slot.source.resolved_backend

                cam_lock = self._get_process_lock(self.codigo_camara)
                step_ok = False
                try:
                    with cam_lock:
                        if self._stop_event.is_set():
                            break

                        now_mono = time.monotonic()
                        has_persistence = (
                            getattr(self._coordinator, "_detection_repository", None) is not None
                        )
                        cam_persist_state = self._camera_persist_states.setdefault(
                            self.codigo_camara,
                            {"last_persist_ts": 0.0, "had_vehicle": False},
                        )
                        last_ts = float(cam_persist_state.get("last_persist_ts", 0.0))
                        debounce_ttl = float(self._get_debounce_ttl())
                        time_elapsed_ok = (now_mono - last_ts) >= debounce_ttl
                        new_arrival = not bool(cam_persist_state.get("had_vehicle", False))
                        persist_flag = bool(has_persistence and (time_elapsed_ok or new_arrival))

                        envelope = self._coordinator.process_camera_step(
                            self.codigo_camara,
                            persist_as_new_event=persist_flag,
                        )

                        if envelope is None:
                            self._stop_event.wait(frame_interval)
                            continue

                        vr = envelope.vision_result
                        if vr.status == VisionStatus.CAMERA_ERROR:
                            self._consecutive_errors += 1
                            now_log = time.monotonic()
                            if now_log - last_error_log_ts >= 5.0:
                                logger.warning(
                                    "Fallo de lectura USB en '%s' (intento %d): %s",
                                    self.codigo_camara,
                                    self._consecutive_errors,
                                    vr.error_message,
                                )
                                last_error_log_ts = now_log

                            if self._consecutive_errors >= 3:
                                self._clear_live_frame()

                            if self._consecutive_errors >= self.disconnect_threshold:
                                logger.warning(
                                    "Desconexión física detectada en '%s'. Liberando descriptor para reconexión limpia.",
                                    self.codigo_camara,
                                )
                                slot.source.release()
                                self._consecutive_errors = 0
                                self._stop_event.wait(self.reconnect_interval_seconds)
                                continue
                        else:
                            self._consecutive_errors = 0
                            step_ok = True

                            if persist_flag and vr.vehicle_detected and envelope.id_deteccion is not None:
                                cam_persist_state["last_persist_ts"] = now_mono
                                self._last_persist_timestamps[self.codigo_camara] = now_mono
                            cam_persist_state["had_vehicle"] = bool(vr.vehicle_detected)

                            seq, frame_bgr = slot.source.get_last_frame()
                            if frame_bgr is not None and not self._stop_event.is_set():
                                h, w = frame_bgr.shape[:2]
                                self._last_resolution = f"{w}x{h}"
                                try:
                                    pixel_roi = None
                                    if slot.area is not None:
                                        pixel_roi = project_normalized_roi(
                                            slot.area, frame_width=w, frame_height=h
                                        )
                                    dets = envelope.detections_in_roi if envelope else ()
                                    annotated_bgr = render_annotated_frame(
                                        frame_bgr,
                                        detections_in_roi=dets,
                                        pixel_roi=pixel_roi,
                                    )
                                    ok_enc, enc_bytes = cv2.imencode(
                                        ".jpg",
                                        annotated_bgr,
                                        [cv2.IMWRITE_JPEG_QUALITY, 80],
                                    )
                                    live_jpeg = enc_bytes.tobytes() if ok_enc else None
                                except Exception as annot_exc:
                                    logger.warning(
                                        "Fallo al anotar fotograma USB para '%s': %s",
                                        self.codigo_camara,
                                        annot_exc,
                                    )
                                    ok_enc, enc_bytes = cv2.imencode(
                                        ".jpg",
                                        frame_bgr,
                                        [cv2.IMWRITE_JPEG_QUALITY, 80],
                                    )
                                    live_jpeg = enc_bytes.tobytes() if ok_enc else None

                                if live_jpeg is not None and not self._stop_event.is_set():
                                    latency_ms = round((time.perf_counter() - tick_start) * 1000)
                                    cond = self._get_condition(self.codigo_camara)
                                    with cond:
                                        if not self._stop_event.is_set():
                                            self._latest_frames_store[self.codigo_camara] = {
                                                "jpeg": live_jpeg,
                                                "sequence": envelope.frame_sequence or seq,
                                                "timestamp": time.time(),
                                                "status": vr.status.value,
                                                "vehicle_detected": bool(vr.vehicle_detected),
                                                "tipo_vehiculo": vr.vehicle_type_pred,
                                                "confianza": vr.vehicle_confidence,
                                                "in_roi": envelope.metrics.in_roi_now if envelope else 0,
                                                "latency_ms": latency_ms,
                                            }
                                            cond.notify_all()
                except Exception as loop_exc:
                    now_log = time.monotonic()
                    if now_log - last_error_log_ts >= 5.0:
                        logger.error(
                            "Excepción aislada en CameraPullWorker '%s': %s",
                            self.codigo_camara,
                            loop_exc,
                            exc_info=True,
                        )
                        last_error_log_ts = now_log
                    self._stop_event.wait(0.5)
                    continue

                elapsed = time.perf_counter() - tick_start
                sleep_for = frame_interval - elapsed
                if not step_ok:
                    sleep_for = max(0.25, sleep_for)
                if sleep_for > 0:
                    self._stop_event.wait(sleep_for)
        finally:
            self._release_slot_source()


class CameraPullWorkerManager:
    """Administrador thread-safe de workers Pull por cámara lógica y dispositivo físico."""

    def __init__(
        self,
        *,
        latest_frames_store: Dict[str, Dict[str, Any]],
        get_condition_fn: Callable[[str], threading.Condition],
        get_process_lock_fn: Callable[[str], threading.RLock],
        camera_persist_states: Dict[str, Dict[str, Any]],
        last_persist_timestamps: Dict[str, float],
        get_debounce_ttl_fn: Callable[[], float],
    ) -> None:
        self._latest_frames_store = latest_frames_store
        self._get_condition = get_condition_fn
        self._get_process_lock = get_process_lock_fn
        self._camera_persist_states = camera_persist_states
        self._last_persist_timestamps = last_persist_timestamps
        self._get_debounce_ttl = get_debounce_ttl_fn

        self._workers: Dict[str, CameraPullWorker] = {}
        self._lock = threading.RLock()

    def is_running(self, codigo_camara: str) -> bool:
        code = codigo_camara.strip().upper()
        with self._lock:
            w = self._workers.get(code)
            return bool(w and w.is_running)

    def get_camera_using_device(self, device_index: int) -> Optional[str]:
        """Retorna el código de cámara que tiene activo un worker sobre `device_index`."""
        with self._lock:
            for code, w in self._workers.items():
                if w.is_running and w.device_index == int(device_index):
                    return code
            return None

    def get_active_usb_map(self) -> Dict[int, Dict[str, Any]]:
        """Mapa `{device_index: metadata}` de dispositivos actualmente gestionados por workers."""
        with self._lock:
            active_map: Dict[int, Dict[str, Any]] = {}
            for code, w in self._workers.items():
                if w.is_running and w.device_index is not None:
                    meta = w.get_metadata()
                    active_map[int(w.device_index)] = meta
            return active_map

    def start_worker(
        self,
        *,
        codigo_camara: str,
        coordinator: VisionEngineCoordinator,
        device_index: Optional[int] = None,
        target_fps: Optional[float] = None,
        reconnect_interval_seconds: float = 2.0,
    ) -> CameraPullWorker:
        code = codigo_camara.strip().upper()
        if target_fps is None:
            raw_fps = os.environ.get("VIGIA_USB_TARGET_FPS", "15.0").strip()
            try:
                target_fps = float(raw_fps)
            except ValueError:
                target_fps = 15.0

        with self._lock:
            if device_index is not None:
                other_cam = self.get_camera_using_device(device_index)
                if other_cam is not None and other_cam != code:
                    raise RuntimeError(
                        f"El dispositivo USB {device_index} ya está en uso por la cámara '{other_cam}'."
                    )

            existing = self._workers.pop(code, None)
            if existing is not None:
                existing.stop(clear_frames=False, timeout=5.0)

            worker = CameraPullWorker(
                codigo_camara=code,
                device_index=device_index,
                coordinator=coordinator,
                latest_frames_store=self._latest_frames_store,
                get_condition_fn=self._get_condition,
                get_process_lock_fn=self._get_process_lock,
                camera_persist_states=self._camera_persist_states,
                last_persist_timestamps=self._last_persist_timestamps,
                get_debounce_ttl_fn=self._get_debounce_ttl,
                target_fps=target_fps,
                reconnect_interval_seconds=reconnect_interval_seconds,
            )
            worker.start()
            self._workers[code] = worker
            return worker

    def stop_worker(
        self,
        codigo_camara: str,
        *,
        clear_frames: bool = True,
        timeout: float = 5.0,
    ) -> bool:
        code = codigo_camara.strip().upper()
        with self._lock:
            worker = self._workers.pop(code, None)
        if worker is None:
            if clear_frames:
                try:
                    cond = self._get_condition(code)
                    with cond:
                        self._latest_frames_store.pop(code, None)
                        cond.notify_all()
                except Exception:
                    pass
            return False
        return worker.stop(clear_frames=clear_frames, timeout=timeout)

    def stop_all(self, *, clear_frames: bool = True, timeout: float = 5.0) -> None:
        with self._lock:
            codes = list(self._workers.keys())
        for code in codes:
            try:
                self.stop_worker(code, clear_frames=clear_frames, timeout=timeout)
            except Exception as exc:
                logger.warning("Error deteniendo CameraPullWorker '%s' en stop_all: %s", code, exc)
