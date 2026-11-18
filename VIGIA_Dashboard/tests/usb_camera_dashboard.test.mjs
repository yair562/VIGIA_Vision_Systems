/**
 * VIGÍA Vision Systems — Pruebas de Integración Dashboard USB (VIGIA-USB-04)
 *
 * Cobertura de las 10 pruebas requeridas por la especificación:
 * 1. Detección USB desde Dashboard (listUsbCameras).
 * 2. Enrolamiento USB exitoso (enrollUsbCamera).
 * 3. Conflicto HTTP 409 (ACTIVE_CREDENTIAL_CONFLICT y USB_DEVICE_IN_USE).
 * 4. Sustitución confirmada (confirm_replace: true).
 * 5. Revocación USB (revokeDevice con detención de worker y liberación de hardware).
 * 6. Tabla unificada con dispositivos móviles y USB (clasificación con metadatos reales).
 * 7. Visualización MJPEG unificada (reutilización de cameras-view).
 * 8. Manejo de errores de API (401 AuthError, 403 ForbiddenError, 500 ServerError).
 * 9. Compatibilidad con enrolamiento QR (MOB-QR-01 intacto).
 * 10. Compatibilidad con la interfaz existente y navegación administrativa.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import {
  createApiService,
  ApiError,
  AuthError,
  ForbiddenError,
  ServerError
} from '../web/js/services/api-service.js';
import { createDeviceService } from '../web/js/services/device-service.js';
import { renderDevicesTable } from '../web/js/components/devices-table.js';
import { renderAdminDevicesView } from '../web/js/views/devices-view.js';
import { renderCamerasView } from '../web/js/views/cameras-view.js';

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
    if (this._textContent) return this._textContent;
    return this.children.map((c) => (c.textContent || '')).join('');
  }
  set textContent(v) {
    this._textContent = String(v);
    this.children = [];
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
  location: { hash: '#devices', search: '', pathname: '/app' },
  history: { replaceState: () => {} },
  confirm: () => true,
  addEventListener: () => {},
  removeEventListener: () => {}
};

test('1. Detección USB desde Dashboard (listUsbCameras)', async () => {
  const calls = [];
  const mockFetch = async (url, options) => {
    calls.push({ url, options });
    if (url.includes('/api/v1/devices/usb-cameras')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({
          ok: true,
          cameras: [
            {
              device_index: 0,
              name: 'Cámara USB Local 0 (Webcam)',
              resolution: '640x480',
              backend: 'DSHOW',
              available: true,
              in_use_by_camera: null
            },
            {
              device_index: 1,
              name: 'Cámara USB Local 1',
              resolution: '1280x720',
              backend: 'MSMF',
              available: false,
              in_use_by_camera: 'CAM-ENTRADA'
            }
          ],
          total: 2
        })
      };
    }
    return { ok: false, status: 404, headers: { get: () => 'application/json' }, json: async () => ({}) };
  };

  const apiService = createApiService({ fetchFn: mockFetch });
  const deviceService = createDeviceService({ apiService });

  const cameras = await deviceService.listUsbCameras(4);
  assert.equal(cameras.length, 2);
  assert.equal(cameras[0].device_index, 0);
  assert.equal(cameras[0].available, true);
  assert.equal(cameras[1].in_use_by_camera, 'CAM-ENTRADA');
  assert.equal(calls[0].options.method, 'GET');
  assert.equal(calls[0].options.credentials, 'include');
  assert.ok(calls[0].url.includes('/devices/usb-cameras?max_index=4'));
});

test('2. Enrolamiento USB exitoso (enrollUsbCamera)', async () => {
  const calls = [];
  const mockFetch = async (url, options) => {
    calls.push({ url, options });
    if (url.includes('/api/v1/devices/usb/enroll')) {
      return {
        ok: true,
        status: 201,
        headers: { get: () => 'application/json' },
        json: async () => ({
          ok: true,
          codigo_camara: 'CAM-SALIDA',
          device_index: 0,
          device_name: 'Webcam Carril Salida',
          id_credencial: 'cred-usb-1234',
          backend: 'DSHOW',
          worker_started: true,
          replaced_previous: false
        })
      };
    }
    return { ok: false, status: 404, headers: { get: () => 'application/json' }, json: async () => ({}) };
  };

  const apiService = createApiService({ fetchFn: mockFetch });
  const deviceService = createDeviceService({ apiService });

  const result = await deviceService.enrollUsbCamera({
    codigoCamara: 'CAM-SALIDA',
    deviceIndex: 0,
    deviceName: 'Webcam Carril Salida',
    confirmReplace: false
  });

  assert.equal(result.ok, true);
  assert.equal(result.id_credencial, 'cred-usb-1234');
  assert.equal(result.worker_started, true);
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(calls[0].options.credentials, 'include');
  const body = JSON.parse(calls[0].options.body);
  assert.equal(body.codigo_camara, 'CAM-SALIDA');
  assert.equal(body.device_index, 0);
  assert.equal(body.confirm_replace, false);
});

test('3. Conflicto HTTP 409 (ACTIVE_CREDENTIAL_CONFLICT y USB_DEVICE_IN_USE)', async () => {
  // Simular 409 por conflicto de credencial activa
  const mock409Conflict = async (url, options) => ({
    ok: false,
    status: 409,
    headers: { get: () => 'application/json' },
    json: async () => ({
      ok: false,
      error: 'ACTIVE_CREDENTIAL_CONFLICT',
      message: "La cámara 'CAM-SALIDA' ya tiene un dispositivo activo ('Pixel 8'). Confirme con confirm_replace=true.",
      existing_device: {
        id_credencial: 'cred-prev-1',
        nombre_dispositivo: 'Pixel 8'
      }
    })
  });

  const apiConflict = createApiService({ fetchFn: mock409Conflict });
  const devConflict = createDeviceService({ apiService: apiConflict });

  await assert.rejects(
    async () => devConflict.enrollUsbCamera({ codigoCamara: 'CAM-SALIDA', deviceIndex: 0 }),
    (err) => {
      assert.equal(err instanceof ApiError, true);
      assert.equal(err.status, 409);
      assert.equal(err.code, 'ACTIVE_CREDENTIAL_CONFLICT');
      assert.equal(err.data?.existing_device?.nombre_dispositivo, 'Pixel 8');
      return true;
    }
  );

  // Simular 409 por dispositivo USB en uso por otro carril
  const mock409InUse = async () => ({
    ok: false,
    status: 409,
    headers: { get: () => 'application/json' },
    json: async () => ({
      ok: false,
      error: 'USB_DEVICE_IN_USE',
      message: "El dispositivo USB 0 ya se encuentra en uso por la cámara 'CAM-ENTRADA'.",
      in_use_by_camera: 'CAM-ENTRADA'
    })
  });

  const apiInUse = createApiService({ fetchFn: mock409InUse });
  const devInUse = createDeviceService({ apiService: apiInUse });

  await assert.rejects(
    async () => devInUse.enrollUsbCamera({ codigoCamara: 'CAM-SALIDA', deviceIndex: 0 }),
    (err) => {
      assert.equal(err.status, 409);
      assert.equal(err.code, 'USB_DEVICE_IN_USE');
      assert.equal(err.data?.in_use_by_camera, 'CAM-ENTRADA');
      return true;
    }
  );
});

test('4. Sustitución confirmada (confirm_replace: true)', async () => {
  const calls = [];
  const mockFetch = async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true,
      status: 201,
      headers: { get: () => 'application/json' },
      json: async () => ({
        ok: true,
        codigo_camara: 'CAM-SALIDA',
        device_index: 0,
        replaced_previous: true
      })
    };
  };

  const apiService = createApiService({ fetchFn: mockFetch });
  const deviceService = createDeviceService({ apiService });

  const res = await deviceService.enrollUsbCamera({
    codigoCamara: 'CAM-SALIDA',
    deviceIndex: 0,
    deviceName: 'Webcam Nueva',
    confirmReplace: true
  });

  assert.equal(res.ok, true);
  assert.equal(res.replaced_previous, true);
  const parsed = JSON.parse(calls[0].options.body);
  assert.equal(parsed.confirm_replace, true);
});

test('5. Revocación USB (revokeDevice con detención de worker y liberación de hardware)', async () => {
  const calls = [];
  const mockFetch = async (url, options) => {
    calls.push({ url, options });
    if (url.includes('/api/v1/devices/cred-usb-99/revoke')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({
          ok: true,
          message: 'Credencial de dispositivo revocada exitosamente.'
        })
      };
    }
    return { ok: false, status: 404, headers: { get: () => 'application/json' }, json: async () => ({}) };
  };

  const apiService = createApiService({ fetchFn: mockFetch });
  const deviceService = createDeviceService({ apiService });

  const revRes = await deviceService.revokeDevice('cred-usb-99', 'Revocación USB desde Dashboard');
  assert.equal(revRes.ok, true);
  assert.equal(calls[0].options.method, 'POST');
  assert.ok(calls[0].url.endsWith('/devices/cred-usb-99/revoke'));
  const body = JSON.parse(calls[0].options.body);
  assert.equal(body.motivo, 'Revocación USB desde Dashboard');
});

test('6. Tabla unificada con dispositivos móviles y USB (clasificación con metadatos reales)', async () => {
  const mockDevicesResponse = {
    ok: true,
    devices: [
      {
        id_credencial: 'cred-movil-1',
        id_camara: 'cam-uuid-1',
        codigo_camara: 'CAM-ENTRADA',
        nombre_dispositivo: 'Pixel 8 Pro',
        dispositivo_info: {
          tipo: 'MOVIL',
          modelo: 'Pixel 8'
        },
        activado_en: '2026-11-10T10:00:00Z',
        activa: true,
        ultima_actividad: '2026-11-10T10:30:00Z'
      },
      {
        id_credencial: 'cred-usb-1',
        id_camara: 'cam-uuid-2',
        codigo_camara: 'CAM-SALIDA',
        nombre_dispositivo: 'Webcam HD Pro',
        dispositivo_info: {
          modo: 'pull_usb',
          tipo: 'USB_LOCAL',
          device_index: 0,
          backend: 'DSHOW',
          uri_stream: 'usb://0'
        },
        activado_en: '2026-11-10T11:00:00Z',
        activa: true,
        ultima_actividad: '2026-11-10T11:15:00Z'
      }
    ],
    total: 2
  };

  const mockFetch = async () => ({
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => mockDevicesResponse
  });

  const apiService = createApiService({ fetchFn: mockFetch });
  const deviceService = createDeviceService({ apiService });

  const devices = await deviceService.listDevices();
  assert.equal(devices.length, 2);

  // Verificación dispositivo móvil
  assert.equal(devices[0].nombre, 'Pixel 8 Pro');
  assert.equal(devices[0].tipo, 'Cámara Móvil (Teléfono)');
  assert.equal(devices[0].isUsb, false);
  assert.equal(devices[0].activa, true);

  // Verificación dispositivo USB
  assert.equal(devices[1].nombre, 'Webcam HD Pro');
  assert.equal(devices[1].tipo, 'Cámara USB (Local)');
  assert.equal(devices[1].isUsb, true);
  assert.equal(devices[1].deviceIndex, 0);
  assert.equal(devices[1].backend, 'DSHOW');
  assert.equal(devices[1].activa, true);

  // Renderizar la tabla unificada
  const tableEl = renderDevicesTable({ devices });
  const rows = tableEl.querySelectorAll('tr');
  // Header row + 2 data rows = 3 rows
  assert.equal(rows.length, 3);

  // Fila móvil
  const mobileRow = rows[1];
  assert.ok(mobileRow.textContent.includes('Pixel 8 Pro'));
  assert.ok(mobileRow.textContent.includes('Cámara Móvil (Teléfono)'));

  // Fila USB
  const usbRow = rows[2];
  assert.ok(usbRow.textContent.includes('Webcam HD Pro'));
  assert.ok(usbRow.textContent.includes('Cámara USB (Local)'));
  assert.ok(usbRow.textContent.includes('DSHOW'));
});

test('7. Visualización MJPEG unificada (reutilización de cameras-view)', async () => {
  const calls = [];
  const mockFetch = async (url) => {
    calls.push(url);
    if (url.includes('/api/v1/cameras')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({
          ok: true,
          cameras: [
            {
              id_camara: 'uuid-1',
              codigo: 'CAM-ENTRADA',
              nombre: 'Cámara Carril Entrada',
              activa: true,
              areas: []
            },
            {
              id_camara: 'uuid-2',
              codigo: 'CAM-SALIDA',
              nombre: 'Cámara Carril Salida (USB)',
              activa: true,
              areas: []
            }
          ]
        })
      };
    }
    return { ok: false, status: 404, headers: { get: () => 'application/json' }, json: async () => ({}) };
  };

  const apiService = createApiService({ fetchFn: mockFetch });
  const container = fakeDocument.createElement('div');

  await renderCamerasView({
    container,
    apiService,
    currentUser: { username: 'admin', rol: 'ADMINISTRADOR' },
    onNavigate: () => {}
  });

  // Ambas cámaras lógicas deben renderizarse en el visor
  assert.ok(calls.some((u) => u.includes('/api/v1/cameras')));
  const cards = container.querySelectorAll('.camera-card');
  assert.equal(cards.length, 2);
});

test('8. Manejo de errores de API (401, 403, 500)', async () => {
  const createMockErrorApi = (status, error, message) =>
    createApiService({
      fetchFn: async () => ({
        ok: false,
        status,
        headers: { get: () => 'application/json' },
        json: async () => ({ ok: false, error, message })
      })
    });

  // 401
  const dev401 = createDeviceService({ apiService: createMockErrorApi(401, 'UNAUTHORIZED', 'No autenticado') });
  await assert.rejects(
    async () => dev401.listUsbCameras(),
    (err) => err instanceof AuthError && err.status === 401
  );

  // 403
  const dev403 = createDeviceService({ apiService: createMockErrorApi(403, 'FORBIDDEN', 'Requiere ADMINISTRADOR') });
  await assert.rejects(
    async () => dev403.enrollUsbCamera({ codigoCamara: 'CAM-SALIDA', deviceIndex: 0 }),
    (err) => err instanceof ForbiddenError && err.status === 403
  );

  // 500
  const dev500 = createDeviceService({ apiService: createMockErrorApi(500, 'USB_PROBE_FAILED', 'Fallo de hardware') });
  await assert.rejects(
    async () => dev500.listUsbCameras(),
    (err) => err instanceof ServerError && err.status === 500
  );
});

test('9. Compatibilidad con enrolamiento QR (MOB-QR-01 intacto)', async () => {
  const calls = [];
  const mockFetch = async (url, options) => {
    calls.push({ url, options });
    if (url.includes('/api/v1/devices/pairing-qr')) {
      return {
        ok: true,
        status: 201,
        headers: { get: () => 'application/json' },
        json: async () => ({
          ok: true,
          claim_token: 'vigia_claim_token_999',
          codigo_camara: 'CAM-ENTRADA',
          expira_en: '2026-11-13T10:00:00Z',
          qr_image_data: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
        })
      };
    }
    if (url.includes('/api/v1/devices')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({ ok: true, devices: [], total: 0 })
      };
    }
    return { ok: false, status: 404, headers: { get: () => 'application/json' }, json: async () => ({}) };
  };

  const apiService = createApiService({ fetchFn: mockFetch });
  const deviceService = createDeviceService({ apiService });

  const qrRes = await deviceService.generatePairingQr('CAM-ENTRADA', 15);
  assert.equal(qrRes.ok, true);
  assert.equal(qrRes.claim_token, 'vigia_claim_token_999');
  assert.equal(qrRes.codigo_camara, 'CAM-ENTRADA');
  const body = JSON.parse(calls[0].options.body);
  assert.equal(body.codigo_camara, 'CAM-ENTRADA');
  assert.equal(body.ttl_minutes, 15);
});

test('10. Compatibilidad con la interfaz existente y navegación administrativa', async () => {
  const mockFetch = async (url) => {
    if (url.includes('/api/v1/devices/usb-cameras')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({
          ok: true,
          cameras: [
            { device_index: 0, name: 'Webcam Integrada', resolution: '640x480', backend: 'DSHOW', available: true }
          ]
        })
      };
    }
    if (url.includes('/api/v1/devices')) {
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({ ok: true, devices: [], total: 0 })
      };
    }
    return { ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => ({}) };
  };

  const apiService = createApiService({ fetchFn: mockFetch });
  const deviceService = createDeviceService({ apiService });
  const container = fakeDocument.createElement('div');

  await renderAdminDevicesView({
    container,
    deviceService,
    activeRoute: 'devices',
    currentUser: { username: 'admin', rol: 'ADMINISTRADOR' },
    onNavigate: () => {}
  });

  // 1. Botones principales presentes
  const cameraViewerBtn = container.querySelector('#btn-camera-viewer');
  const addDeviceBtn = container.querySelector('#btn-add-device');
  const enrollUsbBtn = container.querySelector('#btn-enroll-usb');

  assert.ok(cameraViewerBtn, 'Botón de visualización de cámaras presente');
  assert.ok(addDeviceBtn, 'Botón de enrolamiento QR móvil presente');
  assert.ok(enrollUsbBtn, 'Botón de enrolamiento USB presente');
  assert.equal(enrollUsbBtn.textContent, 'Enrolar Cámara USB');

  // 2. Abrir panel USB al hacer click
  enrollUsbBtn.dispatchEvent({ type: 'click' });
  const usbPanel = container.querySelector('#usb-enrollment-title');
  assert.ok(usbPanel, 'El panel de enrolamiento USB se montó correctamente');

  // 3. Elementos obligatorios del formulario USB
  const usbSelect = container.querySelector('#usb-device-select');
  const camSelect = container.querySelector('#usb-cam-code');
  const nameInput = container.querySelector('#usb-device-name');
  const submitUsbBtn = container.querySelector('#btn-submit-usb-enroll');

  assert.ok(usbSelect, 'Selector de dispositivo USB presente');
  assert.ok(camSelect, 'Selector de carril lógico destino presente');
  assert.ok(nameInput, 'Campo de nombre descriptivo presente');
  assert.ok(submitUsbBtn, 'Botón de conectar y activar USB presente');

  // 4. Cerrar panel USB con segundo click (toggle)
  enrollUsbBtn.dispatchEvent({ type: 'click' });
  const closedPanel = container.querySelector('#usb-enrollment-title');
  assert.equal(closedPanel, null, 'El panel de enrolamiento USB se cerró en toggle');
});
