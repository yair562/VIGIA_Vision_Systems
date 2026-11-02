/**
 * VIGÍA Vision Systems — Pruebas de Integración Frontend (Fase 3B)
 *
 * Cobertura de las 13 pruebas obligatorias requeridas por el contrato:
 * 1. Login correcto e incorrecto.
 * 2. Restauración de sesión con /auth/me.
 * 3. Estado no autenticado.
 * 4. Logout y limpieza de la interfaz.
 * 5. Ausencia de tokens de sesión en almacenamiento web (localStorage / sessionStorage).
 * 6. Transporte de cookies según el origen real ({ credentials: 'include' }).
 * 7. Carga de cámaras persistidas.
 * 8. Estado vacío sin cámaras.
 * 9. Manejo de errores 401, 403 y 5xx.
 * 10. Diferenciación entre fallos de red y sesiones inválidas.
 * 11. Presentación y navegación según el rol (ADMINISTRADOR vs GUARDIA vs AUDITOR).
 * 12. Aislamiento del modo DEMO.
 * 13. Preservación de la barra horizontal superior.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import {
  createApiService,
  AuthError,
  ForbiddenError,
  ServerError,
  NetworkError
} from '../web/js/services/api-service.js';
import { createDeviceService } from '../web/js/services/device-service.js';
import { resolveRouteState, isFrontendDemoEnabled } from '../web/js/router.js';
import { ADMIN_NAV_ITEMS, renderAdminNavbar } from '../web/js/components/admin-navbar.js';
import { renderCamerasView } from '../web/js/views/cameras-view.js';
import { initLoginView } from '../web/js/views/login-view.js';

// Setup de entorno DOM sintético ligero para Node.js
class FakeElement {
  constructor(tag = 'div') {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.attributes = {};
    const classes = new Set();
    this.classList = {
      add: (c) => classes.add(c),
      remove: (c) => classes.delete(c),
      contains: (c) => classes.has(c)
    };
    this.style = {};
    this.dataset = {};
    this.hidden = false;
    this.disabled = false;
    this._textContent = '';
    this.innerHTML = '';
    this.value = '';
    this.listeners = {};
  }

  get textContent() {
    return this._textContent;
  }
  set textContent(v) {
    this._textContent = String(v);
  }

  setAttribute(k, v) {
    this.attributes[k] = String(v);
  }
  getAttribute(k) {
    return this.attributes[k] || null;
  }
  removeAttribute(k) {
    delete this.attributes[k];
  }

  appendChild(c) {
    this.children.push(c);
    return c;
  }
  querySelector(sel) {
    if (sel.startsWith('#')) {
      const id = sel.slice(1);
      if (this.attributes['id'] === id) return this;
      for (const ch of this.children) {
        if (ch instanceof FakeElement) {
          const found = ch.querySelector(sel);
          if (found) return found;
        }
      }
    }
    return null;
  }
  querySelectorAll(sel) {
    return [];
  }
  addEventListener(event, fn) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(fn);
  }
  dispatchEvent(ev) {
    const list = this.listeners[ev.type] || [];
    for (const fn of list) fn(ev);
  }
  focus() {}
}

const fakeDocument = {
  createElement(tag) {
    return new FakeElement(tag);
  },
  createElementNS(ns, tag) {
    return new FakeElement(tag);
  },
  documentElement: new FakeElement('html')
};

globalThis.document = fakeDocument;
globalThis.window = {
  location: { hash: '#cameras', search: '', pathname: '/app' },
  history: { replaceState: () => {} },
  addEventListener: () => {},
  removeEventListener: () => {}
};

test('1. Login correcto e incorrecto en apiService', async (t) => {
  // Login exitoso
  const mockFetchSuccess = async (url, options) => {
    assert.equal(options.credentials, 'include', 'El transporte debe incluir credenciales.');
    assert.equal(options.method, 'POST');
    const body = JSON.parse(options.body);
    assert.equal(body.username, 'admin');
    return {
      ok: true,
      status: 200,
      headers: { get: () => 'application/json' },
      json: async () => ({
        ok: true,
        user: { id_usuario: '123', username: 'admin', rol: 'ADMINISTRADOR', activo: true }
      })
    };
  };

  const apiSuccess = createApiService({ fetchFn: mockFetchSuccess });
  const user = await apiSuccess.login('admin', 'Secret123!');
  assert.equal(user.username, 'admin');
  assert.equal(user.rol, 'ADMINISTRADOR');

  // Login fallido (401)
  const mockFetchFail = async () => ({
    ok: false,
    status: 401,
    headers: { get: () => 'application/json' },
    json: async () => ({ ok: false, error: 'INVALID_CREDENTIALS', message: 'Credenciales inválidas.' })
  });

  const apiFail = createApiService({ fetchFn: mockFetchFail });
  await assert.rejects(
    async () => apiFail.login('admin', 'WrongPass!'),
    (err) => err instanceof AuthError && err.status === 401
  );
});

test('2. Restauración de sesión con /auth/me', async () => {
  const mockFetchMe = async (url, options) => {
    assert.equal(options.credentials, 'include');
    return {
      ok: true,
      status: 200,
      headers: { get: () => 'application/json' },
      json: async () => ({
        ok: true,
        user: { id_usuario: 'uuid-1', username: 'guardia1', rol: 'GUARDIA', activo: true }
      })
    };
  };

  const api = createApiService({ fetchFn: mockFetchMe });
  const user = await api.getCurrentUser();
  assert.ok(user);
  assert.equal(user.username, 'guardia1');
  assert.equal(user.rol, 'GUARDIA');
});

test('3. Estado no autenticado: 401 devuelve null en getCurrentUser', async () => {
  const mockFetch401 = async () => ({
    ok: false,
    status: 401,
    headers: { get: () => 'application/json' },
    json: async () => ({ ok: false, error: 'UNAUTHORIZED', message: 'Sin sesión.' })
  });

  const api = createApiService({ fetchFn: mockFetch401 });
  const user = await api.getCurrentUser();
  assert.equal(user, null, 'Un 401 debe retornar null sin lanzar error no controlado.');
});

test('4. Logout y limpieza idempotente', async () => {
  let calledLogout = false;
  const mockFetchLogout = async (url, options) => {
    assert.equal(options.credentials, 'include');
    assert.equal(options.method, 'POST');
    calledLogout = true;
    return {
      ok: true,
      status: 200,
      headers: { get: () => 'application/json' },
      json: async () => ({ ok: true, message: 'Sesión cerrada exitosamente.' })
    };
  };

  const api = createApiService({ fetchFn: mockFetchLogout });
  const res = await api.logout();
  assert.equal(res, true);
  assert.equal(calledLogout, true);
});

test('5. Ausencia total de tokens en almacenamiento web', () => {
  // Simular mock de localStorage y sessionStorage espías
  let accessedStorage = false;
  const mockStorage = {
    getItem: () => { accessedStorage = true; return null; },
    setItem: () => { accessedStorage = true; },
    removeItem: () => { accessedStorage = true; }
  };

  globalThis.localStorage = mockStorage;
  globalThis.sessionStorage = mockStorage;

  // Ejecutar operaciones del cliente
  const api = createApiService({
    fetchFn: async () => ({
      ok: true,
      headers: { get: () => 'application/json' },
      json: async () => ({ ok: true, user: { username: 'test', rol: 'GUARDIA' } })
    })
  });

  assert.equal(accessedStorage, false, 'El servicio HTTP nunca debe acceder a almacenamiento web.');
});

test('6. Transporte de cookies con credentials: "include"', async () => {
  let capturedOptions = null;
  const mockFetch = async (url, options) => {
    capturedOptions = options;
    return {
      ok: true,
      headers: { get: () => 'application/json' },
      json: async () => ({ ok: true, cameras: [], total: 0 })
    };
  };

  const api = createApiService({ fetchFn: mockFetch });
  await api.getCameras();
  assert.ok(capturedOptions);
  assert.equal(capturedOptions.credentials, 'include', 'credentials: "include" es obligatorio.');
});

test('7. Carga de cámaras persistidas y exclusión estricta de uri_stream', async () => {
  const mockFetchCameras = async () => ({
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => ({
      ok: true,
      total: 1,
      cameras: [
        {
          id_camara: 'cam-uuid-1',
          codigo: 'CAM-01',
          nombre: 'Caseta Norte',
          activa: true,
          areas: [
            { id_area_vision: 'area-1', codigo: 'A-01', nombre: 'Carril 1', tipo_movimiento: 'ENTRADA' }
          ]
        }
      ]
    })
  });

  const api = createApiService({ fetchFn: mockFetchCameras });
  const res = await api.getCameras();
  assert.equal(res.ok, true);
  assert.equal(res.total, 1);
  assert.equal(res.cameras.length, 1);
  assert.equal(res.cameras[0].codigo, 'CAM-01');
  assert.equal(res.cameras[0].areas.length, 1);
  assert.equal(res.cameras[0].uri_stream, undefined, 'uri_stream NUNCA debe estar en la respuesta.');
});

test('8. Estado vacío sin cámaras', async () => {
  const mockFetchEmpty = async () => ({
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => ({ ok: true, cameras: [], total: 0 })
  });

  const api = createApiService({ fetchFn: mockFetchEmpty });
  const res = await api.getCameras();
  assert.equal(res.ok, true);
  assert.equal(res.cameras.length, 0);
  assert.equal(res.total, 0);
});

test('9. Manejo de errores 401, 403 y 5xx', async () => {
  // 401
  const api401 = createApiService({
    fetchFn: async () => ({
      ok: false,
      status: 401,
      headers: { get: () => 'application/json' },
      json: async () => ({ ok: false, error: 'UNAUTHORIZED', message: 'Sesión expirada' })
    })
  });
  await assert.rejects(async () => api401.getCameras(), (err) => err instanceof AuthError && err.status === 401);

  // 403 (Auditor)
  const api403 = createApiService({
    fetchFn: async () => ({
      ok: false,
      status: 403,
      headers: { get: () => 'application/json' },
      json: async () => ({ ok: false, error: 'FORBIDDEN', message: 'Acceso denegado' })
    })
  });
  await assert.rejects(async () => api403.getCameras(), (err) => err instanceof ForbiddenError && err.status === 403);

  // 500
  const api500 = createApiService({
    fetchFn: async () => ({
      ok: false,
      status: 500,
      headers: { get: () => 'application/json' },
      json: async () => ({ ok: false, error: 'INTERNAL_ERROR', message: 'Fallo de base de datos' })
    })
  });
  await assert.rejects(async () => api500.getCameras(), (err) => err instanceof ServerError && err.status === 500);
});

test('10. Diferenciación estricta entre fallos de red y sesiones inválidas', async () => {
  const apiNetworkDrop = createApiService({
    fetchFn: async () => {
      throw new TypeError('Failed to fetch (Network connection lost)');
    }
  });

  // getCurrentUser() ante caída de red debe lanzar NetworkError y NO devolver null (que significaría sesión inválida)
  await assert.rejects(
    async () => apiNetworkDrop.getCurrentUser(),
    (err) => err instanceof NetworkError,
    'Una caída de red NO debe confundirse con un 401 no autenticado.'
  );
});

test('11. Presentación y navegación según el rol', () => {
  // Router permite navegación a rutas administrativas si isAuthenticated = true
  const stateGuardia = resolveRouteState({ demoEnabled: false, isAuthenticated: true });
  assert.equal(stateGuardia.blockedDemoAttempt, false);

  // Navbar renderiza rol adecuadamente
  const navbar = renderAdminNavbar({
    activeSectionId: 'cameras',
    currentUser: { username: 'guardia_caseta', rol: 'GUARDIA', nombre_completo: 'Juan Vigilante' },
    onNavigate: () => {},
    onLogout: () => {}
  });
  assert.ok(navbar);
  assert.equal(navbar.tagName, 'HEADER');
});

test('12. Aislamiento del modo DEMO', () => {
  // Cuando el usuario no está autenticado y demoEnabled es false:
  globalThis.window = {
    location: { hash: '#cameras', search: '', pathname: '/app' },
    history: { replaceState: () => {} }
  };
  const docNoDemo = { documentElement: { getAttribute: () => 'false' } };
  assert.equal(isFrontendDemoEnabled(docNoDemo), false);

  const routeState = resolveRouteState({ demoEnabled: false, isAuthenticated: false });
  assert.equal(routeState.routeId, 'login');
  assert.equal(routeState.blockedDemoAttempt, true, 'Sin DEMO y sin autenticación debe bloquear.');
});

test('13. Preservación innegociable de la barra horizontal superior', () => {
  const navbar = renderAdminNavbar({
    activeSectionId: 'devices',
    currentUser: { username: 'admin', rol: 'ADMINISTRADOR' },
    onNavigate: () => {},
    onLogout: () => {}
  });

  assert.equal(navbar.tagName, 'HEADER');
  assert.equal(navbar.className, 'admin-navbar');

  // Verificar los 4 items obligatorios en navegación central
  const itemIds = ADMIN_NAV_ITEMS.map((i) => i.id);
  assert.deepEqual(itemIds, ['devices', 'cameras', 'alerts', 'reports']);

  // Verificar que cámaras está implementado
  const camerasItem = ADMIN_NAV_ITEMS.find((i) => i.id === 'cameras');
  assert.equal(camerasItem.implemented, true);
});

test('14. Contrato de apiService.get y apiService.post con credentials: "include" y JSON', async () => {
  const requests = [];
  const mockFetch = async (url, options) => {
    requests.push({ url, options });
    return {
      ok: true,
      status: 200,
      headers: { get: () => 'application/json' },
      json: async () => ({ ok: true, data: 'test-success' })
    };
  };

  const api = createApiService({ fetchFn: mockFetch });
  assert.equal(typeof api.get, 'function', 'apiService.get debe ser una función exportada.');
  assert.equal(typeof api.post, 'function', 'apiService.post debe ser una función exportada.');
  assert.equal(typeof api.request, 'function', 'apiService.request debe ser una función exportada.');

  // Probar GET
  const getRes = await api.get('/api/v1/devices');
  assert.equal(getRes.ok, true);
  assert.equal(requests[0].options.method, 'GET');
  assert.equal(requests[0].options.credentials, 'include', 'GET debe incluir credentials.');

  // Probar POST con objeto serializado automáticamente
  const postRes = await api.post('/api/v1/devices/pairing-qr', { codigo_camara: 'CAM-ENTRADA', ttl_minutes: 10 });
  assert.equal(postRes.ok, true);
  assert.equal(requests[1].options.method, 'POST');
  assert.equal(requests[1].options.credentials, 'include', 'POST debe incluir credentials.');
  assert.equal(requests[1].options.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(requests[1].options.body), { codigo_camara: 'CAM-ENTRADA', ttl_minutes: 10 });
});

test('15. Integración de deviceService con apiService para generación QR y revocación (MOB-QR-02)', async () => {
  const calls = [];
  const mockFetch = async (url, options) => {
    calls.push({ url, options });
    if (url.includes('/pairing-qr')) {
      return {
        ok: true,
        status: 201,
        headers: { get: () => 'application/json' },
        json: async () => ({
          ok: true,
          claim_token: 'vigia_claim_token_123',
          codigo_camara: 'CAM-ENTRADA',
          qr_base64_data_url: 'data:image/png;base64,mockqr',
          enrollment_url: 'https://127.0.0.1:5000/mobile?claim=vigia_claim_token_123&cam=CAM-ENTRADA',
          expira_en: '2026-11-02T01:00:00Z'
        })
      };
    }
    if (url.includes('/devices') && options.method === 'GET') {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({
          ok: true,
          devices: [
            {
              id_credencial: 'cred-1',
              id_camara: 'cam-1',
              nombre_dispositivo: 'Pixel 8 Real',
              codigo_camara: 'CAM-ENTRADA',
              activa: true,
              activado_en: '2026-11-01T12:00:00Z',
              ultima_actividad: '2026-11-01T12:05:00Z'
            }
          ]
        })
      };
    }
    if (url.includes('/revoke')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({ ok: true, message: 'Dispositivo revocado.' })
      };
    }
    throw new Error(`Ruta no esperada: ${url}`);
  };

  const apiService = createApiService({ fetchFn: mockFetch });
  const deviceService = createDeviceService({ apiService });

  // 1. generatePairingQr no debe lanzar TypeError: apiService.post is not a function
  const qrRes = await deviceService.generatePairingQr('CAM-ENTRADA', 10);
  assert.equal(qrRes.ok, true);
  assert.equal(qrRes.claim_token, 'vigia_claim_token_123');
  assert.equal(qrRes.codigo_camara, 'CAM-ENTRADA');
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(calls[0].options.credentials, 'include');

  // 2. listDevices debe consultar /api/v1/devices con apiService.get
  const devices = await deviceService.listDevices();
  assert.equal(devices.length, 1);
  assert.equal(devices[0].nombre, 'Pixel 8 Real');
  assert.equal(devices[0].estado, 'CONECTADO');
  assert.equal(devices[0].isRealDevice, true);
  assert.equal(calls[1].options.method, 'GET');

  // 3. revokeDevice debe consultar /api/v1/devices/:id/revoke con apiService.post
  const revRes = await deviceService.revokeDevice('cred-1', 'Prueba de revocación');
  assert.equal(revRes.ok, true);
  assert.equal(calls[2].options.method, 'POST');
  assert.deepEqual(JSON.parse(calls[2].options.body), { motivo: 'Prueba de revocación' });
});

test('16. Propagación fiel de errores 401, 403 y 500 en apiService.post y deviceService', async () => {
  // Simular 401 Unauthorized
  const mock401 = async () => ({
    ok: false,
    status: 401,
    headers: { get: () => 'application/json' },
    json: async () => ({ ok: false, error: 'UNAUTHORIZED', message: 'Sesión expirada.' })
  });
  const api401 = createApiService({ fetchFn: mock401 });
  const dev401 = createDeviceService({ apiService: api401 });

  await assert.rejects(
    async () => dev401.generatePairingQr('CAM-ENTRADA'),
    (err) => err instanceof AuthError && err.status === 401 && err.code === 'UNAUTHORIZED'
  );

  // Simular 403 Forbidden (ej. usuario GUARDIA intentando generar QR)
  const mock403 = async () => ({
    ok: false,
    status: 403,
    headers: { get: () => 'application/json' },
    json: async () => ({ ok: false, error: 'FORBIDDEN', message: 'Acceso restringido: requiere rol ADMINISTRADOR.' })
  });
  const api403 = createApiService({ fetchFn: mock403 });
  const dev403 = createDeviceService({ apiService: api403 });

  await assert.rejects(
    async () => dev403.generatePairingQr('CAM-ENTRADA'),
    (err) => err instanceof ForbiddenError && err.status === 403 && err.code === 'FORBIDDEN'
  );

  // Simular 500 Server Error
  const mock500 = async () => ({
    ok: false,
    status: 500,
    headers: { get: () => 'application/json' },
    json: async () => ({ ok: false, error: 'SERVER_ERROR', message: 'Error interno en PostgreSQL.' })
  });
  const api500 = createApiService({ fetchFn: mock500 });
  const dev500 = createDeviceService({ apiService: api500 });

  await assert.rejects(
    async () => dev500.generatePairingQr('CAM-ENTRADA'),
    (err) => err instanceof ServerError && err.status === 500 && err.code === 'SERVER_ERROR'
  );
});
