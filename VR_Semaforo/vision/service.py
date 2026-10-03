from vision.camera import capture_pc
from vision.processor import contar_carritos
from traffic.analyzer import TrafficAnalyzer

def process_pc_capture():
    frame = capture_pc()

    if frame is None:
        cantidad = 0
    else:
        cantidad = contar_carritos(frame)

    return TrafficAnalyzer().analizar(cantidad)