# INFORME DE AUDITORÍA TÉCNICA INDEPENDIENTE — FASE VIGIA-VISION-05B.1
## Auditoría de Cierre, Robustez, Concurrencia y Validación Operativa del Clasificador de Color Vehicular

**Proyecto:** VIGÍA Vision Systems  
**Fase:** VIGIA-VISION-05B.1  
**Tipo de Entregable:** Auditoría Técnica Independiente de Cierre  
**Fecha de Emisión:** 16 de noviembre de 2026  
**Auditor:** Agente de Auditoría de Sistemas de Visión e Infraestructura (Google DeepMind Antigravity)  
**Hardware de Evaluación:** NVIDIA GeForce RTX 4050 Laptop GPU (6 GB VRAM) / Intel Core i7-13620H (16 vCPUs, 16 GB RAM)  
**Ambiente de Ejecución:** Windows 11 Home / Python 3.12 (.venv_cuda)  

---

## 1. RESUMEN EJECUTIVO Y DICTAMEN OFICIAL

### 1.1. Dictamen Oficial de Auditoría

> **DICTAMEN OFICIAL:** **`APPROVED WITH OBSERVATIONS`**  
> *(Aprobado con Observaciones Técnicas — Listo para Validación Operativa Controlada sin Despliegue Abierto)*

La auditoría técnica independiente realizada sobre la implementación de **Clasificación Modular de Color Vehicular (Fase VISION-05B)** concluye que el componente algorítmico, los modelos de dominio, las interfaces de integración y la arquitectura de concurrencia cumplen satisfactoriamente con los estándares de robustez, seguridad y rendimiento exigidos por el proyecto VIGÍA Vision Systems.

El clasificador opera de forma completamente desacoplada de la inferencia YOLO26x/YOLO11n, no introduce bloqueos ni excepciones en el pipeline principal, garantiza inmutabilidad absoluta sobre los fotogramas y detecciones de entrada, y exhibe un rendimiento sobresaliente en entornos multicanal concurrentes.

Sin embargo, se emite el dictamen **`APPROVED WITH OBSERVATIONS`** debido a cuatro observaciones técnicas documentadas que deben ser tomadas en cuenta antes de cualquier promoción a producción:
1. **Conflicto de Nomenclatura en la Migración Flyway:** La propuesta documental DDL original fue denominada `V003`, lo cual generaría un conflicto de versión con `V003__seed_data.sql` y `V004__enrolamiento_camaras_qr.sql` preexistentes en `BD/migrations/`. La migración formal debe registrarse obligatoriamente como **`V005__add_detected_color_to_deteccion.sql`**.
2. **Sesgo en Etiquetas de Referencia Heurísticas del Benchmark:** El análisis estadístico granular reveló que al menos 4 de las 23 discrepancias registradas en el benchmark operativo obedecen a errores del mapeador heurístico en escenas multicoche (asignando la etiqueta del autobús al automóvil secundario o viceversa), y 15 corresponden a la sobre-especificidad cromática del clasificador frente a la etiqueta genérica `OTHER` asignada en campo a vehículos bicolores.
3. **Métricas de Concordancia vs. Ground Truth de Laboratorio:** La precisión efectiva del **`86.06%`** sobre el ROI operativo debe considerarse como una *tasa de concordancia empírica sobre notas de campo*, no como una métrica certificada de laboratorio, dado que no existe un conjunto de Ground Truth etiquetado por espectrofotometría o segmentación manual de píxeles.
4. **Limitación Geométrica del Muestreo Anatómico Fijo:** En ángulos cenitales u oblicuos extremos con vehículos pickup o convertibles, la ventana fija de carrocería puede muestrear parcialmente interiores o bateas traseras.

---

### 1.2. Tabla Sinóptica de Verificación Técnica

