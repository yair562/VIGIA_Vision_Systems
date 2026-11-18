# VIGIA-VISION-07B — Evaluación Integral de Detección Vehicular (YOLO26x) y Clasificación de Color

**Proyecto:** VIGÍA Vision Systems  
**Fase:** VISION-07B (Evaluación Integral Read-Only y Preparación para LPR/ANPR)  
**Fecha de auditoría:** 2026-11-16 / 2026-11-17 UTC  
**Entorno productivo auditado:** `VIGIA_API.ingest_service` (`https://0.0.0.0:5001`) sobre NVIDIA GeForce RTX 4050 Laptop GPU (6 GB VRAM, `cuda:0`)  
**Modelo de detección efectivo:** `experiments/yolo26x/weights/yolo26x.pt` (FP16, NMS-Free `end2end`, EXP-10 `frontal_aux_imgsz=384`)  
**Modelo fallback configurado:** `yolo11n.pt` (sin activaciones registradas: `fallback_count = 0`)  
**Artefactos JSON generados (no destructivos):**
- `experiments/vision_07b/results/fase_e_live_snapshot.json`
- `experiments/vision_07b/results/vision_07b_evaluation_results.json`
- Scripts reproducibles: `experiments/vision_07b/scripts/capture_fase_e_snapshot.py` y `experiments/vision_07b/scripts/evaluate_vision_07b.py`

**Dictamen Oficial:** **`APPROVED WITH OBSERVATIONS — INCOMPLETE GROUND TRUTH`**

---

## 1. Resumen ejecutivo

La fase **VISION-07B** ejecutó una auditoría técnica estática, de runtime en vivo (estrictamente solo-lectura) y de evaluación offline sobre el pipeline de visión computacional de **VIGÍA Vision Systems**, manteniendo intactos el servicio productivo (`VIGIA_API.ingest_service`), `.env` (SHA-256 verificado antes y después: `144055B9C5257B07798C68C2793A91DC7235915FE3AC5155178202E507A05C96`), pesos, umbrales, cámaras físicas y esquema PostgreSQL.

### Hallazgos clave

1. **Detección vehicular (`YOLO26x` + EXP-10 + filtro ROI >= `0.70`):**
   - Sobre las **279 imágenes únicas** del corpus histórico catalogado (`etapa_a_b_classified_inventory.json`, `evidencias_vigia/20261101..20261116`), YOLO26x logró una **tasa de presencia vehicular** del **86.38 %** (`241/279`) al umbral operativo `0.70` y del **96.77 %** (`270/279`) al umbral candidato `0.25`.
   - En autobuses escolares Tipo C vistos frontalmente (`0°`, *n* = 18), la tasa de presencia alcanzó **94.44 %** (`17/18`) a `>= 0.70` y **100.0 %** (`18/18`) a `>= 0.25`, pero persistió la confusión semántica de COCO entre `bus`, `truck` y `car` (`0` predicciones `bus`, `4` `truck`, `13` `car` cuando coexiste con auto frontal o se clasifica el morro como automóvil, `1` perdido a `0.70`).
   - En capturas físicas operativas recientes **sin anotación bbox** (`20261117`, evaluación no equiparable a Precision/Recall formal), `CAM-SALIDA` (`720x1280`, *n* = 303) registró detección en **100.0 %** de frames (296/303 multi-vehículo) con latencia media **35.79 ms**; la muestra estratificada de `CAM-ENTRADA` (`640x480`, *n* = 375 de 2,108 archivos en disco) registró **92.8 %** de frames con vehículo en ROI (`282/375` multi-vehículo) y latencia media **40.92 ms**.

2. **Divergencia crítica entre dos implementaciones del clasificador de color:**
   - Se detectaron **dos módulos distintos** en el repositorio: el clasificador realmente instanciado por `VisionEngineCoordinator` en producción (`VIGIA_Vision/detection/color_classifier.py`) y el módulo separado que fue evaluado en el benchmark VISION-05B (`VIGIA_Vision/classification/color_classifier.py`).
   - Re-evaluado sobre los exactamente mismos **185 registros ROI con Ground Truth de VISION-05B**, el clasificador real de **producción** superó al módulo de benchmark: **78.38 %** de concordancia absoluta (`145/185`), **86.83 %** excluyendo `UNKNOWN` y **9.73 %** de abstención (`18/185`), frente a **76.76 %** (`142/185`), **86.06 %** y **10.81 %** (`20/185`) en el módulo VISION-05B, con ganancia marcada en alto contraste/glare (**100.0 %**, *n* = 25) y baja iluminación (**27.78 %** vs **5.56 %**), aunque con menor precisión en vehículos color rosa (`OTHER`: **48.15 %** vs **66.67 %** excluyendo collages de pantalla) al confundir rosa pastel con `RED` o `UNKNOWN`.
   - En la suite sintética calibrada sobre **las 12 categorías cromáticas** (36 casos), producción obtuvo **88.89 %** absoluto y **96.67 %** excluyendo `UNKNOWN` (**16.67 %** `UNKNOWN`), frente a **86.11 %** y **90.32 %** del módulo benchmark.

3. **Integridad vehículo-color, arquitectura multi-vehículo y brecha de persistencia:**
   - A nivel de unidad (`VehicleColorClassifier.classify`), el aislamiento por bounding box es **estricto (100 %)**: alterar píxeles fuera del bbox a verde puro `(0,255,0)` produjo resultados bit a bit idénticos en todos los vehículos de escenas reales multi-vehículo (`4/4` escenarios, incluyendo escenas de 3 vehículos simultáneos). En concurrencia dual-cámara aislada dentro de `VisionEngineCoordinator`, `CAM-ENTRADA` y `CAM-SALIDA` operaron con **0 % de contaminación cruzada**.
   - **Brechas estructurales detectadas:** (a) `VisionEngineCoordinator` solo clasifica `detections_in_roi[0]` (el vehículo primario), ignorando los vehículos secundarios (`[1..N]`); (b) la tabla PostgreSQL `deteccion` y `DetectionInsertDTO` **no persisten** `color_detectado` ni `confianza_color`; y (c) `/api/v1/supervision/status` y `/api/v1/cameras/<c>/status` no exponen el color predicho ni las métricas de `color_classifier`.

4. **Brecha de Ground Truth y viabilidad LPR (VISION-08):**
   - No existen anotaciones manuales de bounding box `[x1, y1, x2, y2]` en píxeles (`manifest_v1.json` = 604 `UNANNOTATED`; `benchmarks/vigia_bench_v1/manifest_v1_seed.json` = 150 `PENDING_HUMAN_REVIEW`), imposibilitando calcular `AP`, `mAP@0.5` o `mAP@0.5:0.95`. Además, solo 4–5 de las 12 categorías de color poseen vehículos físicos reales en disco (`WHITE`, `BLACK`, `SILVER`, `GREEN`, `BROWN`, `ORANGE` carecen de corpus físico real dedicado).
   - **LPR/ANPR preliminar:** las capturas actuales (`CAM-ENTRADA 640x480`, ancho estimado de placa p50 = **17.5 px**, 0.0 % `>= 80 px`; `CAM-SALIDA 720x1280`, ancho estimado p50 = **46.9 px**, 0.11 % `>= 80 px`) corresponden principalmente a modelos a escala / escritorio sin placas reales legibles y óptica VGA en entrada, por lo que requieren actualización de resolución/óptica (`>= 1080p`) antes de activar LPR en campo, aun cuando la integración modular del pipeline está lista para recibir un módulo LPR independiente.

---

## 2. Arquitectura actual inspeccionada (FASE A)

La auditoría línea por línea sobre el código real arrojó respuestas exactas a las 8 preguntas de verificación (FASE A):

