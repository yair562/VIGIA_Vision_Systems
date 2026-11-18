# VIGIA-VISION-06 — Promoción de YOLO26x a Producción

**Proyecto:** VIGÍA Vision Systems  
**Área:** Computer Vision / MLOps / Producción en Tiempo Real  
**Fecha de Ejecución:** 2026-11-16 (UTC: 2026-11-17T00:44:29Z)  
**Hardware Productivo:** NVIDIA GeForce RTX 4050 Laptop GPU (6,140.5 MiB VRAM), CUDA 12.4, Driver 566.36  
**Entorno de Ejecución:** `.venv_cuda` — Python 3.11.1, PyTorch 2.6.0+cu124, TorchVision 0.21.0+cu124, Ultralytics 8.4.171  
**Checkpoint Activo en Producción:** [yolo26x.pt](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/weights/yolo26x.pt)  
**Checkpoint de Respaldo / Rollback:** [yolo11n.pt](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/yolo11n.pt)  
**Veredicto Oficial:** `APPROVED — YOLO26x ACTIVE IN PRODUCTION`

---

## 1. AUDITORÍA INICIAL Y CONTEXTO DEL SISTEMA

Previo a la promoción a producción (FASE 1):
1. **Estado del Repositorio:** La rama de trabajo en [VIGIA_Vision_Systems](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems) contenía cambios locales de fases previas aprobadas (`VIGIA_API/ingest_service.py`, `VIGIA_Vision/detection/yolo_detector.py`, `VIGIA_Vision/runtime/coordinator.py`, `VIGIA_Dashboard/`, `certs/`), los cuales fueron respetados sin sobrescritura.
2. **Servicios Operativos Detectados:**
   - **Signer Criptográfico Aislado:** [start_signer.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/start_signer.py) (`task-5087`, Named Pipe `\\.\pipe\vigia_ca_signer`). Permaneció activo ininterrumpidamente durante toda la fase.
   - **Servicio de Ingesta VIGÍA:** `VIGIA_API.ingest_service` (`task-5089`, iniciado a las `11:01:39` CST en puertos `5001` HTTPS y `5080` CRL). Al momento de la auditoría operaba con línea base `yolo11n.pt` (133,011 inferencias acumuladas, `effective_fp16=false`, `end2end=false`, `vram_allocated_mb=84.32 MiB`).
   - **Base de Datos PostgreSQL:** Contenedor Docker `vigia-db` saludable en `127.0.0.1:5434` con 1,461 registros iniciales en `deteccion`.
3. **Topología Activa de Cámaras en PostgreSQL:**
   - `CAM-ENTRADA` (`2296f49a-edac-4b39-87cb-0f9b1499b82b`): `usb://0` -> área `ROI-ENT` (`ENTRADA`), worker pull USB activo a 15.0 FPS.
   - `CAM-SALIDA` (`53a9c846-3bac-464c-a1bd-017690c961c0`): `push://cam-salida` -> área `ROI-SAL` (`SALIDA`), enrolada para captura móvil.
   - Cámaras auxiliares Push (`VIGIA_EXTRA_CAMERAS=CAM-03,CAM-04`): `CAM-03` (`ROI-ENT`) y `CAM-04` (`ROI-SAL`).
4. **Verificación Documental VISION-05C:** Se verificó coincidencia exacta SHA-256 (`31528E7BAA3C8ADEFAA8FDD62264C491E944E17DF0B95F59993D391D02F32D91`) entre el informe primario y espejo de [VIGIA-VISION-05C_ACTIVACION_CONTROLADA_YOLO26X.md](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_vision/VIGIA-VISION-05C_ACTIVACION_CONTROLADA_YOLO26X.md).

---

## 2. CONFIGURACIÓN ANTERIOR Y NUEVA (SOFTWARE/.ENV)

La configuración operativa global se gestiona de forma centralizada mediante [Software/.env](file:///C:/GEST.PROY.TI/Software/.env) a través de `VIGIA_Core.config.env_loader` y `load_yolo_config_from_env()` en [yolo_detector.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py). No se introdujeron variables desconocidas por el código ni configuraciones duplicadas.

| Parámetro / Variable | Configuración Anterior (`yolo11n.pt`) | Nueva Configuración Producción (`yolo26x.pt`) | Origen / Observación |
| :--- | :--- | :--- | :--- |
| `VIGIA_YOLO_MODEL` | *(no definida $\to$ default `yolo11n.pt`)* | `experiments/yolo26x/weights/yolo26x.pt` | Checkpoint YOLO26x verificado |
| `VIGIA_INFERENCE_DEVICE` | `auto` | `auto` | Base global conservada |
| `VIGIA_YOLO_DEVICE` | *(no definida $\to$ herencia `auto`)* | `cuda:0` | GPU CUDA explícita |
| `VIGIA_YOLO_IMGSZ` | *(default `640`)* | `640` | Resolución primaria preservada |
| `VIGIA_YOLO_QUANTIZE` | *(default `None` / FP32)* | `16` | FP16 nativo en Tensor Cores RTX 4050 |
| `VIGIA_YOLO_NMS` | *(default `None` / NMS clásico)* | `false` | NMS-Free end2end verificado |
| `VIGIA_YOLO_FALLBACK_ENABLED` | *(default `True`)* | `true` | Resiliencia atómica habilitada |
| `VIGIA_YOLO_FALLBACK_MODEL` | *(default `yolo11n.pt`)* | `yolo11n.pt` | Modelo de respaldo operativo |
| `VIGIA_YOLO_DEDUP_IOU` | *(default `0.55`)* | `0.55` | Deduplicación intra-frame EXP-10 |
| `VIGIA_YOLO_CONSOLIDATE_CONFIDENCE` | *(default `True`)* | `true` | Consolidación inter-clase EXP-10 |
| `VIGIA_YOLO_FRONTAL_AUX_ENABLED` | *(default `True`)* | `true` | Sonda multiescala condicional EXP-10 |
| `VIGIA_YOLO_FRONTAL_AUX_IMGSZ` | *(default `384`)* | `384` | Resolución sonda auxiliar |
| `VIGIA_YOLO_FRONTAL_AUX_TRIGGER_CONF` | *(default `0.70`)* | `0.70` | Umbral disparo de sonda auxiliar |
| `VIGIA_VEHICLE_CONFIDENCE_THRESHOLD` | `0.70` | `0.70` | Sin cambios |
| `VIGIA_MOBILE_FRAME_TTL_SECONDS` | `3.0` | `3.0` | Sin cambios |
| Secretos (`POSTGRES_PASSWORD`, `VIGIA_CAMERA_KEY`) | `[REDACTED]` | `[REDACTED]` | Intactos (sin alteración) |

- **Respaldo de Configuración Anterior (.env.yolo11n.bak):** SHA-256 `DF9AAECDF56935E837E8E9273313D925BBB984336191B88C7B5103C0096004C8`
- **Perfil Activo de Producción (.env / .env.yolo26x.prod):** SHA-256 `144055B9C5257B07798C68C2793A91DC7235915FE3AC5155178202E507A05C96`

---

## 3. ARCHIVOS MODIFICADOS Y CREADOS EN ESTA FASE

1. **Modificado (Configuración Global):** `C:\GEST.PROY.TI\Software\.env` — Promoción de variables `VIGIA_YOLO_*` hacia `yolo26x.pt` en `cuda:0` con FP16, NMS-Free y EXP-10.
2. **Creado (Respaldo Rollback y Perfil):** `C:\GEST.PROY.TI\Software\.env.yolo11n.bak` y `C:\GEST.PROY.TI\Software\.env.yolo26x.prod`.
3. **Modificado (Telemetría de Inferencia y Seguridad OOM):** [yolo_detector.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py)
   - Atribución explícita por inferencia (`last_inference_model` y `inferences_by_model`) bajo bloqueo atómico `RLock` para no atribuir inferencias de fallback `yolo11n.pt` a `yolo26x.pt`.
   - Liberación preventiva de referencia de modelo primario, `gc.collect()` y `torch.cuda.empty_cache()` dentro de `_activate_fallback_locked()` previo a instanciar `yolo11n.pt` ante errores CUDA / OOM.
   - Actualización de `effective_fp16`, `end2end` y `effective_imgsz` mediante `_verify_nms_free_post_predict()` al conmutar hacia fallback.
   - Guarda defensiva FP16 cuando `device == "cpu"` sin mock inyectado ("FP16 si está soportada").
4. **Modificado (Telemetría por Cámara):** [coordinator.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/runtime/coordinator.py)
   - Registro de `last_inference_model` exacto en cada paso de `_record_camera_processed()` y exposición en `get_operational_metrics()["cameras"]`.
5. **Creado (Pruebas Unitarias VISION-06):** [test_vision_06_production_promotion.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/tests/unit/test_vision_06_production_promotion.py).
6. **Creado (Benchmark de Capacidad Multicámara FASE 4):** [validate_vision_06_capacity.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/scripts/validate_vision_06_capacity.py) y salida [vision_06_capacity_results.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/results/vision_06_capacity_results.json).
7. **Creado (Informe Primario y Espejo):** [VIGIA-VISION-06_PROMOCION_YOLO26X_PRODUCCION.md](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_vision/VIGIA-VISION-06_PROMOCION_YOLO26X_PRODUCCION.md) y su espejo en `C:\GEST.PROY.TI\Software\Docs\fase_vision\VIGIA-VISION-06_PROMOCION_YOLO26X_PRODUCCION.md`.

---

## 4. CHECKPOINTS Y VERIFICACIÓN CRIPTOGRÁFICA (SHA-256)

| Modelo | Ruta Resuelta en Disco | Tamaño (Bytes) | Hash SHA-256 | Rol Operativo |
| :--- | :--- | :---: | :--- | :--- |
| **YOLO26x** | `C:\GEST.PROY.TI\Software\VIGIA_Vision_Systems\experiments\yolo26x\weights\yolo26x.pt` | 118,667,365 | `9fdd44a31c504547ffb81d2c6d9e6dac3493c8eaa8b0398d3f43bae6c7003e92` | Primario en Producción |
| **YOLO11n** | `C:\GEST.PROY.TI\Software\VIGIA_Vision_Systems\yolo11n.pt` | 5,613,764 | `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1` | Respaldo Automático & Rollback |

---

## 5. IDENTIDAD DEL MODELO EN RUNTIME, PRECISIÓN, EXP-10 Y NMS-FREE

Verificado directamente en los logs de arranque de la instancia productiva (`task-5412`) y mediante consulta autenticada a `GET https://127.0.0.1:5001/api/v1/supervision/status`:

- **Logs de Inicialización (`task-5412`):**
  ```
  2026-11-16 18:44:11,718 [INFO] VIGIA_Vision.detection.yolo_detector: Dispositivo CUDA explícito validado: NVIDIA GeForce RTX 4050 Laptop GPU en cuda:0 (6140 MB VRAM).
  2026-11-16 18:44:13,603 [INFO] VIGIA_Vision.detection.yolo_detector: Detector YOLO inicializado: modelo_solicitado='yolo26x.pt', modelo_efectivo='yolo26x.pt', weights_path='C:\GEST.PROY.TI\Software\VIGIA_Vision_Systems\experiments\yolo26x\weights\yolo26x.pt', device='cuda:0', imgsz=640, quantize=16, nms=False, fallback_enabled=True, ultralytics='8.4.171'.
  2026-11-16 18:44:14,312 [INFO] VIGIA_Vision.detection.yolo_detector: Estado AutoBackend verificado: modelo='yolo26x.pt', end2end=True, one2one_cv2=True, one2many_cv2_liberada=True.
  ```
- **Telemetría Runtime (`detector`):**
  - `requested_model`: `"yolo26x.pt"`
  - `effective_model`: `"yolo26x.pt"`
  - `last_inference_model`: `"yolo26x.pt"`
  - `inferences_by_model`: `{"yolo26x.pt": 216}`
  - `device`: `"cuda:0"`
  - `quantize`: `16` / `effective_fp16`: `true` (parámetros verificados en `torch.float16` sobre CUDA)
  - `nms`: `false` / `end2end`: `true` / `end2end_verified`: `true`
  - **EXP-10:** `deduplicate_iou_threshold: 0.55`, `consolidate_frontal_confidence: true`, `frontal_aux_enabled: true`, `frontal_aux_imgsz: 384`, `frontal_aux_trigger_confidence: 0.7`
- **Estado del Fallback en Producción:**
  - `fallback_enabled`: `true`, `using_fallback`: `false`, `fallback_count`: `0`, `fallback_reason`: `null`, `fallback_timestamp`: `null`.

---

## 6. POLÍTICA DE FALLBACK Y TELEMETRÍA VERIFICADA

El mecanismo de resiliencia atómica protegido bajo `threading.RLock()` garantiza consistencia ante accesos concurrentes multicámara y cubre los cinco modos de fallo exigidos:
1. **Fallos de inicialización (`model_init`):** Verificado con pesos inexistentes y corruptos (`yolo11n.pt` toma el control sin detener el servicio).
2. **Excepciones de inferencia (`runtime_inference`):** Conmutación transparente en caliente y reintento único del fotograma en curso.
3. **Errores CUDA y OOM:** Liberación explícita de referencia al modelo primario + `gc.collect()` + `torch.cuda.empty_cache()` antes de instanciar `yolo11n.pt`.
4. **Salidas numéricas no válidas (`NaN`/`Inf`):** Rechazo estricto en `_parse_prediction_results()` y conmutación automática a `yolo11n.pt`.
5. **Trazabilidad sin encubrimiento:** `effective_model`, `last_inference_model`, `inferences_by_model`, `using_fallback`, `fallback_reason`, `fallback_timestamp`, `inference_errors`, `cuda_errors`, `init_errors`, `fallback_count` y `last_recovery_ms` reportados en `GET /api/v1/supervision/status` y por cámara (`cameras[code].last_inference_model`).

---

## 7. CAPACIDAD OPERATIVA Y RESULTADOS DE INFERENCIA EN PRODUCCIÓN

### 7.1. Prueba Controlada de Capacidad y Concurrencia GPU (FASE 4 — 100 Inferencias Multicámara)
Ejecutado mediante [validate_vision_06_capacity.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/scripts/validate_vision_06_capacity.py) con carga simultánea en 2 hilos (`CAM-ENTRADA` + `CAM-SALIDA`, mezcla 50% vehículos reales / 50% cuadros vacíos que ejercitan la sonda auxiliar 384):
- **Inferencias Totales:** `100` (`yolo26x.pt: 100`, `0` errores, `0` frames descartados).
- **Throughput Agregado Concurrente:** **`24.66 FPS`** (`inference_fps`: **`24.75 FPS`**).
- **Latencias:** Media **`40.401 ms`**, **P50 `42.143 ms`**, **P95 `48.323 ms`**, **P99 `104.194 ms`**.
- **Espera Media por Lock GPU:** `queue_wait_mean_ms = 37.58 ms` (`CAM-ENTRADA` procesó `12.03 FPS`, `CAM-SALIDA` procesó `12.90 FPS`, sin inanición entre hilos).
- **Memoria GPU (VRAM):**
  - Total GPU: `6,140.5 MiB` (`4,401.0 MiB` libres en el sistema durante la carga simultánea de 2 hilos).
  - Asignada PyTorch pico: **`487.07 MiB`** | Reservada PyTorch pico: **`626.0 MiB`** (~10.2% de los 6 GB).
  - Estabilidad entre múltiples hilos efímeros secuenciales validada aparte: consumo fijo en `402.84 MiB` sin fugas.
- **Memoria de Proceso (RAM RSS):** `491.28 MiB` inicial $\to$ `1,324.99 MiB` tras 100 inferencias concurrentes.

### 7.2. Evidencia en el Servicio Productivo Activo (`task-5412`)
1. **Salud de Servicios:**
   - `GET https://127.0.0.1:5001/` $\to$ `200 OK` (`{"service": "VIGIA Vision Systems - Ingest API", "status": "ONLINE", "version": "VO-03B"}`).
   - `GET http://127.0.0.1:5080/api/v1/tls/ca.crl` $\to$ `200 OK` (`498 bytes`).
2. **Flujo Continuo en Cámara USB Real (`CAM-ENTRADA`, `usb://0`):**
   - `GET /api/v1/cameras/CAM-ENTRADA/status`: `operational_state: "TRANSMITIENDO"`, `status: "VEHICLE_DETECTED_NO_PLATE"`, `tipo_vehiculo: "AUTOMOVIL"`, `confianza: 0.7429`, `sequence: 213`.
   - `vision_metrics.cameras["CAM-ENTRADA"]`: `processed_count: 215`, `processed_fps: 14.36`, `dropped_frames: 0`, `last_inference_model: "yolo26x.pt"`.
   - `vision_metrics.detector`: `total_inferences: 216`, `inference_fps: 22.07`, `latency_mean_ms: 45.315`, **P50 `42.668 ms`**, **P95 `48.418 ms`**, **P99 `55.586 ms`**, `frontal_aux_triggers: 204`, `frontal_aux_recoveries: 27`, `duplicates_suppressed: 105`, `vram_allocated_mb: 402.84 MiB`, `vram_reserved_mb: 594.0 MiB`.
   - Telemetría externa `nvidia-smi`: `NVIDIA GeForce RTX 4050 Laptop GPU | 6141 MiB total | 1854 MiB used | 4068 MiB free | 37% GPU util`.
3. **Inferencia Real vía HTTPS Push (`POST /api/v1/cameras/CAM-03/push`):**
   - Prueba pre-rollback (`idempotency=vision06-prod-probe-001`): HTTP `200 OK`, `AUTOMOVIL`, `confianza=0.9744`, `id_deteccion=5c4780b9-e890-4539-96fb-c1c0e9a2a9ce`.
   - Prueba final post-promoción (`idempotency=vision06-prod-final-002`): HTTP `200 OK`, `AUTOMOVIL`, `confianza=0.9744`, `id_deteccion=65c5c88d-8df9-47ff-9f59-7607c058d7fb`, `original_evidence_path=20261117/CAM-03/20261117T004429_092162Z_2c189362dd4c_orig.jpg`, `annotated_evidence_path=20261117/CAM-03/20261117T004429_092162Z_2c189362dd4c_annot.jpg`.

---

## 8. REGISTRO DE REINICIOS CONTROLADOS Y INSTANCIA ÚNICA

Todos los reinicios se realizaron verificando previamente la liberación completa de sockets (`5001`, `5080`) y procesos hijo Python en Windows para impedir instancias duplicadas o contención sobre `usb://0`:

| Evento | Tarea / PID Launcher / PID Child | Modelo Activo | Estado Puertos & Cámaras |
| :--- | :--- | :--- | :--- |
| **Estado Inicial** | `task-5089` (PID `33916` / `37220`) | `yolo11n.pt` | Activo en `5001`/`5080` y `usb://0` |
| **Reinicio 1 (Promoción)** | `task-5089` detenido limpiamente $\to$ `task-5393` iniciado | `yolo26x.pt` | Sin colisión; probe HTTP `5c4780b9...` y USB verificados |
| **Reinicio 2 (Prueba Rollback)** | `task-5393` detenido $\to$ `task-5403` iniciado con `.env.yolo11n.bak` | `yolo11n.pt` | `yolo11n.pt` verificado en `5001` (`761c41e6...`, `confianza=0.817`) + 125 frames USB |
| **Reinicio 3 (Producción Final)** | `task-5403` detenido $\to$ **`task-5412` (PID `46712` / `19556`) activo** | **`yolo26x.pt`** | **Única instancia activa** junto con `task-5087` (`start_signer.py`) |

---

## 9. ESTADO DE POSTGRESQL, SEGURIDAD Y REGISTROS PERSISTENTES (FASE 6)

- **Esquemas, Credenciales y Certificados:** Sin modificaciones en DDL ni permisos de PostgreSQL. Los secretos `.env` y la Root CA permanecieron íntegros (el demonio `start_signer.py` renovó automáticamente el certificado hoja TLS para incluir la IP LAN vigente `192.168.1.105` preservando la Root CA).
- **Contenedor PostgreSQL:** `vigia-db` (`Up 8 hours (healthy)` en `127.0.0.1:5434`). Total de filas en `deteccion` al cierre: `1,516` (incluyendo capturas continuas de `CAM-ENTRADA` y las 3 sondas de validación documentadas).
- **Registros de Prueba Persistidos (Identificados y Conservados sin Eliminación):**
  1. `id_deteccion=5c4780b9-e890-4539-96fb-c1c0e9a2a9ce` | `AUTOMOVIL` | `confianza=0.974` | `20261117/CAM-03/20261117T004301_717232Z_e3d12d3f2a7a_orig.jpg` (`2026-11-17T00:43:01Z`, sonda promoción YOLO26x)
  2. `id_deteccion=761c41e6-4d72-47a7-a9db-00157dfade5a` | `AUTOMOVIL` | `confianza=0.817` | `20261117/CAM-03/20261117T004342_431629Z_cfd004b1cdf0_orig.jpg` (`2026-11-17T00:43:42Z`, sonda prueba rollback YOLO11n)
  3. `id_deteccion=65c5c88d-8df9-47ff-9f59-7607c058d7fb` | `AUTOMOVIL` | `confianza=0.974` | `20261117/CAM-03/20261117T004429_092162Z_2c189362dd4c_orig.jpg` (`2026-11-17T00:44:29Z`, sonda final producción YOLO26x)

---

## 10. PRUEBAS EJECUTADAS TRAS CAMBIOS FINALES

| Suite / Verificación | Alcance | Conteo | Resultado |
| :--- | :--- | :---: | :---: |
| **Suites Visión y Detección YOLO** | `test_vision_06_production_promotion`, `test_vision_05a`, `test_vision_04a`, `test_vision_03c2`, `test_yolo_detector`, `test_vision_05b`, `test_vision_02a`, `test_vision_pipeline` | 95 pruebas | **95 PASS / 0 FAIL (15.50 s)** |
| **Componentes Base Visión (Aislada)** | `test_vision_stage1_components` | 16 pruebas | **16 PASS / 0 FAIL (0.18 s)** |
| **Dominio Core, Repositorio e Ingesta API** | `test_domain_models`, `test_detection_repository`, `test_topology_validator`, `test_mobile_ingest_api` | 111 pruebas | **111 PASS / 0 FAIL (8.02 s)** |
| **Benchmark Capacidad Multicámara CUDA** | `validate_vision_06_capacity.py` (100 inferencias reales concurrentes) | 100 infs | **PASS (0 errores, 24.66 FPS)** |
| **Pruebas End-to-End Servicio Vivo** | Salud HTTP/CRL, Push HTTPS `CAM-03`, USB Live `CAM-ENTRADA` y Rollback vivo | 3 reinicios | **PASS (Exit Code 0)** |
| **TOTAL PRUEBAS UNITARIAS/INTEGRACIÓN** | **Todas ejecutadas después de promoción `.env` y ediciones finales** | **222 pruebas** | **222 PASS / 0 FAIL** |

---

## 11. PROCEDIMIENTO VERIFICADO DE ROLLBACK A YOLO11N (FASE 7)

El rollback **no requiere descargar pesos ni reconstruir `.venv_cuda`**. El procedimiento fue ejecutado y verificado en vivo en esta fase (`task-5403`):

1. **Detener ordenadamente** el proceso activo de `VIGIA_API.ingest_service` y verificar liberación de puertos `5001`/`5080`:
   ```powershell
   Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*VIGIA_API.ingest_service*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
   ```
2. **Restaurar el respaldo de configuración anterior** (modelo `yolo11n.pt`, `quantize=None`, `nms=None`, `VIGIA_INFERENCE_DEVICE=auto`):
   ```powershell
   Copy-Item -Path "C:\GEST.PROY.TI\Software\.env.yolo11n.bak" -Destination "C:\GEST.PROY.TI\Software\.env" -Force
   ```
3. **Reiniciar el servicio de ingesta**:
   ```powershell
   Set-Location C:\GEST.PROY.TI\Software\VIGIA_Vision_Systems
   .\.venv_cuda\Scripts\python.exe -m VIGIA_API.ingest_service
   ```
4. **Confirmar salud e inferencia** verificando `GET https://127.0.0.1:5001/` (`status: "ONLINE"`) y `GET https://127.0.0.1:5001/api/v1/supervision/status` (`effective_model: "yolo11n.pt"`, `using_fallback: false`).

*(Evidencia de verificación en vivo: `task-5403` confirmó `yolo11n.pt` en GPU CUDA con `vram_allocated_mb=84.32 MiB`, `confianza=0.817` en `CAM-03` (`id_deteccion=761c41e6...`) y 125 frames USB en `CAM-ENTRADA` antes de restaurar `.env.yolo26x.prod`).*

---

## 12. LIMITACIONES PENDIENTES

1. **Validación Física Multicámara con Vehículos Reales:** Aunque se validó operación real de `CAM-ENTRADA` (`usb://0`) y carga concurrente sintética/histórica entre `CAM-ENTRADA` y `CAM-SALIDA`/`CAM-03`, `CAM-SALIDA` (`push://cam-salida`) se encuentra en espera de transmisión móvil física simultánea en campo. No se declara precisión certificada al 100% sin evaluación de campo con *ground truth* vehicular anotado.
2. **Semántica MS-COCO Frontal 0° (Autobuses Type C):** En ángulos frontales puros sin perfil lateral, un autobús escolar convencional puede ser etiquetado por MS-COCO como `truck`/`car` mientras EXP-10 consolida la detección vehicular sin pérdida de presencia.
3. **Máquina de Estados Temporal (FSM):** `temporal_fsm_integrated` permanece `false` en `VisionEngineCoordinator` (conforme al alcance de la arquitectura vigente; el seguimiento temporal permanece desacoplado).
4. **Servidor WSGI:** El servicio se sirve sobre `NonBlockingTLSThreadedServer` / Werkzeug para operación local/LAN conforme a los módulos actuales de `VIGIA_API`.

---

## 13. DICTAMEN OFICIAL DE ACEPTACIÓN

# **`APPROVED — YOLO26x ACTIVE IN PRODUCTION`**

Se certifica con evidencia de runtime, telemetría de GPU/VRAM, logs de arranque verificados, persistencia transaccional en PostgreSQL y prueba en vivo de reversión que **`YOLO26x` (`experiments/yolo26x/weights/yolo26x.pt`) se encuentra activo, procesando inferencias reales sobre NVIDIA RTX 4050 CUDA en precisión FP16 con modo NMS-Free nativo, optimizaciones EXP-10 habilitadas y respaldo automático verificado hacia `YOLO11n`**.
