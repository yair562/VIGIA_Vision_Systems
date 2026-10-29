# SPRINT-00 — Diagnóstico y Definición Técnica

## Control Documental
- **Identificador:** `SPRINT-00`
- **Nombre del Sprint:** Diagnóstico, Contratos de Fase 1, Auditoría Integral y Diseño del Motor Propio de Visión Artificial
- **Estado:** `CERRADO` *(reconstrucción retrospectiva verificada sobre el historial de Git y los artefactos de auditoría/diseño)*
- **Periodo Verificado:** 09 de septiembre de 2026 – 29 de octubre de 2026 *(distribuido en tres etapas verificables; véase la nota de precisión cronológica en §1.2)*
- **Commits de Referencia en `VIGIA_Vision_Systems`:** `44da870` (2026-09-09) $\to$ `ae4148d` (2026-10-27) $\to$ `92f4d78` (2026-10-28) $\to$ `4105805` (2026-10-28)
- **Commits de Referencia en Repositorio `BD`:** `3a1aea3` (2026-10-09) $\to$ `9c798ca` (2026-10-11) $\to$ `c8f2a5d` (2026-10-11)
- **Hitos Relacionados:** Fase 0 ([`BASELINE_V1.1.md`](../BASELINE_V1.1.md)) y Fase 1 / Hito `H1` ([`07_cronograma_maestro.md`](../07_cronograma_maestro.md))

---

## 1. Planificación

### 1.1. Objetivo y Justificación
- **Objetivo:** Establecer las bases arquitectónicas, el esquema relacional en PostgreSQL, los contratos inmutables de dominio/persistencia/topología (`DOC-01` a `DOC-05`), auditar el estado real de los activos (`VIGIA_Vision_Systems`, `BD` y el prototipo `VR_Semaforo`) y diseñar la arquitectura del motor propio de visión artificial dentro de `VIGIA_Vision/`.
- **Justificación:** Antes de implementar el motor de visión de producción, era indispensable:
  1. Contar con contratos tipados e inmutables en `VIGIA_Core` y un esquema relacional verificable en PostgreSQL (`BD/migrations/V000..V003`).
  2. Contrastar la documentación con el código existente para no confundir especificaciones propuestas o el prototipo monolítico `VR_Semaforo` con componentes de producción listos.
  3. Definir un diseño propio y desacoplado en `VIGIA_Vision/` que prohibiera reutilizar o importar `VR_Semaforo` en producción.

### 1.2. Estado Inicial Conocido y Precisión Cronológica (Sin Cronología Ficticia)
Conforme a la inspección de `git log` en ambos repositorios (`VIGIA_Vision_Systems` y `BD`), los trabajos que conforman este expediente retrospectivo **no ocurrieron en un único bloque temporal**, sino en tres estratos claramente diferenciables:

1. **Estrato 1 — Fundaciones Documentales y Esquema PostgreSQL (09 sep – 23 oct 2026) `[VERIFICADO EN REPOSITORIO / GIT]`:**
   - Creación del repositorio principal con el prototipo de referencia `VR_Semaforo/` y los documentos canónicos `01` a `10` y [`BASELINE_V1.1.md`](../BASELINE_V1.1.md) (commit inicial `44da870` del 2026-09-09 y replanificación del cronograma en commit `74004bb` del 2026-10-13).
   - Creación del repositorio independiente `C:\GEST.PROY.TI\Software\BD` entre el 09 y el 11 de octubre de 2026 (commits `3a1aea3`, `9c798ca` y `c8f2a5d`), estableciendo el contenedor Docker `vigia-db` en el puerto `5433`, las migraciones `V000` a `V003`, el orquestador `apply_migrations.ps1` y las pruebas SQL `V001__integrity_checks.sql`.
2. **Estrato 2 — Especificaciones Técnicas de Fase 1, Contratos Base y Diagramas (27 – 28 oct 2026) `[VERIFICADO EN REPOSITORIO / GIT]`:**
   - **Commit `ae4148d` (2026-10-27):** Incorporación de [`DOC-01`](../fase_1/DOC-01_modelos_dominio.md) a [`DOC-05`](../fase_1/DOC-05_plan_pruebas_unitarias.md), los 10 diagramas de flujo `DF-01` a `DF-10` en [`11_Diagrama_de_flujo/`](../GEST_PROY_SOFT/11_Diagrama_de_flujo/README.md) y los modelos inmutables [`VisionResult`](../../VIGIA_Core/domain/vision_result.py) y [`AccessDecision`](../../VIGIA_Core/domain/access_decision.py) en `VIGIA_Core/domain/`.
   - **Commits `92f4d78` y `4105805` (2026-10-28):** Incorporación de los diagramas de casos de uso (`DCU-01`, `DCU-02`) y de bloques (`DB-01`, `DB-02`, `DB-03`), implementación de [`detection_repository.py`](../../VIGIA_Core/repository/detection_repository.py) (`IDetectionRepository`, `DetectionInsertDTO`, `PsycopgDetectionRepository`, `map_tipo_vehiculo_ddl_v1`) y [`topology_validator.py`](../../VIGIA_Vision/config/topology_validator.py) (`TopologyValidator` con reglas R1–R8), además de las primeras 5 suites en `tests/unit/` (donde `test_camera.py`, `test_topology_validator.py` y `test_vision_pipeline.py` aún importaban clases de `VR_Semaforo`).
