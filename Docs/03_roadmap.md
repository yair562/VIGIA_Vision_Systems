# VIGIA Vision Systems

## 03 — Roadmap de Desarrollo Orientado a Capacidades

**Estado:** Activo / Fase 0  
**Versión:** 2.0 (Consolidación Arquitectónica y Operacional por Capacidades)  
**Pregunta Central:** *¿En qué orden y bajo qué criterios verificables adquiere VIGIA capacidades reales en el entorno físico?*  
**Propósito:** Establecer la hoja de ruta estratégica y evolutiva de VIGIA, organizada rigurosamente en torno a capacidades funcionales demostrables en el mundo real, situando los componentes de software y hardware como habilitadores técnicos subordinados a cada capacidad.

---

## 1. Principio Rector y Filosofía del Avance

En VIGIA, el avance del proyecto **no se mide por carpetas creadas, líneas de código escritas ni patrones de software implementados**, sino por **capacidades demostrables y reproducibles en el entorno físico**.

El progreso se evalúa exclusivamente por la habilidad del sistema para ejecutar de forma confiable, segura y medible las etapas del ciclo rector:

$$\text{Observar} \longrightarrow \text{Interpretar} \longrightarrow \text{Decidir} \longrightarrow \text{Actuar} \longrightarrow \text{Verificar} \longrightarrow \text{Registrar} \longrightarrow \text{Mejorar}$$

```text
       ┌─────────────────────────────────────────────────────────────┐
       │                       ENTORNO FÍSICO                        │
       │     (Vehículos, carriles, barreras, sensores, semáforos)    │
       └──────────────┬───────────────────────────────▲──────────────┘
                      │                               │
                      ▼                               │
               ┌─────────────┐                        │
               │  PERCIBIR   │                        │
               └──────┬──────┘                        │
                      │ Observación estructurada      │
                      ▼                               │
               ┌─────────────┐                        │
               │   DECIDIR   │                        │
               └──────┬──────┘                        │
                      │ Decisión / Comando autorizado │
                      ▼                               │
               ┌─────────────┐                        │
               │   ACTUAR    │────────────────────────┘
               └──────┬──────┘ Acción física en actuador
                      │
                      ▼
               ┌─────────────┐ ◄──────────────────────┐
               │  VERIFICAR  │ Sensores físicos       │
               └──────┬──────┘ Lazo cerrado           │
                      │ Confirmación / Anomalía       │
                      ▼                               │
               ┌─────────────┐                        │
               │  REGISTRAR  │                        │
               └──────┬──────┘                        │
                      │ Trazabilidad y evidencia      │
                      ▼                               │
               ┌─────────────┐                        │
               │  SUPERVISAR │                        │
               └──────┬──────┘                        │
                      │ Métricas y telemetría         │
                      ▼                               │
               ┌─────────────┐                        │
               │   MEJORAR   │────────────────────────┘
               └─────────────┘ Calibración y aprendizaje
```

> **Regla de Oro de Ingeniería:**  
> Los módulos de software (`VIGIA_Core`, `VIGIA_Vision`, `VIGIA_IoT`, `VIGIA_Automation`, `VIGIA_API`, `VIGIA_Dashboard`) **no son el fin del proyecto**, sino **habilitadores técnicos** que entran en juego únicamente cuando una capacidad física lo demanda.

---

## 2. Mapa Estructural de Capacidades y Fases

```text
03 — Roadmap de Desarrollo Orientado a Capacidades

Fase 0 — Fundaciones y Alineación
│
├── Producto
├── Arquitectura
├── Organización
├── Estándares
└── Auditoría del prototipo de referencia

        ↓

Capacidad 1 — Percibir
│
├── Capturar
├── Detectar vehículo
├── Detectar placa
├── Leer placa
└── Generar observación

        ↓

Capacidad 2 — Decidir
│
├── Mantener estado
├── Consultar autorización
├── Evaluar reglas
└── Generar decisión

        ↓

Capacidad 3 — Actuar
│
├── Generar comando
├── Comunicar con IoT
├── Accionar barrera
└── Controlar semáforo

        ↓

Capacidad 4 — Verificar
│
├── Leer sensores
├── Confirmar actuación
├── Detectar condiciones anómalas
└── Mantener lazo cerrado

        ↓

Capacidad 5 — Registrar
│
├── Registrar eventos
├── Asociar evidencia
├── Mantener trazabilidad
└── Auditar operaciones

        ↓

Capacidad 6 — Supervisar
│
├── Estado en tiempo real
├── Video
├── Alertas
└── Intervención humana

        ↓

Capacidad 7 — Mejorar
│
├── Métricas
├── Telemetría
├── Active Learning (Evolutivo)
├── Calibración
└── Optimización

        ↓

Fase 8 — Validación Integral
│
├── Integración E2E
├── Pruebas de estrés
├── Fallos
├── Casos límite
├── Seguridad
└── Despliegue Edge
```

---

## 3. Desglose Detallado de Fases y Capacidades

---

### Fase 0 — Fundaciones, Alineación y Habilitación de Ingeniería *(Fase Actual)*

* **Naturaleza:** Esta fase **NO** representa una capacidad operacional de VIGIA en el mundo físico. Constituye el conjunto de condiciones previas, acuerdos de arquitectura, estándares de calidad y análisis técnico indispensables para habilitar la construcción del sistema sin deuda técnica prematura ni sobreingeniería.
* **Propósito:** Blindar el desarrollo contra la ambigüedad, la complejidad innecesaria y el acoplamiento caótico entre software y hardware.
* **Ejes de Trabajo e Hitos:**
  * **Producto:**
    * [x] Definición formal del ciclo físico de 7 etapas.
    * [x] Definición del caso de uso rector inicial: *Caseta Inteligente de Acceso Vehicular*.
    * [x] Delimitación: VIGIA es la plataforma de automatización física; la caseta es su primera manifestación demostrable.
  * **Arquitectura:**
    * [x] Aislamiento formal de responsabilidades: Estado/Invariantes (`VIGIA_Core`), Visión (`VIGIA_Vision`), Hardware (`VIGIA_IoT`), Reglas (`VIGIA_Automation`), Servicios (`VIGIA_API`) e Interfaz (`VIGIA_Dashboard`).
    * [x] Adopción del Patrón Mediador centralizado para mantener acoplamiento lineal $O(N)$ frente a conexiones punto a punto $O(N^2)$.
    * [x] Definición de comunicación asíncrona desacoplada y persistencia mediante puertos y adaptadores.
  * **Organización:**
    * [x] Mapeo de límites de responsabilidad y ownership del equipo por módulo (`01_estructura_del_proyecto.md`).
    * [x] Reglas explícitas de código permitido y prohibido por carpeta.
  * **Estándares:**
    * [x] Estándares de desarrollo en Python, convenciones de Git, gestión de configuración desacoplada (`.env`), logging estructurado y manejo uniforme de excepciones (`04_estandares_de_desarrollo.md`).
    * [x] Filosofía de testing sin dependencia forzosa de hardware físico conectado (uso de mocks, stubs y contratos de simulación).
  * **Auditoría Técnica del Prototipo de Referencia (`VR_Semaforo/`):**
    * [ ] Inspección profunda de algoritmos de visión funcional en `VR_Semaforo/vision/` (detección YOLO, preprocesamiento OpenCV).
    * [ ] Inspección del protocolo de comunicación serial y firmware Arduino en `VR_Semaforo/arduino/`.
    * [ ] Identificación y catálogo de deuda técnica a erradicar (monolito Flask, acoplamiento directo entre video y WebSocket, hilos bloqueantes).
    * [ ] Rescate formal de lecciones aprendidas y extracción de requerimientos técnicos probados.
* **Criterio de Salida de la Fase 0:** Documentación base aprobada y congelada; reporte formal de auditoría de `VR_Semaforo/` publicado como insumo para la Capacidad 1.

---

### Capacidad 1 — Percibir

* **Definición Operacional:** Capacidad de VIGIA para observar de forma continua el flujo visual del entorno, detectar la aproximación de un vehículo, localizar su placa de circulación, leer sus caracteres ópticos y emitir una **observación estructurada**.
* **Distinción Conceptual Crítica:**  
  * La visión y la inteligencia artificial **únicamente perciben**; **NO deciden ni autorizan**.
  * El módulo de visión genera una hipótesis perceptual con un nivel de confianza asociado, nunca una orden de actuación física.
* **Flujo Interno de la Capacidad:**
  $$\text{Capturar} \longrightarrow \text{Detectar Vehículo} \longrightarrow \text{Detectar Placa} \longrightarrow \text{Leer Placa} \longrightarrow \text{Generar Observación}$$
* **Hitos de Construcción:**
  * [ ] **Capturar:** Ingesta de video eficiente y resiliente desde cámara local USB o stream de red RTSP con reconexión automática ante caídas.
  * [ ] **Detectar Vehículo:** Segmentación/clasificación del tipo de móvil en la zona de aproximación (automóvil, camioneta, camión, motocicleta).
  * [ ] **Detectar Placa:** Localización geométrica del área de la matrícula vehicular (Bounding Box del plate).
  * [ ] **Leer Placa:** Reconocimiento óptico de caracteres (OCR/LPR) con filtrado morfológico y normalización alfanumérica.
  * [ ] **Generar Observación Estructurada:** Emisión de un objeto tipado e inmutable hacia el sistema central.
* **Modelo Conceptual de Salida (Observación):**
  ```text
  Observación Perceptual:
  ├── ID Evento: obs-20260909-001
  ├── Timestamp: 2026-09-09T09:30:15.120Z
  ├── Tipo de Vehículo: Automóvil
  ├── Placa Detectada: XYZ-789
  ├── Confianza Vehículo: 0.96
  ├── Confianza Placa: 0.94
  ├── Coordenadas Bounding Box: [x1, y1, x2, y2]
  └── URI / Referencia de Fotograma: /evidencias/raw_obs-20260909-001.jpg
  ```
* **Módulos Habilitadores:** `VIGIA_Vision` (pipeline de inferencia y captura) y `VIGIA_Core` (definición formal del contrato del modelo `ObservationEvent`).

---

### Capacidad 2 — Decidir

* **Definición Operacional:** Capacidad de VIGIA para contextualizar una observación perceptual dentro del estado actual del entorno físico, evaluar las políticas y reglas de acceso vigentes, y emitir una **decisión lógica gobernada por invariantes de seguridad**.
* **Distinción Conceptual Crítica:**  
  * Una predicción de IA jamás se traduce directamente en un pulso físico.
  * `VIGIA_Core` mantiene la verdad del estado físico y custodia las restricciones de seguridad.
  * `VIGIA_Automation` evalúa las políticas de negocio (quién puede pasar, en qué horarios, con qué credencial).
  * Si el motor de reglas sugiere "abrir", pero la invariante de seguridad detecta una condición peligrosa (ej. barrera en falla o vehículo en posición insegura), la decisión se bloquea.
* **Flujo Interno de la Capacidad:**
  $$\text{Observación} \longrightarrow \text{Estado del Entorno} \longrightarrow \text{Evaluación de Reglas} \longrightarrow \text{Filtro de Invariantes} \longrightarrow \text{Decisión}$$
* **Hitos de Construcción:**
  * [ ] **Mantener Estado:** Máquina de estados del carril vehicular (ej. `VACÍO`, `VEHÍCULO_EN_APROXIMACIÓN`, `EVALUANDO_ACCESO`, `PASO_AUTORIZADO`, `CRUCE_EN_CURSO`, `ANOMALÍA`).
  * [ ] **Consultar Autorización:** Repositorio local de matrículas vehiculares permitidas, rangos horarios de vigencia y vigencia de membresía/permiso.
  * [ ] **Evaluar Reglas:** Motor determinista de políticas (`SI placa_en_lista_blanca Y horario_valido ENTONCES autorizar; SI_NO denegar`).
  * [ ] **Generar Decisión:** Producción del evento de resolución de acceso (`ACCESO_CONCEDIDO`, `ACCESO_DENEGADO`, `REQUIERE_REGISTRO_MANUAL`) con su justificación explícita.
* **Módulos Habilitadores:** `VIGIA_Core` (gestor de estado de sesión e invariantes de seguridad) y `VIGIA_Automation` (motor de reglas de acceso y tablas de políticas).

---

### Capacidad 3 — Actuar

* **Definición Operacional:** Capacidad de VIGIA para transformar una decisión lógica autorizada en un comando estructurado, transmitirlo por un canal determinista hacia el controlador de hardware y provocar una **acción motriz o lumínica en el mundo físico**.
* **Distinción Conceptual Crítica:**  
  * La decisión lógica no toca el hardware directamente; se traduce en un **comando formal tipado** sujeto a validación previa.
  * Los protocolos de transmisión deben contar con control de flujo, verificación de suma de comprobación (checksum/CRC) y tiempos límite estrictos (timeouts).
* **Flujo Interno de la Capacidad:**
  $$\text{Decisión Lógica} \longrightarrow \text{Generación de Comando} \longrightarrow \text{Comunicación IoT} \longrightarrow \text{Actuador Físico} \longrightarrow \text{Acción Motriz}$$
* **Hitos de Construcción:**
  * [ ] **Generar Comando:** Creación del paquete de comando con identificador correlativo (`CMD_OPEN_BARRIER`, `CMD_SET_SEMAPHORE_GREEN`, `CMD_CLOSE_BARRIER`).
  * [ ] **Comunicar con IoT:** Driver de transporte serial/UART o MQTT con reintentos controlados y manejo de pérdida de enlace.
  * [ ] **Accionar Barrera:** Recepción del comando en el microcontrolador (Arduino / ESP32) y generación de la señal PWM correspondiente para desplazar el servomotor / relevador del mástil.
  * [ ] **Controlar Semáforo:** Cambio coordinado de estados lumínicos (Rojo $\to$ Verde $\to$ Amarillo) sincronizados con la maniobra de la barrera.
* **Módulos Habilitadores:** `VIGIA_Core` (emisión del comando autorizado) y `VIGIA_IoT` (driver de puerto, firmware embebido y circuitos de potencia).

---

### Capacidad 4 — Verificar

* **Definición Operacional:** Capacidad de VIGIA para cerrar el lazo de control, supervisando mediante sensores independientes que la acción física comandada realmente ocurrió en el entorno real y que el proceso concluyó de manera segura.
* **Principio de Lazo Cerrado (*Closed-Loop Control*):**  
  * **VIGIA nunca asume que una orden se ejecutó simplemente porque se envió el comando por el puerto.**
  * Una acción física sólo se considera completada cuando la instrumentación sensorial confirma el cambio de estado del mundo.
* **Flujo Interno de la Capacidad:**
  $$\text{Comando} \longrightarrow \text{Actuación} \longrightarrow \text{Lectura Sensorial} \longrightarrow \text{Estado Físico Real} \longrightarrow \text{Verificación / Anomalía}$$
* **Hitos de Construcción:**
  * [ ] **Leer Sensores:** Ingesta de señales binarias o analógicas de instrumentación en sitio (final de carrera de barrera levantada, sensor ultrasónico de presencia bajo mástil, detector de lazo magnético/fotocelda de cruce completado).
  * [ ] **Confirmar Actuación (ACK Físico):** Verificación de que el mástil alcanzó el ángulo de apertura dentro de una ventana temporal máxima ($t < \tau_{\max}$).
  * [ ] **Detectar Condiciones Anómalas:** Identificación inmediata de fallos operacionales:
    * *Mástil atorado o movimiento incompleto.*
    * *Timeout de respuesta del microcontrolador.*
    * *Presencia de obstáculo debajo del mástil durante comando de cierre (cierre abortado por seguridad).*
  * [ ] **Mantener Lazo Cerrado:** Transición formal del estado global del sistema de acuerdo con la confirmación física verificada.
* **Módulos Habilitadores:** `VIGIA_IoT` (firmware con lectura de interrupciones de sensores y telemetría de estado) y `VIGIA_Core` (árbitro de reconciliación de estado físico vs. estado deseado).

---

### Capacidad 5 — Registrar

* **Definición Operacional:** Capacidad de VIGIA para consolidar la memoria operacional inmutable del sistema, almacenando cronológicamente cada evento, su contexto perceptual, la regla aplicada, las confirmaciones de hardware y la evidencia visual.
* **Propósito Operacional:** Garantizar auditoría forense, trazabilidad operativa estricta y cumplimiento de acuerdos de nivel de servicio (SLA).
* **Flujo Interno de la Capacidad:**
  $$\text{Observación} \longrightarrow \text{Decisión} \longrightarrow \text{Acción} \longrightarrow \text{Verificación Sensorial} \longrightarrow \text{Registro Auditable}$$
* **Hitos de Construcción:**
  * [ ] **Registrar Eventos:** Persistencia estructurada en base de datos local relacional y liviana (SQLite) de toda la secuencia del ciclo con timestamps sincronizados de alta precisión.
  * [ ] **Asociar Evidencia:** Vinculación directa e inmutable del fotograma de entrada, placa recortada y telemetría del sensor con el identificador único del cruce.
  * [ ] **Mantener Trazabilidad:** Almacenamiento del motivo exacto de la decisión tomada (ej. *Permiso ID 402 concedido por lista blanca vigente* o *Denegado por matrícula desconocida*).
  * [ ] **Auditar Operaciones:** Generación de bitácora protegida contra manipulaciones que permita reconstruir segundo a segundo cualquier incidente físico en el acceso.
* **Módulos Habilitadores:** `VIGIA_Core` (puerto de persistencia y servicio de auditoría) y base de datos local embebida.

---

### Capacidad 6 — Supervisar

* **Definición Operacional:** Capacidad de VIGIA para otorgar visibilidad operativa en tiempo real a operadores humanos, emitir alarmas ante discrepancias físicas y permitir la intervención manual segura.
* **Invariante de Seguridad en Intervención Humana:**  
  * La intervención manual de un operador (ej. pulsar "Apertura Forzada" desde el tablero) **NO bypasséa las invariantes de seguridad física**.
  * La orden humana se canaliza a través de `VIGIA_Core`, el cual valida que la acción no comprometa la integridad física de personas o vehículos antes de generar el comando.
* **Hitos de Construcción:**
  * [ ] **Estado en Tiempo Real:** Exposición de variables operacionales vivas (estado del carril, barrera, semáforo, última matrícula leída) mediante WebSockets o sondeo liviano.
  * [ ] **Video:** Streaming de video en vivo de baja latencia con renderizado de recuadros de detección y telemetría sobreimpresa.
  * [ ] **Alertas:** Emisión inmediata de notificaciones audibles o visuales ante anomalías (vehículo detenido indebidamente, fallo de sensor, discrepancia de verificación).
  * [ ] **Intervención Humana:** Panel de control con comandos de supervisión autorizados (abrir, cerrar, poner en modo manual de contingencia, silenciar alarma).
* **Módulos Habilitadores:** `VIGIA_API` (capa de servicios HTTP/WebSockets) y `VIGIA_Dashboard` (interfaz visual web responsiva para monitoreo).

---

### Capacidad 7 — Mejorar

* **Definición Operacional:** Capacidad de VIGIA para aprovechar la evidencia operacional acumulada y la telemetría histórica con el fin de calibrar umbrales, afinar tiempos de ciclo y optimizar la precisión de los modelos perceptuales.
* **Enfoque Pragmático y Evolutivo:**  
  * Las capacidades de reentrenamiento continuo automatizado (*Active Learning*) **NO son obligatorias para el lanzamiento de la primera versión funcional (v1)**.
  * Se conciben como una **capacidad evolutiva posterior**, partiendo en una primera instancia de la recolección pasiva y curada de datos dudosos.
* **Hitos de Construcción:**
  * [ ] **Métricas:** Cálculo y reporte de indicadores clave de rendimiento (KPIs): tasa de reconocimiento exitoso de matrículas, tiempo promedio de ciclo por vehículo, tasa de rechazo de accesos.
  * [ ] **Telemetría:** Monitoreo de latencia de inferencia de visión, latencia de respuesta serial del microcontrolador y tasa de errores de verificación.
  * [ ] **Active Learning (Capacidad Evolutiva):** Filtrado automático y archivo de capturas visuales donde el modelo de OCR tuvo un nivel de confianza limítrofe o discordante para retroalimentar el dataset de entrenamiento.
  * [ ] **Calibración y Optimización:** Mecanismos sencillos para calibrar los tiempos de espera de las reglas de barrera y los umbrales de sensibilidad de detección vehicular según las condiciones de iluminación del sitio.
* **Módulos Habilitadores:** `VIGIA_Vision` (colector de muestras dudosas), `VIGIA_Automation` (módulo de calibración de temporizadores) y telemetría de `VIGIA_Core`.

---

### Fase 8 — Validación Integral y Despliegue en Entorno Real

* **Definición Operacional:** Demostración del ciclo completo de automatización física de principio a fin (*End-to-End*) funcionando de forma ininterrumpida y robusta bajo condiciones ambientales reales o en maqueta física de escala completa.
* **Ciclo Integral a Demostrar:**
  $$\text{Aproximación} \to \text{Percepción} \to \text{Decisión} \to \text{Actuación} \to \text{Verificación} \to \text{Cruce} \to \text{Cierre} \to \text{Registro}$$
* **Hitos de Validación:**
  * [ ] **Integración E2E:** Prueba continua sin fallos de 100 ciclos continuos de aproximación vehicular con vehículos reales o a escala controlada.
  * [ ] **Pruebas de Estrés:** Comportamiento del sistema ante flujo vehicular denso y aproximaciones consecutivas con espacio mínimo entre defensas.
  * [ ] **Matriz de Casos Límite y Manejo de Fallos:**
    * *Vehículo sin placa frontal:* Detección del tipo de vehículo, emisión de alarma, registro de foto de evidencia y denegación segura.
    * *Placa ilegible o manchada:* Manejo de baja confianza, solicitud de asistencia en tablero y desvío a registro manual.
    * *Vehículo no registrado / desconocido:* Denegación expedita, mantenimiento de barrera abajo y semáforo en rojo.
    * *Vehículo autorizado:* Apertura fluida en menos de 1.5 segundos tras alcanzar la zona de lectura.
    * *Vehículo que se detiene antes de cruzar:* Espera por timeout configurado, advertencia preventiva y retención de estado seguro.
    * *Vehículo que retrocede y abandona el carril:* Detección de despeje sin cruce, anulación de la autorización de paso y retorno al estado `VACÍO`.
    * *Pérdida de cámara de video:* Detección inmediata de stream congelado/desconectado, notificación al Dashboard y paso a modo seguro.
    * *Pérdida de comunicación serial con IoT:* Conmutación a estado de falla segura, bloqueo de comandos automáticos e indicación luminosa.
    * *Fallo de sensor físico:* Reporte de timeout de verificación y activación de alerta de mantenimiento.
    * *Actuador que no responde:* Detección por ausencia de cambio en sensor de fin de carrera tras el comando.
    * *Estado físico inesperado (ej. barrera forzada manualmente hacia arriba):* Detección por sensor de carrera fuera de comando y disparo de alarma de intrusión.
    * *Reinicio abrupto del sistema (corte de energía):* Recuperación limpia sin estados indeterminados, lectura del estado físico real al bootear y restauración segura.
  * [ ] **Despliegue Edge:** Empaquetado ligero y puesta en marcha optimizada para hardware de borde (Mini PC, Raspberry Pi o Nvidia Jetson) con consumo controlado de CPU y memoria.

---

## 4. Regla de Avance del Roadmap y Criterio de Finalización

Para evitar la ilusión de progreso fundamentada en código incompleto o no probado, VIGIA adopta las siguientes reglas inviolables:

> ### Regla de Avance Formal
> **Una capacidad NO se considera completada por la sola existencia de código en el repositorio, sino por la demostración reproducible de dicha capacidad funcionando en el entorno objetivo.**
>
> **Ninguna fase o capacidad se dará por cerrada sin contar con criterios de aceptación verificados, pruebas automatizadas correspondientes y evidencia tangible documentada.**

### Formas de Evidencia Aceptadas:
1. **Resultados de Pruebas Automatizadas:** Suites de pruebas unitarias y de integración pasando al 100% en el entorno de pruebas (`tests/`).
2. **Logs Estructurados:** Trazas de ejecución limpias que demuestren el flujo sin excepciones no controladas.
3. **Fotogramas y Capturas:** Evidencia de detecciones y lecturas de OCR con coordenadas y métricas de confianza.
4. **Video de Demostración:** Grabación reproducible del comportamiento físico en maqueta o banco de trabajo.
5. **Telemetría y Métricas:** Mediciones empíricas de tiempos de respuesta, latencias y consumo de recursos.
6. **Reporte de Validación E2E:** Bitácora firmada de ejecución exitosa de la matriz de casos límite.

---

## 5. Relación entre el Roadmap Estratégico y la Ejecución de Ingeniería

Este documento define **QUÉ capacidades se construirán y en qué ORDEN secuencial de dependencias**. No debe confundirse con un backlog de tickets diarios de desarrollo.

La traducción desde este roadmap estratégico hacia el trabajo diario de los desarrolladores sigue esta cadena de trazabilidad:

```text
Capacidad (Roadmap Estratégico)
    │
    ▼
Épica (Gran bloque de funcionalidad técnica)
    │
    ▼
Feature (Característica específica orientada a usuario/operador)
    │
    ▼
Requerimiento (Especificación funcional o técnica no ambigua)
    │
    ▼
Tarea de Ingeniería (Issue / PR de código o infraestructura)
    │
    ▼
Prueba (Unit, Integration o Contract Test)
    │
    ▼
Evidencia Tangible (Criterio de Aceptación / Definition of Done)
```

Los documentos y artefactos técnicos posteriores se encargarán de desglosar los requerimientos detallados, los esquemas de bases de datos, los contratos de interfaces y las definiciones de terminado (*Definition of Done*) para cada tarea individual.

---

## 6. Estado de Decisiones Arquitectónicas

En observancia estricta del principio de mínima complejidad, se formaliza el estatus actual de las decisiones del proyecto:

| Decisión / Componente | Estatus Oficial | Justificación Técnica |
| :--- | :--- | :--- |
| **Monolito Modular en Python** | `Oficial y Aprobada` | Un solo proceso o procesos locales limpios; suficiente para las necesidades de latencia en el borde sin sobrecarga de microservicios. |
| **Persistencia Local Relacional** | `Oficial y Aprobada (SQLite inicial)` | Ligera, confiable, sin dependencias externas complejas para despliegue edge autónomo. |
| **Microcontrolador para Control Físico** | `Oficial y Aprobada (Arduino / ESP32)` | Manejo de señales en tiempo real estricto, PWM y lectura de sensores. |
| **Protocolo de Transporte Serial/UART** | `Oficial y Aprobada` | Conexión cableada simple y robusta entre el procesador principal y el microcontrolador. |
| **Motor de Visión Basado en YOLO** | `Oficial y Aprobada (vía herencia de prototipo)` | Desempeño probado en inferencia en tiempo real en `VR_Semaforo`. |
| **Mecanismo de Reentrenamiento en la Nube** | `Decisión Futura / No v1` | No necesario para el MVP ni para las primeras capacidades funcionales en el sitio. |
| **Protocolos de Red Complejos (gRPC, Kafka)** | `Descartados por Sobreingeniería` | Injustificados para un sistema de acceso vehicular autónomo en el borde. |
| **Elección de Motor OCR Específico** | `Pendiente de Definición en Capacidad 1` | Se resolverá durante las pruebas de la Capacidad 1 tras evaluar velocidad y consumo en hardware edge. |
| **Esquema de Señalización de Paso** | `Pendiente de Definición en Capacidad 3` | Definición de si se utiliza servo estándar de 180°, motor a pasos o relé para barrera industrial real. |
