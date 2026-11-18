# VIGIA-VISION-03C.2 — Integración Experimental Controlada de YOLO26x

**Proyecto:** VIGÍA Vision Systems  
**Fase:** `VISION-03C.2` — Integración experimental controlada de `yolo26x.pt`  
**Fecha de cierre:** 2026-11-14 (UTC `2026-11-14T19:34:51Z`)  
**Hardware validado:** NVIDIA GeForce RTX 4050 Laptop GPU (`6140.5 MiB` VRAM total)  
**Stack verificado:** Python `3.11.1`, PyTorch `2.6.0+cu124`, Ultralytics `8.4.171`  
**Veredicto final:** `APPROVED — EXPERIMENTAL INTEGRATION`

---

## 1. Resumen Ejecutivo

Se ejecutó e integró de forma controlada, seleccionable y totalmente reversible el soporte experimental para **`yolo26x.pt`** (`imgsz=640`, `quantize=16` FP16, `nms=False` NMS-Free nativo `end2end=True`) dentro del subsistema de detección de VIGÍA ([yolo_detector.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py) y [ingest_service.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py)).

La implementación preserva **`yolo11n.pt` como modelo predeterminado de producción** y lo habilita como **fallback funcional automático y seguro** tanto ante fallos de inicialización como ante fallos recuperables durante la inferencia en tiempo de ejecución, manteniendo intactos los contratos `RawVehicleDetection`, `VisionResult`, `VisionEngineCoordinator`, `CameraTemporalStateTracker`, el esquema PostgreSQL y el Dashboard.

---

## 2. Arquitectura Actual vs. Arquitectura Integrada

| Aspecto | Antes (`VISION-03C.1` / Baseline) | Después (`VISION-03C.2`) |
| :--- | :--- | :--- |
| Modelo predeterminado | `yolo11n.pt` fijo en fábrica API | **`yolo11n.pt` preservado como default obligatorio** |
| Selección experimental | No parametrizada para FP16 ni `nms=False` | Configurable vía `VIGIA_YOLO_MODEL`, `VIGIA_YOLO_IMGSZ`, `VIGIA_YOLO_QUANTIZE`, `VIGIA_YOLO_NMS`, `VIGIA_YOLO_DEVICE` |
| Modo NMS-Free `end2end` | No soportado en `YoloDetectorConfig` | Soporte explícito (`nms=False` / `True` / `None`), verificación pre/post-predict de `one2one_cv2` y `AutoBackend.end2end` |
| Resolución de pesos | Dependiente de ruta absoluta o CWD en algunos contextos | `resolve_yolo_weights_path()` determinista respecto a `_REPO_ROOT` (`VIGIA_Vision_Systems`) sin depender de `os.getcwd()` |
| Tolerancia a fallos | Excepción directa (`ModelLoadError` / `InferenceError`) | Fallback automático thread-safe (`threading.RLock`) hacia `yolo11n.pt` en carga inicial, incompatibilidad NMS-Free, error CUDA y salidas `NaN`/`Inf` |
| Instanciación multi-cámara | Instancia única compartida en coordinador | Instancia única compartida preservada para `CAM-ENTRADA` y `CAM-SALIDA` bajo `threading.RLock` |
| Observabilidad | Logs básicos de dispositivo | Logs estructurados `INFO` / `WARNING` / `ERROR` + snapshot `get_runtime_status()` con trazabilidad completa |

---

## 3. Selección de Modelo y Parámetros (`.env` y Cargador Centralizado)

- Se implementó `load_yolo_config_from_env()` en [yolo_detector.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py#L341-L406), utilizando exclusivamente `get_setting` de [env_loader.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Core/config/env_loader.py).
- Se conectó `build_vision_engine_coordinator()` en [ingest_service.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py#L288-L329) manteniendo compatibilidad retrospectiva con el argumento `yolo_weights_path` y la variable heredada `VIGIA_YOLO_WEIGHTS`.
- **Estado de `.env` y `.env.example`:**
  - El archivo productivo local `Software/.env` **no fue modificado** (`LastWriteTime`: `2026-11-08 11:41:53`, `1079` bytes).
  - Se actualizó la plantilla [.env.example](file:///C:/GEST.PROY.TI/Software/.env.example#L106-L125) manteniendo `VIGIA_YOLO_MODEL=yolo11n.pt` como predeterminado activo y dejando el perfil `yolo26x.pt` debidamente comentado para evaluación controlada.

| Variable de entorno | Valor por defecto | Reglas de validación y comportamiento |
| :--- | :--- | :--- |
| `VIGIA_YOLO_MODEL` | `yolo11n.pt` | Acepta nombre de modelo o ruta; respalda compatibilidad con `VIGIA_YOLO_WEIGHTS` si está ausente. |
| `VIGIA_YOLO_IMGSZ` | `640` | Entero positivo estricto; valores `<= 0`, booleanos o no numéricos lanzan `ValueError`. |
| `VIGIA_YOLO_QUANTIZE` | `None` | Acepta vacío/`none`/`null` (`None`), `16`/`fp16` (`16`), `32`/`fp32` (`32`); rechaza otros valores (ej. `8`, `int8`, `invalid`). |
| `VIGIA_YOLO_NMS` | `None` | Distingue `None` (no especificado), `True` (`true`/`1`/`yes`) y `False` (`false`/`0`/`no`); **nunca** se infiere por nombre de pesos. |
| `VIGIA_YOLO_DEVICE` | Fallback a `VIGIA_INFERENCE_DEVICE` (`auto`) | Resuelto mediante `resolve_inference_device()`. |
| `VIGIA_YOLO_FALLBACK_ENABLED` | `True` | Activa/desactiva conmutación automática al respaldo. |
| `VIGIA_YOLO_FALLBACK_MODEL` | `yolo11n.pt` | Modelo estándar destino del fallback. |

---

## 4. Extensión de `YoloDetectorConfig` y `YoloVehicleDetector`

En [yolo_detector.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py#L208-L298):

- Se amplió la clase inmutable `@dataclass(frozen=True) YoloDetectorConfig` conservando los 6 atributos posicionales originales y añadiendo: `quantize: Optional[int] = None`, `nms: Optional[bool] = None`, `augment: bool = False`, `fallback_enabled: bool = True`, `fallback_model_path: Union[str, Path] = "yolo11n.pt"`.
- Se añadió la regla explícita de incompatibilidad en `__post_init__`: `augment=True` (TTA) con `nms=False` (NMS-Free) lanza `ValueError` inmediatamente.
- Se exportaron `load_yolo_config_from_env` y `resolve_yolo_weights_path` en [__init__.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/__init__.py) y [detection/\_\_init\_\_.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/__init__.py).

---

## 5. Manejo de Modo NMS-Free / `quantize` en Ultralytics `8.4.171`

1. `_build_predict_kwargs()` solo incluye `quantize`, `nms` y `augment` en la llamada a `model.predict(...)` cuando corresponden (`quantize is not None`, `nms is not None`, `augment is True`), conservando idéntica la invocación estándar cuando permanecen en `None`/`False`.
2. **Descubrimiento y corrección verificada en hardware real durante `VISION-03C.2`:**
   - Al inspeccionar directamente `YOLO("yolo26x.pt")` en `.venv_cuda` antes de la primera llamada a `.predict()`, Ultralytics expone `model.end2end == False` y `model.model.end2end == False`, mientras el checkpoint declara `model.model.yaml["end2end"] == True` y `head.one2one_cv2 is not None` (`yolo11n.pt` tiene `yaml.get("end2end") == None` y `one2one_cv2 == None`).
   - `_verify_nms_free_pre_predict()` verifica la arquitectura `one2one_cv2` + `yaml["end2end"]` / `head.end2end` en modelos PyTorch reales antes de inferir (rechazando con `ModelLoadError` si se intenta `nms=False` sobre `yolo11n.pt`), y `_verify_nms_free_post_predict()` confirma tras la primera inferencia sobre `AutoBackend` que `AutoBackend.end2end == True`, `one2one_cv2` activo y la rama `one2many` (`cv2`) liberada (`None`).

---

## 6. Mecanismo de Fallback Seguro y Prevención de Fallos Silenciosos

Implementado bajo bloqueo reentrante (`self._lock = threading.RLock()`) en `YoloVehicleDetector`:

- **Fallo en inicialización (`stage="model_init"`):** Cubre archivo `.pt` ausente/corrupto, error CUDA `.to(device)` o incompatibilidad NMS-Free (`nms=False` sobre modelo sin `one2one`). Conmuta a `fallback_model_path` (`yolo11n.pt`, `imgsz=640`, `quantize=None`, `nms=None`, `augment=False`), ejecuta un fotograma sintético de comprobación `(64, 64, 3)` para garantizar operatividad real y registra evento `WARNING`.
- **Fallo recuperable en tiempo de ejecución (`stage="runtime_inference"`):** Ante excepción en `predict()` (p. ej. `RuntimeError: CUDA out of memory`), fallo de verificación `AutoBackend.end2end` o detección de coordenadas/confianza no finitas (`NaN`/`Inf` capturadas en `_parse_prediction_results`), conmuta al respaldo y **reintenta el fotograma actual una única vez** sin propagar error al coordinador ni perder el fotograma en curso.
- **Guardia anti-bucle infinito:** `_using_fallback` se fija a `True` y `fallback_enabled=False` en la configuración de respaldo. Si el propio respaldo falla al inicializarse, durante el único reintento o en llamadas subsecuentes, lanza `ModelLoadError` o `InferenceError` de forma limpia sin reintentos recursivos. Si el modelo solicitado y el de respaldo son idénticos sin overrides experimentales (`quantize=None`, `nms=None`, `augment=False`), no ejecuta fallback redundante.

---

## 7. Logs, Trazabilidad y Observabilidad

- **Al cargar (`INFO`):** Registra `modelo_solicitado`, `modelo_efectivo`, `weights_path`, `device`, `imgsz`, `quantize`, `nms`, `fallback_enabled` y `ultralytics_version`.
- **Al verificar `AutoBackend` (`INFO`):** Registra `end2end`, `one2one_cv2` presente y estado de liberación `one2many_cv2_liberada`.
- **Al activar fallback (`WARNING`):** Registra modelo solicitado, modelo respaldo, etapa (`model_init` o `runtime_inference`), dispositivo, excepción exacta y marca temporal UTC (`fallback_timestamp`).
- **Inspección en runtime:** `YoloVehicleDetector.get_runtime_status()` y propiedades (`using_fallback`, `fallback_reason`, `effective_model_path`, `requested_model_path`, `effective_end2end`).

---

## 8. Rendimiento Multi-Cámara e Integración en Vivo (RTX 4050 GPU)

Validado mediante [validate_vision_03c2_gpu.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/scripts/validate_vision_03c2_gpu.py) con métricas persistidas en [vision_03c2_integration_metrics.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/results/vision_03c2_integration_metrics.json) usando imágenes reales históricas (`evidencias_vigia/20261114/CAM-ENTRADA` `720x1280` y `CAM-SALIDA` `640x480`) dentro de `VisionEngineCoordinator` con una única instancia compartida de `YoloVehicleDetector` en `cuda:0`:

| Escenario medido en GPU | `yolo11n.pt` Default (30 frames) | `yolo26x.pt` FP16 NMS-Free Secuencial (40 frames) | `yolo26x.pt` FP16 NMS-Free Concurrente 2 Hilos (20+20) |
| :--- | :---: | :---: | :---: |
| Tiempo de carga inicial | `141.85 ms` | `246.46 ms` | Reutilización instancia compartida |
| Latencia media | `9.892 ms` | **`18.962 ms`** | `885.05 ms` totales (40 frames wall-clock) |
| Mediana / P95 | `9.939 ms` / `10.976 ms` | **`18.936 ms`** / **`20.152 ms`** | — |
| Min / Max | `8.598 ms` / `11.657 ms` | `17.546 ms` / `20.278 ms` | — |
| FPS efectivos | `101.10 FPS` | **`52.74 FPS`** | **`45.20 FPS`** throughput combinado |
| `AutoBackend.end2end` / `one2one_cv2` / `cv2=None` | `False` / `N/A` | **`True` / `True` / `True`** (`torch.float16`) | `True` / `True` / `True` |
| VRAM asignada estable | `52.32 MiB` | `370.86 MiB` (`0.00 MiB` crecimiento post-warmup en 40 pasos) | `434.86 MiB` (`+64.0 MiB` caché concurrente) |
| VRAM pico asignada / reservada | `81.96 MiB` / `98.00 MiB` | **`513.93 MiB`** / **`626.00 MiB`** (`10.2%` de `6140.5 MiB`) | Incluido en medición de ráfaga |
| Errores / Estado salida coordinador | `0` errores | `0` errores (`40/40` `VEHICLE_DETECTED_NO_PLATE`) | `0` errores (`40/40` `VEHICLE_DETECTED_NO_PLATE`) |

- **Clases vehiculares verificadas en ejecución:** En las muestras reales evaluadas durante el benchmark GPU se detectaron vehículos reales de clase `"car"` (`30/30` en baseline y `40/40` secuenciales en experimental) y `"bus"` (referencia `ultralytics/assets/bus.jpg` en pruebas reales de carga y fallback). El mapeo íntegro COCO `{2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}` fue verificado unitariamente con las 4 clases en `PU-YOLO-05`; durante esta fase no se introdujeron capturas reales nuevas con `"motorcycle"` o `"truck"` en el banco GPU.

---

## 9. Pruebas Automatizadas y Cobertura de Regresión

Se creó la suite [test_vision_03c2_yolo26x_integration.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/tests/unit/test_vision_03c2_yolo26x_integration.py) (15 pruebas unitarias, integración, fallback, concurrencia multihilo y GPU CUDA real).

Resultados observados tras la última edición de código con `C:\GEST.PROY.TI\Software\VIGIA_Vision_Systems\.venv_cuda\Scripts\python.exe -m unittest`:

1. **Suite focal `VISION-03C.2` + `YOLO` + `FSM` + Contrato `yolo26x` (`63` pruebas, `5.136s`, exit code `0`):**
   - `tests.unit.test_yolo_detector`: `22/22 PASSED` (`PU-YOLO-01` a `PU-YOLO-16` en CPU y CUDA + resolución de dispositivos).
   - `tests.unit.test_vision_03c2_yolo26x_integration`: `15/15 PASSED` (configuración por entorno, rechazo de inválidos, fallback init/runtime/NaN, guardia anti-bucle, coordinador + FSM, concurrencia multi-hilo con fallback en vivo, GPU real `yolo26x.pt` NMS-Free FP16, fallback real desde `.pt` corrupto y rechazo real `yolo11n(nms=False)`).
   - `tests.unit.test_vision_02a_temporal_fsm`: `22/22 PASSED`.
   - `experiments.yolo26x.tests.test_yolo26x_contract`: `4/4 PASSED`.
2. **Suite ampliada del subsistema de visión (`114` pruebas en `6.249s`, exit code `0`):**
   - `test_vision_stage1_components`, `test_vision_02a_temporal_fsm`, `test_yolo_detector`, `test_vision_03c2_yolo26x_integration`, `test_async_persistence_pilot`, `test_vision_pipeline`, `test_topology_validator`: **`114/114 PASSED`** (incluyendo verificación de importación limpia sin efectos secundarios cuando se ejecuta antes de pruebas PyTorch/CUDA).
3. **Suite de cámaras, repositorios, dominio y USB (`102` pruebas en `9.375s`, exit code `0`):**
   - `test_camera`, `test_camera_stream_and_backend`, `test_detection_repository`, `test_domain_models`, `test_usb_camera_integration`, `test_lan_detector`, `experiments.yolo26x.tests.test_yolo26x_contract`: **`102/102 PASSED`**.
4. **Nota transparente sobre ejecución global `discover` en `tests/unit`:**
   - Una ejecución no filtrada de `unittest discover` arrojó `51` errores de conexión en suites web/auth que exigen PostgreSQL activo en `127.0.0.1:5434` (contenedor Docker apagado durante esta fase) y `1` fallo preexistente de almacén de certificados Windows en `test_trust_ca_logic.test_16`, ajenos a `VISION-03C.2`.

---

## 10. Archivos Modificados y Creados

| Archivo | Acción | Propósito |
| :--- | :--- | :--- |
| [yolo_detector.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py) | Modificado | `resolve_yolo_weights_path`, `YoloDetectorConfig` ampliado, `load_yolo_config_from_env`, verificación NMS-Free, fallback seguro, guardia NaN/Inf y telemetría `get_runtime_status()` |
| [detection/\_\_init\_\_.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/__init__.py) | Modificado | Reexportación pública de `load_yolo_config_from_env` y `resolve_yolo_weights_path` |
| [\_\_init\_\_.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/__init__.py) | Modificado | Reexportación en paquete raíz `VIGIA_Vision` |
| [ingest_service.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py) | Modificado | Conexión de `build_vision_engine_coordinator` con `load_yolo_config_from_env` |
| [.env.example](file:///C:/GEST.PROY.TI/Software/.env.example) | Modificado | Documentación de perfil default (`yolo11n.pt`) y perfil experimental `yolo26x.pt` comentado |
| [test_vision_03c2_yolo26x_integration.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/tests/unit/test_vision_03c2_yolo26x_integration.py) | Nuevo | Suite unitaria, integración, fallback, concurrencia y GPU CUDA (`15` pruebas) |
| [validate_vision_03c2_gpu.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/scripts/validate_vision_03c2_gpu.py) | Nuevo | Script reproducible de validación multi-cámara y fallback en RTX 4050 |
| [vision_03c2_integration_metrics.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/yolo26x/results/vision_03c2_integration_metrics.json) | Nuevo | Registro verificable de latencias, throughput, VRAM, `end2end` y fallback |
| [VIGIA-VISION-03C.2_INTEGRACION_YOLO26X.md](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_vision/VIGIA-VISION-03C.2_INTEGRACION_YOLO26X.md) | Nuevo | Informe técnico de cierre y espejo en `Software/Docs/fase_vision/` |

---

## 11. Cumplimiento de Restricciones No Negociables

- **Modelo de producción:** `yolo11n.pt` sigue siendo el único modelo predeterminado.
- **`.env` productivo:** `Software/.env` intacto.
- **Contratos e infraestructura:** Sin cambios en `RawVehicleDetection`, `VisionResult`, ROI, umbrales (`0.70` / `0.25` / `0.45`), clases COCO, `CameraTemporalStateTracker`, PostgreSQL, Dashboard, enrolamiento móvil ni lógica USB/PUSH.
- **Dependencias Python:** `.venv` y `.venv_cuda` sin modificaciones de paquetes.
- **Trabajo preexistente:** Todos los cambios previos sin commitear se preservaron íntegros.

---

## 12. Procedimiento de Activación Experimental y Rollback Inmediato

### Activación controlada en entorno de pruebas (`Software/.env`)
```dotenv
VIGIA_YOLO_MODEL=yolo26x.pt
VIGIA_YOLO_IMGSZ=640
VIGIA_YOLO_QUANTIZE=16
VIGIA_YOLO_NMS=false
VIGIA_YOLO_DEVICE=cuda:0
VIGIA_YOLO_FALLBACK_ENABLED=true
VIGIA_YOLO_FALLBACK_MODEL=yolo11n.pt
```

### Rollback instantáneo a producción
Eliminar las líneas experimentales (o establecer `VIGIA_YOLO_MODEL=yolo11n.pt` dejando `VIGIA_YOLO_QUANTIZE=` y `VIGIA_YOLO_NMS=` vacíos o sin definir) y reiniciar el servicio backend.

---

## 13. Riesgos Residuales y Limitaciones Observadas

1. **Dependencia de calibración de confianza (`0.70`) en `one2one`:** Como se documentó en `VISION-03C.1`, el cabezal `one2one` de `yolo26x` emite scores más conservadores en escenas oscuras extremas (`SCALE_MODEL_LAB`). El umbral productivo `0.70` se mantuvo intacto por restricción de fase; su ajuste requiere evaluación previa sobre **`VIGIA-BENCH-REAL` (vehículos 1:1)**.
2. **Consumo pico bajo concurrencia:** Dos cámaras compartiendo `yolo26x.pt` FP16 alcanzan `626 MiB` reservado (`513.93 MiB` asignado pico), holgadamente dentro de `6140.5 MiB` en RTX 4050; equipos con `< 2 GiB` de VRAM deberían permanecer en `yolo11n.pt`.
3. **Muestras de clases minoritarias:** Las clases reales presentes en la validación GPU de esta fase correspondieron a `car` y `bus`; la validación de campo en condiciones nocturnas/reales de `motorcycle` y `truck` queda vinculada a `VISION-03B.1` / `VISION-03C.3`.

---

## 14. Prerrequisitos para Evaluar Promoción a Producción (`VISION-03C.3`)

1. Recolectar el dataset **`VIGIA-BENCH-REAL`** con vehículos reales 1:1 en `CAM-ENTRADA` y `CAM-SALIDA` bajo el protocolo `VIGIA-VISION-03B.1` (incluyendo día, noche, lluvia, ángulos parciales y las 4 clases `car`, `motorcycle`, `bus`, `truck`).
2. Ejecutar comparativa ciega `yolo11n.pt` vs `yolo26x.pt` (`imgsz=640`, `FP16`, `nms=False`) con Ground Truth humano para validar precisión, recall y eventual ajuste calibrado del umbral de confianza `0.70`.
3. Integrar `CameraTemporalStateTracker` (`VISION-02A.1`) en la fase correspondiente antes de promover un cambio de modelo predeterminado.

---

## 15. Veredicto Final

**Veredicto inequívoco:** **`APPROVED — EXPERIMENTAL INTEGRATION`**

La integración experimental de **`yolo26x.pt`** queda completamente implementada, aislada bajo configuración reversible, verificada en RTX 4050 (`18.962 ms` promedio, `52.74 FPS`, `end2end=True`, `513.93 MiB` pico VRAM), respaldada por fallback automático probado hacia **`yolo11n.pt`** sin pérdida del fotograma en curso y libre de regresiones sobre el subsistema de visión de VIGÍA.