| # | Aspecto verificado | Comportamiento exacto en código real | Referencia de código |
|---|---|---|---|
| 1 | **Obtención del bounding box vehicular** | `YoloVehicleDetector.detect(frame_bgr, camera_code)` ejecuta Ultralytics (`yolo26x.pt`, clases COCO `{2: car, 3: motorcycle, 5: bus, 7: truck}`, `imgsz=640`, `quantize=16`, `nms=False`, deduplicación IoU `0.55`, sonda auxiliar EXP-10 `imgsz=384` si max conf < `0.70`) y entrega tuplas `RawVehicleDetection(bbox=BoundingBox(x_min, y_min, x_max, y_max), confidence, raw_label)`. Luego `VisionEngineCoordinator` llama `filter_detections_by_roi(detections, roi, min_confidence=0.70)`, que valida que el centroide del bbox esté dentro de `PixelROI` (`[0.1..0.9, 0.2..0.8]`) y ordena descendentemente por `(confidence, bbox.area)`. | `VIGIA_Vision/detection/yolo_detector.py`, `VIGIA_Vision/detection/roi_and_preprocess.py`, `VIGIA_Vision/runtime/coordinator.py` |
| 2 | **Generación del ROI para el clasificador de color** | `VehicleColorClassifier.classify(frame, bbox, ...)` recorta la subimagen exacta `crop = frame[y1:y2, x1:x2]` limitada al borde de imagen (sin margen externo). Exige ancho `>= 28 px`, alto `>= 28 px`, área `>= 900 px²` y `detection_confidence >= 0.25`. Redimensiona proporcionalmente si el lado mayor excede `max_working_dim = 160`. | `VIGIA_Vision/detection/color_classifier.py` (líneas 129–146, 300+) |
| 3 | **Regiones de la carrocería analizadas** | `_build_anatomical_body_mask()` aplica recortes anatómicos dependientes de clase vehicular: para pesados (`AUTOBUS`, `BUS`, `CAMION`, `TRUCK`) usa `yn=[0.16..0.80]`, `xn=[0.10..0.90]` excluyendo zona de ventana `[0.18..0.50] x [0.16..0.84]`; para `MOTO` usa `yn=[0.22..0.72]`, `xn=[0.18..0.82]`; para `AUTOMOVIL`/default usa `yn=[0.26..0.82]`, `xn=[0.10..0.90]` excluyendo ventana/parabrisas `[0.24..0.44] x [0.20..0.80]`. | `VIGIA_Vision/detection/color_classifier.py` (líneas 420–470) |
| 4 | **Exclusión de cristales, neumáticos, fondo, sombras y reflejos** | Excluye franja inferior (`yn > 0.80/0.82`) y techo/cielo (`yn < 0.16/0.26`) por máscara anatómica; descarta cristales mediante `(V < 75 & S < 52) | (V >= 220 & S < 22)`; elimina reflejos especulares (`V >= 250 & S <= 16 & min_bgr >= 245`, abortando a `OVEREXPOSED_GLARE` si ratio `> 0.65`) y sombras profundas (`V < 24 & L < 22`). Si un anillo perimetral interno difiere del núcleo (`delta_core_bg > 15.0`), resta fondo perimetral de asfalto/entorno. `VehicleColorNormalizer` aplica desplazamiento acotado `[-5, 5]` en canales Lab usando píxeles neutros. | `VIGIA_Vision/detection/color_classifier.py` |
| 5 | **Cálculo y representación de confianza cromática** | Calcula puntaje ponderado heurístico `(0.65 * purity_factor + 0.35 * margin_factor) * region_factor * (1 - glare_penalty) * (1 - blur_penalty)` acotado a `[0.0, 0.98]`, encapsulado en `VehicleColorResult(predominant_color, confidence, status, quality, secondary_color, runner_up_margin, category_scores, dominant_lab, dominant_hsv, processing_time_ms)`. En `VisionResult` se propaga únicamente `vehicle_color_pred: Optional[str]` y `vehicle_color_confidence: Optional[float]`. | `VIGIA_Vision/detection/color_classifier.py` (líneas 860–894), `VIGIA_Core/domain/vision_result.py` |
| 6 | **Asociación entre color e identificador de detección** | En memoria dentro de `process_camera_step()`, el color del primario se inserta en `VisionResult` y en `VisionObservationEnvelope.vehicle_color_result`. **Sin embargo**, `DetectionInsertDTO` y `_INSERT_SQL` en `PsycopgDetectionRepository` **no incluyen columnas de color**, y `evidencias_vigia/*_annot.jpg` (`render_annotated_frame`) tampoco dibuja etiquetas de color. No existe relación 1:1 vehículo-color persistida en PostgreSQL. | `VIGIA_Vision/runtime/coordinator.py`, `VIGIA_Core/repository/detection_repository.py`, `VIGIA_Vision/runtime/evidence_storage.py` |
| 7 | **Comportamiento con múltiples vehículos en un mismo frame** | `VisionEngineCoordinator` extrae `primary = detections_in_roi[0]` y **únicamente llama a `_classify_primary_vehicle_color()` sobre esa detección**. Los vehículos secundarios (`detections_in_roi[1..N]`) nunca pasan por el clasificador de color en producción, aunque sus cajas sí quedan dibujadas en `*_annot.jpg`. | `VIGIA_Vision/runtime/coordinator.py` (líneas 652–725 ref. base) |
| 8 | **Comportamiento cuando el color no puede determinarse** | Retorna `VehicleColor.UNKNOWN` con estados granulares (`LOW_CONFIDENCE_UNKNOWN` si conf `< 0.40`; `AMBIGUOUS_COLOR` si margen `< 0.10`; `LOW_ILLUMINATION` si luminancia V `< 26.0`; `OVEREXPOSED_GLARE` si glare `> 0.65`; `INSUFFICIENT_REGION` si bbox `< 28 px`, área `< 900 px²`, píxeles útiles `< 80` o ratio `< 0.12`; `INVALID_DETECTION` si conf `< 0.25`; `CLASSIFIER_ERROR` en excepción controlada), asignando `confidence = 0.0` (o valor bajo degradado antes del rechazo en margen/confianza), incrementando `_color_unknown_total` sin detener ni fallar el pipeline de visión. | `VIGIA_Vision/detection/color_classifier.py`, `VIGIA_Vision/runtime/coordinator.py` |

### Hallazgo arquitectónico relevante: duplicidad de clasificadores

El repositorio mantiene **dos implementaciones paralelas e incompatibles en firma/estados** de `VehicleColorClassifier`:
1. **`VIGIA_Vision/detection/color_classifier.py`** (**Activo en producción**): usa estados `CLASSIFIED`, `LOW_CONFIDENCE_UNKNOWN`, `AMBIGUOUS_COLOR`, `LOW_ILLUMINATION`, `OVEREXPOSED_GLARE`, `INSUFFICIENT_REGION`, `INVALID_DETECTION`; parámetro `vehicle_class=`; salida `VehicleColorResult` con `ColorRegionQuality`.
2. **`VIGIA_Vision/classification/color_classifier.py`** (**Evaluado por `experiments/vision_05b/scripts/benchmark_color.py` en VISION-05B, desconectado de `VisionEngineCoordinator`**): usa estados `SUCCESS`, `AMBIGUOUS`, `LOW_QUALITY`, `UNRELIABLE_DETECTION`; ponderación elíptica espacial; atributo `.reason`; parámetro `detected_class=`.

---

## 3. Resultados de detección vehicular (FASE B)

### 3.1 Corpus histórico único documentado visualmente (*n* = 279 SHA-256 únicos)

Sobre las **279 imágenes únicas** (`evidencias_vigia/20261101..20261116` con `confirmed_visual_classification`), los resultados de `YoloVehicleDetector` con configuración productiva (`yolo26x.pt`, `cuda:0`, FP16, EXP-10) fueron:

- **Tasa global de presencia en ROI (`>= 0.70`):** **86.38 %** (`241/279`, 38 omitidos a 0.70, confianza media **0.8870**, distribución de etiquetas: `car=193`, `bus=31`, `truck=17`, `NONE=38`).
- **Tasa global de presencia en ROI (`>= 0.25`):** **96.77 %** (`270/279`, solo 9 omitidos a 0.25, confianza media **0.8455**, `car=205`, `bus=40`, `truck=25`, `NONE=9`).
- **Latencia de inferencia GPU (279 muestras tras warmup):** media **54.441 ms**, mediana **43.686 ms**, p90 **79.074 ms**, p95 **81.677 ms**, p99 **91.425 ms**, min **26.137 ms**, max **140.942 ms**. *(La diferencia entre p50 ≈ 43.7 ms y p90 ≈ 79.1 ms se explica por la activación de la segunda pasada EXP-10 `imgsz=384` cuando el primer paso obtiene < 0.70).*

#### Desglose por orientación (Corpus 279)

| Orientación | Total (*n*) | Detectados ROI `>=0.70` | Presencia `0.70` (%) | Detectados ROI `>=0.25` | Presencia `0.25` (%) | Confianza media (`0.70`) | Latencia media (ms) | Etiquetas `0.70` |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| **FRONTAL** | 87 | 76 | 87.36 % | 83 | 95.40 % | 0.8969 | 55.26 | `car:71, truck:4, bus:1, NONE:11` |
| **FRONTAL_OBLICUO** | 36 | 27 | 75.00 % | 36 | 100.00 % | 0.8581 | 65.45 | `car:15, truck:9, bus:3, NONE:9` |
| **LATERAL** | 120 | 102 | 85.00 % | 115 | 95.83 % | 0.8731 | 49.79 | `car:74, bus:27, truck:1, NONE:18` |
| **TRASERO** | 19 | 19 | 100.00 % | 19 | 100.00 % | 0.8996 | 34.64 | `car:16, truck:3` |
| **MULTI_ORIENTATION_SCREEN** | 17 | 17 | 100.00 % | 17 | 100.00 % | 0.9585 | 81.92 | `car:17` |

