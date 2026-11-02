# Sistema de Diseño del Frontend — `VIGIA_Dashboard`

**Proyecto:** VIGÍA Vision Systems  
**Módulo:** `VIGIA_Dashboard`  
**Archivo de tokens:** [`web/css/tokens.css`](../web/css/tokens.css)  
**Versión:** 1.1 (Sprint 02A + Refinamiento Visual `VO-02A-R2`)

---

## 1. Propósito

Este documento define las reglas visuales, variables CSS, esquemas de color en **Modo Claro** y **Modo Oscuro**, tipografía, radios de borde, espaciados, iconografía SVG minimalista, tooltips discretos y patrones de componentes reutilizables de `VIGIA_Dashboard`.

Todos los valores de diseño se concentran en [`web/css/tokens.css`](../web/css/tokens.css) para evitar dispersar valores literales en las hojas de estilo de cada vista.

---

## 2. Paleta de Colores y Temas (`Modo Claro` y `Modo Oscuro`)

El sistema gestiona los temas mediante variables CSS bajo `:root, [data-theme="light"]` para el **Modo Claro** (activo por omisión) y `[data-theme="dark"]` para el **Modo Oscuro**.

### 2.1. Modo Claro (`[data-theme="light"]`)

| Elemento | Referencia de Diseño | Variable CSS (`tokens.css`) | Valor |
| :--- | :--- | :--- | :---: |
| **Fondo general** | Gris muy claro / blanco humo | `--admin-page-bg` | `#F4F4F6` |
| **Tarjeta principal** | Gris claro | `--admin-shell-bg` | `#DFDFE2` |
| **Panel interno** | Blanco sólido | `--admin-panel-bg` | `#FFFFFF` |
| **Botones de acción** | Gris medio | `--admin-btn-bg` | `#BDBDC2` |
| **Botón activo de acción** | Gris medio acentuado | `--admin-btn-bg-active` | `#9898A0` |
| **Icono de navegación superior (normal)** | Gris oscuro discreto (fondo transparente) | `--admin-nav-icon-color` | `#3F3F46` |
| **Icono de navegación superior (hover)** | Fondo sutil redondeado | `--admin-nav-icon-hover-bg` | `rgba(0, 0, 0, 0.06)` |
| **Icono de navegación superior (activo)** | Fondo discreto + indicador inferior | `--admin-nav-icon-active-bg` | `rgba(0, 0, 0, 0.08)` |
| **Indicador de sección activa** | Barra inferior oscura (`18×2.5px`) | `--admin-nav-active-indicator` | `#18181B` |
| **Tooltip emergente (fondo)** | Gris carbón oscuro | `--admin-tooltip-bg` | `#18181B` |
| **Tooltip emergente (texto)** | Blanco legible | `--admin-tooltip-text` | `#FAFAFA` |
| **Texto principal** | Negro | `--admin-text-primary` | `#000000` |
| **Texto secundario** | Gris oscuro | `--admin-text-secondary` | `#3F3F46` |
| **Inputs** | Gris muy claro | `--admin-input-bg` | `#F2F2F4` |
| **Borde de inputs** | Gris neutro | `--admin-input-border` | `#C4C4CC` |
| **Bloques de datos (columnas)** | Gris sólido claro | `--admin-data-block-bg` | `#D4D4D8` |
| **Encabezados de columna** | Gris sólido medio | `--admin-data-header-bg` | `#C4C4CA` |
| **Celdas de registro** | Gris claro uniforme | `--admin-data-row-bg` | `#E4E4E7` |
| **Espacios de cámara** | Negro | `--admin-camera-slot-bg` | `#000000` |

### 2.2. Modo Oscuro (`[data-theme="dark"]`)

El modo oscuro conserva un contraste legible evitando el uso de negro puro para todos los fondos, reservando `#000000` exclusivamente para los espacios de reproducción de cámara:

| Elemento | Variable CSS (`tokens.css`) | Valor Oficial |
| :--- | :--- | :---: |
| **Fondo general** | `--admin-page-bg` | `#121212` |
| **Tarjeta principal** | `--admin-shell-bg` | `#1E1E1E` |
| **Panel interno** | `--admin-panel-bg` | `#2C2C2C` |
| **Superficies interactivas / botones** | `--admin-btn-bg` | `#424242` |
| **Botón activo** | `--admin-btn-bg-active` | `#616161` |
| **Icono de navegación superior (normal)** | `--admin-nav-icon-color` | `#A0A0A0` |
| **Icono de navegación superior (hover)** | `--admin-nav-icon-hover-bg` | `rgba(255, 255, 255, 0.08)` |
| **Icono de navegación superior (activo)** | `--admin-nav-icon-active-bg` | `#424242` |
| **Indicador de sección activa** | `--admin-nav-active-indicator` | `#E0E0E0` |
| **Tooltip emergente (fondo)** | `--admin-tooltip-bg` | `#2C2C2C` |
| **Tooltip emergente (texto)** | `--admin-tooltip-text` | `#E0E0E0` |
| **Texto principal** | `--admin-text-primary` | `#E0E0E0` |
| **Texto secundario** | `--admin-text-secondary` | `#A0A0A0` |
| **Inputs** | `--admin-input-bg` | `#1A1A1A` |
| **Borde de inputs** | `--admin-input-border` | `#444444` |
| **Bloques de datos (columnas)** | `--admin-data-block-bg` | `#242424` |
| **Encabezados de columna** | `--admin-data-header-bg` | `#383838` |
| **Celdas de registro** | `--admin-data-row-bg` | `#303030` |
| **Espacios de cámara** | `--admin-camera-slot-bg` | `#000000` |

### 2.3. Colores Semánticos de Estado de Dispositivos

Para distinguir visualmente la condición operativa de cada equipo en la columna **Estado**:

| Estado Operativo | Fondo (Claro / Oscuro) | Texto (Claro / Oscuro) | Indicador Circular (`dot`) |
| :--- | :---: | :---: | :---: |
| **Conectado** (`CONECTADO`) | `#DCFCE7` / `#143321` | `#14532D` / `#BBF7D0` | `#16A34A` / `#4ADE80` |
| **Desconectado** (`DESCONECTADO`) | `#FEE2E2` / `#3B1818` | `#7F1D1D` / `#FECACA` | `#DC2626` / `#F87171` |
| **En mantenimiento** (`EN_MANTENIMIENTO`) | `#FEF3C7` / `#3B2A14` | `#78350F` / `#FDE68A` | `#D97706` / `#FBBF24` |

---

## 3. Tipografía

- **Familia tipográfica (`--font-family-sans`):** `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`.
- **Jerarquía de tamaños:**
  - `--font-size-title`: `clamp(1.375rem, 2.5vw, 1.625rem)` — Títulos principales (`Inicio de Sesión`, `Gestión de Dispositivos`), centrados y en negrita (`700`).
  - `--font-size-subtitle`: `clamp(1.125rem, 2vw, 1.35rem)` — Subtítulos de paneles internos.
  - `--font-size-body`: `1rem` (`16px`) — Texto base y botones principales.
  - `--font-size-small`: `0.875rem` (`14px`) — Celdas de tabla, descripciones y pie de página.
  - `--font-size-xs`: `0.8125rem` (`13px`) — Etiquetas de estado (badges) y metadatos secundarios.

---

## 4. Radios de Borde y Contenedores

| Elemento | Variable CSS | Valor | Aplicación |
| :--- | :--- | :---: | :--- |
| **Tarjeta principal administrativa** | `--admin-shell-radius` | `20px` | Contenedor gris claro `.admin-shell` (`max-width: 1720px`). |
| **Panel interno blanco** | `--admin-panel-radius` | `16px` | Tarjeta blanca `.admin-content-card`. |
| **Botones de icono en barra superior** | `--admin-nav-btn-radius` | `12px` | Botones compactos (`44px × 44px`) en `.admin-navbar`. |
| **Columnas de la cuadrícula** | `--admin-column-radius` | `12px` | Extremos superior e inferior de cada bloque vertical de columna en `.devices-table`. |
| **Celdas de datos** | `--admin-cell-radius` | `8px` | Contenedores internos `.device-cell-box` dentro de cada columna. |
| **Botones de acción y entradas píldora** | `--admin-pill-radius` | `9999px` | Botones inferiores (`Visualización de Cámaras`, `Agregar Dispositivos`) y campos de entrada. |
| **Logotipo circular izquierdo** | `border-radius: 50%` | `44px × 44px` | Logotipo oficial izquierdo en la barra superior (`.admin-nav-brand`). |

---

## 5. Espaciados

Definidos mediante escala progresiva en `tokens.css`:
- `--space-2xs`: `0.25rem` (`4px`)
- `--space-xs`: `0.5rem` (`8px`)
- `--space-sm`: `0.75rem` (`12px`)
- `--space-md`: `1rem` (`16px`)
- `--space-lg`: `1.5rem` (`24px`)
- `--space-xl`: `2rem` (`32px`)

---

## 6. Componentes Visuales Estandarizados

### 6.1. Barra de Navegación Horizontal Superior Minimalista (`VO-02A-R2`)
- **Ubicación y distribución:** Permanece en la parte superior de `.admin-shell` con el logotipo oficial circular a la izquierda, los 4 accesos centrales (`Dispositivos`, `Cámaras`, `Alertas`, `Informes`) en el centro y el acceso a `Perfil` en el extremo derecho.
- **Iconos SVG inline minimalistas:**
  - Construidos nativamente en [`admin-navbar.js`](../web/js/components/admin-navbar.js) sin librerías externas ni emojis.
  - Dimensiones de `22×22px` (`20×20px` en móvil), `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`, `stroke-width="1.85"`, `stroke-linecap="round"` y `stroke-linejoin="round"`.
- **Estados visuales de cada botón (`.admin-nav-btn`, `.admin-profile-btn`):**
  - **Normal:** Fondo transparente (`background-color: transparent`), icono discreto (`--admin-nav-icon-color`), área interactiva de `44×44px`.
  - **Hover:** Fondo sutil redondeado (`--admin-nav-icon-hover-bg`) y transición fluida de color (`170ms ease`).
  - **Activo (`aria-current="page"`, `.admin-nav-btn--active`):** Fondo discreto (`--admin-nav-icon-active-bg`), icono de alto contraste (`--admin-nav-icon-active-color`) e **indicador visual inferior** (`.admin-nav-indicator` de `18×2.5px`) para que el estado activo no dependa exclusivamente del color.
  - **Focus-visible:** Contorno accesible al navegar con teclado (`--focus-ring-color`).

### 6.2. Tooltips Discretos debajo de cada Icono (`.admin-nav-tooltip`)
- Al pasar el cursor (`:hover`) o enfocar con teclado (`:focus-visible`), cada icono de la barra superior muestra debajo (`top: calc(100% + 8px)`) una etiqueta discreta (`role="tooltip"`, vinculada mediante `aria-describedby`) con el nombre de su sección (`Dispositivos`, `Cámaras`, `Alertas`, `Informes`, `Perfil`).
- La transición utiliza `opacity` y `transform` (`180ms ease`) sin desplazar otros elementos del layout, respetando `@media (prefers-reduced-motion: reduce)`.

### 6.3. Cuadrícula / Tabla de Cinco Columnas (`.devices-table`) y Tarjetas Proporcionadas
- Utiliza `border-collapse: separate; border-spacing: 0.65rem 0; table-layout: fixed;` para que cada una de las 5 columnas (`Nombre del Dispositivo`, `Tipo`, `Estado`, `Última Actividad`, `Acciones`) conforme un **área rectangular vertical de fondo gris sólido** (`--admin-data-block-bg`) coronada por su encabezado (`--admin-data-header-bg`).
- La tarjeta blanca `.admin-content-card` ajusta su altura al contenido real sin alturas mínimas arbitrarias.
- El bloque `.admin-under-construction` ("Sección en desarrollo") emplea dimensiones compactas (`max-width: 600px; padding: 1.15rem 1.35rem`) ajustadas a su contenido real.

---

## 7. Criterios Responsive

1. **Escritorio (`>= 1024px`):**
   - Contenedor `.admin-shell` expandido hasta `1720px` (`--admin-max-width`), aprovechando monitores `1366×768`, `1440×900` y `1920×1080`.
   - Barra de navegación horizontal en la parte superior (Logo circular izquierdo + 4 iconos centrales + icono de Perfil derecho) con tooltips emergentes debajo de cada icono.
   - Cuadrícula de 5 columnas verticales con separación de `0.65rem`.
2. **Tableta (`640px – 1023px`):**
   - Conserva la barra horizontal superior sin cambios estructurales y reduce proporcionalmente el espaciado entre las 5 columnas (`0.4rem`) sin desbordamiento horizontal.
3. **Móvil (`< 640px`):**
   - Conserva la barra de navegación en la parte superior mostrando debajo de cada icono SVG una etiqueta corta legible (`Dispositivos`, `Cámaras`, `Alertas`, `Informes`, `Perfil`) con áreas táctiles `>= 46×46px` (superiores al mínimo de `44×44px`). En pantallas muy estrechas (`<= 380px`), los 4 iconos centrales se distribuyen limpiamente en una segunda fila dentro de la misma barra superior para evitar cualquier compresión o desbordamiento horizontal.
   - La tabla de 5 columnas se transforma automáticamente en **tarjetas verticales por dispositivo**, inyectando el nombre de cada columna mediante `content: attr(data-label)` en `.device-cell-box::before`.
   - Los botones principales inferiores (`Visualización de Cámaras` y `Agregar Dispositivos`) ocupan el `100%` del ancho de la tarjeta.
