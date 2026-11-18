# VIGIA-VISION-03B — Construcción del Benchmark Vehicular `VIGIA-BENCH-v1`

- **Proyecto:** VIGÍA Vision Systems  
- **Fase:** `VIGIA-VISION-03B` (Construcción reproducible del conjunto de evaluación con Ground Truth)  
- **Fecha:** 2026-11-13  
- **Versión del Benchmark:** `VIGIA-BENCH-v1` (Semilla `manifest_v1_seed.json`, SHA-256: `a1b154c1398172f7dbf1a0b51e0067de86ef0cfece2aca8ab40711e80cce3a7e`)  
- **Dictamen Final:** **`BENCHMARK INCOMPLETE`** — Infraestructura, inventario, deduplicación, esquema y herramientas completadas sin modificar código de producción; se detiene antes de declarar métricas hasta recibir **anotaciones manuales humanas (`150` imágenes en `PENDING_HUMAN_REVIEW`)**, **imágenes negativas reales (`0/60`)** y **muestras vehiculares faltantes**.

---

## 1. Inventario del corpus

Se inspeccionó la totalidad del repositorio de evidencias [evidencias_vigia](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/evidencias_vigia) (verificando que no existen imágenes ni videos de prueba fuera de esta ruta en el workspace). Se registraron **`604` imágenes originales `*_orig.jpg`** (`1,208` archivos JPEG si se incluyen sus pares renderizados `*_annot.jpg`), distribuidas en **`208` hashes SHA-256 únicos**.

### 1.1 Desglose global por origen y duplicados exactos

| Categoría real verificada | Total `*_orig.jpg` | Hashes SHA-256 únicos | Proporción | Detalle técnico comprobado |
| :--- | :---: | :---: | :---: | :--- |
| **`SYNTHETIC_STOCK`** (Ultralytics `bus.jpg`, EMT Madrid `M1 SOL/SEVILLA` + 4 peatones) | **399** | **3** | `66.06%` | `392` copias exactas en `640x480` (`SHA: 81e969e79ce5...`, `Laplacian=4487.308`, `Y=116.4`) generadas el `2026-11-05` (`CAM-ENTRADA`: 158, `CAM-SALIDA`: 120, `CAM-03`: 76, `CAM-04`: 38) + `5` copias en `810x1080` (`SHA: 37c80acd7d27...`) + `2` copias recodificadas `810x1080` (`SHA: 22dd33ab1890...`). |
| **`SCALE_MODEL_LAB`** (Vehículos a escala en escritorio/mano) | **185** | **185** | `30.63%` | `13` sesiones temporales entre `2026-11-04` y `2026-11-14` (`CAM-ENTRADA`: 55, `CAM-SALIDA`: 130). Cupé rojo a escala (`TOYOTA`), autobús escolar amarillo die-cast con trompa frontal, cupé color vino de fondo y `1` chasis LEGO sin carrocería (`20261104T163435_585610Z_5f6dd24bfe47_orig.jpg`). |
| **`SCREEN_RECAPTURE`** (Móvil apuntando a pantalla de PC) | **20** | **20** | `3.31%` | `2` sesiones en `CAM-ENTRADA` (`2026-11-05 15:12–15:13`: 9 frames; `2026-11-11 22:40–22:41`: 11 frames, todos `720x1280`): búsquedas de Google Imágenes (`"autos"`, `"Tipos de Carrocerías"`, `"vehiculos"`) con múltiples miniaturas e iconos. |
| **`REAL_FULL_SCALE`** (Vehículos 1:1 en calle/acceso) | **0** | **0** | `0.00%` | **No existen capturas reales de vehículos tamaño real** tomadas por las cámaras del sistema. |
| **`NEGATIVE_CONTROL`** (Escenas sin vehículos) | **0** | **0** | `0.00%` | **No existen negativos almacenados**, pues el runtime solo persiste en disco cuando `vehicle_detected=True`. |
| **Total inspeccionado** | **604** | **208** | `100.00%` | `0` imágenes duplicadas físicamente fuera de `evidencias_vigia/`. |

