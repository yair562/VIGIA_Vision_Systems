from vision.camera import capture_pc
from vision.pipeline import VisionPipeline
from traffic.analyzer import TrafficAnalyzer


_pipeline = VisionPipeline()


def process_pc_capture():
    frame = capture_pc()

    if frame is None:
        vision = {
            "status": "TECHNICAL_ERROR",
            "vehicle_detected": False,
            "vehicle_count": 0,
            "vehicles": [],
            "error": "Camera frame could not be captured.",
        }
        cantidad = 0
    else:
        vision_result = _pipeline.process(frame)
        vision = vision_result.to_dict()
        cantidad = vision_result.vehicle_count

    result = TrafficAnalyzer().analizar(cantidad)
    result["vision"] = vision
    return result