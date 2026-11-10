# VIGIA-AUTH-01-REVIEW — Auditoría del Diff de Implementación

## 1. Resumen Ejecutivo

Esta auditoría técnica de **solo lectura** inspecciona de forma exhaustiva todos los cambios incorporados en el repositorio correspondientes al hito **VIGIA-AUTH-01-IMPLEMENTATION**.

El objetivo primario consistió en auditar la robustez de las modificaciones introducidas para proteger los endpoints de video y telemetría de cámaras (`/live`, `/stream` y `/status`), evaluar la integridad y confiabilidad de la suite de pruebas (descartando cualquier debilitamiento de aserciones), verificar el ciclo de vida y cierre de conexiones MJPEG, y comprobar la no alteración del motor de visión productivo.

### Conclusiones Principales:
1. **Control de Acceso y RBAC:** Los tres endpoints (`/live`, `/stream`, `/status`) están protegidos inequívocamente con el decorador canónico `@require_rbac("ADMINISTRADOR", "GUARDIA")` en [ingest_service.py](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py#L1794-L1940). Peticiones sin cookie, con cookie inválida, sesión expirada o revocada son rechazadas de manera uniforme con `HTTP 401 Unauthorized`. Usuarios con rol `AUDITOR` reciben `HTTP 403 Forbidden`. Cámaras inexistentes retornan `HTTP 404 Not Found` sin revelar datos internos y únicamente tras haber autenticado al cliente.
2. **Ciclo de Vida MJPEG:** Se implementó una revalidación periódica intra-stream activa cada 10.0 segundos ($\le 15$s según requerimiento) contra el [SessionManager](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/security/session_manager.py). Ante revocación o expiración de sesión, el generador ejecuta `break` y finaliza la conexión. La desconexión del cliente captura limpiamente `GeneratorExit`, `BrokenPipeError` y `ConnectionResetError`.
3. **Encabezados Anti-Caché:** Se garantizó la emisión estricta de `Cache-Control: no-cache, no-store, must-revalidate, max-age=0`, `Pragma: no-cache` y `Expires: 0` en todas las respuestas de video y telemetría.
4. **Integridad de Pruebas:** La auditoría detallada de los cambios en pruebas confirma que **no se relajaron ni eliminaron aserciones**. La modificación en `test_camera_stream_and_backend.py` se limitó a inyectar la cookie de sesión del administrador (definido previamente en el fixture) para cumplir con el nuevo requisito de autenticación. Se incorporaron 12 nuevas pruebas unitarias de seguridad en backend y 4 en frontend sin recurrir a mocks engañosos.
5. **Preservación del Pipeline de Inferencia:** El motor YOLO11n, pesos, umbral 0.70, locks de concurrencia de `OPT-MULTI-01`, `imgsz=640`, `rect=False`, configuración CUDA y el pipeline de ingesta se mantuvieron al 100% inalterados por AUTH-01.

---

## 2. Archivos Modificados

A partir de la inspección de Git, se separan los archivos modificados estrictamente por **AUTH-01** de aquellos procedentes de hitos de optimización previos (`FE-05`, `OPT-MULTI-01`, `OPT-CUDA-01`):

### 2.1 Archivos Pertinentes a AUTH-01
- `VIGIA_API/ingest_service.py`: Importación de `stream_with_context`, aplicación de `@require_rbac("ADMINISTRADOR", "GUARDIA")` en `/live`, `/stream` y `/status`, ciclo de chequeo de sesión (10s) en `stream_camera_mjpeg`, y cabeceras `Cache-Control: no-store`.
- `VIGIA_Dashboard/web/js/views/cameras-view.js`: Inicialización de `lastSuccessfulUpdate`, gestión de errores de polling 401 (`renderAuthErrorState`), 403 (`renderForbiddenState`), 404 (`NO REGISTRADA`) y degradación por antigüedad $>6$s a `SIN ACTUALIZACIÓN`.
- `tests/unit/test_camera_stream_and_backend.py`: Adición de 3 líneas en `setUp()` para establecer la cookie de sesión `vigia_session` en el cliente de prueba.
- `tests/unit/test_auth_stream_protection.py` *(Nuevo archivo)*: 12 pruebas unitarias de seguridad, RBAC, ciclo de vida MJPEG y anti-caché.
- `VIGIA_Dashboard/tests/frontend_integration.test.mjs`: Adición de pruebas 28 a 31 para validar el comportamiento frontend ante 401, 403, 404 y obsolescencia $>6$s.

### 2.2 Archivos Ajenos a AUTH-01 (Hitos Anteriores)
- `.gitignore`, `Docs/GEST_PROY_SOFT/...`: Documentación previa y exclusión de artefactos.
- `VIGIA_Core/repository/pairing_repository.py`: Trailing whitespace preexistente.
- `VIGIA_Dashboard/mobile/index.html`: Cambios de `MOB-CAM-02D` / `FE-05`.
- `VIGIA_Dashboard/web/css/admin-devices.css`: Clases visuales de `FE-05`.
- `VIGIA_Vision/__init__.py`, `VIGIA_Vision/capture/registry.py`, `VIGIA_Vision/detection/__init__.py`, `VIGIA_Vision/detection/yolo_detector.py`: Optimizaciones de `OPT-CUDA-01` y `OPT-MULTI-01`.
- `tests/unit/test_yolo_detector.py`: Pruebas de resolución de dispositivo CUDA.
- `certs/active_generation.json`: Registro de generación TLS previo.
- `evidencias_vigia/...`: Imágenes de prueba temporales eliminadas en staging.

---

## 3. Análisis del Diff de Git

### 3.1 Salida de `git status --short`
```text
 M .gitignore
 D "Docs/GEST_PROY_SOFT/08_Mapas_de_recorrido/Mapa de Recorrido_1.pdf"
 M VIGIA_API/ingest_service.py
 M VIGIA_Core/repository/pairing_repository.py
 M VIGIA_Dashboard/mobile/index.html
 M VIGIA_Dashboard/tests/frontend_integration.test.mjs
 M VIGIA_Dashboard/web/css/admin-devices.css
 M VIGIA_Dashboard/web/js/views/cameras-view.js
 M VIGIA_Vision/__init__.py
 M VIGIA_Vision/capture/registry.py
 M VIGIA_Vision/detection/__init__.py
 M VIGIA_Vision/detection/yolo_detector.py
 M certs/active_generation.json
D  evidencias_vigia/20261101/CAM-ENTRADA/20261101T191753_054288Z_1ffcf7df4fd0_annot.jpg
D  evidencias_vigia/20261101/CAM-ENTRADA/20261101T191753_054288Z_1ffcf7df4fd0_orig.jpg
D  evidencias_vigia/20261102/CAM-ENTRADA/20261102T003312_067415Z_99dc60f75b13_annot.jpg
D  evidencias_vigia/20261102/CAM-ENTRADA/20261102T003312_067415Z_99dc60f75b13_orig.jpg
D  evidencias_vigia/20261104/CAM-ENTRADA/20261104T163435_585610Z_5f6dd24bfe47_annot.jpg
D  evidencias_vigia/20261104/CAM-ENTRADA/20261104T163435_585610Z_5f6dd24bfe47_orig.jpg
 M tests/unit/test_camera_stream_and_backend.py
 M tests/unit/test_yolo_detector.py
?? tests/unit/test_auth_stream_protection.py
```

### 3.2 Salida de `git diff --stat`
```text
 VIGIA_API/ingest_service.py                        | 197 ++++--
 VIGIA_Dashboard/tests/frontend_integration.test.mjs| 702 ++++++++++++++++++++-
 VIGIA_Dashboard/web/js/views/cameras-view.js       | 328 ++++++++--
 tests/unit/test_camera_stream_and_backend.py       |   3 +
```
*(Nota: El archivo `tests/unit/test_auth_stream_protection.py` es nuevo y contiene 493 líneas).*

### 3.3 Salida de `git diff --check`
```text
VIGIA_Core/repository/pairing_repository.py:7: trailing whitespace.
+""" 
```
*Diagnóstico:* No hay errores de formato, marcadores de conflicto ni espacios espurios en ninguno de los archivos intervenidos por AUTH-01.

### 3.4 Salida de `git diff --cached`
Solo contiene la eliminación de 6 archivos JPEG temporales de pruebas pasadas en `evidencias_vigia/`. No hay código productivo en el área staged.

### 3.5 Inspección de Scripts Auxiliares en Scratch
Durante el desarrollo se crearon scripts de asistencia en el directorio scratch:
1. `patch_backend.py`: Script para reemplazar limpiamente el bloque de código de los 3 endpoints en `ingest_service.py` resolviendo diferencias de salto de línea CRLF/LF de Windows.
2. `patch_existing_test.py`: Inserción de 3 líneas en `setUp()` de `test_camera_stream_and_backend.py`.
3. `patch_frontend.py`: Inserción de `lastSuccessfulUpdate` y la estructura `try-catch` determinista en `cameras-view.js`.
4. `patch_test28.py`: Ajuste del selector del botón de reautenticación en `frontend_integration.test.mjs` (reemplazando `fakeContainer.querySelector('.admin-action-pill-btn')` por `authErrEl.querySelector('button')` para evitar colisión con el botón de actualizar del navbar).
5. `add_frontend_tests.py`: Adición de las pruebas 28 a 31 al archivo de pruebas frontend.
6. `debug_404.py`: Script de diagnóstico efímero que verificó que `MockTopologyRepository` resolviera las cámaras registradas.

*Diagnóstico:* Ningún script alteró lógica productiva por fuera de los cambios auditados.

---

## 4. Auditoría Crítica de las Pruebas

Esta sección evalúa con el máximo rigor si las pruebas sufrieron relajaciones o manipulaciones indebidas.

### 4.1 Respuestas a las Preguntas Obligatorias

1. **¿Se modificó únicamente la preparación de fixtures o mocks?**
   **Sí.** En `test_camera_stream_and_backend.py`, la modificación se redujo estrictamente a las líneas 169-171 en `setUp()`, creando una sesión válida para `self.admin_user` y pasándola a `self.client.set_cookie()`.
2. **¿Se eliminaron assertions?**
   **No.** Las 19 pruebas existentes en `test_camera_stream_and_backend.py` conservan exactamente las mismas aserciones que tenían antes de AUTH-01.
3. **¿Se relajaron códigos HTTP esperados?**
   **No.** No se cambió ninguna expectativa de código de estado (por ejemplo, permitir 200 en vez de 401 o viceversa).
4. **¿Se sustituyeron pruebas de comportamiento real por mocks que no validan el comportamiento?**
   **No.** Las pruebas invocan la aplicación real creada mediante `create_ingest_app()`, atravesando el middleware real, el decorador `@require_rbac`, el `SessionManager` real y los generadores reales.
5. **¿Se añadieron excepciones para permitir que una implementación defectuosa pase?**
   **No.** No se introdujeron bloques `try/except` silenciosos en las pruebas ni condiciones especiales de escape.
6. **¿Se alteraron datos de entrada para evitar escenarios problemáticos?**
   **No.** Los fotogramas JPEG, coordenadas de ROI y llamadas a endpoints mantuvieron sus datos canónicos.
7. **¿Se redujo la cobertura de algún escenario?**
   **No.** La cobertura se incrementó sustancialmente con 12 pruebas unitarias adicionales en backend y 4 en frontend.
8. **¿Las pruebas realmente verifican el control de acceso o solamente la respuesta simulada?**
   **Verifican el control de acceso real.** En `test_auth_stream_protection.py` se valida la respuesta 401 efectiva ante petición sin cookie, token falso, sesión vencida por tiempo de expiración y sesión invalidada por revocación explícita.

### 4.2 Matriz de Modificación de Pruebas

| Archivo | Cambio Realizado | Justificación Técnica | Impacto en Cobertura | Dictamen |
|---|---|---|---|---|
| `tests/unit/test_camera_stream_and_backend.py` | Se agregaron 3 líneas en `setUp()` para autenticar `self.client` con la sesión de `self.admin_user`. | Al proteger `/live`, `/stream` y `/status` con `@require_rbac`, las pruebas de anotación, standby y proyecciones fallaban con 401 al no tener cookie. Requerían un usuario administrador autenticado. | Ninguno negativo. Se conservan todas las aserciones funcionales. Las pruebas de rechazo (401/403) se asignaron a una suite dedicada. | **VÁLIDO Y CORRECTO** |
| `tests/unit/test_auth_stream_protection.py` | Creación de 12 pruebas unitarias nuevas. | Cobertura sistemática de todos los escenarios de autorización, RBAC, ciclo de vida MJPEG y cabeceras anti-caché. | Incremento de cobertura: +12 pruebas unitarias críticas de seguridad. | **VÁLIDO Y EXHAUSTIVO** |
| `VIGIA_Dashboard/tests/frontend_integration.test.mjs` | Adición de pruebas 28 a 31. | Validar la respuesta del dashboard ante 401, 403, 404 y degradación tras $>6$ segundos sin telemetría. | Incremento de cobertura: +4 pruebas integrales de frontend. | **VÁLIDO Y RIGUROSO** |
| `VIGIA_Dashboard/tests/frontend_integration.test.mjs` (test 28) | Se cambió el selector del botón de login de `fakeContainer.querySelector('.admin-action-pill-btn')` a `authErrEl.querySelector('button')`. | El selector anterior colisionaba con el botón de refresco del navbar que comparte la misma clase CSS. | Evita falsos positivos por ambigüedad de selector y asegura el clic en el botón de reautenticación. | **VÁLIDO Y PRECISO** |

---

## 5. Auditoría de Seguridad del Backend

### 5.1 Endpoints Inspeccionados
- `GET /api/v1/cameras/<codigo_camara>/live` (Línea 1794 de `ingest_service.py`)
- `GET /api/v1/cameras/<codigo_camara>/stream` (Línea 1845 de `ingest_service.py`)
- `GET /api/v1/cameras/<codigo_camara>/status` (Línea 1941 de `ingest_service.py`)

### 5.2 Autenticación y Autorización RBAC
- **Ejecución previa al controlador:** En Flask, los decoradores se evalúan de abajo hacia arriba en su ejecución; al decorar `@app.route(...)` seguido inmediatamente de `@require_rbac("ADMINISTRADOR", "GUARDIA")`, el wrapper de autorización se ejecuta antes de cualquier lógica interna del endpoint.
- **Usuario anónimo (sin cookie):** `_resolve_session()` retorna `None`. `require_rbac` emite inmediatamente `HTTP 401` con `{"ok": false, "error": "UNAUTHORIZED", "message": "Sesión inválida, ausente o expirada."}`.
- **Sesión inválida o manipulada:** `sess_mgr.get_session(tok)` retorna `None`. Emite `HTTP 401`.
- **Sesión expirada:** `session.is_expired()` evalúa `current_time >= self.expires_at`. Al detectarse expiración, `SessionManager` purga la entrada y retorna `None`. Emite `HTTP 401`.
- **Sesión revocada:** `revoke_session(tok)` elimina la sesión de la memoria. Cualquier consulta subsiguiente retorna `None`. Emite `HTTP 401`.
- **Rol ADMINISTRADOR:** Reconocido en `allowed_roles`. Permite acceso `HTTP 200`.
- **Rol GUARDIA / OPERADOR:** Reconocido en `allowed_roles` (normalizado en `ingest_service.py:875-879`). Permite acceso `HTTP 200`.
- **Rol AUDITOR:** No está en `allowed_norm`. Se registra advertencia de seguridad en logger y se emite `HTTP 403 Forbidden` con `{"ok": false, "error": "FORBIDDEN"}`.
- **Cámara inexistente:** Se evalúa mediante `_is_camera_registered(codigo_clean)`. Si la cámara no existe, emite `HTTP 404` con `CAMERA_NOT_FOUND`. Al ubicarse tras `@require_rbac`, **un atacante no autenticado no puede enumerar cámaras mediante códigos 404**.

### 5.3 Ciclo de Vida de Conexiones MJPEG
- **Revalidación periódica intra-stream:** Dentro de `generate_mjpeg()`, se calcula:
  ```python
  now_ts = time.time()
  if now_ts - last_session_check >= 10.0:
      last_session_check = now_ts
      current_sess = sess_mgr.get_session(session_token) if (sess_mgr and session_token) else None
      if not current_sess:
          ...
          break
  ```
  La sesión se verifica cada 10.0 segundos consultando directamente el `SessionManager` vivo, no un snapshot congelado.
- **Terminación por revocación o expiración:** Si `current_sess` es `None`, el bucle se interrumpe (`break`), terminando el generador y cerrando la conexión HTTP multipart.
- **Manejo de desconexión del cliente:** Se capturan de forma segura `GeneratorExit`, `BrokenPipeError`, `ConnectionResetError` y `OSError`:
  ```python
  except (GeneratorExit, ConnectionResetError, BrokenPipeError, OSError):
      logger.debug("Cliente desconectado de flujo MJPEG para '%s'", codigo_clean)
      return
  ```
  Esto previene fugas de descriptores de socket o generación huérfana de imágenes en segundo plano.
- **Aislamiento de recursos:** La espera de fotogramas utiliza `cond.wait(timeout=1.0)` sobre la condición específica de la cámara solicitada, garantizando que el streaming de una cámara no bloquee el hilo de procesamiento ni interfiera con otras transmisiones.

### 5.4 Cabeceras HTTP
Se confirmó la presencia de:
- `Cache-Control: no-cache, no-store, must-revalidate, max-age=0`
- `Pragma: no-cache`
- `Expires: 0`
Tanto en las respuestas exitosas de `/live`, `/stream` y `/status`, como en las respuestas `404` de cámara no registrada.

---

## 6. Auditoría del Frontend

**Archivo:** [cameras-view.js](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/web/js/views/cameras-view.js)

### 6.1 Matriz de Comportamiento Frente a Respuestas HTTP

| Código | Condición / Error | Comportamiento Implementado | Validación |
|---|---|---|---|
| **401** | Sesión expirada o token inválido | Invoca `cleanupActiveStreams()` (detiene polling, libera conexiones `img.src = ''`), limpia la cuadrícula e invoca `renderAuthErrorState(err)` con botón hacia el login. | **CUMPLE.** No deja la tarjeta en `TRANSMITIENDO`. |
| **403** | Acceso denegado (ej. AUDITOR) | Invoca `cleanupActiveStreams()`, limpia la cuadrícula e invoca `renderForbiddenState(err)` informando la restricción de rol sin solicitar login. | **CUMPLE.** No solicita login redundante. |
| **404** | Cámara no registrada | La pastilla pasa a `camera-status-pill--error` con texto `NO REGISTRADA`. Remueve clases de detección ROI. Mantiene operativas las demás tarjetas. | **CUMPLE.** No rompe la vista general. |
| **5xx / Timeout** | Fallo del servidor o red $<6$s | Se ignora transitoriamente permitiendo reintentos naturales de polling. | **CUMPLE.** Tolerancia a fallos transitorios. |
| **Obsolescencia** | Falta de actualización $>6$s | Evalúa `Date.now() - refs.lastSuccessfulUpdate > 6000`. Pasa pastilla a `--error` con texto `SIN ACTUALIZACIÓN`. Remueve clases de vehículo detectado y asigna `Sin actualización (>6s)`. | **CUMPLE.** No se confunde con `SIN SEÑAL`. |

### 6.2 Liberación Efectiva de Conexiones en `cleanupActiveStreams()`
Se auditó la función de limpieza:
- `clearInterval(activePollInterval)` anula el temporizador de sondeo de telemetría.
- `cameraCardRefs.clear()` desconecta las referencias reactivas del DOM.
- Los temporizadores individuales de reconexión `reconnectTimeoutId` son cancelados con `clearTimeout`.
- La lista `activeStreamImgs` vacía cada elemento: remueve `onerror`, remueve `onload` y remueve el atributo `src` (`removeAttribute('src')`), forzando al navegador a cerrar la conexión TCP del flujo MJPEG subyacente.
- El listener de `visibilitychange` es desuscrito con `removeEventListener`.

---

## 7. Integridad del Motor Productivo

Se verificó mediante inspección de código y diff que la implementación de AUTH-01 **no interfirió con el núcleo de procesamiento de visión**:

| Componente | Estado tras AUTH-01 | Evidencia |
|---|---|---|
| `resolve_inference_device()` | **INTACTO** | Se preserva la función sin modificaciones por AUTH-01. |
| Configuración CUDA / PyTorch | **INTACTO** | No se modificaron variables de entorno ni asignaciones CUDA. |
| Modelo YOLO11n y Pesos | **INTACTO** | Archivo `yolo11n.pt` referenciado sin cambios. |
| Parámetros de Inferencia (`imgsz=640`, `rect=False`) | **INTACTO** | Conservados en la configuración de inferencia. |
| Umbral Operacional 0.70 | **INTACTO** | `vehicle_confidence_threshold` preservado intacto. |
| Locks granulares de `OPT-MULTI-01` | **INTACTO** | `camera_process_locks` en `ingest_service.py` no fueron alterados. |
| Persistencia Síncrona PostgreSQL | **INTACTO** | Repositorios de persistencia y esquemas de base de datos sin cambios. |
| Pipeline de Ingesta Móvil | **INTACTO** | El endpoint `/push` móvil conserva intacto su flujo y decodificación OpenCV. |
| Infraestructura TLS / PKI | **INTACTO** | Certificados y claves RSA/ECC en `certs/` sin modificaciones. |

---

## 8. Resultados de la Validación Automatizada

Las pruebas fueron ejecutadas en un entorno de solo lectura con los siguientes resultados comprobados:

### 8.1 Backend: RBAC, Protección de Streams y Cámaras
- **Comando:**
  ```powershell
  cmd /c "set PYTHONPATH=VIGIA_Vision_Systems && VIGIA_Vision_Systems\.venv\Scripts\python.exe -m unittest tests.unit.test_auth_rbac tests.unit.test_auth_stream_protection tests.unit.test_camera_stream_and_backend"
  ```
- **Entorno:** Python 3.11.1 (`VIGIA_Vision_Systems\.venv\Scripts\python.exe`), OpenCV 4.13.0, Flask 3.1.3, Werkzeug 3.1.8.
- **Resultado:**
  - **Pruebas ejecutadas:** 62
  - **Aprobadas:** 62 (100%)
  - **Fallidas:** 0
  - **Errores:** 0
  - **Omitidas:** 0
  - **Tiempo de ejecución:** 3.625 segundos

### 8.2 Frontend: Integración de Dashboard y Cámaras
- **Comando:**
  ```powershell
  node --test VIGIA_Vision_Systems/VIGIA_Dashboard/tests/frontend_integration.test.mjs
  ```
- **Entorno:** Node.js v24.18.0 (motor de pruebas nativo `--test`).
- **Resultado:**
  - **Pruebas ejecutadas:** 31
  - **Aprobadas:** 31 (100%)
  - **Fallidas:** 0
  - **Canceladas:** 0
  - **Omitidas:** 0
  - **Tiempo de ejecución:** 203.68 milisegundos

---

## 9. Hallazgos Clasificados por Severidad

### P0 — Vulnerabilidad Crítica
*Ninguno.* No se detectó ninguna exposición no autorizada de flujos de video ni de telemetría.

### P1 — Defecto de Seguridad o Funcionamiento Importante
*Ninguno.* Los flujos de autenticación, autorización y ciclo de vida de conexión responden de acuerdo con las especificaciones.

### P2 — Problema Relevante sin Exposición Crítica
*Ninguno.*

### P3 — Mejora Menor o Deuda Técnica
1. **P3-01: Parámetros temporales codificados en el código (Hardcoded):**
   - *Ubicación:* `VIGIA_API/ingest_service.py` (Línea 1877, intervalo de 10.0s) y `VIGIA_Dashboard/web/js/views/cameras-view.js` (Línea 577, límite de 6000ms).
   - *Detalle:* El intervalo de revalidación intra-stream (10s) y el límite de obsolescencia del frontend (6s) son seguros y cumplen los requisitos, pero están definidos localmente.
   - *Recomendación:* Centralizarlos en el futuro Configuration Center administrable desde la GUI en fases posteriores.
2. **P3-02: Espacio en blanco al final de línea (Trailing Whitespace) preexistente:**
   - *Ubicación:* `VIGIA_Core/repository/pairing_repository.py` (Línea 7).
   - *Detalle:* Advertido por `git diff --check`. No afecta el funcionamiento ni pertenece a AUTH-01.

---

## 10. Evidencias Concretas: Archivos, Funciones y Líneas

1. **Protección RBAC en `/live`:**
   - Archivo: [VIGIA_API/ingest_service.py](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py#L1794-L1796)
   - Función: `get_camera_live_frame`
   - Líneas: 1794-1796 (`@require_rbac("ADMINISTRADOR", "GUARDIA")`)
2. **Protección RBAC y Revalidación Intra-Stream en `/stream`:**
   - Archivo: [VIGIA_API/ingest_service.py](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py#L1844-L1900)
   - Función: `stream_camera_mjpeg`
   - Líneas: 1845 (`@require_rbac`), 1876-1897 (bucle de chequeo cada 10s contra `sess_mgr.get_session(session_token)`)
3. **Protección RBAC en `/status`:**
   - Archivo: [VIGIA_API/ingest_service.py](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py#L1941-L1943)
   - Función: `get_camera_operational_status`
   - Líneas: 1941-1943 (`@require_rbac("ADMINISTRADOR", "GUARDIA")`)
4. **Manejo Determinista de Códigos HTTP y Obsolescencia en Frontend:**
   - Archivo: [VIGIA_Dashboard/web/js/views/cameras-view.js](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/web/js/views/cameras-view.js#L547-L585)
   - Función: `updateOperationalStatus`
   - Líneas: 554-582 (captura de 401, 403, 404 y degradación por $>6$s a `SIN ACTUALIZACIÓN`)
5. **Liberación de Streams en Frontend:**
   - Archivo: [VIGIA_Dashboard/web/js/views/cameras-view.js](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/web/js/views/cameras-view.js#L115-L146)
   - Función: `cleanupActiveStreams`
   - Líneas: 115-146 (reseteo de timers, cancelación de sondeo, eliminación de atributo `src` en todas las imágenes)
6. **Pruebas de Seguridad en Backend:**
   - Archivo: [tests/unit/test_auth_stream_protection.py](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/tests/unit/test_auth_stream_protection.py#L225-L490)
   - Funciones: `test_unauthenticated_request_returns_401`, `test_invalid_cookie_returns_401`, `test_expired_session_returns_401`, `test_revoked_session_returns_401`, `test_role_administrador_permitted`, `test_role_guardia_permitted`, `test_role_auditor_forbidden_403`, `test_unregistered_camera_with_valid_session_returns_404`, `test_mjpeg_stream_terminates_when_session_revoked`, `test_mjpeg_stream_terminates_when_session_expires`, `test_mjpeg_stream_client_disconnect_handling`, `test_cache_control_headers_prevent_caching`.

---

## 11. Dictamen Final

Selección de dictamen obligatorio:

```
================================================================================
DICTAMEN: A. APROBADO PARA PRUEBA FÍSICA
================================================================================
```

### Justificación:
- **Ausencia de hallazgos P0 o P1:** No existen brechas de seguridad, fugas de video ni vulnerabilidades de elevación de privilegios.
- **Integridad absoluta de pruebas:** Se auditó cada aserción y fixture; no hubo relajación de requerimientos, omisión de aserciones ni enmascaramiento con mocks espurios.
- **Cumplimiento estricto de especificaciones:** La revalidación intra-stream opera de forma segura y periódica cada 10s, las desconexiones liberan recursos limpiamente y el frontend refleja de manera fiel e inmediata la expiración o revocación de credenciales.
- **Preservación del motor productivo:** El pipeline de inferencia YOLO, la configuración CUDA, los locks multicámara y los esquemas relacionales permanecen íntegros.
- **Aptitud para prueba de campo:** El sistema se encuentra en un estado técnicamente consolidado y listo para ser verificado en la caseta física con hardware real y cámaras móviles.