### 1.2 Desglose de las `205` capturas físicas por sesión, fecha, cámara, resolución, luminancia y nitidez

| Sesión | Fecha (UTC) | Cámara | Resolución | Total bruto | Retenidas (`VIGIA-BENCH-v1`) | Dominio | Nitidez `Laplacian` (mín..med..máx) | Luminancia `Y` (mín..med..máx) | Condición visual dominante |
| :---: | :--- | :--- | :---: | :---: | :---: | :--- | :---: | :---: | :--- |
| `S01` | `2026-11-04` | `CAM-ENTRADA` | `720x1280` | 1 | **1** | `SCALE_MODEL_LAB` | `~61.3` | `~86.1` | Chasis LEGO en escritorio (`IGNORE`), sombra. |
| `S02` | `2026-11-04` | `CAM-ENTRADA` | `720x1280` | 9 | **9** | `SCALE_MODEL_LAB` | `33.9..98.8` | `86.1..144.9` | Cupé rojo en mano al sol y en escritorio. |
| `S03` | `2026-11-05` | `CAM-ENTRADA` | `720x1280` | 6 | **6** | `SCALE_MODEL_LAB` | `55.9..125.8` | `130.3..138.1` | Cupé rojo sobre cuaderno y mesa. |
| `S04` | `2026-11-05` | `CAM-ENTRADA` | `720x1280` | 9 | **9** | `SCREEN_RECAPTURE` | `215.2..932.2` | `85.5..120.7` | Monitor con resultados de Google Imágenes. |
| `S05` | `2026-11-06` | `CAM-ENTRADA` | `720x1280` | 5 | **5** | `SCALE_MODEL_LAB` | `29.6..451.1` | `72.7..135.5` | Cupé rojo sobre escritorio (oclusión por dedos). |
| `S06` | `2026-11-06` | `CAM-ENTRADA` | `720x1280` | 7 | **7** | `SCALE_MODEL_LAB` | `29.6..451.1` | `72.7..135.5` | Cupé rojo con dedos/mano cubriendo techo/carrocería. |
| `S07` | `2026-11-06` | `CAM-ENTRADA` | `720x1280` | 2 | **2** | `SCALE_MODEL_LAB` | `29.6..451.1` | `72.7..135.5` | Cupé rojo sobre escritorio, lateral completo. |
| `S08` | `2026-11-10` | `CAM-ENTRADA` | `720x1280` | 10 | **10** | `SCALE_MODEL_LAB` | `18.0..37.0..68.2` | `124.2..139.6..152.3` | Cupé rojo sobre mesa blanca (reflejos altos). |
| `S09` | `2026-11-11` | `CAM-ENTRADA` | `720x1280` | 11 | **11** | `SCREEN_RECAPTURE` | `129.7..280.2..452.0` | `110.6..125.2..129.9` | Monitor Google Imágenes `"vehiculos"`. |
| `S10` | `2026-11-14` | `CAM-ENTRADA` | `640x480` | 1 | **1** | `SCALE_MODEL_LAB` | `5.9` | `71.3` | Cámara USB en mano en habitación oscura + desenfoque. |
| `S11` | `2026-11-14` | `CAM-ENTRADA` | `720x1280` | 5 | **4** | `SCALE_MODEL_LAB` | `9.3..35.7` | `37.1..100.2` | Cupé rojo con luz verde tenue (subexpuesto). |
| `S12` | `2026-11-14` | `CAM-ENTRADA` | `720x1280` | 9 | **8** | `SCALE_MODEL_LAB` | `9.3..27.9..35.7` | `37.1..86.3..100.2` | Cupé rojo iluminado junto a teclado y cámara web. |
| `S13` | `2026-11-14` | `CAM-SALIDA` | `640x480` | 32 | **10** | `SCALE_MODEL_LAB` | `2.0..7.1..25.0` | `13.7..125.7..159.3` | USB oscuro/subexpuesto y desenfoque severo (`22` descartadas). |
| `S14` | `2026-11-14` | `CAM-SALIDA` | `640x480` | 15 | **11** | `SCALE_MODEL_LAB` | `2.0..7.1..25.0` | `13.7..125.7..159.3` | Cupé rojo con reflejo fuerte en mesa y oclusión por mano. |
| `S15` | `2026-11-14` | `CAM-SALIDA` | `640x480` | 83 | **54** | `SCALE_MODEL_LAB` | `2.0..7.1..25.0` | `13.7..125.7..159.3` | Autobús amarillo die-cast + cupé rojo + cupé vino (`29` ráfagas descartadas). |
| **Total físico** | **6 días** | **2 cámaras** | `640x480`, `720x1280` | **205** | **148** | `128 SCALE` + `20 SCREEN` | — | — | `57` ráfagas consecutivas casi idénticas eliminadas. |

