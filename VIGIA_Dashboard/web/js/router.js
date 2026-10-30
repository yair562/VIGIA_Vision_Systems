/**
 * VIGÍA Vision Systems — Enrutador Ligero de Vistas y Previsualización DEMO (Sprint 02A — VO-02A-R1)
 *
 * Rutas soportadas mediante hash URL:
 * - #login          : Pantalla de Inicio de Sesión (Sprint 01, predeterminada)
 * - #devices        : Gestión de Dispositivos (Administrador — Sprint 02A, Modo DEMO)
 * - #cameras        : Monitoreo de Cámaras (Ruta preparada — en desarrollo)
 * - #alerts         : Gestión de Alertas (Ruta preparada — en desarrollo)
 * - #reports        : Gestión de Informes (Ruta preparada — en desarrollo)
 * - #profile        : Perfil (Ruta preparada — en desarrollo)
 * - #camera-viewer  : Visualización de Cámaras (Ruta independiente preparada — en desarrollo)
 *
 * CONTROL DE SEGURIDAD (OBS-SEG-01):
 * - El modo DEMO está DESHABILITADO por defecto (data-demo-enabled="false").
 * - Ni el hash #devices ni el parámetro ?demo=admin habilitan el modo DEMO por sí mismos.
 * - Solo cuando el entorno de desarrollo del servidor establece explícitamente
 *   VIGIA_ENABLE_FRONTEND_DEMO=1 (inyectando data-demo-enabled="true" en <html>) se
 *   permite acceder a las rutas de previsualización administrativa sin sesión.
 */

const ADMIN_ROUTES = new Set([
  'devices',
  'cameras',
  'alerts',
  'reports',
  'profile',
  'camera-viewer'
]);

/**
 * Comprueba si el modo de previsualización DEMO fue habilitado explícitamente
 * por la bandera de entorno del servidor en el documento raíz.
 * @param {Document} doc
 * @returns {boolean}
 */
export function isFrontendDemoEnabled(doc = document) {
  const rootEl = doc?.documentElement;
  if (!rootEl) return false;
  return rootEl.getAttribute('data-demo-enabled') === 'true';
}

/**
 * Extrae el identificador de ruta solicitada y verifica si el modo DEMO está autorizado.
 * @param {Object} options
 * @param {boolean} options.demoEnabled - Estado de habilitación del modo DEMO
 * @returns {{ routeId: string, blockedDemoAttempt: boolean, requestedRoute: string | null }}
 */
export function resolveRouteState({ demoEnabled = isFrontendDemoEnabled() } = {}) {
  const rawHash = (window.location.hash || '').replace(/^#\/?/, '').trim().toLowerCase();
  const params = new URLSearchParams(window.location.search);
  const queryWantsDemo = params.get('demo') === 'admin' || params.get('view') === 'devices';

  const requestedAdminRoute = ADMIN_ROUTES.has(rawHash)
    ? rawHash
    : queryWantsDemo
      ? 'devices'
      : null;

  if (requestedAdminRoute) {
    if (!demoEnabled) {
      return {
        routeId: 'login',
        blockedDemoAttempt: true,
        requestedRoute: requestedAdminRoute
      };
    }
    return {
      routeId: requestedAdminRoute,
      blockedDemoAttempt: false,
      requestedRoute: requestedAdminRoute
    };
  }

  return {
    routeId: 'login',
    blockedDemoAttempt: false,
    requestedRoute: null
  };
}

/**
 * Mantiene compatibilidad devolviendo el identificador de ruta efectivo ('login' si DEMO está deshabilitado).
 * @returns {string}
 */
export function resolveCurrentRoute() {
  return resolveRouteState().routeId;
}

/**
 * Navega programáticamente hacia una ruta actualizando el hash.
 * @param {string} routeId
 */
export function navigateToRoute(routeId) {
  const target = routeId || 'login';
  const expectedHash = `#${target}`;
  if (window.location.hash !== expectedHash) {
    window.location.hash = expectedHash;
  } else {
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  }
}

/**
 * Inicializa el observador de rutas y notifica cada cambio.
 * @param {(routeId: string, routeState: { routeId: string, blockedDemoAttempt: boolean, requestedRoute: string | null }) => void} onRouteChange
 */
export function initRouter(onRouteChange) {
  const handleRoute = () => {
    const state = resolveRouteState();
    if (typeof onRouteChange === 'function') {
      onRouteChange(state.routeId, state);
    }
  };

  window.addEventListener('hashchange', handleRoute);
  handleRoute();

  return {
    navigateTo: navigateToRoute,
    getCurrentRoute: resolveCurrentRoute,
    isDemoEnabled: isFrontendDemoEnabled
  };
}
