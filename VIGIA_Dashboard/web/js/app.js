/**
 * VIGÍA Vision Systems — Punto de Entrada de la Aplicación Web (Fase 3B)
 *
 * Responsabilidades:
 * - Orquestar la sesión y autenticación real mediante cookie HttpOnly 'vigia_session'.
 * - Restaurar la sesión al inicio consultando GET /api/v1/auth/me sin inventar sesiones
 *   locales y sin procesar tokens en el cliente.
 * - Diferenciar deterministamente caídas de red o errores de servidor (5xx) de sesiones
 *   inválidas (401), presentando un estado recuperable con botón de reintento.
 * - Conectar el formulario de inicio de sesión a POST /api/v1/auth/login.
 * - Conectar el control de logout de la barra superior a POST /api/v1/auth/logout.
 * - Enrutar entre la vista de Inicio de Sesión, la vista de Cámaras reales conectadas
 *   a PostgreSQL y las pantallas administrativas autorizadas según el rol (ADMINISTRADOR / GUARDIA).
 * - Aislar estrictamente el modo DEMO de la autenticación y las cámaras reales.
 */

import { initLoginView } from './views/login-view.js';
import { renderAdminDevicesView } from './views/devices-view.js';
import { renderCamerasView } from './views/cameras-view.js';
import { createDeviceService } from './services/device-service.js';
import { createApiService, NetworkError, ServerError } from './services/api-service.js';
import { initRouter, navigateToRoute } from './router.js';

const DEMO_DISABLED_NOTICE =
  'El modo de previsualización DEMO está deshabilitado por defecto. Inicia sesión para acceder al sistema institucional.';

