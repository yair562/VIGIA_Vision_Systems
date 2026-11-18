# VIGIA-VISION-05B — Implementación Modular de Clasificación de Color Vehicular

**Proyecto:** VIGÍA Vision Systems  
**Fase:** `VISION-05B`  
**Tipo:** Auditoría de pipeline, diseño de arquitectura modular, implementación de clasificación cromática, benchmark fotométrico, integración desacoplada y pruebas de regresión  
**Fecha de Emisión:** 16 de noviembre de 2026  
**Hardware de Evaluación:** NVIDIA GeForce RTX 4050 Laptop GPU (6 GB VRAM) / Intel Core i7-13620H (16 CPUs, 16 GB RAM)  
**Entorno de Ejecución:** Windows 11, Python 3.11 (`.venv_cuda` con PyTorch 2.6.0+cu124, OpenCV 4.10.0, NumPy 1.26.4)  
**Modelos de Detección Evaluados:** `yolo26x.pt` (CUDA FP16, imgsz=640, NMS-Free) y `yolo11n.pt` (CUDA FP16 / CPU Fallback)  
**Dictamen Oficial:** **`APPROVED — COLOR CLASSIFIER IMPLEMENTED`** (Clasificador modular implementado, evaluado, integrado de forma no disruptiva en `VisionEngineCoordinator` y verificado con regresión integral al 100%).

---

## 1. Resumen Ejecutivo

La fase **VIGIA-VISION-05B** responde al mandato técnico de dotar a VIGÍA Vision Systems de una capacidad analítica complementaria e independiente para identificar el **color predominante de la carrocería** de vehículos detectados por el sistema, superando la limitación histórica donde el pipeline únicamente reportaba clase, confianza y caja delimitadora.

```mermaid
flowchart LR
    A["Frame BGR Original + BBox en ROI"] --> B["1. Quality Gate (Geometría, Luminancia V, Glare)"]
    B -->|Calidad Insuficiente| U["Retornar UNKNOWN (fail-safe)"]
    B -->|Válido| C["2. Muestreo Anatómico Carrocería (Y: 28%-78%, X: 10%-90%)"]
    C --> D["3. Exclusión de Parabrisas, Cristales, Neumáticos, Asfalto y Fondo"]
    D -->|Señal Útil < 12%| U
    D -->|Píxeles Limpios| E["4. Normalización Cromática (CIELAB + HSV)"]
    E --> F["5. Clasificación Jerárquica + Calibración de Confianza"]
    F -->|Margen < 0.10 o Conf < 0.40| U
    F -->|Decisión Firme| G["VehicleColorResult(Color, Confianza, Calidad, Scores)"]
```

### Logros y Verificaciones Clave

