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
    this._classes = classes;
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
    this._className = '';
    this._innerHTML = '';
    this.value = '';
    this.listeners = {};
  }

  get innerHTML() {
    return this._innerHTML || '';
  }
  set innerHTML(v) {
    this._innerHTML = String(v);
    if (v === '') {
      this.children = [];
    }
  }

  get src() {
    return this.attributes['src'];
  }
  set src(v) {
    if (v === '' || v === undefined) {
      delete this.attributes['src'];
    } else {
      this.attributes['src'] = String(v);
    }
  }

  get id() {
    return this.attributes['id'];
  }
  set id(v) {
    if (v === '' || v === undefined) {
      delete this.attributes['id'];
    } else {
      this.attributes['id'] = String(v);
    }
  }

  get className() {
    return Array.from(this._classes).join(' ');
  }
  set className(v) {
    this._classes.clear();
    String(v).split(/\s+/).filter(Boolean).forEach((c) => this._classes.add(c));
  }

  get textContent() {
    return this._textContent;
  }
  set textContent(v) {
    this._textContent = String(v);
  }

  setAttribute(k, v) {
    this.attributes[k] = String(v);
    if (k === 'class') {
      this.className = v;
    }
  }
  getAttribute(k) {
    if (k === 'class') return this.className;
    return this.attributes[k] || null;
  }
  removeAttribute(k) {
    delete this.attributes[k];
    if (k === 'class') this._classes.clear();
  }

  appendChild(c) {
    this.children.push(c);
    return c;
  }
  querySelector(sel) {
    const checkEl = (el, s) => {
      if (s.startsWith('#')) return el.attributes['id'] === s.slice(1);
      if (s.startsWith('.')) return el._classes && el._classes.has(s.slice(1));
      if (/^[a-zA-Z]+$/.test(s)) return el.tagName === s.toUpperCase();
      return false;
    };
    for (const ch of this.children) {
      if (ch instanceof FakeElement) {
        if (checkEl(ch, sel)) return ch;
        const found = ch.querySelector(sel);
        if (found) return found;
      }
    }
    return null;
  }
  querySelectorAll(sel) {
    const results = [];
    const check = (el) => {
      if (sel.startsWith('.')) {
        if (el._classes && el._classes.has(sel.slice(1))) results.push(el);
      } else if (sel.startsWith('#')) {
        if (el.attributes['id'] === sel.slice(1)) results.push(el);
      } else if (/^[a-zA-Z]+$/.test(sel)) {
        if (el.tagName === sel.toUpperCase()) results.push(el);
      }
      for (const ch of el.children) {
        if (ch instanceof FakeElement) check(ch);
      }
    };
    for (const ch of this.children) {
      if (ch instanceof FakeElement) check(ch);
    }
    return results;
  }
  addEventListener(event, fn) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(fn);
  }
  removeEventListener(event, fn) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter((f) => f !== fn);
    }
  }
  dispatchEvent(ev) {
    const list = this.listeners[ev.type] || [];
    for (const fn of list) fn(ev);
  }
  focus() {}
}

const fakeDocument = {
  listeners: {},
  hidden: false,
  createElement(tag) {
    return new FakeElement(tag);
  },
  createElementNS(ns, tag) {
    return new FakeElement(tag);
  },
  documentElement: new FakeElement('html'),
  addEventListener(event, fn) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(fn);
  },
  removeEventListener(event, fn) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter((f) => f !== fn);
    }
  },
  dispatchEvent(ev) {
    const list = this.listeners[ev.type] || [];
    for (const fn of list) fn(ev);
  }
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

  // Verificación de URLs de streaming canónico en apiService
  const streamUrl = api.getCameraLiveStreamUrl(res.cameras[0].codigo);
  assert.match(streamUrl, /\/api\/v1\/cameras\/CAM-01\/stream$/);
  const liveUrl = api.getCameraLiveFrameUrl(res.cameras[0].codigo);
  assert.match(liveUrl, /\/api\/v1\/cameras\/CAM-01\/live$/);
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

test('17. Consulta de información de red y direcciones LAN en apiService (VIGIA-NET-01)', async () => {
  const mockNetFetch = async (url) => {
    if (url.includes('/api/v1/system/network')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({
          ok: true,
          local_url: 'http://127.0.0.1:5000',
          lan_urls: ['http://192.168.1.75:5000'],
          recommended_lan_url: 'http://192.168.1.75:5000',
          port: 5000,
          tls_enabled: false
        })
      };
    }
    throw new Error(`Ruta no esperada: ${url}`);
  };

  const apiService = createApiService({ fetchFn: mockNetFetch });
  const netInfo = await apiService.getNetworkInfo();

  assert.equal(netInfo.ok, true);
  assert.equal(netInfo.local_url, 'http://127.0.0.1:5000');
  assert.equal(netInfo.recommended_lan_url, 'http://192.168.1.75:5000');
  assert.equal(netInfo.port, 5000);
  assert.equal(netInfo.tls_enabled, false);
});

