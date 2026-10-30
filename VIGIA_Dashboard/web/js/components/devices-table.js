/**
 * VIGÍA Vision Systems — Componente Reutilizable de Cuadrícula de Dispositivos (Sprint 02A)
 *
 * Estructura visual de cinco columnas:
 * 1. Nombre del Dispositivo
 * 2. Tipo
 * 3. Estado (Conectado, Desconectado, En mantenimiento)
 * 4. Última Actividad
 * 5. Acciones (Operaciones disponibles sobre el registro — provisional DEMO)
 *
 * No contiene lógica de acceso a PostgreSQL ni llamadas HTTP directas.
 */

const COLUMNS = Object.freeze([
  Object.freeze({ key: 'nombre', label: 'Nombre del Dispositivo' }),
  Object.freeze({ key: 'tipo', label: 'Tipo' }),
  Object.freeze({ key: 'estado', label: 'Estado' }),
  Object.freeze({ key: 'ultimaActividad', label: 'Última Actividad' }),
  Object.freeze({ key: 'acciones', label: 'Acciones' })
]);

/**
 * Determina la clase modificadora CSS para el estado del dispositivo.
 * @param {string} estadoCode
 * @returns {string}
 */
function resolveStatusModifier(estadoCode) {
  switch (estadoCode) {
    case 'CONECTADO':
      return 'device-status-pill--online';
    case 'DESCONECTADO':
      return 'device-status-pill--offline';
    case 'EN_MANTENIMIENTO':
    default:
      return 'device-status-pill--maintenance';
  }
}

/**
 * Construye una celda con el bloque rectangular gris interno (.device-cell-box).
 * @param {string} columnLabel
 * @param {Node | HTMLElement} contentNode
 * @returns {HTMLTableCellElement}
 */
function createDataCell(columnLabel, contentNode) {
  const td = document.createElement('td');
  const box = document.createElement('div');
  box.className = 'device-cell-box';
  box.setAttribute('data-label', columnLabel);
  box.appendChild(contentNode);
  td.appendChild(box);
  return td;
}

/**
 * Renderiza la tabla/cuadrícula de 5 columnas para la lista de dispositivos.
 *
 * @param {Object} options
 * @param {Array<Object>} options.devices - Lista de dispositivos a presentar
 * @param {(device: Object, actionType: string) => void} options.onDeviceAction - Callback de acción por fila
 * @returns {HTMLElement}
 */
export function renderDevicesTable({ devices = [], onDeviceAction } = {}) {
  const wrapper = document.createElement('div');
  wrapper.className = 'devices-grid-wrapper';

  const table = document.createElement('table');
  table.className = 'devices-table';
  table.setAttribute('aria-label', 'Tabla de dispositivos registrados (Modo DEMO)');

  // Encabezados de las 5 columnas
  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');

  COLUMNS.forEach((col) => {
    const th = document.createElement('th');
    th.scope = 'col';
    th.textContent = col.label;
    headerRow.appendChild(th);
  });

  thead.appendChild(headerRow);
  table.appendChild(thead);

  // Cuerpo de registros
  const tbody = document.createElement('tbody');

  devices.forEach((device) => {
    const tr = document.createElement('tr');
    tr.dataset.deviceId = device.id;

    // 1. Nombre del Dispositivo
    const nameContainer = document.createElement('div');
    const nameStrong = document.createElement('span');
    nameStrong.className = 'device-name-text';
    nameStrong.textContent = device.nombre;
    const codeSub = document.createElement('span');
    codeSub.className = 'device-code-sub';
    codeSub.textContent = `${device.id} · ${device.ubicacionDemo || 'Ubicación DEMO'}`;
    nameContainer.appendChild(nameStrong);
    nameContainer.appendChild(codeSub);
    tr.appendChild(createDataCell(COLUMNS[0].label, nameContainer));

    // 2. Tipo
    const typeSpan = document.createElement('span');
    typeSpan.textContent = device.tipo;
    tr.appendChild(createDataCell(COLUMNS[1].label, typeSpan));

    // 3. Estado
    const statusPill = document.createElement('span');
    statusPill.className = `device-status-pill ${resolveStatusModifier(device.estado)}`;
    const dot = document.createElement('span');
    dot.className = 'device-status-dot';
    dot.setAttribute('aria-hidden', 'true');
    const statusText = document.createElement('span');
    statusText.textContent = device.estadoEtiqueta;
    statusPill.appendChild(dot);
    statusPill.appendChild(statusText);
    tr.appendChild(createDataCell(COLUMNS[2].label, statusPill));

    // 4. Última Actividad
    const activityTime = document.createElement('time');
    activityTime.textContent = device.ultimaActividad;
    tr.appendChild(createDataCell(COLUMNS[3].label, activityTime));

    // 5. Acciones (Provisional DEMO claramente identificado)
    const actionsGroup = document.createElement('div');
    actionsGroup.className = 'device-row-actions';

    const detailBtn = document.createElement('button');
    detailBtn.type = 'button';
    detailBtn.className = 'device-action-btn';
    detailBtn.textContent = 'Detalle (Provisional)';
    detailBtn.setAttribute('aria-label', `Ver detalle provisional de ${device.nombre}`);
    detailBtn.addEventListener('click', () => {
      if (typeof onDeviceAction === 'function') {
        onDeviceAction(device, 'detalle-provisional');
      }
    });

    actionsGroup.appendChild(detailBtn);
    tr.appendChild(createDataCell(COLUMNS[4].label, actionsGroup));

    tbody.appendChild(tr);
  });

  table.appendChild(tbody);
  wrapper.appendChild(table);

  return wrapper;
}

