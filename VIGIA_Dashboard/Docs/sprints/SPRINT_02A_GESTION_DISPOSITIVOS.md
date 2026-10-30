# SPRINT 02A — Interfaz de Gestión de Dispositivos (Administrador)

---

## 1. Identificador y Objetivo

- **Identificador:** `SPRINT_02A`
- **Nombre:** Interfaz de Gestión de Dispositivos (Administrador)
- **Módulo:** `VIGIA_Dashboard/`
- **Fecha de cierre:** 30 de octubre de 2026
- **Objetivo:** Implementar la primera pantalla del módulo de administración de **VIGÍA Vision Systems** (**Gestión de Dispositivos**) respetando fielmente el diseño visual proporcionado, utilizando datos sintéticos DEMO desacoplados, preparando la barra de navegación superior reutilizable y asegurando adaptabilidad responsive en móvil, tableta y escritorio, así como soporte de tokens para modo claro y modo oscuro.

---

## 2. Alcance Implementado

1. **Contenedor principal administrativo (`.admin-shell`):** Fondo general gris humo (`#F4F4F6` en modo claro / `#121212` en modo oscuro) y tarjeta principal gris claro (`#DFDFE2` / `#1E1E1E`) con bordes redondeados de `20px`.
2. **Barra de navegación superior reutilizable (`admin-navbar.js`):**
   - Logotipo circular a la izquierda con el recurso oficial `/assets/brand/producto_figura_dark.svg`.
   - Cuatro botones de navegación centrados tipo píldora (`Dispositivos`, `Cámaras`, `Alertas`, `Informes`) con fondo gris medio y texto negro centrado, marcando `Dispositivos` como sección activa (`aria-current="page"`).
   - Botón circular de `Perfil` a la derecha.
3. **Área de contenido y cuadrícula de 5 columnas (`devices-table.js`):**
   - Tarjeta interna blanca sólida (`#FFFFFF` / `#2C2C2C` en modo oscuro) con título centrado en negrita **Gestión de Dispositivos**.
   - Tabla estructurada en cinco columnas con áreas rectangulares de fondo gris sólido por columna: `Nombre del Dispositivo`, `Tipo`, `Estado`, `Última Actividad` y `Acciones`.
   - Distinción visual clara para los estados `Conectado`, `Desconectado` y `En mantenimiento`.
   - Transformación responsiva a tarjetas de registro en pantallas móviles (`< 640px`) para evitar comprimir las cinco columnas.
4. **Datos sintéticos y capa de servicio (`devices-demo-data.js` + `device-service.js`):**
   - Conjunto de **7 dispositivos DEMO** variados y etiquetados explícitamente como `[DEMO]`, separados del HTML y de los componentes visuales mediante una interfaz de servicio asíncrona en memoria.
5. **Acciones principales y pie de página (`devices-view.js`):**
   - Botón píldora **Visualización de Cámaras** conectado a la ruta `#camera-viewer`.
   - Botón píldora **Agregar Dispositivos** que despliega el formulario provisional DEMO con validación local de campos obligatorios y confirmación DEMO sin persistencia en backend.
   - Pie de página centrado **VIGIA Vision Systems** en la parte inferior del contenedor principal.
6. **Conservación íntegra del Inicio de Sesión (Sprint 01):**
   - La vista de login no fue reconstruida ni alterada en su diseño o validaciones; sólo se añadió el contenedor `#admin-root` en `web/index.html` y el enrutador hash en `web/js/app.js` para permitir la previsualización DEMO en `/app#devices`.

---

## 3. Archivos Creados y Modificados

### Archivos Creados
1. [`VIGIA_Dashboard/web/css/admin-devices.css`](../../web/css/admin-devices.css) — Estilos del contenedor administrativo, barra de navegación superior, cuadrícula de 5 columnas con bloques rectangulares grises, estados, acciones principales y adaptación móvil/tableta/escritorio.
2. [`VIGIA_Dashboard/web/js/data/devices-demo-data.js`](../../web/js/data/devices-demo-data.js) — 7 registros sintéticos DEMO aislados de la capa visual.
3. [`VIGIA_Dashboard/web/js/services/device-service.js`](../../web/js/services/device-service.js) — Servicio de acceso a datos de dispositivos en memoria preparado para futura sustitución por API.
4. [`VIGIA_Dashboard/web/js/components/admin-navbar.js`](../../web/js/components/admin-navbar.js) — Componente reutilizable de la barra de navegación superior (`devices`, `cameras`, `alerts`, `reports`, `profile`).
5. [`VIGIA_Dashboard/web/js/components/devices-table.js`](../../web/js/components/devices-table.js) — Componente reutilizable de la cuadrícula/tabla de 5 columnas.
6. [`VIGIA_Dashboard/web/js/views/devices-view.js`](../../web/js/views/devices-view.js) — Controlador de la pantalla **Gestión de Dispositivos**, formulario provisional DEMO y avisos de secciones en desarrollo.
7. [`VIGIA_Dashboard/web/js/router.js`](../../web/js/router.js) — Enrutador basado en hash para alternar entre `#login` y las rutas administrativas en Modo DEMO.
8. [`VIGIA_Dashboard/Docs/SISTEMA_DISENO.md`](../SISTEMA_DISENO.md) — Documentación del sistema de diseño (Modo Claro, Modo Oscuro, tipografía, radios, espaciados y componentes).
9. [`VIGIA_Dashboard/Docs/NAVEGACION_Y_RUTAS.md`](../NAVEGACION_Y_RUTAS.md) — Documentación de las secciones administrativas, identificadores y estado de rutas.
10. [`VIGIA_Dashboard/Docs/MODO_DEMO.md`](../MODO_DEMO.md) — Documentación del origen de datos sintéticos, separación DEMO/API y URLs de previsualización.
11. [`VIGIA_Dashboard/Docs/sprints/SPRINT_02A_GESTION_DISPOSITIVOS.md`](./SPRINT_02A_GESTION_DISPOSITIVOS.md) — Presente informe del Sprint 02A.

### Archivos Modificados
1. [`VIGIA_Dashboard/web/css/tokens.css`](../../web/css/tokens.css) — Ampliación con variables reutilizables del administrador para Modo Claro y Modo Oscuro (`[data-theme="dark"]`).
2. [`VIGIA_Dashboard/web/index.html`](../../web/index.html) — Enlace a `admin-devices.css` e inclusión del contenedor `<main class="admin-viewport" id="admin-root" hidden></main>`, conservando intacto `<main class="login-viewport" id="app-root">`.
3. [`VIGIA_Dashboard/web/js/app.js`](../../web/js/app.js) — Integración del enrutador hash y del parámetro opcional `?theme=dark|light` junto con la inicialización intacta de `initLoginView`.
4. [`VIGIA_API/ingest_service.py`](../../../VIGIA_API/ingest_service.py) — Actualización mínima de la lista blanca `ALLOWED_DASHBOARD_ASSETS` para permitir que Flask sirva los nuevos módulos CSS y JS del Sprint 02A bajo `/dashboard-assets/<path:filename>`.
5. [`VIGIA_Dashboard/README.md`](../../README.md) y [`VIGIA_Dashboard/Docs/README.md`](../README.md) — Actualización del estado actual, árbol de archivos y enlaces a los nuevos documentos.

---

## 4. Componentes Implementados y Reutilizabilidad

| Componente / Módulo | Ubicación | Responsabilidad y Reutilización |
| :--- | :--- | :--- |
| **`renderAdminNavbar`** | `web/js/components/admin-navbar.js` | Renderiza el encabezado administrativo con logo circular oficial, las 4 píldoras centrales y el botón circular de Perfil. Reutilizable en las futuras vistas de `Cámaras`, `Alertas`, `Informes` y `Perfil`. |
| **`renderDevicesTable`** | `web/js/components/devices-table.js` | Construye la cuadrícula de 5 columnas con áreas rectangulares de fondo gris sólido y celdas `.device-cell-box`. Desacoplada del origen de datos. |
| **`createDeviceService`** | `web/js/services/device-service.js` | Encapsula `listDevices()`, `getDeviceById()` y `previewAddDeviceDemo()`. Permite cambiar de datos DEMO a llamadas HTTP a `VIGIA_API` sin tocar la UI. |
| **`initRouter` / `navigateToRoute`** | `web/js/router.js` | Gestiona las transiciones por hash (`#login`, `#devices`, `#cameras`, `#alerts`, `#reports`, `#profile`, `#camera-viewer`). |

---

## 5. Pruebas Realizadas y Resultados

1. **Verificación de servicio HTTP desde Flask (`127.0.0.1:5000` y LAN `192.168.1.75:5000`):**
   - Se comprobaron mediante peticiones HTTP reales todos los recursos existentes y los nuevos módulos del Sprint 02A servidos por `VIGIA_API/ingest_service.py`:
     - `GET /app` → `200 OK`
     - `GET /dashboard-assets/css/tokens.css` → `200 OK`
     - `GET /dashboard-assets/css/admin-devices.css` → `200 OK`
     - `GET /dashboard-assets/js/app.js` → `200 OK`
     - `GET /dashboard-assets/js/router.js` → `200 OK`
     - `GET /dashboard-assets/js/data/devices-demo-data.js` → `200 OK`
     - `GET /dashboard-assets/js/services/device-service.js` → `200 OK`
     - `GET /dashboard-assets/js/components/admin-navbar.js` → `200 OK`
     - `GET /dashboard-assets/js/components/devices-table.js` → `200 OK`
     - `GET /dashboard-assets/js/views/devices-view.js` → `200 OK`
     - `GET /assets/brand/producto_figura_dark.svg` → `200 OK`
     - `GET /` y `GET /mobile` → `200 OK` (intactos)
     - `POST /api/v1/cameras/CAM-ENTRADA/push` → `503 Service Unavailable` (modo *fail-closed* intacto)
2. **Suite de pruebas automatizadas del repositorio (`unittest`):**
   - Ejecución de `.\.venv\Scripts\python.exe -m unittest discover -s tests/unit -p "test_*.py" -v`: **162 pruebas ejecutadas, 162 aprobadas (`OK`)**.
3. **Inspección de estructura, datos DEMO y criterios de aceptación:**
   - Se verificó que `devices-demo-data.js` provee 7 registros DEMO con estados `Conectado`, `Desconectado` y `En mantenimiento`, que `devices-table.js` genera las 5 columnas requeridas con sus atributos `data-label` para adaptación móvil y que ninguna función realiza llamadas a PostgreSQL ni a endpoints inexistentes.

---

## 6. Limitaciones Conocidas

1. **Fase exclusivamente de interfaz (Modo DEMO):** Los datos mostrados en **Gestión de Dispositivos** son sintéticos y las altas provisionales en `Agregar Dispositivos` solo se validan en memoria durante la visualización actual.
2. **Secciones hermanas en desarrollo:** Las opciones `Cámaras`, `Alertas`, `Informes`, `Perfil` y `Visualización de Cámaras` están registradas en la navegación y muestran un aviso explícito de funcionalidad en desarrollo.
3. **Sin selector interactivo de tema en la UI final:** Los estilos de Modo Claro y Modo Oscuro están completamente implementados mediante variables CSS y pueden alternarse añadiendo `?theme=dark` o `?theme=light` en la URL, quedando listos para vincularse a un control de usuario cuando se especifique.

---

## 7. Pendientes para la Siguiente Fase

1. Implementar el formulario completo de registro y configuración de dispositivos/cámaras conforme a las especificaciones del siguiente sprint.
2. Desarrollar las vistas administrativas restantes (`Monitoreo de Cámaras`, `Visualización de Cámaras`, `Gestión de Alertas`, `Gestión de Informes` y `Perfil`) reutilizando `admin-navbar.js` y el contenedor `.admin-shell`.
3. Integrar `device-service.js` y `login-view.js` con los endpoints reales de `VIGIA_API` cuando se aborde la fase de integración con backend.

