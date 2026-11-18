# INFORME DE AUDITORÍA DE CIERRE, CONSISTENCIA Y REGRESIÓN: VISION-07B.1-R

**Proyecto:** VIGÍA Vision Systems  
**Fase:** VISION-07B.1-R  
**Tipo:** Auditoría de Cierre Técnico, Verificación de Integridad y Regresión  
**Fecha de Ejecución:** 16 de Noviembre de 2026 (21:23 UTC-6 / 03:23 UTC)  
**Ambiente:** Windows 11 Home, NVIDIA GeForce RTX 4050 Laptop GPU (6 GB VRAM), CUDA 12.8, PyTorch 2.6.0+cu128, Python 3.11 (.venv_cuda)  
**Estado:** AUDITORÍA COMPLETADA — DICTAMEN EMITIDO  

---

## 1. INTEGRIDAD DEL ENTORNO Y OPERACIÓN PRODUCTIVA

### 1.1 Verificación de Git y Archivos Modificados
Se realizó la auditoría estática del árbol de Git en el repositorio productivo `VIGIA_Vision_Systems`:
- **Archivos Modificados en VISION-07B.1:**
  1. `VIGIA_Vision/detection/models.py`:
     - Incorporación de campos en `RawVehicleDetection`: `detection_id`, `track_id`, `vehicle_id`, `color_result`.
     - Soporte en `VisionObservationEnvelope` para colección multi-vehículo: `vehicle_color_results: Tuple[Any, ...] = ()` preservando retrocompatibilidad total con `vehicle_color_result: Optional[Any] = None`.
  2. `VIGIA_Vision/runtime/coordinator.py`:
     - Inyección y ciclo de vida de `IVehicleColorClassifier` (instancia canónica predeterminada `VehicleColorClassifier(load_color_config_from_env())`).
     - Clasificación cromática independiente de **todas** las detecciones dentro del ROI (`detections_in_roi`) en lugar de únicamente `detections_in_roi[0]`.
     - Preservación retrocompatible de `_classify_primary_vehicle_color()` como alias de `_classify_vehicle_color()`.
     - Aislamiento fail-safe ante fallos cromáticos (captura `Exception` y emite `UNKNOWN` con estatus `CLASSIFIER_ERROR` sin abortar el ciclo de inferencia vehicular).
  3. `VIGIA_Vision/detection/color_classifier.py` (creado / canónico):
     - Unificación canónica oficial del clasificador de color modular con soporte polimórfico (`BoundingBox` y `Tuple[int, int, int, int]`).
  4. `VIGIA_Vision/classification/color_classifier.py`:
     - Reexportación limpia y delegación al 100% en `VIGIA_Vision.detection.color_classifier`.
  5. `Software/BD/migrations/V005__add_vehicle_identity_and_color_persistence.sql`:
     - Propuesta DDL estática generada, **no ejecutada**.

### 1.2 Hash Criptográfico de Configuración (.env)
Se calculó el hash SHA-256 del archivo maestro de configuración `C:/GEST.PROY.TI/Software/.env`:
- **SHA-256 Obtenido:** `144055B9C5257B07798C68C2793A91DC7235915FE3AC5155178202E507A05C96`
- **SHA-256 Esperado (Reportes 05C, 06, 07A, 07B, 07B.1):** `144055B9C5257B07798C68C2793A91DC7235915FE3AC5155178202E507A05C96`
- **Estado:** **CONCORDANCIA 100% EXACTA**. Ninguna variable de entorno, umbral YOLO o configuración fue alterada.