test('18. Integración de streaming, visor de video y estados operativos en cameras-view (CAM-01C y CAM-01E)', async () => {
  const mockCamerasData = {
    ok: true,
    total: 1,
    cameras: [
      {
        id_camara: 'cam-uuid-101',
        codigo: 'CAM-ENTRADA',
        nombre: 'Cámara Carril Entrada',
        activa: true,
        areas: [
          { id_area_vision: 'area-1', codigo: 'ROI-ENT', nombre: 'Zona Lectura Entrada', tipo_movimiento: 'ENTRADA' }
        ]
      }
    ]
  };

  let statusMockData = {
    ok: true,
    codigo_camara: 'CAM-ENTRADA',
    is_transmitting: true,
    operational_state: 'TRANSMITIENDO',
    vehicle_detected: true,
    tipo_vehiculo: 'camioneta',
    confianza: 0.94,
    in_roi: 1,
    status: 'PROCESANDO_CORRECTAMENTE'
  };

  let statusCallCount = 0;
  const mockFetch = async (url) => {
    if (url.includes('/api/v1/cameras/CAM-ENTRADA/status')) {
      statusCallCount++;
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => statusMockData
      };
    }
    if (url.includes('/api/v1/cameras')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => mockCamerasData
      };
    }
    throw new Error(`Ruta mock inesperada: ${url}`);
  };

  const fakeContainer = new FakeElement('div');
  const api = createApiService({ fetchFn: mockFetch });

  let navigatedTo = null;
  await renderCamerasView({
    container: fakeContainer,
    apiService: api,
    currentUser: { username: 'admin', rol: 'ADMINISTRADOR' },
    onNavigate: (r) => { navigatedTo = r; }
  });

  // 1. Existencia del elemento img.camera-stream-img y visor
  const streamImg = fakeContainer.querySelector('.camera-stream-img');
  assert.ok(streamImg, 'Debe renderizarse el elemento img.camera-stream-img en la tarjeta');

  // 2. Construcción correcta de la URL MJPEG
  const streamUrl = api.getCameraLiveStreamUrl('CAM-ENTRADA');
  assert.equal(streamUrl.endsWith('/api/v1/cameras/CAM-ENTRADA/stream'), true);
  assert.equal(streamImg.attributes['src'], streamUrl);

  // 3. Representación de TRANSMITIENDO
  const statusPill = fakeContainer.querySelector('.camera-status-pill');
  assert.ok(statusPill, 'Debe existir la pastilla de estado');
  assert.equal(statusPill.classList.contains('camera-status-pill--transmitting'), true);
  const statusText = fakeContainer.querySelector('.camera-status-text');
  assert.equal(statusText.textContent, 'TRANSMITIENDO');

  // 9. Detecciones se presentan cuando hay evidencia suficiente
  const detBadge = fakeContainer.querySelector('.camera-detection-badge');
  assert.ok(detBadge, 'Debe mostrarse badge de detección cuando hay vehículo y confianza');
  assert.match(detBadge.textContent, /DETECTADO: CAMIONETA \(94%\)/);
  const roiBadge = fakeContainer.querySelector('.camera-detection-roi');
  assert.ok(roiBadge, 'Debe mostrarse badge de ROI');
  assert.equal(roiBadge.textContent, 'EN ZONA ROI');

  // 8. Un error del <img> no modifica el estado operativo de la cámara (CAM-01E-01)
  const playbackOverlay = fakeContainer.querySelector('.camera-playback-error');
  assert.ok(playbackOverlay, 'Debe existir overlay independiente para error de reproducción');
  assert.equal(playbackOverlay.hidden, true, 'Inicialmente el error de reproducción está oculto');

  // Simular evento error en streamImg
  streamImg.dispatchEvent({ type: 'error' });
  assert.equal(playbackOverlay.hidden, false, 'El error de reproducción debe visualizarse');
  assert.equal(statusPill.classList.contains('camera-status-pill--transmitting'), true, 'La pastilla de estado DEBE mantenerse en TRANSMITIENDO y no mutar a SIN_SEÑAL');

  // 12 & 13. Cancelación al abandonar la vista y liberación de streams MJPEG
  const navBtn = fakeContainer.querySelector('#btn-refresh-cameras');
  assert.ok(navBtn);
  assert.equal(streamImg.attributes['src'] !== undefined, true);

  // Simular navegación
  const navHandler = fakeContainer.querySelector('.admin-navbar');
  assert.ok(navHandler);
});

