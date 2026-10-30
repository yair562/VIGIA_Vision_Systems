# INFORME VO-02A-R1 — Corrección de Observaciones de Auditoría (Sprint 02A)

---

## Control Documental

- **Identificador:** `VO-02A-R1`
- **Auditoría de Origen:** [`VO-02A_AUDITORIA_GESTION_DISPOSITIVOS.md`](./VO-02A_AUDITORIA_GESTION_DISPOSITIVOS.md)
- **Fecha de Ejecución:** 30 de octubre de 2026
- **Objetivo:** Resolver los cuatro hallazgos identificados en la auditoría `VO-02A` (`OBS-SEG-01`, `OBS-FLASK-02`, `OBS-UX-03`, `OBS-CSS-01`) conservando intacto el diseño aprobado de **Gestión de Dispositivos** y de **Inicio de Sesión**.

---

## 1. Resumen de Cambios Aplicados por Hallazgo

### 1.1. Resolución de `OBS-SEG-01` — Control Explícito del Modo DEMO
- **`VIGIA_Dashboard/web/index.html`:** Se estableció en el elemento raíz `<html lang="es" data-theme="light" data-demo-enabled="false">` el valor predeterminado seguro `data-demo-enabled="false"`.
- **`VIGIA_API/ingest_service.py`:**
  - `create_ingest_app()` incorpora el parámetro opcional `enable_frontend_demo: Optional[bool] = None`. Si no se especifica, evalúa la variable de entorno explícita `VIGIA_ENABLE_FRONTEND_DEMO` (cuyo valor predeterminado es falso).
  - La ruta `GET /app` inyecta `data-demo-enabled="true"` únicamente cuando `app.config["FRONTEND_DEMO_ENABLED"]` es `True`.
- **`VIGIA_Dashboard/web/js/router.js` y `web/js/app.js`:**
  - Se implementaron `isFrontendDemoEnabled()` y `resolveRouteState()`.
  - Cuando `data-demo-enabled` es `"false"` (por defecto), ni `#devices` ni `?demo=admin` permiten abrir las vistas administrativas: el enrutador devuelve `routeId: 'login'` con `blockedDemoAttempt: true`, reemplaza el hash por `#login` y muestra en el contenedor accesible `#login-feedback` el aviso:
    > *«El modo de previsualización DEMO está deshabilitado por defecto. Inicia sesión o habilita VIGIA_ENABLE_FRONTEND_DEMO=1 en el entorno de desarrollo.»*

### 1.2. Resolución de `OBS-FLASK-02` — Preservación de HTTP 404 y Excepciones HTTP de Werkzeug
- **`VIGIA_API/ingest_service.py`:**
  - Se registró el manejador explícito `@app.errorhandler(404)` que responde con código HTTP `404` y cuerpo JSON `{"ok": false, "error": "NOT_FOUND", "message": "El recurso o la ruta solicitada no existe."}`.
  - En `@app.errorhandler(Exception)` (`handle_unexpected_exception`), se añadió la guarda `if isinstance(exc, HTTPException): return exc` para garantizar que ningún código HTTP estándar de Werkzeug se convierta accidentalmente en `500`, mientras que cualquier excepción inesperada de tiempo de ejecución continúa registrándose en el log del servidor y devolviendo `500 INTERNAL_ERROR` sin exponer trazas al cliente.

### 1.3. Resolución de `OBS-UX-03` — Botón para Salir de la Vista DEMO
- **`VIGIA_Dashboard/web/js/views/devices-view.js` y `web/js/app.js`:**
  - Se añadió en la cabecera de la tarjeta administrativa, junto a la insignia `MODO DEMO`, el botón accesible `#btn-exit-demo` con el texto **`Salir de DEMO / Ir al Inicio de Sesión`**.
  - Al pulsarlo, invoca `exitDemoToLogin()` en `app.js`, el cual reinicia la instancia en memoria de `createDeviceService()` (limpiando cualquier alta temporal `DEMO-TMP-*`), limpia y oculta `#admin-root`, limpia avisos previos del formulario de login y navega a `#login` sin simular el cierre de una sesión autenticada.

### 1.4. Resolución de `OBS-CSS-01` — Limpieza de Reglas CSS sin Uso
- **`VIGIA_Dashboard/web/css/admin-devices.css`:**
  - Se eliminaron las reglas no utilizadas `.dev-preview-toolbar` y `.dev-preview-btn`.
  - Se incorporaron las reglas `.admin-demo-status-row` y `.admin-exit-demo-btn` empleadas por el nuevo botón de salida de DEMO.

---

## 2. Pruebas Ejecutadas y Resultados

### 2.1. Pruebas de Control del Modo DEMO y Seguridad HTTP en Flask

| Prueba Ejecutada | Configuración | Resultado Obtenido | Estado |
| :--- | :--- | :--- | :---: |
| `GET /app` con configuración por defecto | `VIGIA_ENABLE_FRONTEND_DEMO` no definida | `200 OK` — HTML contiene `data-demo-enabled="false"`. | **Aprobado** |
| Intento de acceso a `/app#devices` o `/app?demo=admin` por defecto | `data-demo-enabled="false"` | `resolveRouteState()` retorna `{ routeId: 'login', blockedDemoAttempt: true }`, permanece en Login y muestra aviso de acceso DEMO deshabilitado. | **Aprobado** |
| `GET /app` con DEMO habilitado (localhost y LAN `192.168.1.75`) | `$env:VIGIA_ENABLE_FRONTEND_DEMO = "1"` | `200 OK` — HTML contiene `data-demo-enabled="true"` tanto en `127.0.0.1` como en `192.168.1.75`. | **Aprobado** |
| Acción del botón `Salir de DEMO / Ir al Inicio de Sesión` | `data-demo-enabled="true"` | Reinicia `deviceService` en memoria, oculta `#admin-root` y regresa a `#login`. | **Aprobado** |
| Ruta inexistente `GET /ruta-inexistente` | Flask activo | Responde **HTTP `404`** (ya no devuelve `500`). | **Aprobado** |
| Intentos de traversal `GET /dashboard-assets/../mobile/index.html` y `GET /assets/brand/..%2fREADME.md` | Flask activo | Responden **HTTP `404`** (bloqueados). | **Aprobado** |
| Métodos no permitidos `POST /app` y `GET /api/v1/cameras/CAM-ENTRADA/push` | Flask activo | Responden **HTTP `405`**. | **Aprobado** |
| Rutas existentes `GET /`, `GET /mobile` y `POST /api/v1/cameras/<codigo>/push` | Flask activo | Conservan su comportamiento exacto (`200 OK`, `200 OK` y `503` *fail-closed* sin clave). | **Aprobado** |

### 2.2. Pruebas de Integridad y Regresión
- Suite unitaria del repositorio (`unittest discover -s tests/unit -p "test_*.py" -v`): **162 pruebas ejecutadas, 162 aprobadas (`OK`)**.
- `VIGIA_Dashboard/mobile/index.html` (`13,071` bytes), `VIGIA_Dashboard/web/css/login.css` (`5,717` bytes), `VIGIA_Dashboard/web/js/views/login-view.js` (`5,418` bytes) y `BD/` permanecen sin cambios.

---

## 3. Observaciones Abiertas

- **Ninguna (0 observaciones abiertas).** Los cuatro hallazgos de `VO-02A` quedaron cerrados y verificados.