*(Nota metodológica: la categoría "Trasera oblicua" está agrupada dentro de `TRASERO` en los metadatos históricos, e.g., `EV-0430..0436` = "Auto rojo en vista trasera oblicua con sombra/contraluz", con 100 % de detección).*

#### Desglose por tipo de vehículo GT primario y caso especial Autobús Escolar Tipo C (0°)

| Tipo de vehículo GT | Total (*n*) | Detectados `0.70` | Presencia `0.70` | Presencia `0.25` | Etiquetas `0.70` | Observación técnica |
|---|---:|---:|---:|---:|---|---|
| **Automóvil (`car`)** | 203 | 178 | 87.68 % | 96.06 % | `car:168, truck:9, bus:1, NONE:25` | Mayoría de omisiones a 0.70 ocurren en baja iluminación severa (`EV-0475..`) o ángulos extremos con oclusión. |
| **Autobús (`bus`) — Total** | 68 | 55 | 80.88 % | 98.53 % | `bus:30, car:17, truck:8, NONE:13` | Incluye urbano `bus.jpg`, lateral y frontal Tipo C. |
| **↳ Caso especial: Autobús Escolar Tipo C Frontal (0°)** | 18 | 17 | **94.44 %** | **100.00 %** | `car:13, truck:4, NONE:1` | **Presencia resuelta (EXP-10)**, pero **0/18** salen como `bus`: `EV-0668` puro clasifica como `truck` (`0.7578`) y escenas con auto rojo al frente/fondo seleccionan `car` como primaria por mayor confianza (`~0.93`). |
| **Camioneta (`pickup`/`SUV`)** | 0 aislado* | — | — | — | — | **Brecha de taxonomía COCO:** COCO carece de clase `camioneta`/`SUV`; SUVs (como el Jeep/SUV cian en `20261116/17`) se predicen como `car`, `truck` o `bus` (`OTRO` en DDL). En collages `SCREEN` aparecen camionetas pickup sin bbox GT. |
| **Camión / Motocicleta** | 8 (`MULTI_SCREEN`) | 8 | 100.0 % | 100.0 % | `car:8` (primario) | Solo presentes en recapturas multi-objeto de Google Imágenes (`EV-0449..456`); cero muestras físicas aisladas de motocicleta o camión real. |

#### Desglose por tamaño aparente (aproximación por área relativa del bbox — sin calibración física de distancia)

> **Nota explícita:** Al no existir telemetría de distancia física ni calibración métrica de cámara, el tamaño aparente se aproxima mediante el porcentaje de área del bounding box respecto al área total del frame (`bbox.area / frame_area * 100`).

| Rango de área relativa (`0.70`) | Total (*n*) | Presencia `0.70` | Confianza media `0.70` | Etiquetas `0.70` |
|---|---:|---:|---:|---|
| **`< 2 %` (Lejano / Pequeño)** | 2 | 100.0 % (2/2) | 0.8254 | `car:2` |
| **`2–10 %` (Intermedio-lejano)** | 104 | 100.0 % (104/104) | 0.9066 | `car:97, truck:7` |
| **`10–25 %` (Intermedio)** | 106 | 100.0 % (106/106) | 0.8752 | `car:73, bus:28, truck:5` |
| **`> 25 %` (Cercano)** | 29 | 100.0 % (29/29) | 0.8643 | `car:21, bus:3, truck:5` |
| **`MISSED_AT_070` (Omitidos a 0.70)** | 38 | 0.0 % (76.32 % a 0.25) | `0.5002` (a 0.25) | `0.25`: `car:12, bus:9, truck:8, NONE:9` |

En subconjuntos anotados de dificultad: **Oclusión parcial** (*n* = 107) obtuvo **77.57 %** a `0.70` y **95.33 %** a `0.25` (confianza media `0.8760`); **Vehículo pequeño o lejano** (*n* = 66) obtuvo **98.48 %** (`65/66`) a `0.70` y **100.0 %** a `0.25`.

#### Desglose por iluminación y desenfoque

| Condición | Total (*n*) | Presencia `0.70` | Presencia `0.25` | Confianza media (`0.70`) | Latencia media (ms) |
|---|---:|---:|---:|---:|---:|
| **Luz diurna / Normal (`NORMAL_DAY`)** | 189 | 85.71 % (162) | 97.35 % (184) | 0.8804 | 54.43 |
| **Contraluz / Luz intensa (`BACKLIGHT_GLARE`)** | 53 | 98.11 % (52) | 100.00 % (53) | 0.9172 | 56.39 |
| **Baja iluminación (`LOW_LIGHT`)** | 37 | **72.97 % (27)** | 89.19 % (33) | 0.8688 | 51.73 |
| **Nítido (`SHARP`)** | 44 | **100.00 % (44)** | 100.00 % (44) | 0.9181 | 56.28 |
| **Desenfoque moderado (`MODERATE_BLUR`)** | 83 | 77.11 % (64) | 95.18 % (79) | 0.8976 | 54.25 |
| **Desenfoque severo (`SEVERE_BLUR`)** | 152 | 87.50 % (133) | 96.71 % (147) | 0.8716 | 54.01 |

*(Nota sobre iluminación nocturna artificial: el corpus histórico no incluye capturas vehiculares exteriores nocturnas reales con faros/alumbrado público; las pruebas `LOW_LIGHT` y las capturas nocturnas de interiores `20261117` emplean iluminación artificial interior de escritorio).*

### 3.2 Tasa operativa en capturas recientes `20261117` (sin anotación GT formal)

> **Advertencia metodológica:** Las siguientes métricas corresponden exclusivamente a **tasa operativa de disparo/clasificación en frames sin Ground Truth bbox**. No representan Precision ni Recall formales.

- **`CAM-ENTRADA` (muestra estratificada *n* = 375 de 2,108 archivos `_orig.jpg` `640x480`):**
  - Frames con al menos 1 detección en ROI (`>= 0.70`): **92.80 %** (`348/375`; histograma por frame: `0 det=27`, `1 det=66`, `2 det=117`, `3 det=165`).
  - Distribución de etiquetas ROI (`>= 0.70`): `car=741`, `truck=54` (y `car=827, truck=60, bus=2` a `>= 0.25`).
  - **Causa empírica de `CAMION`/`OTRO` en BD `20261117`:** La inspección visual de `_orig.jpg` / `_annot.jpg` y re-inferencia demostró que sobre la escena con convertible rosa, Jeep/SUV abierto turquesa y auto deportivo rojo miniatura: (1) el SUV turquesa abierto y el deportivo miniatura oscilan entre `car`, `truck` y `bus` según oclusión parcial del brazo del operador (`20261117T013131`: `bus conf=0.6550` sobre el SUV turquesa, `truck conf=0.7667` sobre el auto rojo; `20261117T015137`: `truck conf=0.9451`); y (2) la compresión JPEG al guardar `*_orig.jpg` desplaza ligeramente las confianzas en frontera respecto a la inferencia en memoria sobre el tensor crudo BGR de OpenCV DSHOW (explicando `DB=OTRO 0.935` en `20261117T013126` vs offline JPEG `car 0.9142`).
- **`CAM-SALIDA` (totalidad en disco *n* = 303 archivos `_orig.jpg` `720x1280`):**
  - Frames con detección ROI (`>= 0.70`): **100.00 %** (`303/303`; `1 det=7`, `2 det=6`, `3 det=290`).
  - Etiquetas ROI (`>= 0.70`): `car=855`, `truck=34`.
- **`CAM-03` (*n* = 3 archivos `640x480`):** **100.00 %** (`3/3`), todas `car`.

---

## 4. Resultados de clasificación de color (FASE C)

### 4.1 Comparativa global: clasificador real de Producción vs módulo VISION-05B

Se separan expresamente **color de referencia**, **color estimado**, **confianza** y **estado** para ambos módulos en tres evaluaciones complementarias:

| Suite / Corpus | Clasificador | *N* | Concordancia absoluta (%) | Accuracy excl. `UNKNOWN` (%) | `% UNKNOWN` | Latencia media (ms) |
|---|---|---:|---:|---:|---:|---:|
| **Suite Sintética 12 Categorías** (36 casos) | **Producción (`detection.color_classifier`)** | 36 | **88.89 %** (32/36) | **96.67 %** (29/30) | 16.67 % (6) | < 3.0 ms |
| **Suite Sintética 12 Categorías** (36 casos) | Baseline 05B (`classification.color_classifier`) | 36 | 86.11 % (31/36) | 90.32 % (28/31) | 13.89 % (5) | — |
| **GT VISION-05B Exacto (Todas)** | **Producción (`detection.color_classifier`)** | 185 | **78.38 %** (145/185) | **86.83 %** (145/167) | **9.73 %** (18) | **2.57 ms** |
| **GT VISION-05B Exacto (Todas)** | Baseline 05B (guardado `benchmark_color`) | 185 | 76.76 % (142/185) | 86.06 % (142/165) | 10.81 % (20) | 16+ ms |
| **GT VISION-05B Excl. Collages Pantalla** | **Producción (`detection.color_classifier`)** | 176 | **82.39 %** (145/176) | **90.62 %** (145/160) | **9.09 %** (16) | ~2.57 ms |
| **GT VISION-05B Excl. Collages Pantalla** | Baseline 05B (guardado `benchmark_color`) | 176 | 80.68 % (142/176) | 90.45 % (142/157) | 10.80 % (19) | — |
| **Corpus Único Histórico Unívoco** (222) | **Producción (`detection.color_classifier`)** | 222 | **78.38 %** (174/222) | 91.10 % (174/191) | 13.96 % (31) | ~2.6 ms |
| **Corpus Único Histórico Unívoco** (222) | Baseline 05B (`classification.color_classifier`) | 222 | 75.68 % (168/222) | **93.33 %** (168/180) | 18.92 % (42) | — |

### 4.2 Evaluación de las 12 categorías (Cobertura Sintética vs Disponibilidad Real)

En la **suite sintética calibrada (3 muestras por categoría)** los resultados por clase del clasificador de Producción fueron:
- **100 % F1 (`P=1.00, R=1.00`)**: `GRAY`, `RED`, `BLUE`, `GREEN`, `YELLOW`, `BROWN`, `ORANGE`, `OTHER` (magenta/rosa/púrpura). *(En contraste, Baseline 05B confundió `BROWN_v1 [45,85,130]` como `ORANGE` y 2 variantes `SILVER` como `WHITE`)*.
- **`SILVER`:** `Precision=1.00, Recall=0.6667, F1=0.80` (variante clara `[205,210,214]` clasificada como `WHITE` conf `0.98`, demostrando la frontera estrecha `WHITE`/`SILVER`).
- **`WHITE`:** `Precision=0.6667, Recall=0.6667, F1=0.6667` (`WHITE_v2 [250,250,248]` activó correctamente `OVEREXPOSED_GLARE -> UNKNOWN`).
- **`BLACK`:** `Precision=1.00, Recall=0.3333, F1=0.50` (`BLACK_v0 [18,18,20]` y `BLACK_v2 [12,12,14]` activaron `LOW_ILLUMINATION -> UNKNOWN` al quedar bajo `min_luminance_v = 26.0`, mientras Baseline 05B sí clasificó `BLACK_v0` como `BLACK` con conf `0.7376`).
- **`UNKNOWN`:** `Recall=1.00` (3/3 casos extremos oscuro/glare/bbox `<28 px`), `Precision=0.50` (por las 3 abstenciones de seguridad sobre `BLACK` muy oscuro y `WHITE` casi saturado).

En **capturas físicas reales (`evidencias_vigia`)**:
- Solo **`RED`** (*n* = 117 en 05B / 136 en hist-222), **`YELLOW`** (*n* = 30 / 59), **`OTHER`** (rosa, *n* = 27 reales / 21), **`BLUE`** (*n* = 2 / 5) y **`GRAY`** (*n* = 1 degradado con contraluz `EV-0003`) cuentan con muestras físicas verificadas.
- **`WHITE`, `BLACK`, `SILVER`, `GREEN`, `BROWN`, `ORANGE`** carecen de vehículos físicos individuales dedicados en el corpus; en consecuencia, su capacidad en campo real no está validada empíricamente (aunque el modelo cian/turquesa real de `20261116/17` cae consistentemente en `BLUE` [40/40 en `CAM-SALIDA` y `128` en `CAM-ENTRADA`]).

### 4.3 Sensibilidad a iluminación, sombras, recorte parcial y colores similares

1. **Iluminación (sobre GT VISION-05B *n* = 185 con clasificador de Producción):**
   - `GLARE_OR_HIGH_CONTRAST` (*n* = 25): **100.00 %** (`25/25`, `0` `UNKNOWN`).
   - `NORMAL` (*n* = 142): **80.99 %** absoluto (**85.19 %** excluyendo `UNKNOWN`, `4.93 %` `UNKNOWN`).
   - `LOW_LIGHT` (*n* = 18): **27.78 %** (`5/18`), **61.11 %** `UNKNOWN` (`11/18`, mayormente `LOW_ILLUMINATION`), aunque superior al `5.56 %` (`1/18`) de Baseline 05B. En la distribución de estados sobre los 185 registros: `CLASSIFIED=167`, `LOW_ILLUMINATION=10`, `AMBIGUOUS_COLOR=7`, `LOW_CONFIDENCE_UNKNOWN=1`.
2. **Escalamiento artificial de brillo (`0.25x` a `1.35x`) en vehículos reales:**
   - `red_toy_cam_salida` (`RED`): resistente desde `0.25x` (`RED 0.7535`) hasta `1.35x` (`RED 0.8920`).
   - `yellow_bus` (`YELLOW`): estable `0.50x..1.35x` (`YELLOW 0.8204..0.9079`), pero colapsa a `BLACK (0.8621)` a `0.25x`.
   - `blue_bus` (`BLUE`): estable `0.75x..1.35x` (`BLUE 0.6740..0.7939`), colapsa a `BLACK` a `<= 0.50x`.
   - `dark_blue_corsa` (automóvil real azul marino `EV-0428`): a escala `1.00x` y `1.35x` da `UNKNOWN (AMBIGUOUS_COLOR, 0.3536)`, y al oscurecer (`0.25x..0.75x`) vira a `BLACK` (`0.5240..0.7256`).
3. **Oclusión / Recorte parcial (mitades `left/right/top/bottom 50 %` de bbox real):**
   - `yellow_bus` y `red_toy_cam_salida`: **100 % invariantes** (`5/5` recortes mantienen `YELLOW` / `RED`).
   - `blue_bus`: mantiene `BLUE` en `4/5` recortes, fallando a `UNKNOWN (0.2832)` únicamente en `top_50pct` donde predominan techo blanco y parabrisas.
   - `dark_blue_corsa`: altamente sensible por reflejos del cielo/entorno (`full` -> `UNKNOWN`, `left_50` -> `BLACK`, `right_50`/`top_50` -> `RED` falso positivo por reflejo cálido del muro ladrillo adyacente).
4. **Diferenciación de colores similares:**
   - `PINK -> OTHER vs RED`: En `CAM-03` (`20261117T004301`, convertible rosa limpio), **Producción** predijo **`RED` (`0.810`, `CLASSIFIED`)** mientras Baseline 05B predijo correctamente **`OTHER` (`0.757`)**. En `CAM-SALIDA` (`20261117T010754`), el mismo convertible rosa dio `UNKNOWN (0.422, AMBIGUOUS_COLOR)` en Producción y `OTHER (0.853)` en Baseline 05B.
   - `SILVER vs WHITE`: Diferencia adecuadamente gris plata medio (`[192,195,200]` -> `SILVER 0.98`), pero plata muy claro (`[205,210,214]`) vira a `WHITE (0.98)`.
   - `RED vs ORANGE / BROWN`: Diferencia correctamente en condiciones limpias, pero sobre el vehículo miniatura rojo con calcomanía amarilla sobre mantel cálido (`20261117T015134/015137`), Producción osciló a `ORANGE (0.501–0.595)` y `BROWN (0.459 en 013131)`.

### 4.4 Estabilidad temporal entre fotogramas consecutivos (`20261117`, ráfagas de 20 frames)

| Ráfaga consecutiva (20 frames c/u) | Cámara | Frames detectados | Etiquetas YOLO | Secuencia / Moda Producción | Consistencia moda Prod (%) | Saltos frame-a-frame (Prod / 05B) | `stdev` conf. Prod |
|---|---|---:|---|---|---:|---:|---:|
| `burst_inicio` | `CAM-ENTRADA` | 20/20 | `car:20` | `5x OTHER -> 15x RED` (Moda `RED`) | **75.00 %** | **1** / 4 | 0.1107 |
| `burst_medio` | `CAM-ENTRADA` | 13/20 | `car:12, truck:1, NONE:7` | `RED -> UNK -> NO_DET -> BLUE/OTHER` | **53.85 %** | **5** / 3 | 0.1210 |
| `burst_ocluido_final` | `CAM-ENTRADA` | 14/20 | `car:13, truck:1, NONE:6` | `BLUE -> UNK -> RED -> BLACK -> RED` | **35.71 %** | **6** / 8 | 0.2085 |
| `burst_nitido_multi` | `CAM-SALIDA` | 20/20 | `car:20` | `16x UNKNOWN, 4x BLUE` (Moda `UNKNOWN`) | 80.00 % (abst.) | **5** / 5 | 0.1580 |
| `burst_inicio` | `CAM-SALIDA` | 20/20 | `car:20` | `RED` dominante con `BLUE`/`GREEN`/`UNK` | **80.00 %** | **6** / 6 | 0.1315 |

*(Conclusión de estabilidad: sin filtro temporal / suavizado EMA entre frames, pequeñas variaciones de sombra, oclusión de brazo o cambio del vehículo en slot primario provocan hasta 6 saltos cromáticos en 14–20 frames consecutivos).*

---

## 5. Matrices de confusión

### 5.1 Detección vehicular sobre Corpus Único Histórico (`n = 271` clases únicas `car` + `bus`)

**Umbral productivo ROI `>= 0.70` (Exactitud clase primaria = `198/271 = 73.06 %`):**

| GT \ Predicción `0.70` | `car` | `bus` | `truck` | `motorcycle` | `NONE` (perdido) | Total |
|---|---:|---:|---:|---:|---:|---:|
| **`car`** | **168** | 1 | 9 | 0 | 25 | **203** |
| **`bus`** | 17 | **30** | 8 | 0 | 13 | **68** |
| **`truck`** | 0 | 0 | **0** | 0 | 0 | **0** |
| **`motorcycle`** | 0 | 0 | 0 | **0** | 0 | **0** |

**Umbral candidato ROI `>= 0.25` (Exactitud clase primaria = `219/271 = 80.81 %`):**

| GT \ Predicción `0.25` | `car` | `bus` | `truck` | `motorcycle` | `NONE` (perdido) | Total |
|---|---:|---:|---:|---:|---:|---:|
| **`car`** | **180** | 1 | 14 | 0 | 8 | **203** |
| **`bus`** | 17 | **39** | 11 | 0 | 1 | **68** |

### 5.2 Color — Suite Sintética de 12 Categorías (`n = 36`, Clasificador de Producción)

| GT \ Pred | `WHITE` | `BLACK` | `GRAY` | `SILVER` | `RED` | `BLUE` | `GREEN` | `YELLOW` | `BROWN` | `ORANGE` | `OTHER` | `UNKNOWN` | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **`WHITE`** | **2** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | **3** |
| **`BLACK`** | 0 | **1** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | **3** |
| **`GRAY`** | 0 | 0 | **3** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **3** |
| **`SILVER`** | 1 | 0 | 0 | **2** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **3** |
| **`RED`** | 0 | 0 | 0 | 0 | **3** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **3** |
| **`BLUE`** | 0 | 0 | 0 | 0 | 0 | **3** | 0 | 0 | 0 | 0 | 0 | 0 | **3** |
| **`GREEN`** | 0 | 0 | 0 | 0 | 0 | 0 | **3** | 0 | 0 | 0 | 0 | 0 | **3** |
| **`YELLOW`** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **3** | 0 | 0 | 0 | 0 | **3** |
| **`BROWN`** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **3** | 0 | 0 | 0 | **3** |
| **`ORANGE`** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **3** | 0 | 0 | **3** |
| **`OTHER`** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **3** | 0 | **3** |
| **`UNKNOWN`** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **3** | **3** |

### 5.3 Color — Corpus Real GT VISION-05B (`n = 185`, Producción vs Baseline)

*(Nota: columnas sin predicciones ni soporte se omiten por claridad; la matriz completa 12×12 reside en `vision_07b_evaluation_results.json`).*

**Clasificador de Producción (`78.38 %` abs. / `86.83 %` excl. `UNKNOWN`):**

| GT \ Pred Prod | `BLACK` | `GRAY` | `SILVER` | `RED` | `BLUE` | `YELLOW` | `BROWN` | `ORANGE` | `OTHER` | `UNKNOWN` | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **`RED`** | 2 | 0 | 0 | **103** | 0 | 1 | 0 | 0 | 0 | 11 | **117** |
| **`BLUE`** | 0 | 0 | 0 | 0 | **1** | 0 | 0 | 0 | 0 | 1 | **2** |
| **`YELLOW`** | 0 | 0 | 0 | 2 | 0 | **28** | 0 | 0 | 0 | 0 | **30** |
| **`OTHER`** *(rosa + collages)* | 0 | 6 | 1 | 6 | 2 | 0 | 1 | 1 | **13** | 6 | **36** |

**Baseline VISION-05B (`76.76 %` abs. / `86.06 %` excl. `UNKNOWN`):**

| GT \ Pred 05B | `WHITE` | `RED` | `BLUE` | `YELLOW` | `BROWN` | `ORANGE` | `OTHER` | `UNKNOWN` | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **`RED`** | 0 | **95** | 0 | 1 | 4 | 0 | 0 | 17 | **117** |
| **`BLUE`** | 0 | 0 | **2** | 0 | 0 | 0 | 0 | 0 | **2** |
| **`YELLOW`** | 0 | 3 | 0 | **27** | 0 | 0 | 0 | 0 | **30** |
| **`OTHER`** | 2 | 2 | 9 | 0 | 0 | 2 | **18** | 3 | **36** |

**Corpus Histórico Unívoco (*n* = 222, Producción `78.38 %` abs. / `91.10 %` excl. `UNKNOWN`):**
`GRAY (1)` -> `{UNKNOWN: 1}`; `RED (136)` -> `{RED: 107, BLACK: 3, UNKNOWN: 26}`; `BLUE (5)` -> `{BLUE: 3, UNKNOWN: 2}`; `YELLOW (59)` -> `{YELLOW: 51, RED: 8}`; `OTHER (21)` -> `{OTHER: 13, RED: 6, UNKNOWN: 2}`.

---

## 6. Métricas calculadas sobre Ground Truth

### 6.1 Detección vehicular — Métricas a nivel de imagen (vs imposibilidad de `AP`/`mAP`)

| Métrica / Clase | Umbral `0.70` (Prod) | Umbral `0.25` (Raw) | Soporte (*n*) | Alcance exacto |
|---|---:|---:|---:|---|
| **`car` — Precision / Recall / F1** | **0.9081** / **0.8276** / **0.8660** | **0.9137** / **0.8867** / **0.9000** | 203 | Clasificación de imagen primaria en corpus único (`271`) |
| **`bus` — Precision / Recall / F1** | **0.9677** / **0.4412** / **0.6061** | **0.9750** / **0.5735** / **0.7222** | 68 | Penalizado por confusión `truck`/`car` en Tipo C `0°` |
| **Presencia vehicular global (279)** | Recall **86.38 %** | Recall **96.77 %** | 279 | Todas las 279 imágenes contienen >=1 vehículo |
| **`AP` por clase, `mAP@0.5`, `mAP@0.5:0.95`** | **NO CALCULABLE (N/A)** | **NO CALCULABLE (N/A)** | 0 bboxes GT | `manifest_v1.json` (604 `UNANNOTATED`), `manifest_v1_seed.json` (150 `PENDING_HUMAN_REVIEW`): **0 polígonos/bboxes GT manuales `[x1,y1,x2,y2]`**. |

### 6.2 Clasificación de color — Precision, Recall y F1 sobre GT disponible (Producción)

| Categoría | Corpus Real `05B` Excl. Screen (*n* = 176): **P / R / F1 (soporte)** | Corpus Histórico Unívoco (*n* = 222): **P / R / F1 (soporte)** | Suite Sintética 12 Clases (*n* = 36): **P / R / F1 (soporte)** |
|---|---|---|---|
| **RED** | **0.9364 / 0.8803 / 0.9075** (117) | **0.8843 / 0.7868 / 0.8327** (136) | 1.0000 / 1.0000 / 1.0000 (3) |
| **YELLOW** | **0.9655 / 0.9333 / 0.9492** (30) | **1.0000 / 0.8644 / 0.9273** (59) | 1.0000 / 1.0000 / 1.0000 (3) |
| **OTHER** *(rosa)* | **1.0000 / 0.4815 / 0.6500** (27) | **1.0000 / 0.6190 / 0.7647** (21) | 1.0000 / 1.0000 / 1.0000 (3) |
| **BLUE** | 0.3333 / 0.5000 / 0.4000 (2) | 1.0000 / 0.6000 / 0.7500 (5) | 1.0000 / 1.0000 / 1.0000 (3) |
| **GRAY** | Sin muestra GT real (0) | 0.00 / 0.00 / N/A (1 degradada) | 1.0000 / 1.0000 / 1.0000 (3) |
| **WHITE / BLACK / SILVER / GREEN / BROWN / ORANGE** | **Sin muestras GT reales en flota (0)** | **Sin muestras GT reales (0)** | Véase Sección 4.2 (`1.00` en `GREEN/BROWN/ORANGE`, `0.80 SILVER`, `0.67 WHITE`, `0.50 BLACK`) |
| **UNKNOWN** *(abstención)* | 16 predicciones (9.09 % abst.) | 31 predicciones (13.96 % abst.) | 0.5000 / 1.0000 / 0.6667 (3 reales + 3 seg.) |

