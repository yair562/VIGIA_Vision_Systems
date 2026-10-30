# Documentación Técnica del Frontend — `VIGIA_Dashboard`

Bienvenido al espacio documental exclusivo del módulo **`VIGIA_Dashboard`** de **VIGÍA Vision Systems**.

Esta carpeta centraliza el diseño arquitectónico, la planificación evolutiva y el seguimiento verificable por sprints de la interfaz de usuario, manteniendo su control de avance independiente de la documentación general del sistema.

---

## 1. Índice de Documentos

| Documento | Descripción | Estado |
| :--- | :--- | :---: |
| [`PLAN_DESARROLLO_FRONTEND.md`](./PLAN_DESARROLLO_FRONTEND.md) | Planificación evolutiva del frontend estructurada por sprints, con objetivos, entregables y estado actual. | Vigente |
| [`ARQUITECTURA_FRONTEND.md`](./ARQUITECTURA_FRONTEND.md) | Definición técnica de la arquitectura modular en HTML5, CSS3 y JS Vanilla ES6, estrategia responsive, uso de recursos oficiales y límites de responsabilidad. | Vigente |
| [`SISTEMA_DISENO.md`](./SISTEMA_DISENO.md) | Tokens visuales, paleta en Modo Claro y Modo Oscuro, tipografía, radios, espaciados y componentes reutilizables. | Vigente |
| [`NAVEGACION_Y_RUTAS.md`](./NAVEGACION_Y_RUTAS.md) | Secciones administrativas, identificadores de navegación, rutas previstas y comportamiento de botones. | Vigente |
| [`MODO_DEMO.md`](./MODO_DEMO.md) | Origen de los datos sintéticos DEMO, separación con `VIGIA_API`, restricciones de persistencia y mecanismo de previsualización. | Vigente |
| [`sprints/SPRINT_01_INFRAESTRUCTURA_Y_LOGIN.md`](./sprints/SPRINT_01_INFRAESTRUCTURA_Y_LOGIN.md) | Registro técnico detallado del Sprint 01: infraestructura visual y pantalla de inicio de sesión. | Completado |
| [`sprints/SPRINT_02A_GESTION_DISPOSITIVOS.md`](./sprints/SPRINT_02A_GESTION_DISPOSITIVOS.md) | Registro técnico detallado del Sprint 02A: interfaz administrativa de Gestión de Dispositivos en Modo DEMO. | Completado |

---

## 2. Convenciones de Seguimiento por Sprints

Cada sprint del frontend genera un documento individual dentro del directorio [`sprints/`](./sprints/) siguiendo la nomenclatura:

```text
SPRINT_<NN>_<NOMBRE_DESCRIPTIVO>.md
```

Todo informe de sprint documenta únicamente funcionalidades implementadas y verificadas, registrando explícitamente las limitaciones vigentes y los requerimientos que pasan al siguiente sprint.

