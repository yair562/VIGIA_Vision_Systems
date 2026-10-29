# Gestión y Trazabilidad Documental por Sprints — VIGÍA Vision Systems

Bienvenido al registro operativo de evolución por sprints de **VIGÍA Vision Systems**.

Este directorio establece un mecanismo único, verificable y ligero para rastrear qué se planificó construir en cada iteración técnica, cuál era el estado real del repositorio al iniciar, qué archivos fueron creados o modificados, qué decisiones técnicas se adoptaron, qué pruebas se ejecutaron (distinguiendo con rigor entre resultados **reportados** y **verificados**) y qué riesgos o pendientes permanecen abiertos.

---

## 1. Propósito del Sistema Documental de Sprints

La documentación de este directorio cumple el tercer nivel de la jerarquía definida en [`05_marco_de_planificacion_y_ejecucion.md`](../05_marco_de_planificacion_y_ejecucion.md):

1. **Nivel Estratégico — Roadmap ([`03_roadmap.md`](../03_roadmap.md)):** Define qué capacidades físicas debe adquirir VIGÍA y en qué orden conceptual.
2. **Nivel Temporal — Cronograma Maestro ([`07_cronograma_maestro.md`](../07_cronograma_maestro.md)):** Define los hitos temporales (`H1`–`H6`) replanificados el 13 de octubre de 2026 hacia la entrega del 16 de diciembre de 2026.
3. **Nivel Operativo y de Evidencia — Expedientes de Sprint (`Docs/gestion_sprints/`):** Registra la ejecución real de ingeniería sobre el código, la base de datos y las pruebas, evitando depender de la memoria de conversaciones o de informes aislados.

> **Principio de No Duplicación:**
> Los expedientes de sprint **no sustituyen ni copian** los documentos de arquitectura, contratos o esquemas de base de datos. Funcionan como un **índice de evolución y auditoría** que enlaza a las fuentes técnicas canónicas.

---

## 2. Decisión de Estructura: Expediente Único por Sprint

Para mantener la trazabilidad sin fragmentar el contexto ni duplicar metadatos, se adopta la modalidad de **un único expediente Markdown por sprint** (`SPRINT-XX_<descriptor>.md`), acompañado de este índice general y de una plantilla base:

```text
Docs/gestion_sprints/
├── README.md                                        # Índice general, normas de evidencia y estado global
├── PLANTILLA_SPRINT.md                              # Plantilla canónica para abrir nuevos sprints
├── SPRINT-00_diagnostico_y_definicion_tecnica.md    # Diagnóstico, contratos Fase 1 y diseño del motor propio
├── SPRINT-01_base_modular_motor_vision.md           # Etapa 1 de VIGIA_Vision (captura, ROI, evidencias, coordinador)
└── SPRINT-02_deteccion_real_vehiculos.md            # Trabajo futuro candidato (Etapa 2: detector YOLO e integración BD)
```

### Justificación frente a tres archivos separados por sprint
- **Cohesión de lectura:** Permite auditar en un solo archivo la relación directa entre *objetivo planificado $\to$ archivos modificados $\to$ pruebas ejecutadas $\to$ criterios de aceptación cumplidos o pendientes*.
- **Cero duplicación de contexto:** Evita repetir listas de archivos, identificadores, fechas y riesgos en tres archivos distintos (`planificacion.md`, `ejecucion.md`, `cierre.md`).
- **Estructura interna obligatoria:** Cada expediente único contiene invariablemente las tres secciones formales: **1. Planificación**, **2. Ejecución** y **3. Validación y Cierre**.

---

## 3. Convención de Identificación y Nomenclatura

