# Plan de Desarrollo del Frontend — `VIGIA_Dashboard`

**Proyecto:** VIGÍA Vision Systems  
**Módulo:** `VIGIA_Dashboard`  
**Enfoque tecnológico:** HTML5 + CSS3 + JavaScript Vanilla ES6 (ES Modules) — Responsive Web Design

---

## 1. Objetivo del Plan

Establecer una hoja de ruta incremental, trazable y verificable para el desarrollo de la aplicación web responsiva de **VIGÍA Vision Systems**, asegurando el desacoplamiento respecto al backend (`VIGIA_API`), el motor de visión (`VIGIA_Vision`) y la capa de dominio (`VIGIA_Core`).

---

## 2. Resumen de Estado por Sprints

| Sprint | Nombre | Objetivo Principal | Estado | Documento de Evidencia |
| :---: | :--- | :--- | :---: | :--- |
| **Sprint 01** | Infraestructura visual y login | Estructura inicial, identidad visual, pantalla de inicio de sesión responsiva y documentación base. | **COMPLETADO** | [`SPRINT_01_INFRAESTRUCTURA_Y_LOGIN.md`](./sprints/SPRINT_01_INFRAESTRUCTURA_Y_LOGIN.md) |
| **Sprint 02** | Integración de autenticación | Conexión real con la API de autenticación, manejo de sesión, errores y redirección por rol validado. | Pendiente | *Se generará en Sprint 02* |
| **Sprint 03** | Interfaz del Guardia | Panel operativo para el rol `OPERADOR` (Guardia), visualización de cámaras, detecciones y estados de acceso. | Pendiente | *Se generará en Sprint 03* |
| **Sprint 04** | Interfaz del Administrador | Panel administrativo para el rol `ADMINISTRADOR`, gestión de usuarios, cámaras y consultas operativas. | Pendiente | *Se generará en Sprint 04* |
| **Sprint 05** | Integración y refinamiento | Integración de extremo a extremo de vistas, validación responsive integral, accesibilidad y cierre de defectos. | Pendiente | *Se generará en Sprint 05* |

---

## 3. Desglose Preliminar de Sprints

### Sprint 01 — Infraestructura visual y login *(Actual — Completado)*
- Definición y creación de la estructura inicial de directorios en `VIGIA_Dashboard/web/` y `VIGIA_Dashboard/Docs/`.
- Conservación íntegra del cliente móvil de captura existente (`VIGIA_Dashboard/mobile/index.html`).
- Integración de los tokens visuales de diseño (`tokens.css`) y del símbolo oficial de VIGÍA (`producto_figura_dark.svg`) sin duplicar archivos originales.
- Implementación de la pantalla de Inicio de Sesión conforme al wireframe aprobado.
- Adaptación responsiva en los tres rangos definidos: móvil (`< 640px`), tableta (`640px – 1023px`) y escritorio (`>= 1024px`).
- Validación de campos obligatorios, estados de carga y retroalimentación accesible sin simular sesiones ni inventar credenciales.
- Establecimiento de la documentación técnica base del frontend.

### Sprint 02 — Integración de autenticación *(Pendiente)*
- Definición y consumo del contrato real de comunicación con `VIGIA_API` para autenticación.
- Implementación del flujo real de inicio y cierre de sesión contra el backend.
- Manejo seguro del estado de sesión en el cliente sin almacenar contraseñas en `localStorage` ni `sessionStorage`.
- Tratamiento de errores reales del servidor y de red (credenciales incorrectas, cuenta inactiva, rol no autorizado, error de conexión).
- Enrutamiento inicial hacia la vista correspondiente según los permisos e identidad validados por el backend (`OPERADOR` o `ADMINISTRADOR`).

### Sprint 03 — Interfaz del Guardia *(Pendiente)*
- Diseño e implementación de la estructura de navegación para el rol Guardia (`OPERADOR`).
- Construcción del panel operativo adaptable a móvil, tableta y escritorio.
- Componentes para visualización de cámaras y flujo de supervisión.
- Presentación clara de la información de detecciones vehiculares y lecturas de matrículas.
- Representación visual de los estados de operación y acceso del sistema.

### Sprint 04 — Interfaz del Administrador *(Pendiente)*
- Diseño e implementación del panel administrativo para el rol `ADMINISTRADOR`.
- Interfaz para la gestión de usuarios, conforme a las operaciones que habilite el backend.
- Interfaz para el registro, consulta, configuración y activación/desactivación de cámaras y áreas de visión.
- Visualización de bitácoras, eventos de acceso e información administrativa.

### Sprint 05 — Integración y refinamiento *(Pendiente)*
- Integración completa de la navegación entre el inicio de sesión y los paneles operativos/administrativos.
- Incorporación de la imagen de fondo definitiva de inicio de sesión cuando esté disponible mediante la variable `--login-bg-image`.
- Validación exhaustiva de adaptabilidad responsive en dispositivos móviles, tabletas y pantallas de escritorio.
- Auditoría de accesibilidad (navegación por teclado, contraste, lectores de pantalla).
- Pruebas integrales de interacción y corrección de defectos.

---

## 4. Reglas de Gobernanza para Sprints Futuros

1. Cada sprint abordará únicamente los objetivos y requerimientos autorizados para su iteración.
2. Ninguna funcionalidad se documentará como implementada antes de haber sido codificada y verificada.
3. Se preservará la arquitectura modular basada en HTML5, CSS3 y JavaScript Vanilla ES6.
4. Al cierre de cada sprint se actualizará la tabla de seguimiento de este documento y se añadirá el informe correspondiente en `VIGIA_Dashboard/Docs/sprints/`.

