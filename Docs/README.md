# VIGIA Vision Systems — Repositorio Central de Documentación

Bienvenido a la base de documentación técnica, arquitectónica y metodológica de **VIGIA Vision Systems**.

---

## 1. Propósito de la Documentación

El propósito fundamental de este directorio es actuar como la **fuente única de verdad** técnica para el diseño, evolución y gobernanza de la plataforma.

En proyectos de alta complejidad que combinan Visión Artificial, Inteligencia Artificial, Hardware IoT, Microcontroladores, Automatización en tiempo real y Sistemas Web, la ausencia de especificaciones formales genera silos de trabajo, dependencias circulares y deuda técnica inmediata.

Esta documentación garantiza que:
* Las responsabilidades de cada módulo y de cada integrante estén formalmente delimitadas.
* Las decisiones arquitectónicas se fundamenten en principios de ingeniería de software sólidos (desacoplamiento, abstracción de hardware y modelos).
* La transición desde el prototipo actual (`VR_Semaforo`) hacia la arquitectura definitiva de `VIGIA` ocurra de manera metódica y controlada.
* Los contratos de interfaz y eventos se definan antes de la implementación de código dependiente.

---

## 2. Mapa de Progresión Conceptual

Para comprender la plataforma de forma lógica y estructurada, la documentación está diseñada para profundizar progresivamente a través del siguiente orden de lectura:

```text
┌──────────────────────────────────────┐
│     01 — Estructura del Proyecto     │ ──> ¿Quién es responsable de qué?
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│    02 — Arquitectura del Sistema     │ ──> ¿Cómo se relacionan los módulos?
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│          03 — Roadmap                │ ──> ¿En qué orden construiremos el sistema?
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│     04 — Estándares de Desarrollo    │ ──> ¿Cómo debe escribirse y mantenerse el código?
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│   05 — Planificación y Ejecución     │ ──> ¿Cómo nos organizamos y ejecutamos en paralelo?
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│      06 — Propuesta del Proyecto     │ ──> ¿Cuál es la visión ejecutiva e impacto del proyecto?
└──────────────────────────────────────┘
```

---

## 3. Organización de los Documentos

La documentación se estructura en documentos temáticos numerados de forma secuencial:

| Documento | Título | Pregunta Central | Estado | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| **[01](file:///home/yair/VIGIA_Vision_Systems/Docs/01_estructura_del_proyecto.md)** | **Estructura del Proyecto** | *¿Quién es responsable de qué?* | `Activo / Fase 0` | Organización de carpetas del repositorio, responsabilidades técnicas por directorio, código admitido vs. prohibido por módulo, límites de responsabilidad y ownership del equipo. |
| **[02](file:///home/yair/VIGIA_Vision_Systems/Docs/02_arquitectura_del_sistema.md)** | **Arquitectura del Sistema** | *¿Cómo se relacionan los módulos?* | `Activo / Fase 0` | Arquitectura conceptual global, ciclo *Perceive → Process → Analyze → Decide → Act → Record*, delimitación de `VIGIA_Core` (autoridad de estado y seguridad) frente a `VIGIA_Automation` (políticas y reglas), persistencia basada en puertos/adaptadores, contrato bidireccional IoT con ACKs y fundamentación del Patrón Mediador ($O(N)$ vs $O(N^2)$). |
| **[03](file:///home/yair/VIGIA_Vision_Systems/Docs/03_roadmap_de_desarrollo_orientado_a_capacidades.md)** | **Roadmap Orientado a Capacidades** | *¿En qué orden y bajo qué criterios verificables adquiere VIGIA capacidades reales en el entorno físico?* | `Activo / Fase 0` | Hoja de ruta estratégica por capacidades físicas demostrables (Fase 0 a Fase 8), criterios de avance por evidencia, matriz de casos límite y trazabilidad de ingeniería. *(Alias: [`03_roadmap.md`](file:///home/yair/VIGIA_Vision_Systems/Docs/03_roadmap.md))* |
| **[04](file:///home/yair/VIGIA_Vision_Systems/Docs/04_estandares_de_desarrollo.md)** | **Estándares de Desarrollo** | *¿Cómo debe escribirse y mantenerse el código?* | `Activo / Fase 0` | Guías de codificación en Python, convenciones de Git, gestión de configuración y variables de entorno, logging estructurado, manejo de excepciones y filosofía de testing sin hardware físico. |
| **[05](file:///home/yair/VIGIA_Vision_Systems/Docs/05_marco_de_planificacion_y_ejecucion.md)** | **Marco de Planificación y Ejecución** | *¿Cómo nos organizamos, planificamos y ejecutamos en paralelo sin bloqueos?* | `Activo / Sprint 0` | Tríada Roadmap/Cronograma/Contratos, Scrum con desarrollo paralelo por Workstreams (A–I), regla de no bloqueo mediante contratos e interfaces, asignación de roles del equipo y objetivos/DoD del Sprint 0. |
| **[06](file:///home/yair/VIGIA_Vision_Systems/Docs/06_propuesta_del_proyecto.md)** | **Propuesta del Proyecto** | *¿Qué es VIGIA, qué problema resuelve y qué valor demuestra en el caso rector?* | `Activo / Propuesta` | Propuesta ejecutiva y académica de 2–3 páginas: misión, visión, propuesta de valor, planteamiento del problema, caso rector de caseta inteligente, alcance y proyección a futuro. |

---

## 4. Convenciones Utilizadas

Para preservar la calidad, claridad y coherencia en toda la documentación técnica, se aplican las siguientes reglas:

### 4.1 Estados de Documentos
Cada documento formal incluye un encabezado con su estado de ciclo de vida:
* `Borrador (Draft)`: Documento en fase de redacción o discusión preliminar.
* `Propuesta (Proposal)`: Documento sometido a revisión del equipo o arquitecto de software.
* `Activo / Congelado (Frozen/Active)`: Documento aprobado que rige el desarrollo actual. Cualquier alteración a una interfaz congelada requiere justificación técnica formal.

### 4.2 Diagramas y Modelado
* **Diagramas conceptuales y de flujo:** Se estructuran preferentemente en texto plano con bloques ASCII o en sintaxis `mermaid` para garantizar su versionabilidad en Git.
* **Flujos de datos:** Se representan con flechas direccionales unívocas indicando el emisor del evento y el consumidor de la acción.

### 4.3 Tipografía y Referencias
* Los nombres de módulos del sistema se escriben con mayúsculas y guiones bajos: `VIGIA_Core`, `VIGIA_Vision`, `VIGIA_IoT`, etc.
* Los componentes o archivos de código se denotan en formato monoespaciado: `README.md`, `requirements.txt`, etc.
* Los roles del equipo y responsabilidades se documentan de forma explícita, separando estrictamente la responsabilidad conceptual del acoplamiento técnico personal.
