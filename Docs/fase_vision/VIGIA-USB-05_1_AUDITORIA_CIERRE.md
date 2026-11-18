# VIGIA-USB-05.1 — Auditoría de Evidencias y Cierre Técnico

**ID del Documento:** `VIGIA-USB-05-1-AUDITORIA-CIERRE`  
**Fecha de Ejecución:** 13 de Noviembre de 2026  
**Fase del Proyecto:** VIGÍA Vision Systems — Fase Visión / Captura USB Local  
**Estado del Cierre:** **APPROVED WITH OBSERVATIONS (APROBADO CON OBSERVACIONES TÉCNICAS)**  
**Versión del Entorno:** PostgreSQL 16.15 (Docker x86_64, `vigia-db`), OpenCV 4.13.0, PyTorch 2.6.0+cu124 (NVIDIA GeForce RTX 4050 Laptop GPU, 6140 MB VRAM), Python 3.11, Node.js v24.18.0, Windows 11 Home  

---

## 1. Resumen Ejecutivo y Dictamen de Cierre

La auditoría técnica **VIGIA-USB-05.1** ha inspeccionado rigurosamente los artefactos, evidencias empíricas, código fuente, aserciones de prueba y estado de control de versiones resultantes de las fases **VIGIA-USB-01** a **VIGIA-USB-05**.

El objetivo es determinar si la integración de cámaras USB locales en VIGÍA Vision Systems puede ser declarada técnicamente cerrada de forma segura, determinista y sin regresiones en la infraestructura móvil QR preexistente.

### Dictamen de Cierre

> [!IMPORTANT]
> **DICTAMEN: APPROVED WITH OBSERVATIONS (APROBADO CON OBSERVACIONES TÉCNICAS).**  
> Todos los criterios funcionales críticos (detección de hardware físico, enrolamiento transaccional ACID en PostgreSQL, streaming MJPEG con inferencia YOLO en GPU CUDA, revocación determinista con liberación física del descriptor de hardware, y compatibilidad bidireccional fail-safe con cámaras móviles QR) están **demostrados de forma empírica y reproducible**.  
> Se emite la calificación con observaciones técnicas secundarias debidamente documentadas respecto a la cobertura de pruebas visuales directas en navegador real y el alcance de la prueba de reinicio en el runner E2E.

---

## 2. Auditoría del Ejecutor E2E (`tests/e2e/test_usb_e2e_physical.py`)

Se realizó una inspección estática y dinámica línea por línea del script ejecutor [`tests/e2e/test_usb_e2e_physical.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/tests/e2e/test_usb_e2e_physical.py).

### 2.1. Calidad de Aserciones y Validación de Resultados Reales

| Parámetro Evaluado | Hallazgo de Auditoría | Calidad |
|---|---|:---:|
| **Comprobación de resultados reales** | Las aserciones no emplean mocks ni valores fijos simulados; evalúan el código de estado HTTP (`200`, `201`, `401`, `403`, `404`, `409`) y el contenido de las respuestas JSON. | **ALTA** |
| **No conversión de errores en éxitos** | Los bloques `assert resp.status_code == ...` fallan inmediatamente ante cualquier desviación. No existen bloques `try/except` que capturen excepciones para marcar pruebas como pasadas silenciosamente. | **ESTRICTA** |
| **Obtención de identificadores** | Los UUIDs de solicitud y credencial se extraen del cuerpo de la respuesta (`id_credencial`, `id_solicitud`) y se correlacionan directamente contra las tablas `camara_credencial` y `camera_pairing_request` de PostgreSQL. | **ROBUSTA** |
| **Validación estructural JSON** | Se comprueban claves obligatorias (`ok`, `dispositivos`, `cameras`, `estado`, `is_transmitting`, `error`). | **ALTA** |
| **Verificación directa en PostgreSQL** | Cada mutación (enrolamiento, revocación, sustitución móvil) ejecuta consultas directas vía `psycopg2` contra `vigia-db`: comprueba `camara.uri_stream`, `camara_credencial.activa`, `clave_cifrado_id = 'usb-local-pull'` y el objeto JSONB `dispositivo_info`. | **EXHAUSTIVA** |
| **Prueba de stream MJPEG** | No valida una imagen estática. Consume el flujo HTTP `multipart/x-mixed-replace`, procesa chunks continuos, extrae 5 delimitadores JPEG (`\xff\xd8` a `\xff\xd9`), decodifica los cuadros con `cv2.imdecode` en matrices `(480, 640, 3)` y verifica el avance de la secuencia YOLO. | **EXHAUSTIVA** |
| **Transición de credenciales móviles** | Verifica el ciclo completo: reclamo de token QR, revocación automática de USB previa, rechazo 409 ante conflicto de carril, reemplazo explícito con `confirm_replace: True`, y rechazo HTTP 401 del token móvil revocado. | **ROBUSTA** |

### 2.2. Aserciones Debilitadas o Condiciones Omitidas Identificadas

1. **Prueba de Reinicio (`test_suite_e`):**  
   En `test_usb_e2e_physical.py`, la prueba verifica la persistencia relacional (`COUNT(*) == 1`) y que el worker esté transmitiendo. No obstante, **no mata ni reinicia el proceso del daemon Flask en caliente dentro del script E2E**.  
   *Mitigación existente:* La prueba unitaria e integración [`test_startup_recovery_of_persisted_usb_slot`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/tests/unit/test_usb_camera_integration.py#L1066) sí inicializa una instancia limpia de la aplicación con `start_pull_workers=True` y demuestra la recuperación automática desde PostgreSQL.
2. **Encabezado `Origin` en CSRF:**  
   El runner `test_usb_e2e_physical.py` omitió una prueba explícita de inyección de encabezado `Origin` foráneo hacia endpoints USB, aunque el mecanismo existe y fue validado independientemente.

---

## 3. Matriz de Cobertura de Requisitos

A continuación se detalla la clasificación individual de los 8 requisitos de auditoría especificados en la directriz:

| Requisito | Clasificación | Evidencia y Justificación Técnica |
|---|:---:|---|
| **1. CSRF** | **VERIFIED** | Demostrado en [`ingest_service.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py#L750) mediante el decorador `@app.before_request def validate_csrf()`. Ante peticiones mutacionales (`POST`) con cookie `vigia_session` y un encabezado `Origin: https://attacker.site`, el servidor responde de forma determinista con `HTTP 403 Forbidden` (`{"error": "CSRF_ERROR"}`). |
| **2. Enrolamiento concurrente** | **VERIFIED** | Protegido a nivel backend por `_usb_enrollment_lock = threading.Lock()` en `ingest_service.py`. En la fase [VIGIA-USB-03](file:///C:/GEST.PROY.TI/Software/Docs/fase_vision/VIGIA-USB-03_VALIDACION_OPERATIVA.md#L114) se ejecutó la prueba con dos hilos sincronizados mediante `threading.Barrier` (hilo ganador: `HTTP 201`, hilo perdedor: `HTTP 409 USB_DEVICE_IN_USE`). En USB-05 se confirmó la colisión secuencial inter-carril. |
| **3. Desconexión física durante captura** | **VERIFIED** | Implementado en `CameraPullWorker._run_capture_loop()` mediante contador de cuadros vacíos consecutivos (`max_consecutive_empty = 5`). Demostrado en [`tests/unit/test_usb_camera_integration.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/tests/unit/test_usb_camera_integration.py#L725) (`test_worker_disconnect_clears_stale_frame_releases_and_recovers`), donde la desconexión física libera el descriptor, purga `_latest_camera_frames` y entra en sondeo exponencial pasivo. |
| **4. Revocación repetida** | **VERIFIED** | Verificado en la Suite G de `test_usb_e2e_physical.py`. La segunda invocación de `POST /api/v1/devices/<id>/revoke` sobre una credencial ya inactiva es rechazada inmediatamente con `HTTP 404 Not Found` (`{"error": "CREDENTIAL_NOT_FOUND_OR_INACTIVE"}`). |
| **5. Recuperación después del reinicio** | **VERIFIED** | Verificado a nivel de bootstrap en [`ingest_service.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py#L4575) y probado formalmente en `test_startup_recovery_of_persisted_usb_slot()`. El servidor consulta las cámaras con `uri_stream LIKE 'usb://%'` al arrancar e instancia los workers automáticamente. |
| **6. Visualización MJPEG en navegador real** | **PARTIAL** | El transporte MJPEG (`multipart/x-mixed-replace`), los delimitadores binarios JPEG, la integridad de imagen (640x480x3) y la inferencia YOLO se verificaron al 100% mediante cliente HTTP E2E. En frontend se validó la integración DOM en [`usb_camera_dashboard.test.mjs`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/tests/usb_camera_dashboard.test.mjs). Sin embargo, no se generó una captura de pantalla visual de un navegador headless (Playwright/Puppeteer) renderizando el canvas/img en vivo. |
| **7. Errores de consola del navegador** | **PARTIAL** | La suite Node.js (31 pruebas de integración frontend) monitorea las excepciones en la capa de servicios sin registrar errores. No obstante, no se extrajeron logs directos de `window.console` desde un navegador Chromium/Edge en ejecución interactiva durante USB-05. |
| **8. Autenticación y RBAC** | **VERIFIED** | Verificado exhaustivamente: peticiones sin sesión responden `HTTP 401 Unauthorized`. Peticiones mutacionales con usuario `guardia_dev` (rol `OPERADOR`) responden `HTTP 403 Forbidden`. Sólo `ADMINISTRADOR` (`admin_dev`) tiene autorización para sondear, enrolar o revocar dispositivos USB. |

---

## 4. Auditoría Técnica de la Cadena de Video

La infraestructura de streaming e inferencia para cámaras USB opera de forma desacoplada y sin duplicación de recursos:

```
[Hardware USB Local (Webcam Index 0)]
                 │  (DirectShow DSHOW, cv2.VideoCapture)
                 ▼
      [CameraPullWorker] (VIGIA_API/usb_worker.py)
                 │
                 ├──► VisionEngineCoordinator.process_camera_step()
                 │            │  (Inferencia YOLO11n en CUDA:0)
                 │            ▼
                 │     Detecciones / Bounding Boxes / ROI
                 │            │
                 ▼            ▼
   [_latest_camera_frames] (Fotograma Anotado en Memoria)
                 │
                 ▼  (Condition Variable notify_all)
   [Endpoint /cameras/<codigo>/stream] (MJPEG multipart/x-mixed-replace)
                 │
                 ▼  (HTTP Streaming continuo)
   [Dashboard Frontend <img src="...">] (cameras-view.js)
```

1. **Captura OpenCV:**  
   Gestionada exclusivamente por [`CameraPullWorker`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/usb_worker.py). Utiliza el backend `cv2.CAP_DSHOW` en Windows para evitar bloqueos del driver de Media Foundation. Lee fotogramas a la cadencia nominal configurada (`USB_TARGET_FPS = 30`).
2. **Inferencia y Anotaciones YOLO:**  
   El worker **no implementa una segunda instancia de YOLO**. Reutiliza la llamada oficial `coordinator.process_camera_step(codigo_camara, raw_frame)`. El modelo `yolo11n.pt` corre en la GPU NVIDIA RTX 4050 (`cuda:0`), calcula la intersección con las áreas de interés (`ROI-ENT` / `ROI-SAL`) y dibuja las cajas delimitadoras y etiquetas sobre el cuadro.
3. **Transporte HTTP MJPEG:**  
   El endpoint `/api/v1/cameras/<codigo_camara>/stream` consume directamente el búfer compartido `_latest_camera_frames`, sincronizado mediante variables de condición (`threading.Condition`). Se garantiza transporte continuo sin polling agresivo ni latencia acumulada.
4. **Decodificación y Presentación:**  
   El Dashboard en [`cameras-view.js`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/web/js/views/cameras-view.js) reutiliza el componente estándar de visualización de cámaras lógicas. El navegador decodifica nativamente el stream HTTP sin necesidad de bibliotecas externas pesadas ni reproductores WebRTC/HLS.

---

## 5. Auditoría Git y Estado de Repositorio

Se ejecutó la inspección del árbol de trabajo en `VIGIA_Vision_Systems` y `BD`:

### 5.1. Resumen de Cambios (`git status --short`)

```
 M VIGIA_API/ingest_service.py
 M VIGIA_API/pull_worker.py
 M VIGIA_Core/repository/pairing_repository.py
 M VIGIA_Dashboard/web/css/admin-devices.css
 M VIGIA_Dashboard/web/js/components/devices-table.js
 M VIGIA_Dashboard/web/js/services/api-service.js
 M VIGIA_Dashboard/web/js/services/device-service.js
 M VIGIA_Dashboard/web/js/views/devices-view.js
 M VIGIA_Vision/capture/__init__.py
 M VIGIA_Vision/capture/sources.py
 M VIGIA_Vision/runtime/coordinator.py
 M certs/active_generation.json
 M certs/audit/ca_issuance.jsonl
?? Docs/fase_vision/VIGIA-USB-02_IMPLEMENTACION_BACKEND.md
?? Docs/fase_vision/VIGIA-USB-03_VALIDACION_OPERATIVA.md
?? Docs/fase_vision/VIGIA-USB-04_INTEGRACION_DASHBOARD.md
?? Docs/fase_vision/VIGIA-USB-05_VALIDACION_E2E_FISICA.md
?? VIGIA_API/usb_worker.py
?? VIGIA_Dashboard/tests/usb_camera_dashboard.test.mjs
?? start_signer.py
?? tests/e2e/
?? tests/unit/test_usb_camera_integration.py
```

En el repositorio `BD`:
```
 M scripts/provision_topology.py
```

### 5.2. Comparación Criptográfica de Informes Duplicados (SHA-256)

| Documento | Hash en `Software/Docs/fase_vision/` | Hash en `VIGIA_Vision_Systems/Docs/` | Coincidencia |
|---|---|---|:---:|
| **VIGIA-USB-02** | `0b4236b296cd51db63e287801d7f678d879dcf3d260317c4be1719f84b4eba24` | `4da8b56dc0d98a8ae8afaa0649662a4fdf5712006b4f4dec2fea83e8c7996e6d` | **DISCREPANCIA (1 enlace)** |
| **VIGIA-USB-03** | `ecf3d1b04309528809dc18cffb9b895bf11e91f7dd00c86272c3fd81f99c07f2` | `ecf3d1b04309528809dc18cffb9b895bf11e91f7dd00c86272c3fd81f99c07f2` | **IDÉNTICOS (OK)** |
| **VIGIA-USB-04** | `a070607fccbe0ca8788b27110b72b1c844856d081ebf4f7458f6f79677db619c` | `a070607fccbe0ca8788b27110b72b1c844856d081ebf4f7458f6f79677db619c` | **IDÉNTICOS (OK)** |
| **VIGIA-USB-05** | `a197172bf2a90fd5658f92ecb162340a3c8837d2b2354222fe295d8e6924a760` | `a197172bf2a90fd5658f92ecb162340a3c8837d2b2354222fe295d8e6924a760` | **IDÉNTICOS (OK)** |

*Nota sobre VIGIA-USB-02:* La única diferencia entre ambos archivos radica en la ruta relativa del hipervínculo hacia el documento predecesor USB-01 (sin diferencias conceptuales ni técnicas).

### 5.3. Integridad de Secretos y Configuración

- **Root CA Private Key (`vigia_root_ca_key.pem`):** Intacta, no modificada ni agregada a staging.
- **Archivo `.env`:** Intacto, sin alteraciones de contraseñas de PostgreSQL ni claves simétricas HMAC.
- **Actualización dinámica de generación TLS:** `certs/active_generation.json` y `certs/audit/ca_issuance.jsonl` fueron actualizados legítimamente por `IsolatedSigner` a través de su Named Pipe seguro al detectar la asignación de la dirección IP de red `192.168.1.66`.

---

## 6. Riesgos Residuales y Recomendaciones de Operación

1. **Monitoreo de Desconexión en Producción:**  
   El mecanismo de backoff exponencial en `CameraPullWorker` reconecta la cámara automáticamente al ser enchufada de nuevo. Se recomienda mantener alertas en el Dashboard ante transiciones a `SIN_SEÑAL` prolongadas (>30 s).
2. **Índice de Dispositivo USB en Entornos Multi-Cámara:**  
   En Windows, los índices numéricos de DirectShow (`0`, `1`, etc.) dependen del orden de enumeración del bus USB del sistema operativo. Si se conectan múltiples cámaras idénticas, se sugiere etiquetarlas físicamente y verificar el selector visual de sondeo de hardware antes de fijar la asignación a carriles.
3. **Prueba Visual Automatizada en CI/CD:**  
   Para futuras fases, se sugiere incorporar Playwright o Puppeteer en el pipeline de integración continua para capturar de forma desatendida screenshots del elemento `<img>` del Dashboard y registrar los eventos de `console.error`.

---

## 7. Dictamen Final de Cierre

La funcionalidad de integración de cámaras USB locales en **VIGÍA Vision Systems** ha cumplido satisfactoriamente todos los criterios funcionales, de seguridad, de base de datos y de coexistencia:

1. Permite detectar, enrolar y revocar cámaras USB desde la interfaz gráfica unificada del Dashboard.
2. Persiste la configuración de forma atómica en PostgreSQL 16 sin interferir con las cámaras móviles.
3. Alimenta el pipeline YOLO en tiempo real con aceleración GPU CUDA.
4. Libera deterministamente los descriptores de hardware en Windows al detener el worker o revocar la credencial.
5. Gestiona las colisiones y sustituciones entre orígenes móviles y físicos con diálogo de confirmación explícita.

**Estado Técnico:** **APPROVED WITH OBSERVATIONS**  
La integración de cámaras USB queda formalmente validada y apta para operación.
