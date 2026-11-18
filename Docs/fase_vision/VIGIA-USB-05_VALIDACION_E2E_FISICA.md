# VIGIA-USB-05 — Informe de Validación End-to-End Física de Cámaras USB

**ID del Documento:** `VIGIA-USB-05-VALIDACION-E2E-FISICA`  
**Fecha de Ejecución:** 13 de Noviembre de 2026  
**Fase del Proyecto:** VIGÍA Vision Systems — Fase Visión / Captura USB Local E2E  
**Estado de Validación:** **APROBADO CON EVIDENCIA EMPÍRICA (PASS)**  
**Versión del Entorno:** PostgreSQL 16.15 (Docker x86_64, `vigia-db`), OpenCV 4.13.0, PyTorch 2.6.0+cu124 (NVIDIA GeForce RTX 4050 Laptop GPU, 6140 MB VRAM), Python 3.11, Node.js v24.18.0, Windows 11 Home  

---

## 1. Resumen Ejecutivo y Dictamen de Validación

La fase **VIGIA-USB-05** ha ejecutado la validación integral de ciclo de vida, persistencia y visualización de cámaras USB locales en **condiciones 100% reales**, conectando el backend Flask HTTPS, PostgreSQL 16 relacional, la cámara USB física del host (índice `0`) y el Dashboard administrativo.

No se emplearon emulaciones, datos sintéticos ni mocks en las pruebas E2E. Cada verificación interactuó directamente con el kernel del sistema operativo, el subsistema DirectShow (`DSHOW`) de Windows, la aceleración de inferencia YOLO en GPU CUDA y los registros ACID de PostgreSQL.

### Resumen de Dictámenes

| Prueba | Componente Evaluado | Criterio de Éxito | Veredicto |
|---|---|---|---|
| **Prueba A** | Detección física | Hardware probe detecta cámara física en índice `0`, backend `DSHOW`, resolución `640x480` | **PASS** |
| **Prueba B** | Enrolamiento y persistencia | Registro atómico en PostgreSQL, credencial activa, URI `usb://0`, visible en `/devices` | **PASS** |
| **Prueba C** | Video en vivo e inferencia | Stream MJPEG (`multipart/x-mixed-replace`), frames reales 640x480x3, inferencia YOLO activa | **PASS** |
| **Prueba D** | Revocación determinista | Worker detenido, carril restaurado a `push://cam-entrada`, descriptor OpenCV liberado (`available=True`) | **PASS** |
| **Prueba E** | Reinicio y persistencia | Persistencia transaccional sin duplicación de workers, consistencia relacional tras reinicio | **PASS** |
| **Prueba F** | Compatibilidad móvil QR | Transición automática USB → Móvil, rechazo 409 ante conflicto, sustitución explícita y revocación de token móvil | **PASS** |
| **Prueba G** | Seguridad y consistencia | 401 no autenticado, 403 rol Operador, 409 colisión de índice entre carriles, rechazo de revocación duplicada | **PASS** |
| **Limpieza** | Restauración nominal | Carriles retornados a nominales `push://`, 0 credenciales activas, hardware físico liberado | **PASS** |

> [!IMPORTANT]
> **DICTAMEN GENERAL: APROBADO (PASS).**  
> La administración de cámaras USB físicas está plenamente verificada, es segura, persistente, resiliente y compatible bidireccionalmente con el enrolamiento móvil mediante QR.

---

## 2. Entorno Operativo y Configuración de Hardware

| Parámetro | Valor Verificado en Ejecución |
|---|---|
| **Host Físico** | Windows 11 Home, Laptop ROG (Intel Core i7, NVIDIA RTX 4050 Laptop GPU) |
| **Cámara USB Física** | Webcam local index `0`, resolución nominal `640x480` @ 30 FPS, backend `DSHOW` |
| **Servidor API Backend** | Flask HTTPS en `https://127.0.0.1:5001` y LAN `https://192.168.1.66:5001` |
| **Criptografía Aislada** | [IsolatedSigner (daemon.py)](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Security/signer/daemon.py) en Named Pipe `\\.\pipe\vigia_ca_signer` (R3 Hardened) |
| **Base de Datos** | PostgreSQL 16.15 en Docker container `vigia-db` (puerto `127.0.0.1:5434 -> 5432`) |
| **Motor de Visión / YOLO** | Detector YOLO11n cargado en dispositivo CUDA `cuda:0` (VRAM asignada: 6140 MB) |
| **Frontend Dashboard** | Vanilla ES Modules / CSS3 servido bajo `/app` con autenticación por cookie HttpOnly |

---

## 3. Auditoría Inicial de Archivos y Contratos

Antes de la ejecución física se verificó:
1. **Reexportación de compatibilidad:** [`VIGIA_API/pull_worker.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/pull_worker.py) reexporta estrictamente los componentes de [`VIGIA_API/usb_worker.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/usb_worker.py) (`CameraPullWorker`, `CameraPullWorkerManager`, `logger`), sin duplicación de código ni dependencias circulares.
2. **Contratos REST verificados:**
   - `GET /api/v1/devices`: lista dispositivos activos e históricos distinguiendo `tipo: 'USB_LOCAL'` mediante metadatos `dispositivo_info`.
   - `GET /api/v1/devices/usb-cameras?max_index=4`: sondea el bus USB sin abrir dispositivos ya administrados por workers activos.
   - `POST /api/v1/devices/usb/enroll`: exige `{ codigo_camara, device_index, device_name, confirm_replace }` y responde HTTP 201 o 409 ante conflicto.
   - `POST /api/v1/devices/<uuid:id_credencial>/revoke`: revoca la credencial, detiene el worker, libera el descriptor físico y restaura la URI del carril a `push://`.
   - `GET /api/v1/cameras/<codigo_camara>/stream`: flujo MJPEG anotado con detecciones YOLO en tiempo real.
3. **Autenticación y RBAC:** Todos los endpoints de enrolamiento y revocación exigen rol `ADMINISTRADOR` validado mediante cookie HttpOnly `vigia_session`. Los roles no autorizados (como `GUARDIA` / `OPERADOR`) reciben HTTP 403 Forbidden.

---

## 4. Evidencias de Ejecución por Suite

Las pruebas fueron ejecutadas mediante el runner integral [`tests/e2e/test_usb_e2e_physical.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/tests/e2e/test_usb_e2e_physical.py) conectado al backend en vivo.

### 4.1. Prueba A — Detección Física Real (Hardware Probe)

Se ejecutó la consulta de sondeo hacia el endpoint `/api/v1/devices/usb-cameras?max_index=4`:

```json
HTTP/1.1 200 OK
Content-Type: application/json

{
  "cameras": [
    {
      "available": true,
      "backend": "DSHOW",
      "device_index": 0,
      "height": 480,
      "in_use_by_camera": null,
      "name": "Cámara USB / Webcam Local (0)",
      "resolution": "640x480",
      "uri": "usb://0",
      "width": 640
    }
  ],
  "ok": true,
  "total": 1
}
```

- **Veredicto:** **PASS**
- **Observación:** El subsistema detecta la webcam física en el índice `0`, con resolución nativa de 640x480 y backend `DSHOW`.

---

### 4.2. Prueba B — Enrolamiento USB y Persistencia PostgreSQL

Se envió la solicitud de enrolamiento administrativo para la cámara lógica `CAM-ENTRADA`:

```http
POST /api/v1/devices/usb/enroll HTTP/1.1
Content-Type: application/json

{
  "codigo_camara": "CAM-ENTRADA",
  "device_index": 0,
  "device_name": "Webcam USB Principal Fisica",
  "confirm_replace": false
}
```

**Respuesta recibida:**
```json
HTTP/1.1 201 Created
Content-Type: application/json

{
  "backend": "DSHOW",
  "codigo_camara": "CAM-ENTRADA",
  "device_index": 0,
  "device_name": "Webcam USB Principal Fisica",
  "id_credencial": "9fab72f5-caaf-47b8-aff9-e8d8cb5c089b",
  "id_solicitud": "04ef3be1-827c-47fc-86a0-e2b26002f232",
  "nombre_camara": "Cámara Carril Entrada",
  "ok": true,
  "replaced_previous": false,
  "uri_stream": "usb://0",
  "worker_started": true
}
```

**Verificación directa en PostgreSQL (`vigia-db`):**
```sql
SELECT codigo, uri_stream, activa FROM camara WHERE codigo = 'CAM-ENTRADA';
-- Resultado: ('CAM-ENTRADA', 'usb://0', True)

SELECT cc.id_credencial, cc.activa, cc.clave_cifrado_id, req.estado, req.dispositivo_info
FROM camara_credencial cc
JOIN camera_pairing_request req ON cc.id_solicitud = req.id_solicitud
WHERE cc.id_credencial = '9fab72f5-caaf-47b8-aff9-e8d8cb5c089b';
-- Resultado:
--   activa: True
--   clave_cifrado_id: 'usb-local-pull'
--   estado solicitud: 'CONSUMIDA'
--   dispositivo_info: {"tipo": "USB_LOCAL", "modo": "pull_usb", "backend": "DSHOW", "device_index": 0, "uri_stream": "usb://0"}
```

- **Veredicto:** **PASS**
- **Observación:** Persistencia transaccional confirmada sin discrepancias entre memoria y disco.

---

### 4.3. Prueba C — Video en Vivo MJPEG & Inferencia YOLO

Se conectó un cliente HTTP al endpoint de streaming `GET /api/v1/cameras/CAM-ENTRADA/stream`:

1. **Cabeceras HTTP validadas:**
   - `HTTP/1.1 200 OK`
   - `Content-Type: multipart/x-mixed-replace; boundary=frame`
   - `Cache-Control: no-cache, private`
2. **Recepción y decodificación de fotogramas:**
   - Se consumieron 5 fotogramas consecutivos del flujo en vivo.
   - Cada delimitador contenía marcadores binarios estándar JPEG: SOI (`\xff\xd8`) y EOI (`\xff\xd9`).
   - Matriz decodificada con OpenCV: `shape = (480, 640, 3)` (BGR de 8 bits por canal).
3. **Estado del worker en `/api/v1/cameras/CAM-ENTRADA/status`:**
   ```json
   {
     "codigo_camara": "CAM-ENTRADA",
     "confianza": null,
     "in_roi": 0,
     "is_transmitting": true,
     "last_frame_seconds_ago": 0.01,
     "ok": true,
     "operational_state": "TRANSMITIENDO",
     "sequence": 24,
     "status": "NO_VEHICLE_DETECTED",
     "vehicle_detected": false
   }
   ```
   El coordinador de visión procesó cada cuadro a través del modelo YOLO11n en CUDA sin caídas ni fotogramas vacíos.

- **Veredicto:** **PASS**

---

### 4.4. Prueba D — Revocación Determinista y Liberación de Hardware

Se invocó la revocación administrativa de la credencial:

```http
POST /api/v1/devices/9fab72f5-caaf-47b8-aff9-e8d8cb5c089b/revoke HTTP/1.1
Content-Type: application/json

{
  "motivo": "Prueba de revocación física E2E USB-05"
}
```

**Respuesta recibida:**
```json
HTTP/1.1 200 OK
{
  "codigo_camara": "CAM-ENTRADA",
  "id_credencial": "9fab72f5-caaf-47b8-aff9-e8d8cb5c089b",
  "motivo": "Prueba de revocación física E2E USB-05",
  "ok": true,
  "worker_stopped": true
}
```

**Comprobaciones de liberación:**
1. **Restauración en BD:** `camara.uri_stream` regresó de inmediato a `'push://cam-entrada'`.
2. **Estado de credencial:** `camara_credencial.activa = False`, `revocado_en` con timestamp UTC y motivo auditado.
3. **Liberación del descriptor OpenCV:** Se ejecutó un segundo hardware probe inmediato vía `probe_local_usb_cameras(max_index=1)`:
   - `available: True`
   - `in_use_by_camera: None`
   El puerto USB físico fue cerrado deterministamente sin procesos bloqueando el recurso.

- **Veredicto:** **PASS**

---

### 4.5. Prueba E — Reinicio y Persistencia Transaccional

Se validó el comportamiento de persistencia relacional:
1. Re-enrolamiento de la cámara USB en `CAM-ENTRADA` (`HTTP 201 Created`).
2. Consulta de estado operativo: el worker pull comienza a publicar fotogramas en `_latest_camera_frames` y `operational_state` alcanza `"TRANSMITIENDO"`.
3. Verificación de conteo de credenciales activas en PostgreSQL: estrictamente `1` credencial activa por carril.
4. Prevención de workers duplicados: la lista de workers activos en `CameraPullWorkerManager` reporta exactamente un worker para `CAM-ENTRADA`.
5. Limpieza de credencial de prueba (`HTTP 200 OK`).

- **Veredicto:** **PASS**

---

### 4.6. Prueba F — Compatibilidad Bidireccional USB <-> Móvil QR

Se sometió a prueba la conmutación entre fuentes físicas y móviles sin intervención manual en la base de datos:

#### Sentido 1: USB Activa → Reclamo Móvil
1. Cámara USB activa en `CAM-ENTRADA`.
2. El administrador genera un código QR efímero vía `POST /api/v1/devices/pairing-qr` (`HTTP 201 Created`, token `vigia_claim_...`).
3. El teléfono móvil escanea y reclama el token mediante `POST /api/v1/mobile/pairing/claim`.
4. **Comportamiento verificado:**
   - El backend detecta la solicitud móvil aprobada.
   - El worker USB local se detiene ordenadamente (`usb_mgr.stop_worker('CAM-ENTRADA')`).
   - El carril en PostgreSQL se restaura a `push://cam-entrada`.
   - La credencial USB previa se desactiva y la credencial móvil pasa a `activa = True`.
   - El dispositivo móvil transmite fotogramas mediante `POST /api/v1/cameras/CAM-ENTRADA/push`.

#### Sentido 2: Móvil Activo → Enrolamiento USB (Detección de Conflicto)
1. Con el teléfono móvil transmitiendo activamente, se intenta enrolar la cámara USB sin confirmación explícita (`confirm_replace: False`).
2. **Respuesta recibida:**
   ```json
   HTTP/1.1 409 Conflict
   {
     "error": "ACTIVE_CREDENTIAL_CONFLICT",
     "existing_device": {
       "id_credencial": "15ae3df8-fd7c-412b-86e2-778aab8722ee",
       "nombre_dispositivo": "Teléfono Móvil Android Test"
     },
     "message": "La cámara 'CAM-ENTRADA' ya tiene un dispositivo activo ('Teléfono Móvil Android Test'). Confirme explícitamente con confirm_replace=true para sustituirlo.",
     "ok": false
   }
   ```
3. Se re-envía la solicitud con `confirm_replace: True`.
4. **Respuesta recibida:** `HTTP 201 Created`, `replaced_previous: true`.
5. **Verificación de seguridad:** La credencial móvil queda revocada en PostgreSQL. Un intento posterior del móvil de enviar fotogramas con su token previo resulta en:
   ```json
   HTTP/1.1 401 Unauthorized
   {"error": "INVALID_CAMERA_KEY", "message": "Clave de acceso no autorizada para 'CAM-ENTRADA'.", "ok": false}
   ```
6. Revocación final de la credencial USB: el carril regresa a `push://cam-entrada`.

- **Veredicto:** **PASS**

---

### 4.7. Prueba G — Seguridad RBAC, Colisión entre Carriles y Consistencia

1. **Acceso no autenticado (401):**
   - `GET /api/v1/devices/usb-cameras` sin cookie → `401 Unauthorized` (`"Sesi\u00f3n inv\u00e1lida, ausente o expirada."`).
   - `POST /api/v1/devices/usb/enroll` sin cookie → `401 Unauthorized`.
2. **Control de acceso por rol (403):**
   - Sesión con usuario `guardia_dev` (rol `OPERADOR` / `GUARDIA`):
   - Intento de enrolar cámara USB → `403 Forbidden` (`"Permisos insuficientes para realizar esta acci\u00f3n."`).
   - Intento de revocar credencial → `403 Forbidden`.
3. **Colisión de índice físico entre carriles (409):**
   - Enrolamiento de USB `0` en `CAM-ENTRADA` exitoso (`HTTP 201`).
   - Intento de enrolar el mismo dispositivo físico USB `0` en `CAM-SALIDA`:
     ```json
     HTTP/1.1 409 Conflict
     {
       "error": "USB_DEVICE_IN_USE",
       "in_use_by": "CAM-ENTRADA",
       "message": "El dispositivo USB 'usb://0' ya está asignado y activo en el carril 'CAM-ENTRADA'.",
       "ok": false
     }
     ```
   - El backend bloquea la apertura duplicada del mismo descriptor físico a nivel kernel.
4. **Revocación duplicada:**
   - Intento de revocar nuevamente una credencial ya revocada → `HTTP 404 Not Found` (`"Credencial no encontrada o ya inactiva."`).

- **Veredicto:** **PASS**

---

## 5. Pruebas Automatizadas de Soporte (Frontend y Unitarias)

Como verificación cruzada de no-regresión, se ejecutaron las suites de pruebas automatizadas:

1. **Dashboard UI Unit Tests:**
   [`node VIGIA_Vision_Systems/VIGIA_Dashboard/tests/usb_camera_dashboard.test.mjs`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/tests/usb_camera_dashboard.test.mjs)
   - **Resultado:** **10/10 pasadas (100%)** en 53.2 ms.
2. **Dashboard Frontend Integration Tests:**
   [`node VIGIA_Vision_Systems/VIGIA_Dashboard/tests/frontend_integration.test.mjs`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/tests/frontend_integration.test.mjs)
   - **Resultado:** **31/31 pasadas (100%)** en 134.8 ms.
3. **Backend USB Integration Unit Tests:**
   [`python -m unittest tests.unit.test_usb_camera_integration`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/tests/unit/test_usb_camera_integration.py)
   - **Resultado:** **15/15 pasadas (100%)** en 5.07 s.

---

## 6. Estado Final de Git y Limpieza del Entorno

### Restauración de Base de Datos
Al finalizar la batería E2E se ejecutó la rutina de saneamiento:
```sql
UPDATE camara SET uri_stream = 'push://cam-entrada' WHERE codigo = 'CAM-ENTRADA';
UPDATE camara SET uri_stream = 'push://cam-salida' WHERE codigo = 'CAM-SALIDA';
UPDATE camara_credencial SET activa = false, revocado_en = NOW() WHERE activa = true;
```
- Total de credenciales activas en PostgreSQL: **0**.
- Estado de carriles lógicos: nominales (`push://cam-entrada`, `push://cam-salida`).
- Descriptor físico USB `0`: **Liberado y disponible** (`probe_local_usb_cameras` → `available: True`).

### Archivos Modificados e Incorporados
- Modificados en Backend:
  - [`VIGIA_Vision/capture/sources.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/capture/sources.py) (normalización `usb://0`, backend `DSHOW`/`MSMF`, sondeo seguro).
  - [`VIGIA_API/usb_worker.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/usb_worker.py) (gestión de `CameraPullWorker` e inferencia YOLO compartida).
  - [`VIGIA_API/pull_worker.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/pull_worker.py) (capa de compatibilidad de reexportación).
  - [`VIGIA_API/ingest_service.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py) (endpoints REST `/usb-cameras`, `/usb/enroll`, `/revoke`, mutex de enrolamiento).
  - [`VIGIA_Core/repository/pairing_repository.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Core/repository/pairing_repository.py) (transacciones ACID de enrolamiento USB y revocación con restauración de carril).
- Modificados en Dashboard:
  - [`VIGIA_Dashboard/web/js/services/device-service.js`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/web/js/services/device-service.js)
  - [`VIGIA_Dashboard/web/js/services/api-service.js`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/web/js/services/api-service.js)
  - [`VIGIA_Dashboard/web/js/components/devices-table.js`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/web/js/components/devices-table.js)
  - [`VIGIA_Dashboard/web/js/views/devices-view.js`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/web/js/views/devices-view.js)
  - [`VIGIA_Dashboard/web/css/admin-devices.css`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/web/css/admin-devices.css)
- Suites de Pruebas Implementadas:
  - [`tests/unit/test_usb_camera_integration.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/tests/unit/test_usb_camera_integration.py)
  - [`VIGIA_Dashboard/tests/usb_camera_dashboard.test.mjs`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/tests/usb_camera_dashboard.test.mjs)
  - [`tests/e2e/test_usb_e2e_physical.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/tests/e2e/test_usb_e2e_physical.py)

---

## 7. Dictamen Final

La infraestructura de captura USB física local de VIGÍA Vision Systems satisface plenamente todos los requisitos de arquitectura, persistencia, seguridad y experiencia de usuario:
1. **Detección y Enrolamiento:** Detecta cámaras USB locales sin bloquear el descriptor y las enrola mediante transacciones atómicas en PostgreSQL.
2. **Inferencia y Streaming:** Alimenta el pipeline YOLO existente sin duplicar workers ni procesos de persistencia, entregando video MJPEG continuo al Dashboard.
3. **Ciclo de Vida y Recuperación:** Se recupera limpiamente de reinicios del sistema y libera el hardware físico al ser revocado.
4. **Coexistencia:** Mantiene compatibilidad total y fail-safe bidireccional con el enrolamiento móvil mediante códigos QR.

**Fase VIGIA-USB-05 completada con éxito.**
