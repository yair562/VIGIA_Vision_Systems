/**
 * VIGÍA Vision Systems — Punto de entrada de la aplicación web (Sprint 01 + Sprint 02A — VO-02A-R1)
 *
 * Responsabilidades:
 * - Inicializar la vista de Inicio de Sesión (#login) conservando su diseño y comportamiento.
 * - Verificar la bandera explícita de entorno de desarrollo (data-demo-enabled) antes de
 *   permitir el acceso a las rutas de previsualización DEMO (#devices, #cameras, #alerts,
 *   #reports, #profile, #camera-viewer).
 * - Si DEMO está deshabilitado por defecto, bloquear cualquier intento de acceso por hash o
 *   query string, regresar a #login y mostrar un aviso accesible de acceso no disponible.
 * - Permitir salir de la vista DEMO hacia #login limpiando cualquier estado temporal en memoria.
 */

import { initLoginView } from './views/login-view.js';
import { renderAdminDevicesView } from './views/devices-view.js';
import { createDeviceService } from './services/device-service.js';
import { initRouter, navigateToRoute } from './router.js';

const DEMO_DISABLED_NOTICE =
  'El modo de previsualización DEMO está deshabilitado por defecto. Inicia sesión o habilita VIGIA_ENABLE_FRONTEND_DEMO=1 en el entorno de desarrollo.';

function bootstrapApp() {
  const loginRoot = document.getElementById('app-root');
  const adminRoot = document.getElementById('admin-root');
  const feedbackEl = document.getElementById('login-feedback');
  let deviceService = createDeviceService();

  // Inicializar el formulario de Inicio de Sesión (Sprint 01 intacto)
  const loginController = initLoginView(document);

  // Configurar tema desde parámetro opcional (?theme=dark | light) para pruebas de diseño
  const searchParams = new URLSearchParams(window.location.search);
  const requestedTheme = searchParams.get('theme');
  if (requestedTheme === 'dark' || requestedTheme === 'light') {
    document.documentElement.setAttribute('data-theme', requestedTheme);
  }

  // Función para salir de la vista DEMO, reiniciar el estado temporal en memoria y volver al login
  function exitDemoToLogin() {
    deviceService = createDeviceService();
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
    navigateToRoute('login');
  }

  // Enrutamiento controlado entre Inicio de Sesión (#login) y previsualización DEMO (#devices, etc.)
  initRouter(async (routeId, routeState) => {
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

    if (loginRoot) {
      loginRoot.hidden = true;
    }
    if (adminRoot) {
      adminRoot.hidden = false;
      document.title = 'Gestión de Dispositivos (DEMO) — VIGÍA Vision Systems';
      await renderAdminDevicesView({
        container: adminRoot,
        deviceService,
        activeRoute: routeId,
        onNavigate: (nextRoute) => navigateToRoute(nextRoute),
        onExitDemo: () => exitDemoToLogin()
      });
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrapApp);
} else {
  bootstrapApp();
}