3. **Estrato 3 — Auditoría Técnica Integral y Diseño del Motor Propio `VIGIA_Vision` (29 oct 2026) `[REPORTADO POR AGENTE / SESIÓN Y VERIFICADO CONTRA REPOSITORIO]`:**
   - Ejecución en modo de solo lectura de la **Auditoría Integral de VIGÍA** y del **Diseño del Motor Propio de Visión Artificial**, formalizando la prohibición de importar `VR_Semaforo` y definiendo el plan de implementación en 4 etapas dentro de `VIGIA_Vision/`.

### 1.3. Alcance
- **Incluido:**
  - Modelado y migraciones de la base de datos PostgreSQL (`V000`–`V003`).
  - Documentación técnica de Fase 1 (`DOC-01` a `DOC-05`) y diagramas de arquitectura (`DF-01..10`, `DCU-01..02`, `DB-01..03`).
  - Implementación de contratos base en `VIGIA_Core/domain/`, `VIGIA_Core/repository/` y `VIGIA_Vision/config/topology_validator.py`.
  - Auditoría técnica de activos existentes y diseño arquitectónico del motor propio `VIGIA_Vision`.
- **Excluido:**
  - Implementación de los submódulos de captura, ROI, almacenamiento de evidencias y coordinación en `VIGIA_Vision/` (delegados a `SPRINT-01`).

### 1.4. Tareas y Entregables
| ID Tarea | Descripción | Entregable | Estrato Temporal |
| :---: | :--- | :--- | :---: |
| `T00-01` | Estructuración y dockerización de PostgreSQL 16+ (`V000`–`V003`) | Repositorio [`BD/`](../../../BD/README.md) | 09–11 oct 2026 |
| `T00-02` | Especificación de contratos y reglas de Fase 1 | [`Docs/fase_1/DOC-01..05`](../fase_1/DOC-01_modelos_dominio.md) | 27–28 oct 2026 |
| `T00-03` | Implementación de contratos protegidos de dominio, persistencia y topología | `VIGIA_Core/domain/`, `VIGIA_Core/repository/`, `VIGIA_Vision/config/topology_validator.py` | 27–28 oct 2026 |
| `T00-04` | Elaboración de diagramas SVG de flujo, casos de uso y bloques | [`11_Diagrama_de_flujo/`](../GEST_PROY_SOFT/11_Diagrama_de_flujo/README.md), [`12_Diagrama_de_casos_de_uso/`](../GEST_PROY_SOFT/12_Diagrama_de_casos_de_uso/README.md), [`13_Diagramas_de_bloques/`](../GEST_PROY_SOFT/13_Diagramas_de_bloques/README.md) | 27–28 oct 2026 |
| `T00-05` | Auditoría técnica integral del estado real del proyecto | Diagnóstico verificable de brechas entre documentación, código, BD y `VR_Semaforo` | 29 oct 2026 |
| `T00-06` | Diseño arquitectónico del motor propio `VIGIA_Vision` en 4 etapas | Especificación de módulos, contratos internos, ROI, evidencias y plan por etapas | 29 oct 2026 |

### 1.5. Dependencias y Riesgos Identificados
- **Riesgo de contaminación con el prototipo (`VR_Semaforo`):** En el commit `92f4d78`, tres archivos de prueba en `tests/unit/` importaban módulos de `VR_Semaforo/vision/` inyectando `VR_Semaforo` en `sys.path`.
- **Riesgo de discrepancia de catálogos SQL vs. Python:** `VisionResult` admite `'AUTOBUS'`, mientras que la restricción `ck_deteccion_tipo_vehiculo` de PostgreSQL exige `'OTRO'`.
- **Riesgo de desalineación documental:** Coexistencia de documentos de Fase 0 que mencionan SQLite con documentos y migraciones de Fase 1 que implementan PostgreSQL 16+.

