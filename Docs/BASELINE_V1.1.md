# VIGIA Vision Systems — Baseline V1.1

## 1. Estado de la Línea Base

* **Estado Oficial:** `CONGELADA`
* **Fase:** Fase 0 — Documentación, Arquitectura y Fundaciones Metodológicas
* **Fecha de Congelación:** 11 de septiembre de 2026
* **Autoridad de Aprobación:** Vianey (Product Owner) & Yair (Ingeniero de Software / Diseño Eléctrico)

---

## 2. Alcance Congelado

El alcance congelado de la iniciativa tecnológica **VIGIA Vision Systems** en su primera etapa corresponde a la validación experimental y demostrable del ciclo físico completo en el caso rector:

> **Caso Rector:** **Caseta Inteligente de Acceso Vehicular**  
> Detección de aproximación vehicular, lectura óptica de placas (LPR), evaluación determinista de políticas de acceso, validación de invariantes de seguridad física, accionamiento de barrera electromecánica/señalización, verificación sensorial en lazo cerrado de apertura y cruce, y registro persistente de auditoría con evidencia fotográfica.

---

## 3. Arquitectura Congelada

Se congela el modelo arquitectónico basado en el **Patrón Mediador** con **Control en Lazo Cerrado (*Closed-Loop Control*)**:

```text
Entorno Físico (Cámara / Sensores)
      │
      ├──────────────────┐
      ▼                  ▼
VIGIA_Vision         VIGIA_IoT
      │                  │
      └────────┬─────────┘
               ▼
          VIGIA_Core (Estado e Invariantes de Seguridad)
               │
         ┌─────┴─────┐
         ▼           ▼
  VIGIA_Automation  VIGIA_API ◄───► VIGIA_Dashboard
```

* **Ciclo Operativo Fundamental:**  
  $$\text{Observar} \longrightarrow \text{Interpretar} \longrightarrow \text{Decidir} \longrightarrow \text{Actuar} \longrightarrow \text{Verificar} \longrightarrow \text{Registrar} \longrightarrow \text{Mejorar}$$
* **Principios Inviolables de Dominio:**
  1. `VIGIA_Vision` observa e interpreta, pero **no autoriza accesos ni comanda actuadores**.
  2. `VIGIA_IoT` interactúa con el mundo físico y confirma mediante sensores, pero **no evalúa reglas de negocio**.
  3. `VIGIA_Core` mantiene la **autoridad exclusiva sobre el estado del entorno y las invariantes de seguridad física**.
  4. Ninguna acción física se da por concluida sin **verificación sensorial en lazo cerrado**.
  5. `VIGIA_API` y `VIGIA_Dashboard` **jamás acceden directamente al hardware**.
  6. El sistema opera de forma **autónoma en el borde**, sin dependencias críticas de conectividad cloud.

---

## 4. Equipo y Gobernanza Congelados

### 4.1 Estructura Oficial (6 Integrantes)

| Integrante | Roles / Puestos Oficiales | Módulos / Áreas Principales | Entregable Académico Asignado (Confirmado) |
| :--- | :--- | :--- | :--- |
| **Yair** | Ingeniero de Software + Ing. de Diseño Eléctrico | `VIGIA_Core/`, Software Global, Diseño Eléctrico | Ficha de descripción de roles + Requerimientos funcionales y no funcionales |
| **Vianey** | Product Owner (PO) | Product Backlog, Visión del Producto, `Docs/09` | Historia de usuario |
| **Ernesto** | CIO + Ing. de Diseño de Circuitos | `VIGIA_IoT/`, Diseño de Circuitos, Hardware Embebido, Seguridad de Información | Logos, asegurando accesibilidad + Mapas de recorrido |
| **Josue** | Ing. de Procesos | Procesos Operativos, `VIGIA_Automation/`, Gestión Metodológica | Todas las hojas del formato de reuniones |
| **Natalia** | UX / UI | `VIGIA_Dashboard/`, Experiencia de Usuario (UX), Diseño Visual (UI) | Creación de personas |
| **Estef** *(Estefany)* | Analista *(Analistas)* | Análisis de Requisitos y Datos, `VIGIA_Vision/` | Mapa de empatía |

> *Nota:* El equipo está integrado por seis integrantes que desempeñan ocho puestos o funciones oficiales distribuidos entre ellos.

### 4.2 Gobernanza Técnica y Ownership
* **Gobernanza de Producto y Arquitectura:** **Vianey (PO) + Yair (Software/Eléctrico)** (responsables de alinear el backlog y contratos públicos).
* **Ownership Técnico de Implementación:** Cada especialista lidera la implementación técnica de su dominio (Ernesto en Circuitos/IoT, Yair en Software/Eléctrico, Natalia en UX/UI, Josue en Procesos, Estef en Análisis y Vianey en Producto/Backlog).

---

## 5. Documentos Canónicos Oficiales (01 al 09)

| Documento | Título | Responsabilidad Canónica (*Source of Truth*) |
| :---: | :--- | :--- |
| **[`Docs/01`](./01_estructura_del_proyecto.md)** | **Estructura del Proyecto** | Define la organización de carpetas, responsabilidades por módulo, código admitido/prohibido y ownership. |
| **[`Docs/02`](./02_arquitectura_del_sistema.md)** | **Arquitectura del Sistema** | Define el ciclo cerrado, el mediador, la persistencia local y la separación entre políticas e invariantes. |
| **[`Docs/03`](./03_roadmap.md)** | **Roadmap de Capacidades** | Define la hoja de ruta evolutiva estructurada en 7 capacidades físicas demostrables (Fases 0 a 8). |
| **[`Docs/04`](./04_estandares_de_desarrollo.md)** | **Estándares de Desarrollo** | Define la filosofía de mínima complejidad, estilo Python (PEP 8), Git flow y testing con mocks. |
| **[`Docs/05`](./05_marco_de_planificacion_y_ejecucion.md)** | **Marco de Planificación** | Define el marco Scrum con desarrollo paralelo por Workstreams (A–H) y la regla estricta de no bloqueo. |
| **[`Docs/06`](./06_propuesta_del_proyecto.md)** | **Propuesta del Proyecto** | Define la justificación ejecutiva, académica, misión, visión y alcance del caso rector. |
| **[`Docs/07`](./07_cronograma_maestro.md)** | **Cronograma Maestro** | Define el calendario de ejecución temporal (Sep 9 – Dic 16, 2026), Sprints S0–S7 e Hitos H0–H8. |
| **[`Docs/08`](./08_matriz_de_riesgos.md)** | **Matriz de Riesgos** | Define los riesgos técnicos, de hardware e integración con estrategias de mitigación y contingencia. |
| **[`Docs/09`](./09_especificacion_de_requisitos.md)** | **Especificación Requisitos**| Define los Requisitos Funcionales (RF), No Funcionales (RNF), Historias de Usuario (HU) e invariantes. |

---

## 6. Estado del Proyecto

### COMPLETADO (Fase 0):
* Estructura documental canónica normalizada y libre de duplicados activos.
* Organización del equipo consolidada en 6 integrantes con cadena de mando unívoca.
* Arquitectura conceptual desacoplada bajo el Patrón Mediador y Lazo Cerrado.
* Roadmap por capacidades físicas y Cronograma Maestro sincronizados (Sep 9 – Dic 16, 2026).
* Estándares de desarrollo, convenciones Git y disciplina de testing sin hardware físico.
* Propuesta ejecutiva y académica de la iniciativa tecnológica.
* Matriz inicial de riesgos y planes de contingencia documentados.
* Especificación inicial de requisitos de software (RF-01 a RF-15, RNF-01 a RNF-06, HU-01 a HU-05).
* Saneamiento integral de hipervínculos rotos y rutas absolutas.

### PENDIENTE PARA SPRINT 1 (Sep 14 – Sep 27, 2026):
* Refinamiento detallado de requisitos e Historias de Usuario con estimación de esfuerzo.
* Auditoría técnica de código en el prototipo de referencia `VR_Semaforo/` para rescate de snippets.
* Formalización de contratos de datos entre módulos (esquemas de eventos tipados).
* Especificación técnica del protocolo serial byte a byte con el microcontrolador.
* Diseño del esquema relacional de persistencia local (tablas de eventos, vehículos y evidencias).
* Definición detallada del plan de pruebas automatizadas en `tests/`.
* Validación empírica inicial de objetivos de latencia y benchmarks de inferencia.

---

## 7. Decisiones NO Congeladas (Abiertas a Validación en Desarrollo)

Para evitar que propuestas de ingeniería se interpreten erróneamente como restricciones rígidas, se declara explícitamente que **las siguientes decisiones técnicas NO están congeladas y se definirán durante los Sprints 1 y 2**:

1. **Arquitectura y Modelo Específico de Visión:** Elección final del modelo detector (variantes ligeras tipo YOLO u otros detectores edge).
2. **Motor / Framework de OCR:** Selección de la biblioteca de extracción alfanumérica de matrículas tras benchmarks de precisión/latencia.
3. **Placa de Hardware Embebido Definitiva:** Elección entre microcontrolador Arduino (Uno/Nano) o ESP32 según necesidades de memoria y puertos.
4. **Trama Serial Definitiva:** Estructura byte a byte de los mensajes de comando y confirmación sensorial UART.
5. **Esquema Físico de Base de Datos:** DDL final y tipos de campo para SQLite local.
6. **Umbrales Cuantitativos de Rendimiento:** Valores definitivos de latencia máxima (objetivo $\le 1.5\text{ s}$), confianza mínima de OCR (objetivo $\ge 0.80$) y timeouts de seguridad.
7. **Detalle de Empaquetado y Despliegue:** Scripts de instalación y configuración de entorno virtual en la máquina anfitriona.

---

## 8. Próximo Paso Oficial

> **INICIO DE SPRINT 1: Producto, Requisitos Detallados, Contratos de Interfaz y Auditoría de `VR_Semaforo/` (14 al 27 de septiembre de 2026).**
