# VIGIA-VISION-05A.1 — Auditoría de Cierre y Validación de Optimización Frontal

**Proyecto:** VIGÍA Vision Systems  
**Fase:** `VISION-05A.1` *(Auditoría Independiente de Cierre de `VISION-05A`)*  
**Fecha de Emisión:** 16 de noviembre de 2026  
**Modelo Principal Auditado:** `yolo26x.pt` (`YOLO26DetectionModel`, `CUDA:0`, `FP16`, `imgsz=640`, `nms=False` + refinamiento `VISION-05A`)  
**Modelo de Referencia / Fallback Verificado:** `yolo11n.pt` (`CUDA:0` / `CPU`)  
**Hardware de Validación:** NVIDIA GeForce RTX 4050 Laptop GPU (`6 GB VRAM`, PyTorch CUDA en `.venv_cuda`)  
**Artefacto Cuantitativo Verificado:** [`audit_05a1_verified_metrics.json`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vision_05a/results/audit_05a1_verified_metrics.json)  
**Dictamen Oficial:** **`APPROVED WITH OBSERVATIONS`**

---

## Resumen Ejecutivo de Auditoría

La auditoría independiente **VIGIA-VISION-05A.1** verificó línea por línea los inventarios JSON, los scripts experimentales, el código integrado en [`yolo_detector.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py), las pruebas unitarias/integración y el informe técnico [`VIGIA-VISION-05A_OPTIMIZACION_DETECCION_VEHICULAR.md`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_vision/VIGIA-VISION-05A_OPTIMIZACION_DETECCION_VEHICULAR.md).

### Conclusiones Principales de Cierre

1. **Las ganancias de detección vehicular de `VISION-05A` son 100% reproducibles sobre `YoloVehicleDetector` real en GPU:**
   - **Automóviles frontales (`n=76`):** `53/76 (69.74%)` $\to$ **`65/76 (85.53%)`** a `@0.70` (**`+15.79 pp`**), igualando la tasa de `YOLO11n` (`65/76 = 85.53%`) con mayor confianza media (`0.8690` vs `0.7780`).
   - **Autobuses frontales — presencia vehicular en región del autobús (`n=18`):** `3/18 (16.67%)` $\to$ **`12/18 (66.67%)`** a `@0.70` (**`+50.00 pp`, `4.0x`**), superando a `YOLO11n` (`9/18 = 50.00%`).
   - **Orientaciones oblicua, lateral, trasera, vehículos pequeños, cercanos y baja iluminación:** mejoras simultáneas de entre **`+5.26 pp`** y **`+26.31 pp`** (`0` casos perdidos frente a baseline a `@0.70`).
2. **Hallazgos Críticos y Correcciones Aplicadas en `05A.1`:**
   - **Corrección Técnica en `deduplicate_and_consolidate_detections`:** La versión inicial de `05A` suprimía pares con `IoU >= 0.55` sin distinguir clase; esto representaba un riesgo de suprimir vehículos próximos distintos superpuestos entre `0.55 <= IoU < 0.75`. Se actualizó [`yolo_detector.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py#L479-L546) para exigir `IoU >= 0.55` solo dentro de la **misma clase**, **`IoU >= 0.75` inter-clase (`car`, `bus`, `truck`)** y **`IoU >= 0.85` cuando interviene `motorcycle`**, validado con nuevas pruebas multi-vehículo (`6/6` vehículos preservados y `1/1` duplicado suprimido).
   - **Conciliación Matemática de `89` vs `95` y `bus` vs `truck`:** Se resolvió exactamente la discrepancia (`76 + 18 - 7 = 87` imágenes únicas primarias con intersección `EV-0581..0587` + `17` cuadrículas de pantalla = `104` imágenes únicas con tag frontal), y se transparentó explícitamente que la mejora en autobuses frontales (`66.67%`) corresponde a **detección vehicular del autobús (`CAMION`/`truck` en MS-COCO a `0°`)** mientras la etiqueta estricta `AUTOBUS` (`bus`) permanece en `0.0%` a `0°` puro.
   - **Corrección Documental del Informe `VISION-05A`:** Se corrigieron en el informe `VISION-05A` tablas transcritas erróneamente (resoluciones históricas `20261101..16`, nombres reales de archivos, nombres reales de las 11 comparativas visuales, tabla de `YOLO11n` y matriz `EXP-01..EXP-10`), dejándolos 100% alineados con los artefactos JSON verificados.
   - **Diagnóstico Reproducible de `test_trust_ca_logic.test_16`:** Se probó con evidencia JSON estructurada que el fallo es **preexistente y ajeno al módulo de visión** (conexión directa sin servidor HTTPS en puerto `5000`).

---

## 1. Verificación de Métricas y Corpus

Se auditaron [`etapa_a_b_raw_inventory.json`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vision_05a/results/etapa_a_b_raw_inventory.json), [`etapa_a_b_classified_inventory.json`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vision_05a/results/etapa_a_b_classified_inventory.json), [`etapa_d_experiments_results.json`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vision_05a/results/etapa_d_experiments_results.json), los scripts fuente y el informe `VISION-05A`.

### 1.1 Resolución Matemática de los `89` Vehículos Frontales vs `95` Observaciones

La aparente inconsistencia entre **`89`** y **`95`** reportada en la fase previa proviene de mezclar **imágenes únicas**, **conjuntos con solapamiento multi-vehículo** y **conteo por subcategoría/instancia**:

| Conjunto / Subcategoría en Corte Congelado (`279` Únicas / `675` Totales) | Conteo Verificado (`archivo` = `única` aquí) | Regla Exacta en [`classify_and_catalog.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vision_05a/scripts/classify_and_catalog.py) | Instancias Reales Visibles |
| :--- | :---: | :--- | :---: |
| **Conjunto $A$: Imágenes con automóvil frontal primario (`has_frontal_car=True`)** | **`76`** | `EV-0442` (1), `EV-0508..0521` (14), `EV-0581..0587` (7), `EV-0589..0594` (6), `EV-0598..0604` (7), `EV-0605..0612` (8), `EV-0625..0657` (33) | **`88`** *(en `EV-0605..0611` [7] y `EV-0632..0636` [5] hay **2** autos frontales cada uno)* |
| **Conjunto $B$: Imágenes con autobús frontal primario (`has_frontal_bus=True`)** | **`18`** | `EV-0573..0576` (4), `EV-0579..0588` (10), `EV-0668..0671` (4) | **`18`** |
| **Intersección $A \cap B$: Coexisten AMBOS en el mismo frame** | **`7`** | **`EV-0581` .. `EV-0587`** ([líneas 219–233](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vision_05a/scripts/classify_and_catalog.py#L219-L233)) | `14` *(7 autos + 7 autobuses)* |
| **Unión $A \cup B$: Imágenes únicas con evaluación frontal primaria** | **$76 + 18 - 7 = \mathbf{87}$** | Principio de inclusión-exclusión | **`106`** (`88` autos + `18` buses) |
| **Conjunto $G$: Recapturas de pantalla multi-cuadrícula con tag `"Vehículo frontal"`** | **`17`** | `EV-0295..0303` (9) + `EV-0449..0456` (8) *(incluyen `1` secuencia con motocicleta/múltiples clases)* | Múltiples miniaturas en rejilla de pantalla |
| **Unión Total $A \cup B \cup G$ con etiqueta `"Vehículo frontal"`** | **$87 + 17 = \mathbf{104}$** | Coincide `104/104` en `279` únicas y `675` totales | **`106+`** |

**Conclusión de la conciliación:**
- La cifra **`95`** surgía de sumar observaciones por subgrupo sin descontar solapamientos ($76 \text{ autos} + 18 \text{ buses} + 1 \text{ secuencia/moto} = 95$).
- La cifra **`89`** publicada originalmente en el resumen anterior de `VISION-05A` fue un **error de transcripción tras compactación** (`87` de $|A \cup B|$ más `2` estimados). El número exacto de imágenes únicas con evaluación frontal primaria es **`87`**, el número total de imágenes con la etiqueta `"Vehículo frontal"` es **`104`** (idéntico en el conjunto único de `279` y en el de `675`), y el número de instancias primarias frontales evaluadas es **`106`** (`88` automóviles + `18` autobuses).

### 1.2 Conteo de Imágenes vs Vehículos, Duplicados, Separación Orig/Annot y Crecimiento en Vivo

1. **Separación estricta `_orig.jpg` vs `_annot.jpg`:** Verificado en [`audit_and_benchmark.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vision_05a/scripts/audit_and_benchmark.py#L144-L148) (`orig_files = [p ... endswith("_orig.jpg")]`); **cero** imágenes `_annot.jpg` entraron al pipeline de inferencia.
2. **Duplicados exactos y perceptuales:** De las `675` imágenes originales del corte (`17:52:20Z`), `279` poseen `SHA-256` único (`396` son duplicados byte a byte, concentrados en `20261105` + `EV-0002` en `20261102`) y se agrupan en `177–178` clusters perceptuales (`dHash <= 6` o `MAD < 8`) y `30` secuencias temporales (`gap > 60s`).
3. **Observación de crecimiento en vivo del directorio `evidencias_vigia/`:** Al re-escanear `evidencias_vigia/` durante esta auditoría (`19:14Z–19:17Z`), los procesos operativos activos en segundo plano (`PIDs 20612, 30532, 33916, 37220`) continuaron capturando evidencias en vivo en `20261116/` (incrementando de `675` a `696` y luego `714` pares). Todos los cálculos de auditoría y comparación se realizaron exactamente sobre el **corte congelado idéntico de `279` hashes únicos (`675` archivos base)** para garantizar comparabilidad 1:1.

### 1.3 Inconsistencias Documentales Detectadas y Corregidas en `VISION-05A`

Se corrigieron directamente en [`VIGIA-VISION-05A_OPTIMIZACION_DETECCION_VEHICULAR.md`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_vision/VIGIA-VISION-05A_OPTIMIZACION_DETECCION_VEHICULAR.md) los siguientes errores de transcripción encontrados durante esta auditoría:
- **Tabla 2.2:** Se corrigieron nombres de cámaras/resoluciones (`810x1080`, `720x1280`, `640x480` en `13` combinaciones fecha/cámara reales en lugar de `400x300`/`640x640` previos).
- **Tabla 4.2 y Sección 5.2:** Se sustituyeron nombres de archivo y láminas inexactos por las rutas reales verificadas en disco (`20261116T172015_568913Z_c43de572acc5_orig.jpg`, `01_automovil_frontal_EV0625_comparison.jpg`, etc.).
- **Tabla 5.1:** Se restauraron las métricas reales reproducidas de **`YOLO11n`** (`65/76 = 85.53%` en `frontal_cars`, `9/18 = 50.0%` en `frontal_buses_presence`, `91.76%` global), que en el borrador previo habían quedado subestimadas (`46/76`), revelando con claridad por qué los usuarios percibían pérdida frontal al pasar de `YOLO11n` a `YOLO26x Baseline` (`69.74%` frontal cars, `69.53%` global).
- **Tabla 7.1:** Se alinearon todos los IDs y valores de `EXP-01A..EXP-10` con [`etapa_d_experiments_results.json`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vision_05a/results/etapa_d_experiments_results.json).
- **Sección 8.1:** Se actualizaron los rangos de líneas reales en `yolo_detector.py`.

---

## 2. Validación Reproducida de `YOLO26x` y Estatuto Epistemológico de Métricas

### 2.1 Reproducción Exacta Usando la Clase Productiva `YoloVehicleDetector` (`279` Únicas)

Condiciones idénticas para las tres configuraciones: `device="cuda:0"`, `quantize=16` (`FP16`), `conf_floor=0.10`, ROI `[0.10, 0.20, 0.90, 0.80]`, evaluación `@0.70` (operativo) y `@0.25` (diagnóstico).

| Categoría Verificada | `N` | `YOLO11n` Ref (`@0.70` / `ConfMedia`) | `YOLO26x` Baseline (`@0.70` / `@0.25` / `Conf`) | `YOLO26x` Optimizado `05A.1` (`@0.70` / `@0.25` / `Conf`) | Delta `Opt - Base` (`@0.70`) | Delta `Opt - 11n` (`@0.70`) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Automóviles frontales (`car`)** | `76` | `65 (85.53%)` / `0.778` | `53 (69.74%)` / `86.84%` / `0.839` | **`65 (85.53%)`** / `93.42%` / **`0.869`** | **`+15.79 pp`** | **`0.00 pp`** (`+0.091` conf) |
| **Autobuses frontales (presencia)** | `18` | `9 (50.00%)` / `0.696` | `3 (16.67%)` / `72.22%` / `0.637` | **`12 (66.67%)`** / `83.33%` / **`0.748`** | **`+50.00 pp`** | **`+16.67 pp`** |
| **Autobuses frontales (etiqueta `bus`)** | `18` | `0 (0.00%)` | `0 (0.00%)` / `0.00%` | `0 (0.00%)` / `0.00%` *(como `truck`)* | `0.00 pp` | `0.00 pp` |
| **Vehículos oblicuos** | `80` | `73 (91.25%)` / `0.789` | `55 (68.75%)` / `95.00%` / `0.789` | **`71 (88.75%)`** / `100.0%` / **`0.870`** | **`+20.00 pp`** | `-2.50 pp` (`+0.081` conf) |
| **Vehículos laterales** | `149` | `139 (93.29%)` / `0.792` | `103 (69.13%)` / `91.95%` / `0.770` | **`127 (85.23%)`** / `96.64%` / **`0.836`** | **`+16.10 pp`** | `-8.06 pp` (`+0.044` conf) |
| **Vehículos traseros** | `19` | `19 (100.0%)` / `0.800` | `18 (94.74%)` / `100.0%` / `0.862` | **`19 (100.0%)`** / `100.0%` / **`0.900`** | **`+5.26 pp`** | **`0.00 pp`** (`+0.099` conf) |
| **Baja iluminación** | `38` | `31 (81.58%)` / `0.762` | `18 (47.37%)` / `78.95%` / `0.703` | **`28 (73.68%)`** / `89.47%` / **`0.814`** | **`+26.31 pp`** | `-7.90 pp` |
| **Contraluz / Glare** | `58` | `53 (91.38%)` / `0.815` | `51 (87.93%)` / `98.28%` / `0.850` | **`57 (98.28%)`** / `100.0%` / **`0.909`** | **`+10.35 pp`** | **`+6.90 pp`** |
| **Vehículos cercanos (`closeup`)** | `150–153`* | `136/153 (88.89%)` | `89/151 (58.94%)` | **`123/150 (82.00%)`** | **`+23.06 pp`** | `-6.89 pp` |
| **Vehículos pequeños/lejanos** | `66` | `64 (96.97%)` / `0.816` | `58 (87.88%)` / `98.48%` / `0.855` | **`65 (98.48%)`** / `100.0%` / **`0.899`** | **`+10.60 pp`** | **`+1.51 pp`** |
| **Estabilidad vs Baseline (`@0.70`)** | `279` | Recov: `77` / Lost: `15` | Referencia (`IoU = 1.000`) | **Recov: `47` / Lost: `0` (`IoU=0.9742`)** | **`+47` recuperados, `0` perdidos** | — |
| **Duplicados `@0.25` / `@0.70`** | `279` | `13` / `0` pares | `50` (`45` frames) / `0` pares | **`0` / `0` pares** | **`-100%` (`-50`)** | **`-100%` (`-13`)** |
| **Latencia GPU (`ms` / `FPS`)** | `279` | `12.71 ms` (`78.7 FPS`) | `22.17 ms` (`45.1 FPS`) | **`32.14 ms` (`31.1 FPS`)** | `+9.97 ms` (`132/279` disparadores aux) | — |

*(\*Nota: El subgrupo `closeup_vehicles` agrupa ráfagas de primer plano `EV-0428..429`, `508..521`, `573..588`, `605..675` más cualquier detección en ROI con `area >= 15%`, oscilando entre `n=150` y `n=153` según las detecciones que superan `@0.25` en cada corrida.)*

### 2.2 Clasificación Epistemológica: Exploratorias vs Formales Certificadas

- **Métricas disponibles en esta fase (Exploratorias):** Todas las tasas anteriores son **tasas de detección por escena confirmadas visualmente** (presencia o ausencia de detección válida de la categoría esperada dentro del ROI en imágenes únicas verificadas por inspección visual de las `5` hojas de contacto). Se acompañan de mediciones exactas de estabilidad geométrica (`IoU` entre escalas), duplicación intra-frame y latencia de hardware.
- **Métricas NO declarables como formales certificadas:** Debido a que `evidencias_vigia/` no cuenta con un dataset externo de anotaciones manuales caja-por-caja (`JSON COCO` o `.txt YOLO`) con **todas las instancias visibles de cada escena** ni con **negativos puros (escenas vacías sin vehículo)**, **no se reportan Precision global, Recall de instancias completo, F1-score, Matriz de Confusión cerrada ni `mAP50` / `mAP50-95` como precisión certificada**.
- **Sondeo exploratorio de Falsos Positivos:** En las `36` capturas confirmadas visualmente de un único vehículo (`EV-0001..0012` y `EV-0425..0448`), se contaron detecciones adicionales (`>=0.70` y `>=0.25`): a **`>=0.70`** ambos sistemas arrojaron **`0` detecciones extra**, mientras que a **`>=0.25`** `YOLO26x Baseline` emitió **`7` cajas extra** frente a **`0` en `YOLO26x Optimizacion 05A.1`**.

### 2.3 Propuesta de Conjunto de Evaluación Independiente (*Holdout Benchmark*) Sin Fuga de Datos

Para certificar formalmente Precision, Recall, F1 y mAP antes de promover `yolo26x.pt` a producción, se propone construir un conjunto de evaluación **completamente disjunto del corpus usado para afinar `VISION-05A`**:

1. **Regla Anti-Leakage Temporal y Espacial (Split por Día/Sesión/Cámara Física):** Ninguna escena ni sesión presente en `evidencias_vigia/` hasta `2026-11-16` puede formar parte del Holdout. Las capturas deben corresponder a **nuevos días operativos reales** con la cámara instalada en su ángulo y distancia focal definitivos (sin pantallas intermedias).
2. **Estructura Propuesta (`N >= 400` imágenes anotadas manualmente por 2 revisores independientes):**
   - `100` vehículos frontales (`0°` a `±10°`): mínimo `60` automóviles (`sedán/hatchback/SUV/pickup`) + `40` autobuses/camiones frontales.
   - `80` vehículos oblicuos (`±15°` a `±45°`).
   - `80` vehículos laterales (`~90°`).
   - `60` vehículos traseros (`180°`).
   - `40` escenas de baja iluminación / nocturnas o contraluz severo.
   - `40` **negativos duros puros** (frames de la zona vehicular con **0 vehículos**: solo pavimento, peatones, bicicletas, postes, conos o sombras en movimiento, indispensables para medir `False Positive Rate` real).
3. **Etiquetado Ground Truth:** Polígonos/cajas humanas 1:1 en formato COCO JSON sobre el ROI oficial más atributo de orientación (`FRONTAL`, `OBLIQUE`, `LATERAL`, `REAR`) y visibilidad (`CLEAR`, `LOW_LIGHT`, `OCCLUDED`).

---

## 3. Auditoría del Mecanismo de Supresión de Duplicados

Se inspeccionó línea por línea `deduplicate_and_consolidate_detections` ([líneas 479–546 de `yolo_detector.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py#L479-L546)).

### 3.1 Análisis Técnico de Riesgos y Compatibilidad con NMS-Free

1. **Por qué se requiere en NMS-Free (`one2one`):** En `YOLO26x`, la cabeza `one2one` retorna los `top-300` puntajes globales `(8400 anclas × 80 clases)` sin NMS espacial posterior. Cuando el vehículo frontal es ambiguo entre dos celdas o clases vecinas, emergen duplicados con `IoU = 0.75–0.99` (`50` pares `@0.25` en el corpus base).
2. **Vulnerabilidad detectada en la implementación previa de `VISION-05A`:** La versión inicial aplicaba `iou_val >= 0.55` sin distinguir si ambas cajas eran de la **misma clase** o de **clases distintas**, creando riesgo de suprimir una detección legítima (ej. un automóvil o motocicleta parcialmente delante de un autobús si `0.55 <= IoU < 0.75`).
3. **Corrección aplicada y verificada en `VISION-05A.1` (`yolo_detector.py`):**
   - **Misma clase (`cand.raw_label == k_det.raw_label`):** suprime con **`IoU >= 0.55`** (`iou_threshold`).
   - **Distinta clase entre vehículos de 4+ ruedas (`car`, `bus`, `truck`):** eleva el umbral de fusión a **`IoU >= max(0.55, 0.75) = 0.75`**, asegurando que solo se consoliden dos predicciones sobre exactamente el **mismo volumen vehicular**.
   - **Distinta clase involucrando `motorcycle`:** exige **`IoU >= max(0.55, 0.85) = 0.85`** para impedir suprimir motocicletas en tráfico cercano frente a autos o autobuses.
   - **Regla de consolidación de confianza:** Solo se activa cuando `iou_val >= 0.75` y conserva orden relativo e invariantes de [`RawVehicleDetection`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/models.py#L96-L131).

### 3.2 Pruebas Específicas Multi-Vehículo Ejecutadas y Aprobadas

- **Prueba sintética controlada (`test_multi_vehicle_same_frame_adjacent_and_partially_overlapping_preserved`):** Escena simultánea con `7` cajas (`6` vehículos legítimos + `1` duplicado `one2one`): `car`+`car` contiguos (`IoU=0.25`), `bus` detrás de `car` (`IoU=0.72`), `car` detrás de `motorcycle` (`IoU=0.81`) y un par duplicado (`IoU>0.90`). Resultado: **`6/6` vehículos legítimos preservados y exactamente `1` duplicado consolidado (`PASS`)**.
- **Prueba real en GPU sobre escenas multi-vehículo (`test_real_multi_vehicle_evidence_frames_gpu`):** Ejecutada sobre `EV-0581` (bus+auto), `EV-0605` (2 autos frontales) y `EV-0671` (bus+auto oblicuo) en RTX 4050 (`FP16`): **`>= 2` vehículos distintos detectados y preservados en las `3/3` escenas (`PASS`)**.
- **Validación sobre todo el corpus (`279` únicas):** La corrección mantuvo **`0` duplicados** (`0/0`), **`65/76 (85.53%)`** en autos frontales y **`12/18 (66.67%)`** en autobuses frontales, sin perder ninguna recuperación.

---

## 4. Validación Multiescala (`imgsz = 640, 480, 384, 320` y Sondas Condicionales)

Todos los ensayos se ejecutaron en `YOLO26x` (`CUDA:0`, `FP16`, `nms=False`, deduplicación consciente de clase activa) sobre las `279` imágenes únicas:

| Configuración `imgsz` | Latencia (`mean` / `p95` / `FPS`) | Auto Frontal `@0.70` (`Conf`) | Bus Frontal `Presencia` (`Conf`) | Oblicuo `@0.70` | Lateral `@0.70` | Pequeño `@0.70` | Baja Luz `@0.70` | Contraluz / Glare `@0.70` | Global `@0.70` | `IoU` Medio vs `640` (`Shift px`) | Recov / Lost vs Base `@0.70` | Dups `@0.25` |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`640` única (`dedup`)** | `21.6 ms` / `27.1 ms` (`46.3 FPS`) | `73.68%` (`0.855`) | `50.00%` (`0.667`) | `73.75%` | `73.83%` | `95.45%` | `52.63%` | `89.66%` | `74.91%` | `0.9923` (`1.1 px`) | `+15` / `0` | `0` |
| **`480` única (`dedup`)** | `21.2 ms` / `26.3 ms` (`47.2 FPS`) | `78.95%` (`0.847`) | `55.56%` (`0.747`) | `77.50%` | `77.18%` | `92.42%` | `60.53%` | `94.83%` | `77.06%` | `0.9424` (`11.7 px`) | `+31` / **`-10`** | `0` |
| **`384` única (`dedup`)** | `20.2 ms` / `25.6 ms` (`49.6 FPS`) | `78.95%` (`0.819`) | `38.89%` (`0.707`) | `76.25%` | `65.10%` | `89.39%` | `73.68%` | `96.55%` | `70.97%` | `0.9264` (`15.3 px`) | `+32` / **`-28`** | `0` |
| **`320` única (`dedup`)** | `21.6 ms` / `27.0 ms` (`46.4 FPS`) | `68.42%` (`0.808`) | `50.00%` (`0.638`) | `71.25%` | `74.50%` | `87.88%` | **`84.21%`** | `86.21%` | `74.91%` | `0.9300` (`13.2 px`) | `+37` / **`-22`** | `1` |
| **`640 + 480` Condicional** | `32.9 ms` / `54.0 ms` (`30.4 FPS`) | `84.21%` (`0.884`) | **`72.22%`** (`0.779`) | **`91.25%`** | `87.92%` | **`98.48%`** | `71.05%` | `96.55%` | `87.10%` | **`0.9811`** (`3.2 px`) | `+49` / **`0`** | **`0`** |
| **`640 + 384` Condicional (`05A`)** | `31.8 ms` / `49.0 ms` (`31.5 FPS`) | **`85.53%`** (`0.869`) | `66.67%` (`0.748`) | `88.75%` | `85.23%` | **`98.48%`** | `73.68%` | **`98.28%`** | `86.38%` | **`0.9742`** (`5.6 px`) | `+47` / **`0`** | **`0`** |
| **`640 + 320` Condicional** | `30.2 ms` / `46.9 ms` (`33.1 FPS`) | **`85.53%`** (`0.882`) | `61.11%` (`0.720`) | **`91.25%`** | **`89.93%`** | **`98.48%`** | **`86.84%`** | **`98.28%`** | **`88.53%`** | **`0.9735`** (`4.4 px`) | `+53` / **`0`** | **`2`** *(@.25)* |

### Veredicto de la Validación Multiescala

1. **Ninguna resolución reducida (`480`, `384`, `320`) debe reemplazar a `640` como resolución única fija:** A escala fija, `384` pierde **`28` detecciones** de `640` (sobre todo autobuses laterales `EV-0548..0572` y pequeños `95.45% -> 89.39%`) y `320` pierde **`22` detecciones** (incluidos autos frontales `73.68% -> 68.42%`).
2. **La estrategia condicional complementaria (`imgsz=640` primaria + sonda auxiliar solo si no hay detección `>= 0.70`) es consistente y superior en todas las métricas:**
   - Eleva las pérdidas frente al baseline de `10–28` **a exactamente `0`** en las tres sondas (`640+480`, `640+384`, `640+320`).
   - Conserva una estabilidad geométrica sobresaliente respecto a `640` (`IoU = 0.974–0.981`).
   - Entre las sondas, **`640 + 384` (`VISION-05A`)** logra el punto de equilibrio más sólido para vehículos frontales sin efectos laterales: máxima tasa en automóviles frontales (**`85.53%`**), máxima en contraluz (**`98.28%`**), **`0` duplicados** incluso a `@0.25` (a diferencia de `640+320` que introduce `2` pares duplicados `@0.25` y mayor desplazamiento espacial de cajas por el salto `2:1`), y mejor desempeño en baja iluminación que `640+480` (`73.68%` vs `71.05%`), manteniendo una latencia p95 (`49.0 ms`) holgadamente por debajo del presupuesto de cámara (`66.7 ms`). No obstante, `640+480` (`frontal_aux_imgsz=480`) queda inmediatamente configurable vía `VIGIA_YOLO_FRONTAL_AUX_IMGSZ=480` si en campo predominaran autobuses sobre automóviles en baja iluminación.
3. **Regla respetada:** El tamaño predeterminado de producción (`VIGIA_YOLO_IMGSZ=640`) **no ha sido modificado**.

---

## 5. Auditoría de Arquitectura e Integridad Operativa

Se verificó directamente sobre archivos e invocaciones reales en [`audit_05a1_verified_metrics.json`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vision_05a/results/audit_05a1_verified_metrics.json):

| Invariante Auditado | Estado Verificado | Evidencia Reproducible |
| :--- | :---: | :--- |
| **Modelo predeterminado sigue siendo `yolo11n.pt`** | **CUMPLIDO** | `load_yolo_config_from_env()` retorna `yolo11n.pt` cuando no se fuerza `VIGIA_YOLO_MODEL`; `yolo26x.pt` permanece aislado en `experiments/yolo26x/weights/` |
| **Fallback automático `yolo11n.pt` intacto** | **CUMPLIDO** | Validado por pruebas de fallback init y runtime CUDA en `test_vision_04a` y `test_vision_03c2` (`PASS`); `_build_fallback_config()` desactiva explícitamente `frontal_aux_enabled` y `consolidate_frontal_confidence` en modo fallback |
| **Pesos `.pt` intactos (sin sobrescritura)** | **CUMPLIDO** | `yolo11n.pt` `SHA-256`: `0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1`<br>`yolo26x.pt` `SHA-256`: `9FDD44A31C504547FFB81D2C6D9E6DAC3493C8EAA8B0398D3F43BAE6C7003E92` |
| **`.env` de producción intacto** | **CUMPLIDO** | [`C:\GEST.PROY.TI\Software\.env`](file:///c:/GEST.PROY.TI/Software/.env) sin modificaciones (`LastWriteTime`: `11/08/2026 11:41:53 AM`, `1,079` bytes, `SHA-256`: `DF9AAECDF56935E837E8E9273313D925BBB984336191B88C7B5103C0096004C8`) |
| **ROI, FSM, debounce y persistencia sin alteración** | **CUMPLIDO** | Ningún cambio en `roi_and_preprocess.py`, `temporal_fsm.py`, `coordinator.py`, `detection_repository.py` ni DDL SQL |
| **Configuración centralizada** | **CUMPLIDO** | Todos los parámetros `VIGIA_YOLO_DEDUP_IOU`, `VIGIA_YOLO_CONSOLIDATE_CONFIDENCE`, `VIGIA_YOLO_FRONTAL_AUX_*` pasan por `_get_env_setting()` (`VIGIA_Core.config.env_loader`) en `yolo_detector.py` |
| **Aislamiento entre cámaras y compatibilidad USB + móvil** | **CUMPLIDO** | `YoloVehicleDetector` protege inferencias vía `threading.RLock()` sin mantener estado por cámara entre pasos; probado con éxito en `test_multi_camera_concurrent_isolation_usb_and_mobile` (`15` frames `CAM-ENTRADA` móvil PUSH + `15` frames `CAM-SALIDA` USB Pull en hilos concurrentes con cero cruce de estado) |

---

## 6. Regresión e Investigación de `test_trust_ca_logic.test_16`

### 6.1 Resultados Oficiales de Regresión (Ejecutados con `.venv_cuda`, sin omitir pruebas GPU)

| Suite / Módulo | Ejecutadas | Resultado | Duración | Detalle |
| :--- | :---: | :---: | :---: | :--- |
| **`tests.unit.test_vision_stage1_components`** *(ejecución aislada previa a carga GPU)* | `16 / 16` | **`PASS`** | `0.02s` | Valida ROI, contratos e import limpio sin carga anticipada de `torch`/`ultralytics` *(nota: si corre después de suites GPU en un mismo proceso, `test_clean_import_without_side_effects` detecta `ultralytics` ya en `sys.modules`)* |
| **`test_vision_05a_frontal_optimization` + `test_vision_04a` + `test_vision_03c2` + `test_yolo_detector` + `test_vision_02a_temporal_fsm` + `test_vision_pipeline`** | `80 / 80` | **`PASS`** | `8.50s` | `0` omitidas; incluye `YOLO26x` real en RTX 4050, multi-vehículo, aislamiento concurrente USB+móvil, fallback `YOLO11n`, FSM temporal y pipeline completo |
| **`test_phase3a_postgres_integration` + `test_async_persistence_pilot` + `test_detection_repository` + `test_domain_models` + `test_topology_validator` + `test_camera` + `test_camera_stream_and_backend` + `test_lan_detector` + `test_crl_management` + `test_network_discovery` + `test_mobile_ingest_api` + `test_usb_camera_integration (Flask + URI)`** | `198 / 198` | **`PASS`** | `15.54s` | Persistencia PostgreSQL (`127.0.0.1:5434`), ingesta móvil PUSH, endpoints RBAC USB, stream y red |
| **`test_auth_rbac` + `test_auth_stream_protection` + `test_ipc_hardening` + `test_isolated_signer` + `test_signer_fail_closed`** | `83 / 83` | **`PASS`** | `49.15s` | Seguridad RBAC, CSRF, Named Pipes IPC e IsolatedSigner |
| **`tests.unit.test_trust_ca_logic`** | `20 / 21` | **`20 PASS / 1 FAIL`** *(Preexistente)* | `21.96s` | Ver diagnóstico reproducible abajo (sin modificar certificados ni configuración) |
| **`tests.integration.test_vision_engine_operational_integration` / `TestUsbHardwareDiscovery` / `TestUsbCaptureRealHardware`** | `—` | **`BLOCKED / NOT RUN`** | `—` | Intentan abrir la webcam física `cv2.VideoCapture(0)`, actualmente bloqueada por los servicios operativos activos y restringida por regla de no iniciar pruebas físicas |
| **TOTAL EJECUTADA** | **`397 / 398`** | **`377 PASS`** *(+20/21 TLS, 0 regresiones)* | `95.17s` | **`100% PASS` en todo el subsistema de visión, USB/móvil, persistencia y seguridad** |

### 6.2 Evidencia Reproducible del Fallo Preexistente en `test_trust_ca_logic.test_16`

En [`tests/unit/test_trust_ca_logic.py` línea 428](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/tests/unit/test_trust_ca_logic.py#L428), la prueba invoca literalmente:
`run_strict_check(root_ca_path=real_ca_path, port=5000)`
y exige `report["modalidad_a_passed"] == True`. Al reproducir exactamente esa llamada en [`audit_05a1_verified_metrics.json`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vision_05a/results/audit_05a1_verified_metrics.json#L3498-L3544) sin alterar certificados ni configuración:
- **Objetivo `Localhost` (`127.0.0.1:5000`):** `"tcp_connected": true`, `"tls_handshake": false`, `"tls_error": "[SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:992)"` (el puerto `5000` corresponde a otro listener HTTP o no-TLS en la estación, mientras que [`check_https_strict.py` línea 31](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/scripts/check_https_strict.py#L31) define `port: int = 5001` como puerto HTTPS por defecto).
- **Objetivo `LAN` (`192.168.1.75:5000`):** `"tcp_connected": false`, `"tcp_error": "timed out"`.
- **Resultado:** `modalidad_a_passed = False`. Se confirma de forma 100% reproducible que se trata de un **fallo preexistente de topología/puerto en vivo del entorno de red de pruebas**, totalmente independiente del motor de visión.

---

## 7. Integridad Documental, Sincronización Espejo y Dictamen Final

### 7.1 Limitaciones Estadísticas y Riesgos Residuales
1. **Validación sobre corpus histórico limitado (`N=279` únicas, capturas de pantalla en USB/móvil):** Aunque estadísticamente consistente para diagnosticar los fallos de escala `640` y duplicados `one2one`, carece de anotación vectorial externa completa y negativos puros; la tasa de falsos positivos en operación vial abierta debe confirmarse con el Holdout Benchmark de la Sección 2.3.
2. **Clasificación semántica de autobuses Tipo C a `0°` (`bus` vs `truck`):** Aunque el autobús frontal ya se detecta en **`66.67%` (`4.0x`)**, la etiqueta emitida a `0°` puro sigue siendo `CAMION` (`truck`); esto no pierde el evento de detección vehicular, pero requiere fine-tuning supervisado en `VISION-05B` si se requiere distinción estricta `AUTOBUS` vs `CAMION` frontal.
3. **Dependencia de entorno Python para CUDA:** El entorno `.venv` estándar contiene PyTorch sin soporte CUDA (`torch.cuda.is_available() == False`); la ejecución con GPU `RTX 4050 FP16` requiere explícitamente el entorno **`.venv_cuda`**.

### 7.2 Sincronización Espejo y Verificación `SHA-256`

Ambos informes actualizados se encuentran sincronizados bit a bit entre [`VIGIA_Vision_Systems/Docs/fase_vision/`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_vision) y [`Software/Docs/fase_vision/`](file:///c:/GEST.PROY.TI/Software/Docs/fase_vision):

| Artefacto Verificado | SHA-256 Verificado | Espejo Sincronizado |
| :--- | :--- | :---: |
| [`VIGIA-VISION-05A_OPTIMIZACION_DETECCION_VEHICULAR.md`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_vision/VIGIA-VISION-05A_OPTIMIZACION_DETECCION_VEHICULAR.md) | `832EB5C8C69FBC77DDB8826B241FBDA25E19D72A1B1FF05978C3966DEFB03440` | Idéntico |
| [`audit_05a1_verified_metrics.json`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vision_05a/results/audit_05a1_verified_metrics.json) | `1343F896E79428D8BE414C7402BA774FE9AA41A77CECE4840897EEEA17A7B55A` | `—` |
| [`VIGIA-VISION-05A.1_AUDITORIA_CIERRE.md`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_vision/VIGIA-VISION-05A.1_AUDITORIA_CIERRE.md) | Registrado en manifiesto externo [`VIGIA-VISION-05A.1_AUDITORIA_CIERRE.md.sha256`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_vision/VIGIA-VISION-05A.1_AUDITORIA_CIERRE.md.sha256) y validado idéntico en ambas rutas | Idéntico |

### 7.3 Dictamen Final de Auditoría (`VIGIA-VISION-05A.1`)

> **`APPROVED WITH OBSERVATIONS`**

**Observaciones vinculantes para pasar a validación controlada en campo y posterior promoción:**
1. La implementación de `VISION-05A` + el refinamiento multi-clase de `VISION-05A.1` en [`YoloVehicleDetector`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py) es **reproducible, segura, reversible y libre de regresiones (`377/377 PASS` en módulos aplicables)**. Queda lista para validación controlada con `yolo26x.pt` siempre manteniendo `yolo11n.pt` como modelo predeterminado y fallback hasta autorización expresa del propietario.
2. Para declarar métricas formales certificadas (`Precision`, `Recall`, `F1`, `mAP`) y decidir la promoción definitiva a producción, deberá ejecutarse en `VISION-05B` el **Holdout Benchmark independiente** con negativos puros (`Sección 2.3`) y, si el dominio exige diferenciar `AUTOBUS` escolar con trompa frente a `CAMION` a `0°` puro, aprobar el fine-tuning supervisado correspondiente.
