# Ficha Individual de Defensa de Rol — Ingeniero de Diseño Eléctrico (Electrical Design Engineer)
## Proyecto: VIGIA Vision Systems

---

## 1. Identificación del puesto

* **Titular del puesto:** Perez Medina Yair
* **Nombre oficial del puesto:** Ingeniero de Diseño Eléctrico
* **Nombre en inglés / Siglas:** Electrical Design Engineer
* **Área o Naturaleza del rol:** Ingeniería Eléctrica, Distribución de Potencia y Seguridad Eléctrica
* **Ubicación dentro del flujo global:** Cuarta etapa: Diseño y desarrollo técnico concurrente (Infraestructura Eléctrica y Potencia) previo a la integración física.

---

## 2. Propósito del puesto

El Ingeniero de Diseño Eléctrico existe dentro de VIGIA para garantizar que todos los componentes físicos, sensores, barreras, semáforos y computadoras del sistema cuenten con una alimentación eléctrica estable, dimensionada y segura. Su propósito es diseñar la distribución de energía, calcular las protecciones contra sobrecargas y asegurar que la caseta vehicular responda de forma segura ante cortes de energía (*fail-safe*).

> **¿Por qué VIGIA necesita este puesto?**  
> Sin el Ingeniero de Diseño Eléctrico, los motores de las barreras y la electrónica de control sufrirían caídas de tensión, sobrecalentamiento o daños catastróficos por sobrecargas en la red. Asimismo, una instalación eléctrica sin diseño profesional pondría en riesgo la seguridad física de los operadores de caseta y los vehículos.

---

## 3. Responsabilidad principal

Diseñar, calcular, documentar y validar la infraestructura eléctrica, los sistemas de alimentación de potencia, las protecciones contra fallas y el cableado estructurado de la caseta de VIGIA, garantizando un suministro de energía continuo, eficiente y seguro.

---

## 4. ¿Qué hago?

### Actividades principales:
* Diseñar la distribución de circuitos eléctricos y esquemas de alimentación de la caseta VIGIA.
* Dimensionar y seleccionar fuentes de poder conmutadas (AC/DC) y transformadores para actuadores y controladores.
* Calcular y seleccionar dispositivos de protección eléctrica (interruptores termomagnéticos, fusibles y supresores de picos).
* Elaborar planos eléctricos, diagramas unifilares y esquemas de conexionado de potencia.
* Diseñar la lógica de comportamiento seguro ante fallas eléctricas (*fail-safe*) para que la barrera no quede bloqueada ni cause accidentes ante cortes de energía.

### Actividades de apoyo:
* Diseñar el aislamiento de tierras físicas para evitar la transmisión de ruido eléctrico hacia las tarjetas de control.
* Especificar canalizaciones y calibres de cable adecuados para evitar sobrecalentamiento y caídas de tensión por distancia.
* Realizar pruebas de continuidad, medición de aislamiento y estabilidad de voltaje en vacío y bajo carga.

### Actividades de coordinación:
* Coordinar con el Ingeniero de Diseño de Circuitos el acoplamiento entre la alimentación de potencia y la microelectrónica de la PCB.
* Coordinar con el Ingeniero de Software los requerimientos de consumo eléctrico del hardware host de procesamiento.

---

## 5. ¿Qué recibo?

| Insumo / Información | De quién proviene | Para qué lo utilizo |
| :--- | :--- | :--- |
| Requerimientos de actuadores físicos (motores, barreras, semáforos) | Analyst / Product Owner | Determinar la potencia total requerida y las tensiones de operación de la caseta. |
| Requerimientos de consumo y voltajes de microelectrónica (PCB) | Circuit Design Engineer | Dimensionar los ramales de alimentación secundaria y filtros de potencia para las placas. |
| Especificaciones eléctricas del hardware host / cámaras | Software Engineer / CIO | Diseñar las tomas y fuentes dedicadas para el procesamiento de visión por computadora. |
| Presupuesto y directrices de seguridad física | CIO | Seleccionar componentes eléctricos normados dentro de los límites de inversión. |

---

## 6. ¿Qué entrego?

| Entregable / Resultado | A quién se entrega | Para qué sirve |
| ---------------------- | ------------------ | -------------- |
| **Diagramas Unifilares y Planos Eléctricos** | Equipo de Integración e Instalación | Guiar el cableado físico y la conexión segura de todos los equipos de la caseta. |
| **Cuadro de Cargas y Dimensionamiento de Fuentes** | Circuit Design Engineer y CIO | Justificar la selección de fuentes de poder y el consumo energético global. |
| **Especificación de Protecciones y Esquema Fail-Safe** | Equipo Técnico del Proyecto | Garantizar que el sistema proteja a los equipos y personas ante sobrecargas o apagones. |
| **Reportes de Pruebas Eléctricas y Aislamiento** | Evaluación Técnica | Demostrar que los voltajes son estables y no existen riesgos de cortocircuito. |

---

## 7. ¿Con quién me relaciono?

| Rol | Tipo de relación | Qué recibo / qué entrego |
| --- | ---------------- | ------------------------ |
| **Circuit Design Engineer** | Acoplamiento de potencia y señal | **Recibo:** Consumo de la PCB y señales de disparo de relevadores.<br>**Entrego:** Alimentación filtrada y esquemas de conexionado de potencia. |
| **Software Engineer** | Suministro y soporte físico host | **Recibo:** Demanda de energía de la computadora host y cámaras.<br>**Entrego:** Suministro estable y protecciones contra transitorios. |
| **Product Owner (PO)** | Alineación con el escenario rector | **Recibo:** Requerimientos de operación física de la caseta.<br>**Entrego:** Factibilidad eléctrica de los actuadores seleccionados. |
| **Chief Information Officer (CIO)** | Gobernanza de infraestructura física | **Recibo:** Aprobación de recursos para tableros y cableado.<br>**Entrego:** Especificación técnica de materiales eléctricos. |

---

## 8. Límites de responsabilidad

### Mi responsabilidad SÍ incluye:
* El diseño de la red eléctrica de potencia, acometidas, fuentes conmutadas y tableros de protección.
* El cálculo de calibres de conductores, canalizaciones y caídas de tensión.
* El diseño del comportamiento eléctrico *fail-safe* y puesta a tierra física.
* La validación del consumo de corriente y estabilidad de voltaje de la caseta.

### Mi responsabilidad NO incluye:
* **El diseño y ruteo de pistas de la placa PCB:** Corresponde al Circuit Design Engineer.
* **La programación de microcontroladores o software en Python:** Corresponde a Software y Circuitos.
* **El diseño de interfaces gráficas:** Es responsabilidad de UX/UI.
* **La especificación de casos de uso de negocio:** Es del Analyst.
* **La priorización de funcionalidades:** Es del Product Owner.

---

## 9. Lugar dentro del flujo global

El Ingeniero de Diseño Eléctrico forma parte del **bloque de desarrollo concurrente de ingeniería**:

$$\text{Requerimientos} \longrightarrow \mathbf{\text{[ELECTRICAL DESIGN ENGINEER]}} \longrightarrow \text{Infraestructura Eléctrica y Potencia} \longrightarrow \text{Integración Físico-Lógica} \longrightarrow \text{VIGIA}$$

Garantiza que antes de la integración del software con los mecanismos físicos, exista una red de energía probada y protegida para soportar la operación de VIGIA.

---

## 10. Interfaces críticas

### 1. Electrical Design $\longleftrightarrow$ Circuit Design
* **Información / artefacto:** Alimentación de corriente continua (DC), tierras y relevadores de potencia.
* **Propósito:** Separar físicamente la potencia de los motores de la lógica sensible de la PCB.
* **Resultado:** Operación de barreras sin generar picos de voltaje que reinicien el microcontrolador.

### 2. Electrical Design $\longleftrightarrow$ Software Engineer
* **Información / artefacto:** Suministro ininterrumpido y estado de alimentación eléctrica.
* **Propósito:** Asegurar que la computadora host no sufra apagones repentinos que corrompan la base de datos local SQLite.
* **Resultado:** Respaldo y estabilidad eléctrica para la persistencia de datos.

---

## 11. Responsabilidad de validación

### ¿Qué valida este rol?
* Valida la **estabilidad de los voltajes de alimentación**: que las fuentes mantengan voltajes nominales bajo plena carga de los motores.
* Valida el **consumo de corriente y protecciones**: que los interruptores termomagnéticos y fusibles se activen oportunamente ante sobrecargas o cortos.
* Valida el **aislamiento y tierras**: ausencia de fugas eléctricas y correcta derivación de picos de tensión a tierra física.

### ¿Qué NO valida este rol?
* No valida el código fuente del software ni algoritmos de visión.
* No valida la modulación digital de señales en la placa PCB.
* No valida la accesibilidad de la interfaz de usuario.
* No valida el cumplimiento de las historias de usuario (PO).

---

## 12. Pregunta clave del rol

> **¿Cuál es la contribución principal de este puesto a VIGIA?**  
> *"Mi contribución es dotar a VIGIA de una infraestructura de energía segura y robusta: aseguro que todos los sensores, actuadores y computadoras reciban la potencia necesaria de forma ininterrumpida y protegida, garantizando la seguridad eléctrica y la respuesta fail-safe de la caseta."*

---

## 13. Defensa de 30 segundos (Pitch para coevaluación)

> *"Como Ingeniero de Diseño Eléctrico de VIGIA, mi responsabilidad es diseñar, dimensionar y validar la distribución de potencia, protecciones y conexiones eléctricas del sistema. Recibo los requerimientos de consumo de actuadores y computadoras, y entrego planos eléctricos unifilares, esquemas de conexión y sistemas de protección contra sobrecargas y caídas de tensión. Trabajo estrechamente con Ingeniería de Circuitos para acoplar las etapas de potencia y con Software para garantizar estabilidad eléctrica en el procesamiento host. Mi límite es claro: yo me encargo de la infraestructura eléctrica general y seguridad de potencia, mientras que Circuitos maneja la microelectrónica de PCB y Software programa la lógica."*

---

## 14. Preguntas probables del profesor

1. **¿Qué hace exactamente el Ingeniero de Diseño Eléctrico en VIGIA?**  
   *Respuesta:* Diseño la red de alimentación eléctrica de la caseta, selecciono las fuentes de poder, calculo las protecciones termomagnéticas y fusibles, elaboro los planos de conexión y garantizo la seguridad eléctrica del sistema.

2. **¿Cuál es la diferencia entre tu rol y el del Ingeniero de Diseño de Circuitos?**  
   *Respuesta:* Yo atiendo la infraestructura de potencia general (110V/220V AC a 12V/24V DC, motores de barrera, protecciones y cableado de caseta); el Ingeniero de Circuitos atiende la microelectrónica en placa PCB (sensores, microcontroladores y señales a 3.3V/5V).

3. **¿Qué es el esquema fail-safe y cómo lo implementas en VIGIA?**  
   *Respuesta:* Es un diseño de seguridad que ante un corte total de energía desbloquea mecánicamente la barrera o permite su accionamiento manual inmediato, evitando que vehículos queden atrapados o se bloquee el paso de emergencia.

4. **¿Cómo calculas la capacidad de las fuentes de alimentación?**  
   *Respuesta:* Sumo los consumos máximos de corriente de todos los actuadores simultáneos (motor de barrera, luces de semáforo, cámara, host y PCB) y añado un margen de seguridad del 25% al 30% para operar en régimen óptimo.

5. **¿Qué medidas de seguridad eléctrica implementas para los operadores?**  
   *Respuesta:* Aislamiento de conductores, canalizaciones herméticas, conexión a tierra física de todas las carcasas metálicas e interruptores diferenciales para prevenir descargas a los usuarios.

6. **¿Cómo evitas las caídas de tensión en los cables largos hacia la barrera?**  
   *Respuesta:* Calculo el calibre del conductor (AWG) en función de la longitud del carril y la corriente máxima requerida, asegurando que la caída de voltaje sea inferior al 3% permitido por norma.

7. **¿Qué entregable técnico generas para la instalación física?**  
   *Respuesta:* El plano eléctrico unifilar, el esquema de conexionado de bornes y el cuadro de balance de cargas con especificación de protecciones.

8. **¿Cómo te coordinas con el Ingeniero de Software?**  
   *Respuesta:* Verifico que la alimentación de la computadora host y cámaras esté respaldada y libre de fluctuaciones para evitar que caídas de voltaje dañen la base de datos o interrumpan el servicio.

9. **¿Quién valida que el diseño eléctrico sea seguro?**  
   *Respuesta:* Se valida mediante pruebas de banco de aislamiento y carga máxima antes de conectar la electrónica y se somete a revisión del equipo técnico y del CIO.

10. **¿Cómo gestionas el doble rol con Ingeniería de Software?**  
    *Respuesta:* Mantengo la separación técnica de responsabilidades: en Diseño Eléctrico garantizo el suministro y seguridad física; en Software desarrollo los módulos lógicos y servicios de la plataforma.

---

## 15. Preguntas trampa / de presión

1. **"¿Entonces tú eres responsable de reparar el código si el software no manda la orden a la barrera?"**  
   *Respuesta correcta:* *"No en este rol. Como Ingeniero Eléctrico mi responsabilidad es asegurar que si el relevador se activa, el motor reciba el voltaje adecuado para abrir. La emisión del comando lógico corresponde al Ingeniero de Software."*

2. **"¿Por qué es necesario un Ingeniero Eléctrico si basta con conectar todo a un eliminador de pared común?"**  
   *Respuesta correcta:* *"Porque una caseta de acceso vehicular maneja cargas inductivas pesadas como motores y relevadores que generan transitorios y demandan picos de corriente; un diseño eléctrico formal evita incendios, cortocircuitos y fallas operativas continuas."*

3. **"¿Tú decides la ubicación física del Dashboard de control?"**  
   *Respuesta correcta:* *"No. La ergonomía y ubicación de las vistas de control las define el Diseñador UX/UI; mi responsabilidad es asegurar que donde se coloque la pantalla exista una toma de corriente segura y canalizada."*

---

## 16. Conceptos clave que debo dominar

* **Diagrama Unifilar:** Representación gráfica simplificada de un circuito eléctrico que muestra acometidas, tableros, protecciones y cargas.
* **Comportamiento Fail-Safe:** Principio de diseño por el cual una falla en el suministro eléctrico lleva al sistema a un estado seguro para las personas y vehículos.
* **Carga Inductiva:** Equipos como motores o electroimanes que generan picos de corriente al encender y voltajes inversos al apagar.
* **Tierra Física y Aislamiento:** Red de protección para desviar corrientes de fuga y eliminar interferencias en la electrónica de control.
* **Protección Termomagnética:** Dispositivo que desconecta el circuito automáticamente ante sobrecargas sostenidas (térmico) o cortocircuitos instantáneos (magnético).

---

## 17. Escenario de falla

> **¿Qué sucede si el Ingeniero de Diseño Eléctrico no cumple correctamente su responsabilidad?**  
> Si el Ingeniero Eléctrico falla:
> 1. La fuente de poder se satura durante el arranque del motor de la barrera, provocando una caída de voltaje que reinicia la computadora y los microcontroladores.
> 2. No existen protecciones contra sobretensiones, quemando las placas PCB ante una descarga eléctrica en la red.
> 3. La caseta no cuenta con mecanismo *fail-safe*, dejando la barrera trabada y bloqueando el acceso en una emergencia.
> 4. **Impacto en VIGIA:** Pérdida de confiabilidad operativa, riesgos de seguridad física y daños materiales permanentes en el hardware del proyecto.

---

## 18. Resumen de defensa

| Elemento | Respuesta sintética |
| :--- | :--- |
| **Titular** | Perez Medina Yair |
| **Puesto** | Ingeniero de Diseño Eléctrico (Electrical Design Engineer) |
| **Qué hago** | Diseñó la distribución de potencia, dimensiono fuentes de poder, calculo protecciones y esquemas fail-safe. |
| **Qué recibo** | Demandas de consumo de actuadores mecánicos, microelectrónica y computadoras host. |
| **Qué entrego** | Planos eléctricos unifilares, esquemas de conexión de potencia y reportes de pruebas eléctricas. |
| **Con quién trabajo** | Circuit Design Engineer, Software Engineer, Product Owner y CIO. |
| **Qué valido** | Estabilidad de voltaje, capacidad de corriente, funcionamiento de protecciones y aislamiento a tierra. |
| **Qué NO hago** | No ruteo placas PCB de señal ni programo la lógica del software central. |
| **Dónde participo** | En la etapa de desarrollo técnico concurrente previa a la integración física. |
| **Mi responsabilidad principal** | Garantizar un suministro de energía continuo, dimensionado y seguro para todos los componentes de VIGIA. |

---

## 19. Contradicciones documentales

### Contradicción 1: Jerarquía invertida y cargo ficticio en ficha PDF
* **Documento:** `Ficha_Ingeniero_de_diseño_Electrico.pdf` (Secciones 2.2, 2.3 y 2.4).
* **Dato encontrado:** Declara como jefe a un "Chief Technology Officer (CTO)" y en 2.4 indica que le reporta el "Product Owner (PO)".
* **Problema:** En el organigrama de VIGIA no existe el cargo CTO y el Product Owner no le reporta al Ingeniero Eléctrico.
* **Interpretación coherente:** Es un error de plantilla no depurada. La gobernanza estratégica la ejerce el CIO y la dirección funcional del backlog la lidera el Product Owner.
* **Acción recomendada:** Aclarar en la coevaluación que se trata de un residuo de plantilla identificado para su fe de erratas.

---

## 20. Auditoría final

* [x] **Identidad:** Nombre completo (*Perez Medina Yair*) extraído del PDF y cotejado con `Ficha_descripcion_de_roles.md`.
* [x] **Coherencia con VIGIA:** Enfoque explícito en la alimentación de barreras, caseta vehicular y comportamiento fail-safe.
* [x] **Coherencia entre roles:** Diferenciación nítida frente a Circuit Design Engineer (potencia vs. microelectrónica).
* [x] **Defensa oral:** Pitch de 30 segundos estructurado y memorizable.
* [x] **Realismo académico:** Sin tecnologías no sustentadas; cálculos eléctricos enfocados en la escala real del prototipo.