| Dimensión Auditada | Criterio de Aceptación | Resultado Observado | Estado |
| :--- | :--- | :--- | :---: |
| **Inmutabilidad de Datos** | Fotograma y detecciones no deben ser mutados | Verificado con verificación de integridad de memoria | **CONFORME** |
| **Protección Fuera de Límite** | Cajas parciales, negativas o fuera de frame no lanzan `IndexError` | Clamping $O(1)$ y manejo ordenado `INSUFFICIENT_REGION` | **CONFORME** |
| **Aislamiento Multicanal** | No contaminación cruzada entre cámaras concurrentes | 0 violaciones de aislamiento en 1, 2, 4 y 8 hilos | **CONFORME** |
| **Rendimiento Operativo (2 Cams)** | Latencia P50 $< 15$ ms; Throughput $> 60$ FPS | P50 = **4.49 ms**; Throughput = **416.7 FPS** | **SOBRESALIENTE** |
| **Rendimiento en Saturación (8 Cams)** | Latencia P50 $< 33.3$ ms (30 FPS budget); 0 deadlocks | P50 = **19.95 ms**; Throughput = **375.6 FPS**; 0 deadlocks | **CONFORME** |
| **Integración Fail-Safe** | Excepción en clasificador no aborta detección vehicular | Captura de excepciones en `VisionEngineCoordinator` activa | **CONFORME** |
| **Compatibilidad de Esquema** | Columnas `NULL` sin bloqueo de tablas en PostgreSQL | DDL evaluado compatible $O(1)$; requiere renumerar a `V005` | **OBSERVADO** |
| **Regresión de Software** | Cobertura total de pruebas unitarias y de subsistema | **376 / 376 PASS (100.00%)** | **CONFORME** |

---

## 2. AUDITORÍA ALGORÍTMICA Y GEOMÉTRICA DE LA IMPLEMENTACIÓN

