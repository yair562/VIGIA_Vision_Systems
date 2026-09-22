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
| **A** | **Product & Architecture** | Visión del producto, priorización del backlog, arquitectura sistémica y contratos de interfaces. | **Vianey (PO) + Yair (Software/Eléctrico)** | Todo el equipo |
| **B** | **AI / Computer Vision / Data** | Captura de video, detección vehicular, localización de placas, LPR/OCR, datasets y análisis de datos. | **Estef (Analista) + Yair** | Natalia (UX/UI) |
| **C** | **Backend / Core / Automation** | Máquina de estados de carril, reglas de acceso deterministas, persistencia local y lógica de procesos. | **Yair (Software) + Josue (Procesos)** | Vianey (PO) |
| **D** | **Frontend / Dashboard / UX/UI** | Interfaz web de supervisión operativa, renderizado en tiempo real, alertas, wireframes y experiencia de usuario. | **Natalia (UX/UI)** | Estef (Análisis) |
| **E** | **Hardware / Embedded / Circuitos** | Circuitos electrónicos, sensores físicos, actuadores, diseño de potencia e integración física. | **Ernesto (CIO/Circuitos) + Yair (Eléctrico)** | Josue (Procesos) |
| **F** | **DevOps / Infrastructure** | Entornos de desarrollo reproducibles, testing automatizado, linters y empaquetado local. | **Yair (Software)** | Ernesto (CIO) |
| **G** | **Marketing / Market Research** | Investigación de mercado, perfiles de usuario, análisis de competencia, propuesta de valor y difusión. | **Vianey (PO) + Josue (Procesos)** | Natalia, Estef, Yair |
| **H** | **Security / Information Governance** | Invariantes de seguridad física (*fail-safe*), gobernanza de información y protección de datos. | **Ernesto (CIO) + Yair** | Vianey, Josue |

> **Integración de Presencia Web Institucional:**  
> El desarrollo del portal y difusión web se consolida como una **actividad transversal compartida** entre **Marketing / Producto (Vianey/Josue)** y **UX/UI (Natalia)**, evitando silos artificiales.

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

#### Software & Electrical Engineering
* **Yair — Ingeniero de Software + Ing. de Diseño Eléctrico**
  * Diseñar y desarrollar la arquitectura de software, backend/core y liderar el diseño de sistemas eléctricos del proyecto.
  * Coordinar la infraestructura técnica, estándares de código y viabilidad del sistema.
  * **Entregable Académico Asignado (Confirmado):** Ficha de descripción de roles + Requerimientos funcionales y no funcionales (`Docs/09`).
  * Co-responsable de **Documentation**, **Marketing** y **Security**.

#### Product Ownership
* **Vianey — Product Owner (PO)**
  * Definir la visión del producto, gestionar y priorizar el Product Backlog y articular los requisitos funcionales.
  * Asegurar la entrega de valor y alineación del caso rector de Caseta Inteligente.
  * **Entregable Académico Asignado (Confirmado):** Historia de usuario (`Docs/09`).
  * Responsable principal de **Marketing & Market Research**.

#### CIO & Circuit Design Engineering
* **Ernesto — CIO + Ing. de Diseño de Circuitos**
  * Diseñar circuitos electrónicos, integración de sensores, actuadores, hardware embebido (`VIGIA_IoT/`) y gobernar la información técnica.
  * Identificación de sensórica de verificación física y protocolos de comunicación de bajo nivel.
  * **Entregable Académico Asignado (Confirmado):** Logos, asegurando accesibilidad + Mapas de recorrido.
  * Responsable principal de **Security & Information Governance**.

#### Process Engineering
* **Josue — Ing. de Procesos**
  * Diseñar, optimizar y formalizar los flujos de procesos del sistema, control operativo y estandarización del flujo de trabajo.
  * Modelado del ciclo físico y coordinación de dinámicas de equipo.
  * **Entregable Académico Asignado (Confirmado):** Todas las hojas del formato de reuniones (`Docs/GEST_PROY_SOFT/07_Formato_de_reuniones/`).
  * Co-responsable de **Procesos Operativos** y **Marketing**.

#### UX / UI Design
* **Natalia — UX / UI**
  * Diseñar la experiencia de usuario (UX), interfaces visuales interactivas (UI), flujos de interacción del operador y wireframes del dashboard (`VIGIA_Dashboard/`).
  * **Entregable Académico Asignado (Confirmado):** Creación de personas.
  * Participante en **Testing & QA** y **Documentation**.

#### Systems & Requirements Analysis
* **Estef — Analista *(Analistas)***
  * Analizar los requisitos del dominio, especificaciones del sistema, modelado analítico y flujo de datos.
  * Apoyo en la preparación y validación de datos para el pipeline perceptual.
  * **Entregable Académico Asignado (Confirmado):** Mapa de empatía.
  * Participante en **Análisis de Requisitos**, **Testing & QA** y **Documentation**.

---

### 6.2 Responsabilidades Transversales

Estas actividades no constituyen cargos adicionales independientes; son responsabilidades compartidas que todos los integrantes apoyan activamente:

| Área Transversal | Responsable Principal | Participación del Equipo |
| :--- | :--- | :--- |
| **Marketing & Market Research** | Vianey (PO) + Josue (Procesos) | Natalia, Estef y Yair |
| **Security & Information Governance** | Ernesto (CIO) + Yair | Vianey + Josue |
| **Documentation & Project Knowledge** | Yair (Coordinación) | Todos |
| **Testing & System Validation** | Natalia + Estef | Todos |


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

El **Sprint 1 (14 al 27 de septiembre de 2026)** marca el inicio de la construcción formal del sistema. Las actividades planificadas se estructuran distinguiendo entregables confirmados de actividades técnicas pendientes de validación operativa:

### 8.1 Entregables con Responsabilidad Confirmada
1. **Requerimientos Funcionales y No Funcionales:** Refinamiento del catálogo de RF y RNF (`Docs/09_especificacion_de_requisitos.md`). *(Responsable: Yair)*.
2. **Historias de Usuario:** Elaboración y estructuración de historias de usuario (`Docs/09_especificacion_de_requisitos.md`). *(Responsable: Vianey)*.

### 8.2 Actividades Técnicas Planificadas del Proyecto *(Pendientes de Asignación y Validación por el Equipo)*
3. **Auditoría Técnica de `VR_Semaforo/`:** Análisis del prototipo de referencia para identificar rutinas de visión y comunicación serial. *(Actividad técnica del proyecto, pendiente de asignación operativa).*
4. **Contratos de Interfaces:** Definición formal de contratos y esquemas de eventos entre módulos. *(Actividad técnica del proyecto, pendiente de validación).*
5. **Seguimiento de Matriz de Riesgos:** Revisión periódica de riesgos prioritarios (`Docs/08_matriz_de_riesgos.md`). *(Actividad de gestión del proyecto).*

