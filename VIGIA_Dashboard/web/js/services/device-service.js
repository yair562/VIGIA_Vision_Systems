/**
 * VIGÍA Vision Systems — Servicio Canónico de Gestión de Dispositivos (MOB-QR-01)
 *
 * Responsabilidades:
 * - Consultar dispositivos físicos autorizados en PostgreSQL mediante VIGIA_API (/api/v1/devices).
 * - Solicitar generación de códigos QR de enrolamiento efímero (/api/v1/devices/pairing-qr).
 * - Revocar credenciales de dispositivos físicos (/api/v1/devices/:id/revoke).
 * - Proporcionar fallback a DEMO exclusivamente cuando VIGIA_ENABLE_FRONTEND_DEMO está activo
 *   o cuando el backend no esté disponible.
 */

import { DEMO_DEVICES, DEMO_DEVICES_METADATA } from '../data/devices-demo-data.js';

export function createDeviceService({ apiService } = {}) {
  const memoryDevices = DEMO_DEVICES.map((device) => ({ ...device }));

  return Object.freeze({
    isRealBackend() {
      return Boolean(apiService);
    },

    getMetadata() {
      return {
        ...DEMO_DEVICES_METADATA,
        fuente: apiService ? 'PostgreSQL (VIGIA_API)' : 'DEMO en memoria',
        isRealBackend: Boolean(apiService)
      };
    },

    /**
     * Lista dispositivos físicos y cámaras asociadas.
     * Consulta PostgreSQL real vía apiService si está disponible.
     * Clasifica fielmente el tipo de dispositivo utilizando los metadatos reales del backend.
     */
    async listDevices() {
      if (apiService) {
        const resp = await apiService.get('/api/v1/devices');
        if (resp && resp.ok && Array.isArray(resp.devices)) {
          return resp.devices.map((d) => {
            const dispInfo = (d.dispositivo_info && typeof d.dispositivo_info === 'object') ? d.dispositivo_info : {};
            const isUsb = Boolean(
              dispInfo.modo === 'pull_usb' ||
              dispInfo.tipo === 'USB_LOCAL' ||
              (dispInfo.uri_stream && String(dispInfo.uri_stream).startsWith('usb://'))
            );
            const tipoLabel = isUsb ? 'Cámara USB (Local)' : 'Cámara Móvil (Teléfono)';
            const fechaActividad = d.ultima_actividad
              ? d.ultima_actividad.substring(0, 19).replace('T', ' ')
              : (d.activa ? 'En transmisión' : 'Sin capturas');

            return {
              id: d.id_credencial,
              id_credencial: d.id_credencial,
              id_camara: d.id_camara,
              nombre: d.nombre_dispositivo,
              tipo: tipoLabel,
              isUsb,
              deviceIndex: dispInfo.device_index ?? null,
              backend: dispInfo.backend || (isUsb ? 'OPENCV' : null),
              camara_asociada: d.codigo_camara,
              estado: d.activa ? 'CONECTADO' : 'DESCONECTADO',
              estadoEtiqueta: d.activa ? 'Conectado' : 'Revocado',
              activa: d.activa,
              fecha_alta: d.activado_en ? d.activado_en.substring(0, 10) : '—',
              ultima_actividad: fechaActividad,
              ultimaActividad: fechaActividad,
              ubicacionDemo: d.codigo_camara,
              isRealDevice: true,
              dispositivo_info: dispInfo
            };
          });
        }
        return [];
      }
      return memoryDevices.map((item) => ({ ...item }));
    },

    /**
     * Consulta las cámaras USB locales detectadas físicamente en el servidor.
     * Endpoint: GET /api/v1/devices/usb-cameras?max_index=:maxIndex
     * @param {number} [maxIndex=4]
     * @returns {Promise<Array<Object>>}
     */
    async listUsbCameras(maxIndex = 4) {
      if (!apiService) {
        throw new Error('Servicio de API no disponible para consultar cámaras USB.');
      }
      const resp = await apiService.get(`/api/v1/devices/usb-cameras?max_index=${encodeURIComponent(maxIndex)}`);
      if (resp && resp.ok && Array.isArray(resp.cameras)) {
        return resp.cameras;
      }
      return [];
    },

    /**
     * Enrola una cámara USB local asignándola a una cámara lógica (carril).
     * Endpoint: POST /api/v1/devices/usb/enroll
     * @param {Object} payload
     * @param {string} payload.codigoCamara - Código del carril (ej. 'CAM-ENTRADA')
     * @param {number|string} payload.deviceIndex - Índice físico de la cámara (ej. 0 o 'usb://0')
     * @param {string} [payload.deviceName] - Nombre descriptivo para el dispositivo
     * @param {boolean} [payload.confirmReplace=false] - Forzar sustitución si ya hay credencial activa
     * @returns {Promise<Object>}
     */
    async enrollUsbCamera({ codigoCamara, deviceIndex, deviceName, confirmReplace = false }) {
      if (!apiService) {
        throw new Error('Servicio de API no disponible para enrolar cámara USB.');
      }
      return await apiService.post('/api/v1/devices/usb/enroll', {
        codigo_camara: codigoCamara,
        device_index: deviceIndex,
        device_name: deviceName,
        confirm_replace: Boolean(confirmReplace)
      });
    },

    /**
     * Solicita al backend la generación de un código QR de enrolamiento.
     */
    async generatePairingQr(codigoCamara, ttlMinutes = 10) {
      if (!apiService) {
        throw new Error('Servicio de API no disponible para generar código QR.');
      }
      return await apiService.post('/api/v1/devices/pairing-qr', {
        codigo_camara: codigoCamara,
        ttl_minutes: ttlMinutes
      });
    },

    /**
     * Revoca un dispositivo físico autorizado.
     */
    async revokeDevice(idCredencial, motivo = 'Revocación desde Dashboard') {
      if (!apiService) {
        throw new Error('Servicio de API no disponible para revocar dispositivo.');
      }
      return await apiService.post(`/api/v1/devices/${idCredencial}/revoke`, { motivo });
    },

    async getDeviceById(deviceId) {
      const devices = await this.listDevices();
      return devices.find((d) => d.id === deviceId) || null;
    },

    async previewAddDeviceDemo(payload) {
      const cleanName = (payload?.nombre || '').trim();
      const cleanType = (payload?.tipo || '').trim();
      const cleanState = (payload?.estado || 'CONECTADO').trim();

      if (!cleanName) {
        throw new Error('Ingresa el nombre del dispositivo para la validación DEMO.');
      }
      if (!cleanType) {
        throw new Error('Selecciona el tipo de dispositivo.');
      }

      const statusMap = {
        CONECTADO: 'Conectado',
        DESCONECTADO: 'Desconectado',
        EN_MANTENIMIENTO: 'En mantenimiento'
      };

      const normalizedName = cleanName.startsWith('[DEMO]')
        ? cleanName
        : `[DEMO] ${cleanName}`;

      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const formattedDate = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;

      const newRecord = {
        id: `demo-${Date.now()}`,
        nombre: normalizedName,
        tipo: cleanType,
        estado: statusMap[cleanState] || cleanState,
        fecha_alta: formattedDate
      };

      memoryDevices.push(newRecord);
      return { ok: true, device: { ...newRecord } };
    }
  });
}
