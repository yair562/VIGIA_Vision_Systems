# VIGIA-VISION-04B — Preparación y Auditoría para Validación Física Controlada de YOLO26x (Etapa A)

**Proyecto:** VIGÍA Vision Systems  
**Fase:** `VISION-04B` — Etapa A (Inspección, auditoría y preparación sin apertura de cámaras)  
**Modelo experimental objetivo:** `experiments/yolo26x/weights/yolo26x.pt`  
**Modelo predeterminado / respaldo:** `yolo11n.pt`  
**Hardware:** NVIDIA GeForce RTX 4050 Laptop GPU (6141 MiB VRAM)  
**Fecha:** 2026-11-16 UTC

---

## 1. Dictamen de Preparación (Etapa A)

> **READY WITH OBSERVATIONS — AWAITING OWNER AUTHORIZATION**

**Motivo de las observaciones antes de iniciar Etapa B:**
1. PostgreSQL (`127.0.0.1:5434`), CUDA/FP16, los pesos `yolo26x.pt`, el rollback a `yolo11n.pt`, el apagado ordenado (`shutdown`/`close`) y el aislamiento `InferenceBackpressureError` vs `fallback` están verificados y operativos (`278 / 278` pruebas unitarias `PASS` tras las correcciones de esta etapa).
2. En el inventario físico sin apertura de DirectShow, la cámara **`Logitech BRIO`** figura con estado **`Unknown`** (desconectada), mientras que únicamente la webcam integrada **`USB2.0 HD UVC WebCam`** figura **`OK`**; además, en PostgreSQL **`CAM-SALIDA`** está enrolada como `usb://0` y **`CAM-ENTRADA`** como `push://cam-entrada`. Antes de iniciar la Etapa B, el propietario debe confirmar qué cámara física se utilizará (conectar `Logitech BRIO` / usar `USB2.0 HD UVC WebCam` en `CAM-SALIDA` o enrolar móvil en `CAM-ENTRADA`).

*(No se abrió ninguna cámara USB ni DirectShow, no se inició captura móvil PUSH, no se activó `YOLO26x` en el servicio operativo y no se modificó `.env`).*

---

## 2. Estado de PostgreSQL (Solo Lectura)

- **Docker Desktop & Contenedor:** `vigia-db` (`postgres:16-alpine`, ID `14b2a0013cb2`) en estado `Up (healthy)`, exponiendo `127.0.0.1:5434->5432/tcp` (PID `8084` escuchando).
- **Conectividad verificada:** `PostgreSQL 16.15`, base de datos `vigia_db`, usuario `vigia_admin`.
- **Tablas existentes (`18`):** `accion_iluminacion`, `administrativo`, `alerta`, `alumno`, `area_vision`, `camara`, `camara_credencial`, `camera_pairing_request`, `carrera`, `deteccion`, `evento_acceso`, `evento_sensor`, `persona`, `persona_vehiculo`, `schema_version`, `sensor`, `usuario`, `vehiculo`.
- **Migraciones (`schema_version`):** `V000` (`V000__init_database.sql`) hasta `V004` (`V004__enrolamiento_camaras_qr.sql`) aplicadas.
- **Datos actuales relevantes:**
  - `camara`: `('CAM-ENTRADA', 'Cámara Carril Entrada', 'push://cam-entrada', True)`, `('CAM-SALIDA', 'Cámara Carril Salida', 'usb://0', True)`.
  - `area_vision`: `('ROI-ENT', 'ENTRADA', 0.100, 0.200, 0.900, 0.800, True)`, `('ROI-SAL', 'SALIDA', 0.100, 0.200, 0.900, 0.800, True)`.
  - `deteccion`: `650` registros históricos.
  - `usuario` activos: `3` `ADMINISTRADOR`, `3` `OPERADOR`.
  - `camara_credencial`: `69` totales, `2` activas (`revocado_en IS NULL`).

---

## 3. Resultado de las Pruebas Previamente Bloqueadas por PostgreSQL

