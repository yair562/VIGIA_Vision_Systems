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
 * Construye el panel para Enrolamiento QR de Cámaras Móviles (MOB-QR-01).
 * @param {Object} options
 * @param {Object} options.deviceService
 * @param {() => void} options.onEnrolled
 * @param {() => void} options.onClose
 * @returns {HTMLElement}
 */
function createQrEnrollmentPanel({ deviceService, onEnrolled, onClose }) {
  const panel = document.createElement('section');
  panel.className = 'admin-provisional-panel';
  panel.setAttribute('aria-labelledby', 'qr-enrollment-title');

  const header = document.createElement('div');
  header.className = 'admin-provisional-header';

  const title = document.createElement('h2');
  title.id = 'qr-enrollment-title';
  title.className = 'admin-provisional-title';
  title.textContent = 'Enrolamiento Seguro de Cámara Móvil mediante QR';

  const badge = document.createElement('span');
  badge.className = 'admin-demo-badge';
  badge.style.background = '#2563eb';
  badge.style.color = '#ffffff';
  badge.textContent = 'MOB-QR-01';

  header.appendChild(title);
  header.appendChild(badge);

  const description = document.createElement('p');
  description.style.fontSize = 'var(--font-size-small)';
  description.style.color = 'var(--admin-text-secondary)';
  description.textContent =
    'Selecciona la cámara lógica a la que se asociará el teléfono físico. Al generar el código QR, escanéalo con la cámara del dispositivo móvil para vincularlo y comenzar la transmisión de fotogramas.';

  const form = document.createElement('form');
  form.className = 'admin-provisional-form';
  form.noValidate = true;

  // Cámara lógica
  const camGroup = document.createElement('div');
  camGroup.className = 'admin-form-group';
  const camLabel = document.createElement('label');
  camLabel.className = 'admin-form-label';
  camLabel.htmlFor = 'qr-cam-code';
  camLabel.textContent = 'Cámara Lógica Destino *';
  const camSelect = document.createElement('select');
  camSelect.id = 'qr-cam-code';
  camSelect.className = 'admin-form-select';
  [
    { value: 'CAM-ENTRADA', label: 'CAM-ENTRADA — Acceso Principal Norte (Área Entrada)' },
    { value: 'CAM-SALIDA', label: 'CAM-SALIDA — Control de Salida Sur (Área Salida)' }
  ].forEach((opt) => {
    const o = document.createElement('option');
    o.value = opt.value;
    o.textContent = opt.label;
    camSelect.appendChild(o);
  });
  camGroup.appendChild(camLabel);
  camGroup.appendChild(camSelect);

  // TTL
  const ttlGroup = document.createElement('div');
  ttlGroup.className = 'admin-form-group';
  const ttlLabel = document.createElement('label');
  ttlLabel.className = 'admin-form-label';
  ttlLabel.htmlFor = 'qr-ttl-select';
  ttlLabel.textContent = 'Vigencia del Código QR';
  const ttlSelect = document.createElement('select');
  ttlSelect.id = 'qr-ttl-select';
  ttlSelect.className = 'admin-form-select';
  [
    { value: '5', label: '5 minutos' },
    { value: '10', label: '10 minutos (Recomendado)' },
    { value: '15', label: '15 minutos' },
    { value: '30', label: '30 minutos' }
  ].forEach((opt) => {
    const o = document.createElement('option');
    o.value = opt.value;
    o.textContent = opt.label;
    if (opt.value === '10') o.selected = true;
    ttlSelect.appendChild(o);
  });
  ttlGroup.appendChild(ttlLabel);
  ttlGroup.appendChild(ttlSelect);

  // Result container
  const resultContainer = document.createElement('div');
  resultContainer.id = 'qr-result-box';
  resultContainer.style.marginTop = '1rem';
  resultContainer.style.textAlign = 'center';
  resultContainer.hidden = true;

  // Acciones
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
  submitBtn.textContent = 'Generar Código QR';

  actionsDiv.appendChild(cancelBtn);
  actionsDiv.appendChild(submitBtn);

  form.appendChild(camGroup);
  form.appendChild(ttlGroup);
  form.appendChild(actionsDiv);

  const errorBox = document.createElement('div');
  errorBox.className = 'admin-inline-notice admin-inline-notice--warning';
  errorBox.setAttribute('role', 'alert');
  errorBox.hidden = true;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    errorBox.hidden = true;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Generando QR...';

    try {
      const resp = await deviceService.generatePairingQr(camSelect.value, parseInt(ttlSelect.value, 10));
      if (!resp || !resp.ok) {
        throw new Error(resp?.error || 'No se pudo generar el código QR.');
      }

      resultContainer.innerHTML = '';
      resultContainer.hidden = false;

      const imgWrapper = document.createElement('div');
      imgWrapper.style.margin = '1rem auto';
      imgWrapper.style.padding = '1rem';
      imgWrapper.style.background = '#ffffff';
      imgWrapper.style.border = '2px solid var(--admin-border-color, #e2e8f0)';
      imgWrapper.style.borderRadius = '12px';
      imgWrapper.style.display = 'inline-block';

      const qrImg = document.createElement('img');
      qrImg.src = resp.qr_base64_data_url || resp.qr_image_data;
      qrImg.alt = `Código QR para ${resp.codigo_camara}`;
      qrImg.style.width = '240px';
      qrImg.style.height = '240px';
      qrImg.style.display = 'block';

      imgWrapper.appendChild(qrImg);
      resultContainer.appendChild(imgWrapper);

      const targetUrl = resp.enrollment_url || resp.pairing_url || '#';
      const infoBox = document.createElement('div');
      infoBox.style.fontSize = 'var(--font-size-small)';
      infoBox.style.color = 'var(--admin-text-secondary)';
      infoBox.innerHTML = `
        <p><strong>Cámara:</strong> ${resp.codigo_camara}</p>
        <p><strong>Expira:</strong> ${resp.expira_en}</p>
        <p style="margin-top: 0.5rem; word-break: break-all;">
          <strong>Enlace directo para pruebas:</strong><br>
          <a href="${targetUrl}" target="_blank" rel="noopener noreferrer" style="color: #2563eb; text-decoration: underline;">
            ${targetUrl}
          </a>
        </p>
      `;
      resultContainer.appendChild(infoBox);

      const refreshBtn = document.createElement('button');
      refreshBtn.type = 'button';
      refreshBtn.className = 'device-action-btn';
      refreshBtn.style.marginTop = '1rem';
      refreshBtn.textContent = 'Actualizar Lista de Dispositivos';
      refreshBtn.addEventListener('click', () => {
        if (typeof onEnrolled === 'function') onEnrolled();
      });
      resultContainer.appendChild(refreshBtn);

      submitBtn.textContent = 'Regenerar Código QR';
      submitBtn.disabled = false;
    } catch (err) {
      errorBox.textContent = err.message || 'Error al solicitar el código QR.';
      errorBox.hidden = false;
      submitBtn.disabled = false;
      submitBtn.textContent = 'Generar Código QR';
    }
  });

  panel.appendChild(header);
  panel.appendChild(description);
  panel.appendChild(errorBox);
  panel.appendChild(form);
  panel.appendChild(resultContainer);

  return panel;
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
  currentUser = null,
  onNavigate,
  onLogout,
  onExitDemo
}) {
  if (!container || !deviceService) return;

  container.innerHTML = '';

  const shell = document.createElement('div');
  shell.className = 'admin-shell';

  // 1. Barra de navegación horizontal superior reutilizable
  const navActiveId = activeRoute === 'camera-viewer' ? 'cameras' : activeRoute;
  const navbar = renderAdminNavbar({
    activeSectionId: navActiveId,
    currentUser,
    onNavigate: (targetRoute) => {
      if (typeof onNavigate === 'function') {
        onNavigate(targetRoute);
      }
    },
    onLogout
  });
  shell.appendChild(navbar);

  // 2. Tarjeta interna blanca (.admin-content-card)
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

  const isReal = typeof deviceService.isRealBackend === 'function' && deviceService.isRealBackend();

  const demoStatusRow = document.createElement('div');
  demoStatusRow.className = 'admin-demo-status-row';

  const demoTag = document.createElement('span');
  demoTag.className = 'admin-demo-badge';
  if (isReal) {
    demoTag.style.background = '#059669';
    demoTag.style.color = '#ffffff';
    demoTag.textContent = 'CONECTADO — PostgreSQL (VIGIA_API)';
  } else {
    demoTag.textContent = 'MODO DEMO — Datos sintéticos de demostración (Sin conexión a backend)';
  }

  const exitDemoBtn = document.createElement('button');
  exitDemoBtn.type = 'button';
  exitDemoBtn.id = 'btn-exit-demo';
  exitDemoBtn.className = 'admin-exit-demo-btn';
  exitDemoBtn.textContent = 'Salir de DEMO / Ir al Inicio de Sesión';
  if (isReal) {
    exitDemoBtn.hidden = true;
  }
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
      try {
        const devices = await deviceService.listDevices();
        tableSlot.innerHTML = '';
        const tableEl = renderDevicesTable({
          devices,
          onDeviceAction: async (device, actionType) => {
            if (actionType === 'revocar') {
              const confirmed = window.confirm(
                `¿Confirmas la revocación del dispositivo "${device.nombre}" asociado a "${device.camara_asociada || device.ubicacionDemo}"?\nEsta acción es irreversible y bloqueará la transmisión de fotogramas.`
              );
              if (!confirmed) return;
              try {
                const res = await deviceService.revokeDevice(device.id_credencial);
                if (res && res.ok) {
                  showInlineNotice(`Dispositivo "${device.nombre}" revocado exitosamente.`, 'info');
                } else {
                  showInlineNotice(res?.error || 'No se pudo revocar el dispositivo.', 'warning');
                }
                await refreshTable();
              } catch (err) {
                showInlineNotice(err.message || 'Error al revocar el dispositivo.', 'warning');
              }
            } else {
              showInlineNotice(
                `Dispositivo "${device.nombre}" (${device.id}): Tipo "${device.tipo}", Estado "${device.estadoEtiqueta || device.estado}", Ubicación "${device.ubicacionDemo || device.camara_asociada}".`,
                'info'
              );
            }
          }
        });
        tableSlot.appendChild(tableEl);
      } catch (err) {
        tableSlot.innerHTML = '';
        const errNotice = document.createElement('div');
        errNotice.className = 'admin-inline-notice admin-inline-notice--warning';
        errNotice.textContent = err.message || 'Error al consultar dispositivos desde el servidor.';
        tableSlot.appendChild(errNotice);
      }
    }

    await refreshTable();

    shell.appendChild(contentCard);

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
    addDeviceBtn.textContent = isReal ? 'Enrolar Cámara Móvil (QR)' : 'Agregar Dispositivos';
    addDeviceBtn.addEventListener('click', () => {
      if (provisionalContainer.children.length > 0) {
        provisionalContainer.innerHTML = '';
        return;
      }
      if (isReal) {
        const qrPanel = createQrEnrollmentPanel({
          deviceService,
          onEnrolled: async () => {
            await refreshTable();
            showInlineNotice('Lista de dispositivos actualizada.', 'info');
          },
          onClose: () => {
            provisionalContainer.innerHTML = '';
          }
        });
        provisionalContainer.appendChild(qrPanel);
      } else {
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
      }
    });

    primaryActions.appendChild(cameraViewerBtn);
    primaryActions.appendChild(addDeviceBtn);
    shell.appendChild(primaryActions);
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
    shell.appendChild(contentCard);
  }

  // 3.7. Pie de página dentro del contenedor principal
  const footer = document.createElement('footer');
  footer.className = 'admin-footer';
  footer.textContent = 'VIGIA Vision Systems';
  shell.appendChild(footer);

  container.appendChild(shell);
}

