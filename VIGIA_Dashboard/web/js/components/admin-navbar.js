/**
 * VIGÍA Vision Systems — Componente Reutilizable de Barra de Navegación Superior Minimalista
 * (Sprint 02A — Refinamiento Visual VO-02A-R2)
 *
 * Distribución horizontal superior innegociable:
 * ┌──────────────────────────────────────────────────────────────┐
 * │ LOGO       Dispositivos  Cámaras  Alertas  Informes   Perfil │
 * └──────────────────────────────────────────────────────────────┘
 *
 * 1. Logotipo circular oficial de VIGÍA a la izquierda (/assets/brand/producto_figura_dark.svg).
 * 2. Navegación central con 4 botones minimalistas de icono SVG inline (22x22px, trazo uniforme):
 *    - Dispositivos (devices)
 *    - Cámaras (cameras)
 *    - Alertas (alerts)
 *    - Informes (reports)
 * 3. Acceso al Perfil a la derecha con icono SVG minimalista del mismo lenguaje visual.
 * 4. Tooltips discretos debajo de cada icono (role="tooltip", aria-describedby) en :hover y :focus-visible.
 */

export const ADMIN_NAV_ITEMS = Object.freeze([
  Object.freeze({
    id: 'devices',
    label: 'Dispositivos',
    title: 'Gestión de Dispositivos',
    tooltip: 'Dispositivos',
    implemented: true
  }),
  Object.freeze({
    id: 'cameras',
    label: 'Cámaras',
    title: 'Monitoreo de Cámaras',
    tooltip: 'Cámaras',
    implemented: true
  }),
  Object.freeze({
    id: 'alerts',
    label: 'Alertas',
    title: 'Gestión de Alertas',
    tooltip: 'Alertas',
    implemented: false
  }),
  Object.freeze({
    id: 'reports',
    label: 'Informes',
    title: 'Gestión de Informes',
    tooltip: 'Informes',
    implemented: false
  })
]);

export const ADMIN_SPECIAL_ROUTES = Object.freeze({
  profile: Object.freeze({
    id: 'profile',
    label: 'Perfil',
    title: 'Perfil de Usuario',
    tooltip: 'Perfil',
    implemented: false
  }),
  'camera-viewer': Object.freeze({
    id: 'camera-viewer',
    label: 'Visualización de Cámaras',
    title: 'Visualización de Cámaras',
    tooltip: 'Visualización de Cámaras',
    implemented: false
  })
});

const SVG_NS = 'http://www.w3.org/2000/svg';

/**
 * Definición de trazos SVG minimalistas para los 5 elementos de navegación.
 * Todos utilizan viewBox="0 0 24 24", fill="none", stroke="currentColor" y stroke-width="1.85".
 */
const NAV_ICON_PATHS = Object.freeze({
  // Monitor y nodo de dispositivo conectado
  devices: [
    { tag: 'rect', attrs: { x: '2.5', y: '3.5', width: '19', height: '13', rx: '2' } },
    { tag: 'path', attrs: { d: 'M8 20.5h8' } },
    { tag: 'path', attrs: { d: 'M12 16.5v4' } },
    { tag: 'circle', attrs: { cx: '18', cy: '7', r: '1' } }
  ],
  // Cámara de videovigilancia (CCTV / video)
  cameras: [
    { tag: 'rect', attrs: { x: '2.5', y: '6.5', width: '13.5', height: '11', rx: '2' } },
    { tag: 'path', attrs: { d: 'M16 10.25l5.5-3v9.5l-5.5-3' } },
    { tag: 'circle', attrs: { cx: '9.25', cy: '12', r: '2.25' } }
  ],
  // Campana de alertas operativas
  alerts: [
    { tag: 'path', attrs: { d: 'M6 9.5a6 6 0 0 1 12 0c0 5 2 6.5 2 6.5H4s2-1.5 2-6.5' } },
    { tag: 'path', attrs: { d: 'M10 19a2 2 0 0 0 4 0' } }
  ],
  // Documento con barras de métricas e informes
  reports: [
    { tag: 'rect', attrs: { x: '4', y: '3', width: '16', height: '18', rx: '2' } },
    { tag: 'path', attrs: { d: 'M8.5 16v-3' } },
    { tag: 'path', attrs: { d: 'M12 16v-6' } },
    { tag: 'path', attrs: { d: 'M15.5 16v-4.5' } },
    { tag: 'path', attrs: { d: 'M8 7.5h8' } }
  ],
  // Silueta de usuario para Perfil
  profile: [
    { tag: 'circle', attrs: { cx: '12', cy: '8', r: '3.75' } },
    { tag: 'path', attrs: { d: 'M5 19.5a7 7 0 0 1 14 0' } }
  ],
  // Icono minimalista para Cerrar Sesión (Logout)
  logout: [
    { tag: 'path', attrs: { d: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4' } },
    { tag: 'polyline', attrs: { points: '16 17 21 12 16 7' } },
    { tag: 'line', attrs: { x1: '21', y1: '12', x2: '9', y2: '12' } }
  ]
});

/**
 * Construye un elemento <svg> inline minimalista para un ítem de navegación.
 * @param {string} iconId
 * @returns {SVGElement}
 */
function createNavSvgIcon(iconId) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', '22');
  svg.setAttribute('height', '22');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.85');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  svg.classList.add('admin-nav-icon');

  const primitives = NAV_ICON_PATHS[iconId] || NAV_ICON_PATHS.devices;
  primitives.forEach((primitive) => {
    const el = document.createElementNS(SVG_NS, primitive.tag);
    Object.entries(primitive.attrs).forEach(([attr, val]) => {
      el.setAttribute(attr, val);
    });
    svg.appendChild(el);
  });

  return svg;
}

/**
 * Crea un botón de navegación minimalista con icono SVG, indicador de estado activo,
 * etiqueta móvil compacta y tooltip discreto debajo del icono.
 *
 * @param {Object} item
 * @param {string} item.id
 * @param {string} item.label
 * @param {string} item.title
 * @param {string} [item.tooltip]
 * @param {boolean} isActive
 * @param {(sectionId: string) => void} onNavigate
 * @param {string} [extraClass]
 * @returns {HTMLButtonElement}
 */
function createNavIconButton(item, isActive, onNavigate, extraClass = '') {
  const tooltipId = `admin-nav-tooltip-${item.id}`;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = `admin-nav-btn${extraClass ? ` ${extraClass}` : ''}`;
  btn.dataset.navId = item.id;
  btn.setAttribute('aria-label', `${item.label} (${item.title || item.label})`);
  btn.setAttribute('aria-describedby', tooltipId);

  if (isActive) {
    btn.classList.add('admin-nav-btn--active');
    if (extraClass === 'admin-profile-btn') {
      btn.classList.add('admin-profile-btn--active');
    }
    btn.setAttribute('aria-current', 'page');
  }

  // Icono SVG inline minimalista
  const svgIcon = createNavSvgIcon(item.id);

  // Etiqueta corta visible en móvil (< 640px) para no depender exclusivamente de hover
  const mobileLabel = document.createElement('span');
  mobileLabel.className = 'admin-nav-mobile-label';
  mobileLabel.setAttribute('aria-hidden', 'true');
  mobileLabel.textContent = item.label;

  // Indicador visual discreto inferior para la sección activa (no depende únicamente del color)
  const indicator = document.createElement('span');
  indicator.className = 'admin-nav-indicator';
  indicator.setAttribute('aria-hidden', 'true');

  // Tooltip discreto debajo del icono en :hover y :focus-visible
  const tooltip = document.createElement('span');
  tooltip.id = tooltipId;
  tooltip.setAttribute('role', 'tooltip');
  tooltip.className = 'admin-nav-tooltip';
  tooltip.textContent = item.tooltip || item.label;

  btn.appendChild(svgIcon);
  btn.appendChild(mobileLabel);
  btn.appendChild(indicator);
  btn.appendChild(tooltip);

  btn.addEventListener('click', () => {
    if (typeof onNavigate === 'function') {
      onNavigate(item.id);
    }
  });

  return btn;
}

/**
 * Construye el elemento DOM <header class="admin-navbar"> horizontal en la parte superior.
 *
 * @param {Object} options
 * @param {string} options.activeSectionId - Identificador activo ('devices', 'cameras', 'alerts', 'reports', 'profile')
 * @param {Object} [options.currentUser] - Datos del usuario en memoria ({ username, nombre_completo, rol })
 * @param {(sectionId: string) => void} options.onNavigate - Callback al seleccionar una sección
 * @param {() => void} [options.onLogout] - Callback de cierre de sesión
 * @returns {HTMLElement}
 */
export function renderAdminNavbar({ activeSectionId = 'devices', currentUser = null, onNavigate, onLogout } = {}) {
  const header = document.createElement('header');
  header.className = 'admin-navbar';
  header.setAttribute('aria-label', 'Navegación principal del panel de administración');

  // 1. Logotipo circular oficial de VIGÍA a la izquierda
  const brandTooltipId = 'admin-nav-tooltip-brand';
  const brandLink = document.createElement('a');
  brandLink.href = '#devices';
  brandLink.className = 'admin-nav-brand';
  brandLink.setAttribute('aria-label', 'VIGÍA Vision Systems — Ir al inicio');
  brandLink.setAttribute('aria-describedby', brandTooltipId);
  brandLink.addEventListener('click', (event) => {
    event.preventDefault();
    if (typeof onNavigate === 'function') {
      onNavigate(currentUser?.rol === 'GUARDIA' ? 'cameras' : 'devices');
    }
  });

  const brandImg = document.createElement('img');
  brandImg.src = '/assets/brand/producto_figura_dark.svg';
  brandImg.alt = 'Logotipo oficial de VIGÍA';
  brandImg.className = 'admin-nav-brand-img';
  brandImg.width = 32;
  brandImg.height = 32;

  const brandTooltip = document.createElement('span');
  brandTooltip.id = brandTooltipId;
  brandTooltip.setAttribute('role', 'tooltip');
  brandTooltip.className = 'admin-nav-tooltip';
  brandTooltip.textContent = 'Inicio';

  brandLink.appendChild(brandImg);
  brandLink.appendChild(brandTooltip);

  // 2. Navegación central con cuatro secciones (Dispositivos, Cámaras, Alertas, Informes)
  const nav = document.createElement('nav');
  nav.className = 'admin-nav-primary';
  nav.setAttribute('aria-label', 'Secciones del administrador');

  const ul = document.createElement('ul');
  ul.className = 'admin-nav-list';

  ADMIN_NAV_ITEMS.forEach((item) => {
    const li = document.createElement('li');
    li.className = 'admin-nav-item';

    const isActive = item.id === activeSectionId;
    const btn = createNavIconButton(item, isActive, onNavigate);

    li.appendChild(btn);
    ul.appendChild(li);
  });

  nav.appendChild(ul);

  // 3. Extremo derecho: Contenedor con información de usuario, Perfil y Logout
  const userActions = document.createElement('div');
  userActions.className = 'admin-nav-user-actions';

  if (currentUser) {
    const userChip = document.createElement('div');
    userChip.className = 'admin-nav-user-chip';
    userChip.setAttribute('aria-label', `Usuario: ${currentUser.nombre_completo || currentUser.username}`);

    const userName = document.createElement('span');
    userName.className = 'admin-nav-username';
    userName.textContent = currentUser.nombre_completo || currentUser.username;

    const roleBadge = document.createElement('span');
    const rolClean = String(currentUser.rol || 'USUARIO').toUpperCase();
    roleBadge.className = `admin-nav-role-badge admin-nav-role-badge--${rolClean.toLowerCase()}`;
    roleBadge.textContent = rolClean;

    userChip.appendChild(userName);
    userChip.appendChild(roleBadge);
    userActions.appendChild(userChip);
  }

  // Acceso al Perfil
  const profileItem = ADMIN_SPECIAL_ROUTES.profile;
  const profileBtn = createNavIconButton(
    profileItem,
    activeSectionId === 'profile',
    onNavigate,
    'admin-profile-btn'
  );
  userActions.appendChild(profileBtn);

  // Botón de Cerrar Sesión en la barra superior (Fase 3B)
  const logoutBtn = document.createElement('button');
  logoutBtn.type = 'button';
  logoutBtn.className = 'admin-nav-btn admin-logout-btn';
  logoutBtn.id = 'admin-logout-btn';
  logoutBtn.setAttribute('aria-label', 'Cerrar Sesión');
  const logoutTooltipId = 'admin-nav-tooltip-logout';
  logoutBtn.setAttribute('aria-describedby', logoutTooltipId);

  const logoutSvg = createNavSvgIcon('logout');

  const logoutMobileLabel = document.createElement('span');
  logoutMobileLabel.className = 'admin-nav-mobile-label';
  logoutMobileLabel.textContent = 'Salir';

  const logoutTooltip = document.createElement('span');
  logoutTooltip.id = logoutTooltipId;
  logoutTooltip.setAttribute('role', 'tooltip');
  logoutTooltip.className = 'admin-nav-tooltip';
  logoutTooltip.textContent = 'Cerrar Sesión';

  logoutBtn.appendChild(logoutSvg);
  logoutBtn.appendChild(logoutMobileLabel);
  logoutBtn.appendChild(logoutTooltip);

  logoutBtn.addEventListener('click', (event) => {
    event.preventDefault();
    if (typeof onLogout === 'function') {
      onLogout();
    }
  });

  userActions.appendChild(logoutBtn);

  header.appendChild(brandLink);
  header.appendChild(nav);
  header.appendChild(userActions);

  return header;
}
