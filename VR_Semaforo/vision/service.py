from vision.camera import capture_pc
from vision.processor import contar_carritos

def process_pc_capture():
    frame = capture_pc()

    if frame is None:
        return 0

    return contar_carritos(frame)