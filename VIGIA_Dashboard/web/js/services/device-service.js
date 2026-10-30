/**
 * VIGÍA Vision Systems — Servicio de Acceso a Datos de Dispositivos (Sprint 02A)
 *
 * Propósito arquitectónico:
 * - Proveer una interfaz de servicio desacoplada entre las vistas/componentes
 *   y el origen de datos.
 * - En el Sprint 02A devuelve exclusivamente los datos sintéticos DEMO en memoria,
 *   sin consultar PostgreSQL, sin llamar endpoints HTTP y sin persistir en
 *   localStorage/sessionStorage.
 * - En sprints posteriores podrá conectarse a VIGIA_API conservando la misma firma
 *   de métodos para no reconstruir los componentes visuales.
 */

import { DEMO_DEVICES, DEMO_DEVICES_METADATA } from '../data/devices-demo-data.js';

/**
 * Crea una instancia del servicio de dispositivos (actualmente en modo DEMO en memoria).
 */
export function createDeviceService() {
  // Copia efímera en memoria de la sesión de visualización actual (sin persistencia)
  const memoryDevices = DEMO_DEVICES.map((device) => ({ ...device }));

  return Object.freeze({
    /**
     * Retorna metadatos del origen de datos actual (DEMO).
     */
    getMetadata() {
      return DEMO_DEVICES_METADATA;
    },

    /**
     * Obtiene la lista de dispositivos para renderizar en la cuadrícula.
     * @returns {Promise<Array<Object>>}
     */
    async listDevices() {
      return memoryDevices.map((item) => ({ ...item }));
    },

    /**
     * Busca un dispositivo por su identificador en memoria.
     * @param {string} deviceId
     * @returns {Promise<Object | null>}
     */
    async getDeviceById(deviceId) {
      const found = memoryDevices.find((item) => item.id === deviceId);
      return found ? { ...found } : null;
    },

    /**
     * Valida localmente una solicitud provisional de alta en modo DEMO.
     * No guarda en base de datos ni envía peticiones al backend; únicamente
     * retorna una confirmación demostrativa y, opcionalmente, refleja el registro
     * temporal en memoria con el prefijo obligatorio [DEMO].
     *
     * @param {{ nombre: string, tipo: string, estado: string }} payload
     */
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
      const timestamp = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;

      const demoRecord = Object.freeze({
        id: `DEMO-TMP-${String(memoryDevices.length + 1).padStart(3, '0')}`,
        nombre: normalizedName,
        tipo: cleanType,
        estado: statusMap[cleanState] ? cleanState : 'CONECTADO',
        estadoEtiqueta: statusMap[cleanState] || 'Conectado',
        ultimaActividad: `${timestamp} (Provisional DEMO)`,
        ubicacionDemo: 'Registro temporal de demostración (no persistido)'
      });

      memoryDevices.unshift(demoRecord);

      return {
        ok: true,
        persisted: false,
        device: demoRecord,
        message: `Confirmación DEMO: "${demoRecord.nombre}" validado localmente en memoria. No se ha guardado información en el backend ni en PostgreSQL.`
      };
    }
  });
}

