"""
VIGIA_Vision.capture.sources
============================
Contratos y adaptadores de captura de fotogramas para VIGÍA Vision Systems (Etapa 1).

Provee dos modalidades bajo el mismo contrato ``IFrameCaptureSource``:
1. ``OpenCVCaptureSource`` (Pull): fuentes locales USB, streams RTSP o archivos
   de video. No abre descriptores de hardware en ``__init__`` ni al importar el
   módulo; exige invocación explícita a ``open()``.
2. ``MobilePushFrameBuffer`` (Push): buffer en memoria de ranura única
   (*single-slot latest-frame*) ligado a una cámara previamente registrada.
   - Protegido para concurrencia mediante ``threading.RLock``.
   - Sobrescribe el fotograma pendiente si llega uno más reciente (memoria O(1)).
   - Asigna un número de secuencia monótonamente creciente (``frame_sequence``)
     a cada imagen depositada.
   - Rechaza fotogramas cuya antigüedad supere el ``ttl_seconds`` configurado.
   - No reprocesa indefinidamente el mismo ``frame_sequence``: si el consumidor
     consulta el buffer y no ha llegado una secuencia nueva (mientras siga dentro
     del TTL), informa ``is_already_processed=True`` sin declarar error técnico
     ni disparar reprocesamiento redundante.

No abre servidores HTTP ni HTTPS en este módulo.
"""

from __future__ import annotations

import os
import sys
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple, Union, runtime_checkable

from VIGIA_Vision.detection.models import CaptureReadResult


def parse_usb_source_uri(source_uri: Union[int, str]) -> Tuple[Union[int, str], bool]:
    """
    Normaliza una URI o índice de fuente de captura para `OpenCVCaptureSource`.

    Soporta:
    - Enteros >= 0 (ej. ``0``, ``1``) -> ``(0, True)``
    - Cadenas numéricas (ej. ``"0"``) -> ``(0, True)``
    - Esquema explícito USB (ej. ``"usb://0"``) -> ``(0, True)``
    - Streams RTSP/HTTP o rutas locales -> ``(uri, False)``

    Lanza ``ValueError`` si la URI está vacía o si el esquema ``usb://`` no
    contiene un índice entero no negativo válido.
    """
    if isinstance(source_uri, bool):
        raise ValueError(f"source_uri={source_uri!r} no puede ser booleano.")

    if isinstance(source_uri, int):
        if source_uri < 0:
            raise ValueError(f"source_uri={source_uri!r} debe ser un entero >= 0.")
        return source_uri, True

    if isinstance(source_uri, str):
        cleaned = source_uri.strip()
        if not cleaned:
            raise ValueError("source_uri no puede ser una cadena vacía.")

        if cleaned.lower().startswith("usb://"):
            raw_idx = cleaned[6:].strip().rstrip("/")
            if not raw_idx or not raw_idx.isdigit():
                raise ValueError(
                    f"Índice USB inválido en URI {source_uri!r}. "
                    "Se esperaba formato 'usb://<índice>' con entero >= 0 (ej. 'usb://0')."
                )
            return int(raw_idx), True

        if cleaned.isdigit():
            return int(cleaned), True

        return cleaned, False

    raise ValueError(f"source_uri={source_uri!r} debe ser un entero >= 0 o cadena no vacía.")


