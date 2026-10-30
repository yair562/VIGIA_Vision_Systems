/**
 * VIGÍA Vision Systems — Datos Sintéticos de Dispositivos (MODO DEMO — Sprint 02A)
 *
 * IMPORTANTE:
 * - Todos los registros de este módulo son exclusivamente demostrativos (DEMO).
 * - No representan hardware real en operación ni provienen de PostgreSQL.
 * - Se mantienen desacoplados de los componentes visuales para que puedan
 *   sustituirse posteriormente por respuestas de VIGIA_API.
 */

export const DEMO_DEVICES_METADATA = Object.freeze({
  mode: 'DEMO',
  sprint: 'SPRINT_02A',
  persisted: false,
  disclaimer:
    'Datos sintéticos de demostración (DEMO). Sin conexión a PostgreSQL ni persistencia en el backend.'
});

/**
 * Conjunto inicial de dispositivos ficticios (7 registros con variedad de tipos y estados).
 */
export const DEMO_DEVICES = Object.freeze([
  Object.freeze({
    id: 'DEMO-DEV-001',
    nombre: '[DEMO] Cámara Acceso Principal Norte',
    tipo: 'Cámara IP LPR',
    estado: 'CONECTADO',
    estadoEtiqueta: 'Conectado',
    ultimaActividad: '2026-10-30 08:14:22',
    ubicacionDemo: 'Caseta Norte — Carril 1'
  }),
  Object.freeze({
    id: 'DEMO-DEV-002',
    nombre: '[DEMO] Cámara Salida Vehicular Sur',
    tipo: 'Cámara IP LPR',
    estado: 'CONECTADO',
    estadoEtiqueta: 'Conectado',
    ultimaActividad: '2026-10-30 08:14:19',
    ubicacionDemo: 'Caseta Sur — Carril Salida'
  }),
  Object.freeze({
    id: 'DEMO-DEV-003',
    nombre: '[DEMO] Controlador Barrera Vehicular B-01',
    tipo: 'Actuador de Barrera (IoT)',
    estado: 'CONECTADO',
    estadoEtiqueta: 'Conectado',
    ultimaActividad: '2026-10-30 08:12:05',
    ubicacionDemo: 'Caseta Norte — Pluma Principal'
  }),
  Object.freeze({
    id: 'DEMO-DEV-004',
    nombre: '[DEMO] Módulo de Iluminación Auxiliar Nocturna',
    tipo: 'Reflector Inteligente',
    estado: 'EN_MANTENIMIENTO',
    estadoEtiqueta: 'En mantenimiento',
    ultimaActividad: '2026-10-29 22:40:10',
    ubicacionDemo: 'Caseta Norte — Arco Lector'
  }),
  Object.freeze({
    id: 'DEMO-DEV-005',
    nombre: '[DEMO] Sensor de Presencia Vehicular Lazo S-02',
    tipo: 'Sensor Inductivo',
    estado: 'DESCONECTADO',
    estadoEtiqueta: 'Desconectado',
    ultimaActividad: '2026-10-29 19:05:44',
    ubicacionDemo: 'Caseta Sur — Pre-barrera'
  }),
  Object.freeze({
    id: 'DEMO-DEV-006',
    nombre: '[DEMO] Cámara Panorámica Patio de Maniobras',
    tipo: 'Cámara IP PTZ',
    estado: 'CONECTADO',
    estadoEtiqueta: 'Conectado',
    ultimaActividad: '2026-10-30 08:13:51',
    ubicacionDemo: 'Zona Interior — Estacionamiento A'
  }),
  Object.freeze({
    id: 'DEMO-DEV-007',
    nombre: '[DEMO] Unidad de Captura Móvil Auxiliar M-01',
    tipo: 'Terminal Móvil de Ingesta',
    estado: 'EN_MANTENIMIENTO',
    estadoEtiqueta: 'En mantenimiento',
    ultimaActividad: '2026-10-30 07:30:00',
    ubicacionDemo: 'Guardia Ambulante — Acceso 2'
  })
]);

