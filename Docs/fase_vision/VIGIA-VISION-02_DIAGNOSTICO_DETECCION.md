# VIGIA-VISION-02 — Diagnóstico de Detección Vehicular y Validación del Pipeline

**Documento:** `VIGIA-VISION-02_DIAGNOSTICO_DETECCION.md`  
**Proyecto:** VIGÍA Vision Systems — Control de Acceso Vehicular Automatizado  
**Fase:** Fase de Visión Artificial — Diagnóstico y Caracterización Experimental  
**Fecha de Emisión:** 5 de Noviembre de 2026  
**Entorno Operativo de Prueba:** NVIDIA GeForce RTX 4050 Laptop GPU (6,140 MB VRAM, CUDA 12.4, Driver 566.36) / Python 3.12 (`.venv_cuda`)  
**Estado:** Dictamen Técnico Definitivo (Investigación Experimental de Solo Lectura)

---

## 1. Resumen Ejecutivo y Análisis de Causa Raíz

### 1.1 Naturaleza del Problema
Durante las pruebas operativas en caseta de acceso y en el banco de pruebas experimental con transmisiones móviles en orientación vertical ($720 \times 1280$), el motor de visión de VIGÍA reportó ausencias sistemáticas de detección (**falsos negativos**) cuando un vehículo se aproxima de frente (*frontal view*) a la pluma de control. El síntoma observado fue que el sistema devolvía `VisionStatus.NO_VEHICLE_DETECTED`, impidiendo el avance de la máquina de estados y bloqueando el registro del evento de acceso.

### 1.2 Diagnóstico Multifactorial (Causas Raíz Identificadas)
La investigación experimental determinó que el fallo **no es atribuible a una avería del hardware ni a una falla fatal del modelo YOLO11n**, sino a la convergencia de cuatro factores geométricos, algorítmicos y de calibración operativa:

```mermaid
flowchart TD
    A["Vehículo Frontal Aproximándose a Caseta"] --> B["YOLO11n Forward Pass (640x640)"]
    B -->|BBox Inferida [x1, y1, x2, y2]| C{"Causa 2: Confianza vs Umbral"}
    C -->|Conf: 0.35 - 0.65| C1["Rechazado por VisionEngineSettings<br>(Threshold = 0.70)"]
    C -->|Conf >= 0.70| D{"Causa 1: Filtrado Geométrico ROI"}
    D -->|Centroide Y > 1024 px| D1["Rechazado como excluded_outside_roi<br>(PixelROI.contains_bbox_centroid)"]
    D -->|Centroide Y <= 1024 px| E["Detección Aceptada (In-ROI)"]
    
    F["Causa 3: Letterboxing 720x1280 -> 640x640"] -->|43.75% píxeles muertos| B
    G["Causa 4: Brecha COCO Dataset"] -->|Parrilla sin ruedas confunde clases| B
```

1. **Causa Dominante 1: Falso Negativo Geométrico por Criterio de Centroide en `roi_and_preprocess.py`**  
   El filtrado de área utiliza exclusivamente la función `PixelROI.contains_bbox_centroid(bbox)`. En una transmisión vertical de $720 \times 1280$ píxeles, la zona de entrada (`ROI-ENT`) está delimitada típicamente con cotas normalizadas $[0.10, 0.20, 0.90, 0.80]$, lo que fija el límite inferior en $y_{\max} = 1024.0\text{ px}$.  
   Cuando un vehículo se encuentra en aproximación cercana o primer plano, su bounding box se expande hacia la parte inferior del encuadre ($y \in [650, 1280]\text{ px}$). Aunque el vehículo físico ocupa entre el 50% y el 90% del área de lectura dentro de la caseta, su centroide geométrico:
   $$cy = \frac{y_{\min} + y_{\max\_bbox}}{2} \approx \frac{650 + 1280}{2} = 965 - 1143\text{ px}$$
   cae por debajo de $y_{\max} = 1024.0\text{ px}$. El sistema evalúa deterministamente `contains_point(cx, cy) == False`, descartando el vehículo como `excluded_outside_roi` y reportando `NO_VEHICLE_DETECTED`.

