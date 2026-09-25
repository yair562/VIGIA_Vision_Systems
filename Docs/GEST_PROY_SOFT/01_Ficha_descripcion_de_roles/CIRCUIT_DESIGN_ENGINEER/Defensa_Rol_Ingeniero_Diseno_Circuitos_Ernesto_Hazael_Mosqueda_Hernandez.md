# Ficha Individual de Defensa de Rol — Ingeniero de Diseño de Circuitos (Circuit Design Engineer)
## Proyecto: VIGIA Vision Systems

---

## 1. Identificación del puesto

* **Titular del puesto:** Mosqueda Hernandez Ernesto Hazael
* **Nombre oficial del puesto:** Ingeniero de Diseño de Circuitos
* **Nombre en inglés / Siglas:** Circuit Design Engineer
* **Área o Naturaleza del rol:** Ingeniería Electrónica, Diseño de PCBs y Microelectrónica Embebida
* **Ubicación dentro del flujo global:** Cuarta etapa: Diseño y desarrollo técnico concurrente (Electrónica y Microelectrónica) previo a la integración física-lógica.

---

## 2. Propósito del puesto

El Ingeniero de Diseño de Circuitos existe dentro de VIGIA para materializar la capa física de procesamiento de señales y control embebido. Su propósito es diseñar, simular, rutear y ensamblar las placas de circuito impreso (PCB) que permiten capturar con precisión las señales de los sensores físicos de la caseta (presencia de vehículo, finales de carrera de barrera) y enviar los comandos de activación a los actuadores mecánicos sin interferencias electromagnéticas.

> **¿Por qué VIGIA necesita este puesto?**  
> Sin el Ingeniero de Diseño de Circuitos, el software de VIGIA no tendría una interfaz electrónica confiable para interactuar con el mundo físico: las señales sensoriales llegarían con ruido o distorsión, los microcontroladores carecerían de placas de montaje seguras y existiría riesgo constante de daños por ruido electromagnético o acoplamiento deficiente.

---

## 3. Responsabilidad principal

Diseñar, esquematizar, simular, rutear y validar físicamente las placas de circuito impreso (PCB) y los subsistemas de microelectrónica de VIGIA, garantizando la integridad de señal, la compatibilidad electromagnética (EMC/EMI) y la comunicación confiable entre los sensores/actuadores físicos y el software del sistema.

---

## 4. ¿Qué hago?

### Actividades principales:
* Diseñar y simular esquemáticos electrónicos y diagramas de bloques ajustados a las necesidades de VIGIA.
* Realizar el diseño y ruteo de placas de circuito impreso (PCB Layout) multicapa considerando planos de tierra y desacoplamiento.
* Seleccionar y documentar componentes microelectrónicos (microcontroladores, sensores, optoacopladores y etapas de excitación).
* Ensamblar prototipos físicos, soldar componentes y realizar depuración (*debugging*) en banco de laboratorio con osciloscopio y multímetro.
* Generar los paquetes de manufactura para proveedores de fabricación de tarjetas (archivos Gerber, BOM y Pick&Place).

### Actividades de apoyo:
* Establecer los contratos de comunicación y asignación de pines (*pinout*) para el enlace serie/bus con el software.
* Evaluar hojas de datos (*datasheets*) de componentes para verificar compatibilidad de voltajes y tiempos de respuesta.
* Verificar reglas de diseño de fabricación (DRC/ERC y DFM/DFA).

### Actividades de coordinación:
* Coordinar con el Ingeniero de Diseño Eléctrico el acoplamiento de las etapas de potencia y aislamiento de tierra.
* Coordinar con el Ingeniero de Software los protocolos de transmisión de datos de sensores y comandos de actuadores.

---

## 5. ¿Qué recibo?

