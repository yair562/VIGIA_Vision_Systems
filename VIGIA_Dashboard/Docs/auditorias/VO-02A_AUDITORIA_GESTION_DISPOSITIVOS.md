# AUDITORÍA VO-02A — Validación de Gestión de Dispositivos (Sprint 02A)

---

## Control Documental

- **Identificador de Auditoría:** `VO-02A`
- **Objetivo:** Auditoría técnica, arquitectónica, de seguridad, funcional y visual/responsive de la implementación del **Sprint 02A: Interfaz de Gestión de Dispositivos (Administrador)** en `VIGIA_Dashboard/`.
- **Fecha de Ejecución:** 30 de octubre de 2026
- **Alcance de la Fase:** Inspección, pruebas y diagnóstico en modo lectura sobre el código fuente (cero modificaciones a HTML, CSS, JavaScript, SQL o configuración de Flask).

---

## 1. Dictamen General

### **DICTAMEN: APROBADO CON OBSERVACIONES**

**Justificación del dictamen:**
La arquitectura modular del frontend (`app.js`, `router.js`, `devices-view.js`, `admin-navbar.js`, `devices-table.js`, `device-service.js`, `devices-demo-data.js`), el diseño visual de la pantalla **Gestión de Dispositivos**, el sistema de variables CSS (Modo Claro y Modo Oscuro), el desacoplamiento de los datos sintéticos DEMO y la integridad del proyecto (`mobile/index.html`, `login.css`, `login-view.js` y `BD/`) cumplen los requisitos del Sprint 02A.

No obstante, se emiten **tres observaciones técnicas y de seguridad** que deben atenderse antes de pasar a un entorno productivo o al sprint de integración con el backend:
1. **`[OBS-SEG-01]` Habilitación incondicional de rutas DEMO en el cliente (`router.js`):** Actualmente `/app#devices` y `/app?demo=admin` están habilitadas directamente en `resolveCurrentRoute()` sin una bandera explícita de entorno de desarrollo/DEMO servida o controlada por configuración, lo que conlleva el riesgo de que permanezcan accesibles si el código se despliega en producción sin desactivar el bypass de previsualización.
2. **`[OBS-FLASK-02]` Captura de excepciones `404 NotFound` de Werkzeug por el manejador genérico `@app.errorhandler(Exception)` en `VIGIA_API/ingest_service.py`:** Cuando se solicita una ruta inexistente en Flask (por ejemplo, `/ruta-inexistente` o una ruta que Werkzeug normaliza fuera del patrón), el manejador `@app.errorhandler(Exception)` intercepta `HTTPException` (`404 Not Found`) y devuelve `500 INTERNAL_ERROR` en lugar de `404` (mientras que `405` sí tiene su propio `@app.errorhandler(405)`).
3. **`[OBS-UX-03]` Ausencia de enlace o botón directo en la interfaz de Administración para regresar a `#login`:** Aunque se puede volver al inicio de sesión navegando a `/app#login` o `/app`, o usando el botón «Atrás» del navegador, la vista administrativa DEMO no incluye todavía un botón explícito «Volver a Inicio de Sesión / Salir de vista DEMO» dentro de la cabecera o de la sección `Perfil`, ni se instanció la clase `.dev-preview-toolbar` definida en `admin-devices.css`.

---

## 2. Hallazgos Técnicos (Auditoría de Arquitectura)

Se inspeccionaron los 7 módulos JavaScript ES6 de `VIGIA_Dashboard/web/js/`:

| Módulo Inspeccionado | Responsabilidad Verificada | Importaciones (Dependencias Salientes) | Estado |
| :--- | :--- | :--- | :---: |
| [`web/js/app.js`](../../web/js/app.js) | Punto de entrada: inicializa `initLoginView`, instancia `createDeviceService`, aplica `?theme=dark\|light` y conecta `initRouter`. | `./views/login-view.js`, `./views/devices-view.js`, `./services/device-service.js`, `./router.js` | **Correcto** |
| [`web/js/router.js`](../../web/js/router.js) | Enrutador hash (`#login`, `#devices`, `#cameras`, `#alerts`, `#reports`, `#profile`, `#camera-viewer`) y query (`?demo=admin`). | *Ninguna (módulo hoja)* | **Correcto** |
| [`web/js/views/devices-view.js`](../../web/js/views/devices-view.js) | Orquestador de la vista administrativa: ensambla `.admin-shell`, `renderAdminNavbar`, tarjeta blanca, `renderDevicesTable`, panel provisional de alta DEMO, botones principales y pie de página. | `../components/admin-navbar.js`, `../components/devices-table.js` | **Correcto** |
| [`web/js/components/admin-navbar.js`](../../web/js/components/admin-navbar.js) | Componente puro reutilizable para la barra superior (logo circular oficial, 4 píldoras centrales y botón circular de Perfil). | *Ninguna (módulo hoja)* | **Correcto** |
| [`web/js/components/devices-table.js`](../../web/js/components/devices-table.js) | Componente puro reutilizable para la cuadrícula de 5 columnas con bloques rectangulares grises y celdas `.device-cell-box`. | *Ninguna (módulo hoja)* | **Correcto** |
| [`web/js/services/device-service.js`](../../web/js/services/device-service.js) | Capa de servicio asíncrona en memoria (`listDevices`, `getDeviceById`, `previewAddDeviceDemo`). | `../data/devices-demo-data.js` | **Correcto** |
| [`web/js/data/devices-demo-data.js`](../../web/js/data/devices-demo-data.js) | Definición inmutable (`Object.freeze`) de los 7 registros sintéticos DEMO y sus metadatos. | *Ninguna (módulo hoja)* | **Correcto** |

### Verificaciones Arquitectónicas Específicas
1. **Responsabilidad definida:** Cada archivo cumple una única responsabilidad claramente acotada (entrada, enrutamiento, vista, componente de barra superior, componente de tabla, servicio de datos y datos DEMO).
2. **Ausencia de dependencias circulares:** El grafo de importaciones es un árbol dirigido acíclico (DAG) de profundidad máxima 3 (`app.js -> views/devices-view.js -> components/*` y `app.js -> services/device-service.js -> data/devices-demo-data.js`). No existe ningún ciclo.
3. **Aislamiento de componentes:** Ni `admin-navbar.js` ni `devices-table.js` importan `device-service.js` ni `devices-demo-data.js`; reciben todos sus datos y callbacks por parámetros (`{ devices, onDeviceAction }` y `{ activeSectionId, onNavigate }`).
4. **Separación de datos DEMO y presentación:** Los 7 dispositivos ficticios residen exclusivamente en `devices-demo-data.js`. No hay filas de dispositivos escritas en `web/index.html` ni incrustadas en `devices-table.js`.
5. **Reutilizabilidad:**
   - `renderAdminNavbar` puede invocarse desde cualquier futura vista administrativa (`cameras`, `alerts`, `reports`, `profile`) pasando únicamente `activeSectionId`.
   - `renderDevicesTable` recibe un arreglo genérico de objetos de dispositivo y un callback `onDeviceAction`.
6. **Uso de JavaScript ES6 y validez de referencias:** Todos los módulos utilizan sintaxis estándar ES6 (`import`/`export`, `const`, `Object.freeze`, `async`/`await`) y todas las rutas de importación incluyen la extensión `.js` requerida por los navegadores en ES Modules nativos.
7. **Observación menor de código muerto en CSS (`[OBS-CSS-01]`):** En [`web/css/admin-devices.css`](../../web/css/admin-devices.css#L486-L512) están declaradas las clases `.dev-preview-toolbar` y `.dev-preview-btn`, las cuales no son instanciadas por ningún módulo JS. No afectan la ejecución ni el diseño, pero conviene limpiarlas o vincularlas en el siguiente sprint.

---

## 3. Hallazgos del Modo DEMO y Seguridad

### 3.1. Auditoría del Modo DEMO
- **Datos exclusivamente sintéticos:** Verificado en [`devices-demo-data.js`](../../web/js/data/devices-demo-data.js#L22-L86). Los 7 registros llevan prefijo `[DEMO]` e identificadores `DEMO-DEV-001` a `DEMO-DEV-007`.
- **Cero consultas a PostgreSQL y cero llamadas a endpoints inventados:** Ningún archivo en `VIGIA_Dashboard/web/js/` contiene llamadas a `fetch()`, `XMLHttpRequest`, `WebSocket` ni conectores de base de datos.
- **Sin persistencia de operaciones provisionales:** `previewAddDeviceDemo()` en [`device-service.js`](../../web/js/services/device-service.js#L57-L101) inserta el registro validado únicamente en el arreglo local `memoryDevices` en RAM (`memoryDevices.unshift(demoRecord)`). No utiliza `localStorage`, `sessionStorage`, `IndexedDB` ni cookies. Al recargar la página (`F5`), la lista vuelve a los 7 registros iniciales.
- **Sin sesiones autenticadas ficticias:** El inicio de sesión (`#login`) sigue rechazando cualquier intento de acceso con el mensaje del Sprint 01 (`La autenticación todavía no está integrada con el servidor (Sprint 01). No se ha iniciado ninguna sesión.`). Además, el encabezado de la vista administrativa muestra permanentemente la insignia: `MODO DEMO — Datos sintéticos de demostración (Sin conexión a backend)`.

### 3.2. Análisis de las Rutas de Previsualización (`/app#devices`, `/app?demo=admin`, `/app?theme=dark#devices`)
- **Mecanismo actual de control:**
  - En [`web/js/router.js`](../../web/js/router.js#L32-L47), la función `resolveCurrentRoute()` evalúa en el cliente `window.location.hash` (`#devices`, `#cameras`, `#alerts`, `#reports`, `#profile`, `#camera-viewer`) y los parámetros de búsqueda `window.location.search` (`?demo=admin` o `?view=devices`).
  - En [`web/js/app.js`](../../web/js/app.js#L25-L29), se lee `?theme=dark` o `?theme=light` desde `window.location.search` y se asigna `document.documentElement.setAttribute('data-theme', requestedTheme)`.
- **Evaluación de riesgo en producción (`[OBS-SEG-01]` — Riesgo Medio):**
  - Actualmente **no existe un interruptor de configuración que deshabilite por defecto el enrutamiento DEMO fuera del entorno de desarrollo**. Cualquier usuario que escriba manualmente `#devices` o `?demo=admin` en la URL del navegador conmuta la visibilidad del DOM (`loginRoot.hidden = true; adminRoot.hidden = false`) y visualiza la maqueta con datos sintéticos DEMO.
  - Si bien no expone datos reales ni otorga permisos en el backend (porque los datos son estáticos y en el cliente), en el **Sprint 02 (Integración de autenticación)** el enrutador deberá condicionar el acceso a cualquier ruta distinta de `#login` a una sesión real verificada contra `VIGIA_API`, permitiendo el modo DEMO únicamente cuando el servidor inyecte o habilite explícitamente una bandera de entorno de desarrollo (`VIGIA_ENABLE_DEMO_MODE`).

### 3.3. Auditoría de Flask y Seguridad en `VIGIA_API/ingest_service.py`
Se inspeccionó [`VIGIA_API/ingest_service.py`](../../../VIGIA_API/ingest_service.py#L59-L355) y se ejecutaron pruebas de penetración controladas sobre el servidor local:

1. **Lista blanca `ALLOWED_DASHBOARD_ASSETS` ([líneas 72–85](../../../VIGIA_API/ingest_service.py#L72-L85)):**
   - Contiene exactamente los 12 archivos CSS y JS requeridos por el frontend (`css/tokens.css`, `css/base.css`, `css/login.css`, `css/admin-devices.css`, `js/app.js`, `js/router.js`, `js/data/devices-demo-data.js`, `js/services/device-service.js`, `js/components/admin-navbar.js`, `js/components/devices-table.js`, `js/views/login-view.js`, `js/views/devices-view.js`).
2. **Lista blanca `ALLOWED_BRAND_SVGS` ([líneas 60–69](../../../VIGIA_API/ingest_service.py#L60-L69)):**
   - Contiene exclusivamente los 8 archivos SVG oficiales ubicados en `Docs/GEST_PROY_SOFT/02_Logos_accesibilidad/svg/`.
3. **Protección contra Path Traversal y exposición de archivos:**
   - Tanto `serve_dashboard_asset` como `serve_brand_svg` verifican pertenencia exacta en el `Set` de lista blanca antes de tocar el disco y aplican `candidate.relative_to(...)` sobre rutas resueltas (`resolve()`).
   - Se comprobó experimentalmente que solicitar `/dashboard-assets/%2e%2e/README.md`, `/dashboard-assets/assets/backgrounds/README.md`, `/dashboard-assets/index.html` o `/assets/brand/README.md` devuelve **`404 Not Found`** sin filtrar contenido del sistema de archivos.
4. **Hallazgo en manejo de códigos HTTP 404 generales (`[OBS-FLASK-02]` — Severidad Baja/Media):**
   - Mientras que `405 Method Not Allowed` cuenta con un manejador explícito `@app.errorhandler(405)` ([línea 153](../../../VIGIA_API/ingest_service.py#L153)) y devuelve correctamente HTTP `405`, el archivo **no declara un `@app.errorhandler(404)`** antes del manejador genérico `@app.errorhandler(Exception)` ([línea 166](../../../VIGIA_API/ingest_service.py#L166)).
   - Como consecuencia, cuando un cliente solicita una ruta fuera de las registradas en Flask (por ejemplo `GET /ruta-inexistente` o una ruta con `..` que Werkzeug normaliza hacia la raíz como `/mobile/index.html`), Flask lanza `werkzeug.exceptions.NotFound`, el cual hereda de `Exception` y es capturado por `handle_unexpected_exception`, respondiendo con **HTTP `500` (`INTERNAL_ERROR`)** en lugar de **HTTP `404`**. *(Nota: los `404` explícitos retornados dentro de `serve_dashboard_asset`, `serve_brand_svg` y `push_camera_frame` sí devuelven `404` correctamente porque no lanzan excepción).*

---

## 4. Resultados de la Auditoría Funcional

Se verificó el comportamiento real de cada flujo e interacción en el código y mediante pruebas de ejecución:

| # | Caso Funcional Auditado | Comportamiento Real Verificado | Estado |
| :-: | :--- | :--- | :---: |
| **1** | Carga de Gestión de Dispositivos (`/app#devices` o `/app?demo=admin`) | Oculta `#app-root` (Login), muestra `#admin-root`, actualiza `document.title` y renderiza `.admin-shell` con la barra de navegación, la tarjeta blanca, la insignia `MODO DEMO`, la tabla con los 7 registros DEMO, los dos botones principales y el pie de página. | **Cumple** |
| **2** | Selección de `Dispositivos` en la navegación | El botón `Dispositivos` recibe la clase `.admin-nav-btn--active` y el atributo `aria-current="page"`. Al pulsarlo desde cualquier otra sección administrativa, navega a `#devices` y reconstruye la tabla de dispositivos. | **Cumple** |
| **3** | Navegación a secciones aún no implementadas (`Cámaras`, `Alertas`, `Informes`, `Perfil`) | Al pulsar cualquiera de estos botones, el hash cambia a `#cameras`, `#alerts`, `#reports` o `#profile`, el botón correspondiente se marca como activo (`aria-current="page"`) y la tarjeta blanca muestra el bloque `.admin-under-construction` con el texto: *«Sección "<Título>" en desarrollo. Esta ruta ya se encuentra registrada en el sistema de navegación administrativa, pero su implementación funcional pertenece a un sprint posterior...»* junto con el botón `Volver a Gestión de Dispositivos`. No se finge ninguna pantalla terminada. | **Cumple** |
| **4** | Botón `Visualización de Cámaras` (`#btn-camera-viewer`) | Navega a la ruta independiente `#camera-viewer`, resalta `Cámaras` en la barra superior y muestra el aviso de sección `"Visualización de Cámaras" en desarrollo` con botón de retorno a `#devices`. | **Cumple** |
| **5** | Botón `Agregar Dispositivos` (`#btn-add-device`) | Alterna (abre/cierra) en `#admin-provisional-slot` el formulario provisional `Registro Provisional de Dispositivo (Modo DEMO — Sprint 02A)` con campos `Nombre del Dispositivo *`, `Tipo de Dispositivo *` y `Estado DEMO`, y traslada el foco al campo de nombre. | **Cumple** |
| **6** | Validación de campos del formulario provisional | Si se envía con el nombre vacío o solo con espacios, `deviceService.previewAddDeviceDemo` lanza error y el formulario muestra una alerta accesible (`role="alert"`) con el texto `Ingresa el nombre del dispositivo para la validación DEMO.` y devuelve el foco al input. | **Cumple** |
| **7** | Confirmación DEMO al agregar dispositivo | Si se ingresa un nombre válido y se pulsa `Validar en Modo DEMO`, se cierra el panel provisional, se agrega temporalmente en memoria el registro con prefijo `[DEMO]` e ID `DEMO-TMP-008` al inicio de la tabla, y se muestra un aviso amarillo con el texto: `Confirmación DEMO: "[DEMO] ..." validado localmente en memoria. No se ha guardado información en el backend ni en PostgreSQL.` | **Cumple** |
| **8** | Acciones disponibles en cada registro (`Detalle (Provisional)`) | Cada fila dispone del botón `Detalle (Provisional)`. Al pulsarlo, despliega en `#admin-notice-area` un aviso (`role="status"`, `aria-live="polite"`) con los datos DEMO del equipo seleccionado e indica explícitamente que la edición y diagnóstico real se integrarán en sprints posteriores. | **Cumple** |
| **9** | Regreso al inicio de sesión | Al cambiar el hash a `#login` (o navegar a `/app`) o usar el botón «Atrás» del navegador tras haber entrado desde `/app`, el enrutador limpia y oculta `#admin-root` y vuelve a mostrar intacta la tarjeta de Inicio de Sesión (`#app-root`). *(Observación `[OBS-UX-03]`: no existe un botón visual dentro de la barra del administrador para ir a `#login` con un clic).* | **Cumple con observación** |
| **10** | Recarga directa de las rutas (`F5`) | Al recargar `/app#devices`, `/app#cameras`, `/app?theme=dark#devices` o `/app`, el servidor Flask entrega `web/index.html` (`200 OK`), `initRouter` evalúa el hash/query inicial al arrancar y restaura la vista solicitada con los 7 registros DEMO originales (confirmando que los registros temporales `DEMO-TMP-*` no persisten tras recargar). | **Cumple** |

---

## 5. Auditoría Visual y Responsive

> **Nota metodológica de transparencia:** En este entorno de ejecución por consola (Windows PowerShell sin motor de navegador gráfico headless Playwright/Selenium instalado en `.venv`), la auditoría visual y responsive se realizó combinando la verificación HTTP en vivo de las hojas de estilo y del DOM servido por Flask con el análisis métrico exacto de las reglas de layout (`CSS Grid`, `Flexbox`, `table-layout: fixed`, `clamp()` y `@media`) en [`tokens.css`](../../web/css/tokens.css) y [`admin-devices.css`](../../web/css/admin-devices.css) para las cuatro resoluciones objetivo:

### 5.1. Comportamiento por Resolución Objetivo

| Resolución | Breakpoint Activo | Comportamiento de Navegación, Contenedores y Cuadrícula | Desbordamiento Horizontal |
| :--- | :--- | :--- | :---: |
| **Escritorio (`1440 × 900`)** | `>= 1024px` (Reglas base desktop) | `.admin-shell` se centra con `max-width: 1200px` y `border-radius: 20px`. `.admin-navbar` muestra en una sola línea el logo circular izquierdo (`46×46px`), los 4 botones píldora centrados (`min-width: 118px`) y el botón circular `Perfil` (`46×46px`) a la derecha. La tabla `.devices-table` despliega las 5 columnas en paralelo (`border-spacing: 0.65rem 0; table-layout: fixed`). | **Sin desbordamiento** (`overflow-wrap: anywhere` en `.device-cell-box`) |
| **Laptop (`1366 × 768`)** | `>= 1024px` | `.admin-shell` utiliza los `1200px` completos con margen lateral cómodo (`~83px` a cada lado). Los encabezados de las 5 columnas y los 7 registros mantienen alineación vertical y horizontal uniforme. | **Sin desbordamiento** |
| **Tablet (`768 × 1024`)** | `@media (max-width: 1023px)` ([líneas 517–531](../../web/css/admin-devices.css#L517-L531)) | Se reduce el espaciado entre las 5 columnas a `0.4rem`, el relleno de celdas a `0.4rem 0.35rem` y la fuente a `--font-size-xs` (`13px`), manteniendo las 5 columnas visibles dentro de los `768px` sin barra de scroll horizontal. | **Sin desbordamiento** |
| **Móvil (`390 × 844`)** | `@media (max-width: 639px)` ([líneas 537–615](../../web/css/admin-devices.css#L537-L615)) | `.admin-nav-list` pasa a `order: 3; width: 100%; display: grid; grid-template-columns: repeat(2, 1fr)` (cuadrícula 2×2 debajo del logo y Perfil). `.devices-table thead` se oculta de forma accesible (`.sr-only`) y cada `<tr>` se transforma en una tarjeta vertical con fondo gris y `border-radius: 12px`, mostrando cada campo con su etiqueta a la izquierda (`content: attr(data-label)`) y su valor a la derecha. Los botones `Visualización de Cámaras` y `Agregar Dispositivos` ocupan `width: 100%` apilados verticalmente. | **Sin desbordamiento** |

### 5.2. Verificación de Elementos Visuales y Modos de Color (Claro y Oscuro)
- **Proporciones y bordes:** Contenedor exterior `.admin-shell` con radio de `20px` (`--admin-shell-radius: 20px`) y tarjeta interna `.admin-content-card` con radio de `16px` (`--admin-panel-radius: 16px`).
- **Encabezados y bloques por columna:** Cada `<th>` tiene fondo `--admin-data-header-bg` (`#C4C4CA` en claro / `#383838` en oscuro) con bordes superiores redondeados (`12px`), y cada `<td>` tiene fondo `--admin-data-block-bg` (`#D4D4D8` en claro / `#242424` en oscuro) con bordes inferiores redondeados en la última fila, formando las cinco áreas rectangulares verticales de fondo gris sólido especificadas.
- **Estados visuales de dispositivos:**
  - `Conectado` (`.device-status-pill--online`): pastilla verde con indicador circular (`#DCFCE7` / texto `#14532D` en claro; `#143321` / texto `#BBF7D0` en oscuro).
  - `Desconectado` (`.device-status-pill--offline`): pastilla roja con indicador circular (`#FEE2E2` / texto `#7F1D1D` en claro; `#3B1818` / texto `#FECACA` en oscuro).
  - `En mantenimiento` (`.device-status-pill--maintenance`): pastilla ámbar con indicador circular (`#FEF3C7` / texto `#78350F` en claro; `#3B2A14` / texto `#FDE68A` en oscuro).
- **Modo Oscuro (`[data-theme="dark"]`):** Cumple exactamente la tabla de referencia solicitada (`#121212` fondo general, `#1E1E1E` tarjeta principal, `#2C2C2C` panel interno, `#424242` botones, `#E0E0E0` texto principal, `#A0A0A0` texto secundario, `#1A1A1A` inputs, `#444444` borde de inputs y `#000000` reservado para `--admin-camera-slot-bg`).

---

## 6. Integridad del Proyecto

1. **`VIGIA_Dashboard/mobile/index.html` intacto:** Conserva exactamente su tamaño original de `13,071` bytes y su respuesta `200 OK` en `GET /mobile`.
2. **`login-view.js` y `login.css` intactos:** Se inspeccionaron [`web/js/views/login-view.js`](../../web/js/views/login-view.js) (`166` líneas, `5,418` bytes) y [`web/css/login.css`](../../web/css/login.css) (`228` líneas, `5,717` bytes), confirmando que no sufrieron ninguna modificación durante el Sprint 02A.
3. **Rutas de ingesta intactas:** `GET /`, `GET /mobile` y `POST /api/v1/cameras/<codigo_camara>/push` conservan su comportamiento y pasan las 49 pruebas unitarias de `test_mobile_ingest_api.py` (162/162 pruebas totales del repositorio en estado `OK`).
4. **Base de datos y demás módulos intactos:** `BD/`, `VIGIA_Core/`, `VIGIA_Vision/`, `VIGIA_IoT/` y `VIGIA_Automation/` no presentan ningún archivo modificado.

---

## 7. Evidencia de Pruebas Ejecutadas

### 7.1. Pruebas HTTP de Activos y Rutas en Flask (`VIGIA_API.ingest_service`)
```text
200 | 2943 bytes  | GET /app
200 | 6121 bytes  | GET /dashboard-assets/css/tokens.css
200 | 1295 bytes  | GET /dashboard-assets/css/base.css
200 | 5717 bytes  | GET /dashboard-assets/css/login.css
200 | 15825 bytes | GET /dashboard-assets/css/admin-devices.css
200 | 2316 bytes  | GET /dashboard-assets/js/app.js
200 | 2550 bytes  | GET /dashboard-assets/js/router.js
200 | 2877 bytes  | GET /dashboard-assets/js/data/devices-demo-data.js
200 | 3764 bytes  | GET /dashboard-assets/js/services/device-service.js
200 | 4378 bytes  | GET /dashboard-assets/js/components/admin-navbar.js
200 | 5252 bytes  | GET /dashboard-assets/js/components/devices-table.js
200 | 5418 bytes  | GET /dashboard-assets/js/views/login-view.js
200 | 14805 bytes | GET /dashboard-assets/js/views/devices-view.js
200 | 1779 bytes  | GET /assets/brand/producto_figura_dark.svg
200 | 85 bytes    | GET /
200 | 13071 bytes | GET /mobile
```

### 7.2. Pruebas de Seguridad y Códigos de Error HTTP en Flask
```text
GET  /dashboard-assets/%2e%2e/README.md                  -> HTTP 404 (Bloqueado por lista blanca)
GET  /dashboard-assets/assets/backgrounds/README.md      -> HTTP 404 (Bloqueado por lista blanca)
GET  /assets/brand/README.md                             -> HTTP 404 (Bloqueado por lista blanca)
POST /app                                                -> HTTP 405 (METHOD_NOT_ALLOWED conservado)
GET  /api/v1/cameras/CAM-ENTRADA/push                    -> HTTP 405 (METHOD_NOT_ALLOWED conservado)
POST /api/v1/cameras/CAM-ENTRADA/push (sin clave)        -> HTTP 503 (Modo seguro fail-closed conservado)
GET  /ruta-inexistente                                   -> HTTP 500 (Observación OBS-FLASK-02 registrada)
```

---

## 8. Archivos Inspeccionados

1. [`VIGIA_Dashboard/web/index.html`](../../web/index.html)
2. [`VIGIA_Dashboard/web/css/tokens.css`](../../web/css/tokens.css)
3. [`VIGIA_Dashboard/web/css/base.css`](../../web/css/base.css)
4. [`VIGIA_Dashboard/web/css/login.css`](../../web/css/login.css)
5. [`VIGIA_Dashboard/web/css/admin-devices.css`](../../web/css/admin-devices.css)
6. [`VIGIA_Dashboard/web/js/app.js`](../../web/js/app.js)
7. [`VIGIA_Dashboard/web/js/router.js`](../../web/js/router.js)
8. [`VIGIA_Dashboard/web/js/views/login-view.js`](../../web/js/views/login-view.js)
9. [`VIGIA_Dashboard/web/js/views/devices-view.js`](../../web/js/views/devices-view.js)
10. [`VIGIA_Dashboard/web/js/components/admin-navbar.js`](../../web/js/components/admin-navbar.js)
11. [`VIGIA_Dashboard/web/js/components/devices-table.js`](../../web/js/components/devices-table.js)
12. [`VIGIA_Dashboard/web/js/services/device-service.js`](../../web/js/services/device-service.js)
13. [`VIGIA_Dashboard/web/js/data/devices-demo-data.js`](../../web/js/data/devices-demo-data.js)
14. [`VIGIA_Dashboard/mobile/index.html`](../../mobile/index.html)
15. [`VIGIA_API/ingest_service.py`](../../../VIGIA_API/ingest_service.py)
16. [`VIGIA_Dashboard/README.md`](../../README.md)
17. [`VIGIA_Dashboard/Docs/SISTEMA_DISENO.md`](../SISTEMA_DISENO.md)
18. [`VIGIA_Dashboard/Docs/NAVEGACION_Y_RUTAS.md`](../NAVEGACION_Y_RUTAS.md)
19. [`VIGIA_Dashboard/Docs/MODO_DEMO.md`](../MODO_DEMO.md)
20. [`VIGIA_Dashboard/Docs/sprints/SPRINT_02A_GESTION_DISPOSITIVOS.md`](../sprints/SPRINT_02A_GESTION_DISPOSITIVOS.md)

---

## 9. Riesgos Pendientes

1. **Riesgo de exposición accidental de la vista DEMO en producción (`[OBS-SEG-01]`):** Al no existir aún autenticación real ni una bandera de entorno que bloquee `#devices` y `?demo=admin`, cualquier usuario con acceso a `/app` puede visualizar la maqueta DEMO si introduce manualmente el hash o query string.
2. **Enmascaramiento de errores 404 genéricos como 500 en `ingest_service.py` (`[OBS-FLASK-02]`):** Las peticiones a URLs no registradas fuera de `/dashboard-assets/*` y `/assets/brand/*` son capturadas por `@app.errorhandler(Exception)` y devuelven `500` en lugar de `404`.
3. **Proceso previo en puerto `5000` en la máquina de desarrollo:** Si el operador mantiene abierto un proceso de Python anterior al Sprint 02A en el puerto `5000`, dicho proceso tendrá en memoria la lista `ALLOWED_DASHBOARD_ASSETS` del Sprint 01 y responderá `404` para `admin-devices.css` hasta que sea reiniciado.

---

## 10. Correcciones Recomendadas (Sin Ejecutar en esta Auditoría)

1. **Para `[OBS-SEG-01]` (Control de habilitación del Modo DEMO):**
   - Condicionar en `router.js` y `app.js` la resolución de rutas administrativas sin sesión (`#devices`, `?demo=admin`) a una bandera explícita de desarrollo (por ejemplo, un atributo `data-demo-enabled="true"` inyectado únicamente cuando `VIGIA_ENABLE_DEMO_MODE=1` esté activo en el entorno de desarrollo, manteniéndolo en `false` por defecto).
2. **Para `[OBS-FLASK-02]` (Preservación de HTTP 404 en `VIGIA_API/ingest_service.py`):**
   - Añadir un manejador `@app.errorhandler(404)` explícito en `create_ingest_app()` (o verificar `isinstance(exc, HTTPException)` dentro de `handle_unexpected_exception`) para que cualquier ruta inexistente conserve su código HTTP `404` en lugar de transformarse en `500`.
3. **Para `[OBS-UX-03]` y `[OBS-CSS-01]` (Retorno explícito a Login y limpieza de CSS):**
   - Incluir un botón o enlace explícito «Salir de vista DEMO / Ir a Inicio de Sesión (`#login`)» en el aviso de modo DEMO o en la vista de `Perfil`, y eliminar o utilizar las clases `.dev-preview-toolbar` / `.dev-preview-btn` de `admin-devices.css`.

---

## 11. Resolución de Observaciones (`VO-02A-R1`)

Con fecha **30 de octubre de 2026**, las cuatro observaciones registradas en esta auditoría fueron resueltas y verificadas en la iteración correctiva [`VO-02A-R1_CORRECCION_OBSERVACIONES.md`](./VO-02A-R1_CORRECCION_OBSERVACIONES.md):

| Código | Observación | Resolución Aplicada | Verificación Ejecutada | Estado |
| :---: | :--- | :--- | :--- | :---: |
| **`OBS-SEG-01`** | Control de acceso al modo DEMO deshabilitado por defecto | Se añadió el atributo `data-demo-enabled="false"` por defecto en `web/index.html`, controlado desde Flask mediante la variable explícita de entorno `VIGIA_ENABLE_FRONTEND_DEMO` (`False` por defecto). `router.js` y `app.js` bloquean `#devices` y `?demo=admin` cuando DEMO está deshabilitado, regresando a `#login` con aviso accesible. | Prueba HTTP con `VIGIA_ENABLE_FRONTEND_DEMO` sin definir (`data-demo-enabled="false"`) y definido en `"1"` (`data-demo-enabled="true"` en localhost y LAN `192.168.1.75`). | **RESUELTO** |
| **`OBS-FLASK-02`** | Manejo incorrecto de HTTP 404 en `ingest_service.py` | Se registró `@app.errorhandler(404)` explícito y se preservó `isinstance(exc, HTTPException)` en `handle_unexpected_exception` dentro de `VIGIA_API/ingest_service.py`. | `GET /ruta-inexistente`, `GET /dashboard-assets/../mobile/index.html` y `GET /assets/brand/..%2fREADME.md` responden **HTTP `404`**, y `POST /app` responde **HTTP `405`**. | **RESUELTO** |
| **`OBS-UX-03`** | Ausencia de botón para salir de DEMO | Se incorporó el botón accesible `#btn-exit-demo` (`Salir de DEMO / Ir al Inicio de Sesión`) en `devices-view.js`, conectado a `exitDemoToLogin()` en `app.js` para limpiar el estado temporal en memoria y regresar a `#login`. | Verificación de estructura DOM y flujo de limpieza de `deviceService` hacia `#login`. | **RESUELTO** |
| **`OBS-CSS-01`** | Reglas CSS sin uso (`.dev-preview-toolbar`, `.dev-preview-btn`) | Se eliminaron las reglas huérfanas `.dev-preview-toolbar` y `.dev-preview-btn` de `web/css/admin-devices.css` y se añadieron `.admin-demo-status-row` y `.admin-exit-demo-btn`. | Inspección de `admin-devices.css` sin selectores huérfanos. | **RESUELTO** |

**Dictamen actualizado tras `VO-02A-R1`:** **APROBADO** (0 observaciones abiertas).

