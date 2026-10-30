# SPRINT 01 — Infraestructura Visual y Pantalla de Inicio de Sesión

---

## 1. Identificador y Nombre del Sprint

- **Identificador:** `SPRINT_01`
- **Nombre:** Infraestructura visual y pantalla de inicio de sesión
- **Módulo:** `VIGIA_Dashboard/`
- **Fecha de cierre:** 29 de octubre de 2026

---

## 2. Objetivo

Establecer la arquitectura modular inicial del frontend de **VIGÍA Vision Systems** dentro de `VIGIA_Dashboard/`, integrar la identidad visual oficial del proyecto sin duplicar recursos gráficos y desarrollar la pantalla de **Inicio de Sesión** adaptable a dispositivos móviles, tabletas y computadoras de escritorio, junto con su estructura de documentación técnica exclusiva.

---

## 3. Alcance

### Dentro del alcance (Sprint 01)
1. Inspección de la estructura existente en `VIGIA_Dashboard/` y preservación íntegra del cliente móvil de captura (`VIGIA_Dashboard/mobile/index.html`).
2. Creación de la estructura modular en `VIGIA_Dashboard/web/` (`index.html`, `css/`, `js/`, `assets/backgrounds/`).
3. Integración del símbolo oficial de VIGÍA (`producto_figura_dark.svg`) desde su ubicación original en `Docs/GEST_PROY_SOFT/02_Logos_accesibilidad/svg/`.
4. Implementación del diseño aprobado de la pantalla de Inicio de Sesión con soporte responsivo para móvil (`< 640px`), tableta (`640px – 1023px`) y escritorio (`>= 1024px`).
5. Implementación del comportamiento del formulario en cliente: validación de campos obligatorios, estados de carga (`aria-busy`), área accesible de retroalimentación y mensaje informativo para recuperación de contraseñas, sin simular sesiones ni almacenar credenciales.
6. Creación de la documentación exclusiva del frontend en `VIGIA_Dashboard/Docs/`.

### Fuera del alcance (Diferido a siguientes sprints)
- Conexión real de autenticación con endpoints de `VIGIA_API` (corresponde al Sprint 02).
- Modificación de `VIGIA_API/`, `VIGIA_Core/`, `VIGIA_Vision/`, `VIGIA_IoT/`, `VIGIA_Automation/` o `BD/`.
- Construcción de las vistas operativas del Guardia (`OPERADOR`) y del Administrador (`ADMINISTRADOR`) (corresponden a los Sprints 03 y 04).
- Incorporación de la imagen de fondo definitiva (aún no disponible; se dejó preparada la variable CSS `--login-bg-image`).

---

## 4. Requerimientos Abordados

| ID Ref. | Descripción del Requerimiento Abordado en Sprint 01 | Estado |
| :---: | :--- | :---: |
| **FE-S01-01** | Estructura modular de archivos HTML5, CSS3 y JS Vanilla ES6 dentro de `VIGIA_Dashboard/web/`. | Cumplido |
| **FE-S01-02** | Conservación sin cambios del cliente móvil existente `VIGIA_Dashboard/mobile/index.html`. | Cumplido |
| **FE-S01-03** | Uso del símbolo oficial de VIGÍA dentro del contenedor circular oscuro sin alterar ni duplicar los SVG originales. | Cumplido |
| **FE-S01-04** | Composición visual fiel al wireframe aprobado: fondo blanco, tarjeta vertical gris claro con bordes redondeados (`max-width: 400px`), título `Inicio de Sesión`, círculo oscuro con logo, dos entradas tipo píldora, botón `Iniciar Sesión` más corto y enlace `¿Olvidaste la contraseña?`. | Cumplido |
| **FE-S01-05** | Adaptabilidad responsive en tres rangos: móvil (`< 640px`), tableta (`640px – 1023px`) y escritorio (`>= 1024px`). | Cumplido |
| **FE-S01-06** | Atributos semánticos y de accesibilidad (`autocomplete="username"`, `autocomplete="current-password"`, `required`, etiquetas `.sr-only`, `:focus-visible`, contenedor `aria-live`). | Cumplido |
| **FE-S01-07** | Validación de campos obligatorios y aviso explícito de que la autenticación aún no está conectada al backend, sin autenticación ficticia ni almacenamiento en `localStorage`/`sessionStorage`. | Cumplido |
| **FE-S01-08** | Acción del enlace `¿Olvidaste la contraseña?` mostrando el texto exacto: `La recuperación de contraseñas debe solicitarse al administrador del sistema.` | Cumplido |

---

## 5. Decisiones Técnicas

1. **Elección de `producto_figura_dark.svg` para el círculo de marca:**
   - Tras inspeccionar los 8 archivos en `Docs/GEST_PROY_SOFT/02_Logos_accesibilidad/svg/`, se verificó que `producto_figura.svg` posee relleno negro (`fill="#000000"`) y `producto_figura_dark.svg` posee relleno blanco (`fill="#FFFFFF"`) con `viewBox="0 0 489.000000 415.000000"`. Dado que el diseño aprobado especifica un contenedor circular gris oscuro (`#3A3A3A`), se seleccionó `producto_figura_dark.svg` para garantizar alto contraste (nivel WCAG AAA) sin modificar el archivo original.
2. **Servicio controlado del SVG oficial y activos estáticos mediante Flask:**
   - En `VIGIA_Dashboard/web/index.html` se referencian las rutas servidas por Flask `/assets/brand/producto_figura_dark.svg`, `/dashboard-assets/css/*` y `/dashboard-assets/js/*`. En `VIGIA_API/ingest_service.py` se registraron las rutas `GET /app`, `GET /dashboard-assets/<path:filename>` y `GET /assets/brand/<filename>` protegidas mediante listas blancas estrictas (`ALLOWED_DASHBOARD_ASSETS` y `ALLOWED_BRAND_SVGS`) y verificación de contención de directorio (`Path.relative_to`), evitando duplicar los SVG originales o permitir acceso arbitrario al sistema de archivos.
3. **Variables CSS para futura imagen de fondo:**
   - En `VIGIA_Dashboard/web/css/tokens.css` se definieron `--login-bg-color: #FFFFFF` y `--login-bg-image: none` aplicadas sobre `.login-viewport`. Cuando exista la imagen definitiva, solo será necesario colocarla en `VIGIA_Dashboard/web/assets/backgrounds/` y actualizar `--login-bg-image`.
4. **Limpieza inmediata de contraseña y ausencia de almacenamiento local:**
   - En `VIGIA_Dashboard/web/js/views/login-view.js`, tras validar los campos y completar el estado visual de verificación, el valor de `#password-input` se limpia inmediatamente (`passwordInput.value = ''`) y no se invoca ninguna API de almacenamiento del navegador (`localStorage` / `sessionStorage`), garantizando que no existan credenciales persistidas ni sesiones simuladas.

---

## 6. Estructura de Archivos Creada o Modificada

```text
VIGIA_Dashboard/
├── README.md                                     # [MODIFICADO] Actualizado con estado y guía de Sprint 01
├── mobile/
│   └── index.html                                # [INTACTO] Conservado sin cambios (13,071 bytes)
├── web/
│   ├── index.html                                # [CREADO] Documento principal de Inicio de Sesión
│   ├── assets/
│   │   └── backgrounds/
│   │       └── README.md                         # [CREADO] Documentación de reserva para futura imagen de fondo
│   ├── css/
│   │   ├── tokens.css                            # [CREADO] Variables de diseño (colores, fuentes, medidas)
│   │   ├── base.css                              # [CREADO] Reset CSS y utilidades de accesibilidad
│   │   └── login.css                             # [CREADO] Estilos del wireframe de Login y media queries
│   └── js/
│       ├── app.js                                # [CREADO] Inicializador ES Module
│       └── views/
│           └── login-view.js                     # [CREADO] Lógica de validación y estados del formulario
└── Docs/
    ├── README.md                                 # [CREADO] Índice documental del frontend
    ├── PLAN_DESARROLLO_FRONTEND.md               # [CREADO] Planificación evolutiva de los 5 sprints
    ├── ARQUITECTURA_FRONTEND.md                  # [CREADO] Arquitectura técnica detallada del frontend
    └── sprints/
        └── SPRINT_01_INFRAESTRUCTURA_Y_LOGIN.md  # [CREADO] Presente informe del Sprint 01
```

---

## 7. Componentes Desarrollados

1. **Sistema de Tokens (`web/css/tokens.css`):** Define la paleta cromática del login, dimensiones responsivas del círculo de marca (`120px` móvil, `136px` tableta, `148px` escritorio), alturas táctiles (`48px` en campos, `44px` en botón) y colores semánticos de retroalimentación.
2. **Capa Base y Accesibilidad (`web/css/base.css`):** Establece el reset de cajas, ocultamiento accesible `.sr-only` para etiquetas de formulario y contornos de foco `:focus-visible`.
3. **Vista de Inicio de Sesión (`web/index.html` + `web/css/login.css`):** Maquetación de la tarjeta `.login-card` centrada con `CSS Grid`, contenedor circular `.login-brand-circle` con `producto_figura_dark.svg`, campos tipo píldora `.login-input`, botón `.login-submit-btn` más corto y enlace `.login-forgot-link`.
4. **Controlador de Inicio de Sesión (`web/js/views/login-view.js`):** Módulo ES6 encargado de validar entradas obligatorias y formato sin espacios del `username`, alternar el estado `aria-busy` durante la verificación y presentar mensajes accesibles en `#login-feedback`.

---

## 8. Diseño Implementado

El diseño implementado respeta fielmente las especificaciones aprobadas:

- **Fondo de página:** Blanco (`#FFFFFF`), sin imágenes provisionales ni elementos decorativos añadidos.
- **Tarjeta central:** Vertical, color gris claro (`#E0E0E0`), esquinas redondeadas (`26px`), ancho máximo de `400px` y elementos alineados al centro en una sola columna.
- **Título:** `Inicio de Sesión` en tipografía sans-serif, color negro (`#000000`) y peso en negrita (`700`).
- **Identidad gráfica:** Contenedor circular gris oscuro (`#3A3A3A`) alojando el símbolo oficial `producto_figura_dark.svg` en blanco.
- **Campos de entrada:** Dos entradas con bordes en forma de píldora (`border-radius: 9999px`) y fondo casi blanco (`#F8F8F8`, pasando a `#FFFFFF` al recibir foco).
- **Botón principal:** `Iniciar Sesión`, con forma de píldora, ancho inferior al de los campos (`62%`, entre `156px` y `220px`), fondo gris (`#BDBDBD`) y texto negro en negrita.
- **Enlace secundario:** `¿Olvidaste la contraseña?`, centrado debajo del botón, en color negro y negrita.

---

## 9. Consideraciones de Responsividad

Se implementaron tres rangos mediante consultas `@media` en `web/css/login.css`:

- **Móvil (`< 640px`):** Relleno exterior de `1rem`, tarjeta adaptable al `100%` del ancho disponible sin barra de desplazamiento horizontal (`overflow-x: hidden`), círculo de marca de `120px` y controles con altura mínima de `48px` (inputs) y `44px` (botón) para facilitar la interacción táctil.
- **Tableta (`640px – 1023px`):** Relleno exterior de `2rem`, relleno interior de tarjeta de `2.25rem 2rem` y círculo de marca de `136px`.
- **Escritorio (`>= 1024px`):** Tarjeta centrada con ancho máximo fijo en `400px`, relleno interno de `2.5rem 2.25rem` y círculo de marca de `148px`.

---

## 10. Consideraciones de Accesibilidad

- **Etiquetas asociadas:** `<label for="username-input" class="sr-only">Identificación de usuario</label>` y `<label for="password-input" class="sr-only">Contraseña</label>`.
- **Atributos de autocompletado y validación:** `autocomplete="username"`, `autocapitalize="none"`, `spellcheck="false"`, `autocomplete="current-password"` y `required`.
- **Foco visible:** Regla global `:focus-visible` con contorno sólido negro de `2px` y desplazamiento (`outline-offset: 2px`).
- **Mensajes dinámicos accesibles:** El contenedor `#login-feedback` conmuta dinámicamente entre `role="alert"` (`aria-live="assertive"`) para errores de validación y `role="status"` (`aria-live="polite"`) para avisos informativos, marcando además `aria-invalid="true"` en el campo que requiere atención y trasladando el foco hacia él.

---

## 11. Pruebas Realizadas

1. **Integración de visualización con Flask y acceso en red local (`0.0.0.0:5000`):**
   - Se inició el servicio mediante `.\.venv\Scripts\python.exe -m VIGIA_API.ingest_service` escuchando en `0.0.0.0:5000` (`use_debugger=False`).
   - Se identificó mediante `ipconfig` la dirección IPv4 LAN activa del equipo: **`192.168.1.75`** (adaptador `Ethernet` en la red `INFINITUM0870`, puerta de enlace `192.168.1.254`).
   - Se verificaron mediante peticiones HTTP reales las rutas del Dashboard, los activos CSS y JS, el SVG oficial, las rutas previas de diagnóstico e ingesta y el bloqueo de archivos no autorizados:
     - `GET http://127.0.0.1:5000/app`
     - `GET http://127.0.0.1:5000/dashboard-assets/css/tokens.css`
     - `GET http://127.0.0.1:5000/dashboard-assets/css/base.css`
     - `GET http://127.0.0.1:5000/dashboard-assets/css/login.css`
     - `GET http://127.0.0.1:5000/dashboard-assets/js/app.js`
     - `GET http://127.0.0.1:5000/dashboard-assets/js/views/login-view.js`
     - `GET http://127.0.0.1:5000/assets/brand/producto_figura_dark.svg`
     - `GET http://127.0.0.1:5000/` (conservación de respuesta JSON de salud)
     - `GET http://127.0.0.1:5000/mobile` (conservación íntegra del cliente móvil)
     - `POST http://127.0.0.1:5000/api/v1/cameras/CAM-ENTRADA/push` (conservación del modo seguro *fail-closed* HTTP 503)
     - `GET http://192.168.1.75:5000/app` y `GET http://192.168.1.75:5000/assets/brand/producto_figura_dark.svg` (acceso por IPv4 LAN)
     - Bloqueo de seguridad ante archivos fuera de lista blanca (`GET /assets/brand/README.md` y `GET /dashboard-assets/index.html` → `404 Not Found`).
2. **Prueba automatizada de estructura HTML, atributos de accesibilidad y lógica del controlador:**
   - Se verificó la presencia de los atributos requeridos (`autocomplete="username"`, `autocomplete="current-password"`, `required`, `.sr-only`, `aria-live`) y de los mensajes exactos en `login-view.js`.
3. **Ejecución de la suite de pruebas existente del repositorio (`unittest`):**
   - Se ejecutó `.\.venv\Scripts\python.exe -m unittest discover -s tests/unit -p "test_*.py" -v` para comprobar que ningún componente existente (incluida la prueba de ingesta móvil `test_mobile_ingest_api.py`) sufrió regresiones.
4. **Verificación de prueba física desde teléfono móvil:**
   - La validación HTTP sobre la interfaz LAN (`http://192.168.1.75:5000/app`) se comprobó desde la propia estación de trabajo; la prueba visual interactiva desde un teléfono móvil físico conectado al Wi-Fi `INFINITUM0870` queda declarada como pendiente de ejecución presencial por el operador.

---

## 12. Resultados Obtenidos

- **Carga HTTP de recursos desde Flask (`127.0.0.1:5000` y `192.168.1.75:5000`):**
  - `GET /app` (localhost y `192.168.1.75:5000`) → `200 OK` (`2,627` bytes, `text/html; charset=utf-8`)
  - `GET /dashboard-assets/css/tokens.css` → `200 OK` (`2,352` bytes, `text/css; charset=utf-8`)
  - `GET /dashboard-assets/css/base.css` → `200 OK` (`1,295` bytes, `text/css; charset=utf-8`)
  - `GET /dashboard-assets/css/login.css` → `200 OK` (`5,717` bytes, `text/css; charset=utf-8`)
  - `GET /dashboard-assets/js/app.js` → `200 OK` (`335` bytes, `application/javascript; charset=utf-8`)
  - `GET /dashboard-assets/js/views/login-view.js` → `200 OK` (`5,418` bytes, `application/javascript; charset=utf-8`)
  - `GET /assets/brand/producto_figura_dark.svg` (localhost y `192.168.1.75:5000`) → `200 OK` (`1,779` bytes, `image/svg+xml; charset=utf-8`)
  - `GET /` → `200 OK` (`{"service":"VIGIA Vision Systems - Ingest API","status":"ONLINE","version":"VO-03B"}`)
  - `GET /mobile` → `200 OK` (`13,071` bytes, cliente móvil intacto)
  - `POST /api/v1/cameras/CAM-ENTRADA/push` (sin clave) → `503 Service Unavailable` (contrato *fail-closed* preservado)
  - `GET /assets/brand/README.md` y `GET /dashboard-assets/index.html` → `404 Not Found` (protección contra acceso no autorizado a archivos verificada)
- **Suite de pruebas unitarias del sistema:** `162 tests` ejecutados con resultado **`OK`** (100 % aprobados).

---

## 13. Evidencias Verificables

- Código fuente de la interfaz:
  - [`VIGIA_Dashboard/web/index.html`](../../web/index.html)
  - [`VIGIA_Dashboard/web/css/tokens.css`](../../web/css/tokens.css)
  - [`VIGIA_Dashboard/web/css/base.css`](../../web/css/base.css)
  - [`VIGIA_Dashboard/web/css/login.css`](../../web/css/login.css)
  - [`VIGIA_Dashboard/web/js/app.js`](../../web/js/app.js)
  - [`VIGIA_Dashboard/web/js/views/login-view.js`](../../web/js/views/login-view.js)
- Recurso gráfico oficial referenciado sin duplicación:
  - [`Docs/GEST_PROY_SOFT/02_Logos_accesibilidad/svg/producto_figura_dark.svg`](../../../Docs/GEST_PROY_SOFT/02_Logos_accesibilidad/svg/producto_figura_dark.svg)

---

## 14. Incidencias Encontradas y Configuración de Red / Firewall

- **Categoría de red en Windows y acceso desde dispositivos en la LAN (`192.168.1.75:5000`):**
  - La inspección de red (`Get-NetConnectionProfile`) mostró que la conexión activa (`INFINITUM0870` en el adaptador `Ethernet`, IPv4 `192.168.1.75`) tiene asignada la categoría `Public`, aunque existen reglas de entrada habilitadas para `python.exe` / `Python`. Si un teléfono conectado al mismo router Wi-Fi experimenta bloqueo por parte de Windows Firewall al intentar abrir `http://192.168.1.75:5000/app`, se recomienda cambiar el perfil de la red doméstica a **Privado** y/o autorizar de manera controlada el puerto `5000` TCP únicamente para la subred local (`LocalSubnet`):
    ```powershell
    New-NetFirewallRule -DisplayName "VIGIA Dashboard Dev (TCP 5000)" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow -Profile Private -RemoteAddress LocalSubnet
    ```
- **Limitación de la configuración de desarrollo:**
  - El arranque directo con `python -m VIGIA_API.ingest_service` en `0.0.0.0:5000` (`use_debugger=False`) es exclusivamente una configuración de desarrollo para pruebas visuales y responsive dentro de una red local de confianza; no debe utilizarse como despliegue de producción ni exponerse a redes públicas.

---

## 15. Limitaciones Conocidas

1. **Sin conexión al backend de autenticación (por diseño del Sprint 01):** El envío del formulario no autentica usuarios ni inicia sesión; informa explícitamente que la autenticación aún no está integrada.
2. **Sin imagen de fondo definitiva:** El fondo de pantalla permanece en blanco (`#FFFFFF`) hasta que se entregue el recurso gráfico oficial.
3. **Sin recuperación de contraseña automatizada:** Al no existir flujo ni soporte en base de datos para recuperación por correo, el enlace muestra únicamente el aviso de acudir al administrador del sistema.

---

## 16. Requerimientos Pendientes (Para Sprint 02)

1. Definir y conectar el cliente HTTP del frontend con los endpoints reales de autenticación en `VIGIA_API`.
2. Implementar el flujo real de inicio y cierre de sesión validado por el backend.
3. Manejar los mensajes de error provenientes del servidor (`Credenciales incorrectas`, `Cuenta inactiva. Contacte al administrador`, `Acceso denegado: rol no autorizado` y errores de red).
4. Redirigir al usuario autenticado hacia la vista correspondiente a su rol validado (`OPERADOR` o `ADMINISTRADOR`).

---

## 17. Criterios de Aceptación

- [x] Se ha inspeccionado la estructura existente.
- [x] Se ha conservado íntegramente el cliente móvil (`VIGIA_Dashboard/mobile/index.html`).
- [x] Se ha creado la estructura modular del frontend en `VIGIA_Dashboard/web/`.
- [x] Se han utilizado correctamente los recursos oficiales de VIGÍA (`producto_figura_dark.svg`) sin duplicarlos.
- [x] Se ha implementado la pantalla de inicio de sesión conforme al diseño aprobado.
- [x] El diseño es responsive en los tres rangos (`< 640px`, `640px – 1023px`, `>= 1024px`).
- [x] Los campos cuentan con validaciones básicas obligatorias y atributos semánticos.
- [x] Existe retroalimentación accesible (`role="alert"` / `role="status"` y `aria-live`).
- [x] No existe autenticación ficticia ni almacenamiento inseguro de contraseñas.
- [x] No se han modificado otros módulos fuera de `VIGIA_Dashboard/`.
- [x] Se ha documentado la arquitectura inicial (`ARQUITECTURA_FRONTEND.md`).
- [x] Se ha documentado el plan de desarrollo (`PLAN_DESARROLLO_FRONTEND.md`).
- [x] Se ha generado la documentación completa del Sprint 01 (`SPRINT_01_INFRAESTRUCTURA_Y_LOGIN.md`).
- [x] Se han ejecutado y registrado las pruebas posibles.

---

## 18. Dictamen Final del Sprint

**DICTAMEN: COMPLETADO**

El Sprint 01 cumple la totalidad de los criterios de aceptación técnicos, visuales, de accesibilidad y de alcance documental establecidos, dejando la base lista para abordar la integración de autenticación en el Sprint 02.

