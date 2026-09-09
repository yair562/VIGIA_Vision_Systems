# VIGIA Vision Systems

## 05 — Marco de Planificación y Ejecución

**Estado:** Activo / Fase 0 — Sprint 0  
**Versión:** 1.0  
**Pregunta Central:** *¿Cómo nos organizamos, planificamos y ejecutamos el desarrollo en paralelo sin bloqueos entre hardware, software y producto?*  
**Propósito:** Definir formalmente la distinción metodológica entre Roadmap, Cronograma y Contratos/Sprints, establecer el marco Scrum adaptado al desarrollo paralelo por dominios, oficializar los Workstreams, reglar la no-dependencia temporal mediante contratos de interfaz y fijar los entregables y responsabilidades del Sprint 0.

---

# 1. Distinción entre Roadmap, Cronograma y Contratos/Sprints

VIGIA utiliza tres niveles complementarios de planificación y ejecución. Cada nivel responde a una pregunta diferente y no debe sustituir a los demás.

```text
ROADMAP
¿Qué capacidades adquirirá VIGIA y en qué orden?
              │
              ▼
CRONOGRAMA
¿Cuándo trabajará cada equipo y qué entregará?
              │
              ▼
CONTRATOS / SPRINTS
¿Quién es responsable de cada entregable y cómo se acepta?
```

### 1.1 Roadmap (Estratégico)
El **Roadmap** define la evolución funcional y técnica de VIGIA a nivel estratégico.
Su función principal es establecer:
* Qué capacidades debe adquirir VIGIA en el mundo físico.
* En qué orden evolucionarán dichas capacidades.
* Qué dependencias conceptuales existen entre ellas.
* Cuáles son las etapas principales de maduración del sistema.

> **Regla Rectoral:** El Roadmap **no define fechas, asignaciones individuales ni tareas detalladas**. Permanece orientado estrictamente a capacidades y no debe convertirse en un cronograma operativo.

### 1.2 Cronograma (Temporal)
El **Cronograma** transforma el Roadmap en un plan temporal de ejecución.
Su función es establecer:
* Cuándo se trabajará cada línea de trabajo.
* Qué Workstreams estarán activos en cada período.
* Qué entregables se esperan de cada equipo o especialista.
* Cuándo deberán producirse las sesiones de integración entre dominios.
* Qué hitos temporales permiten avanzar hacia las siguientes etapas.

> **Regla de Adaptabilidad:** El Cronograma puede modificarse conforme cambien las estimaciones, prioridades o restricciones del proyecto, **sin alterar necesariamente el Roadmap**.

### 1.3 Contratos y Sprints (Operativo y de Compromiso)
Los **contratos de trabajo y los Sprints** convierten los objetivos del cronograma en responsabilidades ejecutables y auditables.
Definen:
* **Quién** es responsable de cada entregable.
* **Qué** debe producir con exactitud.
* **Qué criterios de aceptación** técnicos y funcionales debe cumplir.
* **Qué evidencia tangible** debe presentar (código, pruebas, logs, videos, esquemáticos).
* **Cuándo** debe entregar el resultado acordado.
* **Cómo** se determina formalmente que el trabajo está terminado (*Definition of Done*).

> Los contratos establecen responsabilidades individuales o por dominio técnico, mientras que los Sprints organizan la ejecución iterativa, la inspección y la adaptación del trabajo.

---

# 2. Metodología Oficial de Trabajo

VIGIA adopta oficialmente:

> **Scrum como marco de trabajo ágil, con desarrollo paralelo por dominios y coordinación mediante un Roadmap común de capacidades.**

La utilización de Scrum no implica que todo el equipo deba trabajar sobre la misma tarea durante cada Sprint. VIGIA organiza el trabajo mediante **Workstreams especializados**, manteniendo un **Product Backlog común** y realizando coordinación, revisión e integración periódica.

```text
                    PRODUCT BACKLOG
                          │
                          ▼
                   SPRINT PLANNING
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
       PRODUCT         SOFTWARE         HARDWARE
          │               │                │
          ▼               ▼                ▼
       Sprint          Sprint           Sprint
          │               │                │
          └───────────────┼────────────────┘
                          ▼
                    SPRINT REVIEW
                          │
                          ▼
                 INTEGRACIÓN / DEMO
                          │
                          ▼
                    RETROSPECTIVA
```

La coordinación central se realiza mediante:
1. **Objetivos comunes de Sprint:** Cada iteración contribuye a una capacidad o hito claro.
2. **Interfaces definidas previamente:** Contratos de datos y eventos congelados antes de codificar.
3. **Criterios de aceptación compartidos:** Definición inequívoca de éxito.
4. **Puntos de integración periódicos:** Demos conjuntas donde los componentes convergen.

---

# 3. Principio de Desarrollo Paralelo

VIGIA adopta explícitamente el principio rector:

> **Los dominios pueden avanzar en paralelo siempre que sus interfaces, responsabilidades y criterios de integración estén formalmente definidos.**

El desarrollo de un dominio no debe bloquear innecesariamente a otro. Durante una misma iteración pueden ejecutarse simultáneamente los diferentes frentes:

```text
AI / COMPUTER VISION
Investigación
Benchmark
Modelos
Preparación de datos
          │
          │
          ├───────────────┐
          │               │
          ▼               ▼
HARDWARE / IoT         BACKEND
Prototipos             Modelos de datos
Sensores               API
Actuadores             Persistencia
Comunicación           Lógica de estado
          │               │
          └───────┬───────┘
                  │
                  ▼
              FRONTEND
              UX/UI
              Dashboard
              Estados del sistema
```

Mientras tanto, la capa de **Producto y Arquitectura**:
```text
PRODUCTO / ARQUITECTURA
Requisitos ──► Priorización ──► Arquitectura ──► Decisiones técnicas
```
coordina la dirección general del producto y mantiene alineados los diferentes dominios sin fisuras conceptuales.

---

# 4. Workstreams Oficiales

El trabajo y el cronograma de VIGIA se estructuran mediante 9 Workstreams especializados:

| ID | Workstream | Alcance Principal |
| :---: | :--- | :--- |
| **A** | **Product & Architecture** | Visión del producto, priorización del backlog, arquitectura sistémica, gobierno técnico y límites de módulos. |
| **B** | **AI / Computer Vision** | Captura de video, detección vehicular, localización de placas, LPR/OCR, datasets y benchmarks de inferencia. |
| **C** | **Backend** | Máquina de estados de carril, reglas de acceso, lógica de invariantes de seguridad, persistencia y servicios core. |
| **D** | **Frontend / Dashboard** | Interfaz web de supervisión operativa, renderizado en tiempo real, alertas y controles manuales autorizados. |
| **E** | **Hardware / IoT** | Circuitos embebidos, firmware (Arduino/ESP32), sensores físicos de presencia/carrera, servomotores y protocolo serial. |
| **F** | **DevOps / Infrastructure** | Entornos de desarrollo, pipelines de testing automatizado, contenedores ligeros para borde y empaquetado Edge. |
| **G** | **Data** | Modelado relacional de bitácoras, persistencia de evidencias, pipeline de datos dudosos y telemetría de rendimiento. |
| **H** | **Marketing / Market Research** | Investigación de mercado, perfiles de usuario, análisis de competencia, dimensionamiento de producto y viabilidad comercial. |
| **I** | **Institutional Web** | Presencia institucional del proyecto VIGIA, documentación pública, identidad de marca y portal de divulgación. |

Cada Workstream cuenta con:
* **Responsable principal** y participantes asignados.
* **Objetivos** específicos por fase e iteración.
* **Entregables** técnicos tangibles.
* **Dependencias** identificadas.
* **Criterios de aceptación** medibles.
* **Evidencias** requeridas para el cierre.
* **Puntos de integración** formal con los demás Workstreams.

> **Nota:** Los Workstreams no representan silos jerárquicos independientes, sino **líneas de trabajo especializadas y coordinadas dentro de un esfuerzo de ingeniería unificado**.

---

# 5. Regla de No Bloqueo

> **Una dependencia lógica entre dominios no debe interpretarse automáticamente como una dependencia temporal.**

```text
VISION ────────────────┐
                       │
HARDWARE ──────────────┼──► INTEGRACIÓN
                       │
BACKEND ───────────────┤
                       │
FRONTEND ──────────────┘
```

Para evitar cuellos de botella donde un equipo espera a otro para comenzar, los equipos deben desarrollar y validar sus componentes de forma desacoplada utilizando:

1. **Interfaces previamente definidas:** Contratos de modelos y firmas de métodos acordados en Fase 0.
2. **Datos simulados (*Fixtures*):** Lotes de imágenes pregrabadas o JSONs estáticos con observaciones sintéticas.
3. **Servicios Mock / Stubs:** Simuladores de microcontrolador o de backend que responden conforme al contrato acordado.
4. **Hardware de prueba en banco:** Maquetas de escritorio independientes del montaje físico final.
5. **Protocolos documentados:** Especificaciones byte a byte de tramas seriales y payloads de red.
6. **Contratos de integración:** Pruebas automatizadas de contrato que validan el cumplimiento de ambas partes.
7. **Criterios de aceptación:** Condiciones medibles que permiten declarar listo un módulo antes de conectarlo al resto.

La integración física y de software ocurre cuando los componentes individuales ya han sido validados contra sus contratos, eliminando sorpresas y bloqueos temporales.

---

# 6. Sprint 0 — Organización y Preparación

Antes de iniciar la construcción formal de las capacidades de VIGIA en el mundo real, se establece el **Sprint 0**, orientado exclusivamente a preparar la organización, los acuerdos técnicos y las condiciones de ingeniería.

### Objetivo del Sprint 0
> *Preparar al equipo, producto, arquitectura, herramientas, responsabilidades y mecanismos de trabajo necesarios para iniciar el desarrollo de VIGIA de manera coordinada y sin bloqueos.*

### Asignación de Roles y Responsabilidades en Sprint 0:

#### Product & Project Management
* **Yahir — Project Manager / CIO**
  * Gobierno inicial y marco de trabajo de VIGIA.
  * Definición y aplicación del marco Scrum adaptado.
  * Organización general del equipo y asignación formal de roles.
  * Preparación de los contratos de trabajo por entregables.
  * Coordinación general, facilitación de ceremonias y planificación inicial.

#### Product & Architecture
* **Josué — Product Owner / System Architect**
  * Construcción inicial y mantenimiento del Product Backlog central.
  * Definición funcional de las necesidades del producto (Caseta Inteligente).
  * Levantamiento de requisitos iniciales e historias de usuario base.
  * Definición de la arquitectura base del sistema y contratos de datos entre módulos.
  * Identificación temprana de dependencias críticas y resolución de decisiones arquitectónicas.

#### Hardware / IoT
* **Ernesto — CTO / Hardware & Embedded / IoT**
  * Arquitectura inicial del subsistema de hardware y control embebido.
  * Inventario técnico de componentes (microcontroladores, sensores, actuadores, fuentes de poder).
  * Identificación y selección de sensores de verificación física (finales de carrera, lazo magnético, presencia).
  * Revisión de protocolos de comunicación física (UART/Serial, tramas de comando, baudrates, timeouts).
  * Definición y montaje del banco de pruebas y entorno de prototipado físico.

#### AI / Computer Vision
* **Stephanie — AI / Computer Vision Engineer / Data Engineer**
  * Arquitectura inicial del pipeline de percepción visual.
  * Identificación de necesidades de datos (imágenes de placas, formatos de video, iluminación).
  * Investigación tecnológica y benchmarks de inferencia en hardware edge.
  * Definición inicial del pipeline de captura, preprocesamiento y estructuración de la observación.
* **Julio + Ever — Computer Vision Specialists**
  * Investigación técnica de modelos de detección vehicular y localización de matrículas.
  * Evaluación de alternativas de OCR ligero (Tesseract, EasyOCR, modelos dedicados).
  * Análisis de los algoritmos previos en `VR_Semaforo/vision/` para auditoría y rescate.
  * Apoyo técnico especializado a la definición del pipeline de visión.

> *Nota de Ingeniería:* Durante el Sprint 0 **no es obligatorio iniciar la implementación de detección o entrenamiento**. El objetivo primordial es evaluar, diseñar y preparar correctamente el dominio antes de codificar la Capacidad 1.

#### Backend / DevOps
* **Vianey — Backend Engineer / DevOps Engineer**
  * Arquitectura inicial del backend y servicios de estado (`VIGIA_Core`).
  * Preparación y estandarización del entorno de desarrollo unificado.
  * Configuración de la estructura inicial del repositorio y dependencias limpias.
  * Identificación de necesidades de persistencia local (diseño preliminar de esquemas SQLite).
  * Preparación de la infraestructura de automatización de pruebas y linters.

#### Frontend / Business Analysis
* **Naty — Frontend Engineer / Business Analyst**
  * Identificación y análisis de necesidades del operador humano en caseta.
  * Estructura inicial de flujos de interacción y wireframes UX/UI.
  * Arquitectura inicial del Dashboard operativo de supervisión (`VIGIA_Dashboard`).
  * Definición preliminar de los estados del carril y vistas requeridas para la supervisión en vivo.

#### Dashboard / Web
* **Jonathan — Dashboard & Web Developer**
  * Apoyo en el diseño e implementación técnica de la interfaz del Dashboard.
  * Preparación de la estructura base del proyecto web (HTML/CSS/JS o framework seleccionado).
  * Análisis inicial y arquitectura del sitio institucional de VIGIA.
  * Identificación de requerimientos técnicos comunes entre ambas interfaces (Dashboard vs. Web Institucional).

#### Marketing / Market Research
* **Ale — Marketing & Market Research**
  * Investigación inicial del mercado de control de accesos vehiculares y automatización física.
  * Identificación y tipificación de clientes potenciales, administradores y operadores finales.
  * Análisis preliminar de soluciones competidoras y alternativas existentes en el mercado.
  * Identificación de oportunidades clave de diferenciación y propuesta de valor del producto VIGIA.

---

# 7. Resultado Esperado del Sprint 0 (*Definition of Done*)

El **Sprint 0** se considerará formalmente concluido cuando el proyecto cuente, como mínimo, con los siguientes entregables verificables:

```text
✓ Equipo organizado con gobernanza clara
✓ Roles técnicos y de gestión unívocamente definidos
✓ Responsabilidades y ownership por componente asignados
✓ Contratos de trabajo por entregables preparados
✓ Marco Scrum adaptado y ceremonias establecidas
✓ Product Backlog inicial construido y priorizado
✓ Roadmap orientado a capacidades aprobado y congelado
✓ Cronograma base temporal alineado con el Roadmap
✓ Arquitectura sistémica y fronteras de módulos formalizadas
✓ Workstreams (A–I) activos con objetivos delimitados
✓ Interfaces iniciales y contratos de datos identificados
✓ Entornos de desarrollo locales estandarizados
✓ Repositorio VIGIA organizado bajo estándares limpios
✓ Criterios iniciales de aceptación definidos por entregable
✓ Mecanismo de revisión periódica e integración continua acordado
```

> **Criterio Fundamental:**  
> El Sprint 0 **no tiene como objetivo demostrar todavía las capacidades físicas finales de VIGIA**.  
> Su propósito exclusivo es **construir las condiciones técnicas, organizacionales y metodológicas necesarias para desarrollarlas con velocidad, rigor y sin bloqueos**.
