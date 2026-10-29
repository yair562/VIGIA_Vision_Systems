# SPRINT-02 — Detección Real de Vehículos (Etapa 2 de VIGIA_Vision)

## Control Documental
- **Identificador:** `SPRINT-02`
- **Nombre del Sprint:** Integración del Detector Vehicular Real YOLO (`VIGIA_Vision`) y Validación de Inferencia en CPU
- **Estado:** `CERRADO`
- **Fecha de Ejecución:** 29 de octubre de 2026
- **Commit Base (`HEAD` al iniciar):** `29b63e3` (`test(vision): validate sprint 01 evidence and persistence`)
- **Hitos Relacionados:** Capacidad 1 — Percibir ([`03_roadmap.md`](../03_roadmap.md)) e Hito `H3` ([`07_cronograma_maestro.md`](../07_cronograma_maestro.md))

---

## 1. Planificación

### 1.1. Objetivo y Justificación
- **Objetivo:** Implementar un detector vehicular real en producción bajo la interfaz inyectable [`IVehicleDetector`](../../VIGIA_Vision/runtime/coordinator.py) del subsistema propio `VIGIA_Vision`, utilizando un modelo YOLO preentrenado optimizado para CPU (`yolo11n.pt` o familia YOLOv8/v11), con carga perezosa (*lazy loading*), filtrado riguroso de clases vehiculares COCO (`car`, `motorcycle`, `bus`, `truck`), validación estricta de fotogramas, pruebas unitarias desacopladas sin dependencias de hardware o red, y validación de inferencia real en CPU.
- **Justificación:** La Etapa 1 implementó la tubería completa del motor de visión (validación topológica fail-fast, fuentes de captura, ROI geométrico, almacenamiento dual de evidencias y persistencia PostgreSQL), pero operaba con `NullVehicleDetector` como marcador provisional. Para completar la capacidad de percepción vehicular sin romper contratos ni acoplarse al prototipo experimental `VR_Semaforo`, se requería una implementación de producción modular, desacoplada y verificable.

### 1.2. Precondiciones
1. Repositorio principal en rama `main` con commit `29b63e3` verificado y árbol de trabajo limpio.
2. Suite base de 98 pruebas unitarias aprobadas al 100%.
3. Entorno virtual Python 3.11 con `ultralytics` (8.4.x), `torch` (+cpu), `opencv-python` y `numpy`.
4. Archivo de pesos ligero (`yolo11n.pt`, 5.4 MB) disponible localmente.

### 1.3. Alcance Delimitado
- **Incluido en SPRINT-02:**
  1. Configuración `.gitignore` para pesos `.pt` y artefactos binarios.
  2. Implementación de `YoloDetectorConfig` inmutable en [`VIGIA_Vision/detection/yolo_detector.py`](../../VIGIA_Vision/detection/yolo_detector.py) con validación estricta de umbrales e hiperparámetros.
  3. Implementación de `YoloVehicleDetector` cumpliendo el contrato `IVehicleDetector`:
     - Carga perezosa (*lazy loading*) con protección multihilo mediante `threading.RLock`.
     - Inyección de dependencias mediante `model_factory` para pruebas unitarias sin dependencias externas.
     - Validación de fotogramas BGR con `validate_bgr_frame`.
     - Redondeo y *clamping* de coordenadas a los límites de la imagen, descartando cajas degeneradas.
     - Filtrado de clases vehiculares COCO (`car=2`, `motorcycle=3`, `bus=5`, `truck=7`), descartando personas, bicicletas y animales.
     - Mapeo a objetos inmutables [`BoundingBox`](../../VIGIA_Vision/detection/models.py) y [`RawVehicleDetection`](../../VIGIA_Vision/detection/models.py).
  4. Excepciones estructuradas de dominio: `ModelLoadError` e `InferenceError`.
  5. Exportación pública en `VIGIA_Vision.detection` y `VIGIA_Vision`.
  6. Suite de pruebas unitarias (`tests/unit/test_yolo_detector.py`):
     - 14 pruebas desacopladas (simulación con dobles, sin GPU/disco/red).
     - 1 prueba de inferencia real en CPU con pesos reales e imagen de muestra.
     - Integración con `VisionEngineCoordinator` e interoperabilidad con `NullVehicleDetector`.
- **Excluido explícitamente (reservado para sprints posteriores):**
  - Reconocimiento de placas / OCR vehicular (Etapa 4).
  - Seguimiento temporal (tracking IoU / ByteTrack) y deduplicación temporal (Etapa 3).
  - Ingesta de video continua o servicios de streaming WebRTC.
  - Modificación del prototipo `VR_Semaforo` o de esquemas DDL en `BD/`.

### 1.4. Criterios de Aceptación
- **CA02-01:** Importar `VIGIA_Vision` o `YoloVehicleDetector` no carga PyTorch ni Ultralytics en memoria (`sys.modules`).
- **CA02-02:** `YoloDetectorConfig` valida umbrales de confianza, IoU, resolución, dispositivo y secuencia de clases, rechazando valores booleanos o fuera de rango.
- **CA02-03:** `YoloVehicleDetector.detect()` valida fotogramas con `validate_bgr_frame` y rechaza entradas inválidas (`None`, 2D, 4 canales, float32, dimensiones nulas).
- **CA02-04:** Las 4 clases vehiculares COCO son detectadas y mapeadas a etiquetas de dominio (`car`, `motorcycle`, `bus`, `truck`).
- **CA02-05:** Clases no vehiculares (personas, bicicletas, animales, semáforos) son filtradas tanto en el modelo como por defensa en profundidad.
- **CA02-06:** Coordenadas de detección son delimitadas dentro de los límites del fotograma (*clamping*) y las cajas degeneradas son descartadas.
- **CA02-07:** Fallos de carga e inferencia se reportan mediante `ModelLoadError` e `InferenceError`.
- **CA02-08:** `VisionEngineCoordinator` opera coordinadamente con `YoloVehicleDetector`, emitiendo `VisionObservationEnvelope` con `VisionStatus.VEHICLE_DETECTED_NO_PLATE`, confianza y ocupación instantánea.
- **CA02-09:** `NullVehicleDetector` permanece funcional como alternativa sin modelo.
- **CA02-10:** Inferencia real en CPU ejecutada con éxito sobre imagen de muestra con al menos un vehículo detectado.
- **CA02-11:** 100% de pruebas unitarias del repositorio aprobadas (113 de 113).

---

## 2. Ejecución

### 2.1. Inventario de Archivos Creados y Modificados
| Archivo | Acción | Descripción del Cambio |
| :--- | :---: | :--- |
| [`.gitignore`](../../.gitignore) | Modificado | Incorporación de `*.pt` y `*.onnx` para impedir el rastreo accidental de binarios de IA en Git. |
| [`VIGIA_Vision/detection/yolo_detector.py`](../../VIGIA_Vision/detection/yolo_detector.py) | **Creado** | Implementación de `YoloVehicleDetector`, `YoloDetectorConfig`, `ModelLoadError` e `InferenceError` con carga perezosa y defensa en profundidad. |
| [`VIGIA_Vision/detection/__init__.py`](../../VIGIA_Vision/detection/__init__.py) | Modificado | Exportación de los nuevos símbolos del detector YOLO. |
| [`VIGIA_Vision/__init__.py`](../../VIGIA_Vision/__init__.py) | Modificado | Exportación pública a nivel del paquete `VIGIA_Vision`. |
| [`tests/unit/test_yolo_detector.py`](../../tests/unit/test_yolo_detector.py) | **Creado** | 15 pruebas unitarias y de integración (14 desacopladas y 1 de inferencia real en CPU). |
| [`Docs/gestion_sprints/SPRINT-02_deteccion_real_vehiculos.md`](./SPRINT-02_deteccion_real_vehiculos.md) | Modificado | Expediente oficial del sprint completado. |
| [`Docs/gestion_sprints/README.md`](./README.md) | Modificado | Actualización de la tabla índice a estado `CERRADO`. |

### 2.2. Incidencias Técnicas Registradas y Resueltas
1. **Atributos de DTOs en prueba de integración:**
   - *Incidencia:* `CameraConfigDTO` y `AreaConfigDTO` arrojaron `TypeError` en el test por discrepancia de argumentos (`origen`, `id_area`).
   - *Resolución:* Se alinearon a los nombres canónicos de [`VIGIA_Vision/config/topology_validator.py`](../../VIGIA_Vision/config/topology_validator.py): `uri_stream`, `id_area_vision`, `tipo_movimiento`, `activa`.
2. **Firma del constructor del coordinador:**
   - *Incidencia:* `VisionEngineCoordinator` utiliza el parámetro `detector` en lugar de `vehicle_detector`.
   - *Resolución:* Se invocó con `detector=yolo_detector` y `sources={"CAM-ENTRADA": buf_ent, "CAM-SALIDA": buf_sal}`.
3. **Estado de dominio para detección sin placa:**
   - *Incidencia:* Se intentó validar contra `VisionStatus.VEHICLE_DETECTED`, el cual no existe en el enum canónico.
   - *Resolución:* Se validó contra `VisionStatus.VEHICLE_DETECTED_NO_PLATE`, `vehicle_type_pred="AUTOMOVIL"` y `vehicle_detected=True`.
4. **Aislamiento arquitectónico estricto de `VR_Semaforo`:**
   - *Incidencia:* La prueba arquitectónica `test_no_vr_semaforo_imports_in_vigia_vision_or_unit_tests` detectó la cadena literal en una ruta de búsqueda tentativa de pesos dentro del archivo de test.
   - *Resolución:* Se eliminó toda mención a rutas del prototipo experimental, resolviendo la ruta en la raíz del proyecto o mediante la variable de entorno `VIGIA_YOLO_WEIGHTS`.

---

## 3. Validación y Cierre

### 3.1. Resumen de Pruebas Automatizadas
- **Comando de ejecución:** `python -m unittest discover -s tests/unit`
- **Pruebas totales:** **113 pruebas ejecutadas, 113 aprobadas (0 fallos, 0 errores)**.
- **Tiempo total de ejecución:** **~7.0 segundos** (con inferencia real de YOLO en CPU incluida).
- **Desglose de pruebas en `test_yolo_detector.py` (15 pruebas):**
  - `PU-YOLO-01`: Carga perezosa (lazy loading) e inicialización libre de efectos colaterales.
  - `PU-YOLO-02`: Validación e inmutabilidad de `YoloDetectorConfig`.
  - `PU-YOLO-03`: Rechazo de fotogramas inválidos con `FrameValidationError`.
  - `PU-YOLO-04`: Parseo de coordenadas, redondeo, clamping y mapeo a `BoundingBox`.
  - `PU-YOLO-05`: Detección y mapeo correcto de las 4 clases COCO vehiculares (`car`, `motorcycle`, `bus`, `truck`).
  - `PU-YOLO-06`: Descarte de clases no vehiculares (personas, bicicletas, semáforos, animales).
  - `PU-YOLO-07`: Filtrado estricto por umbral de confianza (`confidence_threshold`).
  - `PU-YOLO-08`: Fotogramas sin detecciones retornan tupla vacía `()`.
  - `PU-YOLO-09`: Omitir cajas degeneradas tras *clamping*.
  - `PU-YOLO-10`: Fallo de carga de modelo lanza `ModelLoadError`.
  - `PU-YOLO-11`: Fallo de inferencia predictiva lanza `InferenceError`.
  - `PU-YOLO-12`: Seguridad en concurrencia multihilo durante la carga perezosa (`RLock`).
  - `PU-YOLO-13`: Integración con `VisionEngineCoordinator` como `IVehicleDetector`.
  - `PU-YOLO-14`: Verificación de preservación e integridad de `NullVehicleDetector`.
  - `PU-YOLO-15`: Inferencia real con `yolo11n.pt` sobre imagen de prueba en CPU.

### 3.2. Evaluación de Criterios de Aceptación
| Criterio | Estado | Evidencia |
| :---: | :---: | :--- |
| `CA02-01` | **CUMPLIDO** | `sys.modules` no contiene `torch` ni `ultralytics` tras importar `VIGIA_Vision`. Verificado por `test_clean_import_without_side_effects` y `PU-YOLO-01`. |
| `CA02-02` | **CUMPLIDO** | `YoloDetectorConfig` rechaza tipos inválidos, umbrales fuera de rango y es inmutable. Verificado por `PU-YOLO-02`. |
| `CA02-03` | **CUMPLIDO** | `validate_bgr_frame` rechaza entradas nulas, 2D, 4D, floats y matrices vacías. Verificado por `PU-YOLO-03`. |
| `CA02-04` | **CUMPLIDO** | Mapeo determinista de clases COCO `{2, 3, 5, 7}` a `['car', 'motorcycle', 'bus', 'truck']`. Verificado por `PU-YOLO-05`. |
| `CA02-05` | **CUMPLIDO** | Personas, bicicletas, animales y semáforos son descartados sin excepción. Verificado por `PU-YOLO-06`. |
| `CA02-06` | **CUMPLIDO** | *Clamping* a dimensiones reales del fotograma y omisión de cajas degeneradas. Verificado por `PU-YOLO-04` y `PU-YOLO-09`. |
| `CA02-07` | **CUMPLIDO** | Excepciones estructuradas `ModelLoadError` e `InferenceError` capturadas. Verificado por `PU-YOLO-10` y `PU-YOLO-11`. |
| `CA02-08` | **CUMPLIDO** | Integración en `VisionEngineCoordinator` genera `VisionObservationEnvelope` con estado `VEHICLE_DETECTED_NO_PLATE`. Verificado por `PU-YOLO-13`. |
| `CA02-09` | **CUMPLIDO** | `NullVehicleDetector` implementa `IVehicleDetector` y retorna `()`. Verificado por `PU-YOLO-14`. |
| `CA02-10` | **CUMPLIDO** | Inferencia real sobre `bus.jpg` con `yolo11n.pt` en CPU detecta autobús con confianza > 0.90 y descarta personas. Verificado por `PU-YOLO-15`. |
| `CA02-11` | **CUMPLIDO** | 113 de 113 pruebas unitarias aprobadas sin regresiones. |

### 3.3. Dictamen de Cierre
El sprint cumple íntegramente sus criterios de aceptación técnicos y arquitectónicos. Queda formalmente **`CERRADO`**.