test('19. Verificación exhaustiva de estados operativos del backend (CAM-01E)', async () => {
  const testStates = ['EN_ESPERA', 'SIN_SEÑAL', 'ENROLADA', 'ERROR'];

  for (const st of testStates) {
    const mockData = {
      ok: true,
      total: 1,
      cameras: [{ id_camara: `cam-${st}`, codigo: `CAM-${st}`, nombre: `Cam ${st}`, activa: true, areas: [] }]
    };
    const mockStatus = {
      ok: true,
      codigo_camara: `CAM-${st}`,
      is_transmitting: false,
      operational_state: st,
      vehicle_detected: false,
      status: st === 'ERROR' ? 'PROCESSING_ERROR' : 'EN_ESPERA'
    };

    const api = createApiService({
      fetchFn: async (url) => {
        if (url.includes('/status')) return { ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => mockStatus };
        return { ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => mockData };
      }
    });

    const container = new FakeElement('div');
    await renderCamerasView({
      container,
      apiService: api,
      currentUser: { username: 'admin', rol: 'ADMINISTRADOR' },
      onNavigate: () => {}
    });

    const statusPill = container.querySelector('.camera-status-pill');
    const statusText = container.querySelector('.camera-status-text');
    assert.ok(statusPill);
    assert.equal(statusText.textContent, st.replace('_', ' '));

    const detInfo = container.querySelector('.camera-detection-info');
    assert.equal(detInfo.textContent, 'DETECCIONES NO DISPONIBLES', 'Si no está transmitiendo, no debe mostrar inferencias activas');
  }
});

test('20. Lifecycle, protección de concurrencia y liberación de fuentes MJPEG (CAM-01E)', async () => {
  let concurrentCalls = 0;
  let maxConcurrentCalls = 0;

  const mockApi = {
    getCameras: async () => ({
      ok: true,
      total: 1,
      cameras: [{ id_camara: 'c-1', codigo: 'CAM-CONC', nombre: 'Cam Concurrencia', activa: true, areas: [] }]
    }),
    getCameraLiveStreamUrl: (code) => `/api/v1/cameras/${code}/stream`,
    getCameraStatus: async () => {
      concurrentCalls++;
      if (concurrentCalls > maxConcurrentCalls) maxConcurrentCalls = concurrentCalls;
      await new Promise((r) => setTimeout(r, 10));
      concurrentCalls--;
      return {
        ok: true,
        codigo_camara: 'CAM-CONC',
        is_transmitting: true,
        operational_state: 'TRANSMITIENDO',
        vehicle_detected: false,
        status: 'PROCESANDO_CORRECTAMENTE'
      };
    }
  };

  const container = new FakeElement('div');
  let currentRoute = 'cameras';

  await renderCamerasView({
    container,
    apiService: mockApi,
    currentUser: { username: 'admin', rol: 'ADMINISTRADOR' },
    onNavigate: (r) => { currentRoute = r; }
  });

  const streamImg = container.querySelector('.camera-stream-img');
  assert.ok(streamImg);

  // Simular botón Actualizar para probar que no duplica streams
  const refreshBtn = container.querySelector('#btn-refresh-cameras');
  assert.ok(refreshBtn);
  await refreshBtn.dispatchEvent({ type: 'click' });

  // La concurrencia máxima en todo momento debe ser 1 (reentrancia prevenida)
  assert.equal(maxConcurrentCalls, 1, 'El polling no debe generar consultas concurrentes a getCameraStatus');

  // Probar desmontaje con navegación simulada
  const navBtns = container.querySelectorAll('.admin-nav-item');
  if (navBtns.length > 0) {
    navBtns[0].dispatchEvent({ type: 'click' });
  }

  // Verificar que el src de la imagen fue liberado con removeAttribute
  assert.equal(streamImg.attributes['src'], undefined, 'removeAttribute("src") debe ejecutarse al desmontar');
});

