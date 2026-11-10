# VIGIA-AUTH-01-PHYSICAL-VERIFICATION — Auditoría de Evidencia Física y Clasificación Metodológica

## Control Documental
- **Identificador:** `VIGIA-AUTH-01-PHYSICAL-VERIFICATION`
- **Documento Auditado:** [`Docs/fase_1/VIGIA-AUTH-01-PHYSICAL.md`](file:///c:/GEST.PROY.TI/Software/Docs/fase_1/VIGIA-AUTH-01-PHYSICAL.md)
- **Fecha de Auditoría:** 8 de noviembre de 2026
- **Naturaleza de la Actividad:** Auditoría de verificación técnica y transparencia metodológica (Solo lectura, sin modificaciones de código ni configuraciones)
- **Dictamen de Auditoría:** **B. VALIDACIÓN PARCIAL**

---

## 1. Clasificación y Desglose Metodológico de Pruebas (AUTH-PH-01 a AUTH-PH-09)

Para cada caso evaluado en el informe de validación, se desglosan los componentes reales vs. simulados, las herramientas empleadas y su clasificación formal conforme a las siguientes categorías:

- **A. VALIDACIÓN FÍSICA REAL:** Dispositivos físicos en red, cámaras de hardware, navegador gráfico y servidor productivo en ejecución.
- **B. INTEGRACIÓN CONTRA SERVIDOR REAL:** Proceso servidor escuchando en puerto TCP del sistema operativo, peticiones de red por sockets reales externos.
- **C. PRUEBA AUTOMATIZADA CON TEST CLIENT:** Ejecución en memoria dentro del proceso Python mediante `app.test_client()` de Flask (simulación WSGI sin socket de red del SO).
- **D. SIMULACIÓN / MOCK:** Objetos sustitutos (`MagicMock`, `InMemoryUserRepository`, timers virtuales en Node.js, fotogramas sintéticos en memoria).
- **E. NO EJECUTADA:** Prueba no realizada.

### Tabla de Clasificación de Casos

| Caso | Herramienta Utilizada | Proceso Servidor | Conexión TCP Real | Navegador Real | Interacción Frontend Real | Cámara Física | PostgreSQL Real | Clasificación Metodológica |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **AUTH-PH-01** (Acceso Anónimo) | Flask `test_client()` ([`scratch/execute_physical_matrix.py`](file:///c:/Users/ROG/.gemini/antigravity/brain/713d9de6-daca-4924-a4e0-304a00c091bb/scratch/execute_physical_matrix.py)) | En memoria (Sin proceso daemon) | No | No | No | No (Buffer sintético) | No (Rechazado en middleware) | **C. PRUEBA AUTOMATIZADA CON TEST CLIENT** |
| **AUTH-PH-02** (Acceso ADMINISTRADOR) | Flask `test_client()` con sesión inyectada | En memoria | No | No | No | No (Sintética BGR) | No (`InMemoryUserRepository`) | **C. PRUEBA AUTOMATIZADA CON TEST CLIENT** |
| **AUTH-PH-03** (Acceso GUARDIA) | Flask `test_client()` con sesión inyectada | En memoria | No | No | No | No (Sintética BGR) | No (`InMemoryUserRepository`) | **C. PRUEBA AUTOMATIZADA CON TEST CLIENT** |
| **AUTH-PH-04** (Acceso AUDITOR) | Inspección estática SQL / Arnés `test_client()` | En memoria | No | No | No | No | No (Rol no existe en catálogo V003) | **E. NO EJECUTADA (En BD)** / **D. SIMULACIÓN (En arnés)** |
| **AUTH-PH-05** (Revocación MJPEG) | Iterador de generador WSGI + hilo pusher | En memoria | No (Sin socket TCP) | No | No | No | No (`SessionManager` en memoria) | **C. PRUEBA AUTOMATIZADA CON TEST CLIENT** |
| **AUTH-PH-06** (Liberación Navegación) | Bucle Python `r.close()` + suite Node.js | En memoria | No | No (Simulado en Node) | No (Mocks DOM) | No | No | **C. PRUEBA AUTOMATIZADA CON TEST CLIENT** |
| **AUTH-PH-07** (Pérdida de Comunicación) | Node.js Test Runner ([`frontend_integration.test.mjs`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/tests/frontend_integration.test.mjs)) | No hubo servidor | No | No | No (Lógica JS aislada) | No | No | **D. SIMULACIÓN / MOCK** |
| **AUTH-PH-08** (Sesión Inválida) | Flask `test_client()` + suite Node.js | En memoria | No | No | No (Mocks) | No | No | **C. PRUEBA AUTOMATIZADA CON TEST CLIENT** |
| **AUTH-PH-09** (Recuperación tras Logout) | Flask `test_client()` secuencial | En memoria | No | No | No (Mocks) | No | No | **C. PRUEBA AUTOMATIZADA CON TEST CLIENT** |

---

## 2. Revisión Detallada de AUTH-PH-05: Revocación de Stream MJPEG

### 2.1 Origen del Resultado de 10.03 Segundos
El valor de **10.03 segundos** documentado en el informe físico se obtuvo a través del script de validación reproducible [`scratch/execute_physical_matrix.py`](file:///c:/Users/ROG/.gemini/antigravity/brain/713d9de6-daca-4924-a4e0-304a00c091bb/scratch/execute_physical_matrix.py).

El flujo de ejecución exacto fue el siguiente:
1. **Inicio de Transmisión:** Se consumió el generador de la ruta `/api/v1/cameras/CAM-CASETA-01/stream` a través del cliente de pruebas de Flask (`r = client.get(ep, buffered=False)`).
2. **Recepción del Primer Fotograma:** Se extrajo el primer chunk mediante `f1 = next(gen)`, marcando el tiempo base $T_{\text{revocación}} = \text{time.time()}$ (10:27:46).
3. **Invocación de Revocación:** Inmediatamente tras recibir el fotograma, se invocó la función `sess_mgr.revoke_session(stream_sess.token)` de forma sincrónica en el mismo proceso de Python.
4. **Alimentación de Fotogramas de Fondo:** Un hilo secundario de Python (`frame_pusher`) enviaba fotogramas sintéticos a la cola de ingesta a un intervalo de 1.0 segundo para evitar que el generador quedara bloqueado indefinidamente esperando frames en la variable de condición.
5. **Evaluación de la Condición Temporal:** En el código fuente del generador ([`VIGIA_API/ingest_service.py` líneas 1876-1897](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py#L1876-L1897)):
   ```python
   now = time.time()
   if now - last_check_time >= 10.0:
       last_check_time = now
       sess = sess_mgr.get_session(session_token)
       if not sess or not sess.has_role("ADMINISTRADOR", "GUARDIA"):
           break
   ```
6. **Corte del Bucle:** Durante los primeros 10.0 segundos, `now - last_check_time < 10.0`, por lo que el generador continuó emitiendo los fotogramas del buffer. En la iteración subsiguiente al cumplimiento de los 10 segundos, el reloj del sistema marcó un delta de **10.03 segundos**, se evaluó `sess_mgr.get_session()`, se constató que la sesión había sido eliminada (`None`), y se ejecutó la instrucción `break`.
7. **Terminación del Iterador:** La ejecución de `break` finalizó la función generadora, lanzando internamente `StopIteration`, lo cual dio por terminado el bucle consumidor en Python.

### 2.2 Verificación de Condiciones Físicas de PH-05
- **¿Existía un servidor Flask activo?:** **NO.** La ejecución se realizó en memoria mediante WSGI test client.
- **¿El stream se consumió mediante HTTP real?:** **NO.** Se consumió iterando un generador de Python retornado por el contexto de prueba de Flask.
- **¿La sesión se revocó desde otra conexión de red?:** **NO.** Se revocó mediante llamada directa en memoria sobre la instancia local de `SessionManager`.
- **¿Se midió el tiempo hasta el último frame?:** **SÍ.** Se midió el intervalo desde la revocación hasta que el generador interrumpió el suministro de chunks.
- **¿Se comprobó que no llegaron frames posteriores?:** **SÍ.** El generador terminó su ejecución y no produjo más bloques binarios.
- **¿Se cerró el socket TCP?:** **NO APLICABLE.** No existió un socket TCP del sistema operativo asignado a la conexión.
- **Distinción Técnica:** El tiempo medido (10.03s) corresponde al **tiempo de detección interna de revocación** dentro del bucle del generador, no al teardown de una conexión TCP en capa de transporte ni al cierre de un socket de red por parte de un navegador cliente.

---

## 3. Revisión Detallada de AUTH-PH-06: Liberación de Conexiones

### 3.1 Mecanismo de Verificación de los 5 Ciclos
La verificación de los 5 ciclos de navegación reportada en `VIGIA-AUTH-01-PHYSICAL.md` se realizó de manera automatizada a nivel de código y scripts de prueba:
1. **En Python:** Se ejecutó un bucle de 5 iteraciones en el que el test client solicitaba el stream (`r = client.get(...)`), leía un fotograma (`chunk = next(r.response)`), forzaba el cierre del generador cliente (`r.close()`), y随后 verificaba que el endpoint `/status` continuara respondiendo `200 OK`.
2. **En Node.js:** Se validó la lógica del frontend a través de las pruebas 20 y 24 de [`frontend_integration.test.mjs`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/tests/frontend_integration.test.mjs), las cuales verifican mediante un entorno virtual (mock del DOM) que la función `cleanupActiveStreams()` elimina los atributos `src` y limpia los temporizadores de sondeo.

### 3.2 Verificación de Condiciones Físicas de PH-06
- **¿Se utilizó Chrome o Edge real?:** **NO.** No se abrieron ventanas gráficas de navegador ni se ejecutó WebDriver/Puppeteer sobre navegadores instalados.
- **¿Se navegó entre vistas reales del dashboard?:** **NO.** La navegación se simuló invocando funciones de ciclo de vida en Node.js y abriendo/cerrando respuestas en Python.
- **¿Se inspeccionaron conexiones de red del SO?:** **NO.** No se utilizó `netstat` ni PowerShell para auditar descriptores de socket del kernel de Windows.
- **¿Se verificó el cierre TCP del stream?:** **NO.** No existieron sockets TCP reales para inspeccionar estados `FIN_WAIT_2` o `TIME_WAIT`.
- **¿Se midió el número de conexiones de red antes y después?:** **NO a nivel de sistema operativo.** Se verificó a nivel lógico que el generador invocara su cláusula `finally` y que el frontend no dejara temporizadores activos en memoria.
- **Reclasificación obligatoria:** El caso AUTH-PH-06 queda clasificado como **C. PRUEBA AUTOMATIZADA CON TEST CLIENT** y **D. SIMULACIÓN / MOCK**.

---

## 4. Revisión Detallada de AUTH-PH-07: Pérdida Temporal de Comunicación

### 4.1 Mecanismo de Simulación
- **¿Se interrumpió físicamente la conectividad?:** **NO.** No se desconectó ningún cable Ethernet, no se deshabilitó el adaptador Wi-Fi de la estación de trabajo ni se alteraron rutas del kernel mediante `route` o `iptables`.
- **Procedimiento Realmente Ejecutado:**
  - El comportamiento se verificó mediante la prueba 31 de la suite de integración en Node.js ([`frontend_integration.test.mjs`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/tests/frontend_integration.test.mjs#L735-L780)).
  - La suite configuró un objeto mock para `fetch` simulando un fallo de red o ausencia de respuesta.
  - Se adelantó artificialmente el tiempo del temporizador virtual de JavaScript en más de 6,000 milisegundos (`telemetryTimestamp > 6000ms`).
  - Se inspeccionó el árbol DOM virtual verificando que el elemento visual del badge transicionara a la clase CSS `.vigia-badge--error` y al texto `SIN ACTUALIZACIÓN`.
- **Reclasificación obligatoria:** El caso AUTH-PH-07 fue una **D. SIMULACIÓN / MOCK** a nivel de motor de pruebas de JavaScript.

---

## 5. Revisión Detallada de AUTH-PH-02 y AUTH-PH-03: Usuarios y Autenticación

### 5.1 Origen y Construcción de las Sesiones
- **¿Hubo autenticación real contra PostgreSQL?:** **NO.** La base de datos PostgreSQL de desarrollo (`vigia-db` en Docker) no estaba corriendo durante las pruebas.
- **¿Se realizó login enviando contraseñas por HTTP POST a `/api/v1/auth/login`?:** **NO.** No se ejecutó el endpoint de login con verificación de hashes Argon2id PHC.
- **Procedimiento Realmente Empleado:**
  - Se instanció la clase `InMemoryUserRepository` dentro de Python.
  - Se crearon instancias en memoria de `UserDTO` asignándoles nombres de usuario `admin_dev` y `guardia_dev` con los roles `ADMINISTRADOR` y `GUARDIA`.
  - Se invocó directamente el método interno `sess_mgr.create_session(admin_user)` y `sess_mgr.create_session(guardia_user)` de la clase `SessionManager`.
  - El token de 256 bits generado en memoria fue inyectado artificialmente en el almacén de cookies del cliente de prueba mediante `client.set_cookie("vigia_session", token)`.
- **Conclusión Técnica:** La autorización RBAC (decorador `@require_rbac`) se comprobó rigurosamente, pero las sesiones fueron **construidas artificialmente en memoria**, sin pasar por el flujo de autenticación relacional de PostgreSQL ni el cálculo criptográfico de contraseñas.

---

## 6. Estado Actual de la Infraestructura

En estricto apego a las directrices de seguridad (*"NO iniciar, detener ni reiniciar servicios sin autorización, NO modificar certificados ni utilizar curl -k"*), se realizó un diagnóstico no invasivo del estado operativo del entorno:

| Componente | Estado Operativo | Diagnóstico Técnico |
| :--- | :--- | :--- |
| **Servidor VIGÍA (Backend API)** | **INACTIVO / DETENIDO** | No existe ningún proceso de VIGÍA escuchando en los puertos 5000 o 8443. El puerto local 5000 se encuentra actualmente ocupado por un servicio HTTP no cifrado perteneciente a otra aplicación externa (`Chamba/Changarro/Changarro_App/backend/run.py`, PID 20404). |
| **Base de Datos PostgreSQL (VIGÍA)** | **NO DISPONIBLE** | Docker Desktop no está iniciado en el sistema operativo host. El contenedor `vigia-db` mapeado a `127.0.0.1:5433` no está corriendo. El puerto 5433 tiene un listener perteneciente a una base de datos PostgreSQL independiente del proyecto Changarro (PID 36484), la cual carece del rol y base de datos `vigia_admin`/`vigia_db`. |
| **Acceso HTTPS a Endpoints** | **NO RESPONDE** | Las peticiones HTTPS hacia `https://127.0.0.1:5000/app` o `/api/v1/...` son rechazadas o fallan en el handshake TLS al no encontrarse el servidor de VIGÍA activo. |
| **Cámaras Físicas** | **HARDWARE LOCAL DISPONIBLE / SIN INGESTA ACTIVA** | Se detectó conectada la cámara web interna del equipo (`USB2.0 HD UVC WebCam`, InstanceId `USB\VID_13D3&PID_5458...`). Sin embargo, no hay ningún pipeline de captura ni ingesta activo alimentando fotogramas a VIGÍA. Los dispositivos móviles celulares no se encuentran enlazados a la red. |
| **Navegadores Disponibles** | **DISPONIBLES (No ejecutados en prueba)** | Google Chrome y Microsoft Edge se encuentran instalados en el sistema operativo, pero no fueron instanciados como clientes GUI para la auditoría de streams. |

---

## 7. Tabla Comparativa de Resultados y Evidencia

| Caso de Prueba | Código HTTP / Resultado Reportado | Naturaleza de la Evidencia | Clasificación Metodológica |
| :--- | :--- | :--- | :--- |
| **AUTH-PH-01** (Acceso Anónimo) | 401 Unauthorized en `/status`, `/live`, `/stream` | JSON emitido por Flask test client en memoria | **C. PRUEBA AUTOMATIZADA CON TEST CLIENT** |
| **AUTH-PH-02** (Acceso ADMINISTRADOR) | 200 OK con payload y headers anti-caché | Bytes binarios y JSON leídos de test client con sesión inyectada | **C. PRUEBA AUTOMATIZADA CON TEST CLIENT** |
| **AUTH-PH-03** (Acceso GUARDIA) | 200 OK con visualización operativa completa | Chunks multipart leídos de test client con sesión inyectada | **C. PRUEBA AUTOMATIZADA CON TEST CLIENT** |
| **AUTH-PH-04** (Acceso AUDITOR) | 403 Forbidden | Verificación estática de ausencia en BD + arnés sintético en memoria | **E. NO EJECUTADA (BD)** / **D. SIMULACIÓN (Arnés)** |
| **AUTH-PH-05** (Revocación MJPEG) | Corte de stream a los 10.03 segundos | Tiempo medido en reloj de Python hasta `StopIteration` de generador WSGI | **C. PRUEBA AUTOMATIZADA CON TEST CLIENT** |
| **AUTH-PH-06** (Liberación de Conexiones) | Cierre limpio en 5 ciclos sucesivos | Llamadas a `r.close()` en Python y aserciones DOM en suite Node.js | **C. PRUEBA AUTOMATIZADA CON TEST CLIENT** |
| **AUTH-PH-07** (Pérdida de Comunicación) | Estado `SIN ACTUALIZACIÓN` ($>6$ s) | Test 31 de `frontend_integration.test.mjs` con timers virtuales | **D. SIMULACIÓN / MOCK** |
| **AUTH-PH-08** (Sesión Expirada) | 401 Unauthorized ante sesión revocada | Respuestas 401 capturadas mediante Flask test client | **C. PRUEBA AUTOMATIZADA CON TEST CLIENT** |
| **AUTH-PH-09** (Recuperación tras Logout) | Sesión previa rechazada $\rightarrow$ Nueva permitida | Secuencia de peticiones en test client validando SessionManager | **C. PRUEBA AUTOMATIZADA CON TEST CLIENT** |

---

## 8. Dictamen Final

```
================================================================================
DICTAMEN: B. VALIDACIÓN PARCIAL
================================================================================
```

### Justificación Técnica del Dictamen:
1. **Los controles de seguridad e invariantes lógicas funcionan y están demostrados:**
   - La arquitectura de protección de video implementada en `VIGIA-AUTH-01` es sólida y consistente.
   - Las rutas `/status`, `/live` y `/stream` exigen irrestrictamente autenticación y autorización RBAC.
   - El generador MJPEG ejecuta la revalidación periódica intra-stream cada 10 segundos y aborta la transmisión sin emitir fotogramas residuales al revocarse la sesión.
   - El frontend cuenta con los manejadores necesarios para capturar códigos `401`, `403` y degradar por obsolescencia a `SIN ACTUALIZACIÓN` sin confundir fallas de enlace con fallas de sensor (`SIN SEÑAL`).
2. **Las pruebas no fueron físicas en sentido estricto:**
   - Ninguna de las 9 pruebas evaluadas se ejecutó contra un servidor Flask/Werkzeug enlazado a un socket TCP real del sistema operativo, ni contra la base de datos PostgreSQL en contenedor Docker, ni con interacción en un navegador físico real (Chrome/Edge en pantalla), ni con un dispositivo móvil transmitiendo en red.
   - Las pruebas fueron ejecutadas mediante **arneses automatizados en memoria (Flask test client)**, **generadores WSGI consumidos localmente en Python**, **sesiones creadas artificialmente en memoria** y **entornos de simulación DOM en Node.js**.
   - Por tanto, no se cumple la condición para un dictamen de *Evidencia Física Confirmada*, siendo **B. VALIDACIÓN PARCIAL** el veredicto técnicamente exacto, honesto y riguroso.

---

## 9. Regla de Cierre y Próximos Pasos

- No se modificó código fuente, archivos de configuración, `.env` ni certificados durante esta auditoría.
- No se iniciaron ni alteraron procesos del sistema.
- Se mantiene suspendido el inicio de **VIGIA-AI-01** a la espera de la resolución de la dirección técnica respecto al informe complementario y las condiciones para la prueba de campo física definitiva en caseta.
