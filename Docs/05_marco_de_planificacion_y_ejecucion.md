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

El trabajo y el cronograma de VIGIA se estructuran mediante 8 Workstreams especializados y coordinados, normalizados sobre el equipo oficial de 6 integrantes:

| ID | Workstream | Alcance Principal | Responsables Principales | Participación / Apoyo |
| :---: | :--- | :--- | :--- | :--- |
| **A** | **Product & Architecture** | Visión del producto, priorización del backlog, arquitectura sistémica, gobierno técnico y contratos de interfaces. | **Yair + Josue** | Todo el equipo |
| **B** | **AI / Computer Vision / Data** | Captura de video, detección vehicular, localización de placas, LPR/OCR, datasets y benchmarks de inferencia. | **Estefany** | Naty (QA) |
| **C** | **Backend / Core / Automation** | Máquina de estados de carril, reglas de acceso deterministas, persistencia local y servicios de dominio. | **Vianey** | Josue (Arquitectura) |
| **D** | **Frontend / Dashboard / QA / BA** | Interfaz web de supervisión operativa, renderizado en tiempo real, alertas, UX/UI y aseguramiento de calidad (QA). | **Naty** | Vianey (API) |
| **E** | **Hardware / Embedded / IoT** | Circuitos embebidos, firmware (Arduino/ESP32), sensores físicos de presencia/carrera, servomotores y protocolo serial. | **Ernesto** | Vianey (Serial Core) |
| **F** | **DevOps / Infrastructure** | Entornos de desarrollo reproducibles, pipelines de testing automatizado, linters y empaquetado local. | **Vianey** | Yair (CTO) |
| **G** | **Marketing / Market Research** | Investigación de mercado, perfiles de usuario, análisis de competencia, propuesta de valor y difusión pública. | **Yair + Josue** | Naty, Vianey, Estefany (Transversal) |
| **H** | **Security / Information Governance** | Invariantes de seguridad física (*fail-safe*), control de acceso, gobernanza técnica y protección de datos. | **Yair + Ernesto** | Josue, Vianey |

> **Integración de Presencia Web Institucional (Antes "Workstream I"):**  
> Para mantener una estructura limpia y sin silos artificiales, el desarrollo del portal y difusión web se consolida formalmente como una **actividad transversal compartida** entre **Marketing / Producto (Workstreams A/G — Josue/Yair)** y **Frontend / UI (Workstream D — Naty)**, evitando la dispersión en una novena área independiente.

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

### 6.1 Asignación de Roles y Responsabilidades Principales

#### Project Management & CTO
* **Yair — Project Manager + CTO**
  * Coordinar el proyecto, planificar actividades, dar seguimiento al cronograma y gestionar riesgos.
  * Dirigir las decisiones tecnológicas globales y asegurar la viabilidad técnica del sistema.
  * Definición y aplicación del marco Scrum adaptado y facilitación de ceremonias.
  * Preparación de los contratos de trabajo por entregables y gestión de dependencias.
  * Responsable principal de **Documentation** y co-responsable de **Marketing & Market Research** y **Security**.

#### Product Ownership & System Architecture
* **Josue — Product Owner + System Architect**
  * Definir la visión del producto y gestionar/priorizar los requisitos del sistema.
  * Construcción inicial, administración y mantenimiento del Product Backlog central.
  * Diseñar la arquitectura general de VIGIA y los contratos de datos entre módulos (`VIGIA_Core/`, interfaces).
  * Definición funcional de las necesidades del producto (Caseta Inteligente) e historias de usuario base.
  * Co-responsable principal de **Marketing & Market Research** y participante en **Security**.

#### Hardware, IoT & CIO
* **Ernesto — Hardware / Embedded IoT Engineer + CIO**
  * Diseñar e integrar cámaras, sensores, dispositivos IoT y sistemas embebidos (`VIGIA_IoT/`).
  * Gestionar la información, inventario técnico y apoyar la seguridad y gobernanza de la información.
  * Identificación y selección de sensores de verificación física (finales de carrera, lazo magnético, presencia).
  * Revisión y definición de protocolos de comunicación física (UART/Serial, tramas de comando, baudrates, timeouts).
  * Montaje del banco de pruebas y entorno de prototipado físico / maqueta.
  * Co-responsable principal de **Security**.

#### AI, Computer Vision & Data Engineering
* **Estefany — AI / Computer Vision Engineer + Data Engineer**
  * Desarrollar e integrar modelos de IA y visión computacional (`VIGIA_Vision/`).
  * Procesamiento de imágenes y video, localización y detección vehicular, y reconocimiento óptico de matrículas (LPR/OCR).
  * Identificación de necesidades de datos, preparación de datasets, pipelines y gestión de datos para los modelos.
  * Investigación tecnológica y benchmarks de inferencia en hardware edge.
  * Participante en **Marketing & Market Research**, **Testing & Integration** y **Documentation**.

> *Nota de Ingeniería:* Durante el Sprint 0 **no es obligatorio iniciar la implementación de detección o entrenamiento**. El objetivo primordial es evaluar, diseñar y preparar correctamente el dominio antes de codificar la Capacidad 1.

#### Backend & DevOps Engineering
* **Vianey — Backend Engineer + DevOps Engineer**
  * Desarrollar APIs (`VIGIA_API/`), lógica de negocio, gestión de datos, eventos y alertas (`VIGIA_Automation/`).
  * Administrar entornos de desarrollo, despliegues, CI/CD, infraestructura de pruebas automatizadas y monitoreo.
  * Arquitectura inicial de servicios de persistencia local (diseño de esquemas SQLite) y adaptadores de datos.
  * Configuración de la estructura inicial del repositorio, estándares de dependencias y linters.
  * Participante en **Security**, **Marketing & Market Research**, **Testing & Integration** y **Documentation**.

#### Frontend, QA & Business Analysis
* **Naty — Frontend Engineer + QA + Business Analyst**
  * Desarrollar la interfaz visual y el dashboard operativo de supervisión (`VIGIA_Dashboard/`).
  * Identificación y análisis de necesidades del operador humano en caseta, UX/UI y wireframes de interacción.
  * Responsable principal de **Testing & Integration**: diseño de estrategia de QA, pruebas funcionales, de integración y validación integral del sistema.
  * Participante en **Marketing & Market Research** y **Documentation**.

---

### 6.2 Responsabilidades Transversales

Estas actividades no constituyen cargos adicionales independientes; son responsabilidades compartidas que todos los integrantes apoyan activamente:

| Área Transversal | Responsable Principal | Participación del Equipo |
| :--- | :--- | :--- |
| **Marketing & Market Research** | Yair + Josue | Naty, Vianey y Estefany |
| **Security** | Yair + Ernesto | Josue + Vianey |
| **Documentation** | Yair | Todos |
| **Testing & Integration** | Naty | Todos |


---

# 7. Estado de Cierre del Sprint 0 (*Definition of Done*)

El **Sprint 0** se evalúa formalmente con el estado:

> **ESTADO OFICIAL: COMPLETADO CON PENDIENTES MENORES DE SANEAMIENTO DOCUMENTAL**

### Verificación de Entregables del Sprint 0:

```text
✓ Equipo organizado con gobernanza clara (Yair -> Josue -> Áreas Técnicas)
✓ Roles técnicos y de gestión unívocamente definidos (6 integrantes)
✓ Responsabilidades y ownership por componente asignados (Docs/01)
✓ Contratos de trabajo por entregables preparados
✓ Marco Scrum adaptado y ceremonias establecidas (Docs/05)
✓ Product Backlog inicial y caso rector de Caseta formalizado (Docs/09)
✓ Roadmap orientado a capacidades aprobado y congelado (Docs/03)
✓ Cronograma base temporal alineado con el Roadmap (Docs/07)
✓ Arquitectura sistémica y fronteras de módulos formalizadas (Docs/02)
✓ Workstreams (A–I) activos y normalizados sobre los 6 integrantes
✓ Matriz de riesgos inicial consolidada (Docs/08)
✓ Entornos de desarrollo locales estandarizados (.env, .gitignore, PEP 8)
✓ Repositorio VIGIA organizado bajo estándares limpios (Fase 0)
```

---

# 8. Planificación y Alcance del Sprint 1

El **Sprint 1 (14 al 27 de septiembre de 2026)** marca el inicio de la construcción formal del sistema, orientado a cinco entregables críticos:

1. **Requisitos Detallados:** Refinamiento del catálogo de Requisitos Funcionales (RF), Requisitos No Funcionales (RNF) y reglas de negocio (`Docs/09_especificacion_de_requisitos.md`). *(Responsables: Josue + Naty)*.
2. **User Stories:** Redacción y estimación de Historias de Usuario con criterios de aceptación en formato `Given-When-Then`. *(Responsables: Josue + Naty)*.
3. **Auditoría Técnica de `VR_Semaforo/`:** Análisis del prototipo de referencia para rescatar rutinas de OpenCV y comunicación serial con Arduino. *(Responsables: Ernesto + Estefany + Vianey)*.
4. **Contratos de Interfaces:** Especificación formal de esquemas Pydantic (`ObservationEvent`, `Decision`, `Command`, `VerificationEvent`) y tramas seriales IoT. *(Responsables: Josue + Vianey + Ernesto + Estefany)*.
5. **Validación de Matriz de Riesgos:** Revisión quincenal y ajuste de los riesgos prioritarios del proyecto (`Docs/08_matriz_de_riesgos.md`). *(Responsables: Yair + Ernesto)*.