export function bootstrapApp() {
  const loginRoot = document.getElementById('app-root');
  const adminRoot = document.getElementById('admin-root');
  const feedbackEl = document.getElementById('login-feedback');

  const apiService = createApiService();
  let deviceService = createDeviceService({ apiService });

  // Estado volátil en memoria (cero localStorage / sessionStorage)
  let currentUser = null;
  let sessionCheckResolved = false;
  let routerHandle = null;

  // Configurar tema desde parámetro opcional (?theme=dark | light) para pruebas de diseño
  const searchParams = new URLSearchParams(window.location.search);
  const requestedTheme = searchParams.get('theme');
  if (requestedTheme === 'dark' || requestedTheme === 'light') {
    document.documentElement.setAttribute('data-theme', requestedTheme);
  }

  // 1. Inicializar el formulario de Inicio de Sesión
  const loginController = initLoginView(document, {
    apiService,
    onLoginSuccess: (user) => {
      currentUser = user;
      sessionCheckResolved = true;

      // Destino por defecto según el rol: Guardia -> cameras, Administrador -> cameras / devices
      const defaultRoute = user.rol === 'GUARDIA' ? 'cameras' : 'cameras';
      if (routerHandle) {
        routerHandle.notifyAuthChanged();
      }
      navigateToRoute(defaultRoute);
    }
  });

  // Función para cerrar sesión en servidor y cliente
  async function handleLogout() {
    try {
      await apiService.logout();
    } finally {
      currentUser = null;
      deviceService = createDeviceService({ apiService });
      if (adminRoot) {
        adminRoot.hidden = true;
        adminRoot.innerHTML = '';
      }
      if (loginRoot) {
        loginRoot.hidden = false;
      }
      if (loginController && feedbackEl) {
        loginController.renderFeedback(feedbackEl, 'Sesión cerrada exitosamente.', 'info');
      }
      if (routerHandle) {
        routerHandle.notifyAuthChanged();
      }
      navigateToRoute('login');
    }
  }

  // Función para salir de modo DEMO
  function exitDemoToLogin() {
    currentUser = null;
    deviceService = createDeviceService({ apiService });
    if (adminRoot) {
      adminRoot.hidden = true;
      adminRoot.innerHTML = '';
    }
    if (loginRoot) {
      loginRoot.hidden = false;
    }
    if (loginController && feedbackEl) {
      loginController.clearFeedback(feedbackEl);
    }
    if (routerHandle) {
      routerHandle.notifyAuthChanged();
    }
    navigateToRoute('login');
  }

  // 2. Definición del despachador de vistas
  async function dispatchRoute(routeId, routeState) {
    if (!sessionCheckResolved) {
      // Evitar que las vistas protegidas se rendericen antes de resolver la comprobación inicial
      return;
    }

    if (routeId === 'login') {
      if (adminRoot) {
        adminRoot.hidden = true;
        adminRoot.innerHTML = '';
      }
      if (loginRoot) {
        loginRoot.hidden = false;
      }
      document.title = 'Inicio de Sesión — VIGÍA Vision Systems';

      if (routeState?.blockedDemoAttempt && loginController && feedbackEl) {
        loginController.renderFeedback(feedbackEl, DEMO_DISABLED_NOTICE, 'warning');
        if (window.location.hash && window.location.hash !== '#login') {
          window.history.replaceState(null, '', `${window.location.pathname}#login`);
        }
      }
      return;
    }

    // Rutas protegidas o administrativas
    if (loginRoot) {
      loginRoot.hidden = true;
    }
    if (adminRoot) {
      adminRoot.hidden = false;

      if (routeId === 'cameras') {
        document.title = 'Monitoreo de Cámaras — VIGÍA Vision Systems';
        await renderCamerasView({
          container: adminRoot,
          apiService,
          currentUser,
          onNavigate: (nextRoute) => navigateToRoute(nextRoute),
          onLogout: () => handleLogout()
        });
      } else {
        document.title = `${routeId === 'devices' ? 'Gestión de Dispositivos' : 'Panel de Control'} — VIGÍA Vision Systems`;
        await renderAdminDevicesView({
          container: adminRoot,
          deviceService,
          activeRoute: routeId,
          currentUser,
          onNavigate: (nextRoute) => navigateToRoute(nextRoute),
          onLogout: () => handleLogout(),
          onExitDemo: () => exitDemoToLogin()
        });
      }
    }
  }

  // 3. Inicializar el enrutador con conocimiento del estado de autenticación en memoria
  routerHandle = initRouter(dispatchRoute, {
    getAuthState: () => Boolean(currentUser)
  });

  // 4. Restauración de Sesión (GET /api/v1/auth/me) al cargar la aplicación
  async function checkInitialSession() {
    // Mantener la interfaz protegida oculta durante la verificación
    if (adminRoot) adminRoot.hidden = true;
    if (loginRoot) loginRoot.hidden = true;

    try {
      const user = await apiService.getCurrentUser();
      sessionCheckResolved = true;

      if (user) {
        // Sesión válida confirmada por el servidor
        currentUser = user;
        const currentHash = (window.location.hash || '').replace(/^#\/?/, '').trim().toLowerCase();
        const initialRoute =
          currentHash && currentHash !== 'login'
            ? currentHash
            : user.rol === 'GUARDIA'
              ? 'cameras'
              : 'cameras';

        if (routerHandle) {
          routerHandle.notifyAuthChanged();
        }
        navigateToRoute(initialRoute);
      } else {
        // 401 No autenticado: mostrar pantalla de login
        currentUser = null;
        if (loginRoot) loginRoot.hidden = false;
        if (routerHandle) {
          routerHandle.notifyAuthChanged();
        }
        navigateToRoute('login');
      }
    } catch (err) {
      sessionCheckResolved = true;
      currentUser = null;
      // Error de red o error 5xx del servidor: mostrar estado de error recuperable (no 401)
      if (loginRoot) loginRoot.hidden = false;
      if (loginController && feedbackEl) {
        feedbackEl.innerHTML = '';
        const msgSpan = document.createElement('span');
        msgSpan.textContent =
          err instanceof NetworkError
            ? 'No se pudo conectar con el servidor VIGÍA (error de red o backend detenido). '
            : 'El servidor VIGÍA experimentó un error temporal al verificar la sesión. ';

        const retryLink = document.createElement('button');
        retryLink.type = 'button';
        retryLink.style.marginLeft = '0.5rem';
        retryLink.style.textDecoration = 'underline';
        retryLink.style.background = 'none';
        retryLink.style.border = 'none';
        retryLink.style.cursor = 'pointer';
        retryLink.style.color = 'inherit';
        retryLink.style.fontWeight = 'bold';
        retryLink.textContent = 'Reintentar';
        retryLink.addEventListener('click', (e) => {
          e.preventDefault();
          checkInitialSession();
        });

        feedbackEl.appendChild(msgSpan);
        feedbackEl.appendChild(retryLink);
        feedbackEl.className = 'login-feedback login-feedback--warning';
        feedbackEl.hidden = false;
      }
      if (routerHandle) {
        routerHandle.notifyAuthChanged();
      }
      navigateToRoute('login');
    }
  }

  checkInitialSession();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrapApp);
} else {
  bootstrapApp();
}
