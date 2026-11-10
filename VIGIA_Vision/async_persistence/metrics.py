"""
VIGIA_Vision.async_persistence.metrics
======================================
Colector thread-safe de métricas operacionales, percentiles de latencia,
seguimiento de memoria RSS e instrumentación del piloto de persistencia.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import psutil

logger = logging.getLogger(__name__)


class PilotMetricsCollector:
    """
    Colector de telemetría y métricas para el arnés de pruebas del piloto asíncrono.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process = psutil.Process()

        # Temporizaciones (en milisegundos)
        self.enqueue_latencies_ms: List[float] = []
        self.worker_wait_times_ms: List[float] = []
        self.persistence_times_ms: List[float] = []
        self.sql_commit_times_ms: List[float] = []
        self.recovery_latencies_ms: List[float] = []

        # Contadores de eventos
        self.enqueued_count: int = 0
        self.confirmed_count: int = 0
        self.rejected_429_count: int = 0
        self.duplicate_retry_count: int = 0
        self.retry_count: int = 0
        self.dlq_count: int = 0
        self.discontinuity_count: int = 0
        self.recovered_count: int = 0

        # Muestreo de memoria (tiempo_mono, rss_bytes)
        self.rss_samples: List[Tuple[float, int]] = []
        self._start_time_mono = time.monotonic()

    def record_enqueue(self, latency_ms: float, status: str) -> None:
        with self._lock:
            self.enqueue_latencies_ms.append(latency_ms)
            if status == "ENQUEUED":
                self.enqueued_count += 1
            elif status == "QUEUE_SATURATED_429":
                self.rejected_429_count += 1
            elif status == "DUPLICATE_RETRY_ACK":
                self.duplicate_retry_count += 1

    def record_worker_wait(self, wait_ms: float) -> None:
        with self._lock:
            self.worker_wait_times_ms.append(wait_ms)

    def record_persistence_time(self, persist_ms: float) -> None:
        with self._lock:
            self.persistence_times_ms.append(persist_ms)

    def record_sql_commit(self, sql_ms: float) -> None:
        with self._lock:
            self.sql_commit_times_ms.append(sql_ms)
            self.confirmed_count += 1

    def record_retry(self) -> None:
        with self._lock:
            self.retry_count += 1

    def record_dlq(self) -> None:
        with self._lock:
            self.dlq_count += 1

    def record_discontinuity(self) -> None:
        with self._lock:
            self.discontinuity_count += 1

    def record_recovery(self, count: int, latency_ms: float) -> None:
        with self._lock:
            self.recovered_count += count
            self.recovery_latencies_ms.append(latency_ms)

    def record_rss(self) -> int:
        rss = self._process.memory_info().rss
        with self._lock:
            self.rss_samples.append((time.monotonic(), rss))
        return rss

    @staticmethod
    def _compute_stats(values: List[float]) -> Dict[str, float]:
        if not values:
            return {"count": 0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0, "max": 0.0}
        arr = np.array(values, dtype=np.float64)
        return {
            "count": int(len(arr)),
            "p50": float(np.percentile(arr, 50)),
            "p90": float(np.percentile(arr, 90)),
            "p95": float(np.percentile(arr, 95)),
            "p99": float(np.percentile(arr, 99)),
            "mean": float(np.mean(arr)),
            "max": float(np.max(arr)),
        }

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            elapsed_total = max(0.001, time.monotonic() - self._start_time_mono)
            throughput_fps = self.confirmed_count / elapsed_total

            rss_vals = [s[1] for s in self.rss_samples]
            rss_mb_min = (min(rss_vals) / (1024 * 1024)) if rss_vals else 0.0
            rss_mb_max = (max(rss_vals) / (1024 * 1024)) if rss_vals else 0.0
            rss_delta_mb = rss_mb_max - rss_mb_min

            return {
                "elapsed_seconds": round(elapsed_total, 3),
                "throughput_fps": round(throughput_fps, 2),
                "counters": {
                    "enqueued": self.enqueued_count,
                    "confirmed": self.confirmed_count,
                    "rejected_429": self.rejected_429_count,
                    "duplicate_retries": self.duplicate_retry_count,
                    "retries": self.retry_count,
                    "dlq": self.dlq_count,
                    "discontinuities": self.discontinuity_count,
                    "recovered": self.recovered_count,
                },
                "latencies_ms": {
                    "enqueue": self._compute_stats(self.enqueue_latencies_ms),
                    "worker_wait": self._compute_stats(self.worker_wait_times_ms),
                    "persistence": self._compute_stats(self.persistence_times_ms),
                    "sql_commit": self._compute_stats(self.sql_commit_times_ms),
                    "recovery": self._compute_stats(self.recovery_latencies_ms),
                },
                "memory_rss_mb": {
                    "min": round(rss_mb_min, 2),
                    "max": round(rss_mb_max, 2),
                    "delta": round(rss_delta_mb, 2),
                    "samples_count": len(rss_vals),
                },
            }