### 1.6. Criterios de Aceptación
- **CA00-01:** Esquema PostgreSQL versionado (`V000`–`V003`) con tablas `camara`, `area_vision`, `deteccion` y `evento_acceso` definidas.
- **CA00-02:** Contratos `VisionResult`, `AccessDecision`, `IDetectionRepository` / `DetectionInsertDTO` y `TopologyValidator` implementados y cubiertos por pruebas unitarias.
- **CA00-03:** Auditoría técnica completada identificando qué módulos tienen código real y cuáles son solo READMEs o prototipos.
- **CA00-04:** Arquitectura del motor propio `VIGIA_Vision` diseñada sin depender de `VR_Semaforo` y compatible con los contratos protegidos.

---

## 2. Ejecución

### 2.1. Actividades Realizadas y Trazabilidad en Git

#### A. Repositorio `C:\GEST.PROY.TI\Software\BD` `[VERIFICADO EN REPOSITORIO / GIT]`
- **Commit `3a1aea3` (2026-10-09):** Estructura inicial del repositorio de base de datos (`README.md`, `.gitignore`, carpetas `docs/`, `migrations/`, `scripts/`, `tests/`).
- **Commit `9c798ca` (2026-10-11):** Dockerización en `compose.yaml` (`postgres:16-alpine`, contenedor `vigia-db`, puerto `5433`), migraciones `V000__init_database.sql`, `V001__baseline_schema.sql` (15 tablas), `V002__triggers.sql`, `V003__seed_data.sql`, scripts PowerShell (`apply_migrations.ps1`, `check_connection.ps1`, `provision_admin.ps1`) y `tests/V001__integrity_checks.sql`.
- **Commit `c8f2a5d` (2026-10-11):** Documentación técnica en [`BD/docs/arquitectura_motor_vision.md`](../../../BD/docs/arquitectura_motor_vision.md), [`BD/docs/documentacion_base_de_datos.md`](../../../BD/docs/documentacion_base_de_datos.md) y [`BD/docs/modelo_relacional.md`](../../../BD/docs/modelo_relacional.md).

#### B. Repositorio `C:\GEST.PROY.TI\Software\VIGIA_Vision_Systems` `[VERIFICADO EN REPOSITORIO / GIT]`
| Commit y Fecha | Archivos Creados / Modificados | Propósito Verificado |
| :--- | :--- | :--- |
| **`ae4148d`**<br>*(2026-10-27)* | - `Docs/fase_1/DOC-01_modelos_dominio.md`<br>- `Docs/fase_1/DOC-02_auditoria_esquema_bd.md`<br>- `Docs/fase_1/DOC-03_asignacion_validacion_posiciones.md`<br>- `Docs/fase_1/DOC-04_contratos_entre_modulos.md`<br>- `Docs/fase_1/DOC-05_plan_pruebas_unitarias.md`<br>- `Docs/GEST_PROY_SOFT/11_Diagrama_de_flujo/DF-01..DF-10_VIGIA.drawio.svg` y `README.md`<br>- `VIGIA_Core/domain/__init__.py`<br>- `VIGIA_Core/domain/vision_result.py`<br>- `VIGIA_Core/domain/access_decision.py` | Formalización de especificaciones técnicas de Fase 1, diagramas de flujo y contratos inmutables de dominio en `VIGIA_Core`. |
| **`92f4d78`** y **`4105805`**<br>*(2026-10-28)* | - `VIGIA_Core/repository/__init__.py`<br>- `VIGIA_Core/repository/detection_repository.py`<br>- `VIGIA_Vision/__init__.py`<br>- `VIGIA_Vision/config/__init__.py`<br>- `VIGIA_Vision/config/topology_validator.py`<br>- `tests/unit/test_domain_models.py`<br>- `tests/unit/test_detection_repository.py`<br>- `tests/unit/test_topology_validator.py`<br>- `tests/unit/test_camera.py`<br>- `tests/unit/test_vision_pipeline.py`<br>- `Docs/GEST_PROY_SOFT/12_Diagrama_de_casos_de_uso/DCU-01..02`<br>- `Docs/GEST_PROY_SOFT/13_Diagramas_de_bloques/DB-01..03` | Implementación del repositorio de detecciones (`IDetectionRepository`, `DetectionInsertDTO`, `PsycopgDetectionRepository`), del validador topológico (`TopologyValidator`), diagramas de bloques/CU y primeras suites unitarias. |

### 2.2. Decisiones Técnicas y Justificación