| Insumo / Información | De quién proviene | Para qué lo utilizo |
| :--- | :--- | :--- |
| Requerimientos de supervisión sensorial y actuación física | Analyst / Product Owner | Identificar qué sensores y actuadores deben conectarse a la caseta inteligente. |
| Especificaciones de alimentación, potencia y fuentes | Electrical Design Engineer | Diseñar las etapas de regulación local (ej. 5V/3.3V) y proteger la electrónica de ruidos de potencia. |
| Requerimientos de protocolos de datos y velocidad | Software Engineer | Definir los microcontroladores, velocidades de baudios y buses de comunicación (UART/SPI/I2C). |
| Presupuesto y autorización de compras | CIO / Gestión Financiera | Gestionar la adquisición de componentes y mandar a fabricar las placas PCB con proveedores PCBA. |

---

## 6. ¿Qué entrego?

| Entregable / Resultado | A quién se entrega | Para qué sirve |
| ---------------------- | ------------------ | -------------- |
| **Diagramas Esquemáticos Electrónicos** | Equipo de Ingeniería | Documentar la conexión lógica y circuital de cada componente electrónico. |
| **Archivos de Fabricación PCB (Gerber, BOM, Layout)** | Fabricantes de PCB y Archivo Técnico | Enviar a manufactura física las placas de circuito impreso del proyecto. |
| **Tarjetas Electrónicas Prototipadas y Depuradas** | Integración del Sistema (Hardware Host) | Conectar físicamente los sensores de caseta y comandar las barreras/semáforos. |
| **Especificación de Interfaces de Pines y Comunicación** | Software Engineer | Programar los controladores lógicos y lectura de puertos para interactuar con la PCB. |

---

## 7. ¿Con quién me relaciono?

| Rol | Tipo de relación | Qué recibo / qué entrego |
| --- | ---------------- | ------------------------ |
| **Electrical Design Engineer** | Colaboración técnica y acoplamiento físico | **Recibo:** Niveles de voltaje de potencia y protecciones de línea.<br>**Entrego:** Esquemáticos de conexión y requerimientos de consumo de PCB. |
| **Software Engineer** | Contratos de interfaz y comunicación lógica | **Recibo:** Requerimientos de telemetría y comandos de actuación.<br>**Entrego:** Asignación de pines, formatos de trama y hardware probado. |
| **Product Owner (PO)** | Alineación de alcance funcional | **Recibo:** Prioridades de casos de uso del hardware de caseta.<br>**Entrego:** Estado de avance del prototipado físico y fechas de disponibilidad. |
| **Chief Information Officer (CIO)** | Gestión presupuestaria y proveedores | **Recibo:** Aprobación de inversión y cotizaciones de PCBA.<br>**Entrego:** Requerimientos de componentes y especificaciones de proveedores. |

---

## 8. Límites de responsabilidad

### Mi responsabilidad SÍ incluye:
* El diseño, esquemáticos, ruteo de PCB y microelectrónica de adquisición y control.
* La integridad de señal, filtrado de ruido y desacoplamiento de microcontroladores.
* La soldadura, ensamble y pruebas de banco de laboratorio de las tarjetas electrónicas.
* La generación de archivos de manufactura electrónica (BOM, Gerber).

### Mi responsabilidad NO incluye:
* **El diseño de la red eléctrica general de potencia de la caseta:** Las acometidas de corriente alterna, fuentes conmutadas principales y protecciones térmicas son del Electrical Design Engineer.
* **El desarrollo de la lógica central del software en Python:** La arquitectura de software y base de datos es del Software Engineer.
* **El diseño visual del Dashboard:** Es responsabilidad de UX/UI.
* **La priorización del backlog:** Corresponde al Product Owner.
* **El modelado de procesos metodológicos:** Es del Process Engineer.

---

## 9. Lugar dentro del flujo global

El Ingeniero de Diseño de Circuitos participa en el **núcleo de desarrollo concurrente de ingeniería**:

$$\text{Requerimientos} \longrightarrow \mathbf{\text{[CIRCUIT DESIGN ENGINEER]}} \longrightarrow \text{PCB Fabricada y Depurada} \longrightarrow \text{Integración Físico-Lógica} \longrightarrow \text{VIGIA}$$