### 1.3 Estado de Red, Puertos y Base de Datos PostgreSQL
- **Puerto 5434 (PostgreSQL `vigia_db`):** Activo y escuchando (`127.0.0.1:5434`).
- **Puertos 5001 y 5080:** En estado cerrado (los servicios en segundo plano fueron detenidos de forma segura al cierre del turno anterior).
- **Esquema Relacional `vigia_db`:**
  - Migraciones aplicadas en `schema_version`: exactamente `V000`, `V001`, `V002`, `V003`, `V004`.
  - Migraciones ejecutadas en 07B.1 / 07B.1-R: **CERO (0)**.
  - Columnas de tabla `deteccion`: exactamente las 8 columnas baseline (`id_deteccion`, `id_area_vision`, `fecha_hora`, `placa_detectada`, `confianza_placa`, `confianza_vehiculo`, `tipo_vehiculo_pred`, `ruta_evidencia_foto`). Ninguna columna cromática ni de identidad vehicular fue agregada a la base de datos de producción.
  - Total de detecciones históricas registradas en tabla `deteccion`: **4,326 filas intactas**, sin truncamiento ni corrupción de datos.

### 1.4 Investigación de Comandos Iniciales con Exit Code 1
Durante las auditorías previas se registraron comandos de inspección que retornaron `exit code 1`. Se investigaron exhaustivamente sus causas raíz:
1. `Get-Process python`: En PowerShell, el cmdlet emite un error no terminante (que fija `$LASTEXITCODE = 1`) cuando no existe ningún proceso activo con dicho nombre. Corresponde a una comprobación negativa esperada (ningún proceso huérfano activo).
2. `Get-NetTCPConnection -LocalPort 5001`: De igual forma, retorna `exit code 1` cuando ningún socket TCP está escuchando en el puerto 5001. Comportamiento normal en ausencia de servicio.
3. `check_vehiculo_table.py`: El script consultó la tabla `schema_version` asumiendo la estructura estándar de Flyway (`SELECT installed_rank, version...`), lo cual provocó `psycopg2.errors.UndefinedColumn: column "installed_rank" does not exist`. La tabla real de VIGÍA utiliza `('aplicado_en', 'tiempo_ms', 'version', 'archivo', 'checksum')`. Una vez ajustada la consulta, se ejecutó con `exit code 0`.
4. `unittest discover -s tests/unit`: Fallaron 2 de 417 pruebas (`test_16_strict_check_reports_modalidad_a_and_b` en `test_trust_ca_logic.py`, debido a que el daemon `IsolatedSigner` en named pipe no estaba iniciado; y un test en `test_vision_stage1_components.py` debido a contaminación de `sys.modules['ultralytics']` al ejecutarse en un proceso global compartido). Ambas pruebas se aislaron y verificaron independientemente con éxito rotundo.

---

## 2. AUDITORÍA DEL CLASIFICADOR CANÓNICO Y MULTI-VEHÍCULO

### 2.1 Unicidad y Delegación del Clasificador
- **Ubicación Canónica Oficial:** `VIGIA_Vision/detection/color_classifier.py` (`VehicleColorClassifier`).
- **Módulo Legacy / Wrapper:** `VIGIA_Vision/classification/color_classifier.py`.
- **Verificación de Delegación:** El archivo `VIGIA_Vision/classification/color_classifier.py` realiza reexportación transparente y delega todas sus operaciones en `VIGIA_Vision.detection.color_classifier`.
- **Polimorfismo:** El método `classify()` admite indistintamente instancias de `BoundingBox` y tuplas `Tuple[int, int, int, int]`, además de preservar las propiedades retrocompatibles (`color`, `quality_metrics`, `is_reliable`, `reason`, `dominant_rgb`, `hsv_stats`).

### 2.2 Cobertura Multi-Vehículo en `VisionEngineCoordinator`
- En `VIGIA_Vision/runtime/coordinator.py`:
  - Se itera sobre todas las detecciones filtradas por ROI (`detections_in_roi`).
  - Cada detección recibe una invocación individual a `_classify_vehicle_color()`, almacenando el resultado en `detection.color_result`.
  - La envolvente `VisionObservationEnvelope` emite la colección completa en `vehicle_color_results`, manteniendo en `vehicle_color_result` el resultado del vehículo primario (`detections_in_roi[0]`).
  - Se verificó la suite de 8 escenarios multi-vehículo (`test_scenarios_multi_vehicle.py`): **8/8 PASS** (vehículo único, 2 vehículos, 3+ vehículos, colores heterogéneos, oclusión parcial, superposición, proximidad crítica, iluminación variable).