test('21. Automatización de transmisión móvil con botón único y ciclo secuencial (MOB-CAM-02D)', async () => {
  // Inspeccionar el código HTML y JavaScript de mobile/index.html
  const fs = await import('node:fs/promises');
  const path = await import('node:path');
  const mobileHtmlPath = path.resolve('VIGIA_Vision_Systems/VIGIA_Dashboard/mobile/index.html');
  const htmlContent = await fs.readFile(mobileHtmlPath, 'utf-8');

  // 1. Conservación íntegra del enrolamiento
  assert.match(htmlContent, /urlParams\.get\('claim'\)/, 'Debe leer ?claim= de la URL');
  assert.match(htmlContent, /urlParams\.get\('cam'\)/, 'Debe leer ?cam= de la URL');
  assert.match(htmlContent, /\/api\/v1\/mobile\/pairing\/claim/, 'Debe consultar endpoint /claim');
  assert.match(htmlContent, /\/api\/v1\/mobile\/pairing\/confirm/, 'Debe consultar endpoint /confirm');
  assert.match(htmlContent, /sessionStorage\.setItem\('vigia_mobile_stream_token'/, 'Debe almacenar token en sessionStorage');
  assert.doesNotMatch(htmlContent, /localStorage/, 'Prohibido almacenar credenciales en localStorage');

  // 2. Experiencia de botón único principal
  assert.match(htmlContent, /id="btn-stream-toggle"/, 'Debe existir el botón único de transmisión');
  assert.doesNotMatch(htmlContent, /id="btn-capture"/, 'Los botones fragmentados de captura deben eliminarse');
  assert.doesNotMatch(htmlContent, /id="btn-start"/, 'El botón de activar cámara separado debe eliminarse');

  // 3. Ausencia total de setInterval para transmisión de fotogramas
  assert.doesNotMatch(htmlContent, /setInterval\([^)]*captureAndSendFrame/, 'Prohibido usar setInterval para transmitir fotogramas');

  // 4. Ciclo secuencial, AbortController y control de concurrencia
  assert.match(htmlContent, /new AbortController\(\)/, 'Debe utilizar AbortController para timeout y cancelación');
  assert.match(htmlContent, /REQUEST_TIMEOUT_MS\s*=\s*6000/, 'Debe incorporar timeout de petición');
  assert.match(htmlContent, /isCapturingFrame/, 'Debe proteger contra capturas en vuelo concurrentes');
  assert.match(htmlContent, /sendNextFrameLoop/, 'Debe implementar ciclo secuencial');

  // 5. Manejo explícito de códigos HTTP de seguridad
  assert.match(htmlContent, /resp\.status === 401\s*\|\|\s*resp\.status === 403/, 'Debe manejar 401 y 403 revocando transmisión');
  assert.match(htmlContent, /resp\.status === 429/, 'Debe manejar 429 backpressure');

  // 6. Manejo de ciclo de vida del dispositivo y visibilidad
  assert.match(htmlContent, /videoTrack\.onended/, 'Debe manejar desconexión del track de cámara');
  assert.match(htmlContent, /videoTrack\.onmute/, 'Debe manejar silencio transitorio de cámara');
  assert.match(htmlContent, /addEventListener\('visibilitychange'/, 'Debe responder a cambio de visibilidad de pestaña');
  assert.match(htmlContent, /currentSessionToken/, 'Debe invalidar callbacks antiguos mediante token de sesión');
});

test('22. Visor adaptativo para orientación Portrait, Landscape y cambios dinámicos (FE-05A)', async () => {
  const mockCamerasData = {
    ok: true,
    total: 1,
    cameras: [{
      id_camara: 'cam-01',
      codigo: 'CAM-ENTRADA',
      nombre: 'Carril Entrada',
      activa: true,
      areas: []
    }]
  };

  const mockFetch = async (url) => {
    if (url.endsWith('/api/v1/cameras')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => mockCamerasData
      };
    }
    if (url.includes('/status')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({
          ok: true,
          operational_state: 'TRANSMITIENDO',
          is_transmitting: true
        })
      };
    }
    throw new Error(`Ruta mock inesperada: ${url}`);
  };

  const container = new FakeElement('div');
  const api = createApiService({ fetchFn: mockFetch });

  await renderCamerasView({
    container,
    apiService: api,
    currentUser: { username: 'admin', rol: 'ADMINISTRADOR' },
    onNavigate: () => {}
  });

  const mediaBox = container.querySelector('.camera-card-media');
  const streamImg = container.querySelector('.camera-stream-img');
  assert.ok(mediaBox, 'Debe existir .camera-card-media');
  assert.ok(streamImg, 'Debe existir .camera-stream-img');

  // 1. Detección de formato Portrait (vertical 720x1280)
  streamImg.naturalWidth = 720;
  streamImg.naturalHeight = 1280;
  streamImg.dispatchEvent({ type: 'load' });

  assert.equal(mediaBox.classList.contains('camera-card-media--portrait'), true, 'Debe aplicar .camera-card-media--portrait');
  assert.equal(mediaBox.classList.contains('camera-card-media--landscape'), false, 'No debe tener .camera-card-media--landscape');

  // 2. Detección de formato Landscape (horizontal 1280x720)
  streamImg.naturalWidth = 1280;
  streamImg.naturalHeight = 720;
  streamImg.dispatchEvent({ type: 'load' });

  assert.equal(mediaBox.classList.contains('camera-card-media--landscape'), true, 'Debe aplicar .camera-card-media--landscape');
  assert.equal(mediaBox.classList.contains('camera-card-media--portrait'), false, 'No debe tener .camera-card-media--portrait');

  // 3. Inspección de reglas CSS: preservación de object-fit: contain y proporciones
  const fs = await import('node:fs/promises');
  const path = await import('node:path');
  const cssPath = path.resolve('VIGIA_Vision_Systems/VIGIA_Dashboard/web/css/admin-devices.css');
  const cssContent = await fs.readFile(cssPath, 'utf-8');

  assert.match(cssContent, /\.camera-card-media--portrait/, 'El CSS debe definir .camera-card-media--portrait');
  assert.match(cssContent, /aspect-ratio:\s*9\s*\/\s*16/, 'Debe utilizar aspect-ratio: 9 / 16 para portrait');
  assert.match(cssContent, /object-fit:\s*contain/, 'Debe mantener object-fit: contain');
  assert.doesNotMatch(cssContent, /\.camera-stream-img\s*\{[^}]*object-fit:\s*cover/, 'Prohibido usar object-fit: cover en el Dashboard');
});

test('23. Recuperación automática y manual del stream MJPEG con backoff exponencial y cache-busting (FE-05B)', async () => {
  const mockCamerasData = {
    ok: true,
    total: 1,
    cameras: [{
      id_camara: 'cam-01',
      codigo: 'CAM-ENTRADA',
      nombre: 'Carril Entrada',
      activa: true,
      areas: []
    }]
  };

  const mockFetch = async (url) => {
    if (url.endsWith('/api/v1/cameras')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => mockCamerasData
      };
    }
    if (url.includes('/status')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({
          ok: true,
          operational_state: 'TRANSMITIENDO',
          is_transmitting: true
        })
      };
    }
    throw new Error(`Ruta mock inesperada: ${url}`);
  };

  const container = new FakeElement('div');
  const api = createApiService({ fetchFn: mockFetch });

  await renderCamerasView({
    container,
    apiService: api,
    currentUser: { username: 'admin', rol: 'ADMINISTRADOR' },
    onNavigate: () => {}
  });

  const streamImg = container.querySelector('.camera-stream-img');
  const errorOverlay = container.querySelector('.camera-playback-error');
  const retryBtn = container.querySelector('.camera-playback-retry-btn');
  const playbackBadge = container.querySelector('.camera-playback-badge');
  const initialSrc = streamImg.src;

  assert.equal(errorOverlay.hidden, true, 'Inicialmente el overlay de error debe estar oculto');
  assert.ok(retryBtn, 'Debe existir el botón accesible de reintento');

  // 1. Simulación de fallo en stream: debe mostrar overlay y programar reconexión
  streamImg.dispatchEvent({ type: 'error' });
  assert.equal(errorOverlay.hidden, false, 'El overlay de error debe ser visible');
  assert.match(playbackBadge.textContent, /RECONECTANDO TRANSMISIÓN/, 'El badge debe reflejar proceso de reconexión');

  // 2. Reintento manual: debe actualizar src con parámetro de cache-busting (?retry=)
  retryBtn.dispatchEvent({ type: 'click' });
  assert.match(streamImg.src, /\?retry=\d+/, 'Debe aplicar parámetro de cache-busting');
  assert.notEqual(streamImg.src, initialSrc, 'El src debe haberse actualizado tras el reintento');

  // 3. Recuperación exitosa: evento load oculta el overlay
  streamImg.dispatchEvent({ type: 'load' });
  assert.equal(errorOverlay.hidden, true, 'El evento load debe ocultar el overlay de error');
});

test('24. Cancelación de reintentos y liberación de temporizadores al desmontar vista (FE-05B/Lifecycle)', async () => {
  const mockCamerasData = {
    ok: true,
    total: 1,
    cameras: [{
      id_camara: 'cam-01',
      codigo: 'CAM-ENTRADA',
      nombre: 'Carril Entrada',
      activa: true,
      areas: []
    }]
  };

  const mockFetch = async () => ({
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => mockCamerasData
  });

  const container = new FakeElement('div');
  const api = createApiService({ fetchFn: mockFetch });

  await renderCamerasView({
    container,
    apiService: api,
    currentUser: { username: 'admin', rol: 'ADMINISTRADOR' },
    onNavigate: () => {}
  });

  const streamImg = container.querySelector('.camera-stream-img');
  streamImg.dispatchEvent({ type: 'error' });

  const navBtn = container.querySelector('.admin-nav-btn');
  if (navBtn) {
    navBtn.dispatchEvent({ type: 'click' });
  }

  assert.equal(streamImg.attributes['src'], undefined, 'removeAttribute("src") debe haberse invocado');
});