| ID | Decisión Técnica | Justificación |
| :---: | :--- | :--- |
| **`DT00-01`** | **Prohibición de usar `VR_Semaforo` como motor de producción o dependencia** | `VR_Semaforo` es un prototipo experimental de semáforo inteligente que acopla Flask, captura global, inferencia YOLO y control serial de Arduino (`VR_Semaforo/database.py` tiene `0 bytes` y no persiste en PostgreSQL). El motor nuevo debe residir íntegramente en `VIGIA_Vision/`. |
| **`DT00-02`** | **Protección de `VisionResult` y uso de un sobre inmutable (`VisionObservationEnvelope`)** | `VisionResult` (`VIGIA_Core/domain/vision_result.py`) es un contrato congelado que no contiene `id_camara`, `id_area_vision`, cajas delimitadoras ni rutas de evidencia. En lugar de romper el contrato, se diseñó un sobre inmutable en `VIGIA_Vision` que envuelve `VisionResult` intacto junto con el contexto de cámara, área, métricas y rutas de evidencia. |
| **`DT00-03`** | **Mapeo explícito `AUTOBUS -> OTRO` antes de `DetectionInsertDTO`** | `VisionResult` permite `vehicle_type_pred = 'AUTOBUS'`, pero el `CHECK (ck_deteccion_tipo_vehiculo)` de `V001__baseline_schema.sql` solo acepta `('AUTOMOVIL', 'CAMIONETA', 'MOTOCICLETA', 'CAMION', 'OTRO')`. Se definió usar `map_tipo_vehiculo_ddl_v1()` en el coordinador antes de construir `DetectionInsertDTO`. |
| **`DT00-04`** | **Validación *fail-fast* de topología operativa (Reglas R1–R8 de `DOC-03`)** | El esquema SQL permite relación `1:N` entre `camara` y `area_vision`, pero la operación de caseta V1 exige exactamente 2 cámaras activas (`CAM-ENTRADA` y `CAM-SALIDA`) y 2 áreas activas (`ENTRADA`/`ACCESO` y `SALIDA`). `TopologyValidator` bloquea el arranque antes de abrir cualquier cámara si la topología es inválida. |
| **`DT00-05`** | **Plan de implementación incremental en 4 etapas para `VIGIA_Vision`** | Etapa 1: Configuración, adaptador SQL de topología, captura pull/push móvil, ROI, evidencias y coordinador base. Etapa 2: Detector vehicular YOLO (`IVehicleDetector`). Etapa 3: Seguimiento temporal y conteo acumulado de vehículos únicos. Etapa 4: Puerto y adaptador de reconocimiento de matrículas (OCR/LPR). |

### 2.3. Pruebas y Verificaciones Realizadas en el Diagnóstico
- **Estado de las pruebas al cierre del commit `4105805` `[REPORTADO POR AGENTE / SESIÓN]`:**
  - Existían 5 archivos en `tests/unit/` (`test_domain_models.py`, `test_detection_repository.py`, `test_topology_validator.py`, `test_camera.py` y `test_vision_pipeline.py`) con un total de **75 pruebas unitarias**.
  - Sin embargo, 3 de esos archivos (`test_camera.py`, `test_topology_validator.py` y `test_vision_pipeline.py`) importaban directamente `VR_Semaforo/vision/` (`vision.camera`, `vision.service`, `vision.pipeline`), lo que exigía desacoplarlos en `SPRINT-01`.

---

## 3. Validación y Cierre

### 3.1. Evaluación de Criterios de Aceptación
| Criterio | Estado | Evidencia |
| :---: | :---: | :--- |
| **CA00-01** | `CUMPLIDO` | `[VERIFICADO EN REPOSITORIO / GIT]` Migraciones `V000`–`V003` en `C:\GEST.PROY.TI\Software\BD\migrations\`. |
| **CA00-02** | `CUMPLIDO` | `[VERIFICADO EN REPOSITORIO / GIT]` Archivos `vision_result.py`, `access_decision.py`, `detection_repository.py` y `topology_validator.py` en commits `ae4148d` y `92f4d78`. |
| **CA00-03** | `CUMPLIDO` | `[VERIFICADO EN REPOSITORIO / GIT]` Módulos `VIGIA_API`, `VIGIA_Automation`, `VIGIA_Dashboard` y `VIGIA_IoT` verificados como carpetas con solo `README.md`. |
| **CA00-04** | `CUMPLIDO` | `[REPORTADO POR AGENTE / SESIÓN]` Diseño arquitectónico del motor propio `VIGIA_Vision` aprobado como base para `SPRINT-01`. |

### 3.2. Limitaciones Conocidas y Pendientes Transferidos a `SPRINT-01`
1. `VIGIA_Vision/` solo contaba con `config/topology_validator.py`; carecía de submódulos propios de captura (`capture/`), detección/ROI (`detection/`) y ejecución/evidencias (`runtime/`).
2. Las pruebas `test_camera.py`, `test_topology_validator.py` y `test_vision_pipeline.py` dependían de `VR_Semaforo`.
3. Discrepancias documentales abiertas (`DISC-01` a `DISC-06` registradas en [`Docs/gestion_sprints/README.md`](./README.md)).

### 3.3. Decisión de Cierre y Continuidad
- **Dictamen:** `CERRADO` como línea base de diagnóstico y diseño técnico, habilitando la ejecución de `SPRINT-01` (implementación de la Etapa 1 del motor propio `VIGIA_Vision`).
