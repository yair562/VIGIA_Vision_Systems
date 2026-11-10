import sys
from pathlib import Path
from uuid import uuid4

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from VIGIA_API.ingest_service import build_vision_engine_coordinator
from VIGIA_Vision.config.topology_validator import CameraConfigDTO
from VIGIA_Vision.capture.registry import BoundCameraSlot
from VIGIA_Vision.capture.sources import MobilePushFrameBuffer

coord = build_vision_engine_coordinator(open_sources=True)
registry = coord.registry
print("Existing slots:", registry.registered_camera_codes)

# Create slot for CAM-03
slot_ent = registry.get_slot("CAM-ENTRADA")
cam3 = CameraConfigDTO(
    id_camara=uuid4(),
    codigo="CAM-03",
    nombre="Camara 3 Auxiliar",
    uri_stream="push://cam-03",
    activa=True
)
slot3 = BoundCameraSlot(
    camera=cam3,
    area=slot_ent.area,
    source=MobilePushFrameBuffer("CAM-03", ttl_seconds=3.0)
)
slot3.source.open()

# We can add slot3 directly to registry._slots
registry._slots["CAM-03"] = slot3
print("Updated slots:", registry.registered_camera_codes)

# Push frame to CAM-03
import cv2
import ultralytics
assets_dir = Path(ultralytics.__file__).parent / "assets"
bus_img = cv2.imread(str(assets_dir / "bus.jpg"))

slot3.source.push_frame(bus_img)
env = coord.process_camera_step("CAM-03", persist_as_new_event=True)
print("Processed CAM-03 successfully!")
print("  Status:", env.vision_result.status)
print("  Vehicle detected:", env.vision_result.vehicle_detected)
print("  Persisted ID:", env.id_deteccion)
print("  Evidence:", env.original_evidence_path)

coord.shutdown()
