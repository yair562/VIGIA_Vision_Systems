# Flujo Global de Trabajo y Defensa de Roles

## VIGIA Vision Systems

### 1. Propósito

Este documento establece el flujo global de trabajo del proyecto **VIGIA Vision Systems** y proporciona una visión común de las responsabilidades e interacciones entre los puestos que participan en el desarrollo del producto VIGIA.

Su objetivo es que todos los integrantes comprendan:

* **Qué es VIGIA:** Una solución ciberfísica integrada que conecta la percepción visual con el control físico y la automatización en lazo cerrado.
* **Cómo fluye el trabajo** dentro del proyecto.
* **Qué responsabilidad** tiene cada puesto y cuáles son sus límites.
* **Qué información recibe** cada área.
* **Qué resultado genera** cada área.
* **Cómo se relacionan** los diferentes puestos de manera coordinada y no aislada.

Este documento funciona como marco general para la comprensión, alineación y defensa del proyecto en la coevaluación académica. Las responsabilidades detalladas de cada puesto se complementan en sus respectivas fichas de rol.

---

### 2. Flujo global de VIGIA

El trabajo del proyecto se concibe como una cadena de transformación orientada a valor:

$$\text{Objetivos / Necesidades} \longrightarrow \text{Análisis} \longrightarrow \text{Especificación} \longrightarrow \text{Diseño y Desarrollo} \longrightarrow \text{Integración} \longrightarrow \text{Validación} \longrightarrow \text{VIGIA}$$

Estructuralmente, el flujo opera de la siguiente manera:

```text
                    OBJETIVOS / NECESIDADES
                               │
                               ▼
                      PRODUCT OWNER (PO)
                       Define y prioriza
                               │
                               ▼
                            ANALYST
                      Analiza y especifica
                               │
                               ▼
                   REQUERIMIENTOS / ESPECIFICACIÓN
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ▼                      ▼                      ▼
     SOFTWARE              CIRCUITOS              ELÉCTRICO
 (Lógica, APIs, BD)     (PCB, Electrónica)    (Potencia, Seguridad)
        │                      │                      │
        └──────────────────────┼──────────────────────┘
                               │
                          INTEGRACIÓN
                               │
                               ▼
                           VALIDACIÓN
                               │
                               ▼
                         PRODUCTO VIGIA

 ─────────────────────────────────────────────────────────────
  CAPAS DE ACOMPAÑAMIENTO Y GOBIERNO:
   • UX / UI DESIGNER  ───► Acompaña el diseño y la interacción durante el desarrollo
   • PROCESS ENGINEER  ───► Acompaña la organización, estandarización y metodologías
   • CIO (GOBIERNO)    ───► Supervisión transversal, tecnología, seguridad y recursos
 ─────────────────────────────────────────────────────────────
```

---

### 3. Definición de necesidades y producto

#### Product Owner (PO)

El Product Owner representa las necesidades del producto y mantiene la visión funcional y de negocio de VIGIA.

Su función principal consiste en determinar **qué necesita el producto y qué debe atenderse primero**.

El PO trabaja con:
* Necesidades de los usuarios y operadores del sistema.
* Objetivos globales del proyecto y alcance del caso de uso.
* Requerimientos y restricciones de valor.
* Priorización del backlog del producto.
* Definición de criterios de aceptación para cada entrega.

Su principal resultado es una **definición clara y priorizada de lo que el equipo debe construir y validar**.

> **Pregunta clave:**  
> *"¿Qué necesita VIGIA y qué debe desarrollarse primero?"*

---

### 4. Análisis y especificación lógica

#### Analyst

El Analyst toma las necesidades y prioridades definidas por el Product Owner y las transforma en especificaciones lógicas y estructuradas, con el nivel de detalle necesario para que puedan ser utilizadas por las áreas técnicas.

Su responsabilidad se centra en:
* Levantar y organizar información técnica.
* Analizar necesidades operativas y casos de uso.
* Estudiar flujos de trabajo e identificar requerimientos no contemplados.
* Especificar formalmente los requerimientos del sistema.
* Generar documentación técnica de análisis y manuales de operación.

> **Pregunta clave:**  
> *"¿Qué significa exactamente lo que necesita el producto y cómo se puede especificar de manera formal y verificable?"*

---

### 5. Diseño y desarrollo técnico concurrente

A partir de los requerimientos especificados, las tres áreas de ingeniería trabajan de manera coordinada y en paralelo, asegurando compatibilidad mutua mediante contratos de integración.

```text
 ┌──────────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
 │  SOFTWARE ENGINEER   │◄──►│ CIRCUIT DESIGN ENG.  │◄──►│ ELECTRICAL DESIGN ENG│
 │  Lógica, APIs, BD    │    │ PCB, Microelectrónica│    │ Potencia, Seguridad  │
 └──────────────────────┘    └──────────────────────┘    └──────────────────────┘
```

#### Software Engineer
Se encarga de diseñar, estructurar y construir los componentes de software de VIGIA.
* Desarrollo de la arquitectura y módulos centrales de software.
* Integración de servicios y APIs de comunicación.
* Gestión de persistencia y almacenamiento de datos.
* Pruebas técnicas, control de calidad del código y depuración.
* Integración lógica con los controladores del hardware.

> **Pregunta clave:**  
> *"¿Cómo convertimos los requerimientos del sistema en software modular y funcional?"*

#### Circuit Design Engineer
Se encarga del diseño, esquematización y validación de las placas electrónicas y circuitos que procesan señales físicas.
* Diseño de esquemáticos electrónicos y simulación.
* Diseño y ruteo de placas de circuito impreso (PCB).
* Selección de componentes microelectrónicos y sensores.
* Ensamble, verificación en laboratorio y pruebas de señal.
* Coordinación de interfaces de comunicación con el software.

> **Pregunta clave:**  
> *"¿Cómo construimos la electrónica que permite que los sensores y actuadores físicos se comuniquen confiablemente?"*

#### Electrical Design Engineer
Se encarga de la infraestructura eléctrica general, el suministro de energía y la seguridad física del sistema.
* Diseño de la distribución y circuitos de alimentación eléctrica.
* Cálculo y selección de fuentes de poder y protecciones.
* Cableado estructurado y canalizaciones seguras.
* Esquemas de comportamiento seguro ante fallas de energía (*fail-safe*).
* Pruebas de funcionamiento eléctrico y aislamiento.

> **Pregunta clave:**  
> *"¿Cómo proporcionamos energía adecuada, estable y segura para los componentes de VIGIA?"*

---

### 6. Roles de acompañamiento continuo

Ni el diseño de experiencia ni la ingeniería de procesos ocurren de manera aislada al final del proyecto; ambos participan activamente durante el ciclo de desarrollo.

#### UX / UI Designer (Acompañamiento de Interacción)
Se encarga de conceptualizar y diseñar la experiencia de uso y las interfaces mediante las cuales las personas interactúan con VIGIA.
* Investigación de necesidades y contexto del operador (*UX Research*).
* Arquitectura de información y diseño de flujos de interacción (*User Flows*).
* Elaboración de wireframes y prototipos interactivos.
* Diseño visual centrado en accesibilidad, legibilidad y ergonomía.
* Evaluación de usabilidad para retroalimentar el desarrollo del software.

> **Pregunta clave:**  
> *"¿Cómo aseguramos que el usuario pueda comprender e interactuar con VIGIA de manera intuitiva, clara y sin errores?"*

#### Process Engineer (Acompañamiento Organizacional y Operativo)
Se enfoca en modelar, estandarizar y optimizar los procesos de trabajo del equipo y los flujos operativos del producto.
* Modelado y formalización de flujos y procedimientos en diagramas estándar.
* Documentación de procesos operativos de la solución.
* Estandarización de metodologías de trabajo, minutas y formatos de seguimiento.
* Identificación de cuellos de botella y oportunidades de optimización.
* Aseguramiento de la consistencia operativa en la ejecución del proyecto.

> **Pregunta clave:**  
> *"¿Cómo logramos que los procedimientos del equipo y los flujos operativos de VIGIA estén organizados, documentados y se ejecuten de forma consistente?"*

---

### 7. Gobierno y supervisión transversal

#### Chief Information Officer (CIO)

El CIO no representa un paso secuencial de procesamiento de requerimientos, sino una **función transversal de gobierno, dirección y aseguramiento tecnológico** durante todo el ciclo de vida de VIGIA.

Su responsabilidad comprende:
* **Estrategia y alineación:** Asegurar que el desarrollo tecnológico responda a los objetivos globales de la organización.
* **Infraestructura y viabilidad:** Supervisar la disponibilidad de servidores, redes y entornos técnicos de trabajo.
* **Gobierno y recursos:** Administrar presupuestos, viabilidad económica e insumos requeridos por el equipo.
* **Ciberseguridad y continuidad:** Establecer políticas de protección de la información y planes de contingencia.
* **Coordinación general:** Facilitar la resolución de bloqueos interdisciplinarios y la gestión de proveedores.

> **Pregunta clave:**  
> *"¿Cómo gobernamos, protegemos y alineamos los recursos y la infraestructura tecnológica para garantizar la viabilidad y seguridad de VIGIA?"*

---

### 8. Integración

La integración representa el punto de convergencia donde el software, la electrónica de circuitos, la potencia eléctrica y las interfaces de usuario se acoplan para operar como un solo sistema:

```text
               SOFTWARE (Lógica y Servicios)
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
   CIRCUITOS (PCB / Señales)       ELÉCTRICO (Potencia / Red)
            │                                 │
            └────────────────┬────────────────┘
                             │
                             ▼
                     SISTEMA ACOPLADO
                             │
                             ▼
                    INTERFAZ DE USUARIO
```

**Objetivo de la etapa:** Comprobar que las diferentes partes no solo operan de forma aislada, sino que se comunican correctamente a través de sus contratos de interfaz y ejecutan el ciclo completo de supervisión y control físico.

---

### 9. Validación por dominios de responsabilidad

La validación integral del sistema no implica que todos los roles realicen las mismas pruebas. Cada puesto valida el producto desde su propia esfera de competencia técnica:

| Área / Rol | Enfoque de validación | Pregunta de validación |
| :--- | :--- | :--- |
| **Software Engineer** | Funcionamiento técnico del software, pruebas unitarias, APIs y persistencia de datos. | *¿El software procesa los eventos y ejecuta la lógica sin fallas?* |
| **Circuit Design Engineer** | Integridad de señales electrónicas, ausencia de ruido y comunicación con componentes. | *¿La electrónica responde y transmite las lecturas físicas con precisión?* |
| **Electrical Design Engineer** | Suministro de voltaje, consumo de corriente, protecciones y respuesta *fail-safe*. | *¿La distribución eléctrica es estable y segura ante fallas de energía?* |
| **UX / UI Designer** | Facilidad de uso, claridad en la navegación, accesibilidad y retroalimentación visual. | *¿La interfaz permite al usuario operar el sistema con rapidez y sin confusiones?* |
| **Analyst** | Correspondencia estricta entre el sistema construido y los requerimientos especificados. | *¿El sistema cumple fielmente con las especificaciones lógicas documentadas?* |
| **Product Owner (PO)** | Aceptación funcional, cumplimiento de objetivos del producto y entrega de valor. | *¿El producto resuelve el problema planteado y cumple los criterios de aceptación?* |
| **Process Engineer** | Consistencia de flujos de trabajo, tiempos de ciclo y apego a procedimientos estandarizados. | *¿El proceso operativo y la metodología de trabajo se ejecutan de forma fluida y ordenada?* |
| **CIO** | Cumplimiento de estándares de seguridad, disponibilidad de infraestructura y gobernanza TI. | *¿El sistema opera dentro de los lineamientos tecnológicos, legales y de seguridad previstos?* |

---

### 10. Regla común para la defensa en la coevaluación

Para responder con solidez y claridad ante cualquier cuestionamiento, cada integrante debe estructurar su defensa personal con base en **cuatro elementos fundamentales**:

1. **Qué hago:** Mi responsabilidad principal y funciones sustantivas.
2. **Qué recibo:** Los insumos de información o requerimientos que necesito para iniciar mi labor.
3. **Qué entrego:** Los resultados, diseños, código o documentos concretos que genero.
4. **Con quién me relaciono:** Las interfaces de coordinación directa con otros integrantes del equipo.

#### Argumento defensivo clave ante los evaluadores:
Si se pregunta sobre el rol del CIO o la secuencia de trabajo:

> *"El desarrollo técnico se realiza en las áreas correspondientes a partir de los requerimientos del Product Owner y el análisis funcional. El CIO no es una estación de paso del código, sino el rol transversal que gobierna la estrategia tecnológica, los recursos, la infraestructura y la seguridad del proyecto, mientras UX/UI y Procesos acompañan continuamente el diseño de interacción y la estandarización metodológica."*

---

### 11. Resumen de una frase por puesto

| Puesto | Explicación sintética de defensa |
| :--- | :--- |
| **Product Owner (PO)** | Define y prioriza qué necesita el producto y valida que cumpla con los criterios de aceptación. |
| **Analyst** | Analiza, descompone y especifica formalmente los requerimientos y flujos lógicos del sistema. |
| **CIO** | Gobierna la estrategia tecnológica, coordina recursos y asegura la infraestructura y ciberseguridad. |
| **Software Engineer** | Diseña, codifica e integra los componentes de software, las APIs y la persistencia de datos de VIGIA. |
| **Circuit Design Engineer** | Diseña, esquematiza y valida la electrónica y las placas de circuito impreso (PCB). |
| **Electrical Design Engineer** | Diseña, dimensiona y valida la distribución de potencia, protecciones y conexiones eléctricas. |
| **UX / UI Designer** | Diseña la experiencia de usuario, flujos de navegación e interfaces gráficas accesibles. |
| **Process Engineer** | Modela, estandariza y optimiza los procesos operativos y metodologías de trabajo de VIGIA. |