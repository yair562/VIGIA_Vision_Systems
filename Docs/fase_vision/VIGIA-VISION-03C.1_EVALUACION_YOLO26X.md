# VIGIA-VISION-03C.1 — Evaluación Técnica e Incorporación Experimental de YOLO26x

**Proyecto:** VIGÍA Vision Systems  
**Fase:** `VISION-03C.1` — Evaluación técnica e integración experimental aislada  
**Fecha de evaluación:** 2026-11-14 (UTC `2026-11-14T19:12:54Z`)  
**Hardware evaluado:** NVIDIA GeForce RTX 4050 Laptop GPU (`6141 MiB` VRAM, Driver `566.36`, CUDA `12.4`, cuDNN `90100`)  
**Stack experimental:** Python `3.11.1`, PyTorch `2.6.0+cu124`, TorchVision `0.21.0+cu124`, Ultralytics `8.4.171`  
**Estado:** Completada y auditada experimentalmente (cero cambios en código de producción)

---

## 1. Resumen Ejecutivo y Decisión de Arquitectura

Se evaluó de manera aislada y reproducible la arquitectura objetivo **Ultralytics YOLO26x (`yolo26x.pt`)** frente a la línea base actual en producción (**YOLO11n**, `yolo11n.pt`) y la referencia pesada de generación anterior (**YOLO11x**, `yolo11x.pt`), dentro del entorno experimental dedicado [experiments/yolo26x](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/README.md).

### Conclusiones principales

1. **Viabilidad técnica, rendimiento y VRAM en RTX 4050 (6 GB): APROBADA.**
   - En configuración **`640` FP16 con cabezal nativo NMS-Free (`nms=False` / `end2end=True`)**, `yolo26x.pt` alcanza **`17.87 ms` promedio (`p95 = 20.726 ms`, `55.96 FPS`)** y consume apenas **`251.76 MB` de VRAM PyTorch pico** (`1,680.76 MB` NVML totales del sistema frente a `6,141 MiB` físicos), superando en velocidad incluso a `yolo11x` FP16 (`20.543 ms`, `48.68 FPS`).
   - En resolución ampliada **`800` FP16**, sostiene **`24.596 ms` (`p95 = 26.275 ms`, `40.66 FPS`)** con la misma huella de VRAM PyTorch pico (`251.76 MB`, `1,760.76 MB` NVML totales).
   - En prueba sostenida de **`200` iteraciones continuas**, registró **`0` errores CUDA**, **`-0.01 MB` de fuga de VRAM** (`0` leaks), estabilidad térmica (`61.0°C -> 66.0°C` pico en FP16; `64.0°C -> 68.0°C` pico en FP32) y latencia estable (`18.006 ms` en FP16, `26.399 ms` en FP32).
2. **Hallazgo crítico de integración en Ultralytics `8.4.171` (`end2end` vs `nms`):**
   - Aunque `yolo26x.pt` contiene el cabezal dual `one2one` (`ckpt.model.yaml["end2end"] = True`, `reg_max = 1`), el checkpoint carga con `head.end2end == False`.
   - En Ultralytics `8.4.171`, `BasePredictor.setup_model` pasa `end2end=(self.args.nms is False)` a `AutoBackend`, mientras `cfg/default.yaml` fija `nms=None`. En consecuencia, **llamar a `model.predict()` sin `nms=False` (como hace hoy [yolo_detector.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py)) evalúa `nms is False -> False`, haciendo que `Detect.fuse()` elimine la rama `one2one_cv2` y degrade silenciosamente YOLO26x al modo tradicional `one2many + NMS`**.
   - Pasar explícitamente **`nms=False`** en `predict()` activa `AutoBackend.end2end = True`, poda `cv2` (`one2many`) y ejecuta el cabezal nativo NMS-Free `one2one`, reduciendo además la variabilidad (`std 0.603 ms` y `p99 19.144 ms` frente a `std 1.862 ms` y `p99 24.830 ms` con `nms=True`).
3. **Evaluación diagnóstica de dominio y alcance científico:**
   - En capturas multi-vehículo (`SCREEN_RECAPTURE`, `20261111`, `n=11`), `yolo26x` duplica prácticamente la capacidad de propuesta frente a `yolo11n` (`112` cajas a `640` y `128` a `800` vs `72` de `yolo11n`), elevando detecciones pequeñas (`<5%` del frame: `101` y `118` vs `65`).
   - En el subconjunto histórico borderline de `20261114/CAM-SALIDA` (`16` frames con confianza `<0.70` en `yolo11n`), `yolo26x 640 FP16 e2e` recupera `11/16 >= 0.70` (y `yolo26x nms=True` recupera `12/16`).
   - En el subconjunto extremo fuera de distribución (`SCALE_MODEL_LAB__DARK_Y_LT_40`, `n=33` tomas oscuras y desenfocadas de un auto a escala sobre teclado con `Y_mean < 40`, mín. `13.7`), la calibración conservadora de la rama `one2one` de `yolo26x` y `yolo11x` pierde frames frente a `yolo11n` (`25/33 >= 0.25` y `13/33 >= 0.70` en `yolo26x 640 FP16 e2e` vs `33/33` y `26/33` en `yolo11n`), lo que confirma dos reglas metodológicas clave:
     - **No declarar ganancia de `mAP` o `Recall` de carretera** sin validar en **`VIGIA-BENCH-REAL` (vehículos 1:1 con Ground Truth humano)**.
     - **Evaluar calibración de umbral** antes de heredar ciegamente `0.70` al desplegar cabezales `one2one`.

---

## 2. Estado Actual del Sistema y Entorno Experimental Aislado

### 2.1 Verificación de aislamiento sobre producción

No se modificó ningún archivo de código productivo ni artefacto operativo de VIGÍA. Los siguientes componentes permanecen íntegros y sin cambios:
- Motor de detección y runtime: [yolo_detector.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py), [roi_and_preprocess.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/roi_and_preprocess.py), [engine_settings.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/config/engine_settings.py), [temporal_state.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/runtime/temporal_state.py), [coordinator.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/runtime/coordinator.py), [ingest_service.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py).
- Pesos productivos (`yolo11n.pt`, SHA-256 `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`), entornos `.venv/` y `.venv_cuda/`, esquema PostgreSQL y corpus `evidencias_vigia/`.

### 2.2 Estructura creada en `experiments/yolo26x/`

| Ruta | Propósito |
|---|---|
| [README.md](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/README.md) | Documentación de aislamiento y comandos de reproducción. |
| [requirements_yolo26x.txt](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/requirements_yolo26x.txt) | Versiones exactas verificadas en `.venv_yolo26x`. |
| [yolo26x_eval.yaml](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/configs/yolo26x_eval.yaml) | Parámetros experimentales desacoplados. |
| [prepare_weights.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/scripts/prepare_weights.py) | Copia sin alteración de `yolo11n.pt`, descarga oficial de `yolo11x.pt` y `yolo26x.pt` e inspección de integridad. |
| [verify_yolo26x_contract.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/scripts/verify_yolo26x_contract.py) | Verificación de contrato VIGÍA, `end2end`, FP32/FP16 y multirresolución. |
| [run_yolo26x_benchmark.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/scripts/run_yolo26x_benchmark.py) | Benchmark GPU/VRAM/térmico, ablación NMS-Free, TTA y estrés de 200 iteraciones. |
| [evaluate_domains_yolo26x.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/scripts/evaluate_domains_yolo26x.py) | Evaluación diagnóstica por dominio sobre `20261111` (`n=11`) y `20261114` (`n=145`). |
| [test_yolo26x_contract.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/tests/test_yolo26x_contract.py) | Suite `unittest` aislada (`4/4` pruebas en verde). |
| [weights_manifest.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/results/weights_manifest.json) | Manifiesto estructural y criptográfico (SHA-256) de pesos. |
| [contract_verification.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/results/contract_verification.json) | Evidencia JSON de verificación de contrato y ramas `one2one` vs `one2many`. |
| [benchmark_matrix.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/results/benchmark_matrix.json) | Resultados crudos completos del benchmark GPU y estrés sostenido. |
| [domain_evaluation.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/results/domain_evaluation.json) | Métricas comparativas por dominio, cámara, luminancia y subconjunto borderline. |

El entorno `.venv_yolo26x` (`Python 3.11.1`) reutiliza limpiamente el runtime CUDA de `.venv_cuda` mediante `sitecustomize.py` sin duplicar binarios de PyTorch en disco ni modificar `.venv_cuda`.

---

## 3. Análisis Comparativo Arquitectónico: YOLO11n vs YOLO11x vs YOLO26x

Los datos estructurales de [weights_manifest.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/results/weights_manifest.json) y las especificaciones YAML inspeccionadas directamente en Ultralytics `8.4.171` muestran:

| Atributo | `yolo11n.pt` (Producción) | `yolo11x.pt` (Ref. Pesada) | `yolo26x.pt` (Objetivo) |
|---|---|---|---|
| Tamaño en disco | `5,613,764` bytes (`5.354 MB`) | `114,636,239` bytes (`109.326 MB`) | `118,667,365` bytes (`113.170 MB`) |
| SHA-256 | `0ebbc80d...17644ee1` | `7bc158aa...e773a24` | `9fdd44a3...c7003e92` |
| Parámetros sin fusionar | `2,624,080` (`319` módulos PyTorch) | `56,966,176` (`631` módulos PyTorch) | `58,993,368` (`687` módulos PyTorch) |
| Capas / GFLOPs YAML (`640`) | `181` capas / `6.6 GFLOPs` | `357` capas / `196.0 GFLOPs` | `392` capas / `209.5 GFLOPs` (fusionado: `188` capas, `55,725,948` params, `194.4 GFLOPs`) |
| `reg_max` / DFL | `16` (`DFL` activo) | `16` (`DFL` activo) | `1` (`nn.Identity()`, sin DFL) |
| Doble cabezal `one2one` | No (`has_one2one_head=False`) | No (`has_one2one_head=False`) | Sí (`one2one_cv2`, `one2one_cv3`) |
| Inferencia NMS-Free nativa | No (requiere `IoU NMS`) | No (requiere `IoU NMS`) | Sí, activada con `nms=False` (`end2end=True`) |
| Strides | `[8.0, 16.0, 32.0]` | `[8.0, 16.0, 32.0]` | `[8.0, 16.0, 32.0]` |
| Clases COCO (`nc=80`) | `{2: car, 3: motorcycle, 5: bus, 7: truck}` | `{2: car, 3: motorcycle, 5: bus, 7: truck}` | `{2: car, 3: motorcycle, 5: bus, 7: truck}` |

### 3.1 Diferencias arquitectónicas clave de YOLO26x relevantes para VIGÍA

1. **Eliminación de DFL (`reg_max = 1`, `dfl = nn.Identity()`):** Simplifica la regresión de cajas en el cabezal y reduce complejidad de grafo y latencia en inferencia CUDA (`17.87 ms` en `yolo26x` FP16 frente a `20.543 ms` en `yolo11x` FP16 pese a tener ~2M más de parámetros base sin fusionar).
2. **Doble cabezal `one2many` (`cv2`/`cv3`) + `one2one` (`one2one_cv2`/`one2one_cv3`):**
   - Permite entrenar y operar dualmente. En inferencia fusionada para producción NMS-Free (`nms=False`), `Detect.fuse()` descarta `cv2` y `cv3`, entregando directamente predicciones de cardinalidad uno-a-uno en formato `[B, max_det, 6]`.
   - En 15 frames reales de muestra evaluados en [contract_verification.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/results/contract_verification.json), `end2end=True` (`nms=False`) y `nms=True` (`one2many`) coincidieron en conteo en `12/15` frames y difirieron en `3/15`: en `20261114T010116_504289Z` y `20261114T010117_111651Z` de `CAM-SALIDA`, `nms=True` emitió una caja duplicada extra clase `bus` (`0.289` y `0.386`) sobre el mismo vehículo de fondo que `one2one` consolidó limpiamente como `car` + `truck`.
