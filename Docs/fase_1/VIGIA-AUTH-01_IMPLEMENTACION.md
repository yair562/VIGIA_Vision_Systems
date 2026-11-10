# VIGIA-AUTH-01-IMPLEMENTATION — Protección de Video y Telemetría

## 1. Resumen Ejecutivo

En cumplimiento de las directrices de seguridad de **VIGÍA Vision Systems**, se implementó la protección integral de control de acceso basada en roles (RBAC) sobre los tres endpoints de video en vivo y telemetría de cámaras:

- `GET /api/v1/cameras/<codigo>/stream` (flujo continuo multipart/x-mixed-replace MJPEG)
- `GET /api/v1/cameras/<codigo>/live` (fotograma JPEG individual anotado)
- `GET /api/v1/cameras/<codigo>/status` (telemetría operativa y de visión en tiempo real)

Previo a esta intervención, estos endpoints carecían de verificación de sesión HTTP, permitiendo la visualización de transmisiones y estado operativo sin credenciales válidas. Tras la implementación:

1. **Autenticación estricta y RBAC:** Únicamente usuarios autenticados con rol `ADMINISTRADOR` o `GUARDIA` (u `OPERADOR`) pueden acceder. Peticiones sin sesión, con tokens falsos, expirados o revocados reciben `HTTP 401 Unauthorized`. Usuarios con rol `AUDITOR` reciben `HTTP 403 Forbidden`.
2. **Validación periódica intra-stream:** El generador MJPEG valida cada 10 segundos ($\le 15$s según requerimiento) la vigencia y roles de la sesión activa contra el `SessionManager`. Si la sesión expira o es revocada explícitamente, la transmisión finaliza de inmediato liberando los recursos del servidor.
3. **Manejo limpio de desconexión:** Se envuelve el generador en `stream_with_context` y se capturan limpiamente excepciones de desconexión del cliente (`GeneratorExit`, `BrokenPipeError`, `ConnectionResetError`) previniendo fugas de memoria o hilos huérfanos.
4. **Encabezados anti-almacenamiento:** Se incluyeron encabezados `Cache-Control: no-cache, no-store, must-revalidate, max-age=0`, `Pragma: no-cache` y `Expires: 0` en todas las respuestas de video y telemetría.
5. **Frontend reactivo y determinista:** En el dashboard (`cameras-view.js`), ante `401` se cancela el polling, se liberan las conexiones de imagen activas, se elimina cualquier indicación visual de `TRANSMITIENDO` y se invoca `renderAuthErrorState(err)` con redirección a login. Ante `403` se renderiza `renderForbiddenState(err)` sin exigir login innecesario. Ante fallas de actualización $>6$ segundos, se degrada a `SIN ACTUALIZACIÓN` (pastilla `--error`) sin confundir la falla de comunicación con pérdida física de señal (`SIN SEÑAL`).
6. **Invariantes arquitectónicas preservadas:** El motor YOLO, `coordinator.py`, locks de concurrencia, esquemas relacionales, certificados TLS y el umbral de inferencia 0.70 permanecieron intactos. No se introdujeron JWTs en memoria ni tokens en URL.

---

## 2. Modificaciones en Backend

**Archivo modificado:** `VIGIA_Vision_Systems/VIGIA_API/ingest_service.py`

### 2.1 Importación de `stream_with_context`
Se incorporó `stream_with_context` desde Flask para garantizar el enlace del contexto de la petición durante la iteración del generador HTTP:

```python
from flask import Flask, Response, g, jsonify, request, send_from_directory, stream_with_context
```

### 2.2 Aplicación del decorador `@require_rbac("ADMINISTRADOR", "GUARDIA")`
Se aplicó la protección RBAC en la definición de las tres rutas de streaming y telemetría:

```python
@app.route("/api/v1/cameras/<codigo_camara>/live", methods=["GET"])
@require_rbac("ADMINISTRADOR", "GUARDIA")
def get_camera_live_frame(codigo_camara: str):
    ...
```

```python
@app.route("/api/v1/cameras/<codigo_camara>/stream", methods=["GET"])
@require_rbac("ADMINISTRADOR", "GUARDIA")
def stream_camera_mjpeg(codigo_camara: str):
    ...
```

```python
@app.route("/api/v1/cameras/<codigo_camara>/status", methods=["GET"])
@require_rbac("ADMINISTRADOR", "GUARDIA")
def get_camera_operational_status(codigo_camara: str):
    ...
```

### 2.3 Validación periódica de sesión en generador MJPEG
Dentro de `stream_camera_mjpeg`, se extrae el token de sesión y se verifica contra el `SessionManager` cada 10 segundos:

```python
session_token = _extract_session_token()
sess_mgr = app.config.get("SESSION_MANAGER")

def generate_mjpeg():
    cond = _get_camera_condition(codigo_clean)
    last_seq = -1
    standby_sent_time = 0.0
    last_session_check = time.time()

    try:
        while True:
            # Comprobación periódica de sesión (máximo 15s; ejecutamos cada 10s)
            now_ts = time.time()
            if now_ts - last_session_check >= 10.0:
                last_session_check = now_ts
                current_sess = sess_mgr.get_session(session_token) if (sess_mgr and session_token) else None
                if not current_sess:
                    logger.info(
                        "Sesión finalizada o revocada durante stream MJPEG para '%s' (token: %s...)",
                        codigo_clean,
                        session_token[:8] if session_token else "none",
                    )
                    break
                user_roles = {current_sess.rol.upper(), current_sess.db_rol.upper()}
                if "ADMINISTRADOR" not in user_roles and "GUARDIA" not in user_roles and "OPERADOR" not in user_roles:
                    logger.warning(
                        "Rol no autorizado detectado durante stream MJPEG para '%s' (rol: %s)",
                        codigo_clean,
                        current_sess.rol,
                    )
                    break
            ...
```

### 2.4 Encabezados de respuesta anti-almacenamiento
En todas las respuestas de fotogramas, flujos y estados, se añaden las directivas canónicas anti-caché:

```python
headers = {
    "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}
```

---

## 3. Modificaciones en Frontend

**Archivo modificado:** `VIGIA_Vision_Systems/VIGIA_Dashboard/web/js/views/cameras-view.js`

### 3.1 Seguimiento temporal por tarjeta (`lastSuccessfulUpdate`)
En `cameraCardRefs`, se inicializa y actualiza la estampa de tiempo de recepción exitosa de telemetría:

```javascript
const camRefs = {
  card,
  mediaBox,
  statusPill,
  statusText,
  detInfo,
  playbackErrorOverlay,
  playbackBadge,
  playbackMsg,
  retryBtn,
  streamImg,
  reconnectTimeoutId: null,
  reconnectAttempts: 0,
  lastSuccessfulUpdate: Date.now()
};
```

### 3.2 Gestión determinista de errores en `updateOperationalStatus()`
Se reemplazó el bloque `catch (_)` silencioso por una gestión estricta de códigos de estado HTTP y antigüedad de datos:

```javascript
let statusData;
try {
  statusData = await apiService.getCameraStatus(code);
  refs.lastSuccessfulUpdate = Date.now();
} catch (pollErr) {
  if (isViewDestroyed || currentGeneration !== viewGenerationToken) {
    return;
  }
  // 401: Sesión expirada o inválida
  if (pollErr instanceof AuthError || pollErr?.status === 401) {
    cleanupActiveStreams();
    renderAuthErrorState(pollErr);
    return;
  }
  // 403: Usuario sin autorización (p. ej. AUDITOR)
  if (pollErr instanceof ForbiddenError || pollErr?.status === 403) {
    cleanupActiveStreams();
    renderForbiddenState(pollErr);
    return;
  }
  // 404: Cámara no registrada en el sistema
  if (pollErr?.status === 404) {
    refs.statusPill.className = 'camera-status-pill camera-status-pill--error';
    refs.statusText.textContent = 'NO REGISTRADA';
    refs.card.classList.remove('camera-card--vehicle-detected', 'camera-card--roi-active');
    refs.mediaBox.classList.remove('camera-card-media--roi-active');
    refs.detInfo.textContent = 'Cámara no encontrada';
    continue;
  }
  // 5xx / Timeout / Falla de red: Evaluar límite de antigüedad de 6 segundos
  const lastUpdate = refs.lastSuccessfulUpdate || 0;
  const ageMs = Date.now() - lastUpdate;
  if (lastUpdate > 0 && ageMs > 6000) {
    refs.statusPill.className = 'camera-status-pill camera-status-pill--error';
    refs.statusText.textContent = 'SIN ACTUALIZACIÓN';
    refs.card.classList.remove('camera-card--vehicle-detected', 'camera-card--roi-active');
    refs.mediaBox.classList.remove('camera-card-media--roi-active');
    refs.detInfo.textContent = 'Sin actualización (>6s)';
  }
  continue;
}
```

---

## 4. Estrategia de Autorización de Video y Telemetría

La política unificada implementada se rige bajo la siguiente matriz de control:

| Rol de Usuario | Estado de Sesión | `/live` | `/stream` | `/status` | Comportamiento Frontend |
|---|---|---|---|---|---|
| **ADMINISTRADOR** | Activa | **200 OK** | **200 OK** | **200 OK** | Transmisión fluida y telemetría en tiempo real |
| **GUARDIA** | Activa | **200 OK** | **200 OK** | **200 OK** | Transmisión fluida y telemetría en tiempo real |
| **AUDITOR** | Activa | **403 Forbidden** | **403 Forbidden** | **403 Forbidden** | Renderiza `renderForbiddenState` sin solicitar login |
| **Cualquiera** | Ausente / No Cookie | **401 Unauthorized** | **401 Unauthorized** | **401 Unauthorized** | Renderiza `renderAuthErrorState` con botón a login |
| **Cualquiera** | Expirada / Revocada | **401 Unauthorized** | **401 Unauthorized** | **401 Unauthorized** | Detiene polling, limpia streams y pide login |
| **Autorizado** | Cámara Inexistente | **404 Not Found** | **404 Not Found** | **404 Not Found** | Marca tarjeta como `NO REGISTRADA` |

---

## 5. Ciclo de Vida y Cierre de Conexiones MJPEG

Para prevenir fugas de conexiones o consumo descontrolado de hilos ante streaming continuo:
1. **Validación previa al apretón de manos:** `@require_rbac` valida la cookie antes de instanciar el generador multipart. Si es inválida, responde JSON 401 inmediatamente.
2. **Chequeo periódico (10s):** Durante el bucle de streaming, cada 10 segundos se consulta `sess_mgr.get_session(session_token)`. Si la sesión expiró por TTL absoluto, inactividad o fue destruida por logout/revocación en base de datos o memoria, el generador ejecuta `break` y finaliza limpiamente.
3. **Manejo de `GeneratorExit`:** Cuando el navegador o cliente cierra la pestaña, desconecta la conexión HTTP o abandona la vista, Werkzeug o Flask cierran el generador, capturado explícitamente en `except (GeneratorExit, ConnectionResetError, BrokenPipeError, OSError):` liberando buffers y locks de condición.
4. **Desmontaje en el Frontend (`cleanupActiveStreams`):** Ante 401, 403 o cambio de ruta, `cleanupActiveStreams()` vacía `streamImg.src`, cancela intervalos de polling activos y resetea temporizadores de reconexión.

---

## 6. Resultados de Pruebas Automatizadas

Se diseñó e implementó un conjunto de pruebas unitarias exhaustivas en Python (`test_auth_stream_protection.py`) y Node.js (`frontend_integration.test.mjs`), cubriendo el 100% de los requisitos estipulados.

### 6.1 Pruebas de Seguridad en Backend (`test_auth_stream_protection.py`)
Comando ejecutado:
```powershell
cmd /c "set PYTHONPATH=VIGIA_Vision_Systems && VIGIA_Vision_Systems\.venv\Scripts\python.exe -m unittest tests.unit.test_auth_stream_protection"
```
**Resultado: 12 de 12 pruebas PASADAS (100% OK en 0.125s)**