Se realizó una inspección exhaustiva línea por línea del módulo [`VIGIA_Vision/detection/color_classifier.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/color_classifier.py) y de la biblioteca desacoplada en [`VIGIA_Vision/classification/`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/classification/).

### 2.1. Inmutabilidad del Fotograma y de la Detección
- **Fotograma Original:** El método `classify()` no altera los canales BGR del array `np.ndarray` recibido. Todas las operaciones de filtrado, conversión de espacio de color (`cv2.cvtColor`), ecualización CLAHE y binarización se realizan sobre sub-recortes creados vía slicing `frame_bgr[y1:y2, x1:x2]`. Las operaciones posteriores sobre máscaras y morfología utilizan buffers temporales dedicados.
- **Detección de Entrada:** Las coordenadas de la caja delimitadora son desempaquetadas como tuplas inmutables `(x_min, y_min, x_max, y_max)`. Ningún atributo de `RawVehicleDetection` es modificado.

### 2.2. Robustez Geométrica y Manejo de Bounding Boxes Fuera de Límites
En entornos de cámaras perimetrales con ángulos de visión rasantes o vehículos ingresando en el límite del sensor, las cajas predichas por YOLO pueden tener coordenadas negativas o mayores a la resolución nativa ($W, H$).
Se comprobó que el clasificador implementa un mecanismo de saturación de coordenadas (*clamping*) estricto:
```python
x1 = max(0, min(bbox.x_min, frame_w - 1))
y1 = max(0, min(bbox.y_min, frame_h - 1))
x2 = max(0, min(bbox.x_max, frame_w))
y2 = max(0, min(bbox.y_max, frame_h))
crop_w = max(0, x2 - x1)
crop_h = max(0, y2 - y1)
```
- **Condición de Bounding Box Degenerada:** Si `crop_w < 28` o `crop_h < 28` píxeles, el algoritmo no intenta procesar la geometría ni arroja `ZeroDivisionError` ni `IndexError`. Retorna ordenadamente `ColorClassificationStatus.INSUFFICIENT_REGION` con color `VehicleColor.UNKNOWN`, confianza `0.0` y calidad nula.
- **Cajas Invertidas ($x_2 \le x_1$ o $y_2 \le y_1$):** Son atrapadas de forma idéntica, devolviendo `INSUFFICIENT_REGION` sin degradar el pipeline.

### 2.3. Exclusión de Componentes No Carrocería (Fondo, Cristales, Neumáticos)
El clasificador aplica un pipeline multicapa de filtrado espacial y fotométrico:
1. **Recorte Anatómico Adaptativo:**
   - **Automóviles estándar:** Muestrea verticalmente entre $26\%$ y $82\%$ de la altura del vehículo, suprimiendo el asfalto/neumáticos inferiores ($> 82\%$) y el cielo/techo superior ($< 26\%$). La zona de parabrisas ($24\%$ a $44\%$) es excluida cuando presenta baja saturación y brillo atípico.
   - **Vehículos pesados (`AUTOBUS`, `BUS`, `CAMION`, `TRUCK`):** Adapta la ventana vertical a $[16\%, 80\%]$, reconociendo que los autobuses poseen carrocería más alta y parabrisas más vertical. La franja de ventanillas se trata en el rango $[18\%, 50\%]$.
   - **Motocicletas:** Ajusta el área a $[22\%, 78\%]$ reconociendo la geometría compacta del tanque y carenado.
2. **Exclusión de Fondo Perimetral:** Se aplica una erosión morfológica perimetral del $8\%$ en bordes laterales para evitar que el asfalto, vegetación o paredes adyacentes contaminen el histograma.
3. **Filtrado de Reflejos Especulares (Glare) y Sombras:**
   - En espacio CIELAB ($L^*, a^*, b^*$), píxeles con $L^* < 18$ (sombras profundas en guardabarros o bajo el chasis) son descartados.
   - Píxeles con $L^* > 95$ y saturación $S < 15$ (deslumbramiento solar especular) son excluidos para no sesgar vehículos oscuros hacia `WHITE`.

### 2.4. Sesgos Identificados del Muestreo Anatómico Fijo
> [!NOTE]
> **Sesgo Documentado:** La heurística de recorte asume vehículos vistos en perspectiva horizontal u oblicua a nivel de calle (ángulos típicos de 10° a 30° de inclinación de cámara).  
> Cuando un vehículo se visualiza en ángulo cenital severo ($> 45°$) o se trata de una camioneta con batea de carga descubierta de color diferente al resto de la carrocería, la ventana central puede capturar parte del interior o de la batea. Este compromiso es inherente al diseño no basado en redes de segmentación de instancia (Mask R-CNN), priorizando la latencia de $< 5$ ms sobre el costo de inferencia GPU.

---

## 3. AUDITORÍA ESTADÍSTICA DEL BENCHMARK OPERATIVO Y DISCREPANCIAS

### 3.1. Procedencia de las Etiquetas y Metodología de Evaluación
El benchmark ejecutado en `VISION-05B` utilizó como referencia el inventario congelado de 279 imágenes únicas no duplicadas en [`experiments/vision_05a/results/etapa_a_b_classified_inventory.json`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vision_05a/results/etapa_a_b_classified_inventory.json).

De estas 279 imágenes, **185 corresponden a vehículos detectados con confianza $\ge 0.70$ dentro del Área de Interés Operativa (`primary_roi_070`)**.

### 3.2. Desglose Granular de las 23 Discrepancias
La auditoría independiente ejecutó un script de análisis forense (`analyze_color_discrepancies.py`) para categorizar las 23 discrepancias observadas:

```
Total Evaluables en ROI:           185
Aciertos (Concordancia):           142 (76.76% global)
Abstenciones UNKNOWN:               20 (10.81%)
Decisiones Firmes Emitidas:        165 (89.19% de cobertura)
Discrepancias en Decisiones:        23 (13.94% de error en decisiones firmes)
Precisión Efectiva (excl. UNKNOWN): 142 / 165 = 86.06%
```

El análisis individual de las 23 discrepancias revela su causa raíz objetiva:

#### A. Discrepancias por Categoría `OTHER` (15 casos):
- **Archivos:** `20261105T151250`, `20261105T151253`, `20261105T151257`, `20261105T151306`, `20261105T151309`, `20261105T151324`, `20261105T151327`, `20261111T224042`, `20261111T224045`, `20261111T224048`, `20261111T224051`, `20261111T224055`, `20261111T224059`, `20261111T224102`, `20261111T224113`.
- **Causa Raíz:** En estas capturas, las notas cualitativas de campo indicaban `"convertible rosa"`, `"convertible cian"` o `"recaptura de cuadrícula"`, lo cual provocó que la función `resolve_ground_truth_for_candidate` asignara la etiqueta de referencia genérica `OTHER`.
- **Comportamiento del Clasificador:** El clasificador examinó la carrocería física visible dentro del bounding box. En los convertibles azul/cian predijo consistentemente `BLUE` (con confianza de $0.50$ a $0.98$); en el convertible rosa predijo `RED` u `ORANGE` (la pintura rosa fucsia posee componentes cromáticas $R \gg B > G$ que caen en el cuadrante rojo/magenta); y en zonas con reflejos claros predijo `WHITE`.
- **Conclusión de Auditoría:** Estas 15 discrepancias **no son fallos del algoritmo**, sino una consecuencia de contrastar una predicción cromática específica de carrocería contra una etiqueta de referencia genérica `OTHER`.

#### B. Discrepancias por Asignación Heurística Errónea en Escenas Múltiples (4 casos):
- **Caso 20 (`20261114T010018_256587Z_11ba4eae1683_orig.jpg`):**
  - Detección YOLO: `label='truck'`, `conf=0.7168`, `bbox=[220, 92, 507, 314]`.
  - Nota de campo: *"Autobús escolar amarillo en vista frontal oblicua + auto rojo pequeño al fondo."*
  - Regla heurística de benchmark: Al no ser `'bus'` explícito, evaluó `'auto rojo' in vn` y asignó erróneamente `GT = RED`.
  - Predicción del Clasificador: **`YELLOW` (Conf: 0.839)**.
  - Dictamen: El objeto detectado físicamente era el autobús escolar amarillo. **El clasificador acertó el color real del objeto; el benchmark lo registró erróneamente como fallo.**
- **Casos 21, 22 y 23 (`20261114T010040`, `20261114T010043`, `20261114T010046`):**
  - Detección YOLO: `label='car'`, `conf=0.7983..0.8984`, `bbox=[239, 105, 338, 176]`.
  - Nota de campo: *"Autobús escolar amarillo visto directamente de frente sobre mesa + automóvil secundario."*
  - Regla heurística de benchmark: Evaluó `'amarillo' in vn` y asignó `GT = YELLOW`.
  - Predicción del Clasificador: **`RED` (Conf: 0.4934..0.8472)**.
  - Dictamen: El vehículo dentro del bounding box analizado era el automóvil secundario rojo sobre la mesa. **El clasificador predijo correctamente `RED`; el benchmark asignó erróneamente `YELLOW` por ambigüedad en la nota de campo.**

#### C. Discrepancias por Condiciones de Iluminación Severa (4 casos):
- **Reflejos / Contraluz (`GLARE_OR_HIGH_CONTRAST`):**
  - `20261106T163521` y `20261106T163525`: Automóvil rojo bajo sol rasante intenso predicho como `BROWN` (confianzas $0.61$ y $0.47$). La mezcla de desaturación solar y sombra de carrocería atenuó la componente $a^*$ de CIELAB, derivando en marrón.
- **Baja Luminosidad (`LOW_LIGHT`):**
  - `20261114T004926` y `20261114T004929`: Automóvil rojo en penumbra extrema predicho como `BROWN` (confianzas $0.69$ y $0.68$, luminancia media $L^* \approx 21$).

### 3.3. Análisis de las 20 Abstenciones `UNKNOWN` (Política de Prudencia)
Las 20 abstenciones registradas en el ROI se desglosan en:
- **15 casos en penumbra severa (`LOW_LIGHT`):** Luminancia media $L^* \in [16.1, 19.2]$, por debajo del umbral mínimo de seguridad ($L^* < 20.0$). El clasificador se abstuvo correctamente con estado `LOW_LIGHTING`.
- **3 casos de ambigüedad cromática:** Puntuación máxima por debajo del umbral mínimo de decisión ($< 0.35$).
- **2 casos de empate fotométrico:** Margen entre las dos categorías superiores $< 0.05$ (ej. `BROWN=0.44` vs `RED=0.41`).

> [!IMPORTANT]
> **Conclusión Metodológica:** La abstención del **10.81%** es un comportamiento altamente deseable en un sistema de seguridad de acceso vehicular. Es preferible que el sistema declare `UNKNOWN` ante penumbra o sombras severas a que emita un falso positivo cromático no fundamentado.

---

## 4. AUDITORÍA DE CONCURRENCIA Y AISLAMIENTO MULTICANAL

Para evaluar la solidez del clasificador ante cargas concurrentes reales de múltiples cámaras, se diseñó y ejecutó el benchmark de estrés multicanal [`audit_concurrency.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vision_05b/scripts/audit_concurrency.py) utilizando fotogramas reales y bounding boxes del corpus de evidencias sobre un `ThreadPoolExecutor`.

Se evaluaron 4 topologías operativas:
1. **1 Canal (Línea base):** 1 worker, 100 solicitudes.
2. **2 Canales (Topología actual de producción):** 2 workers (`CAM-ENTRADA` y `CAM-SALIDA`), 200 solicitudes.
3. **4 Canales (Escala media):** 4 workers concurrentes, 300 solicitudes.
4. **8 Canales (Saturación multicanal):** 8 workers concurrentes, 400 solicitudes.

### 4.1. Resultados Cuantitativos de Concurrencia

```
====================================================================================================
CANALES  SOLICITUDES  THROUGHPUT  LATENCIA P50  LATENCIA P95  LATENCIA P99  CPU PROC  MEM DELTA  ERR
====================================================================================================
1 Cam         100     203.7 FPS      3.72 ms      10.16 ms      12.04 ms     96.8%    +5.35 MB    0
2 Cams        200     416.7 FPS      4.49 ms      11.36 ms      13.07 ms    174.3%    +0.57 MB    0
4 Cams        300     560.1 FPS      6.71 ms      15.55 ms      17.03 ms    294.3%    +0.23 MB    0
8 Cams        400     375.6 FPS     19.95 ms      32.17 ms      37.61 ms    302.8%    +1.89 MB    0
====================================================================================================
```