---

## 2. Estrategia de muestreo

La herramienta reproducible [bench_tool.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/benchmarks/vigia_bench_v1/bench_tool.py) implementa un filtrado en dos etapas **determinista y verificable** sin copiar ni modificar los JPEG de origen:

1. **Deduplicación exacta por SHA-256 (`SYNTHETIC_STOCK`):**
   - Colapsa los `399` duplicados/recodificaciones de la imagen stock `bus.jpg` de Ultralytics en **exactamente `2` testigos técnicos** (`STOCK_640x480` en `CAM-03` y `STOCK_810x1080` en `CAM-ENTRADA`), etiquetados como `SYNTHETIC_STOCK` para verificación de código y **excluidos por defecto de las métricas de mundo real**.
2. **Deduplicación perceptual y temporal de ráfagas (`SCALE_MODEL_LAB` / `SCREEN_RECAPTURE`):**
   - Las capturas físicas se ordenan cronológicamente dentro de cada cámara y se segmentan en sesiones cuando el intervalo excede `60.0 s`.
   - Dentro de una sesión, un frame solo se incorpora a la semilla `manifest_v1_seed.json` si cumple al menos una condición:
     - Es el **primer frame de la sesión**; o
     - Han transcurrido **`delta_t >= 8.0 s`** respecto al último frame retenido; o
     - La **diferencia media absoluta (`MAD`)** sobre miniatura en escala de grises `32x32` respecto al último frame retenido es **`>= 8.0` niveles** (garantizando cambio de pose, iluminación u oclusión).
   - **Resultado comprobado:** De `604` archivos iniciales se seleccionaron **`150` imágenes semilla no redundantes** (`128` `SCALE_MODEL_LAB` + `20` `SCREEN_RECAPTURE` + `2` `SYNTHETIC_STOCK`), eliminando `397` copias exactas de stock y `57` frames consecutivos casi idénticos en ráfagas (especialmente en `S13` y `S15` de `CAM-SALIDA`).

> [!WARNING]
> **Por qué las `205` (o `212`) capturas originales NO constituyen una muestra estadísticamente representativa:**  
> (1) El `100%` proviene únicamente de frames donde el detector vivo ya superó el umbral de disparo (`>= 0.70`), creando un severo sesgo de supervivencia sin verdaderos negativos (`TN = 0`); (2) El `90.24%` de las físicas corresponden a 3 juguetes repetidos sobre un escritorio y `9.76%` a fotografías de un monitor, con `0` vehículos reales `1:1`; y (3) Existen `57` pares consecutivos prácticamente idénticos separados por `< 1.5 s`.

---

## 3. Protocolo de anotación

Las anotaciones manuales deben registrarse sobre [annotation_sheet_v1.csv](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/benchmarks/vigia_bench_v1/annotation_sheet_v1.csv) o importarse con `bench_tool.py import-csv` respetando estrictamente las siguientes reglas:

### 3.1 Clases admitidas

| Etiqueta `class_label` | Alcance | Regla de anotación y separación |
| :--- | :--- | :--- |
| **`CAR`** | Sedanes, hatchbacks, cupés, SUVs, camionetas cerradas o pickups ligeras. | Si el objeto es un modelo a escala / juguete, anotar `CAR` **y marcar obligatoriamente `is_scale_model = true`** para separar métricas de laboratorio vs calle `1:1`. |
| **`MOTORCYCLE`** | Motocicletas y motonetas (excluir bicicletas sin motor). | Se anota la moto (el conductor va aparte y no se incluye salvo oclusión inseparable del contorno mínimo). |
| **`BUS`** | Autobuses urbanos, escolares o minibuses de pasajeros. | Incluye el autobús escolar amarillo a escala en `CAM-SALIDA` (`is_scale_model = true`). No forzar a `TRUCK` aunque tenga trompa frontal. |
| **`TRUCK`** | Camiones de carga, tráileres, volquetes o furgones comerciales pesados. | Excluir camionetas familiares; exigir rasgos estructurales inequívocos de carga. |
| **`IGNORE`** | Regiones vehiculares ambiguas o fuera de protocolo. | **No penalizan al detector como `FP` si los predice, ni como `FN` si los omite** (`IoA >= 0.50`). Ver criterios en 3.2 y 3.3. |

### 3.2 Criterio para vehículos parcialmente visibles y oclusiones

- **Visibilidad `>= 0.15` (`15%` de la silueta estimada visible) e identificable:** Trazar el `bbox_xyxy` ajustado exclusivamente a la **porción visible dentro del frame o no tapada por oclusor opaco**, asignando `is_partial_border = true` si toca a `<= 2 px` del borde de imagen y `visibility_ratio` real (`0.15..1.00`).
- **Visibilidad `< 0.15` (esquina de defensa/llanta mínima) o silueta imposible de clasificar con certeza:** Marcar obligatoriamente como **`IGNORE`** (`ignore_reason = "PARTIAL_BELOW_15PCT"` o `"UNCLASSIFIABLE_HEAVY_OCCLUSION"`). Nunca adivinar entre `CAR` y `TRUCK`.

### 3.3 Reglas para objetos ambiguos, vehículos de juguete y pantallas

1. **Vehículos de juguete / a escala (`is_scale_model = true`):** **No se asumen automáticamente como vehículos reales.** En `VIGIA-BENCH-v1` llevan la bandera booleana `is_scale_model = true` y pertenecen al dominio `SCALE_MODEL_LAB`, permitiendo evaluar por separado el comportamiento sobre el banco de pruebas físico (`SCALE_MODEL_LAB`) y futuras capturas reales de carretera (`REAL_FULL_SCALE`).
2. **Objetos ambiguos o incompletos:** Ejemplo comprobado: el chasis LEGO de 4 ruedas sin carrocería en `20261104T163435_585610Z_5f6dd24bfe47_orig.jpg` debe marcarse como **`IGNORE`** (`ignore_reason = "AMBIGUOUS_LEGO_CHASSIS"`).
3. **Recapturas de pantalla (`SCREEN_RECAPTURE`):** Las sesiones `S04` (`2026-11-05`) y `S09` (`2026-11-11`) contienen rejillas de Google Imágenes con dibujos animados, iconos vectoriales (cohetes, aviones, trenes) y decenas de miniaturas densas. Si se conservan en el set, sus regiones de pantalla con miniaturas no representativas deben tratarse como **`IGNORE`** (`ignore_reason = "SCREEN_COLLAGE_OR_ICON"`) o marcarse como dominio `SCREEN_RECAPTURE` separado de la evaluación principal.
4. **Cero invención:** Ninguna caja puede ser autogenerada por YOLO y aceptada sin revisión y medición manual del anotador humano.

---

## 4. Esquema de Ground Truth

El esquema formal está definido y validado en [schema_ground_truth.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/benchmarks/vigia_bench_v1/schema_ground_truth.json) (`JSON Schema Draft 2020-12`) y ejemplificado en la plantilla ilustrativa [annotation_template_example.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/benchmarks/vigia_bench_v1/annotation_template_example.json) (`"_is_template_only": true`).

### Campos obligatorios por imagen y por anotación

- **Nivel imagen (`ImageRecord`):** `image_id`, `rel_path`, `sha256` (hex 64), `size_bytes`, `camera_id`, `session_id`, `capture_timestamp_utc`, `width`, `height`, `source_domain` (`REAL_FULL_SCALE` | `SCALE_MODEL_LAB` | `SCREEN_RECAPTURE` | `SYNTHETIC_STOCK` | `NEGATIVE_CONTROL`), `is_negative_sample`, `lighting_condition` (`WELL_LIT` | `UNDEREXPOSED` | `HARSH_GLARE` | `NIGHT_LOW_LIGHT`), `sharpness_tier` (`SHARP` | `MODERATE_BLUR` | `SEVERE_BLUR`), `mean_luminance_y`, `laplacian_variance`, `annotation_status` (`PENDING_HUMAN_REVIEW` | `ANNOTATED_VERIFIED` | `EXCLUDED`), `annotations`.
- **Nivel vehículo (`VehicleAnnotation`):**
  - `annotation_id`, `image_id`, `class_label` (`CAR` | `MOTORCYCLE` | `BUS` | `TRUCK` | `IGNORE`).
  - `bbox_xyxy`: `[x_min, y_min, x_max, y_max]` enteros sobre resolución original.
  - `visibility_ratio`: `0.0 .. 1.0`.
  - `occlusion_level`: `NONE` (ocultación `< 5%`), `PARTIAL` (`5%–50%`), `HEAVY` (`> 50%`).
  - `relative_size`: calculado por área relativa de bbox sobre área del frame: `SMALL` (`< 2%`), `MEDIUM` (`2%–15%`), `LARGE` (`> 15%`).
  - `estimated_distance`: `CLOSE_MACRO` (modelos a escala en escritorio/mano), `CLOSE` (`< 8 m`), `MEDIUM` (`8–25 m`), `FAR` (`> 25 m`), `UNKNOWN` (cuando la óptica/escala impida estimar distancia real en metros).
  - `lighting_local`: `WELL_LIT` | `UNDEREXPOSED` | `GLARE` | `SHADOW`.
  - `is_scale_model` (`bool`), `is_partial_border` (`bool`), `ignore_reason`, `annotator_id`, `annotated_at_utc`.

---

## 5. Distribución de clases

| Clase objetivo | Estado actual en Ground Truth verificado | Presencia visual observada en las `150` imágenes semilla (pendiente de anotar) | Cuota mínima requerida para `BENCHMARK READY` |
| :--- | :---: | :--- | :---: |
| **`CAR`** | **0 verificadas** (`PENDING_HUMAN_REVIEW`) | Alta frecuencia en `SCALE_MODEL_LAB` (`is_scale_model=true`: cupé rojo TOYOTA y cupé vino) y en miniaturas de `SCREEN_RECAPTURE`. | `>= 80` instancias reales (`1:1`) o `>= 80` etiquetadas estratificadas. |
| **`BUS`** | **0 verificadas** (`PENDING_HUMAN_REVIEW`) | Presente en sesiones `S15` (`SCALE_MODEL_LAB`, autobús escolar amarillo a escala) y en `2` testigos `SYNTHETIC_STOCK` (`bus.jpg`). | `>= 25` instancias (`>= 15` fuera de `SYNTHETIC_STOCK`). |
| **`MOTORCYCLE`** | **0 verificadas** | **`0` ejemplares físicos observados** en las sesiones de cámara USB o móvil (solo posibles iconos en collages de pantalla). | `>= 20` instancias reales capturadas y anotadas. |
| **`TRUCK`** | **0 verificadas** | **`0` ejemplares físicos inequívocos** (el autobús escolar amarillo frontal no debe falsificarse como `TRUCK`). | `>= 20` instancias reales capturadas y anotadas. |
| **`IGNORE`** | **0 verificadas** | Presente al menos en `S01` (chasis LEGO), recortes extremos en borde y miniaturas/iconos de `SCREEN_RECAPTURE`. | Según presencia real en escenas. |
| **Negativos (`TN`)** | **0 verificadas** | **`0` imágenes negativas sin vehículos en todo `evidencias_vigia/`.** | **`>= 60` frames negativos controlados.** |

---

## 6. Distribución de condiciones

### 6.1 Estratificación real disponible en las `150` imágenes semilla generadas

| Dimensión | Estrato / Categoría | Imágenes en semilla (`150`) | Porcentaje | Observación |
| :--- | :--- | :---: | :---: | :--- |
| **Cámara** | `CAM-ENTRADA` | 74 | `49.33%` | `53` `SCALE_MODEL_LAB` (`52` móvil + `1` USB) + `20` `SCREEN_RECAPTURE` + `1` testigo `SYNTHETIC_STOCK`. |
| | `CAM-SALIDA` | 75 | `50.00%` | `75` `SCALE_MODEL_LAB` (`640x480` USB DirectShow en `S13..S15`). |
| | `CAM-03` | 1 | `0.67%` | Únicamente testigo `SYNTHETIC_STOCK` `640x480`. |
| **Iluminación** | `WELL_LIT` (`60 <= Y <= 145`) | 116 | `77.33%` | `114` físicas + `2` testigos stock. |
| | `HARSH_GLARE` (`Y > 145`) | 20 | `13.33%` | Reflejos intensos sobre escritorio (`S08`: 3, `S14`: 7, `S15`: 10). |
| | `UNDEREXPOSED` (`Y < 60`) | 14 | `9.33%` | Subexposición real (`S11`: 4 en móvil con luz verde, `S13`: 10 en USB hasta `Y = 13.7`). |
| | `NIGHT_LOW_LIGHT` (exterior nocturno `1:1`) | **0** | `0.00%` | **Brecha:** sin capturas nocturnas de vehículos reales en calle. |
| **Nitidez (`Laplacian`)** | `SEVERE_BLUR` (`< 20`) | 81 | `54.00%` | Concentrado en USB `CAM-SALIDA` (`73/75`) + baja luz `CAM-ENTRADA` (`8`). |
| | `MODERATE_BLUR` (`20..100`) | 42 | `28.00%` | Mayoría móvil `CAM-ENTRADA` en mano/escritorio (`40`) + USB (`2`). |
| | `SHARP` (`>= 100`) | 27 | `18.00%` | `20` `SCREEN_RECAPTURE` + `5` `SCALE_MODEL_LAB` (`S03`/`S05`) + `2` stock. |
| **Negativos (`TN`)** | Escenas vacías / distractores | **0** | `0.00%` | **Brecha crítica:** obligatorio capturar `>= 60` negativos controlados. |

### 6.2 Propuesta de captura adicional controlada (para cerrar brechas antes de `VISION-03B` / `03C`)

1. **Bloque A — Negativos reales controlados (`>= 60` frames, prioridad `CRITICAL`):**
   - `20` frames en `CAM-SALIDA` (USB) y `20` en `CAM-ENTRADA` (móvil) con **escenario vacío** en luz diurna, sombra y baja iluminación (`Y < 60`), para medir tasa real de falsos positivos de fondo.
   - `20` frames con **distractores duros sin vehículos**: teclado, ratón, cables, manos en movimiento, botellas/latas y personas cruzando el ROI.
2. **Bloque B — Vehículos reales `1:1` y clases faltantes (`>= 90` frames, prioridad `HIGH`):**
   - Capturar en acceso vehicular o vía controlada con las cámaras reales del sistema (móvil `CAM-ENTRADA` + laptop/USB `CAM-SALIDA`): automóviles reales (`>= 30`), motocicletas (`>= 20`), camiones de carga (`>= 20`) y autobuses (`>= 15`), cubriendo día, noche/baja luz, distancias cercana/media/lejana y entradas parciales al borde del ROI.

---

## 7. Métricas y protocolo de evaluación

El protocolo está codificado de forma reproducible en [bench_tool.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/benchmarks/vigia_bench_v1/bench_tool.py) (subcomando `evaluate`):

1. **Precondición de integridad y completitud:** Verifica el `sha256` de cada imagen y **rechaza la ejecución (código de salida `2`)** mientras queden imágenes en `PENDING_HUMAN_REVIEW` o insuficientes negativos verificados.
2. **Mapeo de predicciones COCO a clases benchmark:** `2 -> CAR`, `3 -> MOTORCYCLE`, `5 -> BUS`, `7 -> TRUCK`.
3. **Emparejamiento (*Matching*) 1 a 1:**
   - Para cada clase por separado, las predicciones se ordenan de forma descendente por confianza (`conf`).
   - Cada predicción se compara contra las anotaciones Ground Truth de su misma clase e imagen mediante $\text{IoU} = \frac{\text{Área}(B_p \cap B_{gt})}{\text{Área}(B_p \cup B_{gt})}$, asignándose de manera *greedy* al GT no emparejado con mayor IoU siempre que $\text{IoU} \ge \tau$ (`TP`).
   - Las predicciones sin par válido se verifican contra las cajas `IGNORE` de la imagen: si $\text{IoA}(B_p, B_{ign}) = \frac{\text{Área}(B_p \cap B_{ign})}{\text{Área}(B_p)} \ge 0.50$, se **neutralizan** (no cuentan como `FP`); en caso contrario cuentan como `FP`. Toda caja GT no emparejada cuenta como `FN`.
4. **Métricas reportadas:**
   - `Precision`, `Recall`, `F1-score`, `TP`, `FP` y `FN` al umbral operativo principal ($\tau_{\text{IoU}} = 0.50$).
   - `mAP50`: promedio de AP (interpolación COCO de **101 puntos** sobre la curva Precision–Recall) a $\tau_{\text{IoU}} = 0.50$.
   - `mAP50-95`: promedio de AP sobre los 10 umbrales $\tau_{\text{IoU}} \in \{0.50, 0.55, \dots, 0.95\}$.
   - **Latencia de inferencia (`ms/frame`):** medida con `time.perf_counter()` y `torch.cuda.synchronize()` alrededor de `model.predict()`.
5. **Desglose obligatorio:** Totales globales y particionados por **clase**, **cámara** (`CAM-ENTRADA`, `CAM-SALIDA`), **iluminación**, **nitidez** y **`source_domain`** (nunca mezclar `SCALE_MODEL_LAB` ni `SYNTHETIC_STOCK` en el promedio de `REAL_FULL_SCALE`).

---

## 8. Limitaciones estadísticas

1. **Cero verdaderos negativos históricos (`TN = 0`):** Imposible calcular `Precision` o tasa de falsos positivos reales sobre el corpus actual sin capturar primero el Bloque A.
2. **Brecha de dominio física (`0%` vehículos `1:1`):** Las `148` capturas físicas deduplicadas representan modelos a escala en escritorio o fotografías de pantalla, no vehículos reales en vía pública.
3. **Ausencia total de `MOTORCYCLE` y `TRUCK`:** No es estadísticamente válido reportar `mAP` multiclase de las 4 categorías con 2 clases vacías.
4. **Correlación intra-sesión:** A pesar de reducir `205 -> 148` frames, varias imágenes dentro de una misma sesión comparten el mismo objeto red hot/amarillo y fondo de escritorio, reduciendo el tamaño efectivo de muestra independiente ($N_{\text{eff}}$).

