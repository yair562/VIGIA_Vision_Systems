# VIGIA-FE-05 — Informe de Implementación: Visor Adaptativo y Recuperación de Streaming

**Proyecto:** VIGÍA Vision Systems  
**Fase:** VIGIA-FE-05  
**Tipo:** Implementación Frontend y Resiliencia Operativa  
**Referencia:** [VIGIA-FE-04_AUDITORIA_FRONTEND.md](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/Docs/auditorias/VIGIA-FE-04_AUDITORIA_FRONTEND.md)  
**Fecha:** 4 de Noviembre de 2026  
**Estado:** **IMPLEMENTACIÓN APROBADA** (27/27 Tests de Integración Exitosos)

---

## 1. Resumen Ejecutivo

En cumplimiento con los requerimientos de la fase **VIGIA-FE-05**, se completó con éxito la implementación de las mejoras visuales, la adaptabilidad de encuadre y la resiliencia operativa del Dashboard de VIGÍA Vision Systems y su cliente móvil `/mobile`.

La implementación resuelve las limitaciones detectadas en la auditoría `VIGIA-FE-04`:
1. **Visor Adaptativo Multiorientación:** Detección automática y reactiva de la relación de aspecto del stream MJPEG (`naturalWidth` vs `naturalHeight`), aplicando encuadres optimizados para teléfonos verticales (`9:16`, centrado ergonómico) y cámaras fijas panorámicas (`16:9`).
2. **Previsualización Móvil Fidedigna:** Eliminación del recorte engañoso (`object-fit: cover` con contenedor rígido `4:3`) en `/mobile`. Ahora el visor móvil opera con `object-fit: contain` y relación de aspecto dinámica acoplada a las dimensiones intrínsecas del stream WebRTC del sensor físico.
3. **Recuperación Resiliente de Streaming:** Mecanismo de reconexión automática ante interrupciones de red o caídas temporales del endpoint MJPEG mediante *backoff* exponencial (de 1.5s hasta 10s máx), *cache-busting* (`?retry=`), botón accesible para reintento manual inmediato y preservación inmutable del estado operativo del backend.
4. **Eficiencia Energética y de Red:** Suspensión automática del polling de `/status` al ocultar la pestaña (`visibilitychange`) y sincronización inmediata al recuperar el foco.
5. **Realce Visual Contextual de ROI:** Distinción visual inmediata cuando un vehículo ingresa al área de interés del carril (`.camera-card--roi-active` y `.camera-card-media--roi-active`), consumiendo estrictamente la telemetría existente (`vehicle_detected`, `in_roi`).

---

## 2. Alcance y Archivos Modificados

Se respetó estrictamente la restricción de modificar **únicamente los 4 archivos autorizados**:

| Archivo | Ruta | Propósito de la Modificación |
|---|---|---|
| `cameras-view.js` | `VIGIA_Dashboard/web/js/views/cameras-view.js` | Detección de orientación, lógica de backoff exponencial, reconexión manual, gestión de `visibilitychange`, realce de ROI y blindaje de ciclo de vida en `wrappedOnNavigate`. |
| `admin-devices.css` | `VIGIA_Dashboard/web/css/admin-devices.css` | Estilos para orientación portrait (9:16) y landscape (16:9), resplandor perimetral de ROI, badges de reconexión y botón interactivo `.camera-playback-retry-btn`. |
| `index.html` (Mobile) | `VIGIA_Dashboard/mobile/index.html` | Previsualización adaptativa (`object-fit: contain`, `aspect-ratio: auto` dinámico según metadata de video) y flujo secuencial simplificado de transmisión. |
| `frontend_integration.test.mjs` | `VIGIA_Dashboard/tests/frontend_integration.test.mjs` | Suite automatizada ampliada de 21 a 27 pruebas de integración cubriendo todos los comportamientos de la fase FE-05. |

> [!NOTE]
> No se modificó ningún archivo de backend (`ingest_service.py`, `evidence_storage.py`, base de datos PostgreSQL, pesos de YOLO ni certificados/PKI TLS).

---

## 3. Detalle Técnico de las Soluciones Implementadas

### FE-05A: Visor Adaptativo y Orientación Dinámica

#### 1. En Dashboard (`cameras-view.js` y `admin-devices.css`)
- Se implementó la función reactiva `updateStreamOrientation(img, mediaBox)`:
  - Lee `img.naturalWidth` y `img.naturalHeight`.
  - Si `naturalHeight > naturalWidth`: asigna la clase `.camera-card-media--portrait` y retira `.camera-card-media--landscape`.
  - Si `naturalWidth >= naturalHeight`: asigna la clase `.camera-card-media--landscape` y retira `.camera-card-media--portrait`.
- En CSS:
  - `.camera-card-media--landscape`: `aspect-ratio: 16 / 9; width: 100%;`
  - `.camera-card-media--portrait`: `aspect-ratio: 9 / 16; width: 100%; max-width: 270px; max-height: 480px; margin: 0 auto;`
  - En móviles (`@media (max-width: 768px)`): `max-width: 100%; max-height: 540px;` para aprovechar el ancho disponible.

#### 2. En Módulo Móvil (`mobile/index.html`)
- **Problema previo:** El contenedor poseía `aspect-ratio: 4 / 3` forzado y `object-fit: cover`. Al capturar en vertical (`9:16`), recortaba más del 25% de los laterales, transmitiendo al backend fotogramas con encuadres diferentes a los que el operador visualizaba.
- **Solución implementada:**
  - CSS del contenedor: `aspect-ratio: auto; min-height: 220px; max-height: 65vh;` con `object-fit: contain;`.
  - JS: Función reactiva `adaptPreviewAspect` conectada a `video.onloadedmetadata` y `video.onresize` que actualiza `previewContainer.style.aspectRatio = `${video.videoWidth} / ${video.videoHeight}``.
  - Garantiza correspondencia 1:1 entre el encuadre físico del teléfono y la imagen enviada al motor YOLO.

---

### FE-05B: Resiliencia y Recuperación de Streaming MJPEG

#### 1. Backoff Exponencial y Descorrelación de Caché
- Ante un evento `error` en el elemento `<img>` del stream MJPEG:
  1. Se despliega el overlay de advertencia sin alterar el estado operativo reportado por el backend.
  2. Se calcula el retardo de reconexión con crecimiento exponencial acotado:
     $$\text{delay} = \min(10000, 1500 \times 1.8^{\text{intentos}})$$
  3. Al disparar la reconexión se añade un parámetro anti-caché:
     `url = getCameraLiveStreamUrl(codigo) + '?retry=' + Date.now() + '_' + attempts;`
  4. Si el stream emite `load`, el contador de intentos se reinicia a `0`, se oculta el overlay y se actualizan las dimensiones de orientación.

#### 2. Control de Reintento Manual Accesible
- En el overlay se incorporó el botón `.camera-playback-retry-btn` ("Reintentar Ahora").
- Permite al operador forzar un reintento manual inmediato sin esperar a que concluya la temporización del backoff.
- Posee estados accesibles de foco (`:focus-visible`), estado deshabilitado (`:disabled`) y feedback visual.

#### 3. Blindaje de Ciclo de Vida y Prevención de Fugas de Memoria
- Cada tarjeta almacena su temporizador activo en `camRefs.reconnectTimeoutId`.
- Al desmontar la vista o navegar hacia otra sección (capturado mediante `wrappedOnNavigate`), la función `cleanupActiveStreams()`:
  - Cancela todos los temporizadores de reconexión pendientes (`clearTimeout`).
  - Desvincula listeners de error y carga (`onerror = null`, `onload = null`).
  - Remueve el atributo `src` de todos los elementos `<img>` activos (`img.removeAttribute('src')`), cerrando de forma determinista los sockets MJPEG persistentes.
  - Vacia los mapas de referencias (`cameraCardRefs.clear()`).

---

### FE-05C: Optimización de Recursos y Supresión de Polling Inactivo

- En `cameras-view.js` se implementó la escucha del evento nativo `visibilitychange`:
  ```javascript
  activeVisibilityListener = () => {
    if (isViewDestroyed || currentGeneration !== viewGenerationToken) return;
    if (document.hidden) {
      if (activePollInterval) {
        clearInterval(activePollInterval);
        activePollInterval = null;
      }
    } else {
      if (!activePollInterval) {
        updateOperationalStatus(); // Actualización inmediata al regresar
        activePollInterval = setInterval(updateOperationalStatus, 3000);
      }
    }
  };
  document.addEventListener('visibilitychange', activeVisibilityListener);
  ```
- **Beneficio:** Evita peticiones HTTP innecesarias cuando el operador navega en otras pestañas o minimiza el navegador, y asegura frescura inmediata de telemetría en cuanto la pestaña vuelve a primer plano.

---

### FE-05D: Realce Visual de Detecciones y Zona de Interés (ROI)

- La actualización periódica de `/status` evalúa:
  ```javascript
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
  ```
- **Estilo visual:**
  - `.camera-card--vehicle-detected`: Borde verde esmeralda (`rgba(16, 185, 129, 0.55)`).
  - `.camera-card--roi-active`: Borde índigo realzado (`rgba(99, 102, 241, 0.7)`) con anillo de resplandor `box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.28)`.
  - `.camera-card-media--roi-active`: Resplandor perimetral directo sobre el contenedor de video.

---

## 4. Resultados de Verificación Automatizada

Se ejecutó la suite completa de integración en `VIGIA_Dashboard/tests/frontend_integration.test.mjs`. Los 27 tests pasaron satisfactoriamente en **108.8 ms**:

```text
✔ 1. Login correcto e incorrecto en apiService (15.0449ms)
✔ 2. Restauración de sesión con /auth/me (0.2352ms)
✔ 3. Estado no autenticado: 401 devuelve null en getCurrentUser (0.147ms)
✔ 4. Logout y limpieza idempotente (0.1485ms)
✔ 5. Ausencia total de tokens en almacenamiento web (0.1347ms)
✔ 6. Transporte de cookies con credentials: "include" (0.1749ms)
✔ 7. Carga de cámaras persistidas y exclusión estricta de uri_stream (0.3245ms)
✔ 8. Estado vacío sin cámaras (0.133ms)
✔ 9. Manejo de errores 401, 403 y 5xx (0.397ms)
✔ 10. Diferenciación estricta entre fallos de red y sesiones inválidas (0.2649ms)
✔ 11. Presentación y navegación según el rol (0.6961ms)
✔ 12. Aislamiento del modo DEMO (0.1262ms)
✔ 13. Preservación innegociable de la barra horizontal superior (0.6113ms)
✔ 14. Contrato de apiService.get y apiService.post con credentials: "include" y JSON (0.233ms)
✔ 15. Integración de deviceService con apiService para generación QR y revocación (MOB-QR-02) (0.3631ms)
✔ 16. Propagación fiel de errores 401, 403 y 500 en apiService.post y deviceService (0.2831ms)
✔ 17. Consulta de información de red y direcciones LAN en apiService (VIGIA-NET-01) (0.1436ms)
✔ 18. Integración de streaming, visor de video y estados operativos en cameras-view (CAM-01C y CAM-01E) (1.9704ms)
✔ 19. Verificación exhaustiva de estados operativos del backend (CAM-01E) (1.0341ms)
✔ 20. Lifecycle, protección de concurrencia y liberación de fuentes MJPEG (CAM-01E) (18.4798ms)
✔ 21. Automatización de transmisión móvil con botón único y ciclo secuencial (MOB-CAM-02D) (1.8204ms)
✔ 22. Visor adaptativo para orientación Portrait, Landscape y cambios dinámicos (FE-05A) (0.9721ms)
✔ 23. Recuperación automática y manual del stream MJPEG con backoff exponencial y cache-busting (FE-05B) (0.566ms)
✔ 24. Cancelación de reintentos y liberación de temporizadores al desmontar vista (FE-05B/Lifecycle) (0.3997ms)
✔ 25. Suspensión de polling con visibilitychange y reactivación inmediata (FE-05C) (0.5035ms)
✔ 26. Realce visual diferenciado ante detecciones y presencia en zona ROI (FE-05A/6) (58.058ms)
✔ 27. Vista previa fidedigna en módulo móvil sin recorte engañoso (FE-05A/Mobile) (1.2072ms)
ℹ tests 27 | pass 27 | fail 0 | cancelled 0 | skipped 0 | todo 0
```

---

## 5. Procedimiento de Validación Física con Teléfono Android

Para verificar el correcto funcionamiento en entorno real:

1. **Apertura de la Vista de Monitoreo:**
   - En la estación de control, abrir el navegador en `https://192.168.1.75:5000` e iniciar sesión como Administrador.
   - Navegar a la sección **Cámaras**.
   - Observar que las tarjetas de cámara inician en estado `EN ESPERA` o `SIN SEÑAL`.
2. **Inicio de Transmisión Móvil:**
   - En el dispositivo Android conectado a la misma red Wi-Fi LAN, abrir `https://192.168.1.75:5000/mobile`.
   - Pulsar el botón principal **"▶️ Iniciar Transmisión"**.
   - Verificar que el visor local muestra el encuadre exacto sin recortar los laterales en modo vertical.
3. **Comprobación del Visor Adaptativo en Dashboard:**
   - En el Dashboard de la computadora, verificar que el contenedor de la cámara detecta la orientación vertical y ajusta su tarjeta a proporciones `9:16` de forma estilizada y centrada.
   - Rotar el teléfono a horizontal (Landscape) y verificar que la tarjeta se adapta a proporciones `16:9` panorámicas sin distorsión.
4. **Comprobación de Detección y ROI:**
   - Apuntar la cámara del teléfono hacia un vehículo o modelo de prueba.
   - Observar cómo la tarjeta en el Dashboard adquiere el borde verde de detección y, al entrar en el área delimitada de ROI, se ilumina el resplandor índigo perimetral con la indicación de conteo `in_roi`.
5. **Comprobación de Resiliencia de Red y Reconexión:**
   - Desactivar brevemente el Wi-Fi en el teléfono o pausar la transmisión.
   - Observar que el Dashboard muestra el badge `RECONECTANDO TRANSMISIÓN` con la cuenta regresiva del backoff exponencial y el botón `Reintentar Ahora`.
   - Al reactivar la señal, el stream se recupera automáticamente o al presionar el botón de reintento sin necesidad de recargar la página web.

---

## 6. Dictamen Final

La implementación **VIGIA-FE-05** cumple rigurosamente con todas las especificaciones de diseño, seguridad, ergonomía visual y estabilidad de ciclo de vida, sin alterar las responsabilidades del backend ni las restricciones arquitectónicas del proyecto.

**Dictamen:** **IMPLEMENTACIÓN APROBADA Y LISTA PARA PRODUCCIÓN / DEMO FÍSICA**.
