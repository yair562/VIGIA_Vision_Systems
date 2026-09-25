# Ficha Individual de Defensa de Rol — Ingeniero de Software (Software Engineer)
## Proyecto: VIGIA Vision Systems

---

## 1. Identificación del puesto

* **Titular del puesto:** Perez Medina Yair
* **Nombre oficial del puesto:** Ingeniero de Software
* **Nombre en inglés / Siglas:** Software Engineer
* **Área o Naturaleza del rol:** Arquitectura de Software, Desarrollo Backend, APIs y Persistencia de Datos
* **Ubicación dentro del flujo global:** Cuarta etapa: Diseño y desarrollo técnico concurrente (Lógica Central, Servicios y APIs) previo a la integración física-lógica.

---

## 2. Propósito del puesto

El Ingeniero de Software existe dentro de VIGIA para materializar la inteligencia y lógica central del sistema. Su propósito es diseñar, programar, integrar y mantener el núcleo de software de VIGIA (`VIGIA_Core/`), el motor de reglas de decisión deterministas, las interfaces de comunicación (APIs) y la persistencia local de datos, asegurando que el sistema procese eventos del entorno físico y ejecute acciones de acceso de forma rápida, robusta y verificable.

> **¿Por qué VIGIA necesita este puesto?**  
> Sin el Ingeniero de Software, los sensores y cámaras serían únicamente dispositivos pasivos sin capacidad de decisión: no existiría la lógica que contrasta matrículas con listas de permisos, no habría persistencia de eventos para auditoría y la interfaz gráfica no podría recibir datos en tiempo real para el operador.

---

## 3. Responsabilidad principal

Diseñar, codificar, integrar, depurar y mantener los componentes de software de VIGIA (`VIGIA_Core/`), los servicios de lógica de decisión, las APIs de integración y la base de datos local, asegurando la calidad del código, el desacoplamiento modular y la ejecución confiable del lazo cerrado.

---

## 4. ¿Qué hago?

### Actividades principales:
* Diseñar la arquitectura modular de software y estructurar los módulos centrales del sistema (`VIGIA_Core/`).
* Implementar la lógica de toma de decisiones deterministas para el control de acceso vehicular (evaluación de permisos, horarios y estados).
* Desarrollar e integrar servicios de comunicación mediante APIs y controladores para la transmisión de datos hacia el Dashboard y el hardware.
* Implementar y mantener el esquema de persistencia y almacenamiento local en base de datos (SQLite) con registros de auditoría.
* Diseñar y ejecutar pruebas técnicas y unitarias automatizadas para garantizar la estabilidad y calidad del código.

### Actividades de apoyo:
* Mantener el repositorio de código, control de versiones (Git) y aplicar estándares de estilo y buenas prácticas.
* Definir contratos de datos estructurados para el intercambio de información entre el procesamiento de visión, el backend y la interfaz de usuario.
* Implementar mecanismos de manejo de excepciones y registro de eventos (*logging*) para diagnóstico técnico.

### Actividades de coordinación:
* Coordinar con el Ingeniero de Diseño de Circuitos los protocolos de comunicación y tramas de datos serie para interactuar con la PCB.
* Coordinar con el Diseñador UX/UI la integración de las APIs que alimentan visualmente el Dashboard.
* Validar con el Analista que la lógica programada cumpla estrictamente con los requerimientos y casos de uso especificados.

---

## 5. ¿Qué recibo?

| Insumo / Información | De quién proviene | Para qué lo utilizo |
| :--- | :--- | :--- |
| Especificación de requerimientos lógicos y casos de uso | Analyst | Conocer las reglas de decisión, validaciones y flujos de excepción a programar. |
| Prioridades del backlog e historias de usuario refinadas | Product Owner (PO) | Saber qué módulos y funcionalidades de software deben construirse primero. |
| Contratos de pines, tramas de sensores y comandos de PCB | Circuit Design Engineer | Desarrollar los drivers lógicos y la capa de comunicación serial con el hardware. |
| Wireframes, prototipos y flujos de navegación | UX / UI Designer | Diseñar las APIs y contratos de datos requeridos por la interfaz visual del Dashboard. |
| Directrices de ciberseguridad y gobernanza | CIO | Implementar almacenamiento seguro de datos, cifrado y estándares de código. |

---

## 6. ¿Qué entrego?