- **Identificador de sprint:** `SPRINT-XX`, donde `XX` es un número secuencial de dos dígitos (`00`, `01`, `02`, ...).
- **Nombre de archivo:** `SPRINT-XX_<slug_en_snake_case>.md` (en español, sin tildes ni espacios en el nombre de archivo).
- **Nota de armonización histórica:**
  En los documentos de Fase 0 ([`05_marco_de_planificacion_y_ejecucion.md`](../05_marco_de_planificacion_y_ejecucion.md) y [`BASELINE_V1.1.md`](../BASELINE_V1.1.md), fechados en septiembre de 2026) se denominó *"Sprint 0"* a la preparación organizacional de Fase 0 y *"Sprint 1 (14–27 sep 2026)"* a la planificación inicial previa a la replanificación del [`07_cronograma_maestro.md`](../07_cronograma_maestro.md) (13 de octubre de 2026).
  En este registro técnico:
  - **`SPRINT-00`** consolida la fase de diagnóstico, consolidación de base de datos, contratos de Fase 1 (`DOC-01` a `DOC-05`), auditoría técnica y diseño arquitectónico del motor propio.
  - **`SPRINT-01`** corresponde a la implementación de la Etapa 1 del motor propio `VIGIA_Vision`.
  - **`SPRINT-02`** registra como trabajo futuro candidato la Etapa 2 (detección vehicular real con YOLO y pruebas de integración en vivo con PostgreSQL).

---

## 4. Estados Oficiales de un Sprint

Cada sprint debe declarar explícitamente uno de los siguientes estados:

| Estado | Significado Técnico y Documental |
| :--- | :--- |
| **`PLANIFICADO`** | El alcance candidato y los objetivos preliminares están identificados, pero no se ha iniciado la implementación ni existen cambios en el código. |
| **`EN_EJECUCION`** | El desarrollo técnico está activo y en curso; existen tareas o entregables aún en construcción. |
| **`BLOQUEADO`** | El avance está detenido por una incompatibilidad de contratos, una dependencia externa no resuelta o falta de acceso a infraestructura crítica. |
| **`PENDIENTE_DE_VALIDACION`** | Existe código implementado en el árbol de trabajo y/o pruebas unitarias reportadas como exitosas, pero falta validación de integración en el entorno objetivo, revisión humana o confirmación en Git (`commit`). |
| **`CERRADO`** | Todos los criterios de aceptación obligatorios están verificados con evidencia reproducible (unitaria e integración aplicable) y los cambios están confirmados. |
| **`CANCELADO`** | El sprint fue descartado o reemplazado formalmente por una decisión de alcance del Product Owner o de Arquitectura. |

> **Regla de Cierre Estricto:**
> Ningún sprint puede declararse `CERRADO` únicamente porque sus pruebas unitarias con dobles (*mocks/stubs*) hayan pasado si el alcance funcional o la integración con componentes reales (como PostgreSQL o inferencia real) permanece sin verificar.

---

## 5. Clasificación de Certeza y Evidencia (Reportado vs. Verificado)

Para evitar que afirmaciones no comprobadas se conviertan en hechos asumidos, toda tarea, prueba o métrica registrada en un sprint debe calificarse bajo una de las siguientes categorías:

1. **`[VERIFICADO EN REPOSITORIO / GIT]`**
   Hecho comprobado directamente mediante inspección del árbol de archivos en disco, `git status`, `git diff`, `git log` o lectura directa del código fuente y esquemas SQL.
2. **`[REPORTADO POR AGENTE / SESIÓN]`**
   Resultado declarado en un informe de ejecución (por ejemplo, salida de consola de pruebas unitarias o tiempos de ejecución en sesión) cuya existencia en código es consistente, pero que proviene del reporte de ejecución del agente o aún no forma parte de un commit verificado de integración continua.
3. **`[PENDIENTE DE VERIFICAR]`**
   Elemento cuya comprobación empírica no pudo realizarse en el entorno actual (por ejemplo, pruebas contra el contenedor Docker `vigia-db` cuando el demonio Docker Desktop está detenido, o captura con cámaras físicas no conectadas).
4. **`[NO DISPONIBLE]` / `[NO APLICA]`**
   Información histórica que no consta en los commits ni en los documentos del repositorio (por ejemplo, actas o fechas exactas de actividades no registradas en Git), o criterios que no corresponden al alcance del sprint.

