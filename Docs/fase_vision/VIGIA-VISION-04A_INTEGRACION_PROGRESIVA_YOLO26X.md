# VIGIA-VISION-04A — Integración Progresiva de YOLO26x en la Arquitectura Operativa

**Proyecto:** VIGÍA Vision Systems  
**Fase:** `VISION-04A` (Integración progresiva + Rollback controlado)  
**Estrategia:** Opción A — Integración Progresiva  
**Modelo objetivo:** `yolo26x.pt` (`imgsz=640`, `quantize=16` FP16, `nms=False`, `augment=False`, `device=cuda:0`)  
**Modelo predeterminado / respaldo:** `yolo11n.pt`  
**Hardware:** NVIDIA GeForce RTX 4050 Laptop GPU (6141 MiB VRAM)  
**Fecha:** 2026-11-15 UTC

---

## 1. Resumen Ejecutivo

Se ejecutó la integración progresiva de **YOLO26x** dentro de la arquitectura operativa real de VIGÍA Vision Systems (`YoloVehicleDetector`, `VisionEngineCoordinator`, `build_vision_engine_coordinator` e `IngestService`), preservando `yolo11n.pt` como modelo predeterminado de producción, respaldo automático (`fallback`) y opción de rollback inmediato sin cambios de código.

La fase incorporó:
- Verificación en runtime de parámetros efectivos (`effective_fp16`, `effective_imgsz`, `end2end`) y liberación limpia de recursos (`unload()` / `close()` en `shutdown()`).
- Protección de contención GPU mediante espera acotada (`max_inference_wait_ms` -> `InferenceBackpressureError`) y registro explícito de frames descartados por saturación o TTL expirado (`STALE_FRAME_TTL`).
- Observabilidad operativa en tiempo real por detector, GPU y cámara (`get_runtime_status()`, `get_operational_metrics()` y campo sanitizado `vision_metrics` en `GET /api/v1/supervision/status`).
- Validación focalizada (`test_vision_04a_progressive_integration`: `4/4 OK`) y regresión completa post-cambio (`311/311 PASS` en las suites independientes de BD).

---

## 2. Auditoría de Arquitectura

La inspección previa del código en producción confirmó:
1. **Instancia única compartida:** `build_vision_engine_coordinator()` en `VIGIA_API/ingest_service.py` construye una única instancia de `YoloVehicleDetector` inyectada en `VisionEngineCoordinator`, compartida por `CAM-ENTRADA`, `CAM-SALIDA` y cualquier `VIGIA_EXTRA_CAMERAS`. No existen cargas duplicadas ni competencia entre múltiples copias del modelo en VRAM.
2. **Protección de hilo y canal:** `YoloVehicleDetector` serializa carga, fallback e inferencia mediante `threading.RLock`, mientras `IngestService` (`POST /push`) y `CameraPullWorker` (`VIGIA_API/usb_worker.py`) serializan por cámara mediante `get_camera_process_lock(codigo_camara)`.
3. **Brechas identificadas antes de `VISION-04A`:**
   - Ausencia de métricas de latencia (`mean`, `p50`, `p95`, `p99`), `inference_fps`, `queue_wait_ms`, errores CUDA, conteo de fallbacks y `last_recovery_ms` en `YoloVehicleDetector`.
   - Ausencia de espera acotada / backpressure explícito si la GPU se satura bajo múltiples canales.
   - Ausencia de métricas por cámara (`ingest_fps`, `processed_fps`, `dropped_frames`, `drop_reasons`) en `VisionEngineCoordinator` y en `/api/v1/supervision/status`.
   - `CameraTemporalStateTracker` (`VISION-02A.1`) permanece desacoplado en `VIGIA_Vision/runtime/temporal_state.py` pendiente de `VISION-02B`.

---

## 3. Componentes Afectados

