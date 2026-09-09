# VIGIA Vision Systems

## 01 — Estructura del Proyecto, Responsabilidades y Ownership

**Estado:** Activo / Fase 0  
**Versión:** 1.2 (Alineación con el Producto Físico)  
**Pregunta Central:** *¿Quién es responsable de qué dentro del ciclo operativo?*  
**Propósito:** Definir la estructura completa del repositorio, la responsabilidad técnica unívoca de cada directorio al servicio del ciclo físico, las delimitaciones de código y el mapa de ownership del equipo.

---

# 1. Propósito del Documento

Este documento establece la base arquitectónica y de organización de trabajo para **VIGIA Vision Systems**. Su objetivo principal es asegurar una separación limpia de responsabilidades en el código, evitando acoplamientos innecesarios, burocracias de software artificiales y dispersión de esfuerzos.

> **Principio Rector:**  
> VIGIA observa un entorno físico, interpreta lo que ocurre, decide qué debe suceder, actúa sobre el entorno, verifica el resultado y registra la experiencia para supervisión y mejora continua.  
> Los módulos existen únicamente para articular las fases de este ciclo en el mundo real.

---

# 2. Estructura Completa del Repositorio

El repositorio se organiza jerárquicamente de la siguiente manera:

```text
VIGIA_Vision_Systems/
│
├── README.md                          # Visión general, ciclo fundamental y caso rector (Caseta)
│
├── Docs/                              # Documentación técnica, conceptual y de estándares
│   ├── README.md                      # Índice maestro y progresión conceptual
│   ├── 01_estructura_del_proyecto.md  # [Este documento] Estructura, fronteras y ownership
│   ├── 02_arquitectura_del_sistema.md # El ciclo físico, flujo de control y componentes
│   ├── 03_roadmap.md                  # Hoja de ruta orientada a capacidades del producto
│   └── 04_estandares_de_desarrollo.md # Guías de código simple, Git, testing y disciplina técnica
│
├── VR_Semaforo/                       # [Proyecto de Referencia / PoC funcional] (Intacto)
│   ├── app.py                         # Prototipo previo funcional de semáforo inteligente
│   ├── arduino/                       # Firmware original de referencia
│   └── vision/                        # Algoritmos de visión iniciales
│
├── VIGIA_Core/                        # Estado del entorno, coordinación y seguridad
│   └── README.md
│
├── VIGIA_Vision/                      # Captura de video e interpretación visual (vehículos, placas)
│   └── README.md
│
├── VIGIA_IoT/                         # Enlace físico bidireccional (sensores, barreras, verificación)
│   └── README.md
│
├── VIGIA_Automation/                  # Inteligencia de decisión: reglas y políticas operativas
│   └── README.md
│
├── VIGIA_API/                         # Servicios de consulta, configuración y telemetría externa
│   └── README.md
│
├── VIGIA_Dashboard/                   # Panel visual de supervisión, video y control humano
│   └── README.md
│
├── tests/                             # Pruebas automatizadas del ciclo físico con mocks
│   └── README.md
│
├── scripts/                           # Herramientas auxiliares de verificación y mantenimiento
│   └── README.md
│
└── .gitignore                         # Políticas de exclusión limpias para control de versiones
```

---

# 3. Responsabilidad Técnica por Directorio al Servicio del Ciclo

A continuación se detalla la función de cada componente dentro del ciclo físico de VIGIA, especificando qué código **SÍ** pertenece y qué código **NO** debe colocarse.

---

### 3.1 `VR_Semaforo/` (Proyecto de Referencia / PoC Experimental)

* **Responsabilidad:** Servir exclusivamente como punto de referencia experimental y demostrador de concepto previo. Representa los primeros aprendizajes en detección visual (YOLO), conteo vehicular y control de hardware vía Arduino.
* **Código que pertenece:**
  * El código del prototipo original tal cual existe.
* **Código que NO debe colocarse:**
  * Nuevas implementaciones de VIGIA ni refactorizaciones del nuevo sistema.
* **Regla de oro:** **PERMANECE INTACTO.** No se modifica en esta fase; será auditado en la Fase 1.

---

### 3.2 `VIGIA_Core/`

* **Rol en el Ciclo:** **Estado del Entorno, Seguridad y Coordinación.**
* **Responsabilidad:** Es el núcleo que mantiene la representación del estado actual del entorno físico (ej. en la caseta: vehículo presente, placa detectada, estado de la barrera, autorización vigente) y garantiza que cualquier decisión cumpla con restricciones de seguridad antes de autorizar su ejecución física.
* **Código que pertenece:**
  * **Gestor de Estado del Entorno (`StateManager`, `SystemState`):** Memoria de lo que ocurre en el espacio físico.
  * **Reglas Invariantes de Seguridad (`SafetyEnforcer`):** Condiciones físicas no negociables (ej. no bajar la barrera si el sensor de presencia detecta un auto cruzando; no habilitar movimientos conflictivos).
  * **Coordinación del Ciclo:** Enrutamiento directo entre la observación entrante, la evaluación de reglas y la orden de actuación.
  * **Interfaces de Persistencia y Auditoría (`IRepository`, `IAuditLogger`):** Contratos abstractos mínimos para guardar eventos y telemetría.
  * **Gestor de Configuración Central:** Parámetros de operación, tiempos y credenciales.