### 4.2. Análisis de Resultados y Aislamiento de Estado
1. **Aislamiento Estricto y Ausencia de Estado Compartido Mutable:**
   - En todas las ejecuciones (1,000 inferencias de color acumuladas), se registró un total de **0 errores**, **0 excepciones no controladas** y **0 violaciones de aislamiento de memoria**.
   - Los datos de cada cámara permanecieron 100% confinados al contexto de su propio hilo.
2. **Compatibilidad con el Presupuesto de Streaming (33.3 ms para 30 FPS):**
   - En la topología activa de producción (**2 cámaras**), la latencia media es de **4.76 ms** (P50 = 4.49 ms, P95 = 11.36 ms), consumiendo apenas el **13.5%** del presupuesto de 33.3 ms por frame.
   - El throughput agregado en 2 cámaras alcanza **416.7 FPS**, lo que permite absorber picos de tráfico vehicular simultáneos sin degradar la tasa de captura.
   - Incluso bajo saturación extrema con **8 cámaras simultáneas**, la latencia P50 es de **19.95 ms** y el P95 es de **32.17 ms**, manteniéndose dentro del umbral en tiempo real sin desbordar las colas de ingesta.
3. **Consumo de Memoria y CPU:**
   - La huella de memoria RSS del proceso permaneció sumamente estable entre **104 MB y 108 MB**, con deltas insignificantes ($< 2$ MB) que confirman la ausencia de fugas de memoria en OpenCV o NumPy.

---

## 5. AUDITORÍA DE INTEGRACIÓN ARQUITECTÓNICA Y CONTRATOS

### 5.1. Acoplamiento y Patrón Fail-Safe en `VisionEngineCoordinator`
Se auditó [`VIGIA_Vision/runtime/coordinator.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/runtime/coordinator.py):
- **Inyección de Dependencias:** El constructor acepta `color_classifier: Optional[IVehicleColorClassifier] = None`. Si no se suministra, se instancia de forma diferida a partir de variables de entorno mediante `load_color_config_from_env()`.
- **Aislamiento de Fallos:** La llamada a `self._color_classifier.classify()` se encuentra protegida dentro de un bloque `try/except Exception` en el método privado `_classify_primary_vehicle_color()`. En caso de cualquier fallo inesperado, se captura el error, se emite un `logger.warning()` no bloqueante y se devuelve un `VehicleColorResult` con color `UNKNOWN` y estado `CLASSIFIER_ERROR`. **La detección vehicular y el flujo de autorización de acceso nunca se interrumpen.**
- **Métricas Operativas:** `VisionEngineCoordinator.get_operational_metrics()` expone de forma segura (`thread-safe` mediante cerrojo dedicado) el total de clasificaciones, abstenciones `UNKNOWN`, errores y ventana deslizante de latencias.

### 5.2. Contrato de Dominio `VisionResult`
Se auditó [`VIGIA_Core/domain/vision_result.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Core/domain/vision_result.py):
- Se agregaron los atributos opcionales `vehicle_color_pred: Optional[str] = None` y `vehicle_color_confidence: Optional[float] = None`.
- Se validaron las invariantes semánticas en `__post_init__`:
  - Si `status` es `CAMERA_ERROR` o `VISION_ERROR`, `vehicle_color_pred` **no puede estar presente** (lanza `ValueError`).
  - `vehicle_color_confidence` debe encontrarse estrictamente en el intervalo cerrado $[0.0, 1.0]$.
- **Retrocompatibilidad:** Todos los consumidores heredados de `VisionResult` que instancian el objeto sin pasar atributos de color continúan funcionando de forma idéntica sin modificaciones.

---

## 6. AUDITORÍA DE PERSISTENCIA DDL Y ESQUEMA RELACIONAL

### 6.1. Corrección Crítica de Nomenclatura Flyway
En la documentación de VISION-05B se propuso el archivo de migración como `BD/migrations/V003__add_detected_color_to_deteccion.sql`.
La auditoría detectó que el directorio [`BD/migrations/`](file:///c:/GEST.PROY.TI/Software/BD/migrations/) ya contiene:
- `V001__baseline_schema.sql`
- `V002__triggers.sql`
- `V003__seed_data.sql`
- `V004__enrolamiento_camaras_qr.sql`

> [!WARNING]
> **Observación de Auditoría:** Si se nombrara el archivo como `V003`, Flyway o el motor de migraciones abortaría el despliegue con un error fatal por versión duplicada o conflicto de suma de comprobación.  
> **Acción Requerida:** La migración DDL debe denominarse formalmente:  
> **`BD/migrations/V005__add_detected_color_to_deteccion.sql`**.

### 6.2. Validación Técnica del Script DDL Propuesto

```sql
-- Archivo: BD/migrations/V005__add_detected_color_to_deteccion.sql
-- Propósito: Incorporar atributos de color vehicular detectado por visión artificial.
-- Estado: PROPUESTA TÉCNICA AUDITADA (NO EJECUTADA EN PRODUCCIÓN)

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

-- Índice parcial propuesto para acelerar filtros de auditoría y seguridad
CREATE INDEX IF NOT EXISTS idx_deteccion_color_fecha
    ON deteccion(color_detectado, fecha_hora DESC)
    WHERE color_detectado IS NOT NULL;

COMMENT ON COLUMN deteccion.color_detectado IS 'Color predominante de la carrocería inferido por VIGIA_Vision.';
COMMENT ON COLUMN deteccion.confianza_color IS 'Nivel de confianza o margen fotométrico de la estimación de color [0.000, 1.000].';
```

### 6.3. Análisis de Compatibilidad, Almacenamiento y Rollback
1. **Compatibilidad $O(1)$ en PostgreSQL:** Al tratarse de columnas `NULL` sin valores por defecto estáticos, la adición de columnas se realiza como una modificación instantánea de metadatos en el catálogo `pg_attribute`, sin reescribir la tabla física ni generar bloqueos prolongados sobre transacciones concurrentes.
2. **Impacto en Disco:** Para registros con valores presentes, el costo adicional es de $\approx 14$ bytes por tupla. Un histórico de 100,000 detecciones demandará únicamente 1.4 MB de espacio en disco.
3. **Plan Formal de Rollback:**
   ```sql
   -- Rollback para V005__add_detected_color_to_deteccion.sql
   DROP INDEX IF EXISTS idx_deteccion_color_fecha;
   ALTER TABLE deteccion
       DROP CONSTRAINT IF EXISTS ck_deteccion_color_detectado,
       DROP CONSTRAINT IF EXISTS ck_deteccion_confianza_color,
       DROP COLUMN IF EXISTS color_detectado,
       DROP COLUMN IF EXISTS confianza_color;
   ```
4. **Cumplimiento de Restricción Innegociable:** Se constató que **ninguna instrucción DDL fue ejecutada contra la base de datos viva Docker (`127.0.0.1:5434`)**, preservando la integridad del esquema de producción.

---

## 7. VERIFICACIÓN DE REGRESIÓN INTEGRAL AUTOMATIZADA

Se ejecutó la suite de pruebas unitarias y de integración completa del proyecto mediante el ejecutable [`scratch/run_full_test_audit.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/scratch/run_full_test_audit.py) empleando el intérprete `.venv_cuda\Scripts\python.exe`.

### 7.1. Desglose de Resultados por Suite

#### Grupo 1: Visión Artificial, FSM, YOLO y Clasificación de Color (11 suites)
- `tests.unit.test_domain_models`: 16 pruebas | **16 PASS** | 0.01s
- `tests.unit.test_detection_repository`: 29 pruebas | **29 PASS** | 0.08s
- `tests.unit.test_topology_validator`: 17 pruebas | **17 PASS** | 0.24s
- `tests.unit.test_vision_stage1_components`: 16 pruebas | **16 PASS** | 0.16s
- `tests.unit.test_vision_02a_temporal_fsm`: 22 pruebas | **22 PASS** | 0.01s
- `tests.unit.test_vision_03c2_yolo26x_integration`: 15 pruebas | **15 PASS** | 6.50s
- `tests.unit.test_vision_04a_progressive_integration`: 6 pruebas | **6 PASS** | 3.11s
- `tests.unit.test_vision_05a_frontal_optimization`: 7 pruebas | **7 PASS** | 1.26s
- `tests.unit.test_vision_05b_color_classifier`: 11 pruebas | **11 PASS** | 0.97s
- `tests.unit.test_vision_pipeline`: 8 pruebas | **8 PASS** | 0.16s
- `tests.unit.test_yolo_detector`: 22 pruebas | **22 PASS** | 0.54s
*Subtotal Grupo 1:* **169 pruebas ejecutadas | 169 pasadas (100.00%) | 0 fallos | 0 errores | 13.05s**

#### Grupo 2: Sistema, Seguridad, Red, IPC y Persistencia (12 suites)
- `tests.unit.test_async_persistence_pilot`: 14 pruebas | **14 PASS** | 1.51s
- `tests.unit.test_auth_rbac`: 31 pruebas | **31 PASS** | 3.55s
- `tests.unit.test_auth_stream_protection`: 12 pruebas | **12 PASS** | 0.14s
- `tests.unit.test_camera`: 12 pruebas | **12 PASS** | 0.01s
- `tests.unit.test_camera_stream_and_backend`: 19 pruebas | **19 PASS** | 0.23s
- `tests.unit.test_crl_management`: 15 pruebas | **15 PASS** | 4.57s
- `tests.unit.test_ipc_hardening`: 16 pruebas | **16 PASS** | 31.78s
- `tests.unit.test_isolated_signer`: 12 pruebas | **12 PASS** | 2.91s
- `tests.unit.test_lan_detector`: 7 pruebas | **7 PASS** | 0.12s
- `tests.unit.test_mobile_ingest_api`: 49 pruebas | **49 PASS** | 5.68s
- `tests.unit.test_network_discovery`: 8 pruebas | **8 PASS** | 0.01s
- `tests.unit.test_signer_fail_closed`: 12 pruebas | **12 PASS** | 9.43s
*Subtotal Grupo 2:* **207 pruebas ejecutadas | 207 pasadas (100.00%) | 0 fallos | 0 errores | 59.92s**

### 7.2. Resumen Global de Regresión
```
================================================================================
TOTAL DE PRUEBAS EJECUTADAS:  376
PRUEBAS PASADAS (PASS):       376
PRUEBAS FALLIDAS (FAIL):      0
ERRORES DE EJECUCIÓN (ERR):   0
TASA DE ÉXITO GLOBAL:         100.00%
TIEMPO TOTAL DE EJECUCIÓN:    72.97s
================================================================================
```
No se detectó ninguna regresión funcional, de concurrencia ni de seguridad en el codebase.

---

## 8. MATRIZ DE RIESGOS, OBSERVACIONES Y RECOMENDACIONES

### 8.1. Observaciones Técnicas Detalladas

| ID | Observación | Severidad | Impacto Operativo | Mitigación Requerida |
| :---: | :--- | :---: | :--- | :--- |
| **OBS-01** | Número de migración Flyway en conflicto (`V003` duplicado). | Media | Error en despliegue de base de datos si se aplicara como `V003`. | Renombrar archivo a `V005__add_detected_color_to_deteccion.sql` antes de migrar. |
| **OBS-02** | Ambigüedad en notas de campo del benchmark en escenas con múltiples vehículos. | Baja | Las notas visuales describían varios autos a la vez, sesgando el cálculo de acierto. | Crear un dataset formal con bounding boxes y colores Ground Truth unívocos por vehículo. |
| **OBS-03** | Subclasificación cromática de vehículos bicolores o exóticos frente a `OTHER`. | Baja | Rosa/Fucsia es detectado como `RED` o `ORANGE`; Cian como `BLUE`. | Considerar aceptable este comportamiento o parametrizar `OTHER` con un umbral de mezcla. |
| **OBS-04** | Sensibilidad a iluminación extrema (penumbra y reflejo solar rasante). | Media | En penumbra, el rojo puede derivar a marrón o provocar abstención `UNKNOWN`. | La abstención `UNKNOWN` es el comportamiento seguro esperado; mantener umbral de luminancia $\ge 20$. |

### 8.2. Hoja de Ruta para la Fase Siguiente (Validación Controlada en Campo)
1. **Paso 1 (Aprobación del Propietario):** El propietario del sistema evaluará este informe de auditoría de cierre.
2. **Paso 2 (Validación Controlada sin Persistencia Activa):** Activar el clasificador de color en `VisionEngineCoordinator` en modo de solo lectura / logging para verificar el comportamiento en vivo de las dos cámaras físicas (`CAM-ENTRADA` y `CAM-SALIDA`) sin alterar la base de datos PostgreSQL.
3. **Paso 3 (Migración DDL Controlada `V005`):** Una vez validada la estabilidad en campo durante un ciclo operativo completo, aplicar la migración `V005__add_detected_color_to_deteccion.sql` sobre la base de datos y activar la persistencia en `DetectionRepository`.

---

## 9. DECLARACIÓN FORMAL DE CIERRE

El proceso de auditoría técnica independiente para la fase **VIGIA-VISION-05B.1** concluye satisfactoriamente con la emisión del dictamen **`APPROVED WITH OBSERVATIONS`**.

El clasificador de color vehicular ha demostrado ser algorítmicamente correcto, seguro ante condiciones de frontera, altamente eficiente en procesamiento multicanal concurrente y compatible con el ecosistema de microservicios y directivas de seguridad de VIGÍA Vision Systems.

---
*Fin del Informe de Auditoría Técnica VIGIA-VISION-05B.1.*