| Archivo | Rol en `VISION-04A` | Tipo |
| :--- | :--- | :--- |
| `VIGIA_Vision/detection/yolo_detector.py` | Métricas de inferencia/GPU/resiliencia, verificación runtime FP16/imgsz, `InferenceBackpressureError` (`max_wait_ms`) y `unload()`/`close()` | Modificado |
| `VIGIA_Vision/runtime/coordinator.py` | Métricas por cámara (`ingest_fps`, `processed_fps`, `dropped_frames`), propagación `camera_code`/`max_wait_ms`, liberación de detector en `shutdown()` y `get_operational_metrics()` | Modificado |
| `VIGIA_API/ingest_service.py` | Exposición sanitizada de `vision_metrics` en `GET /api/v1/supervision/status` | Modificado |
| `tests/unit/test_vision_04a_progressive_integration.py` | Suite de pruebas de observabilidad, backpressure, TTL, fallback CUDA y pipeline E2E real con `YOLO26x` | Creado |
| `Docs/fase_vision/VIGIA-VISION-04A_INTEGRACION_PROGRESIVA_YOLO26X.md` (+ espejo) | Informe técnico de cierre `VISION-04A` | Creado |

---

## 4. Arquitectura de Integración

```text
[Cámara USB (CameraPullWorker)] ─┐
                                 ├─► get_camera_process_lock(cam) ─► VisionEngineCoordinator.process_camera_step()
[Cámara Móvil (POST /push)]     ─┘                                         │
                                                                           ▼
                                                        YoloVehicleDetector.detect(frame, camera_code, max_wait_ms)
                                                           ├─► RLock GPU (wait acotado -> InferenceBackpressureError)
                                                           ├─► YOLO26x (cuda:0, imgsz=640, FP16, nms=False)
                                                           └─► Fallback automático a yolo11n.pt ante fallo
                                                                           │
                                                                           ▼
                                                  ROI filter -> EvidenceStorage -> IDetectionRepository -> /api/v1/supervision/status
```

---

## 5. Cambios Implementados

1. **`VIGIA_Vision/detection/yolo_detector.py`:**
   - Añadida excepción `InferenceBackpressureError(InferenceError)` cuando la espera sobre `self._lock` supera `max_wait_ms`.
   - Añadida ventana acotada (`deque(maxlen=512)`) de latencias de inferencia y tiempos de espera en cola, junto a contadores de `total_inferences`, `inference_errors`, `cuda_errors`, `init_errors`, `fallback_count` y `last_recovery_ms`.
   - Verificación en runtime tras el primer `predict()` de `AutoBackend.fp16` (`effective_fp16`) y `predictor.args.imgsz` (`effective_imgsz`), manteniendo la verificación `end2end` (`NMS-Free`).
   - Implementados `unload()` y `close()` idempotentes con `torch.cuda.empty_cache()` seguro sin importar `torch` en frío.
2. **`VIGIA_Vision/runtime/coordinator.py`:**
   - Soporte opcional `max_inference_wait_ms` e inspección de firma del detector para compatibilidad 100% con dobles de prueba que implementan `detect(frame)`.
   - Contabilización thread-safe por cámara (`ingest_count`, `processed_count`, `ingest_fps`, `processed_fps`, `dropped_frames`, `drop_reasons`, `last_drop_policy`, `last_queue_wait_ms`, `last_step_ms`, `last_frame_at`, `last_status`).
   - Liberación de detector en `shutdown()`.
3. **`VIGIA_API/ingest_service.py`:**
   - `GET /api/v1/supervision/status` incluye `vision_metrics` eliminando explícitamente `weights_path` y `requested_weights_path` para no exponer rutas locales del servidor.

---

## 6. Configuración

La configuración centralizada vía `load_yolo_config_from_env()` se mantiene intacta y sin escribir `.env` de producción:
- **Predeterminado de producción (sin variables):** `model_path=yolo11n.pt`, `device=auto`, `imgsz=640`, `quantize=None`, `nms=None`, `augment=False`, `fallback_enabled=True`.
- **Perfil experimental activable para `YOLO26x`:**
  - `VIGIA_YOLO_MODEL=experiments/yolo26x/weights/yolo26x.pt`
  - `VIGIA_YOLO_DEVICE=cuda:0`
  - `VIGIA_YOLO_IMGSZ=640`
  - `VIGIA_YOLO_QUANTIZE=16`
  - `VIGIA_YOLO_NMS=false`
  - `VIGIA_YOLO_AUGMENT=false`
  - `VIGIA_YOLO_FALLBACK_ENABLED=true`

