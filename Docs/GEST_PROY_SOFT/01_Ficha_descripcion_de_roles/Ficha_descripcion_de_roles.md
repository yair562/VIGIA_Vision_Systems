# 01 — Ficha de Descripción de Roles

**Proyecto:** VIGIA Vision Systems  
**Área:** Gestión de Proyectos de Software / Organización de Equipo  
**Responsable del Entregable:** Yair  
**Puesto / Rol del Responsable:** Ingeniero de Software + Ing. de Diseño Eléctrico  
**Versión:** 1.0  
**Fecha:** 21 de septiembre de 2026  

---

## 1. Identificación del Cargo

* **Nombre del Puesto:** Ingeniero de Software / Ingeniero de Diseño Eléctrico
* **Responsable:** Yair
* **Reporta a:** Gobernanza General del Proyecto y Product Owner (Vianey)
* **Coordina con:**
  * **CIO / Ing. de Diseño de Circuitos** (Ernesto) — Integración de actuadores, sensores y hardware IoT.
  * **Ing. de Procesos** (Josué) — Flujos operativos de automatización y control de estados.
  * **UX / UI** (Natalia) — Integración de APIs con el Dashboard y visualización operativa.
  * **Analistas** (Estef) — Requisitos de dominio, modelos y flujo de datos.
  * **Product Owner** (Vianey) — Priorización del backlog y alcance funcional.

---

## 2. Objetivo Principal del Cargo

Liderar el diseño arquitectónico, implementación del software del sistema (`VIGIA_Core/`, servicios de automatización, APIs y persistencia local) y la ingeniería de diseño eléctrico del proyecto VIGIA Vision Systems, asegurando que la plataforma opere de manera robusta, desacoplada y con control en lazo cerrado sobre el entorno físico.

---

## 3. Funciones y Responsabilidades Principales

### 3.1 En Ingeniería de Software:
1. **Arquitectura de Software:** Diseñar y estructurar los módulos centrales del sistema (`VIGIA_Core/`, lógica de decisión y servicios de persistencia local).
2. **Contratos e Interfaces:** Definir contratos de datos estructurados para la comunicación entre el pipeline de visión, el subsistema IoT y el dashboard.
3. **Calidad y Estándares de Código:** Garantizar el cumplimiento de estándares de desarrollo (PEP 8, tipado estricto, manejo de excepciones y pruebas unitarias con mocks).
4. **Desacoplamiento y Modularidad:** Asegurar que los componentes de software no dependan rígidamente de hardware específico mediante interfaces abstractas.

### 3.2 En Ingeniería de Diseño Eléctrico:
1. **Diseño y Distribución Eléctrica:** Especificar requerimientos de alimentación, voltajes de operación, fuentes de poder y protección eléctrica para los actuadores (servomotores, relevadores, semáforos) y la electrónica de control.
2. **Seguridad Física y Eléctrica:** Definir esquemas de protección contra sobrecargas, aislamiento de ruido eléctrico en la alimentación de motores y comportamiento seguro (*fail-safe*) ante caídas de tensión.

---

## 4. Requisitos y Competencias Técnicas

* **Lenguajes y Herramientas:** Python 3.10+, SQLite, Git, Pytest.
* **Conocimientos de Ingeniería:** Patrones de arquitectura de software (Patrón Mediador, State Pattern, Clean Architecture), diseño eléctrico básico, circuitos de potencia y control de motores.
* **Competencias Metodológicas:** Scrum, desarrollo iterativo guiado por capacidades, gestión técnica de dependencias.

---

## 5. Resumen de la Estructura Oficial de Puestos del Equipo

| Puesto / Rol Oficial | Responsable | Entregable Académico Asignado |
| :--- | :--- | :--- |
| **Ingenieros de Software + Ing. de Diseño Eléctrico** | **Yair** | Ficha de descripción de roles + Requerimientos funcionales y no funcionales |
| **Product Owner (PO)** | **Vianey** | Historia de usuario |
| **CIO + Ing. de Diseño de Circuitos** | **Ernesto** | Logos, asegurando accesibilidad + Mapas de recorrido |
| **Ing. de Procesos** | **Josué** | Todas las hojas del formato de reuniones |
| **UX / UI** | **Natalia** | Creación de personas |
| **Analistas** | **Estef** | Mapa de empatía |

> *Nota:* El equipo está integrado por seis integrantes que desempeñan ocho puestos o funciones oficiales distribuidos entre ellos.