* **Código que NO debe colocarse:**
  * Motores de base de datos concretos (PostgreSQL, SQLite; estos son adaptadores externos).
  * Inferencia de IA (YOLO, OpenCV, PyTorch).
  * Drivers seriales de hardware (`pyserial`, código Arduino).
  * Rutas HTTP, frameworks web o interfaces gráficas.

---

### 3.3 `VIGIA_Vision/`

* **Rol en el Ciclo:** **Observar $\to$ Interpretar.**
* **Responsabilidad:** Capturar cuadros de video e interpretar su contenido semántico mediante visión por computadora e IA (detectar la presencia de un vehículo, leer los caracteres de una placa vehicular, clasificar el tipo de objeto).
* **Código que pertenece:**
  * Abstracciones de captura de video (webcams, streams RTSP, archivos de prueba).
  * Preprocesamiento de imagen (recorte de área de placa, normalización, ajuste de contraste).
  * Inferencia de modelos de visión (YOLO, OCR de placas, clasificadores).
  * Emisión de observaciones estructuradas (ej. `Vehículo detectado en carril 1 con placa 'XYZ-789' y confianza 0.94`).
* **Código que NO debe colocarse:**
  * Comunicación directa con servomotores o barreras físicas.
  * Decisiones sobre si la placa tiene permiso para entrar (eso es de Reglas/Core).
  * Bases de datos o interfaces web.

---

### 3.4 `VIGIA_IoT/`

* **Rol en el Ciclo:** **Observar (Sensores) $\to$ Actuar (Dispositivos) $\to$ Verificar (Confirmación Física).**
* **Responsabilidad:** Ser la interfaz física de VIGIA. Lee sensores del mundo real, envía órdenes a los actuadores físicos y lee sensores de confirmación para verificar si la acción física realmente ocurrió.
* **Código que pertenece:**
  * **Lectura sensorial:** Sensores de masa metálica, fotoceldas de seguridad, botones de timbre.
  * **Accionamiento físico:** Comandos para servomotores de barrera, relevadores, semáforos LED verde/rojo.
  * **Verificación física:** Lectura de sensores de final de carrera (confirmar si la barrera realmente subió) y sensores de despeje (confirmar si el vehículo ya cruzó).
  * **Adaptadores de comunicación:** Control robusto de puertos Serial (USB), WiFi/MQTT (ESP32), GPIO.
  * **Firmware:** Código de microcontroladores (`.ino` para Arduino, C++ para ESP32).
* **Código que NO debe colocarse:**
  * Inferencia de visión o procesamiento de imágenes.
  * Lógica de autorización o reglas de negocio de la caseta.

---

### 3.5 `VIGIA_Automation/`

* **Rol en el Ciclo:** **Decidir.**
* **Responsabilidad:** Evaluar las reglas y políticas del sistema ante la información interpretada para decidir qué debe suceder.
* **Código que pertenece:**
  * Motor de reglas deterministas (ej. en la caseta: *SI placa está en lista autorizada Y horario es válido $\to$ AUTORIZAR ACCESO; SI NO $\to$ DENEGAR Y REGISTRAR VISITA*).
  * Políticas operativas (modo automático, modo contingencia, modo libre, horarios pico).
  * Lógica de temporización (tiempo de espera antes de ordenar cierre de barrera tras el cruce).
* **Código que NO debe colocarse:**
  * Control a nivel de byte con pines de hardware (la orden pasa a Core/IoT).
  * Almacenamiento maestro de la base de datos de usuarios.
  * Procesamiento de frames de video.

---

### 3.6 `VIGIA_API/`

* **Rol en el Ciclo:** **Supervisión, Consulta e Integración Externa.**
* **Responsabilidad:** Exponer endpoints para que sistemas externos, aplicaciones móviles o el Dashboard puedan consultar el estado del entorno, recibir notificaciones en tiempo real y enviar comandos de control manual supervisados.
* **Código que pertenece:**
  * Endpoints REST (consultar historial de accesos, vehículos registrados, estado de barrera).
  * Canales en tiempo real (WebSockets / SSE) para telemetría visual y de sensores.
  * Autenticación y autorización para operadores.
* **Código que NO debe colocarse:**
  * Lógica de negocio crítica (debe delegarse al Core).
  * Código de interfaz gráfica SPA.

---

### 3.7 `VIGIA_Dashboard/`

* **Rol en el Ciclo:** **Visualización y Mando Operativo Humano.**
* **Responsabilidad:** Proporcionar al guardia u operador de la caseta/instalación una interfaz visual clara para supervisar el acceso en vivo, ver el video con la placa detectada y pulsar botones de apertura manual ante contingencias.
* **Código que pertenece:**
  * Interfaz visual reactiva (vistas de cámaras, tabla de últimos accesos, indicadores de barrera).
  * Controles de mando manual supervisado (botón de apertura de emergencia).
* **Código que NO debe colocarse:**
  * Conexiones directas a hardware sin pasar por la API/Core.
  * Modelos de inferencia pesados en el cliente web.

---

### 3.8 `tests/` y `scripts/`

* **`tests/`:** Pruebas automatizadas de cada etapa del ciclo (simulando cámaras mediante videos grabados y simulando actuadores/sensores con mocks), garantizando que todo el ciclo pueda verificarse sin hardware conectado.
* **`scripts/`:** Utilidades de desarrollo, verificación de dependencias y herramientas de calibración de cámaras.

---

# 4. Flujo de Información en el Caso Rector: Caseta Vehicular

La siguiente secuencia describe cómo colaboran los módulos para cumplir el ciclo de la caseta de acceso:

```text
 1. APROXIMACIÓN           2. IDENTIFICACIÓN
   Sensor detecta auto       Cámara captura y procesa
         │                         │
         ▼                         ▼
   ┌───────────┐             ┌──────────────┐
   │ VIGIA_IoT │             │ VIGIA_Vision │
   └─────┬─────┘             └──────┬───────┘
         │                          │
         │ "Auto en entrada"        │ "Placa: ABC-123"
         └────────────┬─────────────┘
                      ▼
             ┌─────────────────┐
             │   VIGIA_Core    │ ──> Actualiza Estado: Auto en espera
             └────────┬────────┘
                      │ Contexto
                      ▼
           ┌────────────────────┐
           │  VIGIA_Automation  │ ──> Evalúa Reglas: ¿Placa ABC-123 autorizada?
           └──────────┬─────────┘     Decisión: SÍ, ABRIR BARRERA
                      │
                      ▼
             ┌─────────────────┐
             │   VIGIA_Core    │ ──> Valida Seguridad: ¿Barrera libre para subir?
             └────────┬────────┘     Ordena acción
                      │
                      ▼
               ┌─────────────┐
               │  VIGIA_IoT  │ ──> 3. ACTÚA: Pulso a servomotor de barrera
               └──────┬──────┘
                      │
                      ▼ 4. VERIFICA: Sensor de tope confirma "Barrera arriba"
               ┌─────────────┐
               │   VIGIA_Core│ ──> 5. REGISTRA: Acceso exitoso concedido
               └──────┬──────┘
                      │
                      ▼ 6. MEJORA: Si la placa tuvo confianza baja,
                                    archiva imagen para reentrenamiento
```

---

# 5. Mapeo de Roles y Ownership del Equipo

Para garantizar la correcta ejecución del proyecto y evitar colisiones, cada dominio cuenta con responsables técnicos asignados, coordinados bajo el marco formal de trabajo (*ver detalle en [05 — Marco de Planificación y Ejecución](file:///home/yair/VIGIA_Vision_Systems/Docs/05_marco_de_planificacion_y_ejecucion.md)*):

| Integrante | Rol Oficial | Workstream / Módulos bajo su Ownership |
| :--- | :--- | :--- |
| **Yahir** | Project Manager / CIO | **Workstream A** — Gobierno Scrum, Contratos, Planificación y Coordinación General |
| **Josué** | Product Owner / System Architect | **Workstream A** — Product Backlog, Arquitectura Base, `VIGIA_Core/`, Integración del Ciclo |
| **Ernesto** | CTO / Hardware & Embedded / IoT | **Workstream E** — `VIGIA_IoT/`, Microcontroladores (Arduino/ESP32), Sensores, Actuadores y Maqueta |
| **Stephanie** | AI / Computer Vision Engineer / Data Engineer | **Workstream B & G** — `VIGIA_Vision/`, Pipeline Perceptual, LPR/OCR, Datasets y Telemetría |
| **Julio + Ever** | Computer Vision Specialists | **Workstream B** — Modelos de Detección, Benchmark de OCR, Auditoría de `VR_Semaforo/vision/` |
| **Vianey** | Backend Engineer / DevOps Engineer | **Workstream C & F** — `VIGIA_API/`, Servicios de Persistencia (SQLite), Entorno de CI/DevOps |
| **Naty** | Frontend Engineer / Business Analyst | **Workstream D** — Requisitos de Usuario, UX/UI, Wireframes, Arquitectura de `VIGIA_Dashboard/` |
| **Jonathan** | Dashboard & Web Developer | **Workstream D & I** — Implementación de `VIGIA_Dashboard/`, Interfaces Web, Sitio Institucional VIGIA |
| **Ale** | Marketing & Market Research | **Workstream H** — Investigación de Mercado, Validación de Clientes, Análisis de Competencia |