---

## 7. Gestión de Inferencia

- Carga perezosa controlada (`load_model()`), reutilizando una única instancia compartida entre cámaras y evitando recargas por frame.
- Verificación física de ruta de pesos (`resolve_yolo_weights_path`), integridad de arquitectura `one2one` pre-predict cuando `nms=False`, y confirmación post-predict de `end2end`, `fp16` e `imgsz`.
- Liberación explícita de modelo y caché CUDA mediante `coordinator.shutdown()` -> `detector.unload()`.

---

## 8. Concurrencia

- Protección de la GPU compartida mediante `threading.RLock` en `YoloVehicleDetector`, ahora instrumentado con medición de `queue_wait_ms` y timeout opcional `max_wait_ms`.
- Si una cámara sufre saturación en el lock GPU más allá de `max_inference_wait_ms`, `detect()` lanza `InferenceBackpressureError` sin bloquear indefinidamente la ingesta; el coordinador registra `dropped_frames += 1`, `drop_reasons["GPU_BACKPRESSURE_TIMEOUT"]`, `last_drop_policy="DROP_ON_GPU_BACKPRESSURE"` y devuelve `VisionStatus.VISION_ERROR`.
- Si un buffer móvil entrega un frame vencido por TTL, el coordinador registra `drop_reasons["STALE_FRAME_TTL"]` y `policy="DROP_ON_READ_ERROR"`.
- Las métricas distinguen `inference_fps` (rendimiento del motor) de `ingest_fps` y `processed_fps` individuales por cámara.

---

## 9. Postprocesamiento

De acuerdo con la inspección de `VisionEngineCoordinator.process_camera_step()` y los hallazgos de `VISION-03C.3` (`30` pares intra-frame con `IoU >= 0.50` en `YOLO26x` vs `8` en `YOLO11n`, y menor tasa de disparo en `UNDEREXPOSED` a `>=0.70`):
- `filter_detections_by_roi()` ordena las detecciones por confianza descendente y `primary = detections_in_roi[0]` determina la clase vehicular y el único `DetectionInsertDTO` por evento (protegido adicionalmente por debounce temporal en `IngestService` y `CameraPullWorker`).
- Por tanto, los duplicados intra-frame de `nms=False` **no generan filas duplicadas en BD ni evidencias repetidas ni alteran la clasificación primaria**; únicamente pueden incrementar el conteo `in_roi_now` / `total_detected_in_frame`.
- Siguiendo la regla de `VISION-04A` Fase D (no activar NMS arbitrariamente ni alterar thresholds/ROI/clasificación sin evidencia sobre vehículos reales con Ground Truth), se conserva el postprocesamiento actual y se documenta esta observación para su evaluación en la prueba física con `VIGIA-BENCH-REAL`.

---

## 10. Fallback

- **Inicialización:** si `yolo26x.pt` falla al cargar o no cumple `end2end=True` con `nms=False`, `_activate_fallback_locked(..., stage="model_init")` conmuta a `yolo11n.pt`, ejecuta sonda de validación y registra `init_errors`, `fallback_count` y `last_recovery_ms`.
- **Inferencia / CUDA / NaN-Inf:** ante excepción runtime, error CUDA (`cuda_errors`) o coordenadas no finitas, conmuta una única vez a `yolo11n.pt` (`_using_fallback=True` impide bucles infinitos o ping-pong entre modelos) y reintenta el fotograma actual.
- **Doble fallo terminal:** propaga `ModelLoadError` / `InferenceError` de manera controlada sin bloquear el worker.

---

## 11. Observabilidad

