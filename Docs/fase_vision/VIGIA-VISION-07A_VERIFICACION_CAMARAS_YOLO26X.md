# VIGIA-VISION-07A — Verificación de YOLO26x y Cámaras Físicas Simultáneas

**Proyecto:** VIGÍA Vision Systems  
**Área:** Computer Vision / Auditoría de Producción en Tiempo Real  
**Tipo de Fase:** Auditoría y Observación Estricta de Solo Lectura  
**Fecha y Ventana de Observación:** 2026-11-16 (`18:52:23 – 18:59:37` CST | `2026-11-17T00:52:23Z – 00:59:35Z` UTC)  
**Servicio Auditado:** `VIGIA_API.ingest_service` (PID Launcher `46712` / PID Runtime `19556`, Puertos `5001` HTTPS / `5080` CRL)  
**Dictamen Técnico Oficial:** `APPROVED — DUAL CAMERA YOLO26X VERIFIED`

---

## REGLA OPERATIVA Y ALCANCE DE AUDITORÍA

La presente verificación se ejecutó íntegramente bajo modalidad de **observación pasiva y solo lectura**:
- No se modificó [Software/.env](file:///C:/GEST.PROY.TI/Software/.env) (hash SHA-256 preservado sin cambios: `144055B9C5257B07798C68C2793A91DC7235915FE3AC5155178202E507A05C96`).
- No se modificó ningún archivo de código fuente ni se generaron migraciones.
- No se detuvo ni se reinició el servicio productivo ni sus workers activos.
- No se inyectó tráfico HTTP artificial ni se insertaron o eliminaron registros o evidencias en PostgreSQL.

---

## 1. ESTADO DEL SERVICIO PRODUCTIVO (FASE 1)

| Atributo Verificado | Valor Empírico Observado | Evidencia |
| :--- | :--- | :--- |
| **Proceso Activo Único** | `VIGIA_API.ingest_service` (`task-5412`) | Launcher `.venv_cuda` PID `46712` $\to$ Runtime Python `19556` (inicio `18:44:09` CST) |
| **Procesos Duplicados** | `0` (instancia única confirmada) | Inspección `Win32_Process` al inicio y cierre de auditoría |
| **Firmador Criptográfico** | `start_signer.py` (`task-5087`) | Launcher PID `20612` $\to$ Child PID `30532` activo sobre Named Pipe |
| **Puertos en Escucha** | `0.0.0.0:5001` (HTTPS), `0.0.0.0:5080` (CRL), `127.0.0.1:5434` (PostgreSQL) | `netstat -ano` (`PID 19556` en `5001` y `5080`) |
| **Estado General API (`GET /` y `/api/v1/supervision/status`)** | `ONLINE` / `status: "OPERATIONAL"`, `engine_initialized: true` | Consulta autenticada `admin_dev` HTTP `200 OK` |
| **Modelo Solicitado / Activo en Memoria** | `yolo26x.pt` (`requested_model = effective_model = yolo26x.pt`) | Logs arranque + `GET /api/v1/supervision/status` |
| **Configuración Efectiva Runtime** | `device="cuda:0"`, `imgsz=640`, `quantize=16`, `effective_fp16=True`, `nms=False`, `end2end=True`, `end2end_verified=True` | Confirmado en `AutoBackend` (`one2one_cv2=True`, `one2many_cv2_liberada=True`) |
| **Configuración EXP-10 Activa** | `deduplicate_iou_threshold=0.55`, `consolidate_frontal_confidence=True`, `frontal_aux_enabled=True`, `frontal_aux_imgsz=384`, `frontal_aux_trigger_confidence=0.70` | Reportado por `detector` en `/api/v1/supervision/status` |
| **Respaldo / Fallback** | `fallback_enabled=True`, `using_fallback=False`, `fallback_count=0`, `fallback_model="yolo11n.pt"` | Sin activaciones en todo el ciclo productivo |

---

## 2. ESTADO INDIVIDUAL DE `CAM-ENTRADA` (FASE 2)

| Indicador Auditado | Estado / Valor al Inicio (`t=0`, `00:53:02Z`) | Estado / Valor al Cierre (`t=5m`, `00:59:34Z`) |
| :--- | :--- | :--- |
| **ID de Cámara (UUID)** | `2296f49a-edac-4b39-87cb-0f9b1499b82b` (`ROI-ENT`, `ENTRADA`) | Idéntico |
| **Tipo y URI de Conexión** | USB Local física (`usb://0`, backend `DSHOW`, `device_index=0`, `640x480`) | Idéntico (credencial activa `ae6152ac-6c20-40f7-a9a0-2fa1e0522d0e`) |
| **Estado de Conexión / Worker** | `TRANSMITIENDO` (`is_transmitting=true`, worker `VigiaPullWorker-CAM-ENTRADA` activo) | `TRANSMITIENDO` (`last_frame_seconds_ago` continuo $< 0.1$ s) |
| **Último Frame Procesado** | `2026-11-17T00:53:02.707Z` | `2026-11-17T00:59:34.652Z` |
| **Frames Recibidos (`ingest_count`)** | `7,512` | **`13,143`** (`+5,631` frames en ventana M0 $\to$ M5) |
| **Frames Procesados (`processed_count`)** | `7,512` | **`13,143`** (`+5,631` inferencias ejecutadas) |
| **FPS Captura / Procesamiento** | `13.63` / `13.29 FPS` | `14.41` / **`14.30 FPS`** |
| **Frames Descartados / Errores** | `0` descartados / `0` errores | **`0` descartados / `0` errores** |
| **Último Paso de Pipeline (`last_step_ms`)** | `122.925 ms` (con espera GPU `66.559 ms`) | `46.542 ms` (espera GPU `0.001 ms`) |
| **Modelo en Última Inferencia** | `yolo26x.pt` (`AUTOMOVIL`, `confianza=0.990`) | **`yolo26x.pt`** (`AUTOMOVIL`, `confianza=0.9854`) |

---

## 3. ESTADO INDIVIDUAL DE `CAM-SALIDA` (FASE 2)

| Indicador Auditado | Estado / Valor al Inicio (`t=0`, `00:53:02Z`) | Estado / Valor al Cierre (`t=5m`, `00:59:34Z`) |
| :--- | :--- | :--- |
| **ID de Cámara (UUID)** | `53a9c846-3bac-464c-a1bd-017690c961c0` (`ROI-SAL`, `SALIDA`) | Idéntico |
| **Tipo y URI de Conexión** | Push Móvil LAN (`push://cam-salida`, Android Chrome 157 desde `192.168.1.104`) | Idéntico (credencial `09356a98-7faf-4f81-9062-10686e031588`, enrolada `00:50:47Z`) |
| **Estado de Conexión / Recepción** | `TRANSMITIENDO` (`is_transmitting=true`, `POST /api/v1/cameras/CAM-SALIDA/push`) | `TRANSMITIENDO` |
| **Último Frame Procesado** | `2026-11-17T00:53:02.707Z` | `2026-11-17T00:59:34.652Z` |
| **Frames Recibidos (`ingest_count`)** | `130` | **`514`** (`+384` frames en ventana M0 $\to$ M5) |
| **Frames Procesados (`processed_count`)** | `130` | **`514`** (`+384` inferencias ejecutadas) |
| **FPS Captura / Procesamiento** | `0.97` / `0.98 FPS` | `0.99` / **`0.99 FPS`** |
| **Frames Descartados / Errores** | `0` descartados / `0` errores | **`0` descartados / `0` errores** |
| **Último Paso de Pipeline (`last_step_ms`)** | `77.659 ms` | `58.721 ms` |
| **Modelo en Última Inferencia** | `yolo26x.pt` (`AUTOMOVIL`, `confianza=0.9028`) | **`yolo26x.pt`** (`AUTOMOVIL`, `confianza=0.8950`) |

---

## 4. MODELO EFECTIVO Y CONFIRMACIÓN POR CÁMARA (FASE 3)

En las 6 instantáneas registradas entre `00:53:02Z` y `00:59:34Z`, se verificaron directamente sobre `GET /api/v1/supervision/status` los siguientes invariantes sin excepción:
- `detector.effective_model`: **`"yolo26x.pt"`**
- `detector.last_inference_model`: **`"yolo26x.pt"`**
- `detector.inference_metrics.inferences_by_model`: **`{"yolo26x.pt": 13658}`** al cierre (100.0% de las inferencias ejecutadas en todo el tiempo de vida del servicio `task-5412`, incluyendo los 13,143 frames de `CAM-ENTRADA`, los 514 frames de `CAM-SALIDA` y la sonda previa `CAM-03`).
- `detector.effective_fp16`: **`true`**
- `detector.end2end`: **`true`** (`end2end_verified: true`)
- `detector.device`: **`"cuda:0"`**
- `detector.using_fallback`: **`false`**
- **Por cámara:** tanto `cameras["CAM-ENTRADA"]["last_inference_model"]` como `cameras["CAM-SALIDA"]["last_inference_model"]` registraron **`"yolo26x.pt"`** en el 100% de las muestras (`M0..M5`).

No existió ninguna ejecución de `yolo11n.pt` ni activación de fallback.

---

## 5. EVIDENCIA DE INFERENCIA SIMULTÁNEA EN VENTANA DE OBSERVACIÓN (FASE 4)

Se observaron ambas cámaras durante un intervalo continuo superior a 5 minutos (**6 minutos 32 segundos reales**: `00:53:02Z` $\to$ `00:59:34Z`), capturando métricas minuto a minuto:

| Muestra (UTC) | `CAM-ENTRADA` Proc (FPS / Drops) | `CAM-SALIDA` Proc (FPS / Drops) | Total Infs Detector (`inferences_by_model`) | Modelo Activo / Último Modelo | Latencia GPU P50 / P95 / P99 (ms) | VRAM Alloc / Res (`nvidia-smi` Uso / Libre) | GPU Util / Temp | Errores |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: | :---: |
| **M0 (`00:53:02Z`)** | `7,512` (`13.29 fps`, `0`) | `130` (`0.98 fps`, `0`) | `7,643` (`yolo26x.pt: 7,643`) | `yolo26x.pt` / `yolo26x.pt` | `49.07 / 129.13 / 169.75` | `402.84 / 594.0 MiB` (`2,218 / 3,704 MiB`) | `25%` / `65 °C` | `0` |
| **M1 (`00:54:22Z`)** | `8,665` (`14.52 fps`, `0`) | `207` (`1.06 fps`, `0`) | `8,873` (`yolo26x.pt: 8,873`) | `yolo26x.pt` / `yolo26x.pt` | `22.39 / 57.82 / 62.93` | `402.86 / 594.0 MiB` (`2,225 / 3,697 MiB`) | `40%` / `63 °C` | `0` |
| **M2 (`00:55:36Z`)** | `9,740` (`14.25 fps`, `0`) | `279` (`1.04 fps`, `0`) | `10,020` (`yolo26x.pt: 10,020`) | `yolo26x.pt` / `yolo26x.pt` | `22.42 / 58.41 / 117.38` | `402.86 / 594.0 MiB` (`2,163 / 3,759 MiB`) | `26%` / `67 °C` | `0` |
| **M3 (`00:56:55Z`)** | `10,861` (`14.30 fps`, `0`) | `357` (`0.96 fps`, `0`) | `11,219` (`yolo26x.pt: 11,219`) | `yolo26x.pt` / `yolo26x.pt` | `23.17 / 58.88 / 117.48` | `402.84 / 594.0 MiB` (`2,201 / 3,721 MiB`) | `42%` / `64 °C` | `0` |
| **M4 (`00:58:09Z`)** | `11,914` (`14.19 fps`, `0`) | `431` (`1.06 fps`, `0`) | `12,346` (`yolo26x.pt: 12,346`) | `yolo26x.pt` / `yolo26x.pt` | `23.60 / 59.59 / 117.97` | `402.84 / 594.0 MiB` (`2,179 / 3,743 MiB`) | `36%` / `67 °C` | `0` |
| **M5 (`00:59:34Z`)** | **`13,143`** (`14.30 fps`, `0`) | **`514`** (`0.99 fps`, `0`) | **`13,658`** (`yolo26x.pt: 13,658`) | `yolo26x.pt` / `yolo26x.pt` | `39.96 / 60.54 / 121.00` | `402.84 / 594.0 MiB` (`2,174 / 3,748 MiB`) | `43%` / `67 °C` | `0` |

**Incremento Neto Simultáneo Verificado (`M0` $\to$ `M5`):**
- **`CAM-ENTRADA`:** `+5,631` inferencias continuas simultáneas (~14.36 FPS sostenidos).
- **`CAM-SALIDA`:** `+384` inferencias continuas simultáneas (~1.01 FPS sostenidos desde móvil Android LAN).
- **Total Combinado en Ventana:** `+6,015` inferencias ejecutadas concurrentemente en GPU sin descartes ni bloqueos.

---

## 6. MÉTRICAS DE RENDIMIENTO Y EFECTO EXP-10

- **Latencia de Inferencia (ventana móvil de cierre M5):** Media **`35.448 ms`**, Mediana **P50 `39.959 ms`**, **P95 `60.541 ms`**, **P99 `120.995 ms`** (`inference_fps`: **`28.21 FPS`**).
- **Espera Media por Lock GPU (`queue_wait_mean_ms`):** `2.341 – 9.078 ms` (`3.738 ms` al cierre M5). Ambos hilos/fuentes alternaron limpiamente en el mutex GPU sin inanición (`queue_wait` observados en contención ocasional: `66.56 ms` / `115.05 ms` en `CAM-ENTRADA` y `19.75 ms` / `25.90 ms` en `CAM-SALIDA`, siempre por debajo de cualquier límite de bloqueo).
- **Desempeño EXP-10 en Ventana (`M0` $\to$ `M5`):**
  - Disparos de sonda auxiliar 384 (`frontal_aux_triggers`): `5,262` $\to$ `7,606` (**`+2,344`** disparos).
  - Recuperaciones efectivas (`frontal_aux_recoveries`): `1,150` $\to$ `3,484` (**`+2,334`** recuperaciones confirmadas de confianza frontal).
  - Duplicados inter/intra-clase suprimidos (`duplicates_suppressed`): `8,070` $\to$ `30,893` (`+22,823`).

---

## 7. INTEGRIDAD DE DETECCIONES EN POSTGRESQL Y EVIDENCIAS EN DISCO (FASE 5)

Durante la ventana observada (`2026-11-17T00:52:00Z` $\to$ `00:59:35Z`), ambas cámaras persistieron **282 detecciones reales** de forma intercalada en el tiempo:

| Cámara | Área / Tipo Mov. | Detecciones Persistidas | Clases Detectadas | Confianza Min / Max / Media | Rango Horario UTC | Desajustes Ruta / Archivos Faltantes |
| :--- | :--- | :---: | :--- | :---: | :--- | :---: |
| **`CAM-ENTRADA`** | `ROI-ENT` / `ENTRADA` | `153` | `AUTOMOVIL` (`150`), `CAMION` (`3`) | `0.716` / `0.990` / `0.974` | `00:52:02.131Z` – `00:59:34.973Z` | **`0` / `0`** |
| **`CAM-SALIDA`** | `ROI-SAL` / `SALIDA` | `129` | `AUTOMOVIL` (`129`) | `0.855` / `0.969` / `0.905` | `00:52:01.699Z` – `00:59:32.999Z` | **`0` / `0`** |
| **Total Ventana** | — | **`282`** | `AUTOMOVIL` (`279`), `CAMION` (`3`) | — | **`00:52:01Z` – `00:59:34Z`** | **`0` desajustes / `0` faltantes** |

### Muestras Intercaladas Recientes Confirmadas en BD y Disco
1. `0a52a089-5402-4b53-b7b9-dd0ee66101dd` | **`CAM-ENTRADA`** (`AUTOMOVIL`, `0.969`) | `20261117/CAM-ENTRADA/20261117T005934_973784Z_461502264988_orig.jpg` | `00:59:34.973784Z`
2. `98878e61-7179-4688-8683-19132c265ecf` | **`CAM-SALIDA`** (`AUTOMOVIL`, `0.886`) | `20261117/CAM-SALIDA/20261117T005932_999798Z_89f450236ec3_orig.jpg` | `00:59:32.999798Z`
3. `79e462e8-f9a2-46dc-93aa-48868f8cb51d` | **`CAM-ENTRADA`** (`AUTOMOVIL`, `0.989`) | `20261117/CAM-ENTRADA/20261117T005931_939251Z_472670b9801a_orig.jpg` | `00:59:31.939251Z`
4. `994b0b77-95d8-4ee5-ae7e-44ecd894942a` | **`CAM-SALIDA`** (`AUTOMOVIL`, `0.953`) | `20261117/CAM-SALIDA/20261117T005929_032307Z_59677db34891_orig.jpg` | `00:59:29.032307Z`
5. `84a10d3c-9f60-4450-be1d-fe68469eab45` | **`CAM-ENTRADA`** (`AUTOMOVIL`, `0.975`) | `20261117/CAM-ENTRADA/20261117T005928_915016Z_68c4b9554acc_orig.jpg` | `00:59:28.915016Z`
6. `684d6e15-72cc-4159-95ad-6d192949d21d` | **`CAM-SALIDA`** (`AUTOMOVIL`, `0.938`) | `20261117/CAM-SALIDA/20261117T005926_007776Z_37b44dc9752d_orig.jpg` | `00:59:26.007776Z`

Verificación cruzada automática: las **282** filas de la ventana apuntan estrictamente al subdirectorio correspondiente a su `camara.codigo` (`CAMERA_PATH_MISMATCHES=0`) y poseen tanto archivo `*_orig.jpg` como `*_annot.jpg` válidos en disco (`MISSING_ORIG_FILES=0`, `MISSING_ANNOT_FILES=0`).

---

## 8. USO DE GPU, VRAM, ERRORES Y ANOMALÍAS

- **Estabilidad de VRAM PyTorch:** Permaneció completamente plana en **`402.84 – 402.86 MiB`** asignados y **`594.00 MiB`** reservados a lo largo de más de **13,658** inferencias (`0.00 MiB` de fuga).
- **Consumo Global del Sistema (`nvidia-smi`):** Entre **`2,163 MiB` y `2,225 MiB`** utilizados de **`6,141 MiB`** totales (margen libre constante de **`3,697 – 3,759 MiB`**), utilización GPU **`25% – 43%`**, temperatura estable en **`63 – 67 °C`**.
- **Errores o Anomalías Observadas:**
  - En los logs completos del servicio productivo (`task-5412.log`): **`0` `ERROR`**, **`0` `CRITICAL`**, **`0` `Traceback`**, **`0` eventos `FALLBACK`**, **`0` `inference_errors`** y **`0` `cuda_errors`**.
  - Única observación informativa registrada: al invocar una única vez el endpoint de diagnóstico `GET /api/v1/devices/usb-cameras` durante `t=0`, OpenCV emitió mensajes `WARN` al sondear si existían cámaras libres en índices alternos (`device_index=1`), omitiendo correctamente el `device_index=0` en uso por `CAM-ENTRADA` sin interrupción ni error funcional.

---

## 9. DICTAMEN TÉCNICO FINAL

# **`APPROVED — DUAL CAMERA YOLO26X VERIFIED`**

Se certifica técnicamente mediante telemetría runtime, inspección de procesos, auditoría de PostgreSQL, validación física de evidencias en disco y monitoreo continuo simultáneo durante más de 5 minutos que:
1. Ambas cámaras físicas reales (**`CAM-ENTRADA`** USB DSHOW y **`CAM-SALIDA`** Mobile Push HTTPS) reciben fotogramas y alimentan simultáneamente el pipeline productivo (`13,143` y `514` cuadros procesados respectivamente, `0` descartes).
2. Todas las inferencias acumuladas (`13,658 / 13,658`) y la última inferencia individual de cada cámara están atribuidas y ejecutadas por **`yolo26x.pt`** en `cuda:0` con precisión **FP16**, modo **NMS-Free (`end2end=True`)**, optimizaciones **EXP-10** activas y **`using_fallback=false`**.
3. La integridad referencial y de almacenamiento de las `282` detecciones registradas durante la ventana es del **100%** (`0` desajustes entre cámara y archivo de evidencia).
4. El servicio productivo y `.env` permanecen íntegros y sin alteraciones ni reinicios.