Trabaja en paralelo con Ingeniería de Software e Ingeniería Eléctrica para que el hardware electrónico esté listo y probado al momento del ensamble de la caseta.

---

## 10. Interfaces críticas

### 1. Circuit Design $\longleftrightarrow$ Electrical Design
* **Información / artefacto:** Puntos de conexión de potencia y aislamiento galvánico.
* **Propósito:** Evitar que los picos inductivos de los motores de barrera dañen los microcontroladores.
* **Resultado:** Etapa electrónica protegida con optoacopladores y tierras aisladas.

### 2. Circuit Design $\longleftrightarrow$ Software Engineer
* **Información / artefacto:** Contrato de comunicación serie (baudios, tramas de sensores, comandos de relé).
* **Propósito:** Que el software envíe órdenes a la PCB y reciba el estado de los sensores en tiempo real.
* **Resultado:** Enlace bidireccional fluido entre la lógica del sistema y el mundo físico.

---

## 11. Responsabilidad de validación

### ¿Qué valida este rol?
* Valida la **integridad de señales eléctricas de baja tensión**: niveles lógicos a 3.3V/5V, ausencia de rebotes (*bouncing*) en sensores mecánicos y respuesta limpia de osciloscopio.
* Valida la **compatibilidad electromagnética (EMC/EMI)** y disipación térmica de los reguladores de voltaje en la PCB.
* Valida la **continuidad eléctrica y ausencia de cortocircuitos** en las placas antes de energizar.

### ¿Qué NO valida este rol?
* No valida el código Python de alto nivel ni consultas a bases de datos (Software).
* No valida la carga total de corriente en las líneas de potencia de la caseta (Eléctrico).
* No valida la usabilidad de la interfaz de usuario (UX/UI).
* No valida los criterios de negocio del usuario final (PO).

---

## 12. Pregunta clave del rol

> **¿Cuál es la contribución principal de este puesto a VIGIA?**  
> *"Mi contribución es crear la base física de microelectrónica de VIGIA: transformo las necesidades de control en placas PCB confiables y libres de ruido, permitiendo que los sensores y actuadores de la caseta se comuniquen de forma determinista con el software."*

---

## 13. Defensa de 30 segundos (Pitch para coevaluación)

> *"Como Ingeniero de Diseño de Circuitos de VIGIA, mi responsabilidad es diseñar, simular, rutear y validar físicamente las placas PCB y la microelectrónica del sistema. Recibo los requerimientos de supervisión física del Analista y las especificaciones de potencia del Ingeniero Eléctrico, y entrego esquemáticos electrónicos, archivos de fabricación Gerber y prototipos de PCB funcionales y depurados. Trabajo directamente con Ingeniería Eléctrica para aislar ruido y con Software para definir contratos de comunicación serie. Mi límite es claro: yo me encargo de la microelectrónica y señales de PCB, mientras que Diseño Eléctrico maneja la potencia general y Software programa la lógica del sistema."*

---

## 14. Preguntas probables del profesor

1. **¿Qué hace exactamente el Ingeniero de Diseño de Circuitos en VIGIA?**  
   *Respuesta:* Diseño los esquemáticos electrónicos, ruteo las placas de circuito impreso (PCB) multicapa, selecciono los componentes microelectrónicos, armo los prototipos en laboratorio y compruebo la integridad de señal con instrumental técnico.

2. **¿Cuál es la diferencia exacta entre tu trabajo y el del Ingeniero de Diseño Eléctrico?**  
   *Respuesta:* Yo diseño la microelectrónica de señal en PCB (sensores, microcontroladores, comunicación a 3.3V/5V y bajo ruido); el Ingeniero Eléctrico diseña la alimentación de potencia general de la caseta (fuentes, distribución, motores, protecciones y seguridad física).