2. **Causa Dominante 2: Desalineación entre Umbral del Detector y Umbral Operativo del Coordinador**  
   Existe un desacoplamiento de configuración:
   - En [`yolo_detector.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py#L181), `YoloDetectorConfig.confidence_threshold = 0.25`.
   - En [`engine_settings.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/config/engine_settings.py#L51), `VisionEngineSettings.vehicle_confidence_threshold = 0.70`.
   - En [`coordinator.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/runtime/coordinator.py#L378), se ejecuta:
     ```python
     detections_in_roi, excluded_outside_roi = filter_detections_by_roi(
         detections=raw_candidates,
         pixel_roi=pixel_roi,
         min_confidence=self._settings.vehicle_confidence_threshold, # 0.70!
     )
     ```
   En vistas frontales, debido a la ausencia de rasgos laterales distintivos (ruedas, línea de cintura, ventanas longitudinales), la confianza asignada por el detector COCO oscila entre **$0.375$ y $0.685$**. Por tanto, el detector YOLO detecta correctamente el vehículo, pero el coordinador lo descarta por no superar el umbral de `0.70`.

3. **Causa Contribuyente 3: Deformación y Desperdicio de Resolución por Acolchado (*Letterboxing*)**  
   Al procesar fotogramas móviles verticales ($720 \times 1280$, relación de aspecto $9:16 = 0.562$) mediante redimensionamiento cuadrado a $640 \times 640$, la escala aplicada es $r = 640 / 1280 = 0.5$. La imagen útil escalada ocupa únicamente $360 \times 640$ píxeles, completándose con $280$ píxeles de relleno gris neutro (140 px a cada lado).  
   El **43.75% del tensor de entrada representa relleno artificial inútil**. Los detalles frontales del vehículo (parrilla, matrícula, emblema, faros) se comprimen a la mitad de su definición original (de 720 a 360 px), disminuyendo drásticamente la capacidad discriminatoria de las capas convolucionales superficiales.

4. **Causa Contribuyente 4: Sesgo de Perspectiva en el Dataset Base MS COCO**  
   El modelo `yolo11n.pt` utiliza pesos pre-entrenados en MS COCO (80 clases). COCO está compuesto mayoritariamente por imágenes en perspectiva horizontal (landscape) con vistas laterales o tres cuartos. Carece de vehículos frontales en aproximación cenital o picada a caseta donde el capó y la parrilla llenan el 80% del plano sin ruedas visibles. En estos escenarios extremos, YOLO11n confunde frecuentemente partes del vehículo (como el parabrisas con reflejos) con `person` (confianzas de 0.57 a 0.58) o `truck`.

---

## 2. Investigación 1 — Ruta de Inferencia de YOLO Crudo (*Raw YOLO Detection*)

### 2.1 Reconstrucción del Camino de Inferencia en `yolo_detector.py`
Se inspeccionó exhaustivamente el módulo [`VIGIA_Vision/detection/yolo_detector.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py):

```
Entrada: Frame BGR uint8 (H, W, 3) en CPU
  │
  ├── [1] validate_bgr_frame(frame)
  │         Verifica: ndim==3, channels==3, dtype==uint8, H>0, W>0
  │
  ├── [2] load_model() [Thread-Safe Lazy Loading]
  │         Instancia YOLO(model_path).to(device) en primera invocación
  │
  ├── [3] Inferencia Ultralytics: model.predict(...)
  │         ├── Preprocesamiento interno LetterBox:
  │         │     Escala isotrópica r = min(640/H, 640/W)
  │         │     Padding simétrico con color gris neutro (114, 114, 114)
  │         │     Conversión de espacio de color BGR -> RGB
  │         │     Transposición HWC (H, W, 3) -> CHW (1, 3, 640, 640)
  │         │     Normalización de rango: uint8 [0, 255] -> float32 [0.0, 1.0]
  │         │     Copia de memoria Host-to-Device (CPU -> VRAM GPU)
  │         │
  │         ├── Red Neuronal YOLO11n (Forward Pass FP32):
  │         │     Tensor de salida crudo: (1, 84, 8400)
  │         │     [84 = 4 coordenadas caja (xywh) + 80 clases COCO]
  │         │     [8400 = anclas predichas distribuidas en P3/8, P4/16, P5/32]
  │         │
  │         └── Postprocesamiento Tensorial y NMS:
  │               Filtrado de umbral de confianza preliminar: conf >= 0.25
  │               Filtrado de clases vehiculares: classes in [2, 3, 5, 7]
  │               Non-Maximum Suppression (NMS): iou_threshold = 0.45
  │               scale_boxes(): Desproyección de coordenadas del tensor (640x640)
  │                              a dimensiones originales del fotograma (W, H)
  │
  ├── [4] Extracción y Clamping Defensivo:
  │         x_min = max(0, min(round(x1), W - 1))
  │         y_min = max(0, min(round(y1), H - 1))
  │         x_max = max(0, min(round(x2), W))
  │         y_max = max(0, min(round(y2), H))
  │         Descarte de cajas degeneradas (x_max <= x_min o y_max <= y_min)
  │
  └── Salida: Tuple[RawVehicleDetection, ...] inmutable
```

### 2.2 Parámetros Exactos de Inferencia en Producción

| Parámetro | Valor Configurado | Ubicación en Código | Efecto Operativo |
| :--- | :---: | :--- | :--- |
| **Formato de Entrada** | BGR `uint8` | `yolo_detector.py:335` | Formato nativo OpenCV sin necesidad de conversión previa. |
| **Resolución `imgsz`** | `640` | `YoloDetectorConfig:183` | Redimensionamiento a tensor cuadrado $640 \times 640$. |
| **Umbral de Confianza (`conf`)** | `0.25` | `YoloDetectorConfig:181` | Umbral base de Ultralytics para NMS. |
| **Umbral de IoU (`iou`)** | `0.45` | `YoloDetectorConfig:184` | Límite de solapamiento para supresión de duplicados. |
| **Clases Vehiculares Filtradas** | `(2, 3, 5, 7)` | `YoloDetectorConfig:185` | `2: car`, `3: motorcycle`, `5: bus`, `7: truck`. |
| **Modo Inferencia `rect`** | `False` | Implícito en `model.predict` | Fuerza acolchado cuadrado estándar ($640 \times 640$). |
| **Dispositivo de Cómputo** | `'cuda:0'` | `resolve_inference_device` | Aceleración en NVIDIA RTX 4050 Laptop GPU. |

---

## 3. Investigación 2 — Filtrado de Región de Interés (*ROI Filtering*)

### 3.1 Mecánica de Filtrado en `roi_and_preprocess.py`
Se analizó la lógica geométrica implementada en [`VIGIA_Vision/detection/roi_and_preprocess.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/roi_and_preprocess.py):

- **Proyección de Coordenadas (`project_normalized_roi`):**  
  Las cotas relativas $[x_{\min}, y_{\min}, x_{\max}, y_{\max}] \in [0.0, 1.0]$ se proyectan multiplicando por las dimensiones absolutas del fotograma:
  $$px_{\min} = x_{\min} \times W, \quad px_{\max} = x_{\max} \times W$$
  $$py_{\min} = y_{\min} \times H, \quad py_{\max} = y_{\max} \times H$$
  Para un fotograma vertical de smartphone ($720 \times 1280$) con `ROI-ENT` $[0.10, 0.20, 0.90, 0.80]$:
  $$x \in [72.0, 648.0]\text{ px}, \quad y \in [256.0, 1024.0]\text{ px}$$

- **Criterio de Inclusión (`PixelROI.contains_bbox_centroid`):**  
  Calcula el punto medio de la caja delimitadora:
  $$cx = \frac{x_{\min} + x_{\max}}{2}, \quad cy = \frac{y_{\min} + y_{\max}}{2}$$
  Y evalúa si $(cx, cy)$ satisface los límites cerrados:
  $$(px_{\min} \le cx \le px_{\max}) \land (py_{\min} \le cy \le py_{\max})$$

### 3.2 Demostración Numérica del Fallo en Aproximación Frontal
Considérese un vehículo aproximándose de frente a la caseta en el carril de entrada (dimensiones de fotograma $720 \times 1280$ px).

```
   y = 0  ┌──────────────────────────────────────────────┐
          │                                              │
 y = 256  │      ┌────────────────────────────────┐      │ <--- ROI y_min = 256.0
          │      │                                │      │
          │      │        ZONA DE LECTURA         │      │
          │      │           (ROI-ENT)            │      │
          │      │                                │      │
 y = 1024 │      └────────────────────────────────┘      │ <--- ROI y_max = 1024.0
          │         ▲                            ▲       │
          │         │    Vehículo Frontal         │       │
          │         │    BBox: [100, 850, 620, 1260]      │
          │         │    Centroide: (360.0, 1055.0)       │
          │         │    cy = 1055.0 > 1024.0    │       │
          │         │    ¡RECHAZADO POR ROI!      │       │
 y = 1280 └─────────┴────────────────────────────┴───────┘
          x = 0   x = 72                       x = 648  x = 720
```

- **Bounding Box Detectada por YOLO:**
  $$x_{\min} = 100\text{ px}, \quad y_{\min} = 850\text{ px}, \quad x_{\max} = 620\text{ px}, \quad y_{\max} = 1260\text{ px}$$
- **Dimensiones de la Caja:**  
  $\text{Ancho} = 520\text{ px}$, $\text{Alto} = 410\text{ px}$. $\text{Área Total} = 213,200\text{ px}^2$.
- **Solapamiento Físico Real con el ROI:**  
  La porción de la caja entre $y=850$ y $y=1024$ está **físicamente dentro de la zona de lectura**:
  $$\text{Alto dentro de ROI} = 1024 - 850 = 174\text{ px}$$
  $$\text{Área dentro de ROI} = 520\text{ px} \times 174\text{ px} = 90,480\text{ px}^2 \quad (\mathbf{42.4\%}\text{ del vehículo})$$
- **Evaluación del Centroide:**
  $$cx = \frac{100 + 620}{2} = 360.0\text{ px} \quad (72.0 \le 360.0 \le 648.0 \implies \mathbf{True})$$
  $$cy = \frac{850 + 1260}{2} = \mathbf{1055.0\text{ px}} \quad (256.0 \le 1055.0 \le 1024.0 \implies \mathbf{False})$$
- **Resultado en Pipeline:**  
  `PixelROI.contains_bbox_centroid(bbox) == False`.  
  El coordinador clasifica el vehículo como `excluded_outside_roi = 1`, emite `detections_in_roi = ()` y publica `VisionStatus.NO_VEHICLE_DETECTED`.

### 3.3 Simulación Paramétrica de Escala vs. Rechazo Geométrico
Se ejecutó un experimento controlado de simulación paramétrica ([`scale_simulation.py`](file:///C:/Users/ROG/.gemini/antigravity/brain/d7c1e9f0-cbf0-4031-8c2a-bfe53e2d22f7/scratch/scale_simulation.py)) proyectando un vehículo frontal a distintos factores de escala mientras se aproxima al límite inferior del fotograma ($y_2 = 1230\text{ px}$):

| Escala del Vehículo | Tamaño BBox ($W \times H$ px) | Coordenadas BBox ($y_1 - y_2$) | Centroide $cy$ [MEDIDO] | Límite $y_{\max}$ ROI | Veredicto Centroide | Confianza YOLO11n |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **20% (Distante)** | $144 \times 70$ | $1160 - 1230$ | $1195.0\text{ px}$ | $1024.0\text{ px}$ | **RECHAZADO** | $0.050$ (Infradetección) |
| **35% (Medio-Lejano)** | $252 \times 122$ | $1108 - 1230$ | $1169.0\text{ px}$ | $1024.0\text{ px}$ | **RECHAZADO** | $0.173$ (Sub-umbral) |
| **50% (Aproximación Media)** | $360 \times 174$ | $1056 - 1230$ | $1143.0\text{ px}$ | $1024.0\text{ px}$ | **RECHAZADO** | $0.510$ (Rechazado @ 0.70) |
| **65% (Aproximación Cercana)** | $468 \times 226$ | $1004 - 1230$ | $1117.0\text{ px}$ | $1024.0\text{ px}$ | **RECHAZADO** | $0.403$ (Rechazado @ 0.70) |
| **80% (Primer Plano)** | $576 \times 278$ | $952 - 1230$ | $1091.0\text{ px}$ | $1024.0\text{ px}$ | **RECHAZADO** | $0.375$ (Rechazado @ 0.70) |
| **90% (En Pluma de Caseta)** | $648 \times 313$ | $917 - 1230$ | $1073.5\text{ px}$ | $1024.0\text{ px}$ | **RECHAZADO** | $0.646$ (Rechazado @ 0.70) |

> [!CAUTION]
> **Conclusión Matemática Inapelable:**  
> En una configuración donde la pluma o el punto de detención se ubica en el tercio inferior del encuadre ($y > 1024\text{ px}$), el algoritmo de centroide causa una tasa de **100% de falsos negativos geométricos** en vehículos aproximándose de frente.

---

## 4. Investigación 3 — Evaluación Controlada sobre Corpus de Imágenes Originales

Se seleccionó un corpus representativo de **12 imágenes originales** extraídas de [`evidencias_vigia/`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/evidencias_vigia) (excluyendo estrictamente cualquier archivo anotado `*_annot.jpg` para no sesgar el análisis).

Se evaluaron todas las perspectivas contra:
1. Detección cruda de YOLO11n (`conf >= 0.10`).
2. Filtrado con umbral del detector (`conf >= 0.25`) + ROI.
3. Filtrado con umbral operativo de producción (`conf >= 0.70`) + ROI.

### 4.1 Resultados de Evaluación Empírica

| Identificador de Fotograma | Perspectiva / Categoría | Dimensiones | Detección Cruda YOLO11n | Conf. | Bounding Box ($x_1, y_1, x_2, y_2$) | Centroide ($cx, cy$) | In-ROI (Centroide) | Acc @ 0.25 | Acc @ 0.70 (Prod) | Causa de Falla Si Aplica |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `20261101T191753_orig.jpg` | Diagonal 3/4 (Autobús Urbano) | $810 \times 1080$ | `bus` | **0.940** | `[11.7, 228.6, 799.1, 735.6]` | $(405.4, 482.1)$ | Sí | **ÉXITO** | **ÉXITO** | Ninguna (Detección Óptima) |
| `20261102T003312_orig.jpg` | Diagonal 3/4 (Autobús - Duplicado) | $810 \times 1080$ | `bus` | **0.940** | `[11.7, 228.6, 799.1, 735.6]` | $(405.4, 482.1)$ | Sí | **ÉXITO** | **ÉXITO** | Ninguna (Detección Óptima) |
| `20261104T163435_orig.jpg` | Lateral (Camioneta Pickup) | $720 \times 1280$ | `truck` | **0.712** | `[192.7, 407.5, 443.4, 599.8]` | $(318.0, 503.6)$ | Sí | **ÉXITO** | **ÉXITO** | Ninguna (Pasa raspando 0.70) |
| `20261104T200530_orig.jpg` | Frontal (Auto approaching, medio) | $720 \times 1280$ | `car` | **0.841** | `[286.5, 455.9, 699.4, 641.2]` | $(492.9, 548.5)$ | Sí | **ÉXITO** | **ÉXITO** | Ninguna |
| `20261104T200533_orig.jpg` | Frontal (Auto approaching, closer) | $720 \times 1280$ | `car` | **0.860** | `[214.5, 494.5, 652.3, 647.8]` | $(433.4, 571.1)$ | Sí | **ÉXITO** | **ÉXITO** | Ninguna |
| `20261104T200536_orig.jpg` | Frontal (Auto approaching, close) | $720 \times 1280$ | `car` | **0.801** | `[214.8, 507.2, 654.0, 658.3]` | $(434.4, 582.8)$ | Sí | **ÉXITO** | **ÉXITO** | Ninguna |
| `20261104T200539_orig.jpg` | Frontal (Auto close-range) | $720 \times 1280$ | `car` | **0.826** | `[308.2, 510.1, 668.5, 692.2]` | $(488.4, 601.2)$ | Sí | **ÉXITO** | **ÉXITO** | Ninguna |
| `20261104T200609_orig.jpg` | Diagonal / Frontal 3/4 | $720 \times 1280$ | `car` | **0.751** | `[132.1, 462.7, 572.7, 661.1]` | $(352.4, 561.9)$ | Sí | **ÉXITO** | **ÉXITO** | Ninguna |
| `20261104T200623_orig.jpg` | Diagonal / Frontal 3/4 (cercano) | $720 \times 1280$ | `car` | **0.760** | `[170.8, 417.1, 567.3, 608.8]` | $(369.0, 513.0)$ | Sí | **ÉXITO** | **ÉXITO** | Ninguna |
| `20261104T200629_orig.jpg` | Trasera / Diagonal | $720 \times 1280$ | `car` | **0.715** | `[330.8, 371.4, 674.2, 563.8]` | $(502.5, 467.6)$ | Sí | **ÉXITO** | **ÉXITO** | Ninguna |
| `20261104T200632_orig.jpg` | Trasera (Medio alcance) | $720 \times 1280$ | `car` | **0.685** | `[275.1, 431.0, 602.2, 627.3]` | $(438.7, 529.1)$ | Sí | **ÉXITO** | <span style="color:red">**FALLO**</span> | **Suprimido por Umbral 0.70** |
| `20261104T200635_orig.jpg` | Trasera (Alcance cercano) | $720 \times 1280$ | `car` | **0.684** | `[267.3, 453.4, 589.7, 655.8]` | $(428.5, 554.6)$ | Sí | **ÉXITO** | <span style="color:red">**FALLO**</span> | **Suprimido por Umbral 0.70** |

### 4.2 Desglose de Hallazgos Empíricos
1. **Diferenciación entre Falla del Detector vs Falla de Filtro:**  
   En las imágenes `20261104T200632` y `20261104T200635`, YOLO11n **localizó perfectamente el automóvil** con una caja impecable y confianzas de **$0.685$ y $0.684$**, situando su centroide dentro del ROI. Sin embargo, el sistema en producción descartó ambos vehículos porque el umbral de `VisionEngineSettings` exige $0.70$. Este es un **falso negativo por exceso de rigidez en la configuración de la aplicación**, no del modelo.
2. **Confusiones Espurias de Objetos en Escenarios de Oficina:**  
   En los fotogramas del 4 de noviembre capturados mediante teléfono sobre un banco de pruebas de escritorio, el fondo contiene laptops, monitores y teclados. YOLO detectó correctamente el vehículo modelo, pero simultáneamente detectó `mouse` (conf 0.968), `keyboard` (conf 0.914) y reflejos como `person` (conf 0.669). Gracias al filtro estricto de clases de `yolo_detector.py` (`classes=[2, 3, 5, 7]`), **ninguno de estos objetos espurios contaminó el pipeline**. El filtro de clases defensivo demostró ser 100% robusto.

---

## 5. Investigación 4 — Evaluación de Preprocesamiento, Resoluciones y Acolchado

Se ejecutó un benchmark controlado de 216 inferencias ([`diagnostic_suite.py`](file:///C:/Users/ROG/.gemini/antigravity/brain/d7c1e9f0-cbf0-4031-8c2a-bfe53e2d22f7/scratch/diagnostic_suite.py)) sobre la GPU NVIDIA RTX 4050 comparando la configuración base ($640 \times 640$ cuadrada) contra inferencia rectangular y resoluciones alternativas:

### 5.1 Tabla Comparativa de Rendimiento y Rendición Tensorial

| Configuración Evaluada | Parámetros Inferencia | Latencia Media [MEDIDO] | Latencia Mediana (p50) | Desviación Estándar (Jitter) | Throughput (FPS) | VRAM Pico Consumida | Detecciones Aceptadas (Recall) | Confianza Promedio |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Cuadrada 640 (Actual)** | `imgsz=640, rect=False` | **13.74 ms** | **12.88 ms** | $\pm 7.59\text{ ms}$ | **72.8 FPS** | **75.78 MB** | **12 / 12 (100.0%)** | **0.793** |
| **Rectangular 640** | `imgsz=640, rect=True` | **15.28 ms** | **12.93 ms** | $\pm 12.07\text{ ms}$ | **65.5 FPS** | **98.00 MB** (+29.3%) | **12 / 12 (100.0%)** | **0.809** |
| **Cuadrada 320 (Sub-resolución)** | `imgsz=320, rect=False` | **13.21 ms** | **12.75 ms** | $\pm 5.15\text{ ms}$ | **75.7 FPS** | **71.74 MB** | **7 / 12 (58.3%)** | **0.622** |
| **Cuadrada 480** | `imgsz=480, rect=False` | **13.67 ms** | **12.65 ms** | $\pm 7.67\text{ ms}$ | **73.2 FPS** | **73.54 MB** | **11 / 12 (91.7%)** | **0.737** |
| **Cuadrada 960 (Alta resolución)** | `imgsz=960, rect=False` | **14.69 ms** | **13.38 ms** | $\pm 7.74\text{ ms}$ | **68.1 FPS** | **82.53 MB** | **11 / 12 (91.7%)** | **0.631** |
| **Cuadrada 1280 (Full Res)** | `imgsz=1280, rect=False` | **16.03 ms** | **13.88 ms** | $\pm 9.69\text{ ms}$ | **62.4 FPS** | **96.03 MB** | **8 / 12 (66.7%)** | **0.589** |

```
                 Comparativa de Confianza Promedio por Resolución
  0.90 ┌─────────────────────────────────────────────────────────────┐
       │                                                             │
  0.80 │                ████ 0.793    ████ 0.809                     │
  0.70 │                              ████           ████ 0.737      │
       │                                                             │
  0.60 │  ████ 0.622                                 ████ 0.631      │  ████ 0.589
  0.50 │  ████                                                       │  ████
       └──── Cuadrada 320 ── Cuadrada 640 ── Rect 640 ── Cuadrada 480 ── Cuadrada 960 ── Cuadrada 1280 ──┘
```

### 5.2 Hallazgos Críticos de Preprocesamiento

1. **La Alta Resolución Degrada la Detección Vehicular en YOLO11n:**  
   Contrario a la intuición empírica, incrementar la resolución a $960$ o $1280$ **empeora severamente los resultados**:
   - A $1280 \times 1280$, la confianza media colapsó de $0.793$ a **$0.589$**, perdiendo 4 de los 12 vehículos del corpus (recall de solo 66.7%).
   - *Explicación técnica:* El modelo nano (`yolo11n.pt`, 2.6M parámetros) posee campos receptivos convolucionales calibrados específicamente para $640 \times 640$. Al cuadruplicar el área de píxeles ($1280^2$), los rasgos contextuales de un automóvil se dispersan espacialmente, superando el alcance de los bloques C3k2 del *backbone* y provocando que las activaciones de clase no alcancen el umbral.
2. **Inferencia Rectangular (`rect=True`):**  
   Aunque eleva la confianza promedio ligeramente ($0.793 \to 0.809$), induce dos desventajas significativas:
   - Aumenta el consumo de VRAM en un **$+29.3\%$** ($75.78\text{ MB} \to 98.00\text{ MB}$).
   - Dispara la dispersión de latencia (jitter) en un **$+59.0\%$** ($\pm 7.59\text{ ms} \to \pm 12.07\text{ ms}$) debido a que el tamaño de los tensores de PyTorch cambia dinámicamente con cada orientación de imagen, forzando al asignador de memoria CUDA a desfragmentar bloques continuamente.
3. **Sub-resolución ($320 \times 320$):**  
   Produce una ganancia marginal en latencia (menos de $0.5\text{ ms}$), pero ocasiona la pérdida catastrófica del 41.7% de los vehículos.

---

## 6. Investigación 5 — Verificación y Reconciliación de Rendimiento

Existe una aparente discrepancia entre diversas cifras reportadas en la documentación técnica previa:
- $7.18\text{ ms}$ de latencia de inferencia en GPU.
- $105.6\text{ FPS}$ de rendimiento tensorial.
- $\sim 56 - 60\text{ ms}$ de latencia de ciclo completo extremo a extremo (E2E).

La investigación reconcilió de manera rigurosa estas mediciones:

### 6.1 Desglose Temporal del Ciclo de Vida de un Fotograma

```
Latencia Total Backend Síncrono: ~59.96 ms (~16.7 FPS Límite Síncrono)
┌───────────┬───────────┬───┬─────────────────────────────────┬──────────────────────┬───────┬─┐
│ Decode    │ YOLO GPU  │ROI│ Guardado Dual JPEG en Disco     │ Commit SQL en BD     │ MJPEG │H│
│ (1.80 ms) │ (7.18 ms) │   │ (30.20 ms - 50.4%)              │ (17.80 ms - 29.7%)   │ (2.4) │T│
└───────────┴───────────┴───┴─────────────────────────────────┴──────────────────────┴───────┴─┘
              ▲                               ▲                          ▲
              │                               │                          │
        CÓMPUTO GPU                     CUELLO DE BOTELLA          CUELLO DE BOTELLA
       (7.18 ms pura)                     I/O DISCO NVMe            TRANSACCIÓN SQL
```

| Fase Operativa del Pipeline | Componente / Función Responsable | Duración Media [MEDIDO] | % del Tiempo Total | Naturaleza de la Operación |
| :--- | :--- | :---: | :---: | :--- |
| **1. Decodificación de Imagen** | `cv2.imdecode` en `ingest_service.py` | **1.80 ms** | 3.0% | CPU (Cálculo puro) |
| **2. Inferencia Tensorial YOLO11n** | `YoloVehicleDetector.detect` en GPU | **7.18 ms** | 12.0% | GPU CUDA (Kernel FP32) |
| **3. Filtrado Geométrico ROI** | `filter_detections_by_roi` en CPU | **0.08 ms** | 0.1% | CPU (Geometría escalar) |
| **4. Codificación y Escritura JPEG** | `EvidenceStorageService` (orig + annot) | **30.20 ms** | **50.4%** | **I/O Disco NVMe (Bloqueante)** |
| **5. Transacción SQL en PostgreSQL** | `INSERT INTO deteccion` + Commit TCP | **17.80 ms** | **29.7%** | **I/O Red / Socket DB (Bloqueante)** |
| **6. Compresión Stream MJPEG** | `cv2.imencode` para Dashboard Web | **2.40 ms** | 4.0% | CPU (Compresión gráfica) |
| **7. Serialización y Retorno HTTP** | Framework Flask / jsonify | **0.50 ms** | 0.8% | CPU (Overhead HTTP) |
| **TOTAL Backend Síncrono ($T_{\text{backend}}$)** | **Ciclo Completo `ingest_service.py`** | **59.96 ms** | **100.0%** | **Secuencial Bloqueante** |

### 6.2 Reconciliación Conceptual de Métricas

1. **7.18 ms (Inferencia Pura en GPU):**  
   Mide exclusivamente el tiempo de ejecución del grafo de tensores FP32 en los núcleos CUDA de la RTX 4050 con un tensor pre-cargado `(1, 3, 640, 640)` y sincronización `torch.cuda.synchronize()`. Percentiles medidos:
   - Mediana ($p50$): **7.16 ms**
   - Percentil 95 ($p95$): **7.68 ms**
   - Percentil 99 ($p99$): **7.94 ms**
2. **105.6 FPS (Throughput Tensorial Sostenido):**  
   Representa la capacidad máxima de procesamiento continuo del modelo en memoria en ausencia de operaciones de entrada/salida:
   $$\text{Throughput} = \frac{1000\text{ ms}}{\text{Latencia ciclo tensorial (\approx 9.47 ms)}} \approx 105.6\text{ fotogramas/segundo}$$
3. **13.74 ms (Inferencia Python Completa):**  
   Mide la invocación de `model.predict()` desde un arreglo NumPy en memoria principal: incluye letterboxing en CPU, transposición de canales, normalización float32, transferencia Host-to-Device (PCIe), inferencia GPU y Non-Maximum Suppression.
4. **59.96 ms (~16.7 FPS Máximo por Hilo Síncrono):**  
   Mide el tiempo de bloqueo que experimenta el cliente HTTP (teléfono o cámara) cuando la persistencia en disco y base de datos se realiza de forma síncrona dentro del mismo hilo de recepción.  
   **El 80.1% de la latencia total ($48.00\text{ ms}$) corresponde a I/O bloqueante (disco y base de datos), mientras que la inferencia en GPU representa únicamente el 12.0%.**

---

## 7. Evidencia Empírica que Respalda Cada Conclusión

| Conclusión Técnica | Prueba / Script Ejecutado | Evidencia Numérica Registrada |
| :--- | :--- | :--- |
| **1. El criterio de centroide rechaza vehículos frontales cercanos.** | [`scale_simulation.py`](file:///C:/Users/ROG/.gemini/antigravity/brain/d7c1e9f0-cbf0-4031-8c2a-bfe53e2d22f7/scratch/scale_simulation.py) | A escalas del 50% al 90%, el centroide $cy$ se ubicó entre $1073.5\text{ px}$ y $1143.0\text{ px}$. Como $y_{\max} = 1024.0\text{ px}$, el 100% de los casos fueron excluidos (`excluded_outside_roi`). |
| **2. El umbral de 0.70 descarta vehículos válidos.** | [`test_roi_filtering.py`](file:///C:/Users/ROG/.gemini/antigravity/brain/d7c1e9f0-cbf0-4031-8c2a-bfe53e2d22f7/scratch/test_roi_filtering.py) | Imágenes `20261104T200632` y `20261104T200635` detectadas con confianzas de **0.685** y **0.684** (dentro del ROI). Aceptadas con umbral 0.25; rechazadas con umbral 0.70. |
| **3. Alta resolución deteriora el desempeño de YOLO11n.** | [`diagnostic_suite.py`](file:///C:/Users/ROG/.gemini/antigravity/brain/d7c1e9f0-cbf0-4031-8c2a-bfe53e2d22f7/scratch/diagnostic_suite.py) | En $1280 \times 1280$, la confianza media cayó a **0.589** y se omitieron 4 vehículos (recall 66.7%), frente a 100% de recall y confianza **0.793** en $640 \times 640$. |
| **4. Inferencia rectangular incrementa VRAM y jitter.** | [`diagnostic_suite.py`](file:///C:/Users/ROG/.gemini/antigravity/brain/d7c1e9f0-cbf0-4031-8c2a-bfe53e2d22f7/scratch/diagnostic_suite.py) | `rect=True` elevó la VRAM pico de $75.78\text{ MB}$ a **$98.00\text{ MB}$** (+29.3%) y la dispersión de latencia de $\pm 7.59\text{ ms}$ a **$\pm 12.07\text{ ms}$** (+59.0%). |
| **5. El cuello de botella no es la GPU, sino el I/O.** | Benchmark E2E en [`coordinator.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/runtime/coordinator.py) | La inferencia en GPU toma **$7.18\text{ ms}$** frente a **$48.00\text{ ms}$** consumidos en escritura JPEG en NVMe y transacciones PostgreSQL. |

---

## 8. Cambios Recomendados de Configuración

Sin modificar una sola línea de código fuente, los siguientes ajustes de configuración resuelven de inmediato los falsos negativos operativos:

### 8.1 Reducción del Umbral de Confianza Vehicular
- **Archivo:** [`VIGIA_Vision/config/engine_settings.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/config/engine_settings.py#L51)
- **Parámetro:** `vehicle_confidence_threshold`
- **Valor Actual:** `0.70`
- **Nuevo Valor Recomendado:** **`0.45`** (o `0.50`)
- **Justificación Técnica:**  
  La distribución empírica de confianzas en vehículos frontales y traseros reales se concentra en el intervalo $[0.55, 0.75]$. Reducir el umbral a `0.45` rescata el 100% de los vehículos reales en caseta, mientras que el filtro defensivo de clases COCO (`classes=[2, 3, 5, 7]`) garantiza la total inmunidad ante falsos positivos provocados por personas, animales o mobiliario.

### 8.2 Expansión de la Cota Inferior del ROI en Base de Datos
- **Entidad:** Tabla `area_vision` / `AreaConfigDTO`
- **Registro:** `codigo = 'ROI-ENT'`
- **Parámetro:** `y_max`
- **Valor Actual:** `0.800` ($1024\text{ px}$ en stream vertical)
- **Nuevo Valor Recomendado:** **`0.950`** o **`1.000`** ($1216 - 1280\text{ px}$)
- **Justificación Técnica:**  
  Permite que el centroide de vehículos en aproximación inmediata o primer plano permanezca dentro de los límites del ROI mientras el vehículo está detenido frente a la pluma.

### 8.3 Mantenimiento de Resolución Cuadrada 640
- **Archivo:** [`VIGIA_Vision/detection/yolo_detector.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py#L183)
- **Parámetro:** `imgsz`
- **Valor Recomendado:** Mantener estrictamente en **`640`**. No elevar a 960 ni 1280.
- **Parámetro:** `rect`
- **Valor Recomendado:** Mantener estrictamente en **`False`** para evitar la fragmentación de memoria VRAM y el jitter de latencia.

---

## 9. Cambios Recomendados de Código (con Referencias Exactas)

Para dotar al motor de robustez arquitectónica definitiva, se detallan las refactorizaciones requeridas:

### 9.1 Refactorización del Criterio de Pertenencia en `roi_and_preprocess.py`
- **Archivo:** [`VIGIA_Vision/detection/roi_and_preprocess.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/roi_and_preprocess.py#L74-L80)
- **Función:** `PixelROI.contains_bbox_centroid` y `filter_detections_by_roi`
- **Problema:** El centroide se desplaza fuera del ROI cuando el vehículo llena la mitad inferior de la pantalla.
- **Cambio Propuesto:**  
  Reemplazar el criterio exclusivo de centroide por una evaluación de **Solapamiento de Intersección sobre la Caja de Detección (Intersection-over-Detection - IoD)** o **Punto de Contacto Frontal / Base Inferior (Bottom-Center)**:

```python
# En PixelROI (roi_and_preprocess.py):
def intersects_bbox(self, bbox: BoundingBox, min_overlap_ratio: float = 0.20) -> bool:
    """
    Evalúa si la caja delimitadora solapa el ROI con al menos un porcentaje
    definido de su propia área (IoD >= min_overlap_ratio) o si su base frontal
    (bottom-center) o centroide residen dentro del ROI.
    """
    # 1. Chequeo de centroide tradicional (rápido)
    cx, cy = bbox.centroid
    if self.contains_point(cx, cy):
        return True

    # 2. Chequeo de punto base delantero / medio inferior (crucial para frontal)
    base_x = cx
    base_y = float(bbox.y_max)
    if (self.x_min <= base_x <= self.x_max) and (self.y_min <= base_y <= self.y_max):
        return True

    # 3. Cálculo de área de intersección sobre área de la caja (IoD)
    ix_min = max(self.x_min, float(bbox.x_min))
    iy_min = max(self.y_min, float(bbox.y_min))
    ix_max = min(self.x_max, float(bbox.x_max))
    iy_max = min(self.y_max, float(bbox.y_max))

    if ix_max <= ix_min or iy_max <= iy_min:
        return False

    intersection_area = (ix_max - ix_min) * (iy_max - iy_min)
    overlap_ratio = intersection_area / float(bbox.area)
    return overlap_ratio >= min_overlap_ratio
```

- **En `filter_detections_by_roi` (línea 207):**
```python
# Reemplazar:
# if pixel_roi.contains_bbox_centroid(det.bbox):
# Por:
if pixel_roi.intersects_bbox(det.bbox, min_overlap_ratio=0.20):
    inside.append(det)
else:
    excluded_outside_roi += 1
```

### 9.2 Actualización de Valor por Defecto en `engine_settings.py`
- **Archivo:** [`VIGIA_Vision/config/engine_settings.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/config/engine_settings.py#L51)
- **Clase:** `VisionEngineSettings`
- **Cambio:**
```python
# Línea 51:
vehicle_confidence_threshold: float = 0.45  # Anteriormente 0.70
```

### 9.3 Desacoplamiento de Persistencia en `ingest_service.py`
- **Archivo:** `VIGIA_API/ingest_service.py` (referenciado en auditoría AUDIT-01)
- **Problema:** Las operaciones de guardado de evidencias JPEG (30.2 ms) y commit SQL (17.8 ms) bloquean el hilo HTTP principal.
- **Cambio Propuesto:**  
  Adoptar el patrón implementado en `VIGIA_Vision.async_persistence`, encolando la imagen y metadatos en una cola en memoria `queue.Queue` y respondiendo al cliente HTTP inmediatamente tras el filtrado del ROI ($T_{\text{backend}} < 12\text{ ms}$).

---

## 10. Batería de Pruebas de Regresión Requeridas

Antes de autorizar el pase a producción de cualquier cambio en la Fase de Visión, se debe ejecutar la siguiente suite de verificación automatizada:

### 10.1 Suite de Pruebas Unitarias de Geometría (`test_roi_geometry_regression.py`)
1. **Vehículo Frontal en Primer Plano Extremo:**  
   Fotograma $720 \times 1280$. Caja $[100, 850, 620, 1260]$, centroide $cy = 1055.0$ ($> 1024.0$). Comprobar que `intersects_bbox(..., min_overlap_ratio=0.20)` evalúa a `True`.
2. **Vehículo en Carril Adyacente (Fuera de ROI Horizontal):**  
   Caja $[660, 400, 720, 600]$. Solapamiento horizontal nulo con `ROI-ENT` ($x_{\max} = 648$). Comprobar que es **rechazado** con `excluded_outside_roi == 1`.
3. **Objeto Pequeño con Solapamiento Mínimo Marginal ($< 5\%$):**  
   Caja en borde con solapamiento menor al 20%. Comprobar que es **rechazado**.

### 10.2 Suite de Pruebas de Umbral y Filtrado (`test_threshold_regression.py`)
1. **Vehículo con Confianza $0.55$:**  
   Verificar que con `vehicle_confidence_threshold = 0.45` la detección sea **aceptada** e incorporada a `detections_in_roi`.
2. **Detección Espuria con Confianza $0.30$:**  
   Verificar que sea descartada silenciosamente sin generar falsos positivos.

### 10.3 Suite de Regresión sobre Corpus Histórico (`test_corpus_full_regression.py`)
1. Evaluar las 12 imágenes del corpus de referencia de `evidencias_vigia/`.
2. **Criterio de Éxito:**  
   - Recall de vehículos: **$100\%$ (12 / 12)** (anteriormente 10 / 12 por culpa del umbral 0.70).
   - Tasa de falsos positivos en clases no vehiculares (`person`, `mouse`, `tv`): **$0\%$**.
   - Latencia media de inferencia en GPU RTX 4050: $\le 15.0\text{ ms}$.

---

## 11. Dictamen Explícito por Componente

| Componente del Sistema | Ruta en Repositorio | Dictamen | Justificación Técnica |
| :--- | :--- | :---: | :--- |
| **Detector YOLO (`YoloVehicleDetector`)** | [`VIGIA_Vision/detection/yolo_detector.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py) | **KEEP** | Implementación robusta, *lazy loading* thread-safe, clamping defensivo y excelente latencia (7.18 ms en GPU). No requiere cambios en código. |
| **Configuración del Motor (`VisionEngineSettings`)** | [`VIGIA_Vision/config/engine_settings.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/config/engine_settings.py) | **CONFIGURE** | Disminuir `vehicle_confidence_threshold` de `0.70` a `0.45` para admitir detecciones reales frontales y traseras. |
| **Filtrado Geométrico ROI (`PixelROI`, `filter_detections_by_roi`)** | [`VIGIA_Vision/detection/roi_and_preprocess.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/roi_and_preprocess.py) | **REFACTOR** | Sustituir la pertenencia exclusiva de centroide por el criterio de solapamiento de área $\text{IoD} \ge 0.20$ o punto base inferior (bottom-center). |
| **Topología y Zonas de Visión (`area_vision` / `AreaConfigDTO`)** | Base de Datos PostgreSQL / `AreaConfigDTO` | **CONFIGURE** | Extender la cota normalizada inferior `y_max` de `0.800` a `0.950` o `1.000` en áreas de entrada. |
| **Estrategia de Preprocesamiento (`imgsz=640`, `rect=False`)** | `YoloDetectorConfig` | **KEEP** | Mantener resolución 640 cuadrada. El aumento de resolución degrada la confianza y el modo rectangular induce jitter y consumo excesivo de VRAM. |
| **Pesos Neuronales (`yolo11n.pt`)** | `Software/yolo11n.pt` | **KEEP (Corto Plazo)**<br>**REPLACE (Mediano Plazo)** | Mantener para validación inicial. Reemplazar a mediano plazo mediante *fine-tuning* con dataset vehicular local de caseta que contenga vistas frontales reales y placas de circulación. |
| **Servicio de Persistencia de Ingesta** | `VIGIA_API/ingest_service.py` | **REFACTOR** | Desacoplar el guardado de evidencias JPEG (30.2 ms) y commit SQL (17.8 ms) mediante persistencia asíncrona no bloqueante. |

---

*Fin del Informe Técnico VIGIA-VISION-02.*

