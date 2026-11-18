# VIGIA-VISION-03B.1 — Protocolo de Captura del Dataset Vehicular Real (`VIGIA-BENCH-REAL`)

- **Proyecto:** VIGÍA Vision Systems  
- **Fase:** `VIGIA-VISION-03B.1` (Diseño operativo y protocolo reproducible de adquisición de datos reales 1:1)  
- **Fecha:** 2026-11-14  
- **Estado:** **BORRADOR PARA APROBACIÓN DEL RESPONSABLE DEL PROYECTO** (no se han iniciado capturas físicas, no se han detenido servicios ni modificado parámetros activos)  
- **Predecesor:** [VIGIA-VISION-03B_BENCHMARK.md](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_vision/VIGIA-VISION-03B_BENCHMARK.md) (`VIGIA-BENCH-v1` declarado `BENCHMARK INCOMPLETE` por ausencia de vehículos `1:1`, clases `MOTORCYCLE`/`TRUCK` y muestras negativas `TN`)

---

## 0. Principios de diseño y restricciones obligatorias

Este protocolo establece el procedimiento seguro, reproducible y libre de sesgos para construir **`VIGIA-BENCH-REAL`** con vehículos reales a escala `1:1` utilizando las cámaras físicas del sistema (`CAM-ENTRADA` y `CAM-SALIDA`).

### Restricciones operativas inviolables
1. **Sin cambios en producción:** No modificar [yolo_detector.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py), pesos (`yolo11n.pt`), umbrales (`0.25` / `0.70`), resolución activa de cámaras ni la FSM ([temporal_state.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/runtime/temporal_state.py)).
2. **Sin interrupción ni contención:** No detener servicios en ejecución fuera de una ventana de mantenimiento autorizada ni competir por el descriptor USB de `OpenCVCaptureSource` mientras `CameraPullWorker` esté activo.
3. **Aislamiento total de evidencias y BD:** No alterar [evidencias_vigia](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/evidencias_vigia) histórica ni modificar el esquema o registros de PostgreSQL.
4. **Pureza de dominio y Ground Truth:** Prohibido incluir imágenes sintéticas (`SYNTHETIC_STOCK`), modelos a escala (`SCALE_MODEL_LAB`) o recapturas de pantalla (`SCREEN_RECAPTURE`) dentro de `VIGIA-BENCH-REAL`. Prohibido tratar predicciones de YOLO o fotogramas anotados (`*_annot.jpg` / `/live` / `/stream`) como Ground Truth o imagen fuente.

---

## 1. Procedimiento de captura

### 1.1 Por qué NO debe usarse el flujo estándar `evidencias_vigia/` ni `/live` para el benchmark

