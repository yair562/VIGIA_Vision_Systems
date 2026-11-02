# VO-02A-R2 — Refinamiento Visual de la Navegación Superior de VIGÍA

**Proyecto:** VIGÍA Vision Systems  
**Módulo:** `VIGIA_Dashboard`  
**Fase:** Sprint 02A — Refinamiento Visual (`VO-02A-R2`)  
**Fecha:** 2026-10-30  
**Dictamen Final:** **APROBADO**

---

## 1. Nueva Apariencia de la Barra Superior

Se conservó estrictamente la **barra de navegación horizontal en la parte superior** (`<header class="admin-navbar">`) dentro de `.admin-shell`, manteniendo su ubicación y el orden original de sus tres grupos de elementos:

```text
┌──────────────────────────────────────────────────────────────┐
│ LOGO       Dispositivos  Cámaras  Alertas  Informes   Perfil │
└──────────────────────────────────────────────────────────────┘
```

1. **Extremo izquierdo (`.admin-nav-brand`):** Logotipo circular oficial de VIGÍA (`/assets/brand/producto_figura_dark.svg`, `44×44px`) que enlaza a `#devices`.
2. **Zona central (`nav.admin-nav-primary > ul.admin-nav-list`):** Cuatro botones de navegación minimalistas (`44×44px`) con iconos SVG inline, fondo transparente en estado normal y separación horizontal equilibrada (`gap: clamp(0.6rem, 2.2vw, 1.5rem)`), reemplazando los botones grises grandes tipo píldora.
3. **Extremo derecho (`.admin-profile-btn`):** Acceso al perfil del usuario representado mediante un icono SVG minimalista con el mismo lenguaje visual que el resto de la barra superior.
4. **Salida de DEMO (`#btn-exit-demo`):** Conservada en el encabezado de la tarjeta principal (`.admin-card-header`) junto a la insignia `MODO DEMO`.

---

## 2. Iconos Utilizados

Todos los iconos se generan como elementos `<svg>` inline nativos en [`web/js/components/admin-navbar.js`](../../web/js/components/admin-navbar.js) (`viewBox="0 0 24 24"`, `width="22"`, `height="22"`, `fill="none"`, `stroke="currentColor"`, `stroke-width="1.85"`, `stroke-linecap="round"`, `stroke-linejoin="round"`), sin bibliotecas externas ni emojis:

| Sección | Identificador | Símbolo SVG Inline (`22×22px`) | Etiqueta Accesible (`aria-label`) | Tooltip (`role="tooltip"`) |
| :--- | :--- | :--- | :--- | :--- |
| **Gestión de Dispositivos** | `devices` | Monitor rectangular (`rect`) con soporte (`path`) y nodo indicador (`circle`) | `Dispositivos (Gestión de Dispositivos)` | `Dispositivos` |
| **Monitoreo de Cámaras** | `cameras` | Cámara de videovigilancia con cuerpo (`rect`), lente (`circle`) y óptica lateral (`path`) | `Cámaras (Monitoreo de Cámaras)` | `Cámaras` |
| **Gestión de Alertas** | `alerts` | Campana simétrica de notificaciones y alertas (`path`) | `Alertas (Gestión de Alertas)` | `Alertas` |
| **Gestión de Informes** | `reports` | Hoja de informe (`rect`) con encabezado y tres barras de métricas (`path`) | `Informes (Gestión de Informes)` | `Informes` |
| **Perfil de Usuario** | `profile` | Silueta geométrica de cabeza (`circle`) y hombros (`path`) | `Perfil (Perfil de Usuario)` | `Perfil` |

### Estados de Interacción
- **Normal:** Icono discreto (`--admin-nav-icon-color`), fondo transparente (`background-color: transparent`), sin bordes ni sombras pesadas.
- **Hover:** Fondo redondeado sutil (`--admin-nav-icon-hover-bg`, radio `12px`) y cambio moderado de color con transición de `170ms ease`.
- **Activo (`aria-current="page"`, `.admin-nav-btn--active`):** Contraste reforzado (`--admin-nav-icon-active-color`), fondo discreto (`--admin-nav-icon-active-bg`) e **indicador visual geométrico inferior** (`.admin-nav-indicator`, barra horizontal de `18×2.5px` en la base del botón) para que el estado activo no dependa únicamente del color.
- **Focus-visible:** Contorno accesible claro al navegar mediante teclado (`Tab` / `Shift+Tab`).

---

## 3. Tooltips y sus Transiciones

- **Ubicación:** Cada tooltip (`.admin-nav-tooltip`) emerge suavemente **debajo del icono** (`top: calc(100% + 8px)`), centrado horizontalmente con respecto al botón (y alineado al borde correspondiente en los extremos de Logo y Perfil para evitar desbordamientos).
- **Animación CSS:** Utiliza `opacity` (`0 -> 1`) y `transform` (`translateX(-50%) translateY(-4px) -> translateX(-50%) translateY(0)`) con duración de `180ms ease` (dentro del rango `150–220ms`) y `pointer-events: none`, sin desplazar ningún elemento del layout.
- **Activación con ratón y teclado:** Se muestra tanto en `:hover` como en `:focus-visible`.
- **Accesibilidad y movimiento reducido:**
  - Vinculado semánticamente mediante `aria-describedby` y `role="tooltip"`.
  - Respeta `@media (prefers-reduced-motion: reduce)` desactivando las transiciones (`transition: none !important`).
  - En pantallas táctiles (`@media (hover: none)` y móvil `< 640px`), no se depende de `hover`: en móvil se muestran etiquetas cortas visibles debajo de cada icono en la barra superior.

---

## 4. Ajustes del Área de Trabajo y Tarjetas

1. **Ampliación del ancho disponible (`--admin-max-width`):** Se amplió `--admin-max-width` en [`tokens.css`](../../web/css/tokens.css) de `1200px` a `1720px` y se optimizaron los rellenos de `.admin-viewport` (`clamp(0.65rem, 1.8vw, 1.35rem)`) y `.admin-shell` (`clamp(0.85rem, 1.8vw, 1.35rem)`). Con ello, la tabla de 5 columnas de **Gestión de Dispositivos** y las futuras cuadrículas de **Monitoreo de Cámaras** aprovechan el ancho disponible en monitores `1366×768`, `1440×900` y `1920×1080`.
2. **Proporciones de la tarjeta blanca principal (`.admin-content-card`):** Sin `min-height` arbitrario ni alturas fijas; la altura se adapta estrictamente al contenido real con `padding: clamp(1rem, 2vw, 1.5rem)` y `gap: var(--space-md)`.
3. **Compactación de la tarjeta «Sección en desarrollo» (`.admin-under-construction`):** Se redujo su ancho máximo a `600px`, margen vertical a `0.15rem auto`, relleno a `1.15rem 1.35rem` y separación interna a `0.6rem`, conservando íntegros el título, el texto explicativo y el botón `Volver a Gestión de Dispositivos`.

---

## 5. Cambios Responsive

| Rango / Resoluciones | Comportamiento de la Barra Superior y del Contenido |
| :--- | :--- |
| **Escritorio (`1920×1080`, `1440×900`, `1366×768`)** | Barra horizontal superior en una sola fila (Logo izquierdo + 4 iconos centrales + Perfil derecho). Tooltips debajo de cada icono. Tabla de 5 columnas amplia hasta `1720px`. |
| **Tableta (`1024×768`, `768×1024`)** | Conserva la barra horizontal superior sin alterar la estructura. Espaciado de columnas de la tabla ajustado a `0.4rem` sin scroll horizontal. |
| **Móvil (`390×844`, `360×800`)** | Conserva la barra de navegación en la parte superior con áreas táctiles `>= 46×46px` (`>= 44×44px`), mostrando debajo de cada icono SVG una etiqueta corta legible (`Dispositivos`, `Cámaras`, `Alertas`, `Informes`, `Perfil`). En anchos `<= 380px` (`360×800`), los 4 iconos centrales se disponen automáticamente en una fila inferior dentro de la misma cabecera superior para impedir compresión o scroll horizontal. La tabla se presenta en tarjetas verticales por dispositivo. |

---

## 6. Pruebas Ejecutadas

1. **Verificación HTTP de rutas y activos en Flask (`VIGIA_API.ingest_service`):**
   - `GET /app` con configuración por defecto (`enable_frontend_demo` omitido): entrega `200 OK` con `data-demo-enabled="false"`.
   - `GET /app` con `enable_frontend_demo=True`: entrega `200 OK` con `data-demo-enabled="true"`.
   - Descarga de `/dashboard-assets/css/tokens.css`, `/dashboard-assets/css/admin-devices.css`, `/dashboard-assets/js/components/admin-navbar.js`, `/dashboard-assets/js/views/devices-view.js` y `/assets/brand/producto_figura_dark.svg`: todos responden `200 OK` (y `404` JSON para activos inexistentes).
2. **Suite completa de pruebas unitarias del backend e ingesta:**
   - Comando: `.\.venv\Scripts\python.exe -m unittest discover -s tests/unit -p "test_*.py" -v`
   - Resultado: **186 pruebas ejecutadas, 186 aprobadas (`OK`)**.
3. **Inspección de integridad de archivos protegidos (`git status --short --branch`):**
   - `VIGIA_Dashboard/mobile/index.html`, `VIGIA_Dashboard/web/css/login.css`, `VIGIA_Dashboard/web/js/views/login-view.js` y `BD/` permanecen intactos.

---

## 7. Limitaciones Pendientes

- Las vistas operativas de `Monitoreo de Cámaras` (`#cameras`), `Visualización de Cámaras` (`#camera-viewer`), `Gestión de Alertas` (`#alerts`), `Gestión de Informes` (`#reports`) y `Perfil de Usuario` (`#profile`) continúan mostrando el aviso compacto de funcionalidad en desarrollo conforme al alcance del Sprint 02A.
- La validación visual se realizó mediante verificación estructural del DOM generado, reglas CSS, contratos de servicio en Flask (`test_client`) y pruebas unitarias automatizadas; las pruebas interactivas en navegador físico quedan listas para ejecutarse en `http://127.0.0.1:5000/app#devices` (con `VIGIA_ENABLE_FRONTEND_DEMO=1`).
