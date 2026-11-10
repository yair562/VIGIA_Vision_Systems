"""
VIGIA_API.pull_worker
=====================
Mecanismo de captura concurrente desacoplado para fuentes de vídeo tipo Pull
(cámaras USB locales y flujos RTSP) en VIGÍA Vision Systems (VIGIA-USB-02).

Responsabilidades:
- Gestionar el ciclo de vida de un hilo trabajador en segundo plano por cámara física.
- Leer fotogramas continuamente desde ``OpenCVCaptureSource`` a una cadencia objetivo (FPS).
- Ejecutar el pipeline de inferencia y evaluación ROI mediante ``VisionEngineCoordinator.process_camera_step()``.
- Aplicar deduplicación y debounce temporal para persistir únicamente eventos nuevos legítimos.
- Renderizar fotogramas anotados en memoria y publicarlos al buffer global ``_latest_camera_frames``.
- Desconectar y liberar limpiamente descriptores de hardware ante detención o revocación.
- Prevenir colisiones, condiciones de carrera y duplicidad de workers por cámara lógica.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

try:
    import cv2
except ImportError:
    cv2 = None

from VIGIA_Vision.detection.roi_and_preprocess import project_normalized_roi
from VIGIA_Vision.runtime.evidence_storage import render_annotated_frame

logger = logging.getLogger(__name__)


class CameraPullWorker:
    """
    Hilo trabajador en segundo plano administrado para una cámara lógica individual
    alimentada por una fuente pull (USB o RTSP).
    """

    def __init__(
        self,
        codigo_camara: str,
        coordinator: Any,
        frame_consumer: Callable[[str, Dict[str, Any]], None],
        process_lock_provider: Callable[[str], Any],
        target_fps: float = 15.0,
        debounce_seconds: float = 3.0,
        logger_instance: Optional[logging.Logger] = None,
    ) -> None:
        self.codigo_camara = codigo_camara.strip().upper()
        self._coordinator = coordinator
        self._frame_consumer = frame_consumer
        self._lock_provider = process_lock_provider
        self.target_fps = max(1.0, min(60.0, float(target_fps)))
        self.debounce_seconds = max(0.5, float(debounce_seconds))
        self._logger = logger_instance or logger

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._is_running = False
        self._consecutive_failures = 0
        self._lock = threading.RLock()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return bool(self._is_running and self._thread and self._thread.is_alive())

    def start(self) -> bool:
        """Inicia el hilo de captura continua si no está ya en ejecución."""
        with self._lock:
            if self.is_running:
                self._logger.warning("Worker para '%s' ya se encuentra activo.", self.codigo_camara)
                return True

            self._stop_event.clear()
            self._consecutive_failures = 0
            self._thread = threading.Thread(
                target=self._run_loop,
                name=f"VigiaPullWorker-{self.codigo_camara}",
                daemon=True,
            )
            self._is_running = True
            self._thread.start()
            self._logger.info(
                "CameraPullWorker iniciado para cámara '%s' (%.1f FPS, debounce=%.1fs).",
                self.codigo_camara,
                self.target_fps,
                self.debounce_seconds,
            )
            return True

    def stop(self, timeout: float = 3.0) -> bool:
        """Detiene el worker y espera la liberación ordenada del hardware."""
        with self._lock:
            if not self._is_running:
                return True

            self._logger.info("Deteniendo CameraPullWorker para '%s'...", self.codigo_camara)
            self._stop_event.set()
            thread = self._thread

        if thread and thread.is_alive() and threading.current_thread() != thread:
            thread.join(timeout=timeout)
            if thread.is_alive():
                self._logger.warning(
                    "CameraPullWorker para '%s' no finalizó en %.1fs. Forzando cierre de descriptor.",
                    self.codigo_camara,
                    timeout,
                )

        with self._lock:
            self._is_running = False
            self._thread = None
            try:
                if self._coordinator and self._coordinator.registry:
                    slot = self._coordinator.registry.get_slot(self.codigo_camara)
                    if slot and slot.source:
                        slot.source.release()
            except Exception as rel_err:
                self._logger.warning("Excepción al liberar descriptor de '%s': %s", self.codigo_camara, rel_err)

        self._logger.info("CameraPullWorker para '%s' detenido completamente.", self.codigo_camara)
        return True

    def _run_loop(self) -> None:
        """Bucle principal de lectura física, inferencia y publicación de vídeo."""
        interval = 1.0 / self.target_fps
        had_vehicle = False
        last_persist_ts = 0.0

        try:
            slot = self._coordinator.registry.get_slot(self.codigo_camara)
        except Exception as slot_err:
            self._logger.error("No se pudo obtener slot para '%s': %s", self.codigo_camara, slot_err)
            self._is_running = False
            return

        if not slot.source.is_opened():
            if not slot.source.open():
                self._logger.error("No se pudo abrir la fuente física para '%s' al iniciar worker.", self.codigo_camara)

        while not self._stop_event.is_set():
            t_start = time.monotonic()
            try:
                # 1. Adquisición del fotograma de hardware
                read_res = slot.source.read_frame()
                if not read_res.ok or read_res.frame is None:
                    self._consecutive_failures += 1
                    if self._consecutive_failures >= 10:
                        self._logger.warning(
                            "Fallo recurrente de lectura física en '%s' (%d intentos). Reiniciando descriptor...",
                            self.codigo_camara,
                            self._consecutive_failures,
                        )
                        slot.source.release()
                        time.sleep(0.5)
                        slot.source.open()
                        self._consecutive_failures = 0
                    self._stop_event.wait(0.1)
                    continue

                self._consecutive_failures = 0
                frame_bgr = read_res.frame
                h, w = frame_bgr.shape[:2]

                # 2. Evaluación de persistencia atómica (Debounce vehicular)
                now_mono = time.monotonic()
                time_elapsed_ok = (now_mono - last_persist_ts) >= self.debounce_seconds
                new_arrival = not had_vehicle
                persist_debounce_ok = bool(time_elapsed_ok or new_arrival)
                has_persistence = getattr(self._coordinator, "_detection_repository", None) is not None
                persist_flag = bool(has_persistence and persist_debounce_ok)

                # 3. Procesamiento síncrono en VisionEngineCoordinator protegido por lock
                cam_lock = self._lock_provider(self.codigo_camara)
                with cam_lock:
                    envelope = self._coordinator.process_camera_step(
                        self.codigo_camara,
                        persist_as_new_event=persist_flag,
                        read_result=read_res,
                    )

                if envelope is not None and envelope.vision_result is not None:
                    vr = envelope.vision_result
                    current_vehicle = bool(vr.vehicle_detected)
                    if persist_flag and current_vehicle:
                        last_persist_ts = now_mono
                    had_vehicle = current_vehicle

                    # 4. Renderizar fotograma anotado para streaming en tiempo real (MJPEG)
                    live_jpeg = None
                    if cv2 is not None:
                        try:
                            pixel_roi = None
                            if slot.area is not None:
                                pixel_roi = project_normalized_roi(slot.area, frame_width=w, frame_height=h)
                            dets = envelope.detections_in_roi or ()
                            annotated_bgr = render_annotated_frame(frame_bgr, detections_in_roi=dets, pixel_roi=pixel_roi)
                            ok_enc, enc_bytes = cv2.imencode(".jpg", annotated_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
                            if ok_enc:
                                live_jpeg = enc_bytes.tobytes()
                        except Exception as annot_err:
                            self._logger.warning("Fallo al anotar fotograma para '%s': %s", self.codigo_camara, annot_err)

                    if live_jpeg is not None:
                        payload = {
                            "jpeg": live_jpeg,
                            "sequence": envelope.frame_sequence or read_res.frame_sequence,
                            "timestamp": time.time(),
                            "status": vr.status.value,
                            "vehicle_detected": bool(vr.vehicle_detected),
                            "tipo_vehiculo": vr.vehicle_type_pred,
                            "confianza": vr.vehicle_confidence,
                            "in_roi": envelope.metrics.in_roi_now if envelope.metrics else 0,
                            "latency_ms": round((time.monotonic() - t_start) * 1000),
                        }
                        self._frame_consumer(self.codigo_camara, payload)

            except Exception as loop_err:
                if not self._stop_event.is_set():
                    self._logger.error("Error en ciclo de captura de '%s': %s", self.codigo_camara, loop_err, exc_info=True)
                self._stop_event.wait(0.2)

            t_elapsed = time.monotonic() - t_start
            t_sleep = interval - t_elapsed
            if t_sleep > 0:
                self._stop_event.wait(t_sleep)

        # Cierre y liberación final segura
        try:
            slot.source.release()
        except Exception:
            pass
        with self._lock:
            self._is_running = False


class CameraPullWorkerManager:
    """
    Administrador central de ciclo de vida para trabajadores de captura pull.
    Garantiza cardinalidad 1:1 entre cámara lógica y worker en ejecución.
    """

    def __init__(
        self,
        coordinator: Any,
        frame_consumer: Callable[[str, Dict[str, Any]], None],
        process_lock_provider: Callable[[str], Any],
        target_fps: float = 15.0,
        debounce_seconds: float = 3.0,
    ) -> None:
        self._coordinator = coordinator
        self._frame_consumer = frame_consumer
        self._lock_provider = process_lock_provider
        self._target_fps = target_fps
        self._debounce_seconds = debounce_seconds
        self._workers: Dict[str, CameraPullWorker] = {}
        self._lock = threading.RLock()

    def start_worker(self, codigo_camara: str) -> bool:
        """Inicia el worker para la cámara lógica indicada si la fuente es Pull."""
        cam_clean = codigo_camara.strip().upper()
        with self._lock:
            if not self._coordinator or not self._coordinator.registry:
                logger.warning("No se puede iniciar worker para '%s': coordinador no inicializado.", cam_clean)
                return False

            try:
                slot = self._coordinator.registry.get_slot(cam_clean)
            except Exception as exc:
                logger.error("Cámara '%s' no encontrada en el registro de topología: %s", cam_clean, exc)
                return False

            # Si ya hay un worker corriendo para esta cámara, verificar que siga vivo
            existing = self._workers.get(cam_clean)
            if existing and existing.is_running:
                logger.info("Worker para '%s' ya está en ejecución activa.", cam_clean)
                return True

            worker = CameraPullWorker(
                codigo_camara=cam_clean,
                coordinator=self._coordinator,
                frame_consumer=self._frame_consumer,
                process_lock_provider=self._lock_provider,
                target_fps=self._target_fps,
                debounce_seconds=self._debounce_seconds,
            )
            success = worker.start()
            if success:
                self._workers[cam_clean] = worker
            return success

    def stop_worker(self, codigo_camara: str, timeout: float = 3.0) -> bool:
        """Detiene de forma síncrona el worker de la cámara indicada."""
        cam_clean = codigo_camara.strip().upper()
        with self._lock:
            worker = self._workers.pop(cam_clean, None)
            if worker:
                return worker.stop(timeout=timeout)
            return True

    def stop_all(self, timeout: float = 3.0) -> None:
        """Detiene de manera idempotente todos los workers en ejecución."""
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()

        for w in workers:
            try:
                w.stop(timeout=timeout)
            except Exception as err:
                logger.warning("Error al detener worker de '%s': %s", w.codigo_camara, err)

    def is_worker_running(self, codigo_camara: str) -> bool:
        cam_clean = codigo_camara.strip().upper()
        with self._lock:
            w = self._workers.get(cam_clean)
            return bool(w and w.is_running)

    def get_running_cameras(self) -> List[str]:
        with self._lock:
            return [code for code, w in self._workers.items() if w.is_running]