---

## 7. Integridad vehículo-color (FASE D)

Se ejecutaron cuatro pruebas aisladas sin tocar `.env`, BD productiva ni servicio en vivo:

1. **Aislamiento de crop en frames reales multi-vehículo (`all_multi_vehicle_crops_isolated = True`):**
   Se evaluaron 4 escenas multi-vehículo reales (`20261117_multi_3veh` con 3 autos: rosa/rojo/cian; `20261116_bus_red_2veh` con deportivo rojo + bus amarillo; `20261116_pink_cyan_2veh` con rosa + cian; `20261117_occluded_multi` con oclusión). Al reemplazar el **100 % de los píxeles fuera de cada `d.bbox` por verde saturado `(0,255,0)`**, cada una de las 10 detecciones retornó color, confianza y estado **bit a bit idénticos** (`strict_crop_isolated = True` en 10/10), demostrando ausencia total de contaminación entre bboxes cuando se invoca el clasificador por detección.
   - Ejemplo `20261117_multi_3veh` (`720x1280`):
     - Detección `[0]` (`bbox=[242,324,598,570]`, convertible rosa, conf `0.8696`): `UNKNOWN (0.4221, AMBIGUOUS_COLOR)`
     - Detección `[1]` (`bbox=[519,615,581,706]`, deportivo rojo miniatura, conf `0.7607`): **`RED` (`0.8804`, `CLASSIFIED`)**
     - Detección `[2]` (`bbox=[164,525,445,748]`, SUV turquesa/cian, conf `0.7290`): **`BLUE` (`0.8098`, `CLASSIFIED`)**

2. **Contaminación sintética por solapamiento geométrico de boxes:**
   Al intruir un vehículo `BLUE` dentro del bbox de un vehículo `RED` en `0 %`, `15 %`, `30 %` y `50 %` del ancho: hasta `30 %` de solapamiento preservó `RED` (`conf 0.9200 -> 0.9473 -> 0.7367`), pero con **50 % de invasión** (`overlap_frac = 0.50`) el algoritmo invirtió el resultado a **`BLUE (0.4745)`** al dominar los píxeles del intruso dentro del rectángulo anatómico central.

3. **Limitación crítica de `VisionEngineCoordinator` en múltiples vehículos (`secondary_vehicles_color_dropped = True`):**
   Al procesar `20261117_multi_3veh` (3 detecciones en ROI) a través de `VisionEngineCoordinator.process_camera_step()`:
   - Solo clasificó `detections_in_roi[0]` (el convertible rosa -> `UNKNOWN`), **descartando por diseño** el `RED (0.8804)` del vehículo `[1]` y el `BLUE (0.8098)` del vehículo `[2]`.

4. **Aislamiento concurrente dual-cámara y abstención `UNKNOWN`:**
   - **Dual-cámara en hilos simultáneos (`zero_cross_camera_contamination = True`):** Ejecutando `CAM-ENTRADA` (8 pasos escena multi) en paralelo con `CAM-SALIDA` (4 pasos bus amarillo + 4 pasos bus azul), `CAM-ENTRADA` arrojó `[UNKNOWN x8]` y `CAM-SALIDA` arrojó `[YELLOW x4, BLUE x4]` con `error_total = 0` y latencia media de color `5.946 ms`.
   - **Abstenciones de seguridad (`4/4` `UNKNOWN`):** Oscuridad extrema (`LOW_ILLUMINATION`, conf `0.0`), deslumbramiento (`OVEREXPOSED_GLARE`, conf `0.0`), bbox `20x20 px` (`INSUFFICIENT_REGION`, conf `0.0`), confianza de detección `0.10` (`INVALID_DETECTION`, conf `0.0`).

---

## 8. Resultados por cámara y persistencia (FASE E y FASE F)

### 8.1 Estado operativo en vivo (FASE E — Snapshot `2026-11-17T01:56:35Z`)

Consultado en solo-lectura sobre `https://127.0.0.1:5001/api/v1/supervision/status`, `/api/v1/cameras`, `nvidia-smi` y PostgreSQL (`vigia_db` puerto `5434`):

| Parámetro / Métrica | `CAM-ENTRADA` (USB DSHOW) | `CAM-SALIDA` (Móvil HTTPS Push) | `CAM-03` (Auxiliar Push) |
|---|---|---|---|
| **Área de visión / Movimiento** | `ROI-ENT` (`ENTRADA`) | `ROI-SAL` (`SALIDA`) | `ROI-ENT` |
| **Modelo efectivo en memoria** | `yolo26x.pt` (`cuda:0`, FP16, NMS-Free) | `yolo26x.pt` (`cuda:0`, FP16, NMS-Free) | `yolo26x.pt` |
| **Resolución de evidencias `20261117`** | **`640x480`** | **`720x1280`** | `640x480` |
| **Frames ingeridos (`ingest_count`)** | **62,820** | **1,031** | 1 |
| **Frames procesados (`processed_count`)** | **62,820** | **1,031** | 1 |
| **Frames descartados (`dropped_frames`)** | **0** | **0** | **0** |
| **FPS ingreso / procesado en vivo** | **14.87 / 14.81 FPS** | Ingesta esporádica por evento push (`EN_ESPERA`, último hace `2,849.9s` a `01:09:05Z`) | `1` único push (`00:44:29Z`) |
| **Espera en cola / Último paso (`last_step_ms`)** | `0.001 ms` / `49.19 ms` | `3.703 ms` / `123.534 ms` | `12.423 ms` / `134.957 ms` |
| **Detecciones persistidas en BD (`20261117`)** | **2,096** (`AUTOMOVIL: 1,976` [avg `0.8765`], `CAMION: 117` [avg `0.8279`], `OTRO: 3` [avg `0.8413`]) | **303** (`AUTOMOVIL: 303` [avg `0.9244`]) | 0 nuevas bajo código propio (`ROI-ENT`) |
| **Separación de cuellos de botella** | **Captura óptica:** webcam VGA fija (`640x480`, 58.7 % blur mod., 14.9 % blur severo). Pipeline procesa sin retención a 14.8 FPS. | **Transmisión:** cadencia mediana push **3.525 s** (`0.284 Hz`). Óptica nítida (97 % `laplacian >= 120`, 207.9 mediana). | Canal auxiliar de prueba |

- **Estado GPU / VRAM (`nvidia-smi` + `torch`):** NVIDIA GeForce RTX 4050 Laptop GPU usando **1,907 MiB / 6,141 MiB VRAM totales del sistema** (4,015 MiB libres; el proceso Python asigna **402.84 MB** y reserva **594.0 MB**), utilización GPU **39 %**, memoria **10 %**, temperatura **65 °C**, consumo **35.93 W**.
- **Confiabilidad acumulada del servicio:** **63,852 inferencias** ejecutadas en la sesión con **`cuda_errors = 0`**, **`inference_errors = 0`**, **`init_errors = 0`**, **`fallback_count = 0`**, **`duplicates_suppressed = 228,359`**, **`frontal_aux_triggers = 55,309`**, **`frontal_aux_recoveries = 46,118`** (recuperación del **83.38 %** de disparos auxiliares).

### 8.2 Auditoría de persistencia PostgreSQL (FASE F)

La base de datos productiva registra **3,210 filas totales** en `deteccion` (`CAM-ENTRADA`: 2,533; `CAM-SALIDA`: 677). Inspeccionando `information_schema.columns` y `pg_constraint`:

| Atributo solicitado (FASE F) | ¿Persistido hoy? | Columna / Mecanismo actual | Brecha detectada |
|---|---|---|---|
| **Clase vehicular** | Sí | `deteccion.tipo_vehiculo_pred` (`AUTOMOVIL`, `CAMIONETA`, `CAMION`, `MOTOCICLETA`, `OTRO`) | `AUTOBUS` se degrada a `'OTRO'` por `map_tipo_vehiculo_ddl_v1` ante constraint `ck_deteccion_tipo_vehiculo`. |
| **Color del vehículo** | **NO** | *Ausente en tabla `deteccion` y `DetectionInsertDTO`* | Se calcula en RAM en `coordinator.py` y **se descarta sin persistir**. |
| **Confianza de detección** | Sí | `deteccion.confianza_vehiculo` (`numeric [0..1]`) | Completo para vehículo primario. |
| **Confianza de color** | **NO** | *Ausente en tabla `deteccion` y `DetectionInsertDTO`* | Descartada en runtime; tampoco expuesta en `/api/v1/supervision/status`. |
| **Identificador de cámara** | Sí (indirecto) | FK `id_area_vision -> area_vision.id_camara -> camara.codigo` | Íntegro (solo primario por evento). |
| **Timestamp** | Sí | `deteccion.fecha_hora` (`timestamptz`) | Íntegro. |
| **Evidencia original** | Sí | `deteccion.ruta_evidencia_foto` (`*_orig.jpg`) | Completo y limpio (sin anotaciones superpuestas). |
| **Evidencia anotada** | Parcial (solo disco) | Archivo paralelo `*_annot.jpg` en `evidencias_vigia/` | Dibuja ROI amarillo y cajas verdes, pero **no anota texto de clase, confianza ni color**. |

---

## 9. Rendimiento y latencias

| Componente / Escenario | Mediana (p50) | Media | p95 | p99 | Throughput equivalente | Impacto en pipeline |
|---|---:|---:|---:|---:|---:|---|
| **YOLO26x Producción Live (63,852 inf.)** | **44.397 ms** | **43.793 ms** | **51.336 ms** | **56.316 ms** | **22.83 FPS** | Soporta 15 FPS USB + Push simultáneos sin cola (`queue_wait = 0.001 ms`). |
| **YOLO26x Offline Corpus Histórico (279 img.)** | 43.686 ms | 54.441 ms | 81.677 ms | 91.425 ms | ~18.4 FPS | Bimodalidad p50 vs p95 debida a segunda pasada EXP-10 (`imgsz=384`). |
| **YOLO26x Offline `CAM-SALIDA` 720x1280 (303)** | 39.567 ms | 35.794 ms | 56.138 ms | 68.633 ms | ~27.9 FPS | Casi sin disparo auxiliar porque los vehículos superan `0.70` en pasada 1. |
| **YOLO26x Offline `CAM-ENTRADA` 640x480 (375)** | 41.790 ms | 40.924 ms | 58.440 ms | 73.130 ms | ~24.4 FPS | Holgado frente a `0.33 Hz` de persistencia (cooldown 3s) y `14.87 FPS` de lectura. |
| **Clasificador Color Producción (CPU, *n* = 185)** | **2.479 ms** | **2.572 ms** | **3.691 ms** | **4.629 ms** | **~388 FPS** | **No bloquea ni degrada el pipeline (~5.8 % respecto al tiempo de GPU YOLO)**. |
| **Clasificador Color dentro Coordinator Dual-Cam** | — | **5.946 ms** | — | — | ~168 FPS | Incluye extracción y actualización de métricas internas sin locks de contención. |

---

## 10. Problemas encontrados

1. **P0 — Divergencia activa entre clasificadores de color (`detection` vs `classification`):**
   `VIGIA_Vision/detection/color_classifier.py` (ejecutado en producción) y `VIGIA_Vision/classification/color_classifier.py` (probado en VISION-05B) duplican responsabilidades con reglas HSV/Lab y estados distintos (`CLASSIFIED`/`UNKNOWN` vs `SUCCESS`), generando riesgo de falsas validaciones al benchmarkear el módulo incorrecto.
2. **P0 — Pérdida silenciosa del atributo color entre memoria y base de datos / API:**
   `VisionEngineCoordinator` calcula `vehicle_color_pred` y `vehicle_color_confidence`, pero `PsycopgDetectionRepository._INSERT_SQL` y `DetectionInsertDTO` no poseen dichos campos; adicionalmente, `ingest_service.py` `/api/v1/supervision/status` recorta la llave `"color_classifier"` al construir `vision_metrics`, dejando el clasificador invisible para monitoreo operativo y dashboard.
3. **P1 — Clasificador limitado únicamente a `detections_in_roi[0]` en escenas multi-vehículo:**
   En el `97.69 %` de frames recientes de `CAM-SALIDA` (`296/303`) y el `75.20 %` de `CAM-ENTRADA` (`282/375`) coexisten 2 o 3 vehículos en el ROI. Al ignorar `[1..N]`, todo vehículo secundario queda sin color ni registro independiente.
4. **P1 — Inestabilidad temporal frame-a-frame e imprecisión en rosa (`OTHER`) / rojo cálido:**
   En ráfagas estáticas de `CAM-ENTRADA` (`burst_ocluido_final`), el color del vehículo primario saltó 6 veces en 14 detecciones (`BLUE -> UNKNOWN -> RED -> BLACK -> RED`). En `CAM-03`, el convertible rosa fue clasificado como `RED (0.810)` por Producción, y en `CAM-SALIDA` abdujo a `UNKNOWN (AMBIGUOUS_COLOR)` en `138/303` frames.
5. **P1 — Degradación severa en baja iluminación:**
   Sobre `LOW_LIGHT` (*n* = 18), el clasificador alcanzó apenas `27.78 %` de concordancia absoluta (`61.11 %` `UNKNOWN`), y en el auto real azul marino (`EV-0428`) devolvió `UNKNOWN` en condición normal y `BLACK` con ligera subexposición (`<= 0.75x`).
6. **P2 — Confusión semántica de clase vehicular (`car` / `truck` / `bus`) en modelos a escala y Tipo C frontal:**
   El Jeep/SUV turquesa y el auto deportivo miniatura generaron `117` falsas etiquetas `'CAMION'` y `3` `'OTRO'` (`bus`) en `20261117`, y el autobús escolar Tipo C visto de frente (`0°`) obtuvo **0/18** clasificaciones como `bus` (`truck` o `car`).

---

## 11. Limitaciones conocidas

1. **Ground Truth incompleto:** Cero anotaciones manuales de bounding box `[x1, y1, x2, y2]` (`UNANNOTATED` / `PENDING_HUMAN_REVIEW`), impidiendo calcular `AP`, `mAP@0.5` y `mAP@0.5:0.95`.
2. **Cobertura cromática real desbalanceada:** Ausencia de vehículos físicos individuales reales en `WHITE`, `BLACK`, `SILVER`, `GREEN`, `BROWN` y `ORANGE` dentro de `evidencias_vigia/` (validados únicamente mediante suite sintética).
3. **Brecha de dominio (modelos a escala en escritorio vs tráfico vial real):** La gran mayoría de muestras de ambas cámaras corresponde a vehículos a escala sobre mesa con iluminación doméstica y sin placas metálicas reales ni velocidades vehiculares reales (`10–60 km/h`).
4. **Limitación taxonómica COCO vs DDL VIGÍA:** COCO no distingue `CAMIONETA` (pickup/SUV), y `AUTOBUS` se colapsa a `'OTRO'` en el constraint actual de PostgreSQL (`ck_deteccion_tipo_vehiculo`).
5. **Sin calibración métrica de distancia:** El análisis de distancia/escala emplea área relativa del bbox como aproximación no calibrada.

---

## 12. Evaluación preliminar de viabilidad LPR/ANPR (FASE G)

> **Restricción cumplida:** No se instaló OCR ni se activaron modelos LPR durante esta fase.

Las mediciones ópticas directas sobre las evidencias originales `*_orig.jpg` muestran una asimetría crítica entre ambas cámaras:

