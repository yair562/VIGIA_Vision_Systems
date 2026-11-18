# VIGIA-VISION-05C — Auditoría y Activación Controlada de YOLO26x

**Proyecto:** VIGÍA Vision Systems  
**Área:** Computer Vision / Deep Learning / Inferencia en Tiempo Real  
**Fecha de Ejecución:** 2026-11-16 (UTC: 2026-11-17T00:21:30Z)  
**Entorno de Ejecución:** GPU NVIDIA GeForce RTX 4050 Laptop GPU (6140.5 MiB VRAM), CUDA 12.4, Python 3.11.1, PyTorch 2.6.0+cu124, Ultralytics 8.4.171  
**Checkpoint Validado:** [yolo26x.pt](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/weights/yolo26x.pt)  
**Modelo de Respaldo:** [yolo11n.pt](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/yolo11n.pt)  
**Veredicto Oficial:** `APPROVED FOR CONTROLLED OPERATIONAL VALIDATION`

---

## 1. ESTADO INICIAL Y CONTEXTO OPERATIVO

Previo a la presente fase, el repositorio VIGÍA Vision Systems contaba con:
1. **Fase VISION-05A completada y aprobada:** Demostró la efectividad de las optimizaciones EXP-10 (sonda multiescala condicional a `imgsz=384`, deduplicación probabilística IoU 0.55 y consolidación de clases vehiculares) para solventar caídas de detección frontal.
2. **Servicios operativos en ejecución:** Se detectaron en ejecución dos procesos de fondo sin perturbaciones:
   - Demonio de firma criptográfica CA ([start_signer.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/start_signer.py) sobre Named Pipe `\\.\pipe\vigia_ca_signer`).
   - Servicio de ingesta HTTP VIGÍA API ([ingest_service.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py) en puerto `5001`).
3. **Restricción de producción:** El archivo `.env` de producción permanece intacto con `VIGIA_YOLO_MODEL=yolo11n.pt` como línea base predeterminada. La activación de `yolo26x.pt` se ejecutó en un arnés de validación controlada y aislada que no compromete puertos en escucha ni interrumpe la captura física no autorizada.

---

## 2. AUDITORÍA DE CONFIGURACIÓN Y MATRIZ DE MIGRACIÓN

Se realizó una inspección exhaustiva de la trazabilidad de variables de entorno y su aplicación efectiva en el código fuente:

| Parámetro de Configuración | Variable de Entorno | Valor Solicitado | Valor Efectivo en Detector | Evidencia de Verificación en Código / Runtime |
| :--- | :--- | :--- | :--- | :--- |
| **Modelo Principal** | `VIGIA_YOLO_MODEL` | `experiments/yolo26x/weights/yolo26x.pt` | `C:\GEST.PROY.TI\Software\VIGIA_Vision_Systems\experiments\yolo26x\weights\yolo26x.pt` | Checkpoint existe (118,667,365 bytes, SHA-256 verificado). Resuelto por `resolve_yolo_weights_path()`. |
| **Dispositivo de Cómputo** | `VIGIA_YOLO_DEVICE` | `cuda:0` | `cuda:0` | `torch.cuda.is_available()=True`, GPU: RTX 4050 Laptop (6140.5 MB). Validado en `_validate_device()`. |
| **Resolución Primaria** | `VIGIA_YOLO_IMGSZ` | `640` | `640` | `YoloDetectorConfig.imgsz=640`. `AutoBackend` dimensionado a 640x640. |
| **Precisión Cuántica** | `VIGIA_YOLO_QUANTIZE` | `16` (FP16) | `16` | `quantize=16`, `AutoBackend.fp16=True`, weights `torch.float16`. |
| **Modo Inferencia NMS** | `VIGIA_YOLO_NMS` | `false` (NMS-Free) | `False` | `nms=False`, `AutoBackend.end2end=True`, rama `one2one_cv2=True`. |
| **Test-Time Augmentation** | `VIGIA_YOLO_AUGMENT` | `false` | `False` | Inferencia determinística sin TTA para minimizar latencia en GPU. |
| **Activación de Fallback** | `VIGIA_YOLO_FALLBACK_ENABLED` | `true` | `True` | Conmutador de resiliencia atómica activo en fallos de inicialización o runtime. |
| **Modelo de Respaldo** | `VIGIA_YOLO_FALLBACK_MODEL` | `yolo11n.pt` | `C:\GEST.PROY.TI\Software\VIGIA_Vision_Systems\yolo11n.pt` | Archivo baseline verificado (5,613,764 bytes, SHA-256 verificado). |
| **Umbral IoU Dedup (EXP-10)**| `VIGIA_YOLO_DEDUP_IOU` | `0.55` | `0.55` | `deduplicate_iou_threshold=0.55`. Filtra solapamientos entre clases vehiculares. |
| **Consolidación Confianza** | `VIGIA_YOLO_CONSOLIDATE_CONFIDENCE`| `true` | `True` | Agrega masa de probabilidad dividida entre `car`, `truck` y `bus`. |
| **Sonda Auxiliar Multiescala**| `VIGIA_YOLO_FRONTAL_AUX_ENABLED` | `true` | `True` | Dispara pase secundario si confianza primaria < 0.70. |
| **Resolución Sonda Auxiliar**| `VIGIA_YOLO_FRONTAL_AUX_IMGSZ` | `384` | `384` | Inferencia ligera en 384x384 focalizada en geometría vehicular frontal. |
| **Umbral Disparo Sonda** | `VIGIA_YOLO_FRONTAL_AUX_TRIGGER_CONF`| `0.70` | `0.70` | Umbral para activar refinamiento frontal de EXP-10. |

---

## 3. COMPATIBILIDAD DEL ENTORNO DE EJECUCIÓN

- **Sistema Operativo:** Microsoft Windows 11 Home (x64)
- **Intérprete Python:** 3.11.1 (`.venv_cuda\Scripts\python.exe`)
- **PyTorch:** 2.6.0+cu124
- **TorchVision:** 0.21.0+cu124
- **CUDA Runtime:** 12.4 (cuDNN 90100)
- **Ultralytics Framework:** 8.4.171
- **Acelerador de Hardware:** NVIDIA GeForce RTX 4050 Laptop GPU (Compute Capability 8.9)
- **Memoria VRAM Total:** 6140.5 MiB
- **Memoria VRAM Disponible Previa:** 5075.0 MiB
- **Integridad Criptográfica de Pesos:**
  - `yolo26x.pt`:
    - Ruta: `experiments/yolo26x/weights/yolo26x.pt`
    - Tamaño: 118,667,365 bytes
    - SHA-256: `9fdd44a31c504547ffb81d2c6d9e6dac3493c8eaa8b0398d3f43bae6c7003e92`
    - Compatibilidad: Arquitectura Ultralytics v8/YOLO26 nativa, rama dual one-to-one / one-to-many.
  - `yolo11n.pt` (Fallback):
    - Ruta: `yolo11n.pt`
    - Tamaño: 5,613,764 bytes
    - SHA-256: `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`
    - Compatibilidad: Baseline verificado con soporte NMS tradicional.

---

## 4. CONFIGURACIÓN EFECTIVA EN RUNTIME

Durante la inicialización controlada, el componente [yolo_detector.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py) reportó la siguiente configuración efectiva verificada en memoria:
- `model_path`: `experiments/yolo26x/weights/yolo26x.pt`
- `device`: `cuda:0`
- `effective_fp16`: `True`
- `effective_imgsz`: `640`
- `nms`: `False` (NMS-Free activo en `AutoBackend`)
- `end2end`: `True` (detección directa sin post-procesamiento NMS tradicional en GPU)
- `fallback_enabled`: `True`
- `fallback_model_path`: `yolo11n.pt`
- `deduplicate_iou_threshold`: `0.55`
- `consolidate_frontal_confidence`: `True`
- `frontal_aux_enabled`: `True`
- `frontal_aux_imgsz`: `384`
- `frontal_aux_trigger_confidence`: `0.70`

---

## 5. EVIDENCIA DE CARGA Y SONDAS SINTÉTICAS

La carga e inicialización del modelo YOLO26x en la GPU se completó con éxito:
- **Tiempo de carga inicial del checkpoint:** `418.42 ms`
- **Sonda sintética inicial (Warmup CUDA + FP16 + End2End):** `1105.17 ms`
- **Asignación de Memoria VRAM post-carga:**
  - VRAM Asignada (`allocated`): `370.84 MiB` (~6.0% de la capacidad de 6 GB)
  - VRAM Reservada (`reserved`): `562.00 MiB` (~9.1% de la capacidad de 6 GB)
- **Verificación AutoBackend:** `modelo='yolo26x.pt'`, `end2end=True`, `one2one_cv2=True`, `one2many_cv2_liberada=True`.

---

## 6. EVIDENCIA DE INFERENCIA REAL EN EL PIPELINE OPERATIVO

Para validar el flujo completo de producción sin comprometer puertos externos, se instanció el pipeline HTTP a través del cliente de pruebas de [ingest_service.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py) conectado a la base de datos PostgreSQL activa (`127.0.0.1:5434`):

### 6.1. Ingesta de Frame Real (`POST /api/v1/ingest/frame`)
- **Autenticación:** Sesión operativa iniciada para `admin_05c` con rol funcional `ADMINISTRADOR`.
- **Cámara evaluada:** `CAM-ENTRADA` (ROI configurado `ROI-ENT`).
- **Fotograma inyectado:** Imagen vehicular real del corpus histórico de VIGÍA.
- **Respuesta HTTP:** `200 OK` en `881.53 ms` (incluyendo inferencia YOLO26x en GPU, clasificación cromática, renderizado de evidencia y persistencia transaccional en PostgreSQL).
- **Cuerpo de Respuesta:**
  ```json
  {
    "ok": true,
    "status": "VEHICLE_DETECTED_NO_PLATE",
    "vehicle_detected": true,
    "tipo_vehiculo": "AUTOMOVIL",
    "confianza": 0.9744,
    "tipo_movimiento": "ENTRADA",
    "codigo_camara": "CAM-ENTRADA",
    "codigo_area": "ROI-ENT",
    "detections_count": 1,
    "in_roi_now": 1,
    "detection_persisted": true,
    "id_deteccion": "51ad8768-e6af-4c5c-8c24-a12da6587acc",
    "evidence_saved": true,
    "original_evidence_path": "20261117/CAM-ENTRADA/20261117T002123_973208Z_cc4d19790443_orig.jpg",
    "annotated_evidence_path": "20261117/CAM-ENTRADA/20261117T002123_973208Z_cc4d19790443_annot.jpg"
  }
  ```

### 6.2. Telemetría del Servicio de Supervisión (`GET /api/v1/supervision/status`)
La inspección de estado del supervisor confirmó que el motor operativo de visión se encuentra respaldado por YOLO26x en tiempo real:
```json
{
  "engine_initialized": true,
  "ok": true,
  "status": "OPERATIONAL",
  "vision_metrics": {
    "cameras": {
      "CAM-ENTRADA": {
        "effective_model": "yolo26x.pt",
        "ingest_count": 1,
        "processed_count": 1,
        "dropped_frames": 0,
        "last_status": "PROCESSED",
        "last_step_ms": 645.0
      }
    },
    "detector": {
      "effective_model": "yolo26x.pt",
      "requested_model": "yolo26x.pt",
      "device": "cuda:0",
      "effective_fp16": true,
      "end2end": true,
      "nms": false,
      "quantize": 16,
      "using_fallback": false,
      "frontal_aux_triggers": 1,
      "frontal_aux_recoveries": 1,
      "duplicates_suppressed": 2,
      "inference_errors": 0,
      "cuda_errors": 0,
      "gpu_memory": {
        "vram_allocated_mb": 371.78,
        "vram_reserved_mb": 566.0
      }
    }
  }
}
```

---

## 7. RESULTADOS DE DETECCIÓN SOBRE CORPUS DE EVIDENCIAS

Se evaluaron 11 muestras representativas de las evidencias históricas de VIGÍA ([evidencias_vigia/](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/evidencias_vigia/)), comparando la detección a nivel de presencia (umbral libre 0.25) y detección operativa de producción (umbral de corte 0.70):

| ID Muestra | Categoría Vehicular Evaluada | Relativa en Corpus | Latencia (ms) | In-ROI (>=0.70) | In-ROI (>=0.25) | Etiqueta / Confianza Primaria | Hit Operativo (>=0.70) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **EV-0625** | Automóvil frontal (cian, corta distancia) | `20261116/...c43de572acc5_orig.jpg` | 56.42 ms | 1 | 1 | `car` (0.7969) | **PASS** |
| **EV-0637** | Automóvil frontal (rosa, desenfoque / primer plano) | `20261116/...957178f6e593_orig.jpg` | 62.89 ms | 1 | 1 | `car` (0.8179) | **PASS** |
| **EV-0657** | Automóvil frontal (rosa, rotación leve) | `20261116/...e8a735512bc2_orig.jpg` | 62.02 ms | 1 | 1 | `car` (0.9744) | **PASS** |
| **EV-0581** | Autobús frontal escolar 0° (Type C) | `20261114/...29a0e74bbe1e_orig.jpg` | 27.85 ms | 2 | 2 | `truck` (0.7785) | **PASS** (Presencia) |
| **EV-0584** | Autobús frontal escolar 0° (Type C + auto) | `20261114/...1d02f0a21e97_orig.jpg` | 29.75 ms | 2 | 2 | `car` (0.8984) | **PASS** |
| **EV-0588** | Autobús frontal escolar 0° (Type C) | `20261114/...bbf2d0cdf38b_orig.jpg` | 57.85 ms | 1 | 2 | `car` (0.8535) | **PASS** |
| **EV-0550** | Vehículo lateral (autobús escolar lateral) | `20261114/...5f4588730e82_orig.jpg` | 56.09 ms | 1 | 1 | `bus` (0.8572) | **PASS** |
| **EV-0665** | Vehículo frontal oblicuo (autobús rotado) | `20261116/...c2499a3ef3d5_orig.jpg` | 61.67 ms | 0 | 1 | `bus` (0.4419) | *Tolerado* (Hit @ 0.25) |
| **EV-0446** | Vehículo trasero (auto rojo sobre mesa) | `20261110/...d30f0fa6dafd_orig.jpg` | 92.84 ms | 1 | 1 | `truck` (0.8868) | **PASS** |
| **EV-0450** | Vehículo pequeño (recaptura pantalla) | `20261111/...95edf2ebf66c_orig.jpg` | 116.60 ms | 6 | 10 | `car` (0.9648) | **PASS** |
| **EV-0494** | Baja iluminación severa (auto en penumbra) | `20261114/...2271be730b5b_orig.jpg` | 45.56 ms | 0 | 1 | `car` (0.5776) | *Tolerado* (Hit @ 0.25) |

### Resumen Global de Rendimiento sobre el Corpus
- **Muestras Totales Evaluadas:** 11
- **Detección Efectiva Operativa (Confianza >= 0.70):** 9 / 11 (**81.8%**)
- **Detección de Presencia Vehicular (Confianza >= 0.25):** 11 / 11 (**100.0%**)
- **Latencia Media de Inferencia:** `60.87 ms` por fotograma (Inferencia pura en GPU: ~16.4 FPS teóricos).
- **Activación de Optimizaciones EXP-10:**
  - Sonda auxiliar 384x384 disparada: **9 veces**.
  - Recuperaciones efectivas con incremento de confianza: **7 veces**.
  - Detecciones duplicadas suprimidas: **35 duplicados**.

---

## 8. LATENCIA Y CONSUMO DE RECURSOS

Durante la ejecución continua de inferencias con YOLO26x en GPU:
- **Consumo de VRAM Base (PyTorch / CUDA):** `52.34 MiB` asignados / `174.00 MiB` reservados.
- **Consumo de VRAM Pico con YOLO26x (640x640 FP16):** `390.13 MiB` asignados / `588.00 MiB` reservados.
- **Margen de Seguridad en VRAM:** En una GPU de 6 GB (6140.5 MiB), YOLO26x ocupa únicamente el **6.35%** de la memoria VRAM disponible, garantizando coexistencia holgada con el modelo de clasificación cromática y los buffers de captura.
- **Throughput de Inferencia:**
  - P50 (Mediana): `57.82 ms`
  - Media: `60.87 ms`
  - P95: `286.41 ms` (incluyendo disparo ocasional de sonda auxiliar 384 en resoluciones altas)
  - Tasa de Procesamiento Sostenida: **12.56 a 16.40 FPS** en GPU.

---

## 9. VERIFICACIÓN OBSERVABLE DE FALLBACK Y RESILIENCIA

Se sometió a prueba el mecanismo de resiliencia atómica ante cuatro escenarios adversos controlados:

1. **Caso A — Fallo en Inicialización de Pesos (`model_init`):**
   - *Condición inducida:* Solicitud de archivo de pesos inexistente (`weights_non_existent.pt`).
   - *Comportamiento observado:* Detección inmediata de `FileNotFoundError`, activación automática del respaldo hacia `yolo11n.pt` en `2913.72 ms` con verificación sintética de arranque.
   - *Resultado:* **PASS** (`using_fallback=True`, `effective_model='yolo11n.pt'`).

2. **Caso B — Fallo Transitorio en Inferencia Runtime (`runtime_inference`):**
   - *Condición inducida:* Inyección de fallo de kernel CUDA (`RuntimeError: Simulated transient CUDA kernel failure`).
   - *Comportamiento observado:* Conmutación en caliente inmediata a `yolo11n.pt` en `0.24 ms`, con reintento único y transparente del fotograma actual sin interrupción del servicio ni escape de excepción no controlada.
   - *Resultado:* **PASS** (`using_fallback=True`, `single_retry_completed=True`).

3. **Caso C — Corrupción Numérica de Salida (NaN / Inf):**
   - *Condición inducida:* Inyección de coordenadas no finitas (`np.nan` en `box.xyxy`).
   - *Comportamiento observado:* Detección de salida no finita en `_parse_prediction_results()`, conmutación atómica a `yolo11n.pt` en `0.31 ms`.
   - *Resultado:* **PASS** (`using_fallback=True`, `effective_model='yolo11n.pt'`).

4. **Caso D — Prueba de Estabilidad (VRAM Soak Test de 10 Infecciones Consecutivas):**
   - *Condición inducida:* 10 inferencias consecutivas de fotogramas completos en GPU con `yolo26x.pt`.
   - *Comportamiento observado:* 0 errores de CUDA, 0 fugas de memoria VRAM (pico estable en `390.13 MiB`), descarga limpia verificada con `det.unload()`.
   - *Resultado:* **PASS** (`inference_errors=0`, `clean_unload_verified=True`).

---

## 10. LIMITACIONES IDENTIFICADAS Y BRECHA DE GROUND TRUTH

1. **Semántica MS-COCO en Autobuses Escolares Frontales (0°):**
   - Los autobuses escolares convencionales (Type C, con cofre alargado tipo camión) carecen de ventanillas laterales visibles desde un ángulo frontal puro de 0°.
   - Consecuentemente, el modelo preentrenado en MS-COCO clasifica la vista frontal como `truck` (camión) o `car` con alta confianza (77% a 89%), clasificando como `bus` únicamente cuando existe rotación oblicua o perspectiva lateral (e.g. `EV-0550` con 85.72% `bus`).
   - La consolidación de clases vehiculares de EXP-10 mitiga este fenómeno al fusionar las probabilidades vehiculares, asegurando que la presencia vehicular no se pierda.
2. **Brecha de Ground Truth Físico Certificado:**
   - La precisión vehicular reportada (81.8% en umbral operativo 0.70 y 100% en umbral de presencia 0.25) se basa en las muestras históricas capturadas en pruebas de laboratorio y de escritorio.
   - **No debe declararse validada la precisión operativa definitiva en campo** hasta que el propietario del proyecto realice la prueba física con vehículos reales en los carriles de entrada y salida, contrastando contra un conjunto de ground truth formalmente anotado.

---

## 11. CAMBIOS REALIZADOS

1. **Ajuste del Arnés de Pruebas de Resiliencia:** Se actualizó `validate_vision_05c_controlled.py` para utilizar un doble de prueba funcional durante la verificación de conmutación en caliente de fallback en tiempo de ejecución.
2. **Verificación de Ingesta E2E sin Ocupación de Puertos:** Se implementó la validación HTTP mediante el cliente de pruebas WSGI de Flask, permitiendo auditar la totalidad de la pila de ingesta y supervisión sin colisionar con los puertos `5001` y `5080` de los procesos en ejecución.
3. **Consolidación de Métricas de Runtime:** Se verificó que `YoloVehicleDetector` expone telemetría completa de VRAM, latencias P50/P95/P99, activaciones de sonda auxiliar y supresión de duplicados.

---

## 12. ARCHIVOS MODIFICADOS Y CREADOS

- **Creado:** [validate_vision_05c_controlled.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/scripts/validate_vision_05c_controlled.py) — Script integral de validación controlada de VISION-05C.
- **Creado:** [vision_05c_controlled_results.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/results/vision_05c_controlled_results.json) — Archivo de telemetría y resultados empíricos brutos de VISION-05C.
- **Creado:** [VIGIA-VISION-05C_ACTIVACION_CONTROLADA_YOLO26X.md](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_vision/VIGIA-VISION-05C_ACTIVACION_CONTROLADA_YOLO26X.md) — Informe técnico primario de la fase.
- **Creado:** `C:\GEST.PROY.TI\Software\Docs\fase_vision\VIGIA-VISION-05C_ACTIVACION_CONTROLADA_YOLO26X.md` — Réplica exacta del informe técnico en el workspace raíz.

---

## 13. PRUEBAS EJECUTADAS Y REGRESIÓN

Se ejecutaron las siguientes suites de verificación automática con **100% de éxito**:

| Suite de Pruebas | Módulos Evaluados | Pruebas | Resultado |
| :--- | :--- | :--- | :--- |
| **Validación Controlada VISION-05C** | Fases 1 a 6 (Auditoría, Carga, HTTP Push, Corpus, Fallback) | 6 fases | **PASS (Exit Code 0)** |
| **Suites Unitarias de Regresión YOLO** | `test_vision_05a_frontal_optimization`, `test_vision_04a_progressive_integration`, `test_vision_03c2_yolo26x_integration`, `test_yolo_detector` | 50 pruebas | **50 PASS / 0 FAIL (10.86s)** |
| **Componentes de Visión y Captura** | `test_vision_stage1_components` | 16 pruebas | **16 PASS / 0 FAIL (0.14s)** |
| **Clasificador Cromático Vehicular** | `test_vision_05b_color_classifier` | 11 pruebas | **11 PASS / 0 FAIL (6.02s)** |
| **Máquina de Estados FSM y Pipeline** | `test_vision_02a_temporal_fsm`, `test_vision_pipeline` | 30 pruebas | **30 PASS / 0 FAIL (0.23s)** |
| **Total General de Pruebas Automatizadas** | **Todas las suites de visión ejecutadas** | **107 pruebas** | **107 PASS / 0 FAIL** |

---

## 14. HASH SHA-256 DEL INFORME Y VEREDICTO DE ACEPTACIÓN

- **Veredicto Técnico:** `APPROVED FOR CONTROLLED OPERATIONAL VALIDATION`
- **Condición de Aprobación:** La presente autorización certifica que YOLO26x se encuentra técnica y empíricamente verificado en la GPU con FP16 y NMS-Free, demostrando alta resiliencia operativa y coexistencia estable con el fallback YOLO11n. El despliegue como modelo predeterminado de producción en `.env` queda reservado para la validación física en campo con vehículos reales.