La inspección del pipeline en [usb_worker.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/usb_worker.py#L283-L316), [ingest_service.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py#L1962-L2004) y [evidence_storage.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/runtime/evidence_storage.py#L121-L170) demuestra dos limitaciones estructurales para recolección de benchmark:

1. **Sesgo de supervivencia positiva:** El runtime solo persiste `*_orig.jpg` cuando `vehicle_detected=True` (`conf >= 0.70` y centroide en ROI). Nunca guarda negativos reales (`TN`) ni vehículos reales omitidos por YOLO (`FN`), que son precisamente los casos críticos a medir.
2. **Endpoints `/live` y `/stream` contaminados con overlays:** Ambos emiten copias renderizadas (`render_annotated_frame`) con rectángulo amarillo de ROI y cajas verdes dibujadas sobre la imagen en calidad JPEG `80`, invalidándolas como entrada limpia de evaluación.

Por ello, `VIGIA-BENCH-REAL` debe capturar **fotogramas crudos sin overlays (`raw_clean`)** mediante un flujo aislado y sin competencia de hardware.

### 1.2 Arquitectura de adquisición por modo operativo

| Modo | Cuándo aplicar | `CAM-ENTRADA` (Dispositivo móvil / ángulo acceso entrada) | `CAM-SALIDA` (Cámara USB local / punto de salida) | Riesgo sobre servicio activo |
| :--- | :--- | :--- | :--- | :--- |
| **Modo A — Ventana de mantenimiento autorizada (Recomendado)** | Cuando se requiera usar exactamente el mismo hardware USB y servidor local sin sesgo de sensor. | Grabación cruda desde el móvil montado en su posición real (misma orientación vertical `720x1280` o nativa configurada, sin enviar a `/push` ni BD). | Captura local aislada con los mismos parámetros DirectShow vigentes (`640x480` por defecto), ejecutada **únicamente tras detener o liberar el `CameraPullWorker` en ventana autorizada**. | Nulo si se respeta la secuencia de liberación y restauración del servicio. |
| **Modo B — Operación paralela sin detener el servidor activo** | Cuando el servidor HTTPS de VIGÍA deba permanecer encendido y no exista ventana de mantenimiento. | **Permitido con unidad móvil secundaria/idéntica en modo grabador offline** o captura previa al enrolamiento en el mismo soporte físico, sin consumir el token `/push` del carril vivo. | **PROHIBIDO abrir `cv2.VideoCapture(index)` si `CameraPullWorker` tiene el dispositivo ocupado** (`USB_DEVICE_IN_USE` / `CAPTURE_EMPTY_FRAME`). Postergar la captura USB física a Ventana Modo A, o emplear una segunda cámara USB física de idéntico modelo conectada en otro puerto/índice exclusivo para captura offline. | Nulo para `CAM-SALIDA` en producción al evitar doble apertura. |

### 1.3 Procedimiento operativo paso a paso en campo

1. **Preparación del punto físico (Entrada y Salida):**
   - Fijar `CAM-ENTRADA` y `CAM-SALIDA` en su ángulo, altura e inclinación reales de operación (evitar sostener la cámara en la mano salvo que se documente explícitamente como captura móvil de validación).
   - Confirmar visualmente las zonas equivalentes al ROI configurado en operación (`[0.1, 0.2, 0.9, 0.8]` normalizado) para asegurar que los vehículos atraviesen bordes, centro y zona cercana/lejana.
2. **Definición de sesión y evento:**
   - Asignar un identificador único de sesión antes de iniciar (`SREAL_<YYYYMMDD>_<CAM>_<SEQ>`, ej. `SREAL_20261115_CAM-ENTRADA_01`).
   - En cada paso vehicular completo, registrar si corresponde a un evento de **entrada (`ENTRY`)** o **salida (`EXIT`)**, diferenciando el tránsito en una secuencia contigua (`sequence_id`) desde que el vehículo asoma en el borde del encuadre hasta que lo abandona.
3. **Muestreo temporal durante la captura:**
   - **Tránsito en movimiento:** Capturar o extraer fotogramas de video crudo a razón de **`2.0 FPS`** (`delta_t = 0.5 s`) mientras el vehículo cruza el campo visual, seguido de deduplicación offline para retener `3–5` poses distintas por evento (ingreso parcial en borde, centro pleno, alejamiento parcial).
   - **Vehículo detenido o fila lenta:** Extraer máximo **`1 frame cada 5.0 s`** únicamente si cambia la iluminación, el vehículo avanza o entra otro actor en escena.
   - **Escenas negativas (`TN`):** Capturar ráfagas de **`1 frame cada 3.0–5.0 s`** con encuadre libre de vehículos pero con variaciones reales de fondo (peatones, bicicletas, sombras móviles, faros lejanos fuera de calzada, lluvia o reflejos).
4. **Cierre y volcado seguro:**
   - Guardar los fotogramas crudos en formato `.jpg` de alta calidad (`>= 95` o sin recompresión adicional) o `.png` dentro del directorio aislado de la sesión (`benchmarks/vigia_bench_real/sessions/.../raw_frames/`), calculando inmediatamente su `SHA-256` y marcándolos como solo lectura.

---

## 2. Matriz de escenarios (Estratificación mínima objetivo: `360` muestras reales)

Para garantizar cobertura estadística en ambas cámaras (`CAM-ENTRADA` y `CAM-SALIDA`), el objetivo inicial de `VIGIA-BENCH-REAL` es de **al menos `360` frames no redundantes**, distribuidos en las siguientes dimensiones:

### 2.1 Cuotas por clase y condición

| Eje de estratificación | Categorías cubiertas | Cuota mínima total | Reparto sugerido (`CAM-ENTRADA` / `CAM-SALIDA`) | Notas de captura |
| :--- | :--- | :---: | :---: | :--- |
| **Clases vehiculares (`270` positivos)** | `CAR` (automóviles, sedanes, SUV, pickups ligeras) | **`120`** | `60` / `60` | Incluir colores oscuros, blancos, plateados y metálicos bajo sol y sombra. |
| | `MOTORCYCLE` (motocicletas, motonetas con y sin conductor) | **`50`** | `25` / `25` | Capturar de frente, atrás y perfil (clase actualmente `0` en `VIGIA-BENCH-v1`). |
| | `BUS` (autobuses urbanos, escolares, microbuses) | **`50`** | `25` / `25` | Validar que frontal y lateral se etiqueten ambos como `BUS` (no confundir con `TRUCK`). |
| | `TRUCK` (camiones rígidos, volteos, tráileres, furgones pesados) | **`50`** | `25` / `25` | Capturar en movimiento y cruce parcial para evaluar confusión `BUS`/`TRUCK`. |
| **Negativos (`TN`, `90` muestras)** | `NEGATIVE_EMPTY` (calzada/carril completamente vacío) | **`45`** | `22` / `23` | Día, atardecer, noche y cambios de exposición automática. |
| | `NEGATIVE_HARD_DISTRACTORS` (peatones, bicicletas, perros, puestos, sombras, hojas, carritos) | **`45`** | `23` / `22` | Esencial para medir tasa real de falsos positivos sin sesgo. |

### 2.2 Cobertura obligatoria de geometría, cinemática e iluminación (transversal sobre los `270` positivos)

| Dimensión | Condición específica | Cuota mínima en positivos | Objetivo de evaluación |
| :--- | :--- | :---: | :--- |
| **Distancia / Tamaño** | **Cercanos (`CLOSE`, área bbox `> 15%`)** | `>= 70` | Detectar cortes por centroide fuera de ROI en primer plano o techo/cofre dominante. |
| | **Medios (`MEDIUM`, área bbox `2%–15%`)** | `>= 120` | Operación nominal en zona central del ROI. |
| | **Lejanos (`FAR`, área bbox `< 2%`)** | `>= 50` | Medir límite de resolución efectiva (`640x480` USB y ancho `360 px` tras LetterBox vertical). |
| **Cinemática y Visibilidad** | **En movimiento (`IN_MOTION`)** | `>= 160` | Evaluar impacto real del *motion blur* en obturación USB y móvil. |
| | **Parcialmente visibles (`PARTIAL_BORDER`, `15%–60%` en borde)** | `>= 50` | Caso directo para validar política ROI `centroid` vs `hybrid`. |
| | **Oclusiones (`PARTIAL`/`HEAVY` por otro vehículo, poste, árbol o persona)** | `>= 40` | Medir robustez ante pérdida parcial de silueta. |
| **Ángulos** | Frontal, trasero, lateral (`90°`) y oblicuo (`30°–60°`) | `>= 50` por vista | Cubrir ambos sentidos reales (`ENTRY` y `EXIT`). |
| **Iluminación y Clima** | **Día normal (`DAY_WELL_LIT`)** | `>= 140` | Línea base diurna. |
| | **Noche / baja iluminación (`NIGHT_LOW_LIGHT`, `Y < 60`)** | `>= 80` | Faros encendidos, ruido ISO alto y baja luz real. |
| | **Iluminación adversa (`ADVERSE_LIGHTING`: contraluz, sol directo, destellos de faros, sombras duras o pavimento mojado)** | `>= 50` | Evaluar deslumbramiento y caída de confianza por bajo contraste. |

---

## 3. Metadatos obligatorios por muestra

Cada imagen incorporada a `VIGIA-BENCH-REAL` debe quedar indexada en un manifiesto JSON versionado (`manifest_real_v1.json`) cumpliendo los campos requeridos y compatibles con [schema_ground_truth.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/benchmarks/vigia_bench_v1/schema_ground_truth.json):

| Campo | Tipo / Formato | Descripción y regla de llenado |
| :--- | :--- | :--- |
| `image_id` | `string` único | Identificador determinista: `VBR1_<CAMERA_ID>_<TIMESTAMP_UTC>_<SHA256[:8]>`. |
| `sha256` | `string` (64 hex) | Hash SHA-256 calculado sobre los bytes exactos del archivo crudo en disco. |
| `camera_id` | `enum` | `CAM-ENTRADA` \| `CAM-SALIDA` (prohibido inventar códigos no registrados). |
| `capture_timestamp_utc` | `ISO-8601 UTC` | Timestamp original de captura preservado intacto (EXIF / reloj sincronizado NTP). |
| `resolution` / `width`, `height` | `int`, `int` (`"WxH"`) | Resolución nativa original entregada por la cámara (ej. `640x480`, `720x1280`). |
| `session_id` | `string` | Código de sesión física (ej. `SREAL_20261115_CAM-SALIDA_01`). **Clave de partición.** |
| `sequence_id` | `string` | Identificador de secuencia continua para un mismo evento vehicular (`ENTRY` / `EXIT`). |
| `event_direction` | `enum` | `ENTRY` \| `EXIT` \| `STATIC_SCENE` \| `NEGATIVE_BACKGROUND`. |
| `scenario` | `string` / `enum` | Código de escenario: `DAY_CLEAR`, `NIGHT_HEADLIGHTS`, `BACKLIT_GLARE`, `OCCLUDED_TRAFFIC`, `PARTIAL_ENTRY_EDGE`, `FAR_APPROACH`, `NEGATIVE_EMPTY`, `NEGATIVE_PEDESTRIANS_BIKES`, etc. |
| `expected_class` | `enum \| null` | Clase esperada dominante en el evento cuando corresponda (`CAR`, `MOTORCYCLE`, `BUS`, `TRUCK`, `MIXED`, `NONE` para negativos). *Informativo de sesión; no sustituye la anotación por caja.* |
| `lighting_condition` | `enum` | `WELL_LIT` (`60 <= Y <= 145`), `UNDEREXPOSED` (`Y < 60`), `HARSH_GLARE` (`Y > 145` o saturación localizada), `NIGHT_LOW_LIGHT` (captura nocturna real). |
| `sharpness_tier` | `enum` | Calculado objetivamente con varianza del Laplaciano: `SHARP` (`>= 100`), `MODERATE_BLUR` (`20..100`), `SEVERE_BLUR` (`< 20`), preservando también los valores numéricos `laplacian_variance` y `mean_luminance_y`. |
| `source_domain` | `const` | `REAL_FULL_SCALE` (positivos reales) o `NEGATIVE_CONTROL` (negativos reales). |
| `annotation_status` | `enum` | Inicial obligatorio: **`PENDING_HUMAN_REVIEW`**. Solo pasa a **`ANNOTATED_VERIFIED`** tras revisión manual completa, o `EXCLUDED` si falla calidad/privacidad. |

---

## 4. Reglas de deduplicación y aislamiento de secuencias

Para evitar almacenar cientos de frames redundantes que inflen artificialmente las métricas:

1. **Deduplicación exacta por contenido (`SHA-256`):**
   - Cualquier archivo cuyo `sha256` ya exista en el manifiesto real o en el corpus histórico se descarta automáticamente.
2. **Deduplicación perceptual y temporal intra-secuencia:**
   - Dentro de una misma `session_id` y `camera_id`, los frames se ordenan por `capture_timestamp_utc`.
   - Un frame candidato solo se retiene si cumple **al menos uno** de los criterios respecto al último frame retenido:
     - Inicia nueva `sequence_id` o `delta_t >= 5.0 s`; **o**
     - Han pasado `delta_t >= 1.5 s` **y** la diferencia media absoluta sobre miniatura `32x32` en escala de grises cumple **`MAD_32x32 >= 8.0`** (o índice `SSIM <= 0.92`), asegurando desplazamiento real del vehículo o cambio efectivo de escena.
   - Si una secuencia corta (`ENTRY`/`EXIT`) contiene un vehículo entrando al borde del ROI y otro frame distinto en el centro, ambos se preservan siempre que **`MAD_32x32 >= 6.0`** y **`delta_t >= 0.4 s`**, limitando un máximo de **`4` frames por evento vehicular único**.
3. **Regla estricta de agrupación secuencial (Anti-Contaminación):**
   - Todos los frames pertenecientes a una misma `sequence_id` y `session_id` **deben permanecer estrictamente juntos** en un único bloque lógico (`group_key = session_id`).
   - Queda **terminantemente prohibido** realizar división aleatoria a nivel frame (*random frame-level split*) si en futuras fases se subdivide en subconjuntos (`calibración/ajuste` vs `prueba final`): todo split debe efectuarse por `session_id` completo para evitar fuga de datos (*data leakage*) con fondos o vehículos idénticos.

---

## 5. Política de Ground Truth

1. **Anotación 100% manual y verificada:**
   - Las cajas `bbox_xyxy` y etiquetas (`CAR`, `MOTORCYCLE`, `BUS`, `TRUCK`, `IGNORE`) deben ser trazadas manualmente por un anotador humano sobre las imágenes limpias (`raw_frames/`).
   - **Prohibición explícita:** Queda estrictamente prohibido pre-llenar o aprobar automáticamente predicciones de `yolo11n.pt` (u otro modelo) como Ground Truth. Ninguna imagen pasa a `ANNOTATED_VERIFIED` sin verificación visual caja por caja y doble auditoría aleatoria sobre al menos el `20%` de cada sesión.
2. **Tratamiento de objetos ambiguos y visibilidad parcial:**
   - **Visibilidad `>= 15%` de silueta identificable:** Anotar con la clase real (`CAR`, `MOTORCYCLE`, `BUS`, `TRUCK`), ajustando el box únicamente al área visible, con `occlusion_level` (`NONE` `<5%`, `PARTIAL` `5%–50%`, `HEAVY` `>50%`), `visibility_ratio` (`0.15..1.00`) y `is_partial_border=true` si toca a `<= 2 px` del borde del encuadre.
   - **Casos ambiguos o visibilidad `< 15%` (`IGNORE`):** Todo vehículo demasiado lejano (`< 12 px` de altura sin forma distinguible), fuertemente ocluido donde no pueda distinguirse entre `CAR`/`TRUCK`/`BUS`, vehículos cortados con `< 15%` visible, remolques separados o carrocerías atípicas deben etiquetarse como **`IGNORE`** con `ignore_reason` explícito. Nunca forzar una clase dudosa.
   - **Vehículos no motorizados / otros:** Bicicletas sin motor, patinetes eléctricos, carritos de supermercado y carretillas **NO** son `MOTORCYCLE` ni `CAR`; si la escena forma parte de un negativo (`NEGATIVE_HARD_DISTRACTORS`), permanecen sin caja vehicular para probar que el detector no emite falsos positivos.
3. **Separación de dominios:**
   - `VIGIA-BENCH-REAL` contiene **exclusivamente** `REAL_FULL_SCALE` y `NEGATIVE_CONTROL`. Jamás se mezclan capturas de `SCALE_MODEL_LAB`, `SCREEN_RECAPTURE` o `SYNTHETIC_STOCK` ([VIGIA-BENCH-v1](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/benchmarks/vigia_bench_v1/manifest_v1_seed.json)).

---

## 6. Estructura de almacenamiento

El almacenamiento vive **completamente aislado** de `evidencias_vigia/` y de PostgreSQL, bajo un directorio dedicado versionado por manifiestos:

```text
benchmarks/
├── vigia_bench_v1/                    # Semilla existente de laboratorio (03B) — NO modificar
└── vigia_bench_real/                  # Nuevo benchmark real 1:1 (VIGIA-BENCH-REAL)
    ├── README_CAPTURE.md              # Notas de campo y registro de ventanas de captura
    ├── sessions/                      # Carpeta madre de sesiones crudas agrupadas
    │   └── <YYYYMMDD>_<CAM>_<SEQ>/    # Ej: 20261115_CAM-ENTRADA_S01
    │       ├── session_meta.json      # Cámara, ubicación, clima, iluminación, operador, ventana
    │       └── raw_frames/            # SOLO imágenes limpias originales (sin _annot ni overlays)
    │           └── <YYYYMMDDTHHMMSS>_<ffffff>Z_<CAM>_<seq4>.jpg
    ├── manifests/
    │   ├── manifest_real_raw.json     # Índice post-deduplicación (annotation_status=PENDING_HUMAN_REVIEW)
    │   └── manifest_real_v1.json      # Manifiesto congelado tras Ground Truth (ANNOTATED_VERIFIED)
    ├── annotations/
    │   ├── annotation_sheet_real_v1.csv
    │   └── qa_audit_log.json          # Registro de doble revisión humana
    └── splits/
        └── session_splits_v1.json     # Asignación de splits agrupada estrictamente por session_id
```

- **Convención inmutable:** Los archivos dentro de `raw_frames/` se protegen contra sobrescritura (nunca reescribir EXIF ni recomprimir después del cálculo de `SHA-256`).

---

## 7. Criterios de calidad

Cada frame candidato y el conjunto completo deben superar filtros cuantitativos antes de pasar a anotación:

| Criterio | Umbral / Condición de aceptación | Acción ante incumplimiento |
| :--- | :--- | :--- |
| **Integridad de archivo** | Decodificación válida BGR `3` canales por OpenCV (`img is not None`), tamaño `> 10 KB`, `SHA-256` íntegro. | Descartar y marcar `EXCLUDED` (`CORRUPT_FILE`). |
| **Pureza visual** | `0` overlays (sin líneas amarillas/verdes de ROI ni etiquetas renderizadas) y resolución nativa de cámara (`640x480` USB o `720x1280` móvil; sin recortes ni upscaling). | Rechazar lote completo si hubo captura de stream anotado. |
| **Preservación temporal** | Timestamp original (`YYYYMMDDTHHMMSS_ffffffZ` en UTC) válido y monótono dentro de la sesión. | Rechazar o corregir desfase de reloj antes de indexar. |
| **Bandas de nitidez (`Laplacian`)** | `DAY_CLEAR`: exigir mediana de sesión `>= 30.0` (evitar lentes empañados/sucios fuera de especificación). Para estrato de movimiento USB, aceptar blur natural mientras conserve contorno vehicular reconocible por un humano. | Si el vehículo es totalmente irreconocible por desenfoque extremo, excluir o marcar `IGNORE`. |
| **Bandas de luminancia (`Y`)** | Sin fotogramas completamente negros (`Y < 5.0`) ni quemados (`Y > 245.0` en >80% del frame). `NIGHT_LOW_LIGHT`: `8.0 <= Y < 60.0`. | Excluir fotogramas ciegos por transición brusca de autoexposición (primeros `1–2 s` tras abrir cámara). |
| **Balance de dataset** | Negativos `>= 25%` (`>= 90 / 360`); ninguna cámara `< 40%` del total; todas las 4 clases `>= 50` ejemplares (`CAR >= 120`). | Bloquear cierre de recolección hasta completar cuotas faltantes. |

---

## 8. Procedimiento de validación

Antes de declarar el dataset listo para anotación y posteriormente para evaluación, ejecutar un ciclo auditable en dos compuertas:

1. **Compuerta 1 — Validación pre-anotación (automática, solo lectura):**
   - Verificar `SHA-256` de `100%` de los archivos en `raw_frames/` contra `manifest_real_raw.json`.
   - Confirmar `0` duplicados exactos (`SHA-256` únicos == total de imágenes) y `0` frames consecutivos que violen el umbral de deduplicación `MAD_32x32 < 8.0` en `< 1.5 s` (salvo transiciones de borde permitidas).
   - Confirmar que el `100%` de los registros inicia con `annotation_status == "PENDING_HUMAN_REVIEW"` y `annotations == []`, y que `source_domain` pertenece exclusivamente a `REAL_FULL_SCALE` o `NEGATIVE_CONTROL`.
   - Verificar que todas las cuotas de la Sección 2 cumplen el mínimo por cámara, clase esperada, iluminación y negativos.

2. **Compuerta 2 — Validación post-anotación (auditoría humana + verificación de esquema):**
   - Validar el `100%` de las anotaciones importadas contra [schema_ground_truth.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/benchmarks/vigia_bench_v1/schema_ground_truth.json) (coordenadas dentro de `[0, W] x [0, H]`, `x_min < x_max`, `y_min < y_max`, clases válidas y `ignore_reason` presente en todo `IGNORE`).
   - Ejecutar auditoría cruzada humana sobre una muestra aleatoria del `20%` de las imágenes por sesión (tasa de discrepancia aceptable `< 2%` en etiquetas de clase y `IoU >= 0.85` en revisión de cajas).
   - Verificar que `splits/session_splits_v1.json` tiene **intersección estrictamente vacía** de `session_id` y `sequence_id` entre particiones.

---

## 9. Riesgos operativos y mitigaciones

| Riesgo operativo | Probabilidad | Impacto | Mitigación obligatoria |
| :--- | :---: | :---: | :--- |
| **Contención / caída de `CameraPullWorker` USB al intentar capturar desde script externo** (`VIDEOIO(DSHOW)` / `CAPTURE_EMPTY_FRAME`). | Alta | Alto | **Prohibido** abrir el mismo índice USB mientras VIGÍA esté ejecutando `CameraPullWorker`. Realizar capturas USB exclusivamente en ventana de mantenimiento autorizada (Modo A) tras detención controlada, o usar cámara física idéntica dedicada offline (Modo B). |
| **Contaminación de `evidencias_vigia/` o PostgreSQL durante pruebas de campo.** | Media | Alto | La captura del benchmark **nunca** pasa por `VisionEngineCoordinator` con repositorio SQL activo ni escribe en `evidencias_vigia/`. Se almacena exclusivamente en `benchmarks/vigia_bench_real/sessions/`. |
| **Sesgo de confirmación usando YOLO para "seleccionar" frames.** | Media | Alto | La selección temporal se rige únicamente por reloj (`delta_t`) y similitud de píxeles (`MAD_32x32`), jamás por confianza o disparo de `yolo11n.pt`. |
| **Saturación de red LAN / CPU o pérdida de privacidad en vía pública.** | Media | Medio | Capturar en almacenamiento local del dispositivo/estación (sin saturar HTTPS `/push`), operar en acceso privado o zona autorizada y restringir el repositorio local del benchmark conforme a políticas de acceso de datos del proyecto. |
| **Descarte de primeros frames oscuros o desenfocados por ajuste automático al abrir USB.** | Alta | Medio | Esperar `2.0 s` de estabilización tras abrir el stream antes de iniciar el muestreo útil de `raw_frames/`. |

---

## 10. Checklist de captura

### A. Pre-captura (antes de abrir sesión)
- [ ] Aprobación expresa de este protocolo por el responsable del proyecto.
- [ ] Confirmar que **NO** se han modificado pesos, thresholds, resolución, código de producción ni esquema PostgreSQL.
- [ ] Verificar estado del servidor activo: si se usará `CAM-SALIDA` USB en Modo A, programar ventana de mantenimiento autorizada; si es Modo B, verificar que no haya contención sobre el índice USB activo.
- [ ] Sincronizar hora UTC/NTP de laptop y dispositivo móvil (`< 1 s` de deriva).
- [ ] Definir `session_id`, carpeta `benchmarks/vigia_bench_real/sessions/<YYYYMMDD>_<CAM>_<SEQ>/raw_frames/` y plantilla `session_meta.json`.

### B. Durante la captura en campo
- [ ] Descartar los primeros `2.0 s` tras apertura del sensor USB para estabilizar autoexposición.
- [ ] Registrar capturas en posición, ángulo e iluminación reales sin overlays ni anotaciones.
- [ ] Cubrir las 4 clases (`CAR`, `MOTORCYCLE`, `BUS`, `TRUCK`), entradas y salidas (`ENTRY`/`EXIT`), vehículos cercanos/lejanos, parciales en borde, oclusiones, día, noche e iluminación adversa.
- [ ] Capturar obligatoriamente el lote de **negativos reales (`>= 90` frames)** en escenas vacías y con distractores (peatones, bicicletas, sombras) en ambas cámaras.

### C. Post-captura y preparación para Ground Truth
- [ ] Ejecutar cálculo de `SHA-256`, verificación de nitidez (`Laplacian`) y luminancia (`Y`), y aplicar deduplicación perceptual (`MAD_32x32` + `delta_t`).
- [ ] Confirmar que `0` archivos provienen de `*_annot.jpg`, `/live`, `/stream`, `SYNTHETIC_STOCK` ni `SCALE_MODEL_LAB`.
- [ ] Generar `manifest_real_raw.json` con `100%` en `annotation_status = "PENDING_HUMAN_REVIEW"` y `annotations = []`.
- [ ] Entregar `annotation_sheet_real_v1.csv` al equipo de anotación manual humana siguiendo la Sección 5 (sin autogenerar cajas con YOLO).
- [ ] Restaurar y verificar la operación normal de VIGÍA al cerrar cualquier ventana de mantenimiento.
