# VIGIA Vision Systems
## 10 — Descripción Integral del Proyecto

**Estado:** Aprobado / Línea Base  
**Versión:** 1.2  
**Fecha:** Septiembre 2026  
**Documento PDF Asociado:** [Descripcion_del_Proyecto_VIGIA.pdf](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/Descripcion_del_Proyecto_VIGIA.pdf)

---

# 1. Identificación y Naturaleza del Proyecto

### 1.1 Naturaleza de la Iniciativa
**VIGIA Vision Systems** es una iniciativa de desarrollo tecnológico e ingeniería aplicada orientada a la creación de una plataforma modular e inteligente para la supervisión, análisis determinista y control automatizado de entornos físicos en tiempo real.

El proyecto cierra la brecha existente entre el procesamiento digital de alto nivel (visión artificial e inteligencia computacional) y la dinámica del mundo físico (sensores y actuadores electromecánicos). VIGIA concibe el entorno no como un conjunto de eventos aislados, sino como un sistema continuo donde sensores y cámaras capturan la realidad, algoritmos extraen contexto semántico, un motor de reglas evalúa decisiones autorizadas y actuadores ejecutan acciones físicas inmediatas, verificando su cumplimiento en tiempo real.

### 1.2 Misión y Visión
* **Misión:** Desarrollar soluciones integradas de software y hardware que transformen la observación óptica en decisiones autónomas, seguras y verificables, optimizando el control de accesos y la supervisión física con mínima latencia y máxima robustez.
* **Visión:** Consolidar a VIGIA como una plataforma modular, confiable y escalable para la gobernanza de entornos físicos inteligentes (accesos vehiculares, estacionamientos, cruces viales e industria) sin requerir rediseños estructurales en su núcleo tecnológico.

### 1.3 Propuesta de Valor Diferencial (*Beyond CCTV & Isolated LPR*)
A diferencia de los sistemas de videovigilancia pasivos (CCTV) o software aislado de lectura de matrículas (LPR) que se limitan a grabar video o mostrar alertas en pantalla dejando la acción y verificación en manos humanas, **VIGIA integra el ciclo operacional completo**:
* **Percibe** con cámaras y sensores físicos.
* **Evalúa** bajo reglas lógicas e invariantes de seguridad física.
* **Actúa** directamente sobre barreras electromecánicas y señalización semafórica.
* **Verifica** en lazo cerrado (*closed-loop*) que el movimiento mecánico realmente ocurrió.
* **Registra** evidencia estructurada e inmutable para auditoría continua.

---

# 2. Planteamiento del Problema y Justificación

En la gestión contemporánea de entornos físicos (accesos vehiculares, estacionamientos y perímetros restringidos) predominan esquemas operativos con deficiencias críticas:
1. **Dependencia de procesos manuales y fatiga:** La revisión visual y accionamiento manual provocan demoras en horas pico, fatiga en guardias y alta vulnerabilidad a accesos no autorizados.
2. **Sistemas aislados y desarticulados:** Cámaras CCTV, barreras vehiculares y bases de datos operan sin comunicación nativa entre sí.
3. **Ausencia de trazabilidad y certeza forense:** Ante incidencias, no existe correlación temporal confiable entre la orden de apertura, la imagen de evidencia y las lecturas sensoriales.
4. **Control en lazo abierto (*Open-Loop*):** Los sistemas tradicionales ordenan abrir o cerrar barreras a ciegas, sin comprobar sensorialmente si el mecanismo respondió o si un vehículo continúa en la trayectoria de paso.

---

# 3. Objetivos del Proyecto

### 3.1 Objetivo General
Desarrollar y validar una plataforma modular e inteligente capaz de supervisar, gobernar y automatizar un entorno físico en tiempo real, integrando visión computacional, sensores, controladores embebidos IoT y software de toma de decisiones deterministas en un ciclo cerrado y verificable.

### 3.2 Objetivos Específicos
1. **Percepción Inteligente:** Desarrollar la capacidad de capturar video del entorno, detectar la aproximación de vehículos y reconocer ópticamente sus matrículas vehiculares (LPR) en forma de observaciones estructuradas con índice de confianza.
2. **Decisión Determinista:** Implementar un gestor de estado y un motor de reglas que evalúe permisos de acceso de manera segura, garantizando que ninguna acción física se ejecute si viola restricciones de seguridad (*SafetyEnforcer*).
3. **Actuación y Control Embebido:** Diseñar la interfaz de hardware y firmware para comandar de manera confiable dispositivos electromecánicos (barreras y semáforos) mediante protocolos de comunicación robustos.
4. **Verificación en Lazo Cerrado:** Establecer un mecanismo de instrumentación sensorial que compruebe físicamente el cumplimiento de las maniobras comandadas y detecte anomalías o bloqueos mecánicos.
5. **Memoria Operacional y Auditoría:** Construir un repositorio de persistencia local que conserve la cronología completa de cada evento, correlacionando la decisión tomada con la evidencia fotográfica y la telemetría física.
6. **Validación Integral del Sistema:** Demostrar y documentar el funcionamiento ininterrumpido del sistema completo en un escenario de prueba representativo (maqueta/banco de laboratorio) bajo condiciones normales y casos límite.

---

# 4. Arquitectura y Ciclo Operativo Fundamental

### 4.1 El Ciclo Operativo de 7 Fases
\text{Observar} \longrightarrow \text{Interpretar} \longrightarrow \text{Decidir} \longrightarrow \text{Actuar} \longrightarrow \text{Verificar} \longrightarrow \text{Registrar} \longrightarrow \text{Mejorar}

1. **Observar (Observe):** Adquisición de señales crudas mediante cámaras de video y sensores de presencia/masa metálica.
2. **Interpretar (Interpret):** Transformación de señales visuales en información semántica mediante modelos de IA (detección vehicular y segmentación OCR de matrículas).
3. **Decidir (Decide):** Determinación de la acción requerida evaluando políticas de acceso, listas autorizadas y ventanas horarias.
4. **Actuar (Act):** Transmisión de comandos seguros a actuadores físicos (servomotores de barrera y semáforos LED).
5. **Verificar (Verify):** Comprobación física en lazo cerrado mediante sensores de final de carrera (tope superior) y fotoceldas de despeje.
6. **Registrar (Record):** Almacenamiento estructurado e inmutable de la bitácora (timestamp, placa, decisión, foto y confirmación sensorial).
7. **Mejorar (Improve):** Extracción de detecciones con baja confianza (*Active Learning*) para reentrenamiento continuo y calibración.

### 4.2 Desacoplamiento Modular y Responsabilidades
* **VIGIA_Core/:** Orquestador central, gestor de estado del entorno, guardián de invariantes físicas de seguridad (*SafetyEnforcer*) y mediador desacoplado.
* **VIGIA_Vision/:** Pipeline de captura, localización de placa vehicular, segmentación OCR e inferencia de modelos de visión.
* **VIGIA_IoT/:** Firmware embebido (Arduino/ESP32), acondicionamiento de señales sensoriales y control de potencia para actuadores.
* **VIGIA_Automation/:** Motor de reglas deterministas y políticas operativas de autorización.
* **VIGIA_API/:** Endpoints REST y canales WebSockets para telemetría en tiempo real y servicios externos.
* **VIGIA_Dashboard/:** Panel web reactivo para la supervisión del operador de caseta y mandos de apertura manual supervisada.

---

# 5. Caso de Uso Rector: Caseta Inteligente de Acceso Vehicular

Como escenario rector de validación experimental, VIGIA implementa la automatización integral de una caseta vehicular:
1. **Aproximación:** El vehículo entra a la zona de detección visual y activa el sensor de presencia.
2. **Identificación:** VIGIA_Vision segmenta la matrícula y extrae la cadena de caracteres con su confianza.
3. **Autorización:** VIGIA_Automation evalúa la placa contra la lista autorizada y el horario vigente.
4. **Actuación:** Si es concedido y seguro, se comanda la elevación de la barrera y luz verde.
5. **Verificación:** Sensor de final de carrera confirma que la barrera subió; sensor de despeje confirma el cruce.
6. **Cierre Seguro:** Tras verificar el paso completo y tolerancia de seguridad, la barrera desciende y se archiva el registro forense.

### Invariantes Físicas de Seguridad (*Fail-Safe*)
* **INV-01 (Anti-Aplastamiento):** Prohibición absoluta de descenso mientras la fotocelda detecte presencia en la trayectoria del brazo.
* **INV-02 (Confirmación Mecánica):** No habilitar la señal verde hasta confirmar físicamente el tope superior de la barrera.
* **INV-03 (Falla Segura):** Ante desconexión serial o error de microcontrolador, el sistema conmuta a modo restrictivo seguro.

---

# 6. Organización del Equipo y Metodología

### 6.1 Mapeo de Roles y Entregables Académicos
| Integrante | Puesto / Rol Oficial | Responsabilidad de Ingeniería | Entregable Académico Asignado |
| :--- | :--- | :--- | :--- |
| **Yair Pérez Medina** | Ingeniero de Software + Ing. de Diseño Eléctrico | Arquitectura de software, VIGIA_Core/, backend, persistencia y diseño eléctrico de potencia. | Ficha de Roles + Requerimientos Funcionales y No Funcionales |
| **Karen Vianey Juárez Hernández** | Product Owner (PO) | Visión de producto, gestión del Product Backlog, gobernanza de requerimientos y criterios de aceptación. | Historias de Usuario |
| **Ernesto Hazael Mosqueda Hernández** | CIO + Ing. de Diseño de Circuitos | Diseño de circuitos electrónicos, subsistema VIGIA_IoT/, firmware embebido y gobierno de información. | Logos con accesibilidad + Mapas de recorrido |
| **Cristian Josué Soto Cruz** | Ingeniero de Procesos | Diseño y optimización de flujos operativos, automatización (VIGIA_Automation/) y control metodológico. | Formatos de reunión y minutas |
| **Natalia Guadalupe Ramírez Muciño** | Diseñadora UX / UI | Experiencia de usuario, interfaces interactivas para VIGIA_Dashboard/, wireframes y flujos del operador. | Creación de Personas |
| **Estefany Sarahí Arellano Reyes** | Analista de Requisitos y Datos | Análisis de requisitos de dominio, flujo de datos, especificaciones y soporte a VIGIA_Vision/. | Mapa de Empatía |

### 6.2 Marco Metodológico
* **Scrum por Dominios Concurrentes:** Sprints de 2 semanas con avance paralelo de hardware, visión, backend e interfaz.
* **Testeabilidad Continua:** Suite automatizada en 	ests/ con emuladores de hardware y videos pregrabados (fixtures) para pruebas independientes del hardware físico.

---

# 7. Alcance, Proyección y Conclusión

### 7.1 Delimitación del Alcance (Fase 1 / MVP)
* **Dentro del Alcance:** Plataforma base VIGIA_Core, pipeline LPR, controlador IoT en maqueta de pruebas, dashboard web básico y persistencia local de auditoría.
* **Fuera del Alcance:** Despliegue comercial civil a gran escala, cobro de peajes/pasarelas de pago y dependencia de servidores en la nube.

### 7.2 Escalabilidad Futura
La arquitectura desacoplada de VIGIA proyecta una evolución directa hacia control de accesos peatonales, administración inteligente de estacionamientos, semaforización adaptativa urbana y trazabilidad de materiales en la industria.

### 7.3 Conclusión
VIGIA Vision Systems consolida un nuevo estándar en la interacción físico-digital al transformar la visión artificial de un rol meramente observacional a un sistema activo, seguro y auditable de gobernanza física en lazo cerrado.