| Suite | Resultado | Detalle |
| :--- | :---: | :--- |
| `tests.unit.test_mobile_ingest_api` (`49` tests) + `tests.unit.test_crl_management` (`15` tests) | **`PASS`** (`64 / 64`, `10.166s`) | Las `50` pruebas previamente `BLOCKED` por PostgreSQL offline pasaron íntegramente |
| `tests.integration.test_phase3a_postgres_integration` | **`PASS`** | Validación real de esquema, repositorios y persistencia PostgreSQL |
| `tests.integration.test_seed_data_integration` | **`FAIL`** (preexistente datos dev) | `test_synthetic_users_exist_and_verify`: espera `2` usuarios sintéticos pero la BD dev actual contiene `6` usuarios activos (`3` `ADMINISTRADOR`, `3` `OPERADOR`) |

---

## 4. Auditoría de Shutdown y Concurrencia

Se inspeccionaron `YoloVehicleDetector.unload()`/`.close()`, `VisionEngineCoordinator.shutdown()`, `IngestService` (`_cleanup_usb_workers_on_exit` y `finally:`), `CameraPullWorker.stop()` y `CameraPullWorkerManager.stop_all()`:

| Criterio auditado | Estado inicial | Corrección aplicada en `VISION-04B` Etapa A |
| :--- | :--- | :--- |
| 1. No liberar modelo durante inferencia | `PASS` (`self._lock` serializa `detect` y `unload`) | Preservado |
| 2. No ejecutar `torch.cuda.empty_cache()` con hilo activo | `PASS` (protegido bajo `self._lock`) | Preservado |
| 3. Coordinación ordenada de workers al cerrar | Parcial (`_cleanup_usb_workers_on_exit` detenía workers sin llamar `coord.shutdown()`, y `stop_all` no aislaba excepciones por cámara) | `_cleanup_usb_workers_on_exit` ahora detiene `usb_worker_manager.stop_all(...)` y luego invoca `coord.shutdown()`; `stop_all()` aísla excepciones por cámara |
| 4. No permitir nuevas inferencias tras `close()` | **Brecha detectada:** `close()` solo llamaba a `unload()`, permitiendo recarga silenciosa en un `detect()` posterior | Añadido `self._closed = True` en `YoloVehicleDetector.close()` bajo `self._lock`; `load_model()` y `detect()` rechazan llamadas posteriores con `ModelLoadError`/`InferenceError` |
| 5. Cierre idempotente | `PASS` | Preservado y cubierto por test |
| 6. Excepción en shutdown no deja recursos activos | **Brecha detectada:** en `VisionEngineCoordinator.shutdown()`, una excepción en `release_all()` evitaba `detector.unload()` | Envuelto en `try...except...finally` garantizando `self._initialized = False` y `detector.unload()` |

---

## 5. Auditoría de Backpressure y Fallback

- Verificado en `YoloVehicleDetector.detect()`: cuando `self._lock.acquire(timeout=max_wait_ms/1000.0)` vence, lanza `InferenceBackpressureError` **antes** del bloque `try/except` de inferencia, por lo que **nunca activa el fallback a `yolo11n.pt`**.
- Verificado en `VisionEngineCoordinator.process_camera_step()`: captura `InferenceBackpressureError`, incrementa `dropped_frames`, registra `drop_reasons["GPU_BACKPRESSURE_TIMEOUT"]`, fija `last_drop_policy="DROP_ON_GPU_BACKPRESSURE"` y devuelve `VisionStatus.VISION_ERROR` sin bloquear el flujo ni degradar el modelo.
- Comprobado con nueva prueba `test_backpressure_never_activates_fallback_and_recovers_next_frame`: tras el descarte por contención GPU, `using_fallback` permanece `False`, `effective_model` sigue siendo `yolo26x.pt` y el frame inmediato siguiente se infiere normalmente con `yolo26x.pt`.

---

## 6. Inventario de Cámaras (Sin Abrir Dispositivos DirectShow)

- **Dispositivos PnP Windows (`Get-PnpDevice -Class Camera,Image`):**
  1. `USB2.0 HD UVC WebCam` (`USB\VID_13D3&PID_5458&MI_00\7&139903B1&0&0000`) — `Class=Camera`, **`Status=OK`** (cámara integrada).
  2. `Logitech BRIO` (`USB\VID_046D&PID_085E&MI_00\9&A507214&0&0000`) — `Class=Image`, **`Status=Unknown`** (desconectada actualmente).
- **Procesos Python activos / conflictos:** `0` procesos `python.exe` en ejecución; puertos `5000` y `8443` libres (sin contención ni captura abierta).
- **Enrolamiento actual en PostgreSQL:**
  - `CAM-SALIDA`: `usb://0` (`activa=True`).
  - `CAM-ENTRADA`: `push://cam-entrada` (`activa=True`).
- **Nota técnica:** las resoluciones/FPS reales negociadas por DirectShow/MSMF (`640x480`, `1280x720`, etc.) se consultarán únicamente tras autorización en Etapa B para respetar la prohibición de abrir dispositivos en Etapa A.

---

## 7. Estado de CUDA, GPU y Validación del Perfil Experimental

- **GPU:** `NVIDIA GeForce RTX 4050 Laptop GPU`, Driver `566.36`, `49 °C`, `982 / 6141 MiB` usados en `nvidia-smi` (`5075.0 MiB` libres / `6140.5 MiB` totales reportados por PyTorch CUDA), soporte `torch.float16` en `cuda:0` verificado.
- **Pesos verificados:**
  - Experimental `experiments/yolo26x/weights/yolo26x.pt`: `118,667,365` bytes, SHA-256 `9fdd44a31c504547ffb81d2c6d9e6dac3493c8eaa8b0398d3f43bae6c7003e92`.
  - Predeterminado / Rollback `yolo11n.pt`: `5,613,764` bytes, SHA-256 `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`.
- **Resolución de configuración (`load_yolo_config_from_env()` en subproceso aislado sin tocar `.env`):**
  - Base actual: `yolo11n.pt`, `device=cuda:0`, `imgsz=640`, `quantize=None`, `nms=None`.
  - Perfil experimental: `yolo26x.pt`, `device=cuda:0`, `imgsz=640`, `quantize=16`, `nms=False`, `augment=False`, `fallback_enabled=True`.

---

## 8. Correcciones Realizadas y Archivos Modificados

| Archivo | Cambio realizado |
| :--- | :--- |
| `VIGIA_Vision/detection/yolo_detector.py` | Añadido flag `_closed` en `close()` para impedir inferencias/cargas posteriores al cierre |
| `VIGIA_Vision/runtime/coordinator.py` | Endurecido `shutdown()` con `try...except...finally` garantizando limpieza aunque `release_all()` falle |
| `VIGIA_API/usb_worker.py` | Aislamiento de excepciones por cámara en `CameraPullWorkerManager.stop_all()` |
| `VIGIA_API/ingest_service.py` | `_cleanup_usb_workers_on_exit()` invoca `coord.shutdown()` tras detener los workers USB |
| `tests/unit/test_vision_04a_progressive_integration.py` | Añadidas `test_backpressure_never_activates_fallback_and_recovers_next_frame` y `test_shutdown_idempotence_close_blocks_new_inferences_and_exception_resilience` |
| `Docs/fase_vision/VIGIA-VISION-04B_PREPARACION_VALIDACION_FISICA.md` (+ espejo) | Presente informe de preparación `VISION-04B` Etapa A |

---

## 9. Resumen de Pruebas Ejecutadas y Clasificación

| Clasificación | Suites / Alcance | Resultado |
| :---: | :--- | :--- |
| **`PASS`** | `tests.unit.test_vision_stage1_components` (aislada) | `16 / 16` (`0.339s`) |
| **`PASS`** | `test_vision_04a_progressive_integration` (`6/6`) + `03c2` + `yolo_detector` + `02a_fsm` + `yolo26x_contract` + `pipeline` + `topology` + `async_persistence` + `detection_repo` + `domain_models` | `153 / 153` (`13.824s`) |
| **`PASS`** | `test_camera` + `test_camera_stream_and_backend` + `test_lan_detector` + `test_usb_camera_integration` (`TestUsbFlaskEndpoints`, `TestUsbUriNormalizationAndProvision`) | `45 / 45` (`1.244s`) |
| **`PASS`** | `test_mobile_ingest_api` (`49`) + `test_crl_management` (`15`) contra PostgreSQL real | `64 / 64` (`10.166s`) |
| **`PASS`** | `tests.integration.test_phase3a_postgres_integration` | `OK` |
| **`FAIL`** | `tests.integration.test_seed_data_integration.test_synthetic_users_exist_and_verify` | Preexistente por datos dev (`6` usuarios activos en BD vs `2` esperados) |
| **`NOT RUN`** | `TestRealPhysicalUsbWebcam` (`test_usb_camera_integration`), `tests/e2e/test_usb_e2e_physical.py`, `test_phase3b_dashboard_integration.py`, `test_vision_engine_operational_integration.py`, `test_mobile_qr_enrollment_integration.py`, `test_tls_mobile_enrollment_integration.py` | Omitidas deliberadamente en Etapa A para no abrir DirectShow ni iniciar servicios sin autorización |

---

## 10. Riesgos Detectados

1. **`Logitech BRIO` desconectada (`Status=Unknown`):** si la prueba física de Etapa B pretende usar la Logitech BRIO, debe conectarse físicamente antes de autorizar; de lo contrario, el único índice USB disponible es la webcam integrada (`USB2.0 HD UVC WebCam`).
2. **Mapeo de cámara única:** actualmente `CAM-SALIDA` apunta a `usb://0` y `CAM-ENTRADA` a `push://cam-entrada`. Debe confirmarse en qué carril/transporte se ejecutará la validación de cámara única.
3. **Ausencia de Ground Truth humano:** las detecciones de Etapa B deberán revisarse/anotarse manualmente para `VIGIA-BENCH-REAL` antes de declarar métricas de precisión certificadas.

---

## 11. Comandos Exactos para Etapa B (Solo tras Autorización)

### Activación controlada con perfil experimental `YOLO26x` (en sesión efímera, sin modificar `.env`)
```powershell
Set-Location C:\GEST.PROY.TI\Software\VIGIA_Vision_Systems
$env:VIGIA_YOLO_MODEL = "experiments/yolo26x/weights/yolo26x.pt"
$env:VIGIA_YOLO_DEVICE = "cuda:0"
$env:VIGIA_YOLO_IMGSZ = "640"
$env:VIGIA_YOLO_QUANTIZE = "16"
$env:VIGIA_YOLO_NMS = "false"
$env:VIGIA_YOLO_AUGMENT = "false"
$env:VIGIA_YOLO_FALLBACK_ENABLED = "true"
.\.venv_cuda\Scripts\python.exe -m VIGIA_API.ingest_service
```

### Verificación operativa y observabilidad durante Etapa B
```powershell
# Consultar métricas de inferencia, cámara única, VRAM y fallback
# GET /api/v1/supervision/status (con sesión autenticada)
nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total --format=csv,noheader
```

### Rollback inmediato a línea base `YOLO11n`
```powershell
Remove-Item Env:VIGIA_YOLO_MODEL, Env:VIGIA_YOLO_DEVICE, Env:VIGIA_YOLO_IMGSZ, Env:VIGIA_YOLO_QUANTIZE, Env:VIGIA_YOLO_NMS, Env:VIGIA_YOLO_AUGMENT, Env:VIGIA_YOLO_FALLBACK_ENABLED -ErrorAction SilentlyContinue
.\.venv_cuda\Scripts\python.exe -m VIGIA_API.ingest_service
```

---

**En espera de su autorización explícita y confirmación de la cámara física a utilizar para iniciar la Etapa B.**