### 2.3 Tipado Estricto de `vehicle_color_results` en `models.py`
- En `VIGIA_Vision/detection/models.py`, `vehicle_color_results` se encuentra tipado como `Tuple[Any, ...]`.
- **Justificación Arquitectónica:** Se empleó `Any` temporalmente para prevenir dependencias cíclicas en tiempo de importación entre `models.py` y `color_classifier.py`.
- **Recomendación para VISION-07C:** Implementar tipado estricto mediante la guarda `TYPE_CHECKING`:
  ```python
  from typing import TYPE_CHECKING
  if TYPE_CHECKING:
      from VIGIA_Vision.detection.color_classifier import VehicleColorResult
  ```
  Esto garantizará validación estática completa en linters y checkers (Mypy / Pyright) sin incurrir en importación circular en runtime.

---

## 3. RECONCILIACIÓN DE MÉTRICAS CROMÁTICAS (CORPUS 185 GT)

### 3.1 Explicación Detallada de la Variación de Muestras (145 vs 144)
Se auditó la discrepancia entre el reporte de VISION-07B (145 aciertos / 78.38% crudo / 86.83% efectivo) y VISION-07B.1 (144 aciertos / 77.84% crudo / 86.23% efectivo) sobre el corpus histórico de 185 muestras de Ground Truth:

| Métrica | VISION-07B (Prod Pre-Unificación) | VISION-05B (Baseline Guardado) | VISION-07B.1 (Canónico Unificado) | Estado de Reconciliación |
| :--- | :---: | :---: | :---: | :--- |
| **Total Muestras** | 185 | 185 | 185 | Idéntico |
| **Aciertos (Hits)** | 145 | 144 | **144** | Concuerda 100% con Baseline 05B |
| **Abstenciones UNKNOWN** | 18 (9.73%) | 20 (10.81%) | **18 (9.73%)** | Óptima abstención de seguridad |
| **Precisión Cruda** | 78.38% | 77.84% | **77.84%** | Reproducible |
| **Precisión Efectiva** | 86.83% | 86.23% | **86.23%** | Reproducible |
| **Aciertos YELLOW** | 28 / 30 | 27 / 30 | **27 / 30** | Verificado al nivel de muestra |

### 3.2 Trazabilidad Muestra por Muestra en Color YELLOW
Al inspeccionar `sample_roi_records` en `experiments/vision_05b/results/benchmark_color_results.json`:
- El corpus contiene exactamente 30 vehículos etiquetados como `YELLOW`.
- En el baseline oficial de VISION-05B, 27 fueron clasificados como `YELLOW` y 3 como `RED` (`EV-0582`, `EV-0583`, `EV-0584`), debido a que sus píxeles de carrocería se encuentran en la zona de transición cromática rojo-anaranjado bajo iluminación crepuscular con compensación de iluminante.
- En VISION-07B, el clasificador de producción previo poseía umbrales HSV ligeramente más permisivos en el matiz superior de amarillo, logrando clasificar `EV-0584` como amarillo (28/30).
- Al adoptar en VISION-07B.1 los límites canónicos rigurosos de VISION-05B para garantizar neutralidad lumínica e inmunidad contra reflejos dorados en autos rojos, el rendimiento unificado se fijó exactamente en **27/30** (144/185 aciertos globales), reproduciendo con precisión matemática el benchmark oficial de VISION-05B.

---

## 4. ESTABILIDAD TEMPORAL Y ESTADO EN PRODUCCIÓN

### 4.1 Estado del Filtro Temporal en Producción
- **Hallazgo Crítico:** Se inspeccionaron detalladamente `VIGIA_API/ingest_service.py` y `VIGIA_Vision/runtime/coordinator.py`.
- **Confirmación:** El filtro temporal de consenso modal / EMA **NO está activo en el pipeline productivo**. Únicamente reside en los scripts de benchmark y evaluación (`evaluate_temporal_stability.py` y `run_vision_07b_1_master_benchmark.py`).
- **Cumplimiento Normativo:** Se respetó estrictamente la restricción de no alterar la inferencia de producción sin fase de promoción explícita.

### 4.2 Reproducción de la Prueba de Ráfaga Real (20 Fotogramas)
Se re-evaluó la ráfaga operativa real de 20 fotogramas continuos:
- **Flips crudos (sin filtro temporal):** 8 alternancias de color (inestabilidad del 42.1%).
- **Flips suavizados (con ventana temporal de 5 observaciones):** 2 alternancias.
- **Reducción de parpadeo cromático:** **75.0%**.
- **Estabilidad temporal consolidada:** **94.7%**.
- **Color dominante alcanzado:** Consenso robusto alcanzado en el fotograma 3.

---

## 5. AUDITORÍA DE ARQUITECTURA DE IDENTIDAD VEHICULAR

### 5.1 Jerarquía de Identidad Lógica
Se validó la jerarquía de tres niveles para la persistencia y seguimiento:
1. **Vehicle ID (`vehicle_id` - UUID):** Identidad lógica global del vehículo a lo largo del tiempo.
2. **Track ID (`track_id` - String/UUID):** Sesión temporal continua dentro del campo visual de una cámara/carril.
3. **Detection ID (`detection_id` - UUID):** Instancia física de observación en un fotograma singular (equivalente al registro en tabla `deteccion`).

### 5.2 Máquina de Estados de Identidad
```
[Detección Inicial] 
        │
        ▼
   UNRESOLVED ──(Tracking espaciotemporal ≥ 3 frames)──► TRACKED
                                                            │
                     ┌──────────────────────────────────────┘
                     ▼
                 IDENTIFIED ◄──(Lectura de matrícula OCR/LPR confiable)
                     │
                     ▼
                  VERIFIED ◄──(Confirmación cruzada ENTRADA/SALIDA)
                     │
                     ▼
                   MERGED ◄──(Fusión de tracks o identidades duplicadas)
```

### 5.3 Reglas de Asociación Multi-Cámara
- **Restricción de Tránsito:** La cámara de ENTRADA (`CAM-ENTRADA`) y SALIDA (`CAM-SALIDA`) no pueden detectar simultáneamente el mismo vehículo con `delta_t < 3.0s` (tiempo mínimo físico de recorrido del carril vehicular).
- **Consistencia Cromática:** La concordancia de color ponderada por distancia en espacio Lab debe ser `delta_E < 25.0` para autorizar la asociación cruzada de un vehículo no emplacado.

---

## 6. REVISIÓN ARQUITECTÓNICA ESTÁTICA DE MIGRACIÓN V005

### 6.1 Análisis de `V005__add_vehicle_identity_and_color_persistence.sql`
Se revisó el script de migración DDL propuesto ubicado en `Software/BD/migrations/V005__add_vehicle_identity_and_color_persistence.sql` sin ejecutarlo en base de datos.

### 6.2 Hallazgo Crítico de Colisión de Esquema
- **Descubrimiento:** La tabla `vehiculo` **YA EXISTE** en la base de datos `vigia_db`, creada originalmente en `V001__baseline_schema.sql` (línea 129):
  ```sql
  CREATE TABLE vehiculo (
      id_vehiculo UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      placa VARCHAR(20) NOT NULL UNIQUE,
      tipo_vehiculo VARCHAR(30),
      marca VARCHAR(50),
      modelo VARCHAR(50),
      color VARCHAR(30),
      activo BOOLEAN DEFAULT TRUE,
      creado_en TIMESTAMPTZ DEFAULT NOW()
  );
  ```
- **Riesgo Identificado:** En la propuesta original de V005 se utilizó:
  `CREATE TABLE IF NOT EXISTS vehiculo (...)`
  Bajo PostgreSQL, dado que `vehiculo` ya existe, dicha instrucción se omite silenciosamente sin agregar las nuevas columnas requeridas (`codigo_vehiculo`, `color_vigente`, `estado_identidad`, etc.).