3. **Mecanismo exacto de activación de `end2end` en Ultralytics `8.4.171` (Riesgo Crítico Documentado):**
   Al inspeccionar `Detect.fuse()`, `BasePredictor.setup_model()` y `AutoBackend.__init__()`, se comprobó en [contract_verification.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/results/contract_verification.json) lo siguiente:
   - Al cargar `YOLO("yolo26x.pt")`, `ckpt_yaml_end2end = True`, pero `head_end2end_on_load = False` porque `Detect.__init__` construye `one2one_cv2` sin inicializar `self._end2end`. En forward crudo previo a `AutoBackend`, el modelo emite tuple `[1, 84, 8400]`.
   - Al llamar a `model.predict()` **sin pasar `nms=False`** (equivalente al código actual de [YoloVehicleDetector.detect](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py#L229)), `self.args.nms` es `None`, por lo que `BasePredictor.setup_model` envía `end2end=(self.args.nms is False) -> False`. Incluso forzando `model.model.end2end = True` manualmente antes de `predict()`, `AutoBackend` sobreescribe `end2end=False` y `Detect.fuse()` **borra `one2one_cv2`** (`one2one_pruned_is_none = True`), ejecutando la rama tradicional `one2many + NMS`.
   - Solo al pasar **`nms=False`** explícitamente en `predict()`, `AutoBackend.end2end` resulta `True` (`cv2_pruned_is_none = True`, `one2one_cv2_present = True`).
   - Adicionalmente, en Ultralytics `8.4.171`, `half=True` emite advertencia de deprecación en favor de **`quantize=16`** (ambos activan `ab.fp16 = True` con pesos `torch.float16`), y **`augment=True` (TTA) no es compatible con `nms=False` (`end2end=True`)**, emitiendo `"Model does not support 'augment=True', reverting to single-scale prediction."`.

---

## 4. Verificación de Compatibilidad con el Contrato Productivo de VIGÍA

Mediante [verify_yolo26x_contract.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/scripts/verify_yolo26x_contract.py) y las pruebas unitarias en [test_yolo26x_contract.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/tests/test_yolo26x_contract.py) se verificaron sin modificar el código productivo:

1. **Inferencia CUDA multirresolución FP32 y FP16 (`quantize=16`):**
   - Ejecución limpia sobre JPEG reales (`640x480` de `CAM-SALIDA` y `720x1280` de `CAM-ENTRADA`) y tensores reescalados (`1280x720`, `1920x1080`) preservando `orig_shape`, coordenadas `xyxy`, `conf` y `cls`.
   - Paridad numérica FP32 vs FP16 en [contract_verification.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/results/contract_verification.json): p. ej. en `real_jpeg_640x480` (`car 0.9311` FP32 vs `0.9312` FP16) y en `real_jpeg_720x1280` (`car 0.9267` FP32 vs `0.9268` FP16).
2. **Integración completa de tipos y pipeline VIGÍA (`vigia_contract_integration_smoke`):**
   - `YoloVehicleDetector` instanciado con `YoloDetectorConfig(model_path=...yolo26x.pt, device="cuda:0")` emite `RawVehicleDetection` y `BoundingBox` válidos (`raw_detections_count = 2`).
   - `filter_detections_by_roi` filtra correctamente dentro del ROI (`in_roi_count = 1`, `excluded_outside_roi = 0`).
   - `map_raw_label_to_domain_vehicle_type("car")` retorna `"AUTOMOVIL"`.
   - `VisionResult` y `CameraTemporalStateTracker.update(...)` procesan la salida deterministamente (`VEHICLE_CANDIDATE` tras 1 frame y `VEHICLE_PRESENT` tras 2 frames confirmados).
   - Se confirmó también el aviso de compatibilidad: usando `YoloVehicleDetector` sin cambios (`nms` omitido), `yolo_detector_default_end2end_active` queda en `False`, validando la necesidad de extender `YoloDetectorConfig` en `VISION-03C.2`.
3. **Resultado de pruebas unitarias aisladas:**
   ```text
   Ran 4 tests in 3.660s — OK (0 errores, 0 omitidas)
   ```

---

## 5. Benchmark Comparativo GPU, VRAM, CPU, Temperatura y Estabilidad

Ejecutado con [run_yolo26x_benchmark.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/scripts/run_yolo26x_benchmark.py) sobre frames reales de `20261114` (5 iteraciones de warm-up + 30 iteraciones sincronizadas CUDA por celda, `batch=1`). Fuente: [benchmark_matrix.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/results/benchmark_matrix.json).

### 5.1 Matriz comparativa `yolo11n` vs `yolo11x` vs `yolo26x` (`640`, `800`, `960` × `FP32`/`FP16`)

| Modelo | `imgsz` | Precisión | `end2end` | Mean (ms) | p50 (ms) | p95 (ms) | p99 (ms) | FPS medio | VRAM PyTorch Pico (MB) | NVML GPU Total (MB) | GPU Util (%) | Temp Máx (°C) | CPU Proc (%) |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `yolo11n` | 640 | FP32 | `False` | `9.213` | `9.209` | `10.100` | `10.563` | `108.54` | `68.45` | `1460.07` | `12.4` | `47.0` | `105.7` |
| `yolo11n` | 640 | FP16 | `False` | `10.123` | `9.944` | `11.468` | `12.676` | `98.78` | `45.86` | `1444.07` | `20.4` | `47.0` | `99.8` |
| `yolo11n` | 800 | FP32 | `False` | `9.852` | `9.751` | `11.134` | `12.449` | `101.51` | `90.52` | `1504.07` | `26.4` | `48.0` | `100.0` |
| `yolo11n` | 800 | FP16 | `False` | `11.243` | `11.093` | `12.835` | `13.222` | `88.94` | `51.00` | `1444.82` | `19.6` | `48.0` | `95.7` |
| `yolo11n` | 960 | FP32 | `False` | `9.999` | `9.894` | `11.103` | `12.078` | `100.01` | `82.60` | `1478.82` | `31.3` | `49.0` | `179.5` |
| `yolo11n` | 960 | FP16 | `False` | `10.498` | `10.461` | `11.310` | `11.377` | `95.26` | `57.44` | `1464.82` | `19.1` | `49.0` | `99.8` |
| `yolo11x` | 640 | FP32 | `False` | `27.192` | `27.129` | `29.128` | `29.464` | `36.78` | `381.26` | `1938.82` | `78.4` | `56.0` | `94.7` |
| `yolo11x` | 640 | FP16 | `False` | `20.543` | `20.114` | `23.884` | `26.597` | `48.68` | `257.89` | `1682.45` | `68.6` | `58.0` | `95.3` |
| `yolo11x` | 800 | FP32 | `False` | `42.532` | `45.080` | `46.391` | `46.703` | `23.51` | `413.17` | `1953.39` | `90.0` | `60.0` | `98.8` |
| `yolo11x` | 800 | FP16 | `False` | `25.812` | `26.436` | `27.869` | `27.951` | `38.74` | `255.23` | `1764.64` | `82.0` | `61.0` | `101.9` |
| `yolo11x` | 960 | FP32 | `False` | `55.760` | `59.810` | `61.546` | `61.969` | `17.93` | `488.06` | `2064.70` | `90.4` | `62.0` | `100.0` |
| `yolo11x` | 960 | FP16 | `False` | `34.477` | `36.331` | `38.749` | `38.866` | `29.00` | `259.46` | `1796.89` | `79.6` | `62.0` | `94.3` |
| **`yolo26x`** | **640** | **FP32** | **`True`** | **`26.434`** | **`27.047`** | **`28.311`** | **`28.399`** | **`37.83`** | **`375.05`** | **`1964.82`** | **`88.9`** | **`62.0`** | **`99.9`** |
| **`yolo26x`** | **640** | **FP16** | **`True`** | **`17.870`** | **`17.469`** | **`20.726`** | **`21.390`** | **`55.96`** | **`251.76`** | **`1680.76`** | **`66.0`** | **`62.0`** | **`118.9`** |
| **`yolo26x`** | **800** | **FP32** | **`True`** | **`40.269`** | **`41.892`** | **`44.076`** | **`44.633`** | **`24.83`** | **`409.65`** | **`1948.76`** | **`91.9`** | **`63.0`** | **`100.0`** |
| **`yolo26x`** | **800** | **FP16** | **`True`** | **`24.596`** | **`25.418`** | **`26.275`** | **`26.416`** | **`40.66`** | **`251.76`** | **`1760.76`** | **`76.3`** | **`65.0`** | **`96.0`** |
| **`yolo26x`** | **960** | **FP32** | **`True`** | **`55.220`** | **`59.856`** | **`60.792`** | **`61.361`** | **`18.11`** | **`482.77`** | **`2068.76`** | **`94.4`** | **`65.0`** | **`99.1`** |
| **`yolo26x`** | **960** | **FP16** | **`True`** | **`33.210`** | **`35.454`** | **`36.392`** | **`36.536`** | **`30.11`** | **`257.92`** | **`1794.76`** | **`77.9`** | **`66.0`** | **`98.4`** |

### 5.2 Ablación `NMS-Free (nms=False)` vs `NMS tradicional (nms=True)` y Sonda TTA (`640` FP16)

| Variante `yolo26x` (`640` FP16) | `end2end` activo | `tta` | Mean (ms) | Std (ms) | p50 (ms) | p95 (ms) | p99 (ms) | FPS medio | Observación |
|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| `yolo26x_e2e_true_nms_false` | `True` | `False` | `17.836` | `0.603` | `17.716` | `18.804` | `19.144` | `56.07` | Desv. estándar 3.09× menor; cola `p99` `-5.69 ms`. |
| `yolo26x_e2e_false_nms_true` | `False` | `False` | `18.377` | `1.862` | `18.053` | `19.913` | `24.830` | `54.42` | Post-proceso `IoU NMS` introduce jitter en `p99`. |
| `yolo26x_e2e_true_tta` | `True` | `True` | `19.579` | `1.105` | `19.517` | `21.161` | `21.404` | `51.08` | Ultralytics advierte y revierte a single-scale automáticamente. |
| `yolo26x_one2many_nms_tta` | `False` | `True` | `49.267` | `3.798` | `49.377` | `55.011` | `58.143` | `20.30` | TTA multi-escala real multiplica latencia **2.68×** (no apto por defecto). |

### 5.3 Prueba sostenida de 200 iteraciones (`yolo26x`, `imgsz=640`, `nms=False`)

| Métrica de estabilidad (`200` iters) | `FP16` (`quantize=16`) | `FP32` |
|---|---:|---:|
| Errores CUDA | **`0`** | **`0`** |
| Media / p50 / p95 / p99 | `18.006` / `17.904` / `20.133` / `23.917 ms` | `26.399` / `26.915` / `28.107` / `28.419 ms` |
| Throughput promedio | **`55.54 FPS`** | **`37.88 FPS`** |
| Primera mitad vs segunda mitad (`1..100` vs `101..200`) | `17.487` vs `18.525 ms` (`+1.038 ms`) | `26.405` vs `26.393 ms` (`-0.012 ms`) |
| VRAM PyTorch inicio / fin / fuga neta | `140.63` / `140.62` / **`-0.01 MB`** | `248.18` / `248.16` / **`-0.01 MB`** |
| VRAM PyTorch pico asignada | **`251.76 MB`** | **`375.05 MB`** |
| Temperatura GPU inicio / pico / fin | `61.0°C` / **`66.0°C`** / `65.0°C` | `64.0°C` / **`68.0°C`** / `67.0°C` |
| Consumo eléctrico al cierre / CPU proceso | `67.30 W` / `112.1%` | `68.94 W` / `100.0%` |

---

## 6. Evaluación Diagnóstica sobre el Corpus Histórico por Dominio

Mediante [evaluate_domains_yolo26x.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/scripts/evaluate_domains_yolo26x.py) se evaluaron los `156` fotogramas `*_orig.jpg` completos de las jornadas `20261111` y `20261114` indexados en [manifest_v1.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/data/processed/manifest_v1.json), manteniendo separación estricta por dominio de origen (`source_domain`). Fuente de cifras: [domain_evaluation.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/results/domain_evaluation.json).

### 6.1 Dominio A — `SCREEN_RECAPTURE` (`20261111`, `CAM-ENTRADA`, `n=11`)

Escenas de tránsito urbano con múltiples vehículos capturadas desde pantalla/monitor (`720x1280`):

| Configuración | Frames `>=0.25` | Frames `>=0.70` | Cajas totales | Cajas pequeñas (`<5%`) | Cajas borde | Distribución clases totales | Conf. Top-1 media / mín / máx |
|---|---:|---:|---:|---:|---:|---|---|
| `yolo11n 640 FP32` | `11/11` | `11/11` | `72` | `65` | `15` | `car: 68, motorcycle: 4` | `0.8669` / `0.8150` / `0.9194` |
| `yolo11x 640 FP16` | `11/11` | `11/11` | `115` | `107` | `28` | `car: 101, truck: 7, motorcycle: 7` | `0.9105` / `0.8457` / `0.9434` |
| `yolo26x 640 FP32 e2e` | `11/11` | `11/11` | `112` | `101` | `25` | `car: 103, motorcycle: 4, truck: 5` | `0.8914` / `0.7190` / `0.9526` |
| `yolo26x 640 FP16 e2e` | `11/11` | `11/11` | `112` | `101` | `25` | `car: 103, motorcycle: 4, truck: 5` | `0.8915` / `0.7202` / `0.9526` |
| `yolo26x 800 FP16 e2e` | `11/11` | `11/11` | **`128`** | **`118`** | `29` | `car: 114, motorcycle: 4, truck: 9, bus: 1` | `0.8874` / `0.8457` / `0.9385` |
| `yolo26x 640 FP16 nms` | `11/11` | `11/11` | `119` | `108` | `26` | `car: 108, motorcycle: 5, truck: 6` | `0.9039` / `0.8765` / `0.9268` |

**Lectura técnica:** En escenas viales multi-objeto, `yolo26x` (`640`) detecta **`+55.6%`** más instancias vehiculares que `yolo11n` (`112` vs `72`), y a `800` alcanza **`+77.8%`** (`128` vs `72`), concentrado precisamente en vehículos pequeños (`101` y `118` vs `65`). Paridad `FP32` vs `FP16` exacta en conteo (`112` cajas idénticas).

### 6.2 Dominio B — `SCALE_MODEL_LAB` (`20261114`, `n=145`: `CAM-ENTRADA n=15` + `CAM-SALIDA n=130`)

Este dominio corresponde a **maquetas a escala en laboratorio** (auto deportivo rojo, auto guinda, autobús escolar amarillo y fondos de escritorio/teclado oscuro — fuerte cambio de distribución frente a COCO):

| Configuración | All `20261114` (`n=145`) `>=0.25 / >=0.50 / >=0.70` | `CAM-ENTRADA` (`n=15`) `>=0.70` / Top-1 media | `CAM-SALIDA` (`n=130`) `>=0.25 / >=0.70` | `DARK Y<40` (`n=33`) `>=0.25 / >=0.70` | Subconjunto `16` Borderline (`<0.70` en `yolo11n`) `>=0.70 / >=0.25` | Clases totales `CAM-SALIDA` (`car / truck / bus`) |
|---|---|---|---|---|---|---|
| `yolo11n 640 FP32` | `145 / 144 / 129` | `15/15` (`0.8633`) | `130 / 114` | `33 / 26` | `0 / 16` | `132 / 35 / 27` |
| `yolo11x 640 FP16` | `140 / 133 / 112` | `15/15` (`0.9246`) | `125 / 97` | `30 / 30` | `10 / 14` | `132 / 62 / 4` |
| `yolo26x 640 FP32 e2e` | `136 / 127 / 111` | `15/15` (`0.9123`) | `121 / 96` | `24 / 13` | `11 / 14` | `142 / 31 / 32` |
| `yolo26x 640 FP16 e2e` | `137 / 127 / 110` | `15/15` (`0.9125`) | `122 / 95` | `25 / 13` | `11 / 14` | `142 / 31 / 32` |
| `yolo26x 800 FP16 e2e` | `135 / 125 / 107` | `11/15` (`0.7586`) | `120 / 96` | `23 / 16` | `10 / 11` | `135 / 34 / 31` |
| `yolo26x 640 FP16 nms` | `139 / 133 / 123` | `15/15` (`0.9084`) | `124 / 108` | `28 / 19` | `12 / 14` | `140 / 25 / 31` |

### 6.3 Hallazgos críticos revelados por el diagnóstico de dominio

1. **Recuperación en frames borderline iluminados y `CAM-ENTRADA`:**
   - En `CAM-ENTRADA` (`n=15`), `yolo26x 640 FP16 e2e` eleva la confianza media de `0.8633` (`yolo11n`) a **`0.9125`** (p. ej. `20261114T004711_021481Z`: `0.7134 -> 0.9331`).
   - En el subconjunto histórico de `16` frames borderline (`<0.70` en `yolo11n`), `yolo26x 640 FP16 e2e` recupera **`11/16`** por encima de `0.70` (hasta `0.9634`), incluyendo escenas de escritorio como `20261114T005626_093189Z` (`0.6359 -> 0.9634`) y `20261114T005629_603216Z` (`0.5921 -> 0.9419`).
2. **Conservación de distinción `bus` vs `truck` frente a `yolo11x`:**
   - `yolo11x` colapsa casi por completo `bus` hacia `truck` en `20261114/CAM-SALIDA` (`top1 bus: 0`, `all bus: 4`, `all truck: 62`).
   - `yolo26x 640 FP16 e2e` preserva la clase `bus` (`top1 bus: 11`, `all bus: 32`, `all truck: 31`).
3. **Sensibilidad OOD en escenas macro ultra-oscuras (`Y < 40`) y calibración `one2one`:**
   - En las `33` tomas `DARK_Y_LT_40` (`CAM-SALIDA`, auto de juguete sobre teclado mecánico negro, `Y_mean` entre `13.7` y `38.8`, nitidez laplaciana `2.0–4.4`), `yolo26x 640 FP16 e2e` cae a `25/33 >= 0.25` y `13/33 >= 0.70`, omitiendo `8` frames con `Y_mean` entre `13.7` y `21.7` (donde `yolo11n` sí disparó `car`).
   - Asimismo, `yolo26x` con `nms=True` (`one2many`) obtiene `139/145 >= 0.25` y `123/145 >= 0.70` en `20261114` frente a `137/145` y `110/145` con `nms=False` (`one2one`), mostrando que el cabezal `one2one` NMS-Free produce confianzas ligeramente más estrictas cuando las señales texturales son ambiguas o muy subexpuestas.
   - Nota adicional sobre `imgsz=800` en `20261114`: al escalar maquetas macro cercanas (`CAM-ENTRADA n=15`), `800` baja la confianza media de `0.9125` (`640`) a `0.7586` porque el objeto macro ocupa una proporción inusualmente grande respecto a la escala de entrenamiento COCO; en cambio en objetos pequeños (`SCREEN_RECAPTURE`), `800` sube las detecciones totales de `112` a `128`.

---

## 7. Limitaciones Metodológicas Vigentes

1. **Ausencia de Ground Truth humano real:** Ni `20261111` (`SCREEN_RECAPTURE`) ni `20261114` (`SCALE_MODEL_LAB`) cuentan con etiquetas manuales humanas de caseta vial real (`VIGIA-BENCH-REAL` v1 se encuentra pendiente de captura según `VIGIA-VISION-03B.1`). Todo conteo de detecciones en este documento representa **capacidad de propuesta comparativa bajo desplazamiento de dominio**, nunca `mAP@0.5`, `mAP@0.5:0.95` ni tasa oficial de falsos positivos en carretera.
2. **Interacción con el umbral productivo `0.70`:** El umbral actual `vehicle_confidence_threshold = 0.70` de [engine_settings.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/config/engine_settings.py) fue calibrado para `yolo11n`. En `YOLO26x` `one2one`, el salto de `0.70` a `0.50` cambia la cobertura en `20261114` de `110/145` a `127/145`; por ello la calibración final del umbral deberá fijarse tras evaluar sobre `VIGIA-BENCH-REAL` 1:1.

---

## 8. Matriz de Riesgos Operativos y Mitigaciones

| Riesgo | Impacto | Probabilidad | Mitigación en `VISION-03C.2` |
|---|---|---|---|
| Ejecutar `yolo26x.pt` sin `nms=False` | Alto (poda `one2one` silenciosamente y corre `one2many + NMS`) | Alta si no se parametriza | Añadir `nms: Optional[bool]` a `YoloDetectorConfig` y validar/registrar `effective_end2end` en arranque. |
| Umbral `0.70` demasiado estricto para rama `one2one` en escenas nocturnas/difíciles | Medio (posible sub-detección en `Y_mean` muy bajo) | Media | Mantener `0.70` configurable y permitir validar `0.50–0.65` sobre `VIGIA-BENCH-REAL` antes del corte definitivo. |
| Deprecación futura de `half=True` en Ultralytics | Bajo | Baja/Media | Soportar `quantize: Optional[int]` (`16`/`32`) en `YoloDetectorConfig` alineado a Ultralytics `8.4+`. |
| Uso accidental de `augment=True` (TTA) | Medio/Alto (degrada throughput `2.68×` en `one2many` o se ignora en `e2e`) | Baja | No exponer TTA por defecto en captura continua. |
| Regresión tras migración de pesos | Alto | Baja | Rollback instantáneo cambiando variable de entorno `VIGIA_YOLO_WEIGHTS=yolo11n.pt` sin cambios de código. |

---

## 9. Criterios de Decisión (Sección 11 del Mandato)

| Criterio de evaluación | Resultado medido | Veredicto |
|---|---|---|
| Ejecución estable en NVIDIA RTX 4050 6 GB (`0` errores CUDA) | `200/200` iters FP16 y `200/200` iters FP32 con `0` errores | **CUMPLE** |
| Latencia aceptable en tiempo real (`<= 50 ms` p95 objetivo dual-cámara) | `640` FP16: `17.87 ms` media (`p95 20.73 ms`, `55.96 FPS`); `800` FP16: `24.60 ms` (`p95 26.28 ms`, `40.66 FPS`) | **CUMPLE HOLGADAMENTE** |
| Consumo seguro de VRAM (`< 4.0 GB` NVML en GPU 6 GB) | PyTorch pico `251.76 MB`; NVML total `1.68 GB` (`640` FP16) / `1.76 GB` (`800` FP16) | **CUMPLE HOLGADAMENTE** |
| Compatibilidad con contratos `RawVehicleDetection` -> `VisionResult` -> `FSM` | `4/4` pruebas unitarias + humo integral con contratos actuales | **CUMPLE (con extensión `nms`/`quantize` en `03C.2`)** |
| Integración limpia y reversible en arquitectura VIGÍA | Parametrización por `YoloDetectorConfig` + `.env` (`yolo11n.pt` intacto como respaldo) | **CUMPLE** |
| Validación de mejora de precisión/recall real en exteriores | `20261111` muestra `+55.6%/+77.8%` propuestas pequeñas; `20261114` oscuro revela sensibilidad OOD | **CONDICIONADO A `VIGIA-BENCH-REAL` PARA REEMPLAZO PRODUCTIVO FINAL** |

---

## 10. Diseño Propuesto para `VISION-03C.2` (Sin Implementar Todavía)

Para habilitar la incorporación experimental/configurable de `yolo26x.pt` en el motor principal preservando retrocompatibilidad absoluta con `yolo11n.pt`:

1. **Extensión de [yolo_detector.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py) (`YoloDetectorConfig`):**
   - Mantener `model_path="yolo11n.pt"` como valor por defecto seguro hasta validar en `VIGIA-BENCH-REAL`.
   - Agregar parámetros opcionales validados:
     - `quantize: Optional[int] = None` (acepta `None`, `16` para FP16, `32` para FP32; solo pasa `"quantize": 16` en CUDA cuando corresponda).
     - `nms: Optional[bool] = None` (cuando sea `False`, activa el cabezal nativo `one2one` `end2end=True` en YOLO26x; si `None`, preserva el comportamiento actual).
   - Exponer propiedad de diagnóstico read-only en `YoloVehicleDetector` para auditar tras el primer `predict()` el estado efectivo de `predictor.model.end2end` y `fp16`.
2. **Cableado en [ingest_service.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py) y configuración externa (`.env`):**
   - Leer variables opcionales sin romper despliegues existentes:
     - `VIGIA_YOLO_WEIGHTS` (ya existente, default `yolo11n.pt`).
     - `VIGIA_YOLO_IMGSZ` (default `640`).
     - `VIGIA_YOLO_QUANTIZE` (`16` recomendado al usar `yolo26x.pt` en CUDA).
     - `VIGIA_YOLO_NMS` (`false` obligatorio al usar `yolo26x.pt` para activar `end2end=True` NMS-Free).
3. **Configuración recomendada para perfil piloto YOLO26x (`VISION-03C.2`):**
   - `model_path = yolo26x.pt`, `device = cuda:0`, `imgsz = 640` (alternativa `800` si `VIGIA-BENCH-REAL` requiere mayor alcance en vehículos lejanos), `quantize = 16` (FP16), `nms = False` (NMS-Free `end2end=True`), `augment = False`.
4. **Criterio de promoción a producción definitiva:**
   - Mantener `yolo11n.pt` como fallback inmediato.
   - Tras ejecutar `VISION-03C.2` en modo configurable/piloto, correr la batería comparativa A/B (`yolo11n` vs `yolo26x 640 FP16 e2e` vs `yolo26x 800 FP16 e2e`) sobre las capturas reales de `VIGIA-BENCH-REAL` para confirmar precisión, recall y calibrar el umbral final de ROI.

---

## 11. Solicitud de Autorización

La fase **`VISION-03C.1`** queda concluida y documentada con evidencia empírica completa, sin haber tocado ningún archivo de producción. Se solicita autorización explícita para proceder con la fase **`VISION-03C.2` (Integración configurable de YOLO26x en `YoloDetectorConfig` / `YoloVehicleDetector` / `ingest_service.py` y verificación unitaria e integrada en entorno principal)**.