def probe_local_usb_cameras(
    max_index: int = 4,
    active_indices: Optional[Dict[int, Dict[str, Any]]] = None,
    backend_preference: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Sondea cámaras USB locales disponibles sin dejar descriptores físicos abiertos.

    Si un índice se encuentra actualmente en uso por un worker gestionado en
    ``active_indices``, reporta su información sin abrir un segundo descriptor
    simultáneo sobre el hardware.
    """
    import cv2

    results: List[Dict[str, Any]] = []
    active_map = active_indices or {}
    pref = (backend_preference or os.environ.get("VIGIA_USB_OPENCV_BACKEND", "dshow")).strip().lower()

    for idx in range(max(1, int(max_index))):
        if idx in active_map:
            info = active_map[idx]
            results.append(
                {
                    "device_index": idx,
                    "uri": f"usb://{idx}",
                    "name": info.get("name") or f"Cámara USB Local {idx}",
                    "width": info.get("width"),
                    "height": info.get("height"),
                    "resolution": info.get("resolution") or "En uso",
                    "backend": info.get("backend") or "MSMF/DSHOW",
                    "available": True,
                    "in_use_by_camera": info.get("codigo_camara"),
                }
            )
            continue

        cap = None
        opened = False
        backend_used = "DEFAULT"
        try:
            backends_to_try: List[Tuple[str, Optional[int]]] = []
            if sys.platform == "win32":
                if pref == "msmf":
                    backends_to_try = [
                        ("MSMF", getattr(cv2, "CAP_MSMF", None)),
                        ("DSHOW", getattr(cv2, "CAP_DSHOW", None)),
                    ]
                elif pref == "auto":
                    backends_to_try = [
                        ("ANY", getattr(cv2, "CAP_ANY", None)),
                        ("DSHOW", getattr(cv2, "CAP_DSHOW", None)),
                    ]
                else:
                    backends_to_try = [
                        ("DSHOW", getattr(cv2, "CAP_DSHOW", None)),
                        ("MSMF", getattr(cv2, "CAP_MSMF", None)),
                    ]
            else:
                backends_to_try = [("ANY", None)]

            for b_name, b_flag in backends_to_try:
                tmp_cap = cv2.VideoCapture(idx, b_flag) if b_flag is not None else cv2.VideoCapture(idx)
                if tmp_cap is not None and tmp_cap.isOpened():
                    cap = tmp_cap
                    opened = True
                    try:
                        backend_used = cap.getBackendName()
                    except Exception:
                        backend_used = b_name
                    break
                if tmp_cap is not None:
                    try:
                        tmp_cap.release()
                    except Exception:
                        pass

            if opened and cap is not None:
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
                res_str = f"{width}x{height}" if (width > 0 and height > 0) else "Desconocida"
                results.append(
                    {
                        "device_index": idx,
                        "uri": f"usb://{idx}",
                        "name": f"Cámara USB / Webcam Local ({idx})",
                        "width": width if width > 0 else None,
                        "height": height if height > 0 else None,
                        "resolution": res_str,
                        "backend": backend_used,
                        "available": True,
                        "in_use_by_camera": None,
                    }
                )
        except Exception:
            pass
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    return results


@runtime_checkable
class IFrameCaptureSource(Protocol):
    """Contrato común para cualquier fuente de captura de fotogramas de VIGÍA."""

    def open(self) -> bool:
        """Adquiere o habilita explícitamente la fuente de captura."""
        ...  # pragma: no cover

    def is_opened(self) -> bool:
        """Indica si la fuente se encuentra actualmente abierta/habilitada."""
        ...  # pragma: no cover

    def read_frame(self) -> CaptureReadResult:
        """Lee el siguiente fotograma disponible y retorna ``CaptureReadResult``."""
        ...  # pragma: no cover

    def release(self) -> None:
        """Libera de manera idempotente y segura los recursos asociados."""
        ...  # pragma: no cover


class OpenCVCaptureSource:
    """
    Fuente de captura *pull* basada en ``cv2.VideoCapture`` (USB, RTSP o archivo).

    Reglas de ciclo de vida:
    - ``__init__`` no invoca ``cv2.VideoCapture`` ni importa ``cv2`` a nivel de
      módulo con efectos secundarios sobre dispositivos.
    - La apertura ocurre exclusivamente cuando se llama a ``open()``.
    - ``read_frame()`` no abre implícitamente el hardware si ``open()`` no fue
      invocado o falló previamente; retorna ``CaptureReadResult(ok=False)``.
    - ``release()`` es idempotente y seguro ante múltiples llamadas.
    """

    def __init__(
        self,
        source_uri: Union[int, str],
        capture_factory: Optional[Callable[[Union[int, str]], Any]] = None,
        clock: Optional[Callable[[], datetime]] = None,
        backend_preference: Optional[str] = None,
    ) -> None:
        self._raw_source_uri: Union[int, str] = source_uri
        resolved_uri, is_usb = parse_usb_source_uri(source_uri)
        self._source_uri: Union[int, str] = resolved_uri
        self._is_usb: bool = is_usb
        self._backend_preference: Optional[str] = backend_preference

        self._capture_factory = capture_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._cap: Optional[Any] = None
        self._sequence: int = 0
        self._last_frame: Optional[Any] = None
        self._resolved_backend: Optional[str] = None
        self._lock = threading.RLock()

    @property
    def source_uri(self) -> Union[int, str]:
        return self._source_uri

    @property
    def raw_source_uri(self) -> Union[int, str]:
        return self._raw_source_uri

    @property
    def is_usb(self) -> bool:
        return self._is_usb

    @property
    def resolved_backend(self) -> Optional[str]:
        return self._resolved_backend

    def get_last_frame(self) -> Tuple[int, Optional[Any]]:
        """Retorna ``(sequence, frame)`` del último fotograma capturado bajo lock."""
        with self._lock:
            return self._sequence, self._last_frame

    def open(self) -> bool:
        """Abre explícitamente el descriptor de video."""
        with self._lock:
            if self._cap is not None and self._is_cap_opened():
                return True

            try:
                if self._capture_factory is not None:
                    cap = self._capture_factory(self._source_uri)
                    self._resolved_backend = "CUSTOM_FACTORY"
                else:
                    import cv2  # Importación perezosa

                    cap = None
                    if self._is_usb and sys.platform == "win32":
                        pref = (
                            self._backend_preference
                            or os.environ.get("VIGIA_USB_OPENCV_BACKEND", "dshow")
                        ).strip().lower()

                        if pref == "msmf":
                            candidates = [
                                ("MSMF", getattr(cv2, "CAP_MSMF", None)),
                                ("DSHOW", getattr(cv2, "CAP_DSHOW", None)),
                            ]
                        elif pref == "auto":
                            candidates = [
                                ("ANY", getattr(cv2, "CAP_ANY", None)),
                                ("DSHOW", getattr(cv2, "CAP_DSHOW", None)),
                            ]
                        else:
                            candidates = [
                                ("DSHOW", getattr(cv2, "CAP_DSHOW", None)),
                                ("MSMF", getattr(cv2, "CAP_MSMF", None)),
                            ]

                        for b_name, b_flag in candidates:
                            tmp = cv2.VideoCapture(self._source_uri, b_flag) if b_flag is not None else cv2.VideoCapture(self._source_uri)
                            if tmp is not None and tmp.isOpened():
                                cap = tmp
                                try:
                                    self._resolved_backend = cap.getBackendName()
                                except Exception:
                                    self._resolved_backend = b_name
                                break
                            if tmp is not None:
                                try:
                                    tmp.release()
                                except Exception:
                                    pass
                    else:
                        cap = cv2.VideoCapture(self._source_uri)
                        try:
                            self._resolved_backend = cap.getBackendName() if cap is not None else None
                        except Exception:
                            self._resolved_backend = "DEFAULT"

                    # Evitar acumulación de fotogramas antiguos en el buffer interno
                    if cap is not None and hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
                        try:
                            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        except Exception:
                            pass
            except Exception:
                self._cap = None
                self._resolved_backend = None
                return False

            if cap is None:
                self._cap = None
                self._resolved_backend = None
                return False

            try:
                opened = bool(cap.isOpened())
            except Exception:
                opened = False

            if not opened:
                try:
                    cap.release()
                except Exception:
                    pass
                self._cap = None
                self._resolved_backend = None
                return False

            self._cap = cap
            return True

    def _is_cap_opened(self) -> bool:
        if self._cap is None:
            return False
        try:
            return bool(self._cap.isOpened())
        except Exception:
            return False

    def is_opened(self) -> bool:
        with self._lock:
            return self._is_cap_opened()

    def read_frame(self) -> CaptureReadResult:
        """
        Lee el fotograma actual desde el descriptor abierto.
        Si la fuente no está abierta o la lectura falla, retorna ``ok=False``
        con ``error_reason`` descriptivo.
        """
        with self._lock:
            now = self._clock()
            if not self._is_cap_opened():
                return CaptureReadResult(
                    ok=False,
                    frame=None,
                    captured_at=now,
                    frame_sequence=None,
                    error_reason="CAPTURE_SOURCE_NOT_OPEN",
                )

            try:
                ret, frame = self._cap.read()
            except Exception as exc:
                return CaptureReadResult(
                    ok=False,
                    frame=None,
                    captured_at=now,
                    frame_sequence=None,
                    error_reason=f"CAPTURE_READ_EXCEPTION: {exc}",
                )

            if not ret or frame is None:
                return CaptureReadResult(
                    ok=False,
                    frame=None,
                    captured_at=now,
                    frame_sequence=None,
                    error_reason="CAPTURE_EMPTY_FRAME",
                )

            self._sequence += 1
            self._last_frame = frame
            return CaptureReadResult(
                ok=True,
                frame=frame,
                captured_at=now,
                frame_sequence=self._sequence,
                error_reason=None,
            )

    def release(self) -> None:
        """Libera de forma idempotente el descriptor de video."""
        with self._lock:
            cap = self._cap
            self._cap = None
            self._last_frame = None
            self._resolved_backend = None
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    def __enter__(self) -> "OpenCVCaptureSource":
        self.open()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()


class MobilePushFrameBuffer:
    """
    Buffer *push* en memoria de ranura única (*single-slot latest-frame*) para
    una cámara registrada que recibe fotogramas desde un dispositivo móvil.

    Características verificables:
    - **Memoria acotada O(1):** almacena a lo sumo 1 fotograma pendiente por instancia.
    - **Sobrescritura determinista:** ``push_frame()`` reemplaza el fotograma
      anterior e incrementa monótonamente ``frame_sequence``.
    - **Control de vigencia (TTL):** si ``(now - received_at) > ttl_seconds``,
      ``read_frame()`` descarta el fotograma vencido y retorna ``ok=False`` con
      ``error_reason='MOBILE_FRAME_EXPIRED_TTL'``.
    - **No reprocesamiento:** registra ``_last_consumed_sequence``. Si se invoca
      ``read_frame()`` cuando el fotograma vigente ya fue consumido (y aún no
      ha vencido por TTL), retorna ``ok=False, is_already_processed=True,
      error_reason='NO_NEW_FRAME_SEQUENCE'`` para que el coordinador no vuelva
      a ejecutar inferencia sobre la misma imagen.
    """

    def __init__(
        self,
        codigo_camara: str,
        ttl_seconds: float = 3.0,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        if not isinstance(codigo_camara, str) or not codigo_camara.strip():
            raise ValueError("codigo_camara debe ser una cadena no vacía.")
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, (int, float))
            or float(ttl_seconds) <= 0.0
        ):
            raise ValueError("ttl_seconds debe ser un número estrictamente mayor que 0.")

        self._codigo_camara = codigo_camara.strip()
        self._ttl_seconds = float(ttl_seconds)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()

        self._opened: bool = False
        self._latest_frame: Optional[Any] = None
        self._latest_timestamp: Optional[datetime] = None
        self._latest_sequence: int = 0
        self._last_consumed_sequence: int = 0

    @property
    def codigo_camara(self) -> str:
        return self._codigo_camara

    @property
    def ttl_seconds(self) -> float:
        return self._ttl_seconds

    @property
    def latest_sequence(self) -> int:
        with self._lock:
            return self._latest_sequence

    @property
    def last_consumed_sequence(self) -> int:
        with self._lock:
            return self._last_consumed_sequence

    def open(self) -> bool:
        """Habilita el buffer para aceptar y entregar fotogramas."""
        with self._lock:
            self._opened = True
            return True

    def is_opened(self) -> bool:
        with self._lock:
            return self._opened

    def push_frame(
        self,
        frame: Any,
        captured_at: Optional[datetime] = None,
    ) -> int:
        """
        Deposita un nuevo fotograma en la ranura única de la cámara,
        sobrescribiendo cualquier fotograma anterior no consumido.

        Retorna
        -------
        int
            El número de secuencia ``frame_sequence`` asignado al fotograma.
        """
        if frame is None:
            raise ValueError("No se puede depositar un frame None en MobilePushFrameBuffer.")

        ts = captured_at or self._clock()
        if ts.tzinfo is None:
            raise ValueError("captured_at debe incluir zona horaria (UTC).")

        with self._lock:
            if not self._opened:
                raise RuntimeError(
                    f"MobilePushFrameBuffer para '{self._codigo_camara}' no está abierto. "
                    "Invoque open() antes de depositar fotogramas."
                )
            self._latest_sequence += 1
            self._latest_frame = frame
            self._latest_timestamp = ts
            return self._latest_sequence

    def read_frame(self) -> CaptureReadResult:
        """
        Consume el fotograma más reciente si está abierto, dentro del TTL y no
        ha sido procesado previamente.
        """
        with self._lock:
            now = self._clock()

            if not self._opened:
                return CaptureReadResult(
                    ok=False,
                    frame=None,
                    captured_at=now,
                    frame_sequence=None,
                    error_reason="MOBILE_BUFFER_NOT_OPEN",
                )

            if self._latest_frame is None or self._latest_timestamp is None:
                return CaptureReadResult(
                    ok=False,
                    frame=None,
                    captured_at=now,
                    frame_sequence=None,
                    error_reason="MOBILE_BUFFER_EMPTY",
                )

            age_seconds = (now - self._latest_timestamp).total_seconds()
            if age_seconds > self._ttl_seconds:
                # Limpiar referencia al fotograma expirado para liberar memoria
                expired_seq = self._latest_sequence
                self._latest_frame = None
                return CaptureReadResult(
                    ok=False,
                    frame=None,
                    captured_at=now,
                    frame_sequence=expired_seq,
                    error_reason=(
                        f"MOBILE_FRAME_EXPIRED_TTL: age={age_seconds:.3f}s > ttl={self._ttl_seconds:.3f}s"
                    ),
                )

            if self._latest_sequence == self._last_consumed_sequence:
                return CaptureReadResult(
                    ok=False,
                    frame=None,
                    captured_at=now,
                    frame_sequence=self._latest_sequence,
                    error_reason="NO_NEW_FRAME_SEQUENCE",
                    is_already_processed=True,
                )

            self._last_consumed_sequence = self._latest_sequence
            return CaptureReadResult(
                ok=True,
                frame=self._latest_frame,
                captured_at=self._latest_timestamp,
                frame_sequence=self._latest_sequence,
                error_reason=None,
                is_already_processed=False,
            )

    def release(self) -> None:
        """Deshabilita el buffer y limpia la referencia al fotograma en memoria."""
        with self._lock:
            self._opened = False
            self._latest_frame = None
            self._latest_timestamp = None
