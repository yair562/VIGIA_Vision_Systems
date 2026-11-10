/**
 * VIGÍA Vision Systems — Vista Canónica de Monitoreo de Cámaras (Fase 3B)
 *
 * Responsabilidades:
 * - Consultar la topología física y lógica de cámaras persistidas mediante GET /api/v1/cameras.
 * - Gestionar deterministamente los 6 estados obligatorios:
 *   1. Cargando (spinner accesible).
 *   2. Datos disponibles (cuadrícula de cámaras y áreas asociadas).
 *   3. Lista vacía (estado vacío profesional sin inventar cámaras).
 *   4. Error de autenticación 401 (solicitud de reautenticación).
 *   5. Acceso denegado 403 (reestricción para roles no autorizados como AUDITOR).
 *   6. Error de red o del servidor (estado recuperable con reintento).
 * - Cumplir con el invariante de seguridad: uri_stream nunca debe requerirse ni mostrarse.
 * - Conservar íntegramente la barra horizontal superior minimalista.
 */

import { renderAdminNavbar } from '../components/admin-navbar.js';
import { AuthError, ForbiddenError, NetworkError, ServerError } from '../services/api-service.js';

const SVG_NS = 'http://www.w3.org/2000/svg';

function createSvgIcon(paths, size = 20) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', String(size));
  svg.setAttribute('height', String(size));
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.85');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');

  paths.forEach((p) => {
    const el = document.createElementNS(SVG_NS, p.tag);
    Object.entries(p.attrs || {}).forEach(([k, v]) => el.setAttribute(k, v));
    svg.appendChild(el);
  });
  return svg;
}

const ICONS = {
  camera: [
    { tag: 'rect', attrs: { x: '2.5', y: '6.5', width: '13.5', height: '11', rx: '2' } },
    { tag: 'path', attrs: { d: 'M16 10.25l5.5-3v9.5l-5.5-3' } },
    { tag: 'circle', attrs: { cx: '9.25', cy: '12', r: '2.25' } }
  ],
  refresh: [
    { tag: 'path', attrs: { d: 'M21.5 2v6h-6M2.5 22v-6h6' } },
    { tag: 'path', attrs: { d: 'M20.5 12A8.5 8.5 0 0 1 5.5 17.5L2.5 16M3.5 12A8.5 8.5 0 0 1 18.5 6.5L21.5 8' } }
  ],
  lock: [
    { tag: 'rect', attrs: { x: '4', y: '11', width: '16', height: '10', rx: '2' } },
    { tag: 'path', attrs: { d: 'M8 11V7a4 4 0 0 1 8 0v4' } }
  ],
  alert: [
    { tag: 'path', attrs: { d: 'M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z' } },
    { tag: 'line', attrs: { x1: '12', y1: '9', x2: '12', y2: '13' } },
    { tag: 'circle', attrs: { cx: '12', cy: '17', r: '0.75' } }
  ],
  shieldForbidden: [
    { tag: 'path', attrs: { d: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z' } },
    { tag: 'line', attrs: { x1: '9.5', y1: '9.5', x2: '14.5', y2: '14.5' } }
  ]
};

/**
 * Renderiza la vista de Monitoreo de Cámaras conectada al backend real.
 * @param {Object} options
 * @param {HTMLElement} options.container
 * @param {Object} options.apiService
 * @param {Object} [options.currentUser]
 * @param {(route: string) => void} options.onNavigate
 * @param {() => void} [options.onLogout]
 */
export async function renderCamerasView({
  container,
  apiService,
  currentUser = null,
  onNavigate,
  onLogout
}) {
  if (!container) return;
  container.innerHTML = '';

  // Registro de recursos activos para desmontaje limpio y protección de lifecycle
  let viewGenerationToken = 0;
  let isViewDestroyed = false;
  let activePollInterval = null;
  let isPollingInProgress = false;
  let activeVisibilityListener = null;
  const cameraCardRefs = new Map();
  const activeStreamImgs = [];

  /**
   * Actualiza las clases contextuales de orientación según las dimensiones intrínsecas del stream (FE-05A).
   * @param {HTMLImageElement} img
   * @param {HTMLElement} mediaBox
   */
  function updateStreamOrientation(img, mediaBox) {
    if (!img || !mediaBox) return;
    const nw = img.naturalWidth;
    const nh = img.naturalHeight;
    if (nw && nh && nw > 0 && nh > 0) {
      if (nh > nw) {
        mediaBox.classList.add('camera-card-media--portrait');
        mediaBox.classList.remove('camera-card-media--landscape');
      } else {
        mediaBox.classList.add('camera-card-media--landscape');
        mediaBox.classList.remove('camera-card-media--portrait');
      }
    }
  }

  function cleanupActiveStreams() {
    viewGenerationToken += 1;
    if (activePollInterval) {
      clearInterval(activePollInterval);
      activePollInterval = null;
    }
    if (activeVisibilityListener && typeof document !== 'undefined' && typeof document.removeEventListener === 'function') {
      document.removeEventListener('visibilitychange', activeVisibilityListener);
      activeVisibilityListener = null;
    }
    isPollingInProgress = false;
    for (const refs of cameraCardRefs.values()) {
      if (refs.reconnectTimeoutId) {
        clearTimeout(refs.reconnectTimeoutId);
        refs.reconnectTimeoutId = null;
      }
    }
    cameraCardRefs.clear();
    while (activeStreamImgs.length > 0) {
      const img = activeStreamImgs.pop();
      try {
        img.onerror = null;
        img.onload = null;
        if (typeof img.removeAttribute === 'function') {
          img.removeAttribute('src');
        } else {
          img.src = '';
        }
      } catch (_) {}
    }
  }

  // Interceptar navegación para desmontaje limpio
  const originalOnNavigate = onNavigate;
  const wrappedOnNavigate = (route) => {
    isViewDestroyed = true;
    cleanupActiveStreams();
    if (typeof originalOnNavigate === 'function') {
      originalOnNavigate(route);
    }
  };
  onNavigate = wrappedOnNavigate;

  const shell = document.createElement('div');
  shell.className = 'admin-shell';

  // 1. Barra de navegación horizontal superior aprobada
  const navbar = renderAdminNavbar({
    activeSectionId: 'cameras',
    currentUser,
    onNavigate: wrappedOnNavigate,
    onLogout
  });
  shell.appendChild(navbar);

  // 2. Tarjeta blanca principal (.admin-content-card)
  const contentCard = document.createElement('section');
  contentCard.className = 'admin-content-card';
  contentCard.setAttribute('aria-labelledby', 'cameras-heading');

  const cardHeader = document.createElement('div');
  cardHeader.className = 'admin-card-header';

  const headingWrap = document.createElement('div');
  headingWrap.style.display = 'flex';
  headingWrap.style.alignItems = 'center';
  headingWrap.style.gap = '0.75rem';

  const heading = document.createElement('h1');
  heading.id = 'cameras-heading';
  heading.className = 'admin-section-title';
  heading.textContent = 'Monitoreo de Cámaras';

  const sourceBadge = document.createElement('span');
  sourceBadge.className = 'admin-live-badge';
  sourceBadge.textContent = 'PostgreSQL 16 — En Vivo';

  headingWrap.appendChild(heading);
  headingWrap.appendChild(sourceBadge);

  const headerActions = document.createElement('div');
  headerActions.style.display = 'flex';
  headerActions.style.alignItems = 'center';
  headerActions.style.gap = '0.5rem';

  const refreshBtn = document.createElement('button');
  refreshBtn.type = 'button';
  refreshBtn.id = 'btn-refresh-cameras';
  refreshBtn.className = 'admin-action-pill-btn';
  refreshBtn.setAttribute('aria-label', 'Actualizar listado de cámaras');
  refreshBtn.appendChild(createSvgIcon(ICONS.refresh, 16));
  const refreshText = document.createElement('span');
  refreshText.textContent = 'Actualizar';
  refreshBtn.appendChild(refreshText);

  headerActions.appendChild(refreshBtn);
  cardHeader.appendChild(headingWrap);
  cardHeader.appendChild(headerActions);
  contentCard.appendChild(cardHeader);

  // Contenedor dinámico del estado de cámaras
  const camerasSlot = document.createElement('div');
  camerasSlot.id = 'cameras-slot';
  contentCard.appendChild(camerasSlot);
  shell.appendChild(contentCard);

  // Pie de página
  const footer = document.createElement('footer');
  footer.className = 'admin-footer';
  footer.textContent = 'VIGIA Vision Systems';
  shell.appendChild(footer);

  container.appendChild(shell);

  /**
   * Renderiza el estado 1: Cargando
   */
  function renderLoadingState() {
    cleanupActiveStreams();
    camerasSlot.innerHTML = '';
    const stateEl = document.createElement('div');
    stateEl.className = 'camera-state camera-state--loading';
    stateEl.setAttribute('role', 'status');
    stateEl.setAttribute('aria-live', 'polite');

    const spinner = document.createElement('div');
    spinner.className = 'camera-spinner';

    const text = document.createElement('p');
    text.className = 'camera-state-text';
    text.textContent = 'Consultando configuración de cámaras en PostgreSQL...';

    stateEl.appendChild(spinner);
    stateEl.appendChild(text);
    camerasSlot.appendChild(stateEl);
  }

  /**
   * Renderiza el estado 2: Datos disponibles (Cuadrícula de cámaras con streaming en vivo)
   * @param {Array<Object>} cameras
   * @param {number} total
   */
  async function renderDataState(cameras, total) {
    cleanupActiveStreams();
    const currentGeneration = viewGenerationToken;
    camerasSlot.innerHTML = '';

    const summary = document.createElement('div');
    summary.className = 'camera-summary-bar';
    summary.textContent = `Mostrando ${cameras.length} de ${total} cámara(s) registrada(s).`;
    camerasSlot.appendChild(summary);

    const grid = document.createElement('div');
    grid.className = 'camera-grid';

    // Limpiar mapa dinámico por código de cámara para nuevo renderizado
    cameraCardRefs.clear();

    cameras.forEach((cam) => {
      const card = document.createElement('article');
      card.className = 'camera-card';
      card.dataset.cameraId = cam.id_camara;
      card.dataset.cameraCode = cam.codigo;

      // Encabezado de la tarjeta
      const cardHead = document.createElement('header');
      cardHead.className = 'camera-card-header';

      const camTitle = document.createElement('h2');
      camTitle.className = 'camera-card-title';
      camTitle.textContent = cam.nombre || cam.codigo;

      const camCode = document.createElement('span');
      camCode.className = 'camera-code-tag';
      camCode.textContent = cam.codigo;

      const regBadge = document.createElement('span');
      regBadge.className = cam.activa ? 'camera-badge camera-badge--active' : 'camera-badge camera-badge--inactive';
      regBadge.textContent = cam.activa ? 'Activa' : 'Inactiva';

      cardHead.appendChild(camTitle);
      cardHead.appendChild(camCode);
      cardHead.appendChild(regBadge);
      card.appendChild(cardHead);

      // --- VISOR DE STREAMING (CAM-01C / CAM-01E) ---
      const mediaBox = document.createElement('div');
      mediaBox.className = 'camera-card-media';

      // Pastilla de estado operativo (controlada EXCLUSIVAMENTE por el backend)
      const statusPill = document.createElement('span');
      statusPill.className = 'camera-status-pill camera-status-pill--standby';
      const statusDot = document.createElement('span');
      statusDot.className = 'camera-status-dot';
      const statusText = document.createElement('span');
      statusText.className = 'camera-status-text';
      statusText.textContent = 'EN ESPERA';
      statusPill.appendChild(statusDot);
      statusPill.appendChild(statusText);
      mediaBox.appendChild(statusPill);

      // Indicador independiente de error de reproducción dentro del visor (CAM-01E-01 / FE-05B)
      const playbackErrorOverlay = document.createElement('div');
      playbackErrorOverlay.className = 'camera-playback-error';
      playbackErrorOverlay.hidden = true;

      const playbackBadge = document.createElement('span');
      playbackBadge.className = 'camera-playback-badge';
      playbackBadge.textContent = 'ERROR DE REPRODUCCIÓN';

      const playbackMsg = document.createElement('span');
      playbackMsg.textContent = 'No se pudo cargar el flujo de video en este navegador.';

      const retryBtn = document.createElement('button');
      retryBtn.type = 'button';
      retryBtn.className = 'camera-playback-retry-btn';
      retryBtn.textContent = 'Reintentar Conexión';
      retryBtn.setAttribute('aria-label', `Reintentar conexión de streaming para ${cam.codigo}`);

      playbackErrorOverlay.appendChild(playbackBadge);
      playbackErrorOverlay.appendChild(playbackMsg);
      playbackErrorOverlay.appendChild(retryBtn);
      mediaBox.appendChild(playbackErrorOverlay);

      // Imagen para visualización MJPEG (/api/v1/cameras/<codigo>/stream)
      const streamImg = document.createElement('img');
      streamImg.className = 'camera-stream-img';
      streamImg.alt = `Transmisión en vivo de ${cam.nombre || cam.codigo}`;
      streamImg.src = apiService.getCameraLiveStreamUrl(cam.codigo);
      activeStreamImgs.push(streamImg);

      mediaBox.appendChild(streamImg);

      // Franja inferior de detecciones YOLO (CAM-01E-02)
      const detectionsOverlay = document.createElement('div');
      detectionsOverlay.className = 'camera-detections-overlay';

      const detInfo = document.createElement('div');
      detInfo.className = 'camera-detection-info';
      detInfo.textContent = 'DETECCIONES NO DISPONIBLES';

      detectionsOverlay.appendChild(detInfo);
      mediaBox.appendChild(detectionsOverlay);
      card.appendChild(mediaBox);

      // Referencias reactivas por tarjeta para reconexión y ciclo de vida (FE-05B)
      const camRefs = {
        card,
        mediaBox,
        statusPill,
        statusText,
        detInfo,
        playbackErrorOverlay,
        playbackBadge,
        playbackMsg,
        retryBtn,
        streamImg,
        reconnectTimeoutId: null,
        reconnectAttempts: 0,
        lastSuccessfulUpdate: Date.now()
      };

      // Función controlada para ejecutar la reconexión con cache-busting
      function triggerReconnect(isManual = false) {
        if (isViewDestroyed || currentGeneration !== viewGenerationToken) return;
        if (camRefs.reconnectTimeoutId) {
          clearTimeout(camRefs.reconnectTimeoutId);
          camRefs.reconnectTimeoutId = null;
        }

        camRefs.reconnectAttempts += 1;
        playbackBadge.textContent = 'RECONECTANDO TRANSMISIÓN';
        playbackBadge.className = 'camera-playback-badge camera-playback-badge--reconnecting';
        playbackMsg.textContent = isManual
          ? 'Reconectando flujo de video...'
          : `Reconectando transmisión (intento ${camRefs.reconnectAttempts}/5)...`;
        retryBtn.disabled = true;
        retryBtn.textContent = 'Reconectando...';

        try {
          if (typeof streamImg.removeAttribute === 'function') {
            streamImg.removeAttribute('src');
          } else {
            streamImg.src = '';
          }
        } catch (_) {}

        // Asignar URL fresca con parámetro de cache-busting
        const streamUrl = apiService.getCameraLiveStreamUrl(cam.codigo);
        streamImg.src = `${streamUrl}?retry=${Date.now()}`;
      }

      // Programar reconexión automática con backoff exponencial (máximo 10s)
      function scheduleAutoReconnect() {
        if (isViewDestroyed || currentGeneration !== viewGenerationToken) return;
        if (camRefs.reconnectTimeoutId) {
          clearTimeout(camRefs.reconnectTimeoutId);
          camRefs.reconnectTimeoutId = null;
        }

        // Límite máximo de intentos consecutivos automáticos
        if (camRefs.reconnectAttempts >= 5) {
          playbackBadge.textContent = 'ERROR PERSISTENTE';
          playbackBadge.className = 'camera-playback-badge camera-playback-badge--persistent';
          playbackMsg.textContent = 'No se pudo restablecer la transmisión tras varios intentos. Presione "Reintentar Conexión".';
          retryBtn.disabled = false;
          retryBtn.textContent = 'Reintentar Conexión';
          return;
        }

        // Backoff exponencial: ~1.5s, 2.7s, 4.8s, 8.7s, máx 10s
        const delay = Math.min(10000, Math.round(1500 * Math.pow(1.8, camRefs.reconnectAttempts)));
        playbackBadge.textContent = 'RECONECTANDO TRANSMISIÓN';
        playbackBadge.className = 'camera-playback-badge camera-playback-badge--reconnecting';
        playbackMsg.textContent = `Interrupción en la señal de video. Reintentando en ${Math.round(delay / 1000)}s...`;
        retryBtn.disabled = false;
        retryBtn.textContent = 'Reintentar Ahora';

        camRefs.reconnectTimeoutId = setTimeout(() => {
          camRefs.reconnectTimeoutId = null;
          triggerReconnect(false);
        }, delay);
        if (camRefs.reconnectTimeoutId && typeof camRefs.reconnectTimeoutId.unref === 'function') {
          camRefs.reconnectTimeoutId.unref();
        }
      }

      // Reintento manual accesible mediante clic
      retryBtn.addEventListener('click', (e) => {
        if (e && typeof e.preventDefault === 'function') e.preventDefault();
        triggerReconnect(true);
      });

      // Manejo de errores de reproducción sin alterar la pastilla operativa
      streamImg.addEventListener('error', () => {
        if (isViewDestroyed || currentGeneration !== viewGenerationToken) return;
        playbackErrorOverlay.hidden = false;
        scheduleAutoReconnect();
      });

      // Manejo de carga exitosa: restablecer overlay, resetear reintentos y detectar orientación
      streamImg.addEventListener('load', () => {
        if (isViewDestroyed || currentGeneration !== viewGenerationToken) return;
        playbackErrorOverlay.hidden = true;
        camRefs.reconnectAttempts = 0;
        if (camRefs.reconnectTimeoutId) {
          clearTimeout(camRefs.reconnectTimeoutId);
          camRefs.reconnectTimeoutId = null;
        }
        retryBtn.disabled = false;
        retryBtn.textContent = 'Reintentar Conexión';
        updateStreamOrientation(streamImg, mediaBox);
      });

      // Guardar referencias para actualización reactiva vía polling
      cameraCardRefs.set(cam.codigo, camRefs);

      // Áreas de Visión
      const areasSection = document.createElement('div');
      areasSection.className = 'camera-card-areas';

      const areasTitle = document.createElement('h3');
      areasTitle.className = 'camera-areas-title';
      const areasCount = Array.isArray(cam.areas) ? cam.areas.length : 0;
      areasTitle.textContent = `Áreas de Visión (${areasCount})`;
      areasSection.appendChild(areasTitle);

      if (areasCount === 0) {
        const noAreas = document.createElement('p');
        noAreas.className = 'camera-no-areas';
        noAreas.textContent = 'Sin áreas de visión configuradas para esta cámara.';
        areasSection.appendChild(noAreas);
      } else {
        const areasList = document.createElement('ul');
        areasList.className = 'camera-areas-list';

        cam.areas.forEach((area) => {
          const areaItem = document.createElement('li');
          areaItem.className = 'camera-area-item';

          const areaCode = document.createElement('span');
          areaCode.className = 'camera-area-code';
          areaCode.textContent = area.codigo;

          const areaName = document.createElement('span');
          areaName.className = 'camera-area-name';
          areaName.textContent = area.nombre || area.codigo;

          const areaType = document.createElement('span');
          areaType.className = `camera-area-type camera-area-type--${(area.tipo_movimiento || 'desconocido').toLowerCase()}`;
          areaType.textContent = area.tipo_movimiento || 'GENERAL';

          areaItem.appendChild(areaCode);
          areaItem.appendChild(areaName);
          areaItem.appendChild(areaType);
          areasList.appendChild(areaItem);
        });

        areasSection.appendChild(areasList);
      }

      card.appendChild(areasSection);

      // Pie de tarjeta con identificador UUID relacional
      const cardFoot = document.createElement('footer');
      cardFoot.className = 'camera-card-footer';
      cardFoot.textContent = `ID: ${cam.id_camara}`;
      card.appendChild(cardFoot);

      grid.appendChild(card);
    });

    camerasSlot.appendChild(grid);

    // Función para actualizar estados de cámaras vía GET /api/v1/cameras/<codigo>/status
    async function updateOperationalStatus() {
      // Protección de lifecycle y concurrencia (CAM-01E-03 y CAM-01E-04)
      if (isViewDestroyed || currentGeneration !== viewGenerationToken || isPollingInProgress) {
        return;
      }
      isPollingInProgress = true;

      try {
        for (const [code, refs] of cameraCardRefs.entries()) {
          if (isViewDestroyed || currentGeneration !== viewGenerationToken) {
            break;
          }

          // Verificar si las dimensiones cambiaron durante el stream (rotación móvil FE-05A)
          if (refs.streamImg && refs.mediaBox) {
            updateStreamOrientation(refs.streamImg, refs.mediaBox);
          }

          let statusData;
          try {
            statusData = await apiService.getCameraStatus(code);
            refs.lastSuccessfulUpdate = Date.now();
          } catch (pollErr) {
            if (isViewDestroyed || currentGeneration !== viewGenerationToken) {
              return;
            }
            // 401: Sesión expirada o inválida
            if (pollErr instanceof AuthError || pollErr?.status === 401) {
              cleanupActiveStreams();
              renderAuthErrorState(pollErr);
              return;
            }
            // 403: Usuario sin autorización (p. ej. AUDITOR)
            if (pollErr instanceof ForbiddenError || pollErr?.status === 403) {
              cleanupActiveStreams();
              renderForbiddenState(pollErr);
              return;
            }
            // 404: Cámara no registrada en el sistema
            if (pollErr?.status === 404) {
              refs.statusPill.className = 'camera-status-pill camera-status-pill--error';
              refs.statusText.textContent = 'NO REGISTRADA';
              refs.card.classList.remove('camera-card--vehicle-detected', 'camera-card--roi-active');
              refs.mediaBox.classList.remove('camera-card-media--roi-active');
              refs.detInfo.textContent = 'Cámara no encontrada';
              continue;
            }
            // 5xx / Timeout / Falla de red: Evaluar límite de antigüedad de 6 segundos
            const lastUpdate = refs.lastSuccessfulUpdate || 0;
            const ageMs = Date.now() - lastUpdate;
            if (lastUpdate > 0 && ageMs > 6000) {
              refs.statusPill.className = 'camera-status-pill camera-status-pill--error';
              refs.statusText.textContent = 'SIN ACTUALIZACIÓN';
              refs.card.classList.remove('camera-card--vehicle-detected', 'camera-card--roi-active');
              refs.mediaBox.classList.remove('camera-card-media--roi-active');
              refs.detInfo.textContent = 'Sin actualización (>6s)';
            }
            continue;
          }

          if (isViewDestroyed || currentGeneration !== viewGenerationToken || !statusData) {
            continue;
          }

          const opState = statusData.operational_state || (statusData.is_transmitting ? 'TRANSMITIENDO' : 'EN_ESPERA');

          // Actualizar pastilla de estado basada EXCLUSIVAMENTE en backend
          refs.statusPill.className = 'camera-status-pill';
          if (opState === 'TRANSMITIENDO') {
            refs.statusPill.classList.add('camera-status-pill--transmitting');
            refs.statusText.textContent = 'TRANSMITIENDO';
          } else if (opState === 'SIN_SEÑAL') {
            refs.statusPill.classList.add('camera-status-pill--nosignal');
            refs.statusText.textContent = 'SIN SEÑAL';
          } else if (opState === 'ENROLADA') {
            refs.statusPill.classList.add('camera-status-pill--enrolled');
            refs.statusText.textContent = 'ENROLADA';
          } else if (opState === 'ERROR') {
            refs.statusPill.classList.add('camera-status-pill--error');
            refs.statusText.textContent = 'ERROR';
          } else {
            refs.statusPill.classList.add('camera-status-pill--standby');
            refs.statusText.textContent = 'EN ESPERA';
          }

          // Realce visual de tarjeta y contenedor ante detecciones y presencia en ROI (FE-05A/6)
          if (opState === 'TRANSMITIENDO' && statusData.is_transmitting && statusData.vehicle_detected) {
            refs.card.classList.add('camera-card--vehicle-detected');
            if (statusData.in_roi) {
              refs.card.classList.add('camera-card--roi-active');
              refs.mediaBox.classList.add('camera-card-media--roi-active');
            } else {
              refs.card.classList.remove('camera-card--roi-active');
              refs.mediaBox.classList.remove('camera-card-media--roi-active');
            }
          } else {
            refs.card.classList.remove('camera-card--vehicle-detected');
            refs.card.classList.remove('camera-card--roi-active');
            refs.mediaBox.classList.remove('camera-card-media--roi-active');
          }

          // Actualizar información de detecciones reales (CAM-01E-02)
          refs.detInfo.innerHTML = '';
          if (opState === 'TRANSMITIENDO' && statusData.is_transmitting) {
            if (statusData.vehicle_detected && statusData.tipo_vehiculo) {
              const badge = document.createElement('span');
              badge.className = 'camera-detection-badge';
              const pct = typeof statusData.confianza === 'number' ? Math.round(statusData.confianza * 100) : null;
              badge.textContent = `DETECTADO: ${statusData.tipo_vehiculo.toUpperCase()}${pct !== null ? ` (${pct}%)` : ''}`;
              refs.detInfo.appendChild(badge);

              if (statusData.in_roi) {
                const roiBadge = document.createElement('span');
                roiBadge.className = 'camera-detection-roi';
                roiBadge.textContent = 'EN ZONA ROI';
                refs.detInfo.appendChild(roiBadge);
              }
            } else if (statusData.status && statusData.status !== 'DESCONOCIDO' && statusData.status !== 'EN_ESPERA') {
              // Inferencia confirmada por el coordinador sin detección de vehículos
              refs.detInfo.textContent = 'Sin vehículos detectados';
            } else {
              refs.detInfo.textContent = 'DETECCIONES NO DISPONIBLES';
            }
          } else {
            // Si no está transmitiendo, no presentar datos de detección como actuales
            refs.detInfo.textContent = 'DETECCIONES NO DISPONIBLES';
          }
        }
      } finally {
        isPollingInProgress = false;
      }
    }

    // Ejecutar actualización inicial y programar polling cada 3 segundos
    await updateOperationalStatus();
    activePollInterval = setInterval(updateOperationalStatus, 3000);
    if (activePollInterval && typeof activePollInterval.unref === 'function') {
      activePollInterval.unref();
    }

    // Registrar listener de visibilitychange para suspender polling en segundo plano (FE-05C)
    if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
      activeVisibilityListener = () => {
        if (isViewDestroyed || currentGeneration !== viewGenerationToken) return;
        if (document.hidden) {
          if (activePollInterval) {
            clearInterval(activePollInterval);
            activePollInterval = null;
          }
        } else {
          if (!activePollInterval) {
            updateOperationalStatus();
            activePollInterval = setInterval(updateOperationalStatus, 3000);
            if (activePollInterval && typeof activePollInterval.unref === 'function') {
              activePollInterval.unref();
            }
          }
        }
      };
      document.addEventListener('visibilitychange', activeVisibilityListener);
    }
  }

  /**
   * Renderiza el estado 3: Lista vacía
   */
  function renderEmptyState() {
    camerasSlot.innerHTML = '';
    const emptyEl = document.createElement('div');
    emptyEl.className = 'camera-state camera-empty-state';
    emptyEl.setAttribute('role', 'status');

    const icon = createSvgIcon(ICONS.camera, 48);
    icon.classList.add('camera-state-icon');

    const title = document.createElement('h2');
    title.className = 'camera-empty-title';
    title.textContent = 'No hay cámaras registradas';

    const desc = document.createElement('p');
    desc.className = 'camera-empty-desc';
    desc.textContent =
      'Actualmente no existen cámaras lógicas configuradas en la caseta institucional. Los registros de cámaras y áreas creados en PostgreSQL se visualizarán automáticamente aquí.';

    emptyEl.appendChild(icon);
    emptyEl.appendChild(title);
    emptyEl.appendChild(desc);
    camerasSlot.appendChild(emptyEl);
  }

  /**
   * Renderiza el estado 4: Error de autenticación (401)
   */
  function renderAuthErrorState(err) {
    camerasSlot.innerHTML = '';
    const errEl = document.createElement('div');
    errEl.className = 'camera-state camera-state--auth-error';
    errEl.setAttribute('role', 'alert');

    const icon = createSvgIcon(ICONS.lock, 44);
    icon.classList.add('camera-state-icon');

    const title = document.createElement('h2');
    title.className = 'camera-error-title';
    title.textContent = 'Sesión Expirada o No Válida (HTTP 401)';

    const desc = document.createElement('p');
    desc.className = 'camera-error-desc';
    desc.textContent =
      'Su sesión de trabajo ha vencido o la cookie de sesión no fue reconocida por el servidor. Por favor, vuelva a identificarse.';

    const loginBtn = document.createElement('button');
    loginBtn.type = 'button';
    loginBtn.className = 'admin-action-pill-btn';
    loginBtn.textContent = 'Ir al Inicio de Sesión';
    loginBtn.addEventListener('click', () => {
      if (typeof onNavigate === 'function') {
        onNavigate('login');
      }
    });

    errEl.appendChild(icon);
    errEl.appendChild(title);
    errEl.appendChild(desc);
    errEl.appendChild(loginBtn);
    camerasSlot.appendChild(errEl);
  }

  /**
   * Renderiza el estado 5: Acceso denegado (403)
   */
  function renderForbiddenState(err) {
    camerasSlot.innerHTML = '';
    const forbEl = document.createElement('div');
    forbEl.className = 'camera-state camera-state--forbidden';
    forbEl.setAttribute('role', 'alert');

    const icon = createSvgIcon(ICONS.shieldForbidden, 48);
    icon.classList.add('camera-state-icon');

    const title = document.createElement('h2');
    title.className = 'camera-error-title';
    title.textContent = 'Acceso Denegado (HTTP 403 Forbidden)';

    const desc = document.createElement('p');
    desc.className = 'camera-error-desc';
    desc.textContent =
      'Su rol de usuario no cuenta con autorización para consultar la topología de cámaras. Esta función está reservada exclusivamente para los perfiles ADMINISTRADOR y GUARDIA.';

    forbEl.appendChild(icon);
    forbEl.appendChild(title);
    forbEl.appendChild(desc);
    camerasSlot.appendChild(forbEl);
  }

  /**
   * Renderiza el estado 6: Error de red o del servidor (5xx)
   */
  function renderServerErrorState(err) {
    camerasSlot.innerHTML = '';
    const errEl = document.createElement('div');
    errEl.className = 'camera-state camera-state--server-error';
    errEl.setAttribute('role', 'alert');

    const icon = createSvgIcon(ICONS.alert, 44);
    icon.classList.add('camera-state-icon');

    const title = document.createElement('h2');
    title.className = 'camera-error-title';
    title.textContent =
      err instanceof NetworkError
        ? 'Error de Conexión de Red'
        : 'Error del Servidor (HTTP 5xx)';

    const desc = document.createElement('p');
    desc.className = 'camera-error-desc';
    desc.textContent =
      err.message ||
      'No se pudo comunicar con el servicio de cámaras. Verifique el estado de PostgreSQL y la conectividad del backend.';

    const retryBtn = document.createElement('button');
    retryBtn.type = 'button';
    retryBtn.id = 'btn-retry-cameras';
    retryBtn.className = 'admin-action-pill-btn';
    retryBtn.textContent = 'Reintentar Conexión';
    retryBtn.addEventListener('click', () => loadCameras());

    errEl.appendChild(icon);
    errEl.appendChild(title);
    errEl.appendChild(desc);
    errEl.appendChild(retryBtn);
    camerasSlot.appendChild(errEl);
  }

  /**
   * Ejecuta la carga y asigna el estado adecuado.
   */
  async function loadCameras() {
    renderLoadingState();
    refreshBtn.disabled = true;

    try {
      const data = await apiService.getCameras();
      if (!data || !Array.isArray(data.cameras) || data.cameras.length === 0) {
        renderEmptyState();
      } else {
        await renderDataState(data.cameras, data.total);
      }
    } catch (err) {
      if (err instanceof AuthError && err.status === 401) {
        renderAuthErrorState(err);
      } else if (err instanceof ForbiddenError || err.status === 403) {
        renderForbiddenState(err);
      } else {
        renderServerErrorState(err);
      }
    } finally {
      refreshBtn.disabled = false;
    }
  }

  refreshBtn.addEventListener('click', () => loadCameras());
  await loadCameras();
}