| Entregable / Resultado | A quién se entrega | Para qué sirve |
| ---------------------- | ------------------ | -------------- |
| **Código Fuente del Sistema (`VIGIA_Core/`)** | Repositorio del Proyecto | Materializar la lógica central ejecutable y los servicios de VIGIA. |
| **Servicios y APIs de Integración** | UX/UI Designer / Frontend | Proveer los endpoints y datos en tiempo real que consume el Dashboard. |
| **Esquema de Base de Datos y Servicios de Persistencia** | Sistema VIGIA / Auditoría | Almacenar localmente los registros de cruce, vehículos autorizados e incidencias. |
| **Suites de Pruebas Unitarias y Reportes de Cobertura** | Control de Calidad / PO | Demostrar que el software opera sin fallas lógicas bajo casos normales y de error. |
| **Documentación Técnica de Software y Contratos de Datos** | Equipo del proyecto | Facilitar el mantenimiento, modularidad y extensión futura de la plataforma. |

---

## 7. ¿Con quién me relaciono?

| Rol | Tipo de relación | Qué recibo / qué entrego |
| --- | ---------------- | ------------------------ |
| **Analyst** | Especificación y validación lógica | **Recibo:** Requerimientos detallados y casos de prueba.<br>**Entrego:** Consultas de viabilidad de datos y software conforme a especificación. |
| **Product Owner (PO)** | Alineación de valor y aceptación | **Recibo:** Criterios de aceptación y prioridades del backlog.<br>**Entrego:** Incrementos de software funcionando para su validación de aceptación. |
| **Circuit Design Engineer** | Integración físico-lógica | **Recibo:** Especificaciones de comunicación de la PCB y señales de sensores.<br>**Entrego:** Capa de abstracción de hardware (HAL) y comandos de control. |
| **UX / UI Designer** | Integración de interfaces | **Recibo:** Prototipos interactivos y campos de pantalla requeridos.<br>**Entrego:** APIs de datos estructurados para alimentar el Dashboard. |
| **Chief Information Officer (CIO)** | Gobernanza y seguridad | **Recibo:** Políticas de ciberseguridad y entornos de despliegue.<br>**Entrego:** Código auditable con protección de datos y persistencia segura. |

---

## 8. Límites de responsabilidad

### Mi responsabilidad SÍ incluye:
* La arquitectura de software, codificación de servicios centrales y lógica de decisión en Python.
* El diseño de la base de datos local SQLite y servicios de persistencia de eventos.
* El desarrollo de las APIs y contratos de datos para comunicación con el Dashboard.
* La ejecución de pruebas unitarias y pruebas de integración lógica del software.

### Mi responsabilidad NO incluye:
* **El ruteo físico de la placa PCB o soldadura de componentes:** Corresponde al Circuit Design Engineer.
* **El diseño de la red eléctrica de potencia y protecciones de caseta (en rol Software):** Corresponde al Electrical Design Engineer *(aun cuando coincida la misma persona física en ambos roles)*.
* **El diseño gráfico y visual de interfaces:** Corresponde al UX/UI Designer.
* **La priorización del backlog de negocio:** Corresponde al Product Owner.
* **La especificación formal de casos de uso de negocio:** Corresponde al Analyst.

---

## 9. Lugar dentro del flujo global

El Ingeniero de Software es el **eje central de la lógica en el desarrollo concurrente**:

$$\text{Requerimientos (Analyst)} \longrightarrow \mathbf{\text{[SOFTWARE ENGINEER]}} \longrightarrow \text{Software Modular Probado} \longrightarrow \text{Integración Físico-Lógica} \longrightarrow \text{VIGIA}$$

Construye la plataforma de software en paralelo con el diseño de hardware electrónico y eléctrico, permitiendo acoplar la lógica con los componentes físicos en la etapa de integración.

---

## 10. Interfaces críticas

### 1. Software Engineer $\longleftrightarrow$ Circuit Design Engineer
* **Información / artefacto:** Protocolo de comunicación serial (JSON/tramas binarias de sensores y actuadores).
* **Propósito:** Permitir que el software lea en tiempo real los sensores de caseta y active la barrera física.
* **Resultado:** Lazo cerrado operativo entre el mundo lógico y el mundo físico.

### 2. Software Engineer $\longleftrightarrow$ UX/UI Designer
* **Información / artefacto:** Contratos de API para el Dashboard.
* **Propósito:** Proveer al frontend los datos de estado del carril, placa detectada y alertas operativas.
* **Resultado:** Dashboard interactivo que refleja el estado de la caseta en tiempo real.

---

## 11. Responsabilidad de validación

### ¿Qué valida este rol?
* Valida la **calidad técnica del código**: ejecución correcta de pruebas unitarias, manejo exhaustivo de excepciones y rendimiento de consultas a bases de datos.
* Valida los **contratos de API y comunicación serial**: que los datos se transmitan sin corrupción ni pérdidas de paquetes.
* Valida la **persistencia e integridad de datos**: que cada cruce vehicular genere un registro auditable e inmutable en SQLite local.

### ¿Qué NO valida este rol?
* No valida la compatibilidad electromagnética de las PCBs (Hardware).
* No valida la capacidad de corriente de las líneas de potencia (Eléctrico).
* No valida la ergonomía visual ni estándares WCAG de la interfaz (UX/UI).
* No valida la aceptación funcional de negocio (PO).

---

## 12. Pregunta clave del rol

> **¿Cuál es la contribución principal de este puesto a VIGIA?**  
> *"Mi contribución es construir el cerebro lógico de VIGIA: transformo los requerimientos en una arquitectura de software robusta, modular y probada que toma decisiones autónomas de acceso en milisegundos y mantiene un registro auditable de cada evento físico."*

---

## 13. Defensa de 30 segundos (Pitch para coevaluación)

> *"Como Ingeniero de Software de VIGIA, mi responsabilidad es diseñar, codificar e integrar los componentes centrales de software (`VIGIA_Core/`), las APIs de comunicación y la persistencia local de datos. Recibo los requerimientos formales del Analista, las historias priorizadas del PO y los contratos de hardware de Circuitos, y entrego código fuente modular probado, APIs funcionales y la base de datos estructurada. Trabajo con Circuitos para enlazar los drivers de sensores y con UX/UI para conectar el Dashboard. Mi límite es claro: yo desarrollo la lógica, APIs y persistencia de software, mientras que el Analyst especifica requerimientos y Hardware construye la electrónica física."*

---

## 14. Preguntas probables del profesor

1. **¿Qué hace exactamente el Ingeniero de Software en VIGIA?**  
   *Respuesta:* Diseño la arquitectura de software, programo los módulos centrales en Python (`VIGIA_Core/`), implemento el motor de reglas de decisión de acceso, desarrollo las APIs para el Dashboard, gestiono la base de datos SQLite y aplico pruebas unitarias.

2. **¿Cuál es la diferencia entre tu trabajo y el del Analista?**  
   *Respuesta:* El Analista define y especifica la lógica formal y los requerimientos del sistema desde el punto de vista funcional; yo traduzco esas especificaciones en arquitectura de software, patrones de diseño y código ejecutable probado.

3. **¿Cómo está estructurada la arquitectura de software de VIGIA?**  
   *Respuesta:* Se basa en un diseño modular desacoplado (Clean Architecture / Patrón Mediador), donde el núcleo de decisión está aislado de la capa de hardware y de la interfaz de usuario mediante interfaces abstractas y contratos de datos.

4. **¿Por qué se eligió SQLite como base de datos para la caseta?**  
   *Respuesta:* Porque es un motor de base de datos embebido, ligero, libre de mantenimiento y transaccional (ACID), ideal para operar localmente en el host de caseta de forma ininterrumpida sin depender de servidores externos.

5. **¿Cómo garantizas que el software no falle ante datos inesperados?**  
   *Respuesta:* Implemento tipado estricto, validación de contratos de datos, manejo exhaustivo de excepciones y suites de pruebas unitarias automatizadas con *mocks* para simular escenarios de error.

6. **¿Cómo se comunica el software con la placa de circuitos (PCB)?**  
   *Respuesta:* A través de un puerto de comunicación serial estandarizado, donde el software envía comandos estructurados de actuación y recibe eventos sensoriales mediante una capa de abstracción de hardware (HAL).

7. **¿Cómo entregas la información al Diseñador UX/UI para el Dashboard?**  
   *Respuesta:* A través de interfaces de programación (APIs) y eventos estructurados que exponen el estado del carril, la matrícula reconocida, el resultado de la autorización y las bitácoras históricas.

8. **¿Quién valida que tu código funcione correctamente?**  
   *Respuesta:* Yo valido la calidad técnica mediante pruebas unitarias y de integración; el Product Owner valida la aceptación funcional cuando el software opera en el escenario rector de la caseta.

9. **¿Qué ocurre si la computadora pierde conexión de red?**  
   *Respuesta:* El software de VIGIA está diseñado con arquitectura *offline-first*: evalúa los permisos localmente en su base de datos SQLite y continúa operando de forma autónoma sin interrumpir el paso vehicular.

10. **¿Cómo manejas el doble rol con Ingeniería Eléctrica?**  
    *Respuesta:* Mantengo la frontera técnica bien delimitada: en Software atiendo la lógica digital, algoritmos y persistencia; en Diseño Eléctrico aseguro la infraestructura de potencia, cableado y seguridad física.

---

## 15. Preguntas trampa / de presión

1. **"¿Entonces tú eres responsable de diseñar los diagramas de flujo de negocio del proyecto?"**  
   *Respuesta correcta:* *"No. Los diagramas de procesos operativos corresponden al Ingeniero de Procesos y las especificaciones lógicas al Analista. Yo diseño los diagramas de arquitectura técnica y diagramas de clases para la implementación del software."*

2. **"¿Si la barrera física no levanta por falta de voltaje, es un error de software?"**  
   *Respuesta correcta:* *"No. Si el software emitió la trama de activación correctamente por el puerto serie, una falla de accionamiento eléctrico corresponde a la etapa de potencia del Ingeniero Eléctrico o a la etapa de conmutación de Circuitos."*

3. **"¿Tú decides qué campos y botones van en la interfaz gráfica del Dashboard?"**  
   *Respuesta correcta:* *"No. La experiencia del operador, distribución visual y accesibilidad las define el Diseñador UX/UI; yo implemento las APIs para que esos controles ejecuten las funciones lógicas correspondientes."*

---

## 16. Conceptos clave que debo dominar

* **Arquitectura Modular / Clean Architecture:** Separación estricta entre la lógica de negocio (`VIGIA_Core/`), los controladores de hardware y las interfaces visuales.
* **Persistencia Local (SQLite):** Almacenamiento seguro, estructurado y transaccional de datos de acceso y bitácoras en el host local.
* **Capa de Abstracción de Hardware (HAL):** Módulo de software que permite desacoplar la lógica del sistema de los detalles específicos de los microcontroladores.
* **Pruebas Unitarias y Mocks:** Pruebas automatizadas de funciones individuales simulando entradas del hardware para verificar robustez lógica.
* **Arquitectura Offline-First:** Capacidad del software de operar localmente con total autonomía sin depender de conectividad a internet o servidores remotos.

---

## 17. Escenario de falla

> **¿Qué sucede si el Ingeniero de Software no cumple correctamente su responsabilidad?**  
> Si el Ingeniero de Software falla:
> 1. El motor de reglas toma decisiones lentas o erróneas, autorizando accesos no permitidos o bloqueando a usuarios legítimos.
> 2. Las APIs fallan o transmiten datos desordenados, provocando que el Dashboard del **UX/UI** muestre estados incorrectos o se congele.
> 3. La base de datos no registra los eventos, dejando al sistema sin trazabilidad ni evidencia de auditoría ante incidentes.
> 4. **Impacto en VIGIA:** El sistema físico queda inoperativo o inseguro, perdiendo la capacidad de actuar de forma autónoma y determinista.

---

## 18. Resumen de defensa

| Elemento | Respuesta sintética |
| :--- | :--- |
| **Titular** | Perez Medina Yair |
| **Puesto** | Ingeniero de Software (Software Engineer) |
| **Qué hago** | Diseño, codifico e integro los módulos centrales (`VIGIA_Core/`), APIs, base de datos y pruebas unitarias. |
| **Qué recibo** | Requerimientos del Analista, prioridades del PO y contratos de pines de Circuitos. |
| **Qué entrego** | Código fuente modular, APIs de comunicación, esquemas de BD y suites de pruebas unitarias. |
| **Con quién trabajo** | Analyst, Product Owner, Circuit Design Engineer, UX/UI Designer y CIO. |
| **Qué valido** | Funcionamiento técnico del software, calidad del código, pruebas unitarias y contratos de API. |
| **Qué NO hago** | No diseño circuitos de hardware, no ruteo PCBs ni impongo prioridades de negocio. |
| **Dónde participo** | En la etapa de desarrollo técnico concurrente previa y durante la integración físico-lógica. |
| **Mi responsabilidad principal** | Diseñar, codificar e integrar el software central, las APIs y la persistencia local de VIGIA. |

---

## 19. Contradicciones documentales

### Contradicción 1: Cargo inexistente "CTO" en ficha PDF
* **Documento:** `Ficha_Ingeniero_de_Software.pdf` (Sección 2.3).
* **Dato encontrado:** "Jefe inmediato: Chief Technology Officer (CTO)".
* **Problema:** En el organigrama y gobernanza oficial de VIGIA no existe la figura de CTO.
* **Interpretación coherente:** La línea de reporte tecnológico y estratégico es con el CIO, mientras que la coordinación funcional de entregables se realiza con el Product Owner.
* **Acción recomendada:** Señalar en la defensa académica que la referencia a CTO es un residuo formal de plantilla identificado para fe de erratas.

---

## 20. Auditoría final

* [x] **Identidad:** Nombre completo (*Perez Medina Yair*) extraído del PDF y cotejado con `Ficha_descripcion_de_roles.md`.
* [x] **Coherencia con VIGIA:** Enfoque explícito en el núcleo `VIGIA_Core/`, lazo cerrado, persistencia SQLite y APIs de caseta.
* [x] **Coherencia entre roles:** Diferenciación nítida frente al Analyst (código vs. especificación) y UX/UI (backend/APIs vs. diseño visual).
* [x] **Defensa oral:** Pitch de 30 segundos estructurado y memorizable.
* [x] **Realismo académico:** Sin dependencias ficticias; arquitectura modular aplicable a la escala real del proyecto.