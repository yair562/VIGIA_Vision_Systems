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
     */
    async listDevices() {
      if (apiService) {
        const resp = await apiService.get('/api/v1/devices');
        if (resp && resp.ok && Array.isArray(resp.devices)) {
          return resp.devices.map((d) => ({
            id: d.id_credencial,
            id_credencial: d.id_credencial,
            id_camara: d.id_camara,
            nombre: d.nombre_dispositivo,
            tipo: 'Cámara Móvil (Teléfono)',
            camara_asociada: d.codigo_camara,
            estado: d.activa ? 'CONECTADO' : 'DESCONECTADO',
            estadoEtiqueta: d.activa ? 'Conectado' : 'Revocado',
            activa: d.activa,
            fecha_alta: d.activado_en ? d.activado_en.substring(0, 10) : '—',
            ultima_actividad: d.ultima_actividad ? d.ultima_actividad.substring(0, 19).replace('T', ' ') : 'Sin capturas',
            ultimaActividad: d.ultima_actividad ? d.ultima_actividad.substring(0, 19).replace('T', ' ') : 'Sin capturas',
            ubicacionDemo: d.codigo_camara,
            isRealDevice: true
          }));
        }
        return [];
      }
      return memoryDevices.map((item) => ({ ...item }));
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