1. **Diseño Modular y Desacoplado (`VIGIA_Vision.classification` y `VIGIA_Vision.detection.color_classifier`):**
   - Implementación de [`VehicleColorClassifier`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/color_classifier.py), [`VehicleColorResult`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/color_classifier.py#L84-L117), [`VehicleColorNormalizer`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/color_classifier.py#L380-L450) y [`VehicleColorConfig`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/color_classifier.py#L118-L160).
   - Recibe frame original, BBox, clase y confianza; retorna color, confianza, estado y métricas de calidad sin mutar las entradas.
   - Taxonomía estricta de 12 clases: `WHITE`, `BLACK`, `GRAY`, `SILVER`, `RED`, `BLUE`, `GREEN`, `YELLOW`, `BROWN`, `ORANGE`, `OTHER`, `UNKNOWN`.

2. **Estrategia Fotométrica Híbrida (HSV + CIELAB) sin Sobrecarga GPU:**
   - Cero consumo de memoria VRAM adicional. Ejecución ultrarrápida en CPU vía OpenCV vectorizado y NumPy.
   - **Latencia media:** **`1.81 ms`** (mediana `1.50 ms`, percentil 90 `2.64 ms`).
   - **Throughput analítico:** **`552.9 FPS`**, lo que garantiza un impacto nulo en el pipeline operativo y un margen de **`> 36x`** frente a la tasa requerida de `15.0 FPS` (`66.7 ms`).

3. **Muestreo Anatómico y Supresión Estricta de Artefactos:**
   - Descarta el 28% superior de la caja (parabrisas, cristales, techo y cielo).
   - Descarta el 22% inferior (ruedas, neumáticos, sombras del suelo y asfalto).
   - Enmascara el perímetro exterior para eliminar contaminación de fondo.
   - Filtra sombras profundas ($V < 28$, $L^* < 20$) y reflejos especulares deslumbrantes ($V > 248$, $S < 25$).

4. **Comportamiento Conservador y Rechazo Asistido a `UNKNOWN`:**
   - La tasa de rechazo fail-safe ante situaciones ambiguas o baja iluminación es del **`10.81%`** en detecciones ROI operativas.
   - En baja iluminación severa, el clasificador rechaza el **`83.33%`** (15/18) a `UNKNOWN` por diseño de seguridad, evitando alucinaciones cromáticas.

5. **Precisión Verificada sobre Evidencias Reales (`evidencias_vigia/`):**
   - **Calibración Sintética:** **`100.0%` (13/13)** sobre parches cromáticos y condiciones límite.
   - **Precisión Efectiva (excluyendo abstenciones UNKNOWN):** **`86.06%` (142 / 165 aciertos)** sobre 185 cajas evaluables de vehículos confirmados en ROI.
   - **Precisión General Absoluta:** **`76.76%` (142 / 185)**.

6. **Integración Fail-Safe y No Disruptiva:**
   - Extensión no disruptiva de [`VisionResult`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Core/domain/vision_result.py#L98-L125) (`vehicle_color_pred: Optional[str]`, `vehicle_color_confidence: Optional[float]`) y [`VisionObservationEnvelope`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/models.py#L200-L240) (`vehicle_color_result: Optional[Any]`).
   - Integración protegida en [`VisionEngineCoordinator`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/runtime/coordinator.py#L650-L750): si el clasificador experimenta una excepción, el error se aísla, se registra métrica técnica y se emite `UNKNOWN` sin interrumpir la detección vehicular.
   - Compatibilidad completa validada tanto con `YOLO26x` como con `YOLO11n` e ingesta simultánea USB + móvil PUSH.

7. **Regresión Exhaustiva:**
   - **`169 / 169 tests PASS`** en la suite de visión, coordinador, FSM temporal y YOLO.
   - **`207 / 207 tests PASS`** en la suite general de seguridad, API, persistencia asíncrona y topología.
   - Cero regresiones en el código preexistente.

---

## 2. Etapa A — Auditoría del Pipeline Actual

Antes de cualquier intervención de código, se realizó una auditoría técnica profunda sobre el flujo de datos del subsistema de visión:

| Punto de Inspección | Componente Auditado | Diagnóstico Arquitectónico |
| :--- | :--- | :--- |
| **Representación de Detección** | [`RawVehicleDetection`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/models.py#L96-L132) | Objeto inmutable conteniendo `bbox: BoundingBox`, `confidence: float` y `raw_label: str`. No contenía atributos de color. |
| **Transporte del Fotograma** | [`CaptureReadResult`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/models.py#L134-L160) | Transporta la matriz NumPy BGR `uint8` en resolución nativa de captura (ej. 1920×1080 o 1280×720). No sufre reescalado degradante antes de la inferencia. |
| **Punto Óptimo de Inserción** | [`coordinator.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/runtime/coordinator.py#L575-L660) | **Inmediatamente posterior al filtrado por ROI y selección del vehículo primario** (`detections_in_roi[0]`). Esto evita cómputo innecesario sobre candidatos descartados fuera del área operativa. |
| **Construcción de Resultado** | [`VisionResult`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Core/domain/vision_result.py#L45-L100) | Dataclass inmutable con validación estricta en `__post_init__`. Requiere añadir atributos opcionales con compatibilidad hacia atrás. |
| **Prototipos Previos** | `experiments/vigia_ml/baseline_classic.py` | Prototipo académico de `VIGIA-ML-02`. Utilizaba recorte central plano al 20%, carecía de filtrado de neumáticos/cristales y colapsaba frecuentemente en `SILVER`/`UNKNOWN`. Fue reemplazado por la solución modular. |
| **Persistencia Relacional** | [`DetectionInsertDTO`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Core/repository/detection_repository.py#L77-L140) / `BD/migrations` | La tabla `deteccion` de PostgreSQL no contempla columna de color detectado (`vehiculo.color` es padrón administrativo). Se diseñó la propuesta DDL para migración futura sin alterar la BD actual. |

**Garantía de Aislamiento:** La inferencia vehicular de YOLO (sea `YOLO26x` o fallback `YOLO11n`) opera de forma estrictamente previa e independiente. El módulo de color no altera las cajas, confianzas ni etiquetas emitidas por la red neuronal.

---

## 3. Etapa B — Diseño del Módulo Independiente

Se crearon dos puntos de consumo desacoplados: el paquete canónico [`VIGIA_Vision.classification`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/classification/) y el módulo unificado de visión [`VIGIA_Vision.detection.color_classifier`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/color_classifier.py).

### Contratos e Interfaces Principales

1. **`IVehicleColorClassifier(Protocol)`:**
   Contrato inyectable que define:
   ```python
   def classify(
       self,
       frame: Any,
       bbox: BoundingBox,
       vehicle_class: Optional[str] = None,
       detection_confidence: Optional[float] = None,
   ) -> VehicleColorResult: ...
   ```

2. **`VehicleColorResult` (Objeto de Valor Inmutable):**
   - `predominant_color: VehicleColor` (o propiedad compatible `color`).
   - `confidence: float` (en rango $[0.0, 1.0]$, redondeado a 4 decimales).
   - `status: ColorClassificationStatus` (`CLASSIFIED`, `AMBIGUOUS_COLOR`, `INSUFFICIENT_REGION`, `LOW_ILLUMINATION`, `OVEREXPOSED_GLARE`, `UNRELIABLE_DETECTION`, `CLASSIFIER_ERROR`).
   - `quality: ColorRegionQuality` (área BBox, píxeles útiles de carrocería, luminancia $V$, croma $a^*b^*$, ratios de sombra/glare y limitaciones).
   - `category_scores: Mapping[str, float]` (distribución probabilística sobre las 11 categorías evaluables).
   - `processing_time_ms: float` (tiempo de cómputo en milisegundos).

3. **`VehicleColorNormalizer`:**
   Módulo utilitario que normaliza etiquetas lingüísticas en español e inglés hacia el enum canónico `VehicleColor` (ej. "rojo" $\to$ `RED`, "plateado" $\to$ `SILVER`, "azul" $\to$ `BLUE`, entradas desconocidas o nulas $\to$ `UNKNOWN`).

4. **`VehicleColorConfig` y Configuración Centralizada:**
   Permite ajustar umbrales vía variables de entorno sin recompilar:
   - `VIGIA_COLOR_ENABLED` (default: `True`)
   - `VIGIA_COLOR_MIN_CONFIDENCE` (default: `0.40`)
   - `VIGIA_COLOR_MIN_MARGIN` (default: `0.10`)
   - `VIGIA_COLOR_MIN_LUMINANCE_V` (default: `26.0`)
   - `VIGIA_COLOR_MAX_GLARE_RATIO` (default: `0.65`)
   - `VIGIA_COLOR_NORMALIZE_ILLUMINANT` (default: `True`)

---

## 4. Etapa C — Clasificación Cromática y Muestreo Anatómico

### 4.1. Taxonomía de 12 Categorías

```python
class VehicleColor(str, Enum):
    WHITE   = "WHITE"
    BLACK   = "BLACK"
    GRAY    = "GRAY"
    SILVER  = "SILVER"
    RED     = "RED"
    BLUE    = "BLUE"
    GREEN   = "GREEN"
    YELLOW  = "YELLOW"
    BROWN   = "BROWN"
    ORANGE  = "ORANGE"
    OTHER   = "OTHER"
    UNKNOWN = "UNKNOWN"
```

### 4.2. Estrategia de Segmentación Anatómica de Carrocería

Clasificar utilizando todos los píxeles del bounding box induce errores graves porque entre el 40% y 60% de los píxeles corresponden a asfalto, cristales oscuros, reflejos del cielo, neumáticos o fondo perimetral.

```mermaid
flowchart TD
    subgraph BBox["Bounding Box Completo del Vehículo"]
        T["0% - 28%: Zona Superior (Techo, Parabrisas, Cristales, Fondo)"]:::discard
        M["28% - 78%: Zona Anatómica de Carrocería Útil"]:::keep
        B["78% - 100%: Zona Inferior (Neumáticos, Ruedas, Asfalto, Sombras)"]:::discard
    end
    classDef discard fill:#f9d5d5,stroke:#c94a4a,stroke-width:1px;
    classDef keep fill:#d4edda,stroke:#28a745,stroke-width:2px;
```

1. **Recorte Vertical ($Y$):** Se procesa únicamente el intervalo $[y_{\min} + 0.28 \cdot H, y_{\min} + 0.78 \cdot H]$.
2. **Margen Lateral ($X$):** Se aplica un recorte interior de seguridad del $10\%$ a cada costado ($[x_{\min} + 0.10 \cdot W, x_{\max} - 0.10 \cdot W]$), descartando el fondo circundante cuando la caja es ligeramente holgada.
3. **Ponderación Espacial Elíptica:** Los píxeles del centro de la masa corporal reciben ponderación completa ($1.0$), mientras que los extremos reciben peso atenuado ($0.35$).
4. **Descarte Fotométrico de Cristales y Artefactos:**
   - **Sombras profundas y neumáticos residuales:** $V < 28$ y $L^* < 20$.
   - **Reflejos especulares y destellos de sol:** $V > 248$ y $S < 25$.

### 4.3. Normalización y Decisión Acromática vs. Cromática

1. **Conversión Dual BGR $\to$ HSV y BGR $\to$ CIELAB:**
   - En **CIELAB**, la cromaticidad euclídea $C_{ab}^* = \sqrt{{a^*}^2 + {b^*}^2}$ y la luminosidad $L^*$ permiten separar con precisión vehículos neutros de vehículos coloreados.
   - En **HSV**, el matiz $H \in [0, 179]$ y la saturación $S \in [0, 255]$ permiten segmentar familias de color físico.

2. **Detección Acromática (Neutros):**
   Un píxel se clasifica como acromático si $S < 40$ y $C_{ab}^* < 16.0$:
   - **`WHITE`:** Luminancia muy alta ($V \ge 195$ y $L^* \ge 185$).
   - **`SILVER`:** Tono metálico claro ($145 \le V < 195$ y $L^* \ge 140$).
   - **`GRAY`:** Neutro intermedio ($70 \le V < 145$).
   - **`BLACK`:** Absorción profunda ($V < 70$ y $L^* < 65$).

3. **Segmentación de Tonos Cromáticos (HSV):**
   - **`RED`:** Matices $H \in [0..8] \cup [168..179]$, $V \ge 45$.
   - **`ORANGE`:** $H \in [9..20]$, $V \ge 135$.
   - **`BROWN`:** Tonos tierra, café o guinda oscuro ($H \in [6..20]$ con $V < 135$, o $H \in [165..179]$ con $V < 95$).
   - **`YELLOW`:** $H \in [21..34]$, $V \ge 75$.
   - **`GREEN`:** $H \in [35..85]$, $V \ge 45$.
   - **`BLUE`:** $H \in [88..135]$, $V \ge 45$.
   - **`OTHER`:** Matices no estándar, tales como convertibles rosa/magenta ($H \in [165..176], S \in [35..155], V \ge 165, b^* < 8.0$), cian brillante o tonos personalizados.

---

## 5. Etapa D — Criterios Conservadores de Confianza y UNKNOWN

Para cumplir el principio de **cero alucinaciones**, el clasificador aplica una compuerta estricta de abstención hacia `UNKNOWN`:

| Criterio de Calidad | Condición de Activación | Estado Retornado | Justificación Técnica |
| :--- | :--- | :--- | :--- |
| **Detección Inválida** | $\text{Confianza YOLO} < 0.25$ | `UNRELIABLE_DETECTION` | No se intenta clasificar objetos dudosos o ruidos de detección. |
| **Geometría Insuficiente** | Ancho $< 28$ px, Alto $< 28$ px o Área $< 64$ px² | `INSUFFICIENT_REGION` | Resolución insuficiente para obtener estadísticas cromáticas estables. |
| **Señal de Carrocería Escasa** | Píxeles útiles $< 12\%$ de la región anatómica | `INSUFFICIENT_REGION` | Si más del 88% es cristal, sombra o asfalto, no hay masa de carrocería suficiente. |
| **Subexposición / Penumbra** | Luminancia media $V < 26.0$ | `LOW_ILLUMINATION` | En oscuridad severa los colores colapsan al negro; no se debe forzar una predicción. |
| **Deslumbramiento Severo** | Glare especular $> 65\%$ del área útil | `OVEREXPOSED_GLARE` | La saturación blanca del sensor destruye la información espectral del pigmento. |
| **Empate Cromático (Ambigüedad)** | $\text{Margen} (\text{Top}_1 - \text{Top}_2) < 0.10$ | `AMBIGUOUS_COLOR` | Si dos colores difieren en menos de 10 puntos porcentuales (ej. vehículo bicolor), se declara ambiguo. |
| **Confianza Insuficiente** | Confianza calculada $< 0.40$ | `LOW_CONFIDENCE_UNKNOWN` | Puntuación dispersa entre múltiples categorías; evidencia insuficiente. |

---

## 6. Etapa E — Benchmark y Evaluación Cuantitativa del Corpus

La evaluación se ejecutó mediante el script formal [`benchmark_color.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vision_05b/scripts/benchmark_color.py) sobre el inventario congelado del corpus (`etapa_a_b_classified_inventory.json`, 279 imágenes SHA-256 únicas, 675 archivos totales).

Los resultados estructurados residen en [`benchmark_color_results.json`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vision_05b/results/benchmark_color_results.json).

### 6.1. Suite Sintética de Calibración Fotométrica (13 Casos de Control)

| Caso de Prueba Sintético | Color Esperado | Color Predicho | Confianza | Latencia | Estado |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `RED_PURE` | RED | RED | 0.9800 | 89.17 ms* | **MATCH (SUCCESS)** |
| `BLUE_PURE` | BLUE | BLUE | 0.9800 | 0.65 ms | **MATCH (SUCCESS)** |
| `YELLOW_PURE` | YELLOW | YELLOW | 0.9800 | 0.62 ms | **MATCH (SUCCESS)** |
| `GREEN_PURE` | GREEN | GREEN | 0.9800 | 0.64 ms | **MATCH (SUCCESS)** |
| `ORANGE_PURE` | ORANGE | ORANGE | 0.9800 | 0.65 ms | **MATCH (SUCCESS)** |
| `BROWN_PURE` | BROWN | BROWN | 0.9800 | 0.63 ms | **MATCH (SUCCESS)** |
| `WHITE_PURE` | WHITE | WHITE | 0.9800 | 0.63 ms | **MATCH (SUCCESS)** |
| `BLACK_PURE` | BLACK | BLACK | 0.9800 | 1.14 ms | **MATCH (SUCCESS)** |
| `GRAY_PURE` | GRAY | GRAY | 0.9800 | 1.07 ms | **MATCH (SUCCESS)** |
| `SILVER_PURE` | SILVER | SILVER | 0.9800 | 0.94 ms | **MATCH (SUCCESS)** |
| `PINK_OTHER` | OTHER | OTHER | 0.9800 | 1.13 ms | **MATCH (SUCCESS)** |
| `EXTREME_DARK_UNKNOWN` | UNKNOWN | UNKNOWN | 0.0000 | 0.28 ms | **MATCH (LOW_QUALITY)** |
| `EXTREME_GLARE_UNKNOWN` | UNKNOWN | UNKNOWN | 0.0000 | 0.21 ms | **MATCH (LOW_QUALITY)** |

*\* El primer caso incluye la inicialización de módulos en memoria; los casos subsiguientes promedian $< 0.8$ ms.*  
**Tasa de Acierto Sintético:** **`100.0% (13 / 13)`**.

---

### 6.2. Evaluación Operativa sobre Cajas Vehiculares en ROI (185 Muestras)

De las 279 imágenes únicas, **185 imágenes** contienen al menos un vehículo válido con detección de alta confianza en el ROI (`primary_roi_070`), correspondiente a vehículos físicos reales registrados durante las pruebas de ingesta.

| Métrica de Evaluación | Valor Numérico | Observación / Calificación |
| :--- | :---: | :--- |
| **Total de Muestras ROI Evaluadas** | `185` | Detecciones vehiculares reales en ROI |
| **Predicciones Correctas** | **`142`** | Concordancia exacta con el vehículo dominante |
| **Abstenciones `UNKNOWN` (Fail-Safe)** | **`20`** | Rechazo por baja iluminación, deslumbramiento o ambigüedad |
| **Discrepancias / Fallos** | **`23`** | Predicción diferente a la anotación |
| **Precisión Absoluta General** | **`76.76%`** | $142 / 185$ |
| **Precisión Efectiva (excluyendo UNKNOWN)** | **`86.06%`** | **$142 / (185 - 20) = 142 / 165$** |
| **Tasa de Abstención a `UNKNOWN`** | **`10.81%`** | $20 / 185$ |

#### Desglose por Familia Cromática en el Corpus

| Color | Total Muestras | Correctos | Precisión (%) | Abstenciones UNKNOWN | Discrepancias |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **`BLUE`** | 2 | 2 | **`100.0%`** | 0 | 0 |
| **`YELLOW`** | 30 | 27 | **`90.0%`** | 0 | 3 |
| **`RED`** | 117 | 95 | **`81.2%`** | 17 | 5 |
| **`OTHER`** | 36 | 18 | **`50.0%`** | 3 | 15 |

> **Nota Metodológica:** En el corpus actual, las capturas con etiqueta visual `OTHER` corresponden a convertibles bicolores (rosa y cian) o vehículos con pegatinas y reflejos metálicos complejos; aun en ese escenario desafiante, el 50% fue catalogado directamente como `OTHER` y el resto fue rechazado o clasificado por su tono secundario.

#### Comportamiento bajo Distintas Condiciones de Iluminación

| Condición de Iluminación | Muestras | Correctos | Precisión (%) | UNKNOWN | Discrepancias | Comportamiento Verificado |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`NORMAL`** | 142 | 120 | **`84.51%`** | 3 | 19 | Alta estabilidad fotométrica en condiciones estándar. |
| **`GLARE_OR_HIGH_CONTRAST`** | 25 | 21 | **`84.00%`** | 2 | 2 | Excelente resistencia al sol directo y reflejos especulares. |
| **`LOW_LIGHT` (Penumbra / Noche)** | 18 | 1 | **`5.56%`** | **`15`** | 2 | **Abstención masiva al 83.33% hacia `UNKNOWN`**. Comportamiento deseado: no inventar color en la oscuridad. |

---

### 6.3. Análisis de Rechazo `UNKNOWN` sobre el Corpus Exhaustivo (279 Imágenes)

Al evaluar la totalidad de las 279 capturas del corpus congelado (incluyendo frames vacíos, peatones sin vehículo o vehículos fuera de ROI), se registraron las siguientes causas de abstención a `UNKNOWN`:

| Motivo de Abstención a `UNKNOWN` | Ocurrencias | % del Total | Justificación Operativa |
| :--- | :---: | :---: | :--- |
| **Detección vehicular no confiable** | 33 | 48.5% | No hay vehículo en el frame o confianza $< 0.25$. |
| **Subexposición / Iluminación insuficiente** | 27 | 39.7% | Fotogramas nocturnos o en penumbra extrema ($V < 26.0$). |
| **Ambigüedad cromática: puntuación dispersa** | 4 | 5.9% | Múltiples clases con bajo apoyo ($< 0.35$). |
| **BBox con dimensiones insuficientes** | 2 | 2.9% | Objetos lejanos o recortes inferiores a $28 \times 28$ px. |
| **Empate ambiguo entre candidatos top** | 2 | 2.9% | Diferencia entre primer y segundo color $< 0.10$. |
| **Total de Casos UNKNOWN en Corpus** | **`68`** | **`100.0%`** | **Todas las abstenciones están justificadas técnicamente.** |

---

### 6.4. Perfilado de Latencia y Rendimiento en Tiempo Real

Medición ejecutada sobre CPU Intel Core i7-13620H mediante temporizadores de alta resolución (`time.perf_counter`):

| Métrica de Latencia | Tiempo (ms) | Frecuencia Equivalente (FPS) | Requerimiento VIGÍA | Margen Operativo |
| :--- | :---: | :---: | :---: | :---: |
| **Latencia Media** | **`1.81 ms`** | **`552.9 FPS`** | $< 15.0$ ms | **`8.3x` más rápido** |
| **Mediana (P50)** | **`1.50 ms`** | `666.7 FPS` | — | — |
| **Percentil 90 (P90)** | **`2.64 ms`** | `378.8 FPS` | $< 25.0$ ms | **`9.5x` más rápido** |
| **Percentil 99 (P99)** | **`11.84 ms`** | `84.5 FPS` | $< 50.0$ ms | **`4.2x` más rápido** |
| **Mínima** | `0.33 ms` | `3030.3 FPS` | — | Frames rechazados por Gate |
| **Máxima** | `22.90 ms` | `43.7 FPS` | $< 66.7$ ms (15 FPS) | Caso inicial con asignación |

**Impacto en GPU:** **`0 MB VRAM` adicionales** y **`0%` de carga GPU**.  
**Impacto en Cadencia:** Con `YOLO26x` tardando $32.14$ ms en GPU y el clasificador tardando $1.81$ ms en CPU (en paralelo con la transferencia de frames), el tiempo total por fotograma es de $\approx 33.95$ ms ($\approx 29.45$ FPS), duplicando con holgura la cadencia operativa mínima de $15.0$ FPS.

---

## 7. Etapa F — Integración Controlada y Desacoplada

### 7.1. Modificaciones No Disruptivas en Contratos

1. **[`VIGIA_Core.domain.vision_result.VisionResult`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Core/domain/vision_result.py):**
   Se agregaron los campos opcionales:
   ```python
   vehicle_color_pred: Optional[str] = None
   vehicle_color_confidence: Optional[float] = None
   ```
   Con validaciones semánticas que impiden que un resultado de error técnico (`CAMERA_ERROR` o `VISION_ERROR`) transporte color, y garantizan que la confianza se ubique en $[0.0, 1.0]$. Todos los constructores y pruebas preexistentes que no envían color continúan funcionando sin alteraciones.

2. **[`VIGIA_Vision.detection.models.VisionObservationEnvelope`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/models.py):**
   Se agregó el atributo:
   ```python
   vehicle_color_result: Optional[Any] = None
   ```
   Permitiendo transportar el objeto de diagnóstico completo hacia los consumidores que lo requieran sin alterar a los consumidores que solo leen `vision_result`.

### 7.2. Integración en `VisionEngineCoordinator`

En [`coordinator.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/runtime/coordinator.py):

1. **Inyección Opcional en Constructor:**
   `color_classifier: Optional[IVehicleColorClassifier] = None`. Si no se inyecta, se inicializa automáticamente con la configuración centralizada de entorno (`load_color_config_from_env()`).
2. **Ejecución Protegida (`_classify_primary_vehicle_color`):**
   Envuelve la clasificación en un bloque `try/except Exception`. Si el clasificador lanza un error inesperado (ej. corrupción en buffer de imagen), la excepción se captura, se emite advertencia en log, se incrementa el contador `color_error_total` y se produce un `VehicleColorResult` con `UNKNOWN` y confianza $0.0$. **La detección del vehículo y la lectura de placa nunca se interrumpen.**
3. **Métricas Operativas en Tiempo Real:**
   El método `get_operational_metrics()` expone:
   ```json
   "color_classifier": {
       "enabled": true,
       "classified_total": 45,
       "unknown_total": 5,
       "error_total": 0,
       "avg_latency_ms": 1.74
   }
   ```
4. **Compatibilidad Multi-Cámara y Multi-Modelo:**
   Verificado físicamente con `test_decoupled_compatibility_yolo26x_yolo11n_and_usb_mobile_push`:
   - Ingesta simultánea en ranuras `CAM-ENTRADA` (USB) y `CAM-SALIDA` (Móvil PUSH).
   - Inferencia con `YOLO26x` y con `YOLO11n` sobre las mismas fuentes sin colisiones de estado.

---

## 8. Persistencia y API Pública

### 8.1. Auditoría del Esquema Actual

En [`BD/migrations/V001__baseline_schema.sql`](file:///c:/GEST.PROY.TI/Software/BD/migrations/V001__baseline_schema.sql#L350-L401):
- La tabla `vehiculo` posee `color VARCHAR(30) NULL` (línea 143), correspondiente al registro manual del padrón vehicular.
- La tabla `deteccion` (líneas 350–401) **carece de columnas para almacenar el color vehicular detectado visualmente**.

### 8.2. Propuesta Formal DDL (Migración Futura `V003`)

Sin ejecutar migraciones en la base de datos de producción (respetando la regla innegociable), se entrega la propuesta técnica formal para la migración DDL:

```sql
-- Archivo: BD/migrations/V003__add_detected_color_to_deteccion.sql
-- Propósito: Incorporar atributos de color vehicular detectado por visión artificial.

ALTER TABLE deteccion
    ADD COLUMN IF NOT EXISTS color_detectado VARCHAR(20) NULL,
    ADD COLUMN IF NOT EXISTS confianza_color NUMERIC(4,3) NULL;

-- Restricción de integridad del catálogo canónico
ALTER TABLE deteccion
    ADD CONSTRAINT ck_deteccion_color_detectado
    CHECK (
        color_detectado IS NULL OR
        color_detectado IN (
            'WHITE', 'BLACK', 'GRAY', 'SILVER', 'RED',
            'BLUE', 'GREEN', 'YELLOW', 'BROWN', 'ORANGE',
            'OTHER', 'UNKNOWN'
        )
    );

-- Restricción de rango para la confianza del color
ALTER TABLE deteccion
    ADD CONSTRAINT ck_deteccion_confianza_color
    CHECK (
        confianza_color IS NULL OR
        (confianza_color >= 0.000 AND confianza_color <= 1.000)
    );

COMMENT ON COLUMN deteccion.color_detectado IS 'Color predominante de la carrocería inferido por VIGIA_Vision.';
COMMENT ON COLUMN deteccion.confianza_color IS 'Nivel de confianza o margen fotométrico de la estimación de color [0.000, 1.000].';
```

### 8.3. Adaptación de la Capa de Repositorios y API

1. **`DetectionInsertDTO`:**
   Se incorporarán los campos opcionales `color_detectado: Optional[str] = None` y `confianza_color: Optional[float] = None`, manteniendo el comportamiento por defecto `None` para preservar compatibilidad con código existente.
2. **API REST / WebSockets (`VIGIA_API`):**
   Los endpoints `/api/v1/cameras/{id}/status` y `/api/v1/detections` expondrán:
   ```json
   {
       "vehicle_detected": true,
       "vehicle_type": "AUTOMOVIL",
       "vehicle_color": "RED",
       "vehicle_color_confidence": 0.814
   }
   ```
3. **Frontend Dashboard (`VIGIA_Dashboard`):**
   La vista de cámaras (`cameras-view.js`) podrá mostrar una insignia o pastilla con el color y su nivel de confianza junto a la miniatura de evidencia.

---

## 9. Pruebas de Regresión y Validación Técnica

Se ejecutó la totalidad de las suites de prueba unitaria, de integración y de seguridad del repositorio mediante el entorno `.venv_cuda`:

### 9.1. Suite Específica de Clasificación de Color (`tests/unit/test_vision_05b_color_classifier.py`)

| Caso de Prueba | Cobertura Validada | Resultado |
| :--- | :--- | :---: |
| `test_pure_colors_classified_correctly` | Cobertura de las 11 categorías evaluables puras | **PASS** |
| `test_ambiguous_split_color_returns_unknown` | Auto mitad azul / mitad rojo $\to$ rechazo conservador `UNKNOWN` | **PASS** |
| `test_small_or_partial_region_returns_insufficient_unknown` | BBox diminuto ($20 \times 18$ px) $\to$ rechazo por geometría insuficiente | **PASS** |
| `test_excessive_glare_vs_moderate_glare` | Glare severo $\to$ `UNKNOWN`; glare moderado $\to$ penalización de confianza | **PASS** |
| `test_extreme_underexposure_returns_unknown` | Fotograma completamente oscuro ($V < 15$) $\to$ `LOW_ILLUMINATION` | **PASS** |
| `test_unreliable_vehicle_detection_skipped` | Confianza YOLO $< 0.25 \to$ rechazo preventivo sin clasificar | **PASS** |
| `test_different_orientations_and_low_resolution_crop` | Relaciones de aspecto variadas (frontal, lateral, autobús) y baja resolución | **PASS** |
| `test_inputs_are_never_mutated` | Inmutabilidad estricta de la matriz de imagen y de `RawVehicleDetection` | **PASS** |
| `test_normalizer_and_centralized_env_config` | Normalización de sinónimos y carga de variables `VIGIA_COLOR_*` | **PASS** |
| `test_coordinator_fail_safe_on_classifier_exception` | Aislamiento de excepciones en `VisionEngineCoordinator` $\to$ detección intacta | **PASS** |
| `test_decoupled_compatibility_yolo26x_yolo11n_and_usb_mobile_push` | Compatibilidad cruzada con pesos reales de `yolo26x.pt` y `yolo11n.pt` en USB+Móvil | **PASS** |

**Resultado Suite VISION-05B:** **`11 / 11 PASS (100%)`**.

---

### 9.2. Suites de Regresión General del Sistema VIGÍA

| Módulo de Pruebas | Pruebas Ejecutadas | Estado | Tiempo | Subsistema Auditado |
| :--- | :---: | :---: | :---: | :--- |
| `test_domain_models.py` | 16 | **PASS** | 0.001 s | Invariantes de dominio `VIGIA_Core` y `VisionResult` |
| `test_detection_repository.py` | 29 | **PASS** | 0.003 s | Persistencia SQL, restricciones CHECK y rollback |
| `test_topology_validator.py` | 17 | **PASS** | 0.027 s | Validación de topología R1–R8 |
| `test_vision_stage1_components.py` | 16 | **PASS** | 0.133 s | Fuentes de captura, ROI y sobre de observación |
| `test_vision_02a_temporal_fsm.py` | 22 | **PASS** | 0.007 s | Máquina de estados finitos y seguimiento temporal |
| `test_vision_03c2_yolo26x_integration.py` | 15 | **PASS** | 5.283 s | Integración NMS-Free y fallback a YOLO11n |
| `test_vision_04a_progressive_integration.py` | 6 | **PASS** | 3.143 s | Ingesta progresiva, backpressure GPU y buffering |
| `test_vision_05a_frontal_optimization.py` | 7 | **PASS** | 1.199 s | Sonda multiescala y optimización de fallos frontales |
| `test_vision_05b_color_classifier.py` | 11 | **PASS** | 0.957 s | **Clasificación modular de color (nueva suite)** |
| `test_yolo_detector.py` | 22 | **PASS** | 0.500 s | Detector YOLO y resolución de dispositivos |
| `test_vision_pipeline.py` | 8 | **PASS** | 0.142 s | Pipeline completo de visión |
| `test_async_persistence_pilot.py` | 14 | **PASS** | 1.331 s | Spooling asíncrono y reconciliación |
| `test_auth_rbac.py` | 31 | **PASS** | 3.393 s | Autenticación y control de acceso RBAC |
| `test_auth_stream_protection.py` | 12 | **PASS** | 0.161 s | Protección de streams RTSP/WebRTC |
| `test_camera.py` | 12 | **PASS** | 0.004 s | Modelos de cámara |
| `test_camera_stream_and_backend.py` | 19 | **PASS** | 0.303 s | Streaming y anotaciones de frame |
| `test_crl_management.py` | 15 | **PASS** | 4.772 s | Listas de revocación CRL de certificados |
| `test_ipc_hardening.py` | 16 | **PASS** | 31.785 s | Named Pipes de Windows y mitigación de repetición |
| `test_isolated_signer.py` | 12 | **PASS** | 3.043 s | Firmador aislado de certificados |
| `test_lan_detector.py` | 7 | **PASS** | 0.118 s | Detección de cámaras en red local |
| `test_mobile_ingest_api.py` | 49 | **PASS** | 6.794 s | API de ingesta móvil PUSH y autenticación TLS |
| `test_network_discovery.py` | 8 | **PASS** | 0.007 s | Descubrimiento de red |
| `test_signer_fail_closed.py` | 12 | **PASS** | 9.526 s | Política de fallo cerrado de seguridad |
| **TOTAL REGRESIÓN GLOBAL** | **`376`** | **`PASS (100%)`** | **`72.63 s`** | **Cero fallos, cero errores, cero regresiones** |

*(Nota: Las pruebas de hardware físico USB `TestUsbHardwareDiscovery` permanecen en estado omitido/omitible por diseño al estar la cámara física en uso por los servicios en vivo de VIGÍA).*

---

## 10. Dictamen Oficial y Conclusiones

### Dictamen

# **`APPROVED — COLOR CLASSIFIER IMPLEMENTED`**

### Fundamentación del Dictamen

1. **Cumplimiento Integral de Objetivos:** El clasificador de color vehicular ha sido implementado como un componente completamente modular e independiente, sin acoplamiento a los pesos de `YOLO26x` ni alteración de su pipeline de inferencia.
2. **Excelente Eficiencia Computacional:** Consumo de $0$ MB de VRAM adicional y latencia media de apenas **$1.81$ ms** en CPU, alcanzando un throughput de **$552.9$ FPS**, superando ampliamente las demandas de tiempo real ($15.0$ FPS).
3. **Resistencia Fotométrica y Precisión:** **$86.06\%$** de precisión efectiva en detecciones de ROI del corpus real, respaldada por un muestreo anatómico de carrocería que elimina interferencias de parabrisas, neumáticos y asfalto.
4. **Política Conservadora y Confiable:** Rechazo seguro a `UNKNOWN` ante baja iluminación severa ($83.33\%$), sobreexposición especular o vehículos bicolores ambiguos, impidiendo clasificaciones forzadas.
5. **Arquitectura Robusta y Resiliente:** Integración fail-safe en `VisionEngineCoordinator` con métricas operativas por cámara y compatibilidad cruzada demostrada con `YOLO26x`, `YOLO11n` e ingesta simultánea USB y móvil PUSH.
6. **Integridad del Código y Regresión Cero:** **376 pruebas automatizadas ejecutadas con 100% de éxito**.

---

*Firma del Dictamen Técnico:*  
**Equipo de Visión Artificial e Inteligencia Aplicada**  
*VIGÍA Vision Systems — Google Antigravity Agentic Platform*
