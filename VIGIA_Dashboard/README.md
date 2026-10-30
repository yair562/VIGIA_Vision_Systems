# VIGIA_Dashboard

**Interfaz Web de Supervisión Operativa, Monitoreo Visual y Administración de VIGÍA Vision Systems**

---

## 1. Propósito del Módulo

`VIGIA_Dashboard` es el módulo encargado de las interfaces de usuario de **VIGÍA Vision Systems**. Su propósito es ofrecer una aplicación web única, ligera, accesible y adaptable (responsive) para que los dos perfiles operativos del sistema puedan desempeñar sus funciones:

- **Guardia (`OPERADOR`):** supervisión en tiempo real de cámaras, visualización de detecciones vehiculares y matrículas, atención de alertas y control supervisado de accesos.
- **Administrador (`ADMINISTRADOR`):** gestión de usuarios, cámaras, flujos de video, áreas de visión (ROI), padrón vehicular y consulta histórica/estadística de eventos.

Asimismo, el módulo aloja el cliente ligero de captura móvil (`mobile/index.html`) empleado en las pruebas operativas de ingesta de fotogramas hacia `VIGIA_API`.

---

## 2. Responsabilidad del Frontend

- Presentar las vistas e interacciones de usuario respetando la identidad visual y los criterios de accesibilidad WCAG 2.1 definidos en el proyecto.
- Validar la entrada del usuario en el cliente antes de realizar peticiones de red.
- Consumir de forma desacoplada los contratos HTTP que exponga `VIGIA_API`, sin contener lógica de negocio crítica, reglas de autorización definitivas ni acceso directo a la base de datos o al motor de visión.
- Garantizar una experiencia fluida y consistente en teléfonos móviles (`< 640px`), tabletas (`640px – 1023px`) y monitores de escritorio (`>= 1024px`).

---

## 3. Tecnologías Utilizadas

El desarrollo de `VIGIA_Dashboard` se basa exclusivamente en estándares web nativos, sin frameworks de frontend, gestores de paquetes (`npm`/`Node.js`) ni empaquetadores (`bundlers`):

- **HTML5 semántico:** estructura accesible con etiquetas nativas, roles ARIA (`role="alert"`, `role="status"`, `aria-live`) y soporte para navegación completa por teclado.
- **CSS3 moderno:** variables nativas (CSS Custom Properties), diseño mediante `CSS Grid` y `Flexbox`, y consultas de medios (`@media`) para los tres rangos de pantalla.
- **JavaScript Vanilla (ES6+):** arquitectura modular basada en **ES Modules** (`<script type="module">`) con separación clara entre el inicializador de la aplicación y los controladores de cada vista.

---

## 4. Estructura de Directorios

```text
VIGIA_Dashboard/
├── README.md                                     # Descripción general y guía rápida del módulo
├── mobile/
│   └── index.html                                # Cliente móvil de captura e ingesta de fotogramas (VO-03)
├── web/
│   ├── index.html                                # Punto de entrada de la interfaz web (Login + Administración DEMO)
│   ├── assets/
│   │   └── backgrounds/
│   │       └── README.md                         # Espacio reservado para la futura imagen de fondo
│   ├── css/
│   │   ├── tokens.css                            # Variables CSS (Modo Claro, Modo Oscuro, tipografía, espaciados)
│   │   ├── base.css                              # Reset base, foco accesible (:focus-visible) y utilidades (.sr-only)
│   │   ├── login.css                             # Estilos del diseño aprobado de Inicio de Sesión
│   │   └── admin-devices.css                     # Estilos de Administración y Gestión de Dispositivos (Sprint 02A)
│   └── js/
│       ├── app.js                                # Punto de entrada JavaScript (ES Module)
│       ├── router.js                             # Enrutador hash (#login, #devices, #cameras, #alerts, #reports, #profile)
│       ├── data/
│       │   └── devices-demo-data.js              # Conjunto de dispositivos sintéticos DEMO (Sprint 02A)
│       ├── services/
│       │   └── device-service.js                 # Interfaz de servicio de dispositivos desacoplada
│       ├── components/
│       │   ├── admin-navbar.js                   # Barra de navegación superior reutilizable del administrador
│       │   └── devices-table.js                  # Cuadrícula de 5 columnas con bloques rectangulares grises
│       └── views/
│           ├── login-view.js                     # Controlador de Inicio de Sesión (Sprint 01)
│           └── devices-view.js                   # Vista de Gestión de Dispositivos (Sprint 02A)
└── Docs/
    ├── README.md                                 # Índice de la documentación exclusiva del frontend
    ├── PLAN_DESARROLLO_FRONTEND.md               # Hoja de ruta y planificación por sprints del frontend
    ├── ARQUITECTURA_FRONTEND.md                  # Arquitectura técnica, convenciones y límites del módulo
    ├── SISTEMA_DISENO.md                         # Tokens visuales, Modo Claro/Oscuro, componentes y responsive
    ├── NAVEGACION_Y_RUTAS.md                     # Secciones administrativas, rutas e identificadores
    ├── MODO_DEMO.md                              # Datos sintéticos, separación DEMO/API y previsualización
    └── sprints/
        ├── SPRINT_01_INFRAESTRUCTURA_Y_LOGIN.md  # Informe técnico y evidencias del Sprint 01
        └── SPRINT_02A_GESTION_DISPOSITIVOS.md    # Informe técnico y evidencias del Sprint 02A
```

---

## 5. Cómo Ejecutar o Visualizar la Interfaz durante el Desarrollo

El frontend se sirve de forma integrada desde el servicio Flask de `VIGIA_API` ([`VIGIA_API/ingest_service.py`](../VIGIA_API/ingest_service.py)), coexistiendo sin interferencias con las rutas actuales de diagnóstico (`GET /`), captura móvil (`GET /mobile`) e ingesta (`POST /api/v1/cameras/<codigo_camara>/push`).

### 5.1. Rutas del Dashboard en Flask

- `GET /app`: sirve la pantalla principal de `VIGIA_Dashboard` ([`web/index.html`](./web/index.html)).
- `GET /dashboard-assets/<path:filename>`: sirve de forma controlada los archivos CSS y módulos ES6 autorizados de `web/`:
  - `/dashboard-assets/css/tokens.css`
  - `/dashboard-assets/css/base.css`
  - `/dashboard-assets/css/login.css`
  - `/dashboard-assets/js/app.js`
  - `/dashboard-assets/js/views/login-view.js`
- `GET /assets/brand/<filename>`: sirve en modo solo lectura exclusivamente los 8 archivos SVG oficiales de identidad visual ubicados en `Docs/GEST_PROY_SOFT/02_Logos_accesibilidad/svg/` (por ejemplo, `/assets/brand/producto_figura_dark.svg`), sin duplicarlos ni permitir acceso arbitrario al sistema de archivos.

### 5.2. Comando de Arranque del Servicio (Escucha en Red Local `0.0.0.0:5000`)

1. Abrir una terminal en la raíz del repositorio (`VIGIA_Vision_Systems/`):
   ```powershell
   cd c:\GEST.PROY.TI\Software\VIGIA_Vision_Systems
   ```
2. Iniciar el servidor de desarrollo Flask (configurado con `use_debugger=False`, `host="0.0.0.0"`, `port=5000` y modo DEMO **deshabilitado por defecto**):
   ```powershell
   # Arranque estándar (solo Inicio de Sesión; modo DEMO deshabilitado por defecto):
   .\.venv\Scripts\python.exe -m VIGIA_API.ingest_service

   # Arranque con previsualización DEMO habilitada explícitamente para desarrollo (PC y LAN):
   $env:VIGIA_ENABLE_FRONTEND_DEMO = "1"
   .\.venv\Scripts\python.exe -m VIGIA_API.ingest_service
   ```

### 5.3. Acceso desde la Computadora y desde Teléfono Móvil (LAN)

- **Dirección IPv4 LAN detectada (`ipconfig`):** `192.168.1.75` (adaptador `Ethernet` conectado a la red local `INFINITUM0870`, puerta de enlace `192.168.1.254`).
- **Pantalla de Inicio de Sesión (Sprint 01):**
  - Computadora: `http://127.0.0.1:5000/app` (o `http://127.0.0.1:5000/app#login`)
  - Teléfono móvil (red local): `http://192.168.1.75:5000/app`
- **Previsualización de Gestión de Dispositivos — Administrador en Modo DEMO (Sprint 02A):**
  - Computadora (Modo Claro): `http://127.0.0.1:5000/app#devices`
  - Computadora (Modo Oscuro): `http://127.0.0.1:5000/app?theme=dark#devices`
  - Teléfono móvil (red local): `http://192.168.1.75:5000/app#devices`
  *(No utilizar `127.0.0.1` ni `0.0.0.0` en el navegador del teléfono).*

### 5.4. Consideraciones de Red Local y Firewall de Windows

- **Categoría de red y Firewall:** Si el adaptador de red en Windows está clasificado como `Public` o si el ejecutable `.venv\Scripts\python.exe` no cuenta aún con permiso de entrada en el puerto `5000`, el teléfono podría no alcanzar el servidor. Para habilitar el acceso de forma controlada únicamente en la subred local sin desactivar Windows Firewall:
  1. Cambiar el perfil de la red doméstica/laboratorio a **Privado** (`Configuración -> Red e Internet -> Propiedades -> Perfil de red: Privado`).
  2. Si se requiere abrir explícitamente el puerto `5000` TCP para el perfil privado en una consola PowerShell como Administrador:
     ```powershell
     New-NetFirewallRule -DisplayName "VIGIA Dashboard Dev (TCP 5000)" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow -Profile Private -RemoteAddress LocalSubnet
     ```
- **Limitación de entorno de desarrollo:** Este arranque directo con Werkzeug (`python -m VIGIA_API.ingest_service` en `0.0.0.0:5000`) está destinado exclusivamente a pruebas visuales y responsive en una red local de confianza; no constituye una configuración de producción ni debe exponerse a Internet.

> **Nota sobre el cliente móvil de captura (`VO-03`):**  
> El archivo [`mobile/index.html`](./mobile/index.html) se conserva intacto y continúa disponible simultáneamente en `GET /mobile`.

---

## 6. Estado Actual del Desarrollo

- **Sprints completados:**
  - **Sprint 01 — Infraestructura visual y pantalla de inicio de sesión (COMPLETADO).**
  - **Sprint 02A — Interfaz de Gestión de Dispositivos (Administrador — Modo DEMO) (COMPLETADO).**
- **Funcionalidades disponibles:**
  - Pantalla de Inicio de Sesión fiel al wireframe aprobado, integrada con el logotipo oficial `producto_figura_dark.svg`.
  - Estructura general del Administrador, barra de navegación superior reutilizable (`Dispositivos`, `Cámaras`, `Alertas`, `Informes`, `Perfil`) y pantalla **Gestión de Dispositivos** con cuadrícula de 5 columnas, 7 registros sintéticos DEMO, botones `Visualización de Cámaras` y `Agregar Dispositivos` (con formulario provisional DEMO) y soporte para Modo Claro y Modo Oscuro.
  - Adaptación responsiva en móvil (`< 640px`), tableta (`640px – 1023px`) y escritorio (`>= 1024px`).

---

## 7. Referencias a la Documentación Técnica del Frontend

- [Índice de Documentación del Frontend (`Docs/README.md`)](./Docs/README.md)
- [Plan de Desarrollo del Frontend (`Docs/PLAN_DESARROLLO_FRONTEND.md`)](./Docs/PLAN_DESARROLLO_FRONTEND.md)
- [Arquitectura del Frontend (`Docs/ARQUITECTURA_FRONTEND.md`)](./Docs/ARQUITECTURA_FRONTEND.md)
- [Sistema de Diseño (`Docs/SISTEMA_DISENO.md`)](./Docs/SISTEMA_DISENO.md)
- [Navegación y Rutas (`Docs/NAVEGACION_Y_RUTAS.md`)](./Docs/NAVEGACION_Y_RUTAS.md)
- [Modo DEMO (`Docs/MODO_DEMO.md`)](./Docs/MODO_DEMO.md)
- [Reporte del Sprint 01 (`Docs/sprints/SPRINT_01_INFRAESTRUCTURA_Y_LOGIN.md`)](./Docs/sprints/SPRINT_01_INFRAESTRUCTURA_Y_LOGIN.md)
- [Reporte del Sprint 02A (`Docs/sprints/SPRINT_02A_GESTION_DISPOSITIVOS.md`)](./Docs/sprints/SPRINT_02A_GESTION_DISPOSITIVOS.md)