`YoloVehicleDetector.get_runtime_status()` y `VisionEngineCoordinator.get_operational_metrics()` (expuesto en `GET /api/v1/supervision/status` bajo `vision_metrics`) entregan:
- **Inferencia:** `requested_model`, `effective_model`, `device`, `effective_fp16`, `effective_imgsz`, `end2end`, `end2end_verified`, `total_inferences`, `inference_fps`, `latency_mean_ms`, `latency_p50_ms`, `latency_p95_ms`, `latency_p99_ms`, `inference_errors`.
- **Cámaras:** `ingest_count`, `processed_count`, `ingest_fps`, `processed_fps`, `dropped_frames`, `drop_reasons`, `last_drop_policy`, `last_queue_wait_ms`, `last_step_ms`, `last_frame_at`, `last_status`, `effective_model`.
- **GPU:** `vram_allocated_mb`, `vram_reserved_mb` (muestreados desde PyTorch CUDA solo cuando ya está cargado), `cuda_errors`.
- **Resiliencia:** `using_fallback`, `fallback_reason`, `fallback_timestamp`, `init_errors`, `fallback_count`, `last_recovery_ms`.

---

## 12. Integración del Pipeline

| Etapa | Estado verificado | Evidencia |
| :--- | :--- | :--- |
| Captura / Ingestión | `PASS` | `MobilePushFrameBuffer` + `POST /api/v1/cameras/CAM-ENTRADA/push` (`200`) |
| Validación + ROI | `PASS` | `validate_bgr_frame` + `project_normalized_roi` + `filter_detections_by_roi` |
| Inferencia `YOLO26x` | `PASS` | `yolo26x.pt` (`cuda:0`, `FP16`, `imgsz=640`, `end2end=True`) |
| Contrato + Clasificación | `PASS` | `RawVehicleDetection` -> `VisionResult` (`map_raw_label_to_domain_vehicle_type`) |
| FSM Temporal | `ISOLATED` | `CameraTemporalStateTracker` pendiente de `VISION-02B` (`temporal_fsm_integrated=False`) |
| Persistencia | `PASS` (in-memory) / `BLOCKED` (Postgres) | `_InMemoryDetRepo.persist_detection` verificado; Postgres `127.0.0.1:5434` offline |
| Evidencias | `PASS` | `LocalDiskEvidenceStorage` escribe `_orig.jpg` y `_annot.jpg` |
| API + Dashboard | `PASS` | `GET /api/v1/supervision/status` (`200`) con `vision_metrics` sanitizado |

---

## 13. Resultados de Pruebas

| Suite / Comando | Resultado | Detalle |
| :--- | :---: | :--- |
| `tests.unit.test_vision_04a_progressive_integration` | `4 / 4 PASS` (`3.657s`) | Observabilidad, runtime FP16/imgsz, `unload()`, fallback CUDA, backpressure GPU, TTL stale frame, E2E real `YOLO26x` + `/api/v1/supervision/status` |
| `tests.unit.test_vision_stage1_components` (aislada) | `16 / 16 PASS` (`0.218s`) | Importación limpia sin cargar `torch`/`ultralytics` preservada |
| `test_vision_04a` + `03c2` + `yolo_detector` + `02a_fsm` + `yolo26x_contract` + `pipeline` + `topology` + `async_persistence` + `detection_repo` + `domain_models` | `151 / 151 PASS` (`9.951s`) | Cero regresiones en motor de visión, fallback, FSM y repositorios |
| `test_camera` + `test_camera_stream_and_backend` + `test_usb_camera_integration` + `test_lan_detector` | `53 / 53 PASS` (`5.705s`) | Cero regresiones en cámaras USB, buffer móvil y red |
| `test_auth_rbac` + `test_auth_stream_protection` + `test_ipc_hardening` + `test_isolated_signer` + `test_network_discovery` + `test_signer_fail_closed` | `91 / 91 PASS` (`47.622s`) | Cero regresiones en RBAC, CSRF, IPC y signer |

---

## 14. Regresiones y Comparativa contra `VISION-03C.3`

- **Total post-cambio verificado en esta fase:** **`311 / 311 PASS`** (`0` fallos nuevos, `0` errores nuevos).
- **Elementos sin cambio respecto a `VISION-03C.3`:**
  - `BLOCKED` (`50` errores en `test_mobile_ingest_api` y `test_crl_management.test_15_flask_app_crl_endpoint_compatibility`): PostgreSQL offline en `127.0.0.1:5434`.
  - `FAIL` preexistente (`1` fallo en `test_trust_ca_logic.test_16_strict_check_reports_modalidad_a_and_b`): verificación TLS/CA ajena al motor YOLO.
  - `NOT RUN`: pruebas de integración contra PostgreSQL/HTTPS vivo y `tests/e2e/test_usb_e2e_physical.py` (pendiente de hardware físico y autorización del propietario).

---

## 15. Incidencias

- Ninguna incidencia nueva introducida por `VISION-04A`.
- Se mantienen las limitaciones conocidas: ausencia de Ground Truth humano para vehículos reales 1:1 (`VIGIA-BENCH-REAL`), caída de confianza en `SCALE_MODEL_LAB`/`UNDEREXPOSED` a `0.70`, `30` duplicados intra-frame con `nms=False`, PostgreSQL local detenido y `CameraTemporalStateTracker` pendiente de `VISION-02B`.

---

## 16. Rollback

El rollback hacia `yolo11n.pt` es **inmediato, determinista y sin cambios de código**:
1. Eliminar o vaciar `VIGIA_YOLO_MODEL`, `VIGIA_YOLO_QUANTIZE`, `VIGIA_YOLO_NMS`, `VIGIA_YOLO_AUGMENT` en el entorno de ejecución (o fijar `VIGIA_YOLO_MODEL=yolo11n.pt`).
2. Reiniciar el servicio de ingesta; `load_yolo_config_from_env()` restaurará automáticamente la línea base `yolo11n.pt`.
3. Ante fallo súbito de pesos o CUDA en runtime, el fallback automático conmuta sin intervención humana a `yolo11n.pt`.

---

## 17. Estado de Producción

- **Modelo predeterminado activo:** `yolo11n.pt` (protegido, sin promoción automática).
- **Archivos `.env`, certificados `certs/`, esquema PostgreSQL y pesos existentes:** intactos.
- **Nivel actual de despliegue:** **Nivel 1 completado** (integración controlada verificada); **Nivel 2** (validación de una cámara física) y **Nivel 3** (validación multicanal USB + móvil simultánea) listos y **pendientes de autorización del propietario**.

---

## 18. Protocolo de Validación Física (Siguiente Etapa — Nivel 2 y Nivel 3)

1. Iniciar Docker Desktop y PostgreSQL (`127.0.0.1:5434`) y ejecutar las `50` pruebas `BLOCKED` + suites de integración BD.
2. **Nivel 2 (1 cámara física):** enrolar `CAM-ENTRADA` (USB vía `/api/v1/devices/usb/enroll` o móvil vía `/api/v1/devices/pairing-qr`), activar perfil `YOLO26x` por entorno, capturar vehículos reales (`CAR`, `MOTORCYCLE`, `BUS`, `TRUCK`), monitorear `GET /api/v1/supervision/status` (`vision_metrics`), evidencias y persistencia PostgreSQL.
3. **Nivel 3 (multicanal simultáneo):** mantener `CAM-ENTRADA` USB + `CAM-SALIDA` móvil PUSH activas simultáneamente verificando `ingest_fps`, `processed_fps`, `dropped_frames`, `last_queue_wait_ms` y temperatura/VRAM GPU.
4. Construir `VIGIA-BENCH-REAL` con anotación humana obligatoria antes de decidir la promoción definitiva de `yolo26x.pt`.

---

## 19. Dictamen Técnico

> **APPROVED — READY FOR SINGLE CAMERA VALIDATION**

La integración progresiva de **YOLO26x** en la arquitectura operativa de VIGÍA Vision Systems cumple todos los criterios técnicos de aceptación del Nivel 1 (configuración centralizada reversible, instancia GPU única compartida, backpressure/observabilidad, fallback probado, pipeline operativo y `311/311` pruebas unitarias sin regresiones) y queda lista para autorización del propietario para iniciar la validación controlada con una primera cámara física (**Nivel 2**). No equivale a certificar precisión sobre vehículos reales ni autoriza aún la promoción definitiva como modelo predeterminado.