### Evidencia mínima exigida para considerar una tarea terminada
- **Tarea documental o de diseño:** Archivo Markdown o diagrama SVG existente en el repositorio o artefacto técnico trazable sin contradicciones no documentadas.
- **Tarea de implementación de código:** Archivos fuente creados/modificados verificables en el árbol de trabajo o en `git log`, respetando los contratos protegidos.
- **Tarea de pruebas unitarias:** Archivo de prueba existente en `tests/unit/`, comando de ejecución reproducible documentado y distinción explícita entre resultado reportado y verificado.
- **Tarea de integración (BD / Hardware / Modelos):** Ejecución verificada contra el servicio o modelo real (o registro explícito como `PENDIENTE_DE_VALIDACION` si solo se probó con dobles).

---

## 6. Procedimiento Operativo para Gestionar Sprints

### 6.1. Cómo abrir y documentar un sprint nuevo
1. Copiar [`PLANTILLA_SPRINT.md`](./PLANTILLA_SPRINT.md) a `SPRINT-XX_<slug>.md`.
2. Completar el bloque **1. Planificación** antes de modificar código, registrando el commit `HEAD` inicial (`git rev-parse --short HEAD`) y el estado de `git status --short`.
3. Añadir la fila correspondiente en la **Tabla Resumen de Sprints** de este `README.md` con estado `PLANIFICADO` o `EN_EJECUCION`.

### 6.2. Cómo registrar la ejecución, incidencias y cambios de alcance
1. Durante o al término del desarrollo, completar el bloque **2. Ejecución** listando cada archivo creado, modificado o eliminado con su ruta relativa al repositorio.
2. Registrar literalmente cualquier fallo o incidencia ocurrida en las primeras corridas de prueba y cómo se resolvió, sin ocultar errores intermedios.
3. Si un requisito no puede cumplirse o se recorta, **no borrarlo de la sección de Planificación**: registrar el cambio de alcance en Ejecución y su estado real en **3. Validación y Cierre**.

### 6.3. Cómo actualizar el índice general
Cada vez que cambie el estado de un sprint (`PLANIFICADO` $\to$ `EN_EJECUCION` $\to$ `PENDIENTE_DE_VALIDACION` $\to$ `CERRADO`), se debe actualizar la sección **8. Índice de Sprints Registrados** de este documento.

---

## 7. Relación con la Documentación Técnica y Discrepancias Conocidas

### 7.1. Mapa de Fuentes Técnicas Enlazadas

| Dominio Documental | Fuente Técnica Canónica | Relación con los Sprints |
| :--- | :--- | :--- |
| **Estructura y Arquitectura General** | [`Docs/01_estructura_del_proyecto.md`](../01_estructura_del_proyecto.md), [`Docs/02_arquitectura_del_sistema.md`](../02_arquitectura_del_sistema.md), [`Docs/BASELINE_V1.1.md`](../BASELINE_V1.1.md) | Delimitan las fronteras entre `VIGIA_Core`, `VIGIA_Vision`, `VIGIA_IoT`, `VIGIA_Automation`, `VIGIA_API` y `VIGIA_Dashboard`. |
| **Roadmap y Cronograma V1** | [`Docs/03_roadmap.md`](../03_roadmap.md), [`Docs/07_cronograma_maestro.md`](../07_cronograma_maestro.md) | Definen las capacidades físicas y los hitos `H1`–`H6` (13 oct – 16 dic 2026). |
| **Especificaciones y Contratos Fase 1** | [`DOC-01`](../fase_1/DOC-01_modelos_dominio.md), [`DOC-02`](../fase_1/DOC-02_auditoria_esquema_bd.md), [`DOC-03`](../fase_1/DOC-03_asignacion_validacion_posiciones.md), [`DOC-04`](../fase_1/DOC-04_contratos_entre_modulos.md), [`DOC-05`](../fase_1/DOC-05_plan_pruebas_unitarias.md) | Especifican `VisionResult`, `AccessDecision`, `TopologyValidator` (reglas R1–R8), `IDetectionRepository` y el plan de pruebas unitarias. |
| **Diagramas de Flujo, CU y Bloques** | [`11_Diagrama_de_flujo/`](../GEST_PROY_SOFT/11_Diagrama_de_flujo/README.md), [`12_Diagrama_de_casos_de_uso/`](../GEST_PROY_SOFT/12_Diagrama_de_casos_de_uso/README.md), [`13_Diagramas_de_bloques/`](../GEST_PROY_SOFT/13_Diagramas_de_bloques/README.md) | Representan visualmente los flujos `DF-01` a `DF-10`, casos de uso `DCU-01..02` y bloques `DB-01..03`. |
| **Base de Datos PostgreSQL** | [`Docs/Base_de_Datos/01_modelo_conceptual_v1.md`](../Base_de_Datos/01_modelo_conceptual_v1.md), [`Docs/BD/Modelo_Logico_BD_VIGIA_V1.md`](../BD/Modelo_Logico_BD_VIGIA_V1.md) y repositorio [`BD/README.md`](../../../BD/README.md) | Documentan el esquema relacional de 15 tablas en PostgreSQL 16+ (`V000`–`V003`, puerto Docker `5433`). |

### 7.2. Registro de Discrepancias Documentales Detectadas

Conforme a la regla de no resolver contradicciones técnicas silenciosamente, se dejan registradas las siguientes discrepancias verificadas entre documentos existentes:

| ID | Discrepancia Detectada | Documentos en Conflicto | Impacto / Estado |
| :--- | :--- | :--- | :--- |
| **DISC-01** | **Motor de BD: SQLite vs. PostgreSQL 16+** | [`Docs/02_arquitectura_del_sistema.md`](../02_arquitectura_del_sistema.md), [`Docs/03_roadmap.md`](../03_roadmap.md) (línea 405) y [`Docs/BASELINE_V1.1.md`](../BASELINE_V1.1.md) (línea 122) mencionan SQLite local; en cambio, [`Docs/07_cronograma_maestro.md`](../07_cronograma_maestro.md), [`DOC-02`](../fase_1/DOC-02_auditoria_esquema_bd.md) y el repositorio [`BD/`](../../../BD/README.md) implementan PostgreSQL 16+ (`V000`–`V003`). | El código real en `VIGIA_Core/repository/detection_repository.py` y `VIGIA_Vision/config/psycopg_topology_repository.py` opera sobre PostgreSQL (`psycopg2`). |
| **DISC-02** | **Declaración de "Fase 0 sin código" en READMEs de módulos** | [`README.md`](../../README.md) (líneas 263–268), [`VIGIA_Core/README.md`](../../VIGIA_Core/README.md) (líneas 35–39), [`VIGIA_Vision/README.md`](../../VIGIA_Vision/README.md) (líneas 33–36) y [`tests/README.md`](../../tests/README.md) (líneas 48–52) afirman que los módulos carecen de código y que se usará `pytest`. | Desactualizado respecto al árbol real: `VIGIA_Core` y `VIGIA_Vision` ya contienen implementación y `tests/unit/` utiliza `unittest` estándar. |
| **DISC-03** | **Catálogo de clases vehiculares (`AUTOBUS` vs. `OTRO`)** | [`VIGIA_Core/domain/vision_result.py`](../../VIGIA_Core/domain/vision_result.py) admite `'AUTOBUS'`, mientras que `ck_deteccion_tipo_vehiculo` en `BD/migrations/V001__baseline_schema.sql` solo admite `('AUTOMOVIL', 'CAMIONETA', 'MOTOCICLETA', 'CAMION', 'OTRO')`. | Documentado en [`DOC-02`](../fase_1/DOC-02_auditoria_esquema_bd.md) y mitigado en capa de repositorio mediante `map_tipo_vehiculo_ddl_v1('AUTOBUS') -> 'OTRO'`. |
| **DISC-04** | **Diagrama `DB-02` refleja el prototipo `VR_Semaforo` como si fuera el motor activo** | [`DB-02_ARQUITECTURA_MOTOR.drawio.svg`](../GEST_PROY_SOFT/13_Diagramas_de_bloques/DB-02_ARQUITECTURA_MOTOR.drawio.svg) y su [`README.md`](../GEST_PROY_SOFT/13_Diagramas_de_bloques/README.md) describen `vision/service.py`, `vision/pipeline.py` y `Tracker IoU + Cooldown` de `VR_Semaforo` como arquitectura actual. | `VR_Semaforo` quedó restringido exclusivamente a referencia técnica experimental; el motor propio se construye en `VIGIA_Vision/`. |
| **DISC-05** | **Doble archivo de evidencia en disco (`_orig.jpg` y `_annot.jpg`) vs. columna única en BD (`ruta_evidencia_foto`)** | [`DOC-01`](../fase_1/DOC-01_modelos_dominio.md) (§3.2) deja abierta la política entre imagen original y anotada; `VIGIA_Vision/runtime/evidence_storage.py` guarda ambas en disco, pero `DetectionInsertDTO` y la tabla `deteccion` solo poseen un campo `ruta_evidencia_foto`. | En `SPRINT-01`, `VisionEngineCoordinator` persiste en BD únicamente la ruta original (`original_rel_path`), quedando la ruta anotada solo en disco y en memoria (`VisionObservationEnvelope`). |
| **DISC-06** | **DDL de `VIGIA_V1_DDL.sql` en `Docs/BD/` vs. migraciones activas en `BD/migrations/`** | [`Docs/BD/VIGIA_V1_DDL.sql`](../BD/VIGIA_V1_DDL.sql) (commit `bab18e7` del 06 oct 2026) es una copia previa al esquema versionado `V000`–`V003` del repositorio [`BD/migrations/`](../../../BD/migrations/README.md) (11 oct 2026). | La fuente de verdad ejecutable para PostgreSQL es `C:\GEST.PROY.TI\Software\BD\migrations\V000..V003`. |

---

## 8. Índice de Sprints Registrados

| ID Sprint | Nombre del Sprint | Expediente | Periodo / Fecha de Referencia | Estado Actual | Resumen de Alcance y Estado |
| :---: | :--- | :--- | :--- | :---: | :--- |
| **`SPRINT-00`** | **Diagnóstico y Definición Técnica** | [`SPRINT-00_diagnostico_y_definicion_tecnica.md`](./SPRINT-00_diagnostico_y_definicion_tecnica.md) | 09 sep – 29 oct 2026 *(reconstrucción retrospectiva)* | **`CERRADO`** *(con observaciones documentales)* | Consolidación de esquemas PostgreSQL (`V000`–`V003`), especificación `DOC-01` a `DOC-05`, contratos base en `VIGIA_Core` y `VIGIA_Vision`, auditoría integral de activos y diseño arquitectónico del motor propio `VIGIA_Vision` independiente de `VR_Semaforo`. |
| **`SPRINT-01`** | **Base Modular del Motor de Visión Artificial (Etapa 1)** | [`SPRINT-01_base_modular_motor_vision.md`](./SPRINT-01_base_modular_motor_vision.md) | 29 oct 2026 | **`PENDIENTE_DE_VALIDACION`** | Creación de 12 archivos y modificación de 6 archivos en `VIGIA_Vision/` y `tests/unit/` (configuración `0.70`, captura pull/push móvil, registro topológico, ROI, evidencia dual, coordinador con `NullVehicleDetector` y desacoplamiento total de `VR_Semaforo`). 93 pruebas unitarias reportadas `OK`; pendiente commit en Git y prueba de integración real contra contenedor `vigia-db`. |
| **`SPRINT-02`** | **Detección Real de Vehículos (Etapa 2 — Candidato)** | [`SPRINT-02_deteccion_real_vehiculos.md`](./SPRINT-02_deteccion_real_vehiculos.md) | Por planificar | **`PLANIFICADO`** *(No iniciado)* | Trabajo futuro candidato: implementación del adaptador `UltralyticsVehicleDetector` (YOLO) bajo el puerto `IVehicleDetector`, pruebas de integración en vivo con `vigia-db` (Docker puerto `5433`) y resolución de pendientes de `SPRINT-01`. |