---

## 9. Procedimiento de actualización del benchmark

Toda evolución hacia `VIGIA-BENCH-v1.1` o `v2` sigue un ciclo auditable en [benchmarks/vigia_bench_v1](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/benchmarks/vigia_bench_v1):

1. Incorporar nuevas capturas reales o negativas en `evidencias_vigia/` (sin sobrescribir ni borrar existentes).
2. Completar cajas manualmente en [annotation_sheet_v1.csv](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/benchmarks/vigia_bench_v1/annotation_sheet_v1.csv) siguiendo la Sección 3 y validando contra [schema_ground_truth.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/benchmarks/vigia_bench_v1/schema_ground_truth.json).
3. Importar anotaciones verificadas:  
   `python benchmarks/vigia_bench_v1/bench_tool.py import-csv`
4. Auditar integridad SHA-256 y dictamen:  
   `python benchmarks/vigia_bench_v1/bench_tool.py status --strict`
5. Congelar `manifest_v1_annotated.json` registrando su `sha256` antes de ejecutar comparativas `bench_tool.py evaluate` entre configuraciones de modelo, pesos o umbrales (cada corrida genera un JSON inmutable en `runs/` con hash de manifiesto, hash de pesos, configuración de inferencia y fecha UTC).

---

## 10. Criterios de aceptación, pendientes humanos y dictamen final

### 10.1 Criterios mínimos de aceptación para `BENCHMARK READY`

- `100%` de las imágenes del manifiesto con integridad SHA-256 verificada y `0` en estado `PENDING_HUMAN_REVIEW`.
- `>= 60` muestras negativas (`is_negative_sample = true`) anotadas y verificadas.
- Presencia mínima verificada en las `4` clases (`CAR`, `MOTORCYCLE`, `BUS`, `TRUCK`) y separación explícita `is_scale_model` vs `REAL_FULL_SCALE`.
- `bench_tool.py status --strict` retornando código `0`.

### 10.2 Elementos pendientes que requieren intervención humana

1. **Anotación manual de las `150` imágenes semilla** en [annotation_sheet_v1.csv](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/benchmarks/vigia_bench_v1/annotation_sheet_v1.csv) (hoy `150/150` en `PENDING_HUMAN_REVIEW`, comprobado por `bench_tool.py status`).
2. **Captura controlada de `>= 60` frames negativos (`TN`)** en `CAM-ENTRADA` y `CAM-SALIDA` sin vehículos.
3. **Captura de vehículos reales `1:1` y clases ausentes (`MOTORCYCLE`, `TRUCK`, noche)** si el objetivo es validar desempeño en calle y no únicamente en banco de escritorio.

### 10.3 Dictamen Final

**Dictamen:** **`BENCHMARK INCOMPLETE`**

La infraestructura reproducible, la auditoría integral de `604` archivos (`208` SHA-256 únicos), el esquema formal [schema_ground_truth.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/benchmarks/vigia_bench_v1/schema_ground_truth.json), la plantilla [annotation_template_example.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/benchmarks/vigia_bench_v1/annotation_template_example.json), la selección determinista [manifest_v1_seed.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/benchmarks/vigia_bench_v1/manifest_v1_seed.json) (`150` imágenes) y la herramienta [bench_tool.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/benchmarks/vigia_bench_v1/bench_tool.py) quedan listos y verificados (`evaluate` bloqueado con código `2` hasta completar Ground Truth). No se declaran valores de `Precision`, `Recall` ni `mAP` y no se implementa ningún cambio en producción hasta completar la anotación humana y recibir autorización del responsable del proyecto.
