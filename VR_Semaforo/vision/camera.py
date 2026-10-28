"""
VR_Semaforo.vision.camera
=========================
Módulo de captura de vídeo para VIGÍA Vision Systems (Fase 2B).

Refactorizado para eliminar la adquisición de hardware durante la importación.
Proporciona la clase CameraCapture con ciclo de vida explícito (open, read_frame, release)
y mantiene capture_pc() para compatibilidad hacia atrás sin activar hardware en importación.
"""

from typing import Optional, Tuple, Union

try:
    import cv2
except ImportError:
    cv2 = None


class CameraCapture:
    """
    Abstracción de captura de vídeo con ciclo de vida explícito.
    No adquiere hardware en __init__; la apertura se realiza explícitamente
    mediante open() o bajo demanda en read_frame().
    """

    def __init__(self, source: Union[int, str] = 0):
        self.source = source
        self._cap = None

    def open(self) -> bool:
        """Abre el descriptor de captura de forma explícita."""
        if cv2 is None:
            return False
        if self._cap is None or not self._cap.isOpened():
            self._cap = cv2.VideoCapture(self.source)
        return self._cap.isOpened() if self._cap is not None else False

    def is_opened(self) -> bool:
        """Indica si el descriptor de vídeo está actualmente abierto."""
        return self._cap is not None and self._cap.isOpened()

    def read_frame(self) -> Tuple[bool, Optional[object]]:
        """
        Lee el siguiente fotograma de la fuente de captura.
        Retorna:
          (True, frame) ante lectura exitosa.
          (False, None) si la cámara no está abierta o la lectura falla.
        """
        if cv2 is None:
            return False, None

        if not self.is_opened():
            if not self.open():
                return False, None

        ret, frame = self._cap.read()
        if not ret or frame is None:
            return False, None

        return True, frame

    def release(self) -> None:
        """Libera el descriptor de captura de forma segura."""
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            finally:
                self._cap = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


# Instancia por omisión y fábrica inyectable para pruebas
_default_camera: Optional[CameraCapture] = None


def get_default_camera() -> CameraCapture:
    """Obtiene o crea la instancia de captura por omisión (sin abrir hardware)."""
    global _default_camera
    if _default_camera is None:
        _default_camera = CameraCapture(0)
    return _default_camera


def set_default_camera(camera: Optional[CameraCapture]) -> None:
    """Permite inyectar un doble de prueba o sustituir la fuente de captura."""
    global _default_camera
    _default_camera = camera


def capture_pc() -> Optional[object]:
    """
    Función de compatibilidad con los consumidores existentes.
    No abre la cámara al importar el módulo. Solo lee al ser invocada.
    Retorna el fotograma (np.ndarray) o None si la lectura falla.
    """
    camera = get_default_camera()
    success, frame = camera.read_frame()
    return frame if success else None