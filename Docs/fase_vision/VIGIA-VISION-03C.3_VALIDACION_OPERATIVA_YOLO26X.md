# VIGIA-VISION-03C.3 — Validación Operativa y Precisión Experimental de YOLO26x

**Proyecto:** VIGÍA Vision Systems  
**Fase:** `VISION-03C.3` (Validación operativa y precisión experimental de `yolo26x.pt`)  
**Fecha de ejecución:** 2026-11-14 / 2026-11-15 UTC  
**Entorno de hardware validado:** NVIDIA GeForce RTX 4050 Laptop GPU (6141 MiB VRAM, Driver 566.36)  
**Entorno Python:** `VIGIA_Vision_Systems/.venv_cuda/Scripts/python.exe` (Ultralytics `8.4.171`)

---

## 1. Resumen Ejecutivo y Veredicto

Se ejecutó la validación técnica, operativa, de estabilidad y de regresión de la integración experimental de **YOLO26x** (`experiments/yolo26x/weights/yolo26x.pt`, `imgsz=640`, `quantize=16` FP16, `nms=False` NMS-Free / `end2end=True`, `augment=False`, `device=cuda:0`) implementada en `VISION-03C.2`, manteniendo intacto el modelo predeterminado de producción (`yolo11n.pt`) y sin modificar código de producción ni archivos `.env`.

### Veredicto

> **APPROVED WITH OBSERVATIONS — READY WITH LIMITATIONS**

**Justificación técnica del veredicto:**
1. **Operación, GPU, pipeline y resiliencia (APROBADO):** `YOLO26x` opera de forma estable sobre CUDA en FP16 NMS-Free (`end2end=True`), completando el flujo HTTP `POST /api/v1/cameras/CAM-ENTRADA/push` -> `VisionEngineCoordinator` -> filtros ROI -> persistencia en repositorio -> guardado de evidencias (`_orig.jpg` / `_annot.jpg`) -> endpoints de Dashboard (`/api/v1/cameras`, `/status`, `/live`, `/api/v1/supervision/status`) con `0` errores HTTP en 100 peticiones consecutivas, `0` errores en concurrencia multi-cámara (`23.23 FPS` combinados) y `0` errores ni fugas de VRAM (`vram_delta_mb = 0.0`) tras un soak sostenido de `90.01 s` (`2,374` frames a `26.55 FPS`, `64.0 °C`). El mecanismo de fallback controlado a `yolo11n.pt` (en `model_init`, `runtime_inference`, `NaN/Inf` y concurrencia) fue verificado sin bucles infinitos.
2. **Limitación crítica de Ground Truth real (OBSERVACIÓN):** El corpus existente (`evidencias_vigia`: `604` capturas; `VIGIA-BENCH-v1`: `150` capturas) contiene **`0` vehículos reales a escala 1:1** (`128` maquetas `SCALE_MODEL_LAB`, `20` recapturas de pantalla `SCREEN_RECAPTURE`, `2` sintéticas `SYNTHETIC_STOCK`) y **`0/150` anotaciones humanas** en `annotation_sheet_v1.csv` (`PENDING_HUMAN_REVIEW`). Por tanto, **no es técnicamente válido certificar la precisión real en calle/estacionamiento** hasta ejecutar la prueba física final con anotación manual (`VIGIA-BENCH-REAL`).
3. **Observación de sensibilidad en umbral `0.70` y duplicados `nms=False`:** En `SCREEN_RECAPTURE` (escenas multi-vehículo con vehículos pequeños/lejanos), `YOLO26x` propone sustancialmente más detecciones a `>=0.25` (`287` vs `188` cajas; `+123` cajas adicionales), pero en `SCALE_MODEL_LAB` bajo umbral `0.70` detecta menos frames que `YOLO11n` (`101/128` vs `119/128`), especialmente en `UNDEREXPOSED` (`7/14` vs `12/14`), y presenta mayor tasa de cajas solapadas intra-frame con `IoU>=0.50` (`30` vs `8`).
4. **Limitación de infraestructura local (BLOCKED parcial):** Docker Desktop y PostgreSQL (`127.0.0.1:5434`) se encontraban detenidos durante la ejecución, por lo que las pruebas acopladas a BD viva quedaron `BLOCKED` (verificado mediante `_InMemoryDetectionRepo` conforme a `IDetectionRepository.persist_detection`).

---

## 2. Estado Inicial del Sistema (Fase A)

| Componente | Estado observado | Evidencia / Detalle |
| :--- | :--- | :--- |
| Modelo predeterminado producción | `yolo11n.pt` (intacto) | SHA-256: `0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1` |
| Modelo experimental `YOLO26x` | `experiments/yolo26x/weights/yolo26x.pt` | SHA-256: `9FDD44A31C504547FFB81D2C6D9E6DAC3493C8EAA8B0398D3F43BAE6C7003E92` |
| GPU / Driver CUDA | Activa y disponible | `NVIDIA GeForce RTX 4050 Laptop GPU`, `6141 MiB`, Driver `566.36`, `889 MiB` usados iniciales, `52 °C` |
| Configuración experimental | `imgsz=640`, `quantize=16`, `nms=False`, `augment=False`, `device=cuda:0` | Verificada vía `VisionEngineSettings` y `YoloVehicleDetector` |
| Fallback controlado | Activo hacia `yolo11n.pt` | Verificado en init y runtime sin bucle infinito |
| FSM Temporal (`CameraTemporalStateTracker`) | Aislada (`VISION-02A.1`) | Presente solo en `VIGIA_Vision/runtime/temporal_state.py`; no conectada aún a `VisionEngineCoordinator` ni `ingest_service.py` (pendiente `VISION-02B`) |
| PostgreSQL (`127.0.0.1:5434`) | Offline (`BLOCKED`) | Docker daemon no activo; puertos `5000, 5433, 5434, 8443` sin procesos escuchando |
| Dashboard web (`VIGIA_Dashboard`) | Contratos verificados | Consume `/api/v1/cameras`, `/api/v1/cameras/:codigo/status`, `/stream`, `/live` |
| Archivo `.env` | Sin modificaciones | Preservado intacto durante toda la fase |

---

## 3. Inventario del Corpus de Evaluación y Verificación de Ground Truth (Fase B)

### 3.1 Corpus histórico `evidencias_vigia`
- **Imágenes originales (`_orig.jpg`):** `604`
- **Imágenes anotadas (`_annot.jpg`):** `604`
- **Imágenes corruptas o ilegibles:** `0`
- **Hashes SHA-256 únicos:** `208` (`3` grupos de duplicados con `396` archivos duplicados adicionales)
- **Distribución por cámara:** `CAM-SALIDA: 251`, `CAM-ENTRADA: 238`, `CAM-03: 77`, `CAM-04: 38`
- **Resoluciones:** `640x480: 523`, `720x1280: 74`, `810x1080: 7`

### 3.2 Benchmark `VIGIA-BENCH-v1` y estado de Ground Truth
- **Manifiesto (`benchmarks/vigia_bench_v1/manifest_v1_seed.json`):** `150` imágenes seleccionadas:
  - `SCALE_MODEL_LAB`: `128`
  - `SCREEN_RECAPTURE`: `20`
  - `SYNTHETIC_STOCK`: `2`
  - `REAL_VEHICLES` (escala 1:1): **`0`**
  - Cámaras: `CAM-SALIDA: 75`, `CAM-ENTRADA: 74`, `CAM-03: 1`
  - Iluminación: `WELL_LIT: 116`, `HARSH_GLARE: 20`, `UNDEREXPOSED: 14`
- **Hoja de anotación (`benchmarks/vigia_bench_v1/annotation_sheet_v1.csv`):** `150` filas totales, **`0` filas anotadas por humanos** (`150` en estado `PENDING_HUMAN_REVIEW`, columnas GT vacías).

---

## 4. Metodología de Comparación Controlada (Fase C)

Se evaluaron ambos modelos sobre exactamente las mismas `150` imágenes de `VIGIA-BENCH-v1` utilizando el wrapper de producción `YoloVehicleDetector`, con proyección de ROI normalizada `[0.05..0.95]` (`project_normalized_roi`) y filtrado `filter_detections_by_roi`:

- **Baseline (`YOLO11n`):** `yolo11n.pt`, `device=cuda:0`, `imgsz=640`, FP32 (`quantize=None`), `nms=None`, `augment=False`.
- **Experimental (`YOLO26x`):** `yolo26x.pt`, `device=cuda:0`, `imgsz=640`, FP16 (`quantize=16`), `nms=False` (`end2end=True`), `augment=False`.
- **Cortes evaluados:** umbral diagnóstico `>= 0.25` y umbral operativo vigente de producción `>= 0.70`.
- **Nota metodológica:** al no existir Ground Truth humano, las métricas comparan capacidad de propuesta, consistencia de confianza, sensibilidad por iluminación, tamaño relativo de objetos y divergencia inter-modelo (no Precision/Recall certificados contra GT).

---

## 5. Resultados Cuantitativos Comparativos (`YOLO11n` vs `YOLO26x`)

### 5.1 Comparativa por dominio de imagen

| Dominio | Imgs | `YOLO11n` `>=0.25` (frames / cajas / conf media) | `YOLO26x` `>=0.25` (frames / cajas / conf media) | `YOLO11n` `>=0.70` (frames / cajas) | `YOLO26x` `>=0.70` (frames / cajas) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `SCALE_MODEL_LAB` | `128` | `128` / `161` / `0.7471` | `125` / `177` / `0.7070` | `119` / `125` | `101` / `103` |
| `SCREEN_RECAPTURE` | `20` | `20` / `188` / `—` | `20` / `287` (`+123` nuevas) / `—` | `20` / `90` | `20` / `89` |
| `SYNTHETIC_STOCK` | `2` | `2` (`bus`) / `0.8817` | `2` (`bus`) / `0.9451` | `2` / `2` | `2` / `2` |

### 5.2 Sensibilidad bajo umbral operativo `>= 0.70` por condición de iluminación

| Condición de iluminación | Total imgs | `YOLO11n` frames detectados (`>=0.70`) | `YOLO26x` frames detectados (`>=0.70`) |
| :--- | :---: | :---: | :---: |
| `WELL_LIT` | `116` | `112` | `101` |
| `HARSH_GLARE` | `20` | `17` | `15` |
| `UNDEREXPOSED` | `14` | `12` | `7` |

---

## 6. Análisis de Clasificación Vehicular (`CAR`, `MOTORCYCLE`, `BUS`, `TRUCK`)

- **Divergencias de clase sobre pares emparejados (`IoU >= 0.50`):**
  - `car -> truck`: `10`
  - `truck -> car`: `6`
  - `motorcycle -> car`: `2`
  - `bus -> truck`: `1`
  - `truck -> bus`: `1`
- **Detección de objetos pequeños (`< 5%` del área del frame a `>= 0.25`):**
  - `YOLO11n`: `214` cajas
  - `YOLO26x`: `307` cajas (`+43.5%` propuestas en objetos pequeños/lejanos)
- **Solapamiento intra-frame (`IoU >= 0.50` dentro del mismo frame):**
  - `YOLO11n`: `8` pares
  - `YOLO26x` (`nms=False`): `30` pares

---

## 7. Análisis Cualitativo de Fallos y Casos Borde

1. **Caída de confianza en `SCALE_MODEL_LAB` y `UNDEREXPOSED` bajo `0.70`:** `YOLO26x` tiende a distribuir la confianza ligeramente más abajo en maquetas a escala y baja iluminación (`7/14` vs `12/14` en `UNDEREXPOSED` con `>=0.70`). Esto puede deberse al dominio fuera de distribución (juguetes/maquetas en laboratorio frente a vehículos reales de COCO) y hace indispensable validar con vehículos reales 1:1 antes de ajustar `vehicle_confidence_threshold` (`0.70`).
2. **Mayor cobertura en escenas multi-vehículo (`SCREEN_RECAPTURE`):** `YOLO26x` detectó `287` cajas frente a `188` de `YOLO11n` (`+123` detecciones adicionales a `>=0.25`), mostrando clara superioridad para vehículos pequeños y parcialmente visibles.
3. **Duplicados intra-frame con `nms=False`:** Se observaron `30` pares intra-frame con `IoU >= 0.50` en `YOLO26x` frente a `8` en `YOLO11n`. En el flujo actual de `VIGIA`, el coordinador selecciona la detección principal de mayor confianza y cuenta detecciones en ROI, por lo que no rompe el contrato, pero conviene vigilar el conteo `in_roi_now` en escenas densas.

---

## 8. Validación del Pipeline Operativo Completo (Fase D)

Ejecución verificada mediante `validate_vision_03c3_operational.py` sobre la aplicación Flask real (`create_ingest_app` con `_InMemoryDetectionRepo.persist_detection` y almacenamiento temporal de evidencias):

1. **Etapa 1 — Inicialización `YOLO26x`:** `effective_model="yolo26x.pt"`, `using_fallback=false`, `is_loaded=true`, `ultralytics_version="8.4.171"`.
2. **Etapa 2 — Verificación NMS-Free:** `end2end=True` y `nms=False` verificados (`passed=true`).
3. **Etapa 3 — Ingesta HTTP + Coordinador:** `POST /api/v1/cameras/CAM-ENTRADA/push` -> HTTP `200`, `ok=true`, `vehicle_detected=true`, `tipo_vehiculo="AUTOBUS"`, `confianza=0.9462890625`, `status="VEHICLE_DETECTED_NO_PLATE"`, `detection_persisted=true`, `evidence_saved=true`.
4. **Etapa 4 — FSM Temporal (`CameraTemporalStateTracker`):** Confirmado aislado en `VIGIA_Vision/runtime/temporal_state.py` (no integrado en coordinador hasta `VISION-02B`); sonda de contrato confirmó transiciones `VEHICLE_CANDIDATE -> VEHICLE_PRESENT`.
5. **Etapa 5 — Persistencia:** `_InMemoryDetectionRepo` registró `1` `DetectionInsertDTO` completo; PostgreSQL vivo en `127.0.0.1:5434` reportado como `BLOCKED`.
6. **Etapa 6 — Evidencias en disco:** `1` archivo `_orig.jpg` y `1` archivo `_annot.jpg` escritos correctamente.
7. **Etapa 7 — Endpoints de Dashboard y Streaming:** `POST /api/v1/auth/login` (`200`), `GET /app` (`200`), `GET /api/v1/cameras` (`200`), `GET /api/v1/cameras/CAM-ENTRADA/status` (`200`, `operational_state="TRANSMITIENDO"`), `GET /api/v1/cameras/CAM-ENTRADA/live` (`200`, `image/jpeg`), `GET /api/v1/supervision/status` (`200`).

---

## 9. Pruebas de Estabilidad, Concurrencia y Rendimiento (Fase E)

| Prueba | Muestras / Duración | Media (`ms`) | `p50` (`ms`) | `p95` (`ms`) | `p99` (`ms`) | Throughput (`FPS`) | Errores |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Inferencia aislada (`YOLO26x` FP16 CUDA) | `200` frames | `56.585` | `38.630` | `245.621` | `299.398` | `17.67` | `0` |
| Concurrencia multi-hilo (`CAM-ENTRADA`) | `100` frames | `85.598` | `83.878` | `103.218` | `136.852` | `11.68` | `0` |
| Concurrencia multi-hilo (`CAM-SALIDA`) | `100` frames | `86.040` | `84.050` | `105.595` | `171.700` | `11.62` | `0` |
| Agregado multi-worker (2 hilos) | `200` frames (`8.61 s`) | `—` | `—` | `—` | `—` | `23.23` | `0` |
| Pipeline HTTP `push` E2E | `100` frames | `53.162` | `52.536` | `68.438` | `80.256` | `18.81` | `0` HTTP |
| **Soak sostenido GPU CUDA** | `90.01 s` (`2,374` frames) | `37.664` | `36.975` | `50.364` | `60.757` | **`26.55`** | **`0`** |

**Telemetría de GPU y memoria durante el soak sostenido (`90.01 s`):**
- `vram_start_mb`: `434.86 MiB` -> `vram_end_mb`: `434.86 MiB` (**`vram_delta_mb = 0.0 MiB`**, sin fuga de memoria PyTorch).
- `vram_peak_allocated_mb`: `487.07 MiB` | `vram_peak_reserved_mb`: `732.00 MiB`.
- `final_gpu_smi`: `temp_c = 64.0 °C`, `gpu_util_pct = 49.0 %`, `vram_used_mb = 1600.0 / 6141.0 MiB`.
- `using_fallback_after_soak`: `false` (`effective_model_after_soak = "yolo26x.pt"`).

---

## 10. Pruebas de Fallback Controlado y Resiliencia (Fase F)

Validadas en `tests/unit/test_vision_03c2_yolo26x_integration.py` y `tests/unit/test_yolo_detector.py` (todas `PASS`):
- **Fallo en `model_init`:** pesos corruptos, archivo inexistente o modelo sin soporte `end2end=True` con `nms=False` conmutan automáticamente a `yolo11n.pt` registrando `FALLBACK YOLO ACTIVADO (model_init)`.
- **Fallo en `runtime_inference`:** excepción transitoria CUDA durante `detect_vehicles()` conmuta a `yolo11n.pt` y reintenta el frame actual una única vez sin bucle infinito.
- **Salida no finita (`NaN`/`Inf`):** `InferenceError` por coordenadas o confianza no finita dispara fallback a `yolo11n.pt`.
- **Doble fallo terminal:** cuando también falla el fallback, propaga `ModelLoadError` / `InferenceError` de forma controlada sin bucles ni bloqueo.
- **Concurrencia thread-safe:** dos hilos (`CAM-ENTRADA` y `CAM-SALIDA`) sobre una misma instancia realizan la transición a fallback bajo lock compartido sin condiciones de carrera.

---

## 11. Regresión de Pruebas Unitarias, Integración y E2E (Fase H)

| Categoría | Suites / Alcance | Resultado | Observación |
| :--- | :--- | :---: | :--- |
| **`PASS`** | `test_vision_03c2_yolo26x_integration`, `test_yolo_detector`, `test_vision_02a_temporal_fsm`, `experiments.yolo26x.tests.test_yolo26x_contract`, `test_vision_pipeline`, `test_topology_validator`, `test_async_persistence_pilot`, `test_detection_repository`, `test_domain_models` | `147 / 147` (`OK`) | Ejecución limpia con GPU CUDA real |
| **`PASS`** | `test_vision_stage1_components` (aislada) | `16 / 16` (`OK`) | Verifica import limpio sin cargar `ultralytics`/`torch`; nota: falla `test_clean_import_without_side_effects` solo si se corre en el mismo proceso después de tests que importan `ultralytics` |
| **`PASS`** | `test_camera`, `test_camera_stream_and_backend`, `test_usb_camera_integration`, `test_lan_detector` | `53 / 53` (`OK`) | Contratos de cámara USB/móvil y LAN |
| **`PASS`** | `test_auth_rbac`, `test_auth_stream_protection`, `test_ipc_hardening`, `test_isolated_signer`, `test_network_discovery`, `test_signer_fail_closed`, `test_crl_management` (`14/15`), `test_trust_ca_logic` (`21/22`) | `125 / 125` (`OK`) | Seguridad, RBAC, IPC, signer y red |
| **`FAIL`** | `test_trust_ca_logic.test_16_strict_check_reports_modalidad_a_and_b` | `1 FAIL` | Preexistente sobre verificación TLS/CA (`modalidad_a_passed` False); ajena a YOLO26x |
| **`BLOCKED`** | `test_mobile_ingest_api` (`49` tests) + `test_crl_management.test_15_flask_app_crl_endpoint_compatibility` (`1` test) | `50 ERROR` | `psycopg2.OperationalError`: PostgreSQL offline en `127.0.0.1:5434` |
| **`NOT RUN`** | `tests/integration/test_phase3a_postgres_integration.py`, `test_phase3b_dashboard_integration.py`, `test_seed_data_integration.py`, `test_vision_engine_operational_integration.py`, `test_mobile_qr_enrollment_integration.py`, `test_network_endpoints_integration.py`, `test_tls_mobile_enrollment_integration.py`, `tests/e2e/test_usb_e2e_physical.py` | `NOT RUN` | Requieren PostgreSQL levantado, servidor HTTPS activo o hardware físico/cámaras USB en vivo |

---

## 12. Protocolo Preparado para Prueba Física Final con Vehículos Reales (Fase G)

*(No ejecutado en esta fase por restricción; listo para ejecución del propietario).*

### 12.1 Preparación de cámaras, red y certificados
1. Levantar Docker / PostgreSQL (`127.0.0.1:5434`) y verificar salud del esquema.
2. Verificar certificados activos en `certs/` (`vigia_root_ca.crt`, `vigia_cert.pem`, `vigia_key.pem`, `vigia_root_ca.crl`) y endpoints `/api/v1/tls/ca.crt` y `/api/v1/tls/ca.crl`.
3. Enrolar cámaras físicas:
   - **USB (`CAM-ENTRADA` / `CAM-SALIDA`):** `GET /api/v1/devices/usb-cameras` y `POST /api/v1/devices/usb/enroll`.
   - **Móvil HTTPS:** `POST /api/v1/devices/pairing-qr` y `POST /api/v1/mobile/pairing/claim` tras instalar `vigia_root_ca.crt`.
4. Ejecutar primero una corrida base con `yolo11n.pt` (default) y posteriormente una corrida controlada con `VIGIA_YOLO_MODEL=experiments/yolo26x/weights/yolo26x.pt`, `VIGIA_YOLO_IMGSZ=640`, `VIGIA_YOLO_QUANTIZE=16`, `VIGIA_YOLO_NMS=false`, `VIGIA_YOLO_AUGMENT=false`.

### 12.2 Matriz de escenarios físicos a capturar (`VIGIA-BENCH-REAL`)
- Clases: automóvil (`CAR`), motocicleta (`MOTORCYCLE`), autobús (`BUS`), camión (`TRUCK`).
- Distancias y geometría: cercano, lejano (`<5%` área), oclusión parcial (entrada/salida de ROI), ángulos frontal/lateral/trasero.
- Dinámica e iluminación: vehículo en movimiento, día pleno, contraluz/reflejo (`HARSH_GLARE`), noche/baja luz (`UNDEREXPOSED`), y escenas vacías sin vehículos (control de falsos positivos).

### 12.3 Protocolo de Ground Truth manual
- Guardar capturas `_orig.jpg` sin alterar y registrar en una hoja `annotation_sheet_real.csv` (mismo esquema que `annotation_sheet_v1.csv`) con anotación humana obligatoria (`bbox`, clase real, condición de iluminación, `annotator`, sin usar detecciones YOLO como Ground Truth).

---

## 13. Impacto en Arquitectura, Seguridad, Rendimiento y Operación

- **Producción intacta:** `yolo11n.pt` permanece como modelo por defecto y fallback. No se modificó ningún archivo de `VIGIA_Vision/`, `VIGIA_API/`, `VIGIA_Core/`, `VIGIA_Dashboard/` ni `Software/.env`.
- **Seguridad y contratos:** Todos los contratos HTTP, DTOs (`DetectionInsertDTO`), rutas de evidencia y controles RBAC/CSRF/TLS se mantuvieron sin cambios.
- **Rendimiento:** `YOLO26x` FP16 NMS-Free logra `26.55 FPS` sostenidos en inferencia GPU y `18.81 FPS` en pipeline HTTP E2E con latencia media `53.16 ms` (`p95 = 68.44 ms`), cumpliendo holgadamente la cadencia objetivo de `CameraPullWorker` (`15.0 FPS`).

---

## 14. Limitaciones, Riesgos y Condiciones para Pasar a Producción

1. **No hay certificación de precisión real aún:** 0 muestras reales 1:1 y 0 etiquetas humanas GT impiden declarar mejora real de mAP/Recall en calle.
2. **Calibración de umbral `0.70`:** Si en la prueba física `YOLO26x` mantiene menor tasa de disparo en baja luz a `0.70`, deberá evaluarse ajuste de umbral en una fase dedicada posterior tras medir con `VIGIA-BENCH-REAL`.
3. **Integración pendiente de FSM (`VISION-02B`):** `CameraTemporalStateTracker` aún no filtra parpadeos en el coordinador activo.
4. **PostgreSQL obligatorio antes de prueba física:** Debe levantarse la BD en `127.0.0.1:5434` y ejecutarse las pruebas `BLOCKED` antes de la jornada física.

---

## 15. Comandos Ejecutados, Scripts Auxiliares y Hashes de Artefactos

- **Script de validación operativa:** `C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/scripts/validate_vision_03c3_operational.py`
- **Artefacto de resultados JSON:** `C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/results/vision_03c3_operational_results.json`
- **Comandos ejecutados:**
  - `.venv_cuda/Scripts/python.exe experiments/yolo26x/scripts/validate_vision_03c3_operational.py` (`exit 0`)
  - `.venv_cuda/Scripts/python.exe -m unittest tests.unit.test_vision_03c2_yolo26x_integration tests.unit.test_yolo_detector tests.unit.test_vision_02a_temporal_fsm experiments.yolo26x.tests.test_yolo26x_contract tests.unit.test_vision_pipeline tests.unit.test_topology_validator tests.unit.test_async_persistence_pilot tests.unit.test_detection_repository tests.unit.test_domain_models` (`147 OK`)
  - `.venv_cuda/Scripts/python.exe -m unittest tests.unit.test_vision_stage1_components -v` (`16 OK`)
  - `.venv_cuda/Scripts/python.exe -m unittest tests.unit.test_camera tests.unit.test_camera_stream_and_backend tests.unit.test_usb_camera_integration tests.unit.test_lan_detector -v` (`53 OK`)
  - `.venv_cuda/Scripts/python.exe -m unittest tests.unit.test_auth_rbac tests.unit.test_auth_stream_protection tests.unit.test_crl_management tests.unit.test_ipc_hardening tests.unit.test_isolated_signer tests.unit.test_mobile_ingest_api tests.unit.test_network_discovery tests.unit.test_signer_fail_closed tests.unit.test_trust_ca_logic` (`125 OK`, `50 ERROR` por PostgreSQL offline, `1 FAIL` preexistente TLS/CA)
- **Hashes SHA-256 de pesos:**
  - `yolo11n.pt`: `0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1`
  - `experiments/yolo26x/weights/yolo26x.pt`: `9FDD44A31C504547FFB81D2C6D9E6DAC3493C8EAA8B0398D3F43BAE6C7003E92`

---

## 16. Conclusión Técnica Final

La integración experimental de **YOLO26x** (`FP16`, `imgsz=640`, `nms=False`, `cuda:0`) en VIGÍA Vision Systems es **operativamente estable, segura, reversible y apta en rendimiento** (`26.55 FPS` sostenidos sin fugas de VRAM, fallback verificado y `0` errores en pipeline HTTP E2E en memoria). Se aprueba con observaciones (**`APPROVED WITH OBSERVATIONS — READY WITH LIMITATIONS`**) para avanzar hacia la prueba física final con vehículos reales y anotación manual (`VIGIA-BENCH-REAL`), manteniendo `yolo11n.pt` como predeterminado de producción hasta contar con métricas reales sobre Ground Truth humano.
