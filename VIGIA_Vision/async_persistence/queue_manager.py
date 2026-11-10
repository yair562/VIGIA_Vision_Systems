"""
VIGIA_Vision.async_persistence.queue_manager
============================================
Gestor de colas particionadas por ranura de cámara con política estricta
de backpressure, asignación de secuencia causal monótona (camera_sequence)
y diferenciación canónica entre reintentos y capturas consecutivas legítimas.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Dict, Optional, Tuple
from uuid import UUID

from VIGIA_Vision.async_persistence.models import PersistenceTaskDTO

logger = logging.getLogger(__name__)


class CameraPartitionSlot:
    """Ranura aislada de concurrencia para una cámara específica."""

    def __init__(self, codigo_camara: str, max_depth: int = 64) -> None:
        self.codigo_camara = codigo_camara
        self.max_depth = max_depth
        self.queue: queue.Queue[PersistenceTaskDTO] = queue.Queue(maxsize=max_depth)
        self.lock = threading.Lock()
        self.current_sequence: int = 0
        
        # Deduplicación de reintentos basada en identidad lógica de captura (capture_id)
        self.capture_cache: Dict[UUID, Tuple[UUID, float]] = {}  # capture_id -> (task_id, ts_mono)
        
        # Registro de integridad de contenido (content_hash)
        self.content_cache: Dict[str, Tuple[UUID, float]] = {}  # content_hash -> (capture_id, ts_mono)

    def next_sequence(self) -> int:
        """Incrementa atómicamente y retorna la siguiente secuencia causal."""
        with self.lock:
            self.current_sequence += 1
            return self.current_sequence

    def set_sequence_floor(self, floor_seq: int) -> None:
        """Ajusta el piso de secuencia tras una recuperación de spool/BD."""
        with self.lock:
            if floor_seq > self.current_sequence:
                self.current_sequence = floor_seq


class PartitionedQueueManager:
    """
    Gestiona las particiones de colas para múltiples cámaras con límites
    estrictos de memoria RAM y rechazo por saturación (HTTP 429).
    """

    def __init__(
        self,
        max_depth_per_camera: int = 64,
        dedup_window_seconds: float = 60.0,
    ) -> None:
        self._max_depth = max_depth_per_camera
        self._dedup_ttl = dedup_window_seconds
        self._slots: Dict[str, CameraPartitionSlot] = {}
        self._manager_lock = threading.Lock()

    def get_or_create_slot(self, codigo_camara: str) -> CameraPartitionSlot:
        """Obtiene o inicializa de forma thread-safe la ranura de una cámara."""
        with self._manager_lock:
            if codigo_camara not in self._slots:
                self._slots[codigo_camara] = CameraPartitionSlot(
                    codigo_camara, max_depth=self._max_depth
                )
            return self._slots[codigo_camara]

    def assign_camera_sequence(self, codigo_camara: str) -> int:
        """Asigna de forma protegida el siguiente número de secuencia causal."""
        slot = self.get_or_create_slot(codigo_camara)
        return slot.next_sequence()

    def enqueue_task(
        self,
        task: PersistenceTaskDTO,
        timeout: float = 0.200,
    ) -> Tuple[bool, str]:
        """
        Intenta encolar la tarea en la ranura de su cámara.
        
        Retorna:
        - (True, "ENQUEUED"): Tarea nueva admitida y encolada con éxito.
        - (True, "DUPLICATE_RETRY_ACK"): Reintento de la misma captura ya admitido (idempotente).
        - (False, "QUEUE_SATURATED_429"): Cola saturada tras expirar timeout de backpressure.
        """
        slot = self.get_or_create_slot(task.codigo_camara)
        now_mono = time.monotonic()

        with slot.lock:
            # 1. Purgar caché de deduplicación expirada
            expired_captures = [
                cid for cid, (_, ts) in slot.capture_cache.items()
                if (now_mono - ts) > self._dedup_ttl
            ]
            for cid in expired_captures:
                slot.capture_cache.pop(cid, None)

            # 2. Comprobar si es un reintento idéntico de la misma captura lógica
            if task.capture_id in slot.capture_cache:
                logger.info(
                    "Reintento detectado para capture_id=%s en cam=%s. Retornando ACK sin duplicar.",
                    task.capture_id,
                    task.codigo_camara,
                )
                return True, "DUPLICATE_RETRY_ACK"

        # 3. Intento de encolado con timeout acotado (Backpressure)
        try:
            slot.queue.put(task, block=True, timeout=timeout)
        except queue.Full:
            logger.warning(
                "Ranura saturada (%d tareas) para cam=%s. Activando rechazo HTTP 429.",
                slot.max_depth,
                task.codigo_camara,
            )
            return False, "QUEUE_SATURATED_429"

        # 4. Registrar en caché tras encolar exitosamente
        with slot.lock:
            slot.capture_cache[task.capture_id] = (task.task_id, now_mono)
            slot.content_cache[task.content_hash] = (task.capture_id, now_mono)

        return True, "ENQUEUED"

    def get_queue_depth(self, codigo_camara: str) -> int:
        """Retorna la profundidad actual de la cola de una cámara."""
        with self._manager_lock:
            slot = self._slots.get(codigo_camara)
            return slot.queue.qsize() if slot else 0

    def get_total_depth(self) -> int:
        """Retorna la suma agregada de tareas en cola para todas las cámaras."""
        with self._manager_lock:
            return sum(slot.queue.qsize() for slot in self._slots.values())
