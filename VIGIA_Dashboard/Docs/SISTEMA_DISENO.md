# Sistema de Diseño del Frontend — `VIGIA_Dashboard`

**Proyecto:** VIGÍA Vision Systems  
**Módulo:** `VIGIA_Dashboard`  
**Archivo de tokens:** [`web/css/tokens.css`](../web/css/tokens.css)  
**Versión:** 1.0 (Sprint 02A)

---

## 1. Propósito

Este documento define las reglas visuales, variables CSS, esquemas de color en **Modo Claro** y **Modo Oscuro**, tipografía, radios de borde, espaciados y patrones de componentes reutilizables de `VIGIA_Dashboard`.

Todos los valores de diseño se concentran en [`web/css/tokens.css`](../web/css/tokens.css) para evitar dispersar valores literales en las hojas de estilo de cada vista.

---

## 2. Paleta de Colores y Temas (`Modo Claro` y `Modo Oscuro`)

El sistema gestiona los temas mediante variables CSS bajo `:root, [data-theme="light"]` para el **Modo Claro** (activo por omisión) y `[data-theme="dark"]` para el **Modo Oscuro**.

### 2.1. Modo Claro (`[data-theme="light"]`)

| Elemento | Referencia de Diseño | Variable CSS (`tokens.css`) | Valor Hexadecimal |
| :--- | :--- | :--- | :---: |
| **Fondo general** | Gris muy claro / blanco humo | `--admin-page-bg` | `#F4F4F6` |
| **Tarjeta principal** | Gris claro | `--admin-shell-bg` | `#DFDFE2` |
| **Panel interno** | Blanco sólido | `--admin-panel-bg` | `#FFFFFF` |
| **Botones** | Gris medio | `--admin-btn-bg` | `#BDBDC2` |
| **Botón activo** | Gris medio acentuado | `--admin-btn-bg-active` | `#9898A0` |
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

| Elemento | Variable CSS (`tokens.css`) | Valor Hexadecimal Oficial |
| :--- | :--- | :---: |
| **Fondo general** | `--admin-page-bg` | `#121212` |
| **Tarjeta principal** | `--admin-shell-bg` | `#1E1E1E` |
| **Panel interno** | `--admin-panel-bg` | `#2C2C2C` |
| **Botones** | `--admin-btn-bg` | `#424242` |
| **Botón activo** | `--admin-btn-bg-active` | `#616161` |
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
  - `--font-size-small`: `0.875rem` (`14px`) — Celdas de tabla, botones de navegación y pie de página.
  - `--font-size-xs`: `0.8125rem` (`13px`) — Etiquetas de estado (badges) y metadatos secundarios.

---

## 4. Radios de Borde y Contenedores

| Elemento | Variable CSS | Valor | Aplicación |
| :--- | :--- | :---: | :--- |
| **Tarjeta principal administrativa** | `--admin-shell-radius` | `20px` | Contenedor gris claro `.admin-shell` (`max-width: 1200px`). |
| **Panel interno blanco** | `--admin-panel-radius` | `16px` | Tarjeta blanca `.admin-content-card`. |
| **Columnas de la cuadrícula** | `--admin-column-radius` | `12px` | Extremos superior e inferior de cada bloque vertical de columna en `.devices-table`. |
| **Celdas de datos** | `--admin-cell-radius` | `8px` | Contenedores internos `.device-cell-box` dentro de cada columna. |
| **Botones y entradas píldora** | `--admin-pill-radius` | `9999px` | Botones de navegación, botones de acción principales y campos de entrada. |
| **Elementos circulares** | `border-radius: 50%` | `46px × 46px` | Logotipo izquierdo (`.admin-nav-brand`) y botón derecho de Perfil (`.admin-profile-btn`). |

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

### 6.1. Botones
- **Botones de navegación superior (`.admin-nav-btn`):** Forma de píldora (`9999px`), fondo gris medio (`--admin-btn-bg`), texto centrado, altura mínima de `40px`. El botón de la sección activa recibe `--admin-btn-bg-active`, borde de `2px solid var(--admin-text-primary)` y atributo `aria-current="page"`.
- **Botones de acción principales (`.admin-action-pill-btn`):** Ubicados bajo la tarjeta blanca (`Visualización de Cámaras` y `Agregar Dispositivos`), forma de píldora, ancho mínimo de `210px`, altura mínima de `44px` y tipografía en negrita.

### 6.2. Cuadrícula / Tabla de Cinco Columnas (`.devices-table`)
- Utiliza `border-collapse: separate; border-spacing: 0.65rem 0; table-layout: fixed;` para que cada una de las 5 columnas (`Nombre del Dispositivo`, `Tipo`, `Estado`, `Última Actividad`, `Acciones`) conforme un **área rectangular vertical de fondo gris sólido** (`--admin-data-block-bg`) coronada por su encabezado (`--admin-data-header-bg`).
- Dentro de cada columna, los registros se alojan en bloques `.device-cell-box` con altura uniforme (`min-height: 44px`) y ajuste seguro de palabras largas (`overflow-wrap: anywhere`).

---

## 7. Criterios Responsive

1. **Escritorio (`>= 1024px`):**
   - Contenedor `.admin-shell` centrado hasta `1200px`.
   - Barra de navegación en una sola fila horizontal (Logo circular izquierdo + 4 píldoras centradas + Perfil circular derecho).
   - Cuadrícula de 5 columnas verticales con separación de `0.65rem`.
2. **Tableta (`640px – 1023px`):**
   - Reducción proporcional de rellenos y separación entre columnas (`0.4rem`) preservando la vista tabular de 5 columnas sin desbordamiento horizontal.
3. **Móvil (`< 640px`):**
   - Los 4 botones de navegación se organizan en una cuadrícula de 2×2 debajo del logotipo y del botón de Perfil, manteniendo áreas táctiles amplias.
   - La tabla de 5 columnas se transforma automáticamente en **tarjetas verticales por dispositivo**, inyectando el nombre de cada columna mediante `content: attr(data-label)` en `.device-cell-box::before` para impedir que las 5 columnas se compriman o pierdan legibilidad.
   - Los botones principales inferiores (`Visualización de Cámaras` y `Agregar Dispositivos`) ocupan el `100%` del ancho de la tarjeta.