| Caso de Prueba | Resultado | Descripción |
|---|---|---|
| `test_unauthenticated_request_returns_401` | **PASÓ** | Rechazo HTTP 401 sin cookie en `/live`, `/stream` y `/status`. |
| `test_invalid_cookie_returns_401` | **PASÓ** | Rechazo HTTP 401 con token falso o manipulado. |
| `test_expired_session_returns_401` | **PASÓ** | Rechazo HTTP 401 ante expiración por tiempo de vida. |
| `test_revoked_session_returns_401` | **PASÓ** | Rechazo HTTP 401 tras revocación explícita con `revoke_session`. |
| `test_role_administrador_permitted` | **PASÓ** | Acceso exitoso HTTP 200 para `ADMINISTRADOR`. |
| `test_role_guardia_permitted` | **PASÓ** | Acceso exitoso HTTP 200 para `GUARDIA`. |
| `test_role_auditor_forbidden_403` | **PASÓ** | Rechazo HTTP 403 Forbidden para rol `AUDITOR`. |
| `test_unregistered_camera_with_valid_session_returns_404` | **PASÓ** | HTTP 404 al consultar cámaras no registradas con sesión válida. |
| `test_mjpeg_stream_terminates_when_session_revoked` | **PASÓ** | El generador MJPEG finaliza de inmediato si la sesión es revocada durante la transmisión activa. |
| `test_mjpeg_stream_terminates_when_session_expires` | **PASÓ** | El generador MJPEG finaliza de inmediato si la sesión vence durante la transmisión activa. |
| `test_mjpeg_stream_client_disconnect_handling` | **PASÓ** | Manejo limpio de `GeneratorExit` sin excepciones huérfanas. |
| `test_cache_control_headers_prevent_caching` | **PASÓ** | Confirmación de `no-store, no-cache, must-revalidate, max-age=0` en encabezados. |

### 6.2 Pruebas en Frontend (`frontend_integration.test.mjs`)
Comando ejecutado:
```powershell
node --test VIGIA_Vision_Systems/VIGIA_Dashboard/tests/frontend_integration.test.mjs
```
**Resultado: 31 de 31 pruebas PASADAS (100% OK en 0.199s)**

| Caso de Prueba | Resultado | Descripción |
|---|---|---|
| `Test 28 (VIGIA-AUTH-01)` | **PASÓ** | 401 en polling detiene polling, libera streams y muestra pantalla de reautenticación con botón a login. |
| `Test 29 (VIGIA-AUTH-01)` | **PASÓ** | 403 en polling detiene polling y muestra acceso denegado sin exigir login innecesario. |
| `Test 30 (VIGIA-AUTH-01)` | **PASÓ** | 404 en status marca la tarjeta como `NO REGISTRADA` sin romper la cuadrícula. |
| `Test 31 (VIGIA-AUTH-01)` | **PASÓ** | Falta de actualización ($>6$s) degrada a `SIN ACTUALIZACIÓN` sin confundir con `SIN SEÑAL`. |

---

## 7. Evidencia de Regresión de Cámaras Existentes

Se ejecutó la suite completa de pruebas de autenticación RBAC existente y ciclo de vida de cámaras y backend:

```powershell
cmd /c "set PYTHONPATH=VIGIA_Vision_Systems && VIGIA_Vision_Systems\.venv\Scripts\python.exe -m unittest tests.unit.test_auth_rbac tests.unit.test_auth_stream_protection tests.unit.test_camera_stream_and_backend"
```

**Salida obtenida:**
```text
Ran 62 tests in 3.487s

OK
```

Se verificó que:
- Las cámaras autorizadas continúan recibiendo fotogramas push móviles y anotaciones en tiempo real.
- Las proyecciones de ROI y detecciones YOLO se visualizan intactas.
- El aislamiento entre cámaras en paralelo (`test_two_cameras_streaming_simultaneously_and_isolated`) se mantiene inalterado.
- El ciclo de vida de desconexión y reconexión automática frontend sigue operativo.

---

## 8. Limitaciones y Trabajo Futuro

1. **Pruebas en entorno físico:** Las validaciones reportadas se efectuaron rigurosamente mediante suites automatizadas unitarias e integrales en entornos simulados y mocks deterministas. Se recomienda una prueba de campo con el dispositivo móvil Android físico en la caseta institucional antes del paso a producción.
2. **Centralización de parámetros (Configuration Center):** La frecuencia de chequeo intra-stream (10s) y el límite de obsolescencia del frontend (6s) están codificados como constantes seguras. En la siguiente fase de arquitectura centralizada de configuración, podrán exponerse al Configuration Center administrado.

---

## 9. Dictamen Final

```
================================================================================
DICTAMEN: IMPLEMENTADO Y VALIDADO (SUITE AUTOMATIZADA)
================================================================================
```

La vulnerabilidad crítica de visualización no autorizada de video y telemetría ha sido completamente subsanada. El acceso a los streams y estados operativos requiere de manera estricta credenciales autenticadas válidas bajo el modelo RBAC (`ADMINISTRADOR` y `GUARDIA`), el ciclo de vida del flujo MJPEG está blindado contra sesiones expiradas o revocadas, y el frontend reacciona de forma determinista y segura ante cualquier cambio de estado de sesión.
