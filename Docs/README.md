# VIGIA Vision Systems — Repositorio Central de Documentación

Bienvenido a la base de documentación técnica, arquitectónica y metodológica de **VIGIA Vision Systems**.

---

## 1. Propósito de la Documentación

El propósito fundamental de este directorio es actuar como la **fuente única de verdad** técnica para el diseño, evolución y gobernanza de la plataforma.

Esta documentación garantiza que:
* Las responsabilidades de cada módulo y de cada integrante estén formalmente delimitadas.
* Las decisiones arquitectónicas se fundamenten en principios de ingeniería de software sólidos (desacoplamiento, abstracción de hardware y modelos).
* La transición desde el prototipo de referencia (`VR_Semaforo/`) hacia la arquitectura definitiva de `VIGIA` ocurra de manera metódica y controlada.
* Los contratos de interfaz y eventos se definan antes de la implementación de código dependiente.

---

## 2. Estado de Línea Base y Congelación de Fase 0

> **Línea Base Oficial:**  
> La documentación y arquitectura de la **Fase 0** se encuentran formalmente auditadas, saneadas y **congeladas** bajo la versión canónica:  
> 📄 **[`Docs/BASELINE_V1.1.md`](./BASELINE_V1.1.md)** — *Documento de Congelación de la Línea Base de Fase 0.*

---

## 3. Mapa de Progresión Conceptual

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
│          03 — Roadmap                │ ──> ¿En qué orden construiremos las capacidades?
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│     04 — Estándares de Desarrollo    │ ──> ¿Cómo debe escribirse y probarse el código?
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│   05 — Planificación y Ejecución     │ ──> ¿Cómo nos organizamos y ejecutamos en paralelo?
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│      06 — Propuesta del Proyecto     │ ──> ¿Cuál es la visión ejecutiva e impacto?
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│        07 — Cronograma Maestro       │ ──> ¿Cuándo y en qué sprints se entrega cada hito?
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│      08 — Matriz de Riesgos          │ ──> ¿Qué riesgos existen y cómo se mitigan?
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│    09 — Especificación Requisitos    │ ──> ¿Cuáles son los RF, RNF e Historias de Usuario?
└──────────────────────────────────────┘
```

---

## 4. Catálogo de Documentación Oficial Canónica (01 al 09)

| Documento | Título | Pregunta Central | Source of Truth para: | Descripción Resumida |
| :---: | :--- | :--- | :--- | :--- |
| **[01](./01_estructura_del_proyecto.md)** | **Estructura del Proyecto** | *¿Quién es responsable de qué?* | **Organización y Estructura** | Organización de carpetas, responsabilidades técnicas por módulo, código admitido/prohibido y ownership del equipo. |
| **[02](./02_arquitectura_del_sistema.md)** | **Arquitectura del Sistema** | *¿Cómo se relacionan los módulos?* | **Arquitectura del Sistema** | Arquitectura conceptual global, ciclo cerrado, mediador, persistencia local y separación de invariantes vs reglas. |
| **[03](./03_roadmap.md)** | **Roadmap de Capacidades** | *¿En qué orden construiremos las capacidades?* | **Roadmap del Producto** | Hoja de ruta estratégica por 7 capacidades físicas demostrables (Fase 0 a Fase 8) y criterios de avance. |
| **[04](./04_estandares_de_desarrollo.md)** | **Estándares de Desarrollo** | *¿Cómo debe escribirse y mantenerse el código?* | **Estándares Técnicos** | Guías de codificación en Python (PEP 8), convenciones de Git, testing sin hardware físico y logging. |
| **[05](./05_marco_de_planificacion_y_ejecucion.md)** | **Marco de Planificación y Ejecución** | *¿Cómo nos organizamos y ejecutamos en paralelo?* | **Metodología y Scrum** | Scrum adaptado con desarrollo paralelo por Workstreams (A–H), regla de no bloqueo mediante mocks y contratos. |
| **[06](./06_propuesta_del_proyecto.md)** | **Propuesta del Proyecto** | *¿Qué problema resuelve y qué valor demuestra?* | **Propuesta Ejecutiva** | Propuesta ejecutiva y académica: misión, visión, caso rector de caseta inteligente, alcance y proyección a futuro. |
| **[07](./07_cronograma_maestro.md)** | **Cronograma Maestro** | *¿Cuándo y en qué fechas se entrega cada hito?* | **Fechas y Cronograma** | Plan temporal sincronizado (Sep 9 - Dic 16, 2026), matriz S0-S7, hitos H0-H8 y protección del deadline. |
| **[08](./08_matriz_de_riesgos.md)** | **Matriz de Riesgos** | *¿Qué riesgos existen y cómo se mitigan?* | **Gestión de Riesgos** | Matriz de riesgos técnicos, de hardware, visión e integración, con planes de contingencia y responsables. |
| **[09](./09_especificacion_de_requisitos.md)** | **Especificación de Requisitos** | *¿Qué debe hacer el sistema exactamente?* | **Requisitos y Backlog** | Catálogo formal de Requisitos Funcionales (RF), No Funcionales (RNF), Historias de Usuario (HU) y reglas de negocio. |

---

## 5. Directorios Complementarios

* **[`GEST_PROY_SOFT/`](./GEST_PROY_SOFT/)**: Entregables oficiales de Gestión de Proyectos de Software y diseño centrado en el usuario (8 categorías estructuradas). No forma parte del código base ejecutable.
* **[`Referencias/`](./Referencias/)**: Documentos institucionales, normativos y guías metodológicas de referencia académica externa (`Memoria_Tecnica_de_proyecto.pdf` y `Plan_de_calidad.pdf`).
* **[`Archive/`](./Archive/)**: Documentación histórica, versiones preliminares y borradores anteriores preservados para auditoría y trazabilidad.

---

## 6. Regla "Source of Truth"

Cada tipo de información posee una única fuente oficial. Los demás documentos únicamente resumen o enlazan a dicha fuente, evitando duplicidades y desincronizaciones futuras.
