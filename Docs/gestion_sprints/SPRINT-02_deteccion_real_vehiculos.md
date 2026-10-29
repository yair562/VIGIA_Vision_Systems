# SPRINT-02 — Detección Real de Vehículos (Etapa 2 — Propuesta de Alcance Futuro)

## Control Documental
- **Identificador:** `SPRINT-02`
- **Nombre del Sprint:** Integración del Detector Vehicular Real (Etapa 2 de `VIGIA_Vision`) y Validación de Integración con PostgreSQL
- **Estado:** `PLANIFICADO` *(No iniciado — Sin código implementado)*
- **Fecha / Periodo:** No disponible *(pendiente de programación y autorización tras validar y cerrar `SPRINT-01`)*
- **Commit Base (`HEAD` al iniciar):** Pendiente de confirmación del commit de cierre de `SPRINT-01`
- **Hitos Relacionados:** Capacidad 1 — Percibir ([`03_roadmap.md`](../03_roadmap.md)) y Hito `H3` ([`07_cronograma_maestro.md`](../07_cronograma_maestro.md))

> **Advertencia de Rigor Documental:**
> Este expediente registra **exclusivamente trabajo futuro candidato** derivado del diseño arquitectónico de `VIGIA_Vision` y de los pendientes abiertos al concluir `SPRINT-01`.
> **Ningún módulo, adaptador YOLO ni prueba correspondiente a este sprint ha sido iniciado ni implementado.**

---

## 1. Planificación Preliminar (Alcance Candidato)

### 1.1. Objetivo y Justificación Propuestos
- **Objetivo candidato:** Sustituir el detector nulo por omisión (`NullVehicleDetector`) por una implementación real del puerto [`IVehicleDetector`](../../VIGIA_Vision/runtime/coordinator.py) en `VIGIA_Vision/detection/` basada en inferencia vehicular (familia YOLO / Ultralytics), y completar la validación de integración en vivo contra el contenedor PostgreSQL `vigia-db` (puerto `5433`) que quedó pendiente en `SPRINT-01`.
- **Justificación:** La Etapa 1 dejó lista toda la tubería síncrona (validación topológica, captura *pull/push*, proyección de ROI, sobre `VisionObservationEnvelope`, almacenamiento de evidencias y persistencia SQL), pero requiere un adaptador `IVehicleDetector` real para detectar y clasificar vehículos (`car`, `motorcycle`, `bus`, `truck`) sobre fotogramas reales o *fixtures* de imagen/video.

### 1.2. Precondiciones ( Estado Inicial Requerido Antes de Iniciar `SPRINT-02` )
1. Revisión y confirmación en Git (`commit`) de los 12 archivos creados y 6 archivos modificados durante [`SPRINT-01`](./SPRINT-01_base_modular_motor_vision.md).
2. Arranque del servicio Docker Desktop en el sistema anfitrión y verificación del contenedor `vigia-db` en `127.0.0.1:5433`.
3. Confirmación sobre el manejo de la ruta de evidencia anotada (`*_annot.jpg`) frente a la columna única `deteccion.ruta_evidencia_foto` (`DISC-05`).

### 1.3. Alcance Candidato Identificado
- **Candidato a incluir (sujeto a autorización antes de implementar):**
  1. Validación de integración real (no destructiva / con `ROLLBACK`) de [`PsycopgTopologyConfigRepository`](../../VIGIA_Vision/config/psycopg_topology_repository.py) y [`PsycopgDetectionRepository`](../../VIGIA_Core/repository/detection_repository.py) contra `vigia-db` (`127.0.0.1:5433`).
  2. Implementación de un adaptador concreto de [`IVehicleDetector`](../../VIGIA_Vision/runtime/coordinator.py) (propuesto como `UltralyticsVehicleDetector` en `VIGIA_Vision/detection/yolo_detector.py`) con:
     - Carga diferida (*lazy loading*) de pesos `.pt` para no penalizar la importación del paquete ni requerir GPU en pruebas unitarias.
     - Filtrado exclusivo de las clases vehiculares COCO aprobadas (`{2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck'}`).
     - Conversión de tensores/cajas a instancias inmutables de [`RawVehicleDetection`](../../VIGIA_Vision/detection/models.py) y [`BoundingBox`](../../VIGIA_Vision/detection/models.py).
     - Manejo de errores de carga o inferencia para que [`VisionEngineCoordinator`](../../VIGIA_Vision/runtime/coordinator.py) emita `VisionStatus.VISION_ERROR` sin abortar el proceso ni afectar a la otra cámara.
  3. Pruebas unitarias del adaptador de detección con resultados simulados (sin requerir GPU ni pesos pesados en la suite unitaria rápida) y prueba con *fixtures* de imagen controlada.
- **Candidato a mantener excluido en `SPRINT-02` (reservado para etapas posteriores):**
  - Seguimiento temporal multi-objeto (*tracking* IoU / *cooldown*) y conteo acumulado de vehículos únicos (previstos para una Etapa 3 posterior).
  - Reconocimiento óptico de matrículas (OCR / LPR, previsto para una Etapa 4 posterior).
  - Modificación de `VR_Semaforo` o importación de cualquiera de sus módulos.

### 1.4. Tareas Candidatas
| ID Tarea | Descripción Propuesta | Estado |
| :---: | :--- | :---: |
| `T02-01` | Ejecutar verificación de integración en vivo contra `vigia-db` (puerto `5433`) para lectura de topología e inserción revertida con `ROLLBACK`. | `NO INICIADA` |
| `T02-02` | Implementar adaptador concreto de `IVehicleDetector` en `VIGIA_Vision/detection/` sin efectos colaterales en tiempo de importación. | `NO INICIADA` |
| `T02-03` | Crear pruebas unitarias del detector vehicular con dobles de inferencia y pruebas reproducibles con *fixtures* de imagen. | `NO INICIADA` |
| `T02-04` | Resolver o documentar formalmente en `DOC-01`/`DOC-04` la política sobre `evidence_annotated_rel_path` (`*_annot.jpg`). | `NO INICIADA` |

### 1.5. Dependencias y Riesgos Identificados
- **Disponibilidad de pesos `.pt` y entorno `torch`/`ultralytics`:** Aunque `torch` y `ultralytics` están presentes en el intérprete base Python 3.11 del sistema, el motor debe poder ejecutarse en pruebas unitarias sin depender de un archivo `.pt` externo ni de GPU CUDA.
- **Disponibilidad del demonio Docker Desktop:** Necesario para cerrar la verificación de integración con PostgreSQL (`vigia-db`).

### 1.6. Criterios de Aceptación Preliminares
- **CA02-01:** `UltralyticsVehicleDetector` implementa `IVehicleDetector` sin importar `ultralytics` ni cargar pesos en `__init__` o al importar el módulo (carga diferida o inyección de modelo).
- **CA02-02:** Dada una imagen con un vehículo dentro del ROI y confianza $\ge 0.70$, `VisionEngineCoordinator` produce `VisionStatus.VALID_DETECTION`, guarda las evidencias y construye `DetectionInsertDTO` válido.
- **CA02-03:** Cualquier excepción del modelo de inferencia es capturada y traducida a `VisionStatus.VISION_ERROR` sin detener el procesamiento de la otra cámara.
- **CA02-04:** Verificación de lectura de `camara` y `area_vision` contra `vigia-db` (puerto `5433`) ejecutada y documentada con evidencia verificable.

---

## 2. Ejecución

- **Estado:** `No aplica` *(Sprint no iniciado).*
- **Archivos creados / modificados / eliminados:** `Ninguno`.
- **Pruebas ejecutadas:** `Ninguna`.

---

## 3. Validación y Cierre

- **Estado:** `No aplica` *(Sprint en estado `PLANIFICADO`).*