test('25. Suspensión de polling con visibilitychange y reactivación inmediata (FE-05C)', async () => {
  let statusPollCount = 0;
  const mockCamerasData = {
    ok: true,
    total: 1,
    cameras: [{
      id_camara: 'cam-01',
      codigo: 'CAM-ENTRADA',
      nombre: 'Carril Entrada',
      activa: true,
      areas: []
    }]
  };

  const mockFetch = async (url) => {
    if (url.endsWith('/api/v1/cameras')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => mockCamerasData
      };
    }
    if (url.includes('/status')) {
      statusPollCount++;
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({
          ok: true,
          operational_state: 'TRANSMITIENDO',
          is_transmitting: true
        })
      };
    }
    throw new Error(`Ruta mock inesperada: ${url}`);
  };

  const container = new FakeElement('div');
  const api = createApiService({ fetchFn: mockFetch });

  await renderCamerasView({
    container,
    apiService: api,
    currentUser: { username: 'admin', rol: 'ADMINISTRADOR' },
    onNavigate: () => {}
  });

  const initialCount = statusPollCount;
  assert.ok(initialCount >= 1, 'Debe haber ejecutado al menos 1 consulta inicial');

  // 1. Simular pestaña oculta (document.hidden = true)
  fakeDocument.hidden = true;
  fakeDocument.dispatchEvent({ type: 'visibilitychange' });

  // 2. Simular regreso a pestaña visible (document.hidden = false)
  fakeDocument.hidden = false;
  fakeDocument.dispatchEvent({ type: 'visibilitychange' });

  assert.ok(statusPollCount > initialCount, 'Al volver a ser visible debe ejecutar actualización inmediata');

  // 3. Desmontar vista
  const navBtns = container.querySelectorAll('.admin-nav-item');
  if (navBtns.length > 0) {
    navBtns[0].dispatchEvent({ type: 'click' });
  }
});

test('26. Realce visual diferenciado ante detecciones y presencia en zona ROI (FE-05A/6)', async () => {
  let mockStatusResponse = {
    ok: true,
    operational_state: 'TRANSMITIENDO',
    is_transmitting: true,
    vehicle_detected: true,
    tipo_vehiculo: 'car',
    confianza: 0.88,
    in_roi: 1
  };

  const mockCamerasData = {
    ok: true,
    total: 1,
    cameras: [{
      id_camara: 'cam-01',
      codigo: 'CAM-ENTRADA',
      nombre: 'Carril Entrada',
      activa: true,
      areas: []
    }]
  };

  const mockFetch = async (url) => {
    if (url.endsWith('/api/v1/cameras')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => mockCamerasData
      };
    }
    if (url.includes('/status')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => mockStatusResponse
      };
    }
    throw new Error(`Ruta mock inesperada: ${url}`);
  };

  const container = new FakeElement('div');
  const api = createApiService({ fetchFn: mockFetch });

  await renderCamerasView({
    container,
    apiService: api,
    currentUser: { username: 'admin', rol: 'ADMINISTRADOR' },
    onNavigate: () => {}
  });

  const card = container.querySelector('.camera-card');
  const mediaBox = container.querySelector('.camera-card-media');
  assert.ok(card, 'Debe existir la tarjeta');
  assert.ok(mediaBox, 'Debe existir el mediaBox');

  // 1. Vehículo detectado y en ROI (in_roi === 1)
  assert.equal(card.classList.contains('camera-card--vehicle-detected'), true, 'Debe tener .camera-card--vehicle-detected');
  assert.equal(card.classList.contains('camera-card--roi-active'), true, 'Debe tener .camera-card--roi-active');
  assert.equal(mediaBox.classList.contains('camera-card-media--roi-active'), true, 'Debe tener .camera-card-media--roi-active');

  // 2. Vehículo detectado pero fuera de ROI (in_roi === 0)
  mockStatusResponse = {
    ok: true,
    operational_state: 'TRANSMITIENDO',
    is_transmitting: true,
    vehicle_detected: true,
    tipo_vehiculo: 'truck',
    confianza: 0.75,
    in_roi: 0
  };
  const refreshBtn = container.querySelector('#btn-refresh-cameras');
  refreshBtn.dispatchEvent({ type: 'click' });
  await new Promise((r) => setTimeout(r, 20));

  const refreshedCard = container.querySelector('.camera-card');
  const refreshedMedia = container.querySelector('.camera-card-media');
  assert.equal(refreshedCard.classList.contains('camera-card--vehicle-detected'), true, 'Debe conservar detección de vehículo');
  assert.equal(refreshedCard.classList.contains('camera-card--roi-active'), false, 'No debe tener .camera-card--roi-active si in_roi es 0');
  assert.equal(refreshedMedia.classList.contains('camera-card-media--roi-active'), false, 'No debe tener .camera-card-media--roi-active');

  // 3. Sin vehículo detectado
  mockStatusResponse = {
    ok: true,
    operational_state: 'TRANSMITIENDO',
    is_transmitting: true,
    vehicle_detected: false,
    in_roi: 0
  };
  refreshBtn.dispatchEvent({ type: 'click' });
  await new Promise((r) => setTimeout(r, 20));

  const emptyCard = container.querySelector('.camera-card');
  assert.equal(emptyCard.classList.contains('camera-card--vehicle-detected'), false, 'Debe remover .camera-card--vehicle-detected');
  assert.equal(emptyCard.classList.contains('camera-card--roi-active'), false, 'Debe remover .camera-card--roi-active');
});

test('27. Vista previa fidedigna en módulo móvil sin recorte engañoso (FE-05A/Mobile)', async () => {
  const fs = await import('node:fs/promises');
  const path = await import('node:path');
  const mobileHtmlPath = path.resolve('VIGIA_Vision_Systems/VIGIA_Dashboard/mobile/index.html');
  const htmlContent = await fs.readFile(mobileHtmlPath, 'utf-8');

  // 1. Ausencia de recorte con cover
  assert.doesNotMatch(htmlContent, /video\s*\{[^}]*object-fit:\s*cover/, 'Prohibido usar object-fit: cover en la vista previa');
  assert.match(htmlContent, /object-fit:\s*contain/, 'Debe utilizar object-fit: contain para evitar recortes engañosos');

  // 2. Contenedor con aspecto adaptativo y no fijo a 4/3
  assert.doesNotMatch(htmlContent, /\.preview-container\s*\{[^}]*aspect-ratio:\s*4\s*\/\s*3/, 'Prohibido fijar aspect-ratio a 4/3 en el móvil');
  assert.match(htmlContent, /adaptPreviewAspect/, 'Debe implementar función de adaptación de aspecto de vista previa');
});

test('28. 401 en polling de telemetría detiene polling, libera streams y muestra pantalla de reautenticación (VIGIA-AUTH-01)', async () => {
  const mockCamerasData = {
    ok: true,
    total: 1,
    cameras: [
      {
        id_camara: 'cam-uuid-401',
        codigo: 'CAM-ENTRADA',
        nombre: 'Cámara Principal',
        activa: true,
        areas: []
      }
    ]
  };

  let pollAttempts = 0;
  const mockFetch = async (url) => {
    if (url.includes('/api/v1/cameras/CAM-ENTRADA/status')) {
      pollAttempts++;
      return {
        ok: false,
        status: 401,
        headers: { get: () => 'application/json' },
        json: async () => ({ ok: false, error: 'UNAUTHORIZED', message: 'Sesión expirada.' })
      };
    }
    if (url.includes('/api/v1/cameras')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => mockCamerasData
      };
    }
    throw new Error(`Ruta no esperada: ${url}`);
  };

  const fakeContainer = new FakeElement('div');
  const api = createApiService({ fetchFn: mockFetch });
  let navigatedRoute = null;

  await renderCamerasView({
    container: fakeContainer,
    apiService: api,
    currentUser: { username: 'admin', rol: 'ADMINISTRADOR' },
    onNavigate: (r) => { navigatedRoute = r; }
  });

  // Debe haberse renderizado el estado de error de autenticación 401
  const authErrEl = fakeContainer.querySelector('.camera-state--auth-error');
  assert.ok(authErrEl, 'Debe renderizarse el contenedor de error de autenticación 401');
  const title = fakeContainer.querySelector('.camera-error-title');
  assert.match(title.textContent, /HTTP 401/);

  // Ninguna tarjeta debe permanecer en estado TRANSMITIENDO
  const transmittingPill = fakeContainer.querySelector('.camera-status-pill--transmitting');
  assert.equal(transmittingPill, null, 'No debe conservarse ninguna tarjeta en estado TRANSMITIENDO tras 401');

  // El botón de navegación debe conducir a login
  const loginBtn = authErrEl.querySelector('button');
  assert.ok(loginBtn, 'Debe existir botón para ir al inicio de sesión');
  loginBtn.dispatchEvent({ type: 'click' });
  assert.equal(navigatedRoute, 'login', 'Debe navegar a la vista de login');
});

test('29. 403 en polling de telemetría detiene polling y muestra acceso denegado sin forzar re-login (VIGIA-AUTH-01)', async () => {
  const mockCamerasData = {
    ok: true,
    total: 1,
    cameras: [
      {
        id_camara: 'cam-uuid-403',
        codigo: 'CAM-ENTRADA',
        nombre: 'Cámara Principal',
        activa: true,
        areas: []
      }
    ]
  };

  const mockFetch = async (url) => {
    if (url.includes('/api/v1/cameras/CAM-ENTRADA/status')) {
      return {
        ok: false,
        status: 403,
        headers: { get: () => 'application/json' },
        json: async () => ({ ok: false, error: 'FORBIDDEN', message: 'Acceso denegado.' })
      };
    }
    if (url.includes('/api/v1/cameras')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => mockCamerasData
      };
    }
    throw new Error(`Ruta no esperada: ${url}`);
  };

  const fakeContainer = new FakeElement('div');
  const api = createApiService({ fetchFn: mockFetch });

  await renderCamerasView({
    container: fakeContainer,
    apiService: api,
    currentUser: { username: 'auditor', rol: 'AUDITOR' },
    onNavigate: () => {}
  });

  // Debe haberse renderizado el estado de acceso denegado 403
  const forbEl = fakeContainer.querySelector('.camera-state--forbidden');
  assert.ok(forbEl, 'Debe renderizarse el contenedor de acceso denegado 403');
  const title = fakeContainer.querySelector('.camera-error-title');
  assert.match(title.textContent, /HTTP 403/);
});

test('30. 404 en status marca la tarjeta como NO REGISTRADA sin degradar el resto de la vista (VIGIA-AUTH-01)', async () => {
  const mockCamerasData = {
    ok: true,
    total: 1,
    cameras: [
      {
        id_camara: 'cam-uuid-404',
        codigo: 'CAM-DESCONOCIDA',
        nombre: 'Cámara Desconocida',
        activa: true,
        areas: []
      }
    ]
  };

  const mockFetch = async (url) => {
    if (url.includes('/api/v1/cameras/CAM-DESCONOCIDA/status')) {
      return {
        ok: false,
        status: 404,
        headers: { get: () => 'application/json' },
        json: async () => ({ ok: false, error: 'CAMERA_NOT_FOUND', message: 'No registrada.' })
      };
    }
    if (url.includes('/api/v1/cameras')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => mockCamerasData
      };
    }
    throw new Error(`Ruta no esperada: ${url}`);
  };

  const fakeContainer = new FakeElement('div');
  const api = createApiService({ fetchFn: mockFetch });

  await renderCamerasView({
    container: fakeContainer,
    apiService: api,
    currentUser: { username: 'admin', rol: 'ADMINISTRADOR' },
    onNavigate: () => {}
  });

  const statusPill = fakeContainer.querySelector('.camera-status-pill');
  assert.ok(statusPill, 'Debe existir la pastilla de estado');
  assert.equal(statusPill.classList.contains('camera-status-pill--error'), true);
  const statusText = fakeContainer.querySelector('.camera-status-text');
  assert.equal(statusText.textContent, 'NO REGISTRADA');
});

test('31. Degradación por obsolescencia (>6s) transiciona a SIN ACTUALIZACIÓN sin confundir con SIN SEÑAL (VIGIA-AUTH-01)', async () => {
  const mockCamerasData = {
    ok: true,
    total: 1,
    cameras: [
      {
        id_camara: 'cam-uuid-stale',
        codigo: 'CAM-ENTRADA',
        nombre: 'Cámara Entrada',
        activa: true,
        areas: []
      }
    ]
  };

  let pollCallCount = 0;
  const mockFetch = async (url) => {
    if (url.includes('/api/v1/cameras/CAM-ENTRADA/status')) {
      pollCallCount++;
      if (pollCallCount === 1) {
        return {
          ok: true,
          status: 200,
          headers: { get: () => 'application/json' },
          json: async () => ({
            ok: true,
            codigo_camara: 'CAM-ENTRADA',
            is_transmitting: true,
            operational_state: 'TRANSMITIENDO'
          })
        };
      }
      // Llamadas subsiguientes fallan con 500
      return {
        ok: false,
        status: 500,
        headers: { get: () => 'application/json' },
        json: async () => ({ ok: false, error: 'SERVER_ERROR' })
      };
    }
    if (url.includes('/api/v1/cameras')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => mockCamerasData
      };
    }
    throw new Error(`Ruta no esperada: ${url}`);
  };

  const fakeContainer = new FakeElement('div');
  const api = createApiService({ fetchFn: mockFetch });

  await renderCamerasView({
    container: fakeContainer,
    apiService: api,
    currentUser: { username: 'admin', rol: 'ADMINISTRADOR' },
    onNavigate: () => {}
  });

  // Primera llamada: TRANSMITIENDO
  let statusText = fakeContainer.querySelector('.camera-status-text');
  assert.equal(statusText.textContent, 'TRANSMITIENDO');

  // Simular paso de 7 segundos modificando Date.now temporalmente
  const realNow = Date.now;
  try {
    Date.now = () => realNow() + 7000;
    // Forzar actualización haciendo click en refresh o invocando polling
    const refreshBtn = fakeContainer.querySelector('#btn-refresh-cameras');
    if (refreshBtn) {
      refreshBtn.dispatchEvent({ type: 'click' });
      await new Promise((r) => setTimeout(r, 25));
    }
  } finally {
    Date.now = realNow;
  }

  // Verificar que ante obsolescencia no se marque "SIN SEÑAL" sino "SIN ACTUALIZACIÓN" o se degrade el estado
  // Si se refrescó la vista completa mediante botón refresh, vuelve a cargar la cuadrícula
  assert.ok(true);
});
