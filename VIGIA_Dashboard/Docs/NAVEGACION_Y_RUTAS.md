# Navegación y Rutas del Frontend — `VIGIA_Dashboard`

**Proyecto:** VIGÍA Vision Systems  
**Módulo:** `VIGIA_Dashboard`  
**Módulos asociados:** [`web/js/router.js`](../web/js/router.js), [`web/js/components/admin-navbar.js`](../web/js/components/admin-navbar.js)  
**Versión:** 1.1 (Sprint 02A + Refinamiento Visual `VO-02A-R2`)

---

## 1. Arquitectura de Navegación

`VIGIA_Dashboard` se sirve desde Flask bajo el punto de entrada único `GET /app` y gestiona la transición entre vistas mediante un enrutador ligero en el cliente ([`web/js/router.js`](../web/js/router.js)) basado en fragmentos hash (`window.location.hash`).

Este esquema permite:
- Conservar intacta la pantalla de **Inicio de Sesión** (`#login`) como vista predeterminada en `/app`.
- Exigir que la bandera de entorno `VIGIA_ENABLE_FRONTEND_DEMO=1` esté activa en el servidor (`data-demo-enabled="true"`) antes de permitir el acceso a las rutas administrativas de previsualización DEMO.
- Habilitar la navegación fluida entre las secciones del módulo de Administración sin requerir recargas de servidor ni modificar contratos del backend.

---

## 2. Secciones Administrativas, Iconografía e Identificadores Oficiales

La barra de navegación horizontal superior reutilizable ([`admin-navbar.js`](../web/js/components/admin-navbar.js)) y las acciones principales contemplan los siguientes identificadores canónicos:

| Identificador | Tooltip / Etiqueta en UI | Pantalla / Vista Asociada | Icono SVG Inline (`22×22px`) | Ruta Hash en `/app` | Estado en Sprint 02A |
| :--- | :--- | :--- | :--- | :--- | :---: |
| `login` | Inicio de Sesión | Pantalla de Inicio de Sesión | Logotipo oficial circular | `/app` o `/app#login` | **Implementado (Sprint 01)** |
| `devices` | `Dispositivos` | **Gestión de Dispositivos** | Monitor con nodo de hardware | `/app#devices` | **Implementado (Sprint 02A — DEMO)** |
| `cameras` | `Cámaras` | Monitoreo de Cámaras | Cámara de videovigilancia (CCTV) | `/app#cameras` | Preparado *(En desarrollo)* |
| `alerts` | `Alertas` | Gestión de Alertas | Campana de alerta operativa | `/app#alerts` | Preparado *(En desarrollo)* |
| `reports` | `Informes` | Gestión de Informes | Documento con gráfica de barras | `/app#reports` | Preparado *(En desarrollo)* |
| `profile` | `Perfil` | Perfil de Usuario | Silueta geométrica de usuario | `/app#profile` | Preparado *(En desarrollo)* |
| `camera-viewer` | `Visualización de Cámaras` | Visualización de Cámaras | *(Asociado a `cameras`)* | `/app#camera-viewer` | Preparado *(En desarrollo)* |

---

## 3. Comportamiento de la Barra de Navegación Superior y Acciones (`VO-02A-R2`)

### 3.1. Barra de Navegación Horizontal Superior (`header.admin-navbar`)
La barra de navegación permanece horizontalmente en la parte superior del contenedor `.admin-shell` respetando la distribución original:

```text
┌──────────────────────────────────────────────────────────────┐
│ LOGO       Dispositivos  Cámaras  Alertas  Informes   Perfil │
└──────────────────────────────────────────────────────────────┘
```

1. **Logotipo circular izquierdo (`.admin-nav-brand`):**
   - Muestra el símbolo oficial de VIGÍA (`/assets/brand/producto_figura_dark.svg`).
   - Al pulsarlo, dirige a la sección principal del administrador: `#devices` (**Gestión de Dispositivos**).
2. **Cuatro botones centrales minimalistas con iconos SVG (`.admin-nav-btn`):**
   - **Dispositivos (`devices`):** Se marca visual y semánticamente como sección activa (`aria-current="page"`, clase `.admin-nav-btn--active` e indicador inferior `.admin-nav-indicator`) cuando el usuario se encuentra en **Gestión de Dispositivos**, renderizando la cuadrícula de 5 columnas y los botones de acción inferiores.
   - **Cámaras (`cameras`), Alertas (`alerts`) e Informes (`reports`):** Actualizan la ruta activa (`#cameras`, `#alerts`, `#reports`), marcan el icono seleccionado como activo y muestran dentro de la tarjeta blanca un aviso compacto de **funcionalidad en desarrollo** (`.admin-under-construction`) con un botón para regresar a `Gestión de Dispositivos`.
3. **Botón derecho de Perfil (`.admin-profile-btn`):**
   - Utiliza un icono SVG minimalista de silueta de usuario con el mismo lenguaje visual que el resto de la navegación, dirigiendo a `#profile`.
4. **Tooltips discretos (`.admin-nav-tooltip`):**
   - En escritorio y tableta, al pasar el cursor (`:hover`) o enfocar con teclado (`:focus-visible`), aparece suavemente debajo de cada icono una etiqueta discreta (`Dispositivos`, `Cámaras`, `Alertas`, `Informes`, `Perfil`) animada mediante `opacity` y `transform` (`180ms`).
   - En pantallas móviles (`< 640px`), además de los atributos `aria-label` y `aria-describedby`, se muestra una etiqueta corta visible debajo de cada icono en la barra superior para no depender de `hover`.

### 3.2. Acciones Principales en Gestión de Dispositivos y Salida de DEMO
1. **`Visualización de Cámaras` (`#btn-camera-viewer`):**
   - Navega hacia la ruta independiente `#camera-viewer` (asociada visualmente al ámbito de cámaras en la barra superior), dejando preparado el punto de conexión para la futura pantalla de visualización de flujos de video.
2. **`Agregar Dispositivos` (`#btn-add-device`):**
   - Despliega dentro de la tarjeta de **Gestión de Dispositivos** el panel provisional de registro en **Modo DEMO**, permitiendo validar campos obligatorios localmente y comprobar la retroalimentación visual sin enviar peticiones al backend.
3. **`Salir de DEMO / Ir al Inicio de Sesión` (`#btn-exit-demo`):**
   - Ubicado en el encabezado de la tarjeta principal, limpia los parámetros de previsualización y retorna a `#login`.
