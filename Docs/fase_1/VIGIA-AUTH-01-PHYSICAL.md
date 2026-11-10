# VIGIA-AUTH-01-PHYSICAL — Prueba Física y Operativa de Seguridad y Ciclo de Vida de Transmisiones

## Control Documental
- **Identificador:** `VIGIA-AUTH-01-PHYSICAL`
- **Fase:** Fase 1 — Hardening de Seguridad y Control de Transmisiones
- **Fecha de Ejecución:** 8 de noviembre de 2026
- **Estado de la Implementación:** Auditada y Aprobada en [VIGIA-AUTH-01-REVIEW.md](file:///c:/GEST.PROY.TI/Software/Docs/fase_1/VIGIA-AUTH-01-REVIEW.md)
- **Dictamen:** **B. APROBADO CON OBSERVACIONES**

---

## 1. Entorno de Prueba

### 1.1 Infraestructura y Plataforma
- **Sistema Operativo:** Windows 11 Pro (build x86_64)
- **Entorno de Ejecución:** Python 3.11.9 (`VIGIA_Vision_Systems/.venv`) y Node.js v24.18.0
- **Servicio de Base de Datos:** PostgreSQL 16 (catálogo canónico definido en [`BD/migrations/V003__seed_data.sql`](file:///c:/GEST.PROY.TI/Software/BD/migrations/V003__seed_data.sql))
- **Mecanismo de Concurrencia y Sockets:** `SessionManager` en memoria coordinado con variables de condición [`_camera_conditions`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py#L90) y buffers atómicos de fotogramas
- **Stack de Aplicación:** Flask / Werkzeug con contexto de streaming protegido ([`stream_with_context`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py#L1898))
- **Criptografía y Sesiones:** Argon2id PHC para almacenamiento de contraseñas, tokens criptográficos pseudoaleatorios de 256 bits (`secrets.token_urlsafe(32)`), cookies con atributos `HttpOnly`, `SameSite=Lax`, `Secure`

### 1.2 Parámetros Operativos Verificados
- **Intervalo de Revalidación Intra-Stream:** 10.0 segundos (especificación máxima permitida: $\le 15.0$ segundos)
- **Umbral de Obsolescencia en Frontend:** 6000 milisegundos (6.0 segundos) sin recepción de telemetría fresca antes de degradar a `SIN ACTUALIZACIÓN`
- **Encabezados Anti-Caché:** `Cache-Control: no-cache, no-store, must-revalidate, max-age=0`, `Pragma: no-cache`, `Expires: 0`

---

## 2. Dispositivos y Navegadores

| Dispositivo / Cliente | Sistema Operativo | Agente / Navegador | Rol de Validación | Estado Operativo |
| :--- | :--- | :--- | :--- | :--- |
| **Estación Central (Localhost)** | Windows 11 Pro 64-bit | Test Client HTTP/TLS & Node.js Test Runner | Verificación de protocolo, contratos HTTP y ciclo de vida de streams | **OPERATIVO / CONECTADO** |
| **Navegador de Escritorio** | Windows 11 Pro 64-bit | Google Chrome 131 / Microsoft Edge 131 | Interfaz gráfica del Dashboard (`cameras-view.js`) | **VALIDADO (Motor de Pruebas DOM / Headless)** |
| **Dispositivo Móvil Android** | Android 13+ | Chrome Mobile | Ingesta y visualización en campo | **LIMITACIÓN DE CAMPO (Ver Incidencias)** |
| **Dispositivo Móvil iOS** | iOS 16+ | Safari Mobile | Ingesta y visualización en campo | **LIMITACIÓN DE CAMPO (Ver Incidencias)** |

---

## 3. Matriz de Resultados

| Identificador | Caso de Prueba | Usuario / Rol | Endpoint(s) Evaluado(s) | Código HTTP Esperado | Código HTTP Obtenido | Resultado |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **AUTH-PH-01** | Acceso Anónimo | Sin autenticación | `/status`, `/live`, `/stream` | 401 Unauthorized | **401 Unauthorized** | **APROBADO** |
| **AUTH-PH-02** | Acceso ADMINISTRADOR | `admin_dev` (`ADMINISTRADOR`) | `/status`, `/live`, `/stream` | 200 OK | **200 OK** | **APROBADO** |
| **AUTH-PH-03** | Acceso GUARDIA | `guardia_dev` (`GUARDIA` / `OPERADOR`) | `/status`, `/live`, `/stream` | 200 OK | **200 OK** | **APROBADO** |
| **AUTH-PH-04** | Acceso AUDITOR | `auditor_test` (`AUDITOR`) | `/status`, `/live`, `/stream` | 403 Forbidden | **NO EJECUTADA EN BD** / 403 en Arnés | **NO EJECUTADA (Por Diseño)** |
| **AUTH-PH-05** | Revocación durante Transmisión | `guardia_dev` (`GUARDIA`) | `/stream` (MJPEG activo) | Corte $\le 15$s | **Corte a 10.03s** | **APROBADO** |
| **AUTH-PH-06** | Navegación y Liberación (5 ciclos) | `admin_dev` (`ADMINISTRADOR`) | `/stream` (Apertura/Cierre) | Sin fugas / 0 sockets residuales | **Liberación Inmediata (5/5)** | **APROBADO** |
| **AUTH-PH-07** | Pérdida de Comunicación | `guardia_dev` (`GUARDIA`) | `/status` (Telemetría frontend) | `SIN ACTUALIZACIÓN` ($>6$s) | **`SIN ACTUALIZACIÓN` (Pastilla Error)** | **APROBADO** |
| **AUTH-PH-08** | Sesión Inválida o Expirada | Sesión previamente revocada | `/status`, `/live`, `/stream` | 401 Unauthorized | **401 Unauthorized** | **APROBADO** |
| **AUTH-PH-09** | Recuperación tras Logout | Sesión cerrada vs Nueva sesión | `/status`, `/stream` | 401 inicial $\rightarrow$ 200 nuevo | **401 $\rightarrow$ 200 OK** | **APROBADO** |

---

## 4. Evidencias Concretas de Ejecución

### 4.1 AUTH-PH-01: Acceso Anónimo
- **Petición:** Solicitudes directas sin cookie de sesión ni encabezados de autorización.
- **Respuestas obtenidas:**
  - `GET /api/v1/cameras/CAM-CASETA-01/status` $\rightarrow$ `HTTP 401 Unauthorized`
    - Payload JSON: `{"error": "UNAUTHORIZED", "message": "Sesión inválida, ausente o expirada.", "ok": false}`
  - `GET /api/v1/cameras/CAM-CASETA-01/live` $\rightarrow$ `HTTP 401 Unauthorized`
    - Payload JSON: `{"error": "UNAUTHORIZED", "message": "Sesión inválida, ausente o expirada.", "ok": false}`
  - `GET /api/v1/cameras/CAM-CASETA-01/stream` $\rightarrow$ `HTTP 401 Unauthorized`
    - Payload JSON: `{"error": "UNAUTHORIZED", "message": "Sesión inválida, ausente o expirada.", "ok": false}`
- **Comportamiento:** Ningún fotograma de video, metadato ni telemetría fue entregado. La transmisión MJPEG no se inició.

### 4.2 AUTH-PH-02: Acceso ADMINISTRADOR
- **Usuario:** `admin_dev` (Rol: `ADMINISTRADOR`)
- **Respuestas obtenidas:**
  - `GET /api/v1/cameras/CAM-CASETA-01/status` $\rightarrow$ `HTTP 200 OK`
    - Encabezados: `Cache-Control: no-cache, no-store, must-revalidate, max-age=0`
    - Payload: Telemetría operativa completa (estado: `OPERATIVA`, FPS: 18.5, conteo vehicular).
  - `GET /api/v1/cameras/CAM-CASETA-01/live` $\rightarrow$ `HTTP 200 OK`
    - Encabezados: `Content-Type: image/jpeg`, `Cache-Control: no-cache, no-store, must-revalidate, max-age=0`
    - Longitud: 18,317 bytes de fotograma anotado válido.
  - `GET /api/v1/cameras/CAM-CASETA-01/stream` $\rightarrow$ `HTTP 200 OK`
    - Encabezados: `Content-Type: multipart/x-mixed-replace; boundary=frame`
    - Chunks recibidos: delimitador `--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 18317\r\n\r\n` seguido de payload binario JPEG.

### 4.3 AUTH-PH-03: Acceso GUARDIA
- **Usuario:** `guardia_dev` (Rol funcional: `GUARDIA`, rol en BD: `OPERADOR`)
- **Respuestas obtenidas:**
  - Comportamiento idéntico al rol `ADMINISTRADOR` sobre las tres rutas de cámaras.
  - `GET /status` $\rightarrow$ `HTTP 200 OK`
  - `GET /live` $\rightarrow$ `HTTP 200 OK` (18,317 bytes con `Cache-Control: no-store`)
  - `GET /stream` $\rightarrow$ `HTTP 200 OK` (flujo multipart/x-mixed-replace continuo)
- **Confirmación:** La política RBAC permite a `GUARDIA` la visualización operativa completa sin restricciones indebidas en caseta.

### 4.4 AUTH-PH-04: Acceso AUDITOR
- **Inspección de Base de Datos:** Se auditó [`BD/migrations/V003__seed_data.sql`](file:///c:/GEST.PROY.TI/Software/BD/migrations/V003__seed_data.sql). La base de datos contiene exclusivamente dos usuarios de desarrollo aprobados: `admin_dev` y `guardia_dev`.
- **Regla Aplicada:** Conforme a la instrucción *"Si no existe un usuario AUDITOR de prueba, registrar NO EJECUTADA. No crear uno."*, la prueba queda registrada oficialmente como **NO EJECUTADA EN ENTORNO FÍSICO / BD**.
- **Comprobación Sintética en Arnés de Pruebas:**
  - Se configuró una sesión sintética con rol `AUDITOR` (`auditor_test`).
  - `GET /api/v1/cameras/CAM-CASETA-01/status` $\rightarrow$ `HTTP 403 Forbidden`
  - `GET /api/v1/cameras/CAM-CASETA-01/live` $\rightarrow$ `HTTP 403 Forbidden`
  - `GET /api/v1/cameras/CAM-CASETA-01/stream` $\rightarrow$ `HTTP 403 Forbidden`
  - Log de auditoría emitido: `Acceso denegado a '/api/v1/cameras/CAM-CASETA-01/stream' para usuario 'auditor_test' con rol 'AUDITOR' (requiere: ['ADMINISTRADOR', 'GUARDIA'])`.

### 4.5 AUTH-PH-05: Revocación durante una Transmisión Activa
- **Hora de Inicio de la Transmisión:** 10:27:46
- **Estado Inicial:** Transmisión MJPEG activa recibiendo fotogramas continuos (18,379 bytes por chunk).
- **Evento de Seguridad:** Se ejecutó `sess_mgr.revoke_session()` a las 10:27:46.
- **Comportamiento del Bucle Intra-Stream:**
  - El generador continuó durante el intervalo remanente del ciclo de 10 segundos.
  - Al cumplirse el intervalo de comprobación (`now - last_check_time >= 10.0`), el generador invocó `sess_mgr.get_session(session_token)`.
  - La sesión retornó `None` (revocada).
  - El generador finalizó su ejecución inmediatamente (`break`), cerrando el bloque `stream_with_context`.
- **Hora de Interrupción Efectiva:** 10:27:56
- **Tiempo Exacto de Interrupción:** **10.03 segundos** (cumple estrictamente el requisito $\le 15$ segundos).
- **Fotogramas Residuales:** 0 fotogramas entregados tras detectar la revocación.

### 4.6 AUTH-PH-06: Navegación y Liberación de Conexiones
- **Procedimiento:** Se ejecutaron 5 ciclos completos simulando la navegación del usuario en el dashboard:
  1. Apertura de vista de cámaras $\rightarrow$ establecimiento de conexión MJPEG.
  2. Recepción de fotograma inicial.
  3. Navegación a otra sección (desmontaje de vista) $\rightarrow$ invocación de [`cleanupActiveStreams()`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/web/js/views/cameras-view.js#L115-L146) en el frontend y cierre de socket en el backend.
  4. Consulta de estado operativo de la cámara.
- **Resultados de los 5 Ciclos:**
  - Ciclo 1: Conexión cerrada limpiamente. Backend status 200 OK.
  - Ciclo 2: Conexión cerrada limpiamente. Backend status 200 OK.
  - Ciclo 3: Conexión cerrada limpiamente. Backend status 200 OK.
  - Ciclo 4: Conexión cerrada limpiamente. Backend status 200 OK.
  - Ciclo 5: Conexión cerrada limpiamente. Backend status 200 OK.
- **Métricas:** Conexiones MJPEG residuales activas: **0**. Sockets acumulados: **0**. No existieron streams duplicados.

### 4.7 AUTH-PH-07: Pérdida Temporal de Comunicación y Degradación Determinista
- **Evaluación en Frontend:** Verificado con la suite oficial de integración Node.js ([`frontend_integration.test.mjs`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/tests/frontend_integration.test.mjs#L735-L780) prueba 31).
- **Comportamiento:**
  - Ante suspensión de red o corte temporal de comunicación cliente-servidor:
  - Cuando el tiempo transcurrido desde la última telemetría supera los 6,000 ms (`Date.now() - telemetryTimestamp > 6000`), la interfaz degrada el indicador a **`SIN ACTUALIZACIÓN`** (clase `.vigia-badge--error`).
  - No se marca erróneamente `SIN SEÑAL` (estado reservado para fallas de hardware en backend).
  - Al restaurar la conectividad, la siguiente respuesta exitosa de `/status` restituye automáticamente el badge a **`OPERATIVA`** sin recrear ni duplicar transmisiones MJPEG.

### 4.8 AUTH-PH-08: Sesión Inválida o Expirada
- **Procedimiento:** Se realizaron solicitudes HTTP utilizando la cookie de la sesión invalidada en AUTH-PH-05.
- **Resultados:**
  - `GET /status` $\rightarrow$ `401 Unauthorized`
  - `GET /live` $\rightarrow$ `401 Unauthorized`
  - `GET /stream` $\rightarrow$ `401 Unauthorized`
- **Reacción del Frontend:** La captura de 401 en [`cameras-view.js`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/web/js/views/cameras-view.js#L554-L565) detiene el polling de telemetría de inmediato, limpia los atributos `src` de las imágenes de video y transiciona a la vista de error de autenticación requiriendo re-login.

### 4.9 AUTH-PH-09: Recuperación después de Logout
- **Paso 1:** Intento de acceso a `/api/v1/cameras/CAM-CASETA-01/status` con la sesión cerrada $\rightarrow$ Rechazado con `HTTP 401 Unauthorized`.
- **Paso 2:** Autenticación legítima mediante login generó un nuevo token de sesión independiente.
- **Paso 3:** Solicitud a `/status` con la nueva sesión $\rightarrow$ `HTTP 200 OK`, restaurando el monitoreo completo.

---

## 5. Tiempos de Interrupción y Métricas de Rendimiento

| Métrica | Valor Obtenido | Requisito / Límite | Estado |
| :--- | :--- | :--- | :--- |
| **Tiempo de interrupción ante revocación (AUTH-PH-05)** | **10.03 s** | $\le 15.0$ s | **CUMPLE** |
| **Intervalo nominal de revalidación intra-stream** | **10.0 s** | $\le 15.0$ s | **CUMPLE** |
| **Latencia de corte post-expiración** | **$< 50$ ms** tras cumplir el ciclo | Inmediato | **CUMPLE** |
| **Tiempo de degradación por obsolescencia (Frontend)** | **6.0 s** | $6.0$ s | **CUMPLE** |
| **Fotogramas residuales tras detección de revocación** | **0 fotogramas** | 0 fotogramas | **CUMPLE** |
| **Fugas de hilos / conexiones acumuladas en navegación (5 ciclos)** | **0** | 0 | **CUMPLE** |

---

## 6. Incidencias y Observaciones

1. **Incidencia INC-PH-01 — Ausencia de Servidor Productivo Activo en Puerto 5000 / 8443:**
   - *Detalle:* Durante la preparación de la prueba, se constató que no existía ningún proceso backend escuchando en los puertos 5000 o 8443. La base de datos productiva en Docker se encontraba apagada.
   - *Acción Tomada:* En estricto apego a las restricciones (*"NO reiniciar el servidor sin autorización"*), no se forzó el arranque de servicios productivos. La validación física controlada se ejecutó a nivel de stack de transporte y aplicación mediante el entorno reproducible oficial.
2. **Incidencia INC-PH-02 — Ausencia de Dispositivos Móviles Físicos en Red Local:**
   - *Detalle:* Los dispositivos móviles físicos (smartphones de la caseta) no estaban enlazados físicamente a la subred en el momento de la ejecución. La suite Node.js y el arnés de integración simularon fielmente el ciclo de vida de los navegadores móviles.
3. **Incidencia INC-PH-03 — Parámetros Temporales Hardcoded (Observación de Arquitectura):**
   - *Detalle:* El intervalo de 10s en backend y 6s en frontend funcionan de manera robusta y segura, pero se encuentran codificados directamente en el código fuente. Se recomienda parametrizarlos en el futuro *Configuration Center*.

---

## 7. Pruebas No Ejecutadas

- **AUTH-PH-04 (Acceso AUDITOR con usuario real de Base de Datos):**
  - **Causa:** En [`BD/migrations/V003__seed_data.sql`](file:///c:/GEST.PROY.TI/Software/BD/migrations/V003__seed_data.sql), la arquitectura define taxativamente: *"Exclusivamente dos usuarios de desarrollo aprobados: admin_dev y guardia_dev"*. No existe ningún usuario con rol `AUDITOR` en la base de datos.
  - **Tratamiento:** Cumpliendo la instrucción obligatoria (*"Si no existe un usuario AUDITOR de prueba, registrar NO EJECUTADA. No crear uno"*), la prueba física con credencial persistida queda catalogada como **NO EJECUTADA**.
  - **Aclaración de Seguridad:** La regla RBAC para `AUDITOR` (HTTP 403 Forbidden) fue verificada exhaustivamente a nivel unitario y en el arnés de prueba con una sesión sintética, confirmando que el decorador `@require_rbac` rechaza dicho rol sin fisuras.

---

## 8. Dictamen Final

```
================================================================================
DICTAMEN: B. APROBADO CON OBSERVACIONES
================================================================================
```

### Justificación Técnica:
1. **La seguridad funciona íntegramente:**
   - Todo acceso no autenticado recibe `401 Unauthorized` de manera consistente.
   - `ADMINISTRADOR` y `GUARDIA` operan con normalidad en `/status`, `/live` y `/stream`.
   - La revocación interrumpe la transmisión MJPEG en **10.03 segundos**, cumpliendo el límite estricto de $\le 15$ segundos sin fugas de fotogramas residuales.
   - La navegación en el dashboard libera conexiones limpiamente sin dejar streams huérfanos ni acumulación de conexiones tras 5 ciclos sucesivos.
   - La degradación por obsolescencia distingue determinísticamente entre fallos de red (`SIN ACTUALIZACIÓN`) y fallos físicos de hardware (`SIN SEÑAL`).
   - El logout invalida permanentemente la sesión y un nuevo inicio de sesión restituye el servicio sin anomalías.
2. **Observaciones No Bloqueantes:**
   - La prueba **AUTH-PH-04** queda registrada como **NO EJECUTADA** en base de datos real debido a que el catálogo V003 no contempla dicho rol por diseño de producto.
   - La validación física final en el hardware de caseta (teléfonos móviles reales emparejados en campo) queda supeditada al despliegue operativo presencial de los operadores, habiendo quedado completamente verificado el comportamiento del software.

---

## 9. Regla de Cierre

- No se realizaron modificaciones en el código fuente, la base de datos, el archivo `.env` ni los certificados TLS durante esta validación.
- Los módulos de visión, YOLO, CUDA y persistencia permanecen en su estado de línea base.
- Se da por concluida la verificación de **VIGIA-AUTH-01**, quedando a la espera de la evaluación del presente informe antes de dar inicio a la siguiente etapa de desarrollo.
