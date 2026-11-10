from pathlib import Path

path = Path(r"C:\GEST.PROY.TI\Software\VIGIA_Vision_Systems\VIGIA_API\ingest_service.py")
content = path.read_text(encoding="utf-8")

# 1. Update imports
target_import = "from VIGIA_Vision.capture.registry import UnregisteredCameraError"
repl_import = "from VIGIA_Vision.capture.registry import BoundCameraSlot, UnregisteredCameraError"

target_import2 = "from VIGIA_Vision.config.topology_validator import (\n    ITopologyConfigRepository,"
repl_import2 = "from VIGIA_Vision.config.topology_validator import (\n    CameraConfigDTO,\n    ITopologyConfigRepository,"

if target_import in content:
    content = content.replace(target_import, repl_import, 1)
else:
    raise AssertionError("target_import not found")

crlf2 = target_import2.replace("\n", "\r\n")
if crlf2 in content:
    content = content.replace(crlf2, repl_import2.replace("\n", "\r\n"), 1)
elif target_import2 in content:
    content = content.replace(target_import2, repl_import2, 1)
else:
    raise AssertionError("target_import2 not found")

# 2. Add auxiliary camera registration after coordinator.initialize
target_init = "    coordinator.initialize(open_sources=open_sources)\n    return coordinator"
crlf_init = target_init.replace("\n", "\r\n")

repl_init = """    coordinator.initialize(open_sources=open_sources)

    raw_extra_cams = get_setting("VIGIA_EXTRA_CAMERAS", "").strip()
    if raw_extra_cams and coordinator.registry is not None:
        extra_codes = [c.strip().upper() for c in raw_extra_cams.split(",") if c.strip()]
        topo = coordinator.topology
        if topo is not None:
            for idx, code in enumerate(extra_codes):
                target_area = topo.area_entrada if (idx % 2 == 0) else topo.area_salida
                aux_cam = CameraConfigDTO(
                    id_camara=uuid.uuid4(),
                    codigo=code,
                    nombre=f"Cámara Auxiliar {code}",
                    uri_stream=f"push://{code.lower()}",
                    activa=True,
                )
                aux_slot = BoundCameraSlot(
                    camera=aux_cam,
                    area=target_area,
                    source=MobilePushFrameBuffer(code, ttl_seconds=resolved_settings.mobile_frame_ttl_seconds),
                )
                if open_sources:
                    aux_slot.source.open()
                coordinator.registry.register_slot(aux_slot)
                logger.info("Cámara auxiliar multicámara registrada: '%s' -> área '%s'", code, target_area.codigo)

    return coordinator"""

if crlf_init in content:
    content = content.replace(crlf_init, repl_init.replace("\n", "\r\n"), 1)
elif target_init in content:
    content = content.replace(target_init, repl_init, 1)
else:
    raise AssertionError("target_init not found")

path.write_text(content, encoding="utf-8")
print("Successfully updated ingest_service.py for multi-camera support")
