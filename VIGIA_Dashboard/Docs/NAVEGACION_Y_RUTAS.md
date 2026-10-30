# Navegación y Rutas del Frontend — `VIGIA_Dashboard`

**Proyecto:** VIGÍA Vision Systems  
**Módulo:** `VIGIA_Dashboard`  
**Módulos asociados:** [`web/js/router.js`](../web/js/router.js), [`web/js/components/admin-navbar.js`](../web/js/components/admin-navbar.js)  
**Versión:** 1.0 (Sprint 02A)

---

## 1. Arquitectura de Navegación

`VIGIA_Dashboard` se sirve desde Flask bajo el punto de entrada único `GET /app` y gestiona la transición entre vistas mediante un enrutador ligero en el cliente ([`web/js/router.js`](../web/js/router.js)) basado en fragmentos hash (`window.location.hash`).

Este esquema permite:
- Conservar intacta la pantalla de **Inicio de Sesión** (`#login`) como vista predeterminada en `/app`.
- Habilitar la navegación entre las secciones del módulo de Administración durante las fases de desarrollo visual (**Modo DEMO**) sin requerir recargas de servidor ni modificar rutas del backend.

---

## 2. Secciones Administrativas e Identificadores Oficiales

La barra de navegación superior reutilizable ([`admin-navbar.js`](../web/js/components/admin-navbar.js)) y las acciones principales contemplan los siguientes identificadores canónicos:

| Identificador | Etiqueta en UI | Pantalla / Vista Asociada | Ruta Hash en `/app` | Estado en Sprint 02A |
| :--- | :--- | :--- | :--- | :---: |
| `login` | Inicio de Sesión | Pantalla de Inicio de Sesión | `/app` o `/app#login` | **Implementado (Sprint 01)** |
| `devices` | Dispositivos | **Gestión de Dispositivos** | `/app#devices` | **Implementado (Sprint 02A — DEMO)** |
| `cameras` | Cámaras | Monitoreo de Cámaras | `/app#cameras` | Preparado *(En desarrollo)* |
| `alerts` | Alertas | Gestión de Alertas | `/app#alerts` | Preparado *(En desarrollo)* |
| `reports` | Informes | Gestión de Informes | `/app#reports` | Preparado *(En desarrollo)* |
| `profile` | Perfil | Perfil de Usuario | `/app#profile` | Preparado *(En desarrollo)* |
| `camera-viewer` | Visualización de Cámaras | Visualización de Cámaras | `/app#camera-viewer` | Preparado *(En desarrollo)* |

---

## 3. Comportamiento de los Botones de Navegación y Acciones

### 3.1. Barra de Navegación Superior (`.admin-navbar`)
1. **Logotipo circular izquierdo (`.admin-nav-brand`):**
   - Muestra el símbolo oficial de VIGÍA (`/assets/brand/producto_figura_dark.svg`).
   - Al pulsarlo, dirige a la sección principal del administrador: `#devices` (**Gestión de Dispositivos**).
2. **Botones centrales tipo píldora (`.admin-nav-btn`):**
   - **Dispositivos (`devices`):** Se marca visual y semánticamente como sección activa (`aria-current="page"`, clase `.admin-nav-btn--active`) cuando el usuario se encuentra en **Gestión de Dispositivos**, renderizando la cuadrícula de 5 columnas y los botones de acción inferiores.
   - **Cámaras (`cameras`), Alertas (`alerts`) e Informes (`reports`):** Actualizan la ruta activa (`#cameras`, `#alerts`, `#reports`), marcan el botón seleccionado como activo y muestran dentro de la tarjeta blanca un aviso claro de **funcionalidad en desarrollo** con un botón para regresar a `Gestión de Dispositivos`, sin presentar pantallas ficticias que aparenten estar terminadas.
3. **Botón circular derecho de Perfil (`.admin-profile-btn`):**
   - Navega a `#profile` y presenta el aviso estandarizado de funcionalidad en desarrollo.

### 3.2. Acciones Principales en Gestión de Dispositivos
Debajo de la tarjeta blanca interna de **Gestión de Dispositivos** se ubican dos botones tipo píldora:

1. **`Visualización de Cámaras` (`#btn-camera-viewer`):**
   - Navega hacia la ruta independiente `#camera-viewer` (asociada visualmente al ámbito de cámaras en la barra superior), dejando preparado el punto de conexión para la futura pantalla de visualización de flujos de video.
2. **`Agregar Dispositivos` (`#btn-add-device`):**
   - Despliega dentro de la tarjeta de **Gestión de Dispositivos** el panel provisional de registro en **Modo DEMO**, permitiendo validar campos obligatorios localmente y comprobar la retroalimentación visual sin enviar peticiones al backend.