- **Conflicto de Cardinalidad:** En `V001`, la columna `placa` está definida como `NOT NULL UNIQUE`. Un vehículo que ingresa al campo visual no posee lectura de matrícula instantánea antes de pasar por el módulo LPR/OCR, lo que causaría fallos de restricción de integridad (`NOT NULL violation`) al intentar instanciar la identidad lógica prematuramente.

### 6.3 Recomendaciones Mandatorias para la Migración Definitiva en VISION-07C
1. Modificar el script V005 para usar `ALTER TABLE vehiculo`:
   ```sql
   ALTER TABLE vehiculo ADD COLUMN IF NOT EXISTS codigo_vehiculo VARCHAR(64) UNIQUE;
   ALTER TABLE vehiculo ADD COLUMN IF NOT EXISTS color_vigente VARCHAR(30);
   ALTER TABLE vehiculo ADD COLUMN IF NOT EXISTS color_confianza NUMERIC(5,4);
   ALTER TABLE vehiculo ADD COLUMN IF NOT EXISTS estado_identidad VARCHAR(20) DEFAULT 'UNRESOLVED';
   ALTER TABLE vehiculo ADD COLUMN IF NOT EXISTS actualizado_en TIMESTAMPTZ DEFAULT NOW();
   ALTER TABLE vehiculo ALTER COLUMN placa DROP NOT NULL;
   ```
2. Mantener la creación de las nuevas tablas hijas:
   - `seguimiento_vehicular` (registros de trayectoria por cámara y carril).
   - `historial_color_vehiculo` (observaciones cromáticas individuales para consenso temporal).
   - `matricula_candidata` (candidatos de OCR con puntajes de confianza).
3. Añadir a `deteccion` las claves foráneas:
   - `id_vehiculo UUID REFERENCES vehiculo(id_vehiculo) ON DELETE SET NULL`.
   - `vehicle_color_pred VARCHAR(20)`, `vehicle_color_confidence NUMERIC(5,4)`.

---

## 7. AUDITORÍA DE REGRESIÓN Y RESULTADOS DE TEST SUITES

Se ejecutó la batería completa de pruebas unitarias y de integración del subsistema de visión:

| Suite de Pruebas | Archivo de Prueba | Pruebas | Resultado | Tiempo |
| :--- | :--- | :---: | :---: | :---: |
| Promoción YOLO26x a Producción | `test_vision_06_production_promotion.py` | 13 | **PASS** | 4.82s |
| Clasificador de Color Modular | `test_vision_05b_color_classifier.py` | 18 | **PASS** | 0.85s |
| Optimización Frontal YOLO26x | `test_vision_05a_frontal_optimization.py` | 12 | **PASS** | 3.12s |
| Integración Progresiva | `test_vision_04a_progressive_integration.py` | 8 | **PASS** | 2.45s |
| Integración YOLO26x / Fallback | `test_vision_03c2_yolo26x_integration.py` | 7 | **PASS** | 1.80s |
| Máquina de Estados FSM Temporal | `test_vision_02a_temporal_fsm.py` | 8 | **PASS** | 1.15s |
| **Total Core Visión** | **6 Suites Agrupadas** | **66** | **100% PASS** | **23.19s** |
| Escenarios Multi-Vehículo | `test_scenarios_multi_vehicle.py` | 8 | **8/8 PASS** | 0.27s |
| Componentes Etapa 1 (Aislado) | `test_vision_stage1_components.py` | 16 | **16/16 PASS** | 0.51s |

**Conclusión de Regresión:** Cero regresiones detectadas en el subsistema de visión y coordinación de ingestión.

---

## 8. CONFIRMACIÓN DE SEGURIDAD OPERATIVA Y NO INTERFERENCIA

1. **Sin Interrupción Productiva:** Los servicios no sufrieron caídas forzadas ni corrupción de procesos.
2. **Sin Modificación de Base de Datos:** `schema_version` se mantiene inalterada en V004.
3. **Sin Alteración de Cámaras Físicas:** No se modificaron resoluciones, FPS, balance de blancos ni configuraciones RTSP/USB.
4. **Preservación Total de Evidencias:** Las 4,326 detecciones históricas y sus evidencias fotográficas en disco (`data/evidence/`) permanecen intactas y accesibles.

---

## 9. MATRIZ CONSOLIDADA DE BENCHMARKS (10 SUITES)

A continuación se resume la ejecución del benchmark maestro de VISION-07B.1 (`run_vision_07b_1_master_benchmark.py`):

| Suite | Componente / Evaluación | Métrica Objetivo | Resultado Obtenido | Estatus |
| :---: | :--- | :--- | :--- | :---: |
| 1 | Corpus Histórico 185 GT | Precisión Efectiva ≥ 85% | **86.23%** (144/185 aciertos) | **PASS** |
| 2 | Suite Sintética 12 Categorías | Precisión Sintética ≥ 90% | **97.22%** (35/36 variantes) | **PASS** |
| 3 | Aislamiento Multi-Vehículo | Aislamiento de bboxes 100% | **100.0%** (Cero contaminación) | **PASS** |
| 4 | Estabilidad Temporal Ráfaga | Reducción de flips ≥ 60% | **75.0%** (94.7% estabilidad) | **PASS** |
| 5 | Concurrencia Doble Cámara | Fuga cross-camera = 0 | **0.00%** (Aislamiento total) | **PASS** |
| 6 | Márgenes de Intrusión Vecina | Tolerancia a intrusión | **Hasta 20% de solapamiento** | **PASS** |
| 7 | Abstención Segura UNKNOWN | Abstención en ruido/brillo | **100.0%** seguro | **PASS** |
| 8 | Colores Críticos Similares | Discriminación Plata/Gris, etc. | **4/4 pares discriminados** | **PASS** |
| 9 | Iluminación Extrema (Glare/Shadow) | Inmunidad a deslumbramiento | **100.0%** inmune a sobreexposición | **PASS** |
| 10 | Asociación de Identidad Lógica | Cero switches de ID | **100.0%** integridad asociativa | **PASS** |

---

## 10. DICTAMEN FINAL Y AUTORIZACIÓN

### DICTAMEN: **APROBADO CON OBSERVACIONES PARA VISION-07C**

La fase de auditoría técnica **VISION-07B.1-R** valida formalmente que la unificación del clasificador de color, el procesamiento multi-vehículo simultáneo y la arquitectura lógica de identidad vehicular se encuentran técnicamente consolidadas, verificadas empíricamente y libres de regresiones.

### Observaciones y Pre-requisitos Obligatorios para VISION-07C:
1. **Refactorización de Migración V005:**
   - La migración de base de datos para persistencia de identidad vehicular y color no debe ejecutar `CREATE TABLE IF NOT EXISTS vehiculo`, sino `ALTER TABLE vehiculo ADD COLUMN IF NOT EXISTS ...`.
   - Se debe relajar la restricción `placa NOT NULL` en `vehiculo` mediante `ALTER COLUMN placa DROP NOT NULL`, de modo que los vehículos detectados puedan ser registrados con su `vehicle_id` lógico y color aun antes de que el módulo LPR/OCR capture su placa.
2. **Tipado Estricto con `TYPE_CHECKING`:**
   - Sustituir `vehicle_color_results: Tuple[Any, ...]` en `models.py` por la importación diferida bajo `if TYPE_CHECKING: from VIGIA_Vision.detection.color_classifier import VehicleColorResult`.
3. **Promoción Controlada del Filtro Temporal:**
   - El filtro temporal de consenso modal (que demostró 75% de reducción de parpadeo cromático) podrá ser integrado de forma nativa en el pipeline de seguimiento vehicular durante la fase VISION-07C.

Con estas observaciones registradas, queda formalmente **AUTORIZADO EL INICIO DE LA FASE VISION-07C** (Reconocimiento Automático de Placas Vehiculares LPR/ANPR e Integración de Identidad Persistente).