3. **¿Cómo evitas que el ruido de los motores de la barrera afecte a los sensores?**  
   *Respuesta:* Incorporo en el diseño de circuitos desacoplamiento con condensadores cerámicos, planos de masa sólidos, optoaislamiento en las salidas de control y diodos *flyback* para suprimir voltajes inductivos.

4. **¿Qué entregable concreto de tu área se requiere para mandar a fabricar las placas?**  
   *Respuesta:* El paquete completo de manufactura: archivos Gerber para fotoplotter, archivos de perforación Excellon, la lista estructurada de materiales (BOM) y el diagrama de colocación de componentes (Pick & Place).

5. **¿Qué instrumentos utilizas en el laboratorio para validar tus diseños?**  
   *Respuesta:* Osciloscopio digital para verificar formas de onda y tiempos de conmutación, analizador lógico para validar tramas de comunicación digital y multímetro para continuidad y niveles de voltaje.

6. **¿Cómo te coordinas con el Ingeniero de Software?**  
   *Respuesta:* Le entrego la tabla de asignación de pines (*pinout*), los niveles lógicos activos (alto/bajo) y acordamos los protocolos de transmisión serial para que el software lea los sensores y active las barreras.

7. **¿Qué ocurre si un componente seleccionado no está disponible en el mercado?**  
   *Respuesta:* Como parte de mi competencia técnica en selección de componentes, busco equivalentes directos (*pin-to-pin*) o rediseño la etapa circuital para asegurar la continuidad del proyecto.

8. **¿Quién valida tu trabajo antes de que se integre al producto final?**  
   *Respuesta:* Yo realizo las pruebas de banco de laboratorio; posteriormente, la integración se valida en conjunto con el Ingeniero de Software (comunicación lógica) y el Ingeniero Eléctrico (energización).

9. **¿Por qué VIGIA requiere una PCB diseñada a medida en lugar de cables sueltos en una protoboard?**  
   *Respuesta:* Porque una caseta vehicular opera en un entorno industrial con vibraciones y ruido electromagnético; una PCB multicapa ruteada garantiza robustez física, repetibilidad y confiabilidad en lazo cerrado.

10. **¿Cómo manejas el doble rol con el CIO?**  
    *Respuesta:* En el rol técnico de Circuitos respondo operativamente a los plazos del backlog y a las pruebas técnicas; en el rol de CIO mantengo la perspectiva estratégica, financiera y de seguridad global.

---

## 15. Preguntas trampa / de presión

1. **"¿Entonces tú también programas los algoritmos de visión artificial y la lógica en Python?"**  
   *Respuesta correcta:* *"No. La programación en Python y la visión artificial corresponden al Ingeniero de Software. Mi trabajo termina en la placa PCB y la transmisión confiable de señales hacia el host."*

2. **"¿Si la fuente de alimentación de la caseta se quema por una sobretensión de la red eléctrica, fue error de diseño de tu circuito?"**  
   *Respuesta correcta:* *"No necesariamente. El dimensionamiento de la red eléctrica principal, los supresores de transitorios y las fuentes de poder generales son responsabilidad del Ingeniero Eléctrico. Mi responsabilidad es que la PCB tenga protecciones locales contra sobretensión en sus entradas de alimentación."*

3. **"¿Tú decides qué sensores comprar sin consultar al Product Owner?"**  
   *Respuesta correcta:* *"No. Yo propongo los modelos técnicamente viables y precisos para cumplir el requerimiento de detección, pero el alcance y presupuesto deben estar alineados con el PO y aprobados en la gobernanza de TI."*

---

## 16. Conceptos clave que debo dominar

* **PCB Layout:** Ruteo físico de pistas de cobre multicapa para conectar componentes electrónicos respetando distancias de aislamiento y anchos de pista.
* **Integridad de Señal (Signal Integrity):** Garantía de que una señal digital o analógica viaje desde el sensor al microcontrolador sin deformaciones ni falsos disparos.
* **EMC / EMI (Electromagnetic Compatibility / Interference):** Diseño circuital orientado a evitar que el ruido electromagnético interfiera con el funcionamiento del sistema.
* **Archivos Gerber:** Formato vectorial estándar de la industria que describe cada capa física de la PCB para su manufactura automatizada.
* **Optoaislamiento:** Uso de componentes ópticos para separar eléctricamente la lógica sensible de control de los circuitos de potencia que manejan actuadores mecánicos.

---

## 17. Escenario de falla

> **¿Qué sucede si el Ingeniero de Diseño de Circuitos no cumple correctamente su responsabilidad?**  
> Si el Ingeniero de Circuitos falla:
> 1. Las tarjetas PCB presentan ruido en las líneas de sensores, generando lecturas falsas de aproximación vehicular.
> 2. Las señales de control hacia las barreras no tienen suficiente corriente de disparo o sufren rebotes, bloqueando los actuadores.
> 3. El **Ingeniero de Software** recibe datos corruptos por el puerto serie y no puede determinar el estado real del entorno físico.
> 4. **Impacto en VIGIA:** Se rompe el lazo cerrado de control; el sistema no puede verificar si la barrera realmente abrió o si el vehículo despejó el carril, comprometiendo la seguridad física de la caseta.

---

## 18. Resumen de defensa

| Elemento | Respuesta sintética |
| :--- | :--- |
| **Titular** | Mosqueda Hernandez Ernesto Hazael |
| **Puesto** | Ingeniero de Diseño de Circuitos (Circuit Design Engineer) |
| **Qué hago** | Diseño, simulo, ruteo y valido placas PCB multicapa y circuitos de microelectrónica. |
| **Qué recibo** | Requerimientos de supervisión sensorial y especificaciones de suministro eléctrico. |
| **Qué entrego** | Esquemáticos electrónicos, archivos Gerber/BOM y tarjetas PCB físicas depuradas. |
| **Con quién trabajo** | Ingeniero de Diseño Eléctrico, Ingeniero de Software, Product Owner y Proveedores PCBA. |
| **Qué valido** | Integridad de señal, compatibilidad EMC/EMI, continuidad y niveles de voltaje en laboratorio. |
| **Qué NO hago** | No diseño redes de potencia eléctrica general ni programo la lógica del software central. |
| **Dónde participo** | En la etapa de desarrollo técnico concurrente previa y durante la integración física. |
| **Mi responsabilidad principal** | Diseñar y validar la microelectrónica y placas PCB que conectan sensores y actuadores de VIGIA. |

---

## 19. Contradicciones documentales

### Contradicción 1: Auto-reporte de doble rol en ficha PDF
* **Documento:** `FICHA_ING_DIS_CIRCUITOS.pdf` (Sección 2.2).
* **Dato encontrado:** Declara como Jefe Superior al "Chief Information Officer (CIO)".
* **Problema:** En la distribución real del equipo, Ernesto Hazael Mosqueda desempeña ambos roles (CIO y Circuit Design Engineer).
* **Interpretación coherente:** En el ámbito de diseño de circuitos opera como especialista técnico sujeto a los plazos del Backlog del Product Owner; en el ámbito corporativo responde como CIO ante la Junta de Inversionistas.
* **Acción recomendada:** Explicar con naturalidad la separación funcional de responsabilidades durante la coevaluación académica.

---

## 20. Auditoría final

* [x] **Identidad:** Nombre completo (*Mosqueda Hernandez Ernesto Hazael*) extraído del PDF y cotejado con `Ficha_descripcion_de_roles.md`.
* [x] **Coherencia con VIGIA:** Enfoque explícito en lazo cerrado, sensores de caseta y ruteo de PCBs.
* [x] **Coherencia entre roles:** Frontera nítida con Ingeniería Eléctrica (señal vs. potencia) e Ingeniería de Software (hardware vs. código).
* [x] **Defensa oral:** Pitch de 30 segundos estructurado y memorizable.
* [x] **Realismo académico:** Herramientas estándar (EDA, SPICE, osciloscopio) sustentadas en la naturaleza del proyecto.