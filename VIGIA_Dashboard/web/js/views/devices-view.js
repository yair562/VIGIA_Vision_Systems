/**
 * VIGÍA Vision Systems — Vista de Gestión de Dispositivos (Administrador — Sprint 02A)
 *
 * Responsabilidades:
 * - Construir el contenedor principal (.admin-shell), la barra de navegación superior
 *   reutilizable, la tarjeta blanca interna con el título "Gestión de Dispositivos",
 *   la cuadrícula de 5 columnas con datos sintéticos DEMO, las dos acciones principales
 *   ("Visualización de Cámaras" y "Agregar Dispositivos") y el pie de página
 *   "VIGIA Vision Systems".
 * - Mostrar la interfaz provisional DEMO al accionar "Agregar Dispositivos" (con validación
 *   local y confirmación DEMO, sin persistir en backend).
 * - Mostrar un mensaje claro de funcionalidad en desarrollo cuando el usuario selecciona
 *   alguna de las secciones futuras (Cámaras, Alertas, Informes, Perfil o Visualización de Cámaras).
 */

import {
  ADMIN_NAV_ITEMS,
  ADMIN_SPECIAL_ROUTES,
  renderAdminNavbar
} from '../components/admin-navbar.js';
import { renderDevicesTable } from '../components/devices-table.js';

/**
 * Resuelve los metadatos de una sección administrativa por su identificador.
 * @param {string} sectionId
 */
function getSectionInfo(sectionId) {
  const navMatch = ADMIN_NAV_ITEMS.find((item) => item.id === sectionId);
  if (navMatch) return navMatch;
  if (ADMIN_SPECIAL_ROUTES[sectionId]) return ADMIN_SPECIAL_ROUTES[sectionId];
  return ADMIN_NAV_ITEMS[0];
}

/**
 * Construye el panel provisional DEMO para "Agregar Dispositivos".
 * @param {Object} options
 * @param {Object} options.deviceService
 * @param {(result: Object) => void} options.onDeviceAddedDemo
 * @param {() => void} options.onClose
 * @returns {HTMLElement}
 */
function createProvisionalAddDevicePanel({ deviceService, onDeviceAddedDemo, onClose }) {
  const panel = document.createElement('section');
  panel.className = 'admin-provisional-panel';
  panel.setAttribute('aria-labelledby', 'provisional-add-title');

  const header = document.createElement('div');
  header.className = 'admin-provisional-header';

  const title = document.createElement('h2');
  title.id = 'provisional-add-title';
  title.className = 'admin-provisional-title';
  title.textContent = 'Registro Provisional de Dispositivo (Modo DEMO — Sprint 02A)';

  const badge = document.createElement('span');
  badge.className = 'admin-demo-badge';
  badge.textContent = 'Vista provisional: sin persistencia en backend';

  header.appendChild(title);
  header.appendChild(badge);

  const description = document.createElement('p');
  description.style.fontSize = 'var(--font-size-small)';
  description.style.color = 'var(--admin-text-secondary)';
  description.textContent =
    'Este formulario preliminar valida los campos localmente y muestra una confirmación DEMO en memoria. El formulario completo de registro de hardware se implementará en el siguiente sprint.';

  const form = document.createElement('form');
  form.className = 'admin-provisional-form';
  form.noValidate = true;

  // Campo Nombre
  const nameGroup = document.createElement('div');
  nameGroup.className = 'admin-form-group';
  const nameLabel = document.createElement('label');
  nameLabel.className = 'admin-form-label';
  nameLabel.htmlFor = 'demo-device-name';
  nameLabel.textContent = 'Nombre del Dispositivo *';
  const nameInput = document.createElement('input');
  nameInput.type = 'text';
  nameInput.id = 'demo-device-name';
  nameInput.className = 'admin-form-input';
  nameInput.placeholder = 'Ej. Cámara Acceso Oriente';
  nameInput.maxLength = 80;
  nameInput.required = true;
  nameGroup.appendChild(nameLabel);
  nameGroup.appendChild(nameInput);

  // Campo Tipo
  const typeGroup = document.createElement('div');
  typeGroup.className = 'admin-form-group';
  const typeLabel = document.createElement('label');
  typeLabel.className = 'admin-form-label';
  typeLabel.htmlFor = 'demo-device-type';
  typeLabel.textContent = 'Tipo de Dispositivo *';
  const typeSelect = document.createElement('select');
  typeSelect.id = 'demo-device-type';
  typeSelect.className = 'admin-form-select';
  [
    { value: 'Cámara IP LPR', label: 'Cámara IP LPR' },
    { value: 'Cámara IP PTZ', label: 'Cámara IP PTZ' },
    { value: 'Actuador de Barrera (IoT)', label: 'Actuador de Barrera (IoT)' },
    { value: 'Sensor Inductivo', label: 'Sensor Inductivo' },
    { value: 'Reflector Inteligente', label: 'Reflector Inteligente' }
  ].forEach((opt) => {
    const option = document.createElement('option');
    option.value = opt.value;
    option.textContent = opt.label;
    typeSelect.appendChild(option);
  });
  typeGroup.appendChild(typeLabel);
  typeGroup.appendChild(typeSelect);

  // Campo Estado inicial DEMO
  const stateGroup = document.createElement('div');
  stateGroup.className = 'admin-form-group';
  const stateLabel = document.createElement('label');
  stateLabel.className = 'admin-form-label';
  stateLabel.htmlFor = 'demo-device-state';
  stateLabel.textContent = 'Estado DEMO';
  const stateSelect = document.createElement('select');
  stateSelect.id = 'demo-device-state';
  stateSelect.className = 'admin-form-select';
  [
    { value: 'CONECTADO', label: 'Conectado' },
    { value: 'EN_MANTENIMIENTO', label: 'En mantenimiento' },
    { value: 'DESCONECTADO', label: 'Desconectado' }
  ].forEach((opt) => {
    const option = document.createElement('option');
    option.value = opt.value;
    option.textContent = opt.label;
    stateSelect.appendChild(option);
  });
  stateGroup.appendChild(stateLabel);
  stateGroup.appendChild(stateSelect);

  // Botones de acción del panel provisional
  const actionsDiv = document.createElement('div');
  actionsDiv.className = 'admin-provisional-actions';

  const cancelBtn = document.createElement('button');
  cancelBtn.type = 'button';
  cancelBtn.className = 'device-action-btn';
  cancelBtn.textContent = 'Cerrar';
  cancelBtn.addEventListener('click', () => {
    if (typeof onClose === 'function') onClose();
  });

  const submitBtn = document.createElement('button');
  submitBtn.type = 'submit';
  submitBtn.className = 'device-action-btn';
  submitBtn.style.fontWeight = 'var(--font-weight-bold)';
  submitBtn.textContent = 'Validar en Modo DEMO';

  actionsDiv.appendChild(cancelBtn);
  actionsDiv.appendChild(submitBtn);

  form.appendChild(nameGroup);
  form.appendChild(typeGroup);
  form.appendChild(stateGroup);
  form.appendChild(actionsDiv);

  const errorBox = document.createElement('div');
  errorBox.className = 'admin-inline-notice admin-inline-notice--warning';
  errorBox.setAttribute('role', 'alert');
  errorBox.hidden = true;

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    errorBox.hidden = true;
    try {
      const result = await deviceService.previewAddDeviceDemo({
        nombre: nameInput.value,
        tipo: typeSelect.value,
        estado: stateSelect.value
      });
      nameInput.value = '';
      if (typeof onDeviceAddedDemo === 'function') {
        onDeviceAddedDemo(result);
      }
    } catch (err) {
      errorBox.textContent = err.message || 'Verifica los campos obligatorios.';
      errorBox.hidden = false;
      nameInput.focus();
    }
  });

  panel.appendChild(header);
  panel.appendChild(description);
  panel.appendChild(errorBox);
  panel.appendChild(form);

  return panel;
}

/**
 * Renderiza la interfaz administrativa en el contenedor indicado.
 *
 * @param {Object} options
 * @param {HTMLElement} options.container - Contenedor DOM donde montar la vista
 * @param {Object} options.deviceService - Servicio desacoplado de dispositivos
 * @param {string} options.activeRoute - Ruta activa ('devices', 'cameras', 'alerts', 'reports', 'profile', 'camera-viewer')
 * @param {(routeId: string) => void} options.onNavigate - Callback de navegación
 */
export async function renderAdminDevicesView({
  container,
  deviceService,
  activeRoute = 'devices',
  onNavigate,
  onExitDemo
}) {
  if (!container || !deviceService) return;

  container.innerHTML = '';

  const shell = document.createElement('div');
  shell.className = 'admin-shell';

  // 1. Barra de navegación lateral compacta (o barra inferior en móvil)
  const navActiveId = activeRoute === 'camera-viewer' ? 'cameras' : activeRoute;
  const navbar = renderAdminNavbar({
    activeSectionId: navActiveId,
    onNavigate: (targetRoute) => {
      if (typeof onNavigate === 'function') {
        onNavigate(targetRoute);
      }
    }
  });
  shell.appendChild(navbar);

  // 2. Área principal de trabajo flexible (.admin-workspace)
  const workspace = document.createElement('div');
  workspace.className = 'admin-workspace';

  // 2.1. Tarjeta interna blanca (.admin-content-card)
  const contentCard = document.createElement('section');
  contentCard.className = 'admin-content-card';
  contentCard.setAttribute('aria-labelledby', 'admin-main-heading');

  const sectionInfo = getSectionInfo(activeRoute);

  const cardHeader = document.createElement('div');
  cardHeader.className = 'admin-card-header';

  const heading = document.createElement('h1');
  heading.id = 'admin-main-heading';
  heading.className = 'admin-section-title';
  heading.textContent = sectionInfo.title;

  const demoStatusRow = document.createElement('div');
  demoStatusRow.className = 'admin-demo-status-row';

  const demoTag = document.createElement('span');
  demoTag.className = 'admin-demo-badge';
  demoTag.textContent = 'MODO DEMO — Datos sintéticos de demostración (Sin conexión a backend)';

  const exitDemoBtn = document.createElement('button');
  exitDemoBtn.type = 'button';
  exitDemoBtn.id = 'btn-exit-demo';
  exitDemoBtn.className = 'admin-exit-demo-btn';
  exitDemoBtn.textContent = 'Salir de DEMO / Ir al Inicio de Sesión';
  exitDemoBtn.addEventListener('click', () => {
    if (typeof onExitDemo === 'function') {
      onExitDemo();
    } else if (typeof onNavigate === 'function') {
      onNavigate('login');
    }
  });

  demoStatusRow.appendChild(demoTag);
  demoStatusRow.appendChild(exitDemoBtn);

  cardHeader.appendChild(heading);
  cardHeader.appendChild(demoStatusRow);
  contentCard.appendChild(cardHeader);

  // Contenedor de avisos en línea (notificaciones de acciones provisionales)
  const noticeContainer = document.createElement('div');
  noticeContainer.id = 'admin-notice-area';
  contentCard.appendChild(noticeContainer);

  function showInlineNotice(message, variant = 'info') {
    noticeContainer.innerHTML = '';
    const notice = document.createElement('div');
    notice.className =
      variant === 'warning'
        ? 'admin-inline-notice admin-inline-notice--warning'
        : 'admin-inline-notice';
    notice.setAttribute('role', 'status');
    notice.setAttribute('aria-live', 'polite');

    const textSpan = document.createElement('span');
    textSpan.textContent = message;

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'admin-notice-close-btn';
    closeBtn.textContent = 'Cerrar';
    closeBtn.addEventListener('click', () => {
      noticeContainer.innerHTML = '';
    });

    notice.appendChild(textSpan);
    notice.appendChild(closeBtn);
    noticeContainer.appendChild(notice);
  }

  // Si la ruta activa es 'devices', renderizar la cuadrícula completa de 5 columnas y controles
  if (activeRoute === 'devices') {
    const provisionalContainer = document.createElement('div');
    provisionalContainer.id = 'admin-provisional-slot';
    contentCard.appendChild(provisionalContainer);

    const tableSlot = document.createElement('div');
    tableSlot.id = 'admin-devices-table-slot';
    contentCard.appendChild(tableSlot);

    async function refreshTable() {
      const devices = await deviceService.listDevices();
      tableSlot.innerHTML = '';
      const tableEl = renderDevicesTable({
        devices,
        onDeviceAction: (device) => {
          showInlineNotice(
            `Acción provisional DEMO — Dispositivo "${device.nombre}" (${device.id}): Tipo "${device.tipo}", Estado "${device.estadoEtiqueta}", Ubicación "${device.ubicacionDemo}". La edición y diagnóstico real se integrarán en sprints posteriores.`,
            'info'
          );
        }
      });
      tableSlot.appendChild(tableEl);
    }

    await refreshTable();

    workspace.appendChild(contentCard);

    // 3.6. Acciones principales debajo de la tarjeta blanca
    const primaryActions = document.createElement('div');
    primaryActions.className = 'admin-primary-actions';

    const cameraViewerBtn = document.createElement('button');
    cameraViewerBtn.type = 'button';
    cameraViewerBtn.id = 'btn-camera-viewer';
    cameraViewerBtn.className = 'admin-action-pill-btn';
    cameraViewerBtn.textContent = 'Visualización de Cámaras';
    cameraViewerBtn.addEventListener('click', () => {
      if (typeof onNavigate === 'function') {
        onNavigate('camera-viewer');
      }
    });

    const addDeviceBtn = document.createElement('button');
    addDeviceBtn.type = 'button';
    addDeviceBtn.id = 'btn-add-device';
    addDeviceBtn.className = 'admin-action-pill-btn';
    addDeviceBtn.textContent = 'Agregar Dispositivos';
    addDeviceBtn.addEventListener('click', () => {
      if (provisionalContainer.children.length > 0) {
        provisionalContainer.innerHTML = '';
        return;
      }
      const addPanel = createProvisionalAddDevicePanel({
        deviceService,
        onDeviceAddedDemo: async (res) => {
          provisionalContainer.innerHTML = '';
          await refreshTable();
          showInlineNotice(res.message, 'warning');
        },
        onClose: () => {
          provisionalContainer.innerHTML = '';
        }
      });
      provisionalContainer.appendChild(addPanel);
      const firstInput = addPanel.querySelector('#demo-device-name');
      if (firstInput) firstInput.focus();
    });

    primaryActions.appendChild(cameraViewerBtn);
    primaryActions.appendChild(addDeviceBtn);
    workspace.appendChild(primaryActions);
  } else {
    // Secciones contempladas en la navegación pero pendientes para próximos sprints
    const constructionBox = document.createElement('div');
    constructionBox.className = 'admin-under-construction';
    constructionBox.setAttribute('role', 'status');

    const msgTitle = document.createElement('h2');
    msgTitle.className = 'admin-provisional-title';
    msgTitle.textContent = `Sección "${sectionInfo.title}" en desarrollo`;

    const msgText = document.createElement('p');
    msgText.className = 'admin-under-construction-text';
    msgText.textContent =
      'Esta ruta ya se encuentra registrada en el sistema de navegación administrativa, pero su implementación funcional pertenece a un sprint posterior. En el Sprint 02A únicamente se implementa la pantalla Gestión de Dispositivos.';

    const backBtn = document.createElement('button');
    backBtn.type = 'button';
    backBtn.className = 'admin-action-pill-btn';
    backBtn.textContent = 'Volver a Gestión de Dispositivos';
    backBtn.addEventListener('click', () => {
      if (typeof onNavigate === 'function') {
        onNavigate('devices');
      }
    });

    constructionBox.appendChild(msgTitle);
    constructionBox.appendChild(msgText);
    constructionBox.appendChild(backBtn);
    contentCard.appendChild(constructionBox);
    workspace.appendChild(contentCard);
  }

  // 3.7. Pie de página dentro del área de trabajo
  const footer = document.createElement('footer');
  footer.className = 'admin-footer';
  footer.textContent = 'VIGIA Vision Systems';
  workspace.appendChild(footer);

  shell.appendChild(workspace);
  container.appendChild(shell);
}

