# DOC-05. Plan de Pruebas Unitarias y de Integración

## 1. Control Documental
* **Proyecto:** VIGÍA Vision Systems
* **Subsistema:** Calidad y Verificación (`tests/`, `VIGIA_Vision`, `VIGIA_Core`)
* **Documento:** DOC-05 — Plan de Pruebas Unitarias y de Integración (Estrategia de Verificación V1)
* **Fase:** Fase 1 — Especificación Formal y Plan de Calidad
* **Estado:** Propuesta Técnica de Plan de Pruebas (Pendiente de Aprobación Técnica Final)
* **Versión:** 1.0.0
* **Fecha:** 27 de octubre de 2026
* **Autor:** Ingeniero Sénior de QA & Especialista en Pruebas de Software

---

## 2. Propósito y Alcance

### 2.1. Propósito
Establecer la estrategia formal, los casos de prueba verificables, las herramientas y las precondiciones necesarias para validar rigurosamente la calidad de software de los componentes de la Versión 1 (V1) de VIGÍA Vision Systems. 

El plan asegura que cada modelo de dominio, validación de topología, invariante técnica y contrato de persistencia relacional definido en los documentos `DOC-01`, `DOC-02`, `DOC-03` y `DOC-04` cuente con una batería de pruebas objetivas que puedan automatizarse y ejecutarse de manera determinista.

### 2.2. Alcance
* **Dentro del Alcance de V1:**
  * Pruebas unitarias de invariantes semánticas del contrato canónico inmutable `VisionResult` de `VIGIA_Core`.
  * Pruebas unitarias del validador de reglas funcionales de topología operativa (`TopologyValidator` bajo las 8 reglas de `DOC-03`).
  * Pruebas de integración relacional contra las tablas `camara`, `area_vision` y `deteccion` en PostgreSQL (`V001__baseline_schema.sql`).
  * Pruebas de manejo de errores técnicos (desconexión de streams, excepciones de IA y fallos de persistencia de archivos/base de datos).
  * Pruebas de extremo a extremo (E2E) simuladas mediante fixtures de video e inyección de datos.
* **Fuera del Alcance de V1:**
  * Pruebas de estrés de concurrencia masiva distribuida (V1 opera en caseta con dos cámaras físicas en flujo síncrono).
  * Pruebas físicas destructivas con barreras vehiculares reales o microcontroladores físicos (se emulan con mocks/stubs conforme al requisito RNF-03).
  * Pruebas de clientes WebSocket de visualización externa (reservadas para la Fase 6 en `VIGIA_API`).

---

## 3. Estado Real de Verificabilidad de Componentes

Para evitar atribuir madurez de prueba a componentes no construidos, se presenta la clasificación del estado real de verificabilidad:

| Componente / Módulo | Estado de Verificabilidad | Justificación y Evidencia en Repositorio | Estrategia de Prueba Aplicable |
| :--- | :---: | :--- | :--- |
| **`VisionResult` (`VIGIA_Core.domain`)** | **Implementado y Susceptible de Prueba** | [HECHO VERIFICADO] Código completo en `VIGIA_Core/domain/vision_result.py` con validaciones activas en `__post_init__`. | Pruebas unitarias directas automatizadas con `pytest`. |
| **Esquema Relacional PostgreSQL** | **Implementado y Susceptible de Prueba** | [HECHO VERIFICADO] Migraciones DDL existentes en `BD/migrations/V000` a `V003`. PostgreSQL 16 desplegable en local/Docker. | Pruebas de integración relacional contra base de datos real o de pruebas. |
| **Inferencia YOLOv11 (`VR_Semaforo`)** | **Implementado, Pendiente de Verificación Modular** | [HECHO VERIFICADO] Código funcional en `VR_Semaforo/vision/processor.py`. Requiere GPU/CPU con PyTorch y modelo `yolo11n.pt`. | Pruebas de integración con fixtures de imágenes sintéticas y casos límite. |
| **`TopologyValidator`** | **Propuesto y Todavía No Implementado** | [HECHO VERIFICADO] Especificado formalmente en `DOC-03`. En el repositorio aún no existe código implementado en `VIGIA_Vision`. | Pruebas unitarias con mocks de base de datos y pruebas de integración con PostgreSQL. |
| **`DetectionRepository`** | **Propuesto y Todavía No Implementado** | [HECHO VERIFICADO] Especificado en `DOC-04`. En `VR_Semaforo/database.py` el archivo está vacío (0 bytes). | Pruebas de integración relacional de sentencias `INSERT` y captura de excepciones. |
| **Normalización de Matrículas** | **Bloqueado por Decisión Técnica Pendiente** | [HECHO VERIFICADO] Pendiente de aprobar formalmente los formatos de matrícula admitidos y la política de sanitización segura. | Pruebas parametrizadas una vez formalizada la política en DOC-04. |
| **Mapeo `AUTOBUS` vs. `OTRO`** | **Bloqueado por Decisión Técnica Pendiente** | [HECHO VERIFICADO] Pendiente de resolver colegiadamente entre mapeo en aplicación o migración DDL V004. | Pruebas de inserción condicionadas a la resolución de la alternativa elegida. |

---

## 4. Estrategia de Pruebas

Conforme al estándar de testing y disciplina técnica de VIGÍA (`Docs/04_estandares_de_desarrollo.md` y `tests/README.md`), la estrategia se articula en tres niveles:

### 4.1. Pruebas Unitarias (`tests/unit/`)
* **Objetivo:** Verificar la lógica de negocio pura, invariantes semánticas y algoritmos de validación en milisegundos, sin depender de red, disco ni bases de datos activas.
* **Herramientas:** `pytest`, mocks de la biblioteca estándar (`unittest.mock`).
* **Áreas Evaluadas:**
  * Invariantes de inicialización de `VisionResult`.
  * Reglas de validación geométrica de coordenadas ROI ($x_{min} < x_{max}$, etc.).
  * Taxonomía y serialización de errores técnicos (`TopologyValidationError`).
  * Evaluación determinista de la topología mediante repositorios simulados (*mocks*).

### 4.2. Pruebas de Integración (`tests/integration/`)
* **Objetivo:** Verificar la interacción real entre el código Python, el motor relacional PostgreSQL y el sistema de archivos local.
* **Precondición:** Instancia de PostgreSQL con migraciones `V000`–`V003` aplicadas (ej. en contenedor Docker de pruebas o base de datos de test dedicada).
* **Áreas Evaluadas:**
  * Consultas SQL reales sobre `camara` y `area_vision`.
  * Cumplimiento de restricciones DDL (`ck_deteccion_placa`, `ck_deteccion_tipo_vehiculo`, `ck_deteccion_evidencia`).
  * Comprobación del comportamiento ante fallos parciales (escritura de foto fallida vs. fallo de inserción SQL).

### 4.3. Pruebas de Extremo a Extremo (`tests/e2e/`)
* **Objetivo:** Validar el ciclo operativo completo desde el arranque del servicio hasta la emisión del resultado canónico y la persistencia de la detección.
* **Alineación con Requisitos:** Conforme a **RNF-03 (Testeabilidad sin Hardware Físico)** en `Docs/09_especificacion_de_requisitos.md`, las pruebas E2E no exigirán cámaras físicas ni vehículos reales conectados. Se utilizarán **archivos de video pregrabados e imágenes estáticas predefinidas en `tests/fixtures/`**.
* **Flujo Evaluado:** Arranque $\to$ Validación de topología $\to$ Lectura de fixture $\to$ Inferencia IA $\to$ Emisión de `VisionResult` $\to$ Guardado en disco $\to$ `INSERT` en PostgreSQL.

---

## 5. Batería de Pruebas Unitarias del Dominio (`VisionResult`)

*Ubicación de Implementación:* `tests/unit/test_vision_result.py`  
*Referencia de Código:* [`VIGIA_Core/domain/vision_result.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Core/domain/vision_result.py)

| ID Caso | Nombre del Caso de Prueba | Entrada de Prueba | Resultado Esperado | Fundamento / Invariante |
| :---: | :--- | :--- | :--- | :--- |
| **PU-VR-01** | Resultado Válido con Vehículo y Placa | `status=VEHICLE_DETECTED_PLATE_READ`, `vehicle_detected=True`, `vehicle_confidence=0.92`, `plate_located=True`, `plate_text="ABC1234"`, `plate_confidence=0.88` | Instanciación exitosa. Objeto inmutable congelado. | Invariantes cumplidas en rango $[0, 1]$. |
| **PU-VR-02** | Rechazo de Confianza Vehicular Negativa | `vehicle_confidence=-0.01` | Lanza `ValueError("vehicle_confidence=-0.01 fuera del rango [0.0, 1.0]")` | `__post_init__` líneas 116–123. |
| **PU-VR-03** | Rechazo de Confianza Vehicular Mayor a 1.0 | `vehicle_confidence=1.05` | Lanza `ValueError("vehicle_confidence=1.05 fuera del rango [0.0, 1.0]")` | `__post_init__` líneas 116–123. |
| **PU-VR-04** | Rechazo de Confianza OCR Negativa | `plate_confidence=-0.1` | Lanza `ValueError("plate_confidence=-0.1 fuera del rango [0.0, 1.0]")` | `__post_init__` líneas 116–123. |
| **PU-VR-05** | Rechazo de Confianza OCR Mayor a 1.0 | `plate_confidence=1.01` | Lanza `ValueError("plate_confidence=1.01 fuera del rango [0.0, 1.0]")` | `__post_init__` líneas 116–123. |
| **PU-VR-06** | Rechazo de Placa sin Confianza | `plate_text="XYZ789"`, `plate_confidence=None` | Lanza `ValueError("plate_text presente pero plate_confidence es None")` | `__post_init__` líneas 110–113. |
| **PU-VR-07** | Rechazo de Detección en Error de Cámara | `status=CAMERA_ERROR`, `vehicle_detected=True` | Lanza `ValueError("status=VisionStatus.CAMERA_ERROR no puede tener vehicle_detected=True")` | `__post_init__` líneas 103–107. |
| **PU-VR-08** | Rechazo de Detección en Error de Visión | `status=VISION_ERROR`, `vehicle_detected=True` | Lanza `ValueError("status=VisionStatus.VISION_ERROR no puede tener vehicle_detected=True")` | `__post_init__` líneas 103–107. |
| **PU-VR-09** | Evaluación de Métodos Auxiliares | `VisionResult` con `CAMERA_ERROR` y otro con `VEHICLE_DETECTED_PLATE_UNREADABLE` | `res1.is_technical_error == True`; `res2.requires_guard_review == True`; `res2.has_readable_plate == False`. | Métodos inspectores (L129–145). |

---

## 6. Batería de Pruebas de Validación de Topología (`DOC-03`)

*Ubicación de Implementación:* `tests/unit/test_topology_validator.py`  
*Referencia de Especificación:* [`Docs/fase_1/DOC-03_asignacion_validacion_posiciones.md`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_1/DOC-03_asignacion_validacion_posiciones.md)

| ID Caso | Nombre de la Prueba | Mock de Entrada (Cámaras y Áreas) | Resultado Esperado | Regla Validada |
| :---: | :--- | :--- | :--- | :---: |
| **PU-TOP-01** | Topología Nominal V1 Válida | 2 cámaras (`CAM-ENTRADA`, `CAM-SALIDA`, ambas `activa=True`), 2 áreas asociadas (`ENTRADA` y `SALIDA`, ambas `activa=True`). | `is_valid == True`, retorna `OperationalTopologyDTO`. | R1, R2, R3, R4, R5, R6, R7 |
| **PU-TOP-02** | Cámara Entrada Faltante | Solo registrada `CAM-SALIDA`. | `is_valid == False`, `error_code == "ERR_CAM_ENTRADA_FALTANTE"`. | R1 |
| **PU-TOP-03** | Cámara Salida Faltante | Solo registrada `CAM-ENTRADA`. | `is_valid == False`, `error_code == "ERR_CAM_SALIDA_FALTANTE"`. | R2 |
| **PU-TOP-04** | Cámara Operativa Inactiva | `CAM-ENTRADA` tiene `activa = False`. | `is_valid == False`, `error_code == "ERR_CAM_INACTIVA"`. | R1 |
| **PU-TOP-05** | Total de Áreas Insuficiente ($N=1$) | Solo 1 área activa en todo el sistema. | `is_valid == False`, `error_code == "ERR_AREAS_TOTAL_INVALIDO"`. | R3 |
| **PU-TOP-06** | Total de Áreas Excesivo ($N=3$) | 3 áreas activas registradas en la base de datos. | `is_valid == False`, `error_code == "ERR_AREAS_TOTAL_INVALIDO"`. | R3 |
| **PU-TOP-07** | Áreas Huérfanas de Cámara | `CAM-ENTRADA` posee 2 áreas activas; `CAM-SALIDA` tiene 0. | `is_valid == False`, `error_code == "ERR_ASOCIACION_AREA_CAMARA"`. | R4 |
| **PU-TOP-08** | Movimientos Invertidos | Área de `CAM-ENTRADA` es `SALIDA`; área de `CAM-SALIDA` es `ENTRADA`. | `is_valid == False`, `error_code == "ERR_MOVIMIENTO_INVERTIDO"`. | R5, R6 |
| **PU-TOP-09** | Coordenadas ROI Degeneradas | Área de Entrada con $x_{min} = 0.400$, $x_{max} = 0.401$ (área útil insignificante). | `is_valid == False`, `error_code == "ERR_ROI_DEGENERADA"`. | R7 |
| **PU-TOP-10** | Error de Conexión a Base de Datos | `ConfigRepository` lanza excepción de timeout o fallo de red. | `is_valid == False`, `error_code == "ERR_BD_CONEXION"`. | R8 |

---

## 7. Batería de Pruebas de Integración Relacional (PostgreSQL)

*Ubicación de Implementación:* `tests/integration/test_database_constraints.py`  
*Referencia de DDL:* [`BD/migrations/V001__baseline_schema.sql`](file:///c:/GEST.PROY.TI/Software/BD/migrations/V001__baseline_schema.sql)  
*Precondición:* Base de datos PostgreSQL con migraciones `V000`–`V003` aplicadas.

| ID Caso | Nombre de la Prueba | Operación SQL Ejecutada | Resultado Esperado | Restricción DDL Validada |
| :---: | :--- | :--- | :--- | :--- |
| **PI-BD-01** | Inserción Válida de Detección | `INSERT INTO deteccion` con placa `"ABC1234"`, confianzas válidas, `tipo='AUTOMOVIL'`, ruta válida. | Inserción exitosa. Se genera `id_deteccion UUID`. | Tabla `deteccion` completa. |
| **PI-BD-02** | Detección sin Placa (Permitida) | `INSERT INTO deteccion` con `placa_detectada = NULL`, `confianza_placa = NULL`. | Inserción exitosa. Placa opcional aceptada. | `ck_deteccion_placa`. |
| **PI-BD-03** | Rechazo de Placa con Guion | `INSERT INTO deteccion (..., placa_detectada='ABC-123')` | Falla con violación de `ck_deteccion_placa` (`!~ '[[:space:]-]'`). | `ck_deteccion_placa` (L368). |
| **PI-BD-04** | Rechazo de Placa con Espacio | `INSERT INTO deteccion (..., placa_detectada='ABC 123')` | Falla con violación de `ck_deteccion_placa`. | `ck_deteccion_placa` (L368). |
| **PI-BD-05** | Rechazo de Placa en Minúsculas | `INSERT INTO deteccion (..., placa_detectada='abc1234')` | Falla con violación de `ck_deteccion_placa` (`UPPER(...)`). | `ck_deteccion_placa` (L367). |
| **PI-BD-06** | Rechazo de Confianza de Placa Inválida | `INSERT INTO deteccion (..., confianza_placa=1.2)` | Falla con violación de `ck_deteccion_confianza_placa`. | `ck_deteccion_confianza_placa` (L375). |
| **PI-BD-07** | Rechazo de Confianza Vehicular Inválida | `INSERT INTO deteccion (..., confianza_vehiculo=-0.1)` | Falla con violación de `ck_deteccion_confianza_vehiculo`. | `ck_deteccion_confianza_vehiculo` (L380). |
| **PI-BD-08** | Inserción con Tipo de Vehículo `'OTRO'` | `INSERT INTO deteccion (..., tipo_vehiculo_pred='OTRO')` | Inserción exitosa. Valor aceptado por el catálogo SQL. | `ck_deteccion_tipo_vehiculo` (L390). |
| **PI-BD-09** | Rechazo de Tipo de Vehículo `'AUTOBUS'` | `INSERT INTO deteccion (..., tipo_vehiculo_pred='AUTOBUS')` | Falla con violación de `ck_deteccion_tipo_vehiculo`. | Demuestra discrepancia de catálogo. |
| **PI-BD-10** | Rechazo de Ruta de Evidencia Vacía | `INSERT INTO deteccion (..., ruta_evidencia_foto='   ')` | Falla con violación de `ck_deteccion_evidencia` (`BTRIM <> ''`). | `ck_deteccion_evidencia` (L397). |
| **PI-BD-11** | Inserción con Ruta de Evidencia `NULL` | `INSERT INTO deteccion (..., ruta_evidencia_foto=NULL)` | Inserción exitosa. Se admite ausencia de evidencia física. | `ck_deteccion_evidencia` (L395). |
| **PI-BD-12** | Integridad Referencial de Área | `INSERT INTO deteccion (id_area_vision=uuid_inexistente, ...)` | Falla con violación de clave foránea `fk_deteccion_area_vision`. | Clave foránea (L360–362). |

---

## 8. Batería de Pruebas de Extremo a Extremo (E2E Simulado)

*Ubicación de Implementación:* `tests/e2e/test_vision_pipeline_e2e.py`  
*Entorno:* Sin cámaras físicas (conforme a RNF-03); se emplean imágenes pregrabadas en `tests/fixtures/`.

| ID Caso | Escenario E2E Evaluado | Estímulo / Fixture Inyectado | Comportamiento del Sistema | Resultado Esperado |
| :---: | :--- | :--- | :--- | :--- |
| **PE2E-01** | Flujo Completo: Detección Vehicular y Lectura de Matrícula | Fixture `car_with_plate.jpg` inyectado en el servicio de captura simulado. | Pipeline procesa cuadro $\to$ YOLO detecta auto $\to$ OCR lee matrícula $\to$ Se guarda JPEG en disco $\to$ Se inserta en tabla `deteccion`. | `VisionResult(status=VEHICLE_DETECTED_PLATE_READ)`. Se genera fila en `deteccion` con `ruta_evidencia_foto` válida y placa normalizada. |
| **PE2E-02** | Cuadro Vacío sin Vehículos | Fixture `empty_lane.jpg` (carril despejado sin autos). | Pipeline procesa cuadro $\to$ YOLO no detecta objetos $\to$ Emite resultado a Core. | `VisionResult(status=NO_VEHICLE_DETECTED)`. **No se escribe ningún archivo en disco ni se inserta fila en PostgreSQL**. |
| **PE2E-03** | Vehículo sin Placa Visible | Fixture `car_no_plate.jpg` (vista lejana o sin matrícula frontal). | Pipeline procesa cuadro $\to$ YOLO detecta auto $\to$ OCR no localiza matrícula $\to$ Persiste detección. | `VisionResult(status=VEHICLE_DETECTED_NO_PLATE)`. Se inserta fila en `deteccion` con `placa_detectada = NULL`. |
| **PE2E-04** | Resiliencia ante Fallo de Disco | Fixture válido inyectado con directorio de evidencias sin permisos de escritura (`chmod 555`). | Pipeline detecta fallo de escritura en disco $\to$ Registra error técnico $\to$ Invoca persistencia SQL. | Se inserta la fila en `deteccion` con `ruta_evidencia_foto = NULL`. El servicio no colapsa ni lanza excepciones no controladas. |
| **PE2E-05** | Cámara Desconectada en Runtime | Fuente de captura emula pérdida de conexión (`read_frame` retorna `False, None`). | Componente de captura captura el fallo $\to$ Genera resultado de error técnico hacia Core. | `VisionResult(status=CAMERA_ERROR, vehicle_detected=False)`. No hay llamadas a persistencia. Se reintenta el enlace. |

---

## 9. Criterios de Aceptación del Plan de Pruebas

Para considerar que este plan de pruebas es consistente y se encuentra técnicamente listo para su ejecución futura:
1. **Verificabilidad Completa:** Cada caso de prueba cuenta con una precondición explícita, una entrada estructurada y un resultado unívoco esperado.
2. **Cero Declaraciones Falsas:** Ningún caso de prueba se da por ejecutado o aprobado; se especifican como casos automatizables para la fase de construcción de código.
3. **Desacoplamiento Sensorial (RNF-03):** La totalidad de las pruebas E2E puede ejecutarse en entornos de integración continua (CI) sin requerir hardware de video ni dispositivos mecánicos.
4. **Trazabilidad Total:** Los casos cubren las invariantes de `DOC-01`, las restricciones SQL comprobadas en `DOC-02`, las 8 reglas de topología de `DOC-03` y los contratos de errores y persistencia de `DOC-04`.

---

## 10. Trazabilidad de Fuentes de Información
* **Modelos de Dominio:** [`Docs/fase_1/DOC-01_modelos_dominio.md`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_1/DOC-01_modelos_dominio.md)
* **Auditoría de Esquema SQL:** [`Docs/fase_1/DOC-02_auditoria_esquema_bd.md`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_1/DOC-02_auditoria_esquema_bd.md)
* **Validación de Posiciones:** [`Docs/fase_1/DOC-03_asignacion_validacion_posiciones.md`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_1/DOC-03_asignacion_validacion_posiciones.md)
* **Contratos entre Módulos:** [`Docs/fase_1/DOC-04_contratos_entre_modulos.md`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_1/DOC-04_contratos_entre_modulos.md)
* **Esquema Relacional DDL:** [`BD/migrations/V001__baseline_schema.sql`](file:///c:/GEST.PROY.TI/Software/BD/migrations/V001__baseline_schema.sql)
* **Contrato Canónico de Salida:** [`VIGIA_Core/domain/vision_result.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Core/domain/vision_result.py)
* **Contrato de Decisión de Acceso:** [`VIGIA_Core/domain/access_decision.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Core/domain/access_decision.py)
* **Estructura y Guías de Testing:** [`tests/README.md`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/tests/README.md)