| Métrica óptica / LPR | `CAM-ENTRADA` (`20261117`, *n* = 375) | `CAM-SALIDA` (`20261117`, *n* = 303) | Requisito típico mínimo ANPR/OCR funcional |
|---|---|---|---|
| **Resolución de frame** | **`640 x 480`** (VGA, 0.31 MP) | **`720 x 1280`** (HD vertical, 0.92 MP) | `>= 1280 x 720` (recomendado `1920 x 1080`) |
| **Tamaño JPG medio / p50** | `48.43 KB` / `50.81 KB` | `215.37 KB` / `220.12 KB` | Baja compresión (`>= 150 KB` en HD sin artefactos bloque) |
| **Nitidez (`Laplacian var`) p50 / Distribución** | **106.99** (`58.7 %` mod `50–120`, `14.9 %` severo `< 50`, `26.4 % >= 120`) | **207.89** (**97.0 %** nítidas `>= 120`, `2.0 % < 50`) | `Laplacian var >= 120–150` consistente sin motion blur |
| **Luminancia media `Y` / Glare `>=245`** | `99.23` p50 / **`4.86 %` glare p50** (máx `22.82 %`) | `82.21` p50 / **`0.006 %` glare p50** (máx `0.38 %`) | Exposición balanceada sin saturación sobre placa |
| **Ancho bbox vehículo p10 / p50 / p90** | `52 / 105 / 232 px` | `62 / 281 / 359 px` | — |
| **Ancho estimado de placa (`~16.7 % bbox_w`)** | **Mean `21.3 px`, p50 `17.5 px`, p90 `38.7 px`, Máx `52.3 px`** | **Mean `38.2 px`, p50 `46.9 px`, p90 `60.0 px`, Máx `82.7 px`** | **`>= 80–120 px` de ancho** (y altura carácter `>= 18–25 px`) |
| **Detecciones con placa estimada `>= 80 px`** | **0.00 %** (`0 / 795`) | **0.11 %** (`1 / 889`; `6 / 889 >= 60 px`) | Meta operativa `> 90 %` dentro de ROI de lectura |
| **Frecuencia / Cadencia de captura** | Lectura **14.87 FPS**; persistencia mediana `3.012s` (`0.33 Hz`, ráfagas min `0.134s`) | Push móvil HTTP: **mediana `3.525 s`** (`0.284 Hz`, min `1.878 s`) | Para vehículos en movimiento, ráfaga `>= 10–15 FPS` en ventana ROI |

### Diagnóstico LPR por cámara
- **`CAM-ENTRADA` (USB):** En las condiciones actuales (`640x480` VGA + desenfoque moderado/severo en el **73.6 %** de frames + glare hasta `22.8 %`), **NO posee condiciones ópticas adecuadas para LPR** sobre vehículos en aproximación: incluso ocupando 300 px de ancho, una placa física mediría apenas ~50 px (`~9.7 px` de alto de carácter), insuficiente para OCR alfanumérico confiable. Requiere elevar resolución USB a `1280x720` o `1920x1080` MJPG y ubicar/enfocar el carril con ángulo frontal `< 20°` y obturación rápida.
- **`CAM-SALIDA` (Móvil Push):** Posee **excelente nitidez (`97 % >= 120`)** y bajísimo glare (`0.006 %`), pero presenta dos limitantes críticas antes de LPR productivo: (1) orientación **vertical `720x1280`** (desperdicia área vertical en techo/suelo y reduce el ancho útil disponible a 720 px, dejando p90 estimado de placa en `60 px`), y (2) cadencia móvil actual de **1 frame cada ~3.5 segundos**, insuficiente si un vehículo real cruza el ROI en `< 2 segundos`. Se requiere cambiar a orientación **horizontal `1280x720` o `1920x1080`** y cadencia de ráfaga o disparo por proximidad.
- **Conclusión de arquitectura para `VISION-08`:** Las evidencias originales `*_orig.jpg` son limpias (sin recuadros superpuestos) y `VisionResult` ya contempla `plate_located`, `plate_text` y `plate_confidence`, así como los CHECK constraints de `deteccion.placa_detectada` en PostgreSQL; por tanto, **la arquitectura de software sí está preparada** para acoplar un módulo LPR independiente en VISION-08, **condicionada en campo a la mejora óptica de cámaras y validación con placas reales**.

---

## 13. Recomendaciones técnicas (sin implementar en VISION-07B)

1. **[P0 — Arquitectura] Unificar el clasificador de color en un único módulo:**
   Retirar o deprecar `VIGIA_Vision/classification/color_classifier.py` (o consolidar en `VIGIA_Vision/detection/color_classifier.py` la distinción de tonos pastel/rosa `OTHER`) para eliminar divergencia entre benchmarks y producción.
2. **[P0 — Persistencia / Esquema PostgreSQL (Propuesta DDL para fase posterior, NO ejecutada)]:**
   Ampliar la tabla `deteccion`, `DetectionInsertDTO` y `_INSERT_SQL` para conservar trazabilidad completa de color y métricas:
   ```sql
   ALTER TABLE deteccion
     ADD COLUMN color_vehiculo_pred VARCHAR(20) NULL,
     ADD COLUMN confianza_color NUMERIC(5,4) NULL,
     ADD COLUMN estado_color VARCHAR(32) NULL,
     CONSTRAINT ck_deteccion_color_pred CHECK (
       color_vehiculo_pred IS NULL OR color_vehiculo_pred IN (
         'WHITE','BLACK','GRAY','SILVER','RED','BLUE',
         'GREEN','YELLOW','BROWN','ORANGE','OTHER','UNKNOWN'
       )
     ),
     CONSTRAINT ck_deteccion_confianza_color CHECK (
       confianza_color IS NULL OR (confianza_color >= 0 AND confianza_color <= 1)
     );
   ```
   *(Adicionalmente evaluar incluir `'AUTOBUS'` en `ck_deteccion_tipo_vehiculo` para evitar degradación a `'OTRO'`, y exponer `"color_classifier"` + `vehicle_color_pred` en `/api/v1/supervision/status` y `/api/v1/cameras/<c>/status`).*
3. **[P1 — Multi-vehículo y asociación] Iterar sobre todas las detecciones aceptadas en ROI:**
   Permitir que `VisionEngineCoordinator` evalúe `VehicleColorClassifier` para **cada** `RawVehicleDetection` dentro de `detections_in_roi` (adjuntando `(bbox, raw_label, confidence, color_result)` en `VisionObservationEnvelope`), sin limitar la salida al índice `[0]`.
4. **[P1 — Ground Truth formal] Completar campaña de anotación humana en `vigia_bench_v1` y `vigia_ml`:**
   Anotar bounding boxes `[x1, y1, x2, y2]` reales y etiquetas verificadas de las **12 categorías de color** (priorizando vehículos físicos `WHITE`, `BLACK`, `SILVER`, `GREEN`, `BROWN`, `ORANGE`, `Camioneta`, `Camión`, `Motocicleta` y escena nocturna exterior real) para desbloquear cálculo formal de `mAP@0.5` y `mAP@0.5:0.95`.
5. **[P1 — Estabilidad temporal y calibración cromática] Suavizado multi-frame y ajuste de rosa/azul oscuro:**
   Integrar consenso temporal por ventana deslizante (moda ponderada por confianza de color sobre los últimos 3–5 frames del track) y ajustar umbrales CIELAB/chroma para distinguir rosa pastel (`OTHER`) frente a `RED` y azul marino oscuro frente a `BLACK`/`UNKNOWN`.
6. **[P2 — Prerrequisitos ópticos previos a VISION-08 LPR/ANPR]:**
   Configurar `CAM-ENTRADA` y `CAM-SALIDA` en paisaje `>= 1280x720` (`1920x1080` recomendado en carril LPR), asegurar enfoque/obturación con `Laplacian var >= 150`, validar ancho de placa `>= 90 px` sobre vehículos reales con placas mexicanas/estándar y elevar la frecuencia de envío/captura en ROI antes de activar OCR en `VISION-08`.

---

## 14. Dictamen final

### **`APPROVED WITH OBSERVATIONS — INCOMPLETE GROUND TRUTH`**

**Justificación técnica del dictamen conforme a la Sección 11:**
- **No procede `NOT APPROVED`:** El aislamiento de crop del clasificador de color alcanzó **100 %** en frames multi-vehículo, la concurrencia dual-cámara en `VisionEngineCoordinator` demostró **0 % de contaminación cruzada**, la inferencia YOLO26x opera de manera estable con **0 errores en 63,852 inferencias** (`22.83 FPS` GPU, latencia p50 `44.4 ms`) y el clasificador de color añade solo `2.57–5.95 ms` sin degradar el pipeline.
- **No procede `APPROVED — VEHICLE DETECTION AND COLOR EVALUATED` pleno:** Faltan anotaciones manuales de bounding box `[x1, y1, x2, y2]` (imposibilitando `AP` y `mAP`), faltan muestras físicas reales en 6 de las 12 categorías cromáticas y existen brechas de ingeniería documentadas (clasificador secundario duplicado en `classification/`, ausencia de persistencia de color en PostgreSQL/API, y clasificación restringida al vehículo primario `detections_in_roi[0]`).

### Preparación para avanzar a `VISION-08 (LPR/ANPR)`

- **Pipeline de detección + módulo de color:** **Apto como base de arquitectura modular** para integrar `VISION-08` como módulo independiente (los frames `*_orig.jpg`, el esquema de placas en PostgreSQL y `VisionResult` ya contemplan la extensión), **condicionado a**:
  1. Cerrar las observaciones P0 (unificación del clasificador de color + migración DDL/DTO para persistir `color_vehiculo_pred` y `confianza_color`).
  2. Elevar la resolución física/orientación de captura (`>= 1280x720` horizontal) y ejecutar pruebas físicas con automóviles reales portando matrículas antes de declarar operable el OCR en campo.
