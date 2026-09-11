# VIGIA Vision Systems

**Plataforma de automatización inteligente orientada a entornos físicos.**

> *VIGIA observa un entorno físico mediante sensores y visión computacional, interpreta lo que ocurre, toma decisiones controladas y ejecuta acciones mediante dispositivos físicos. El resultado de las acciones se verifica y registra para supervisión y mejora continua.*
>
> *La arquitectura y las tecnologías utilizadas deben mantenerse al mínimo necesario para cumplir este ciclo y resolver necesidades reales del sistema.*

---

## 1. ¿Qué es VIGIA Vision Systems?

**VIGIA Vision Systems** es una plataforma de software y hardware diseñada para gobernar, supervisar y automatizar entornos del mundo real. 

Su función esencial no es desplegar tecnologías complejas por moda, sino cumplir un ciclo continuo y coherente:

$$\text{ENTORNO} \longrightarrow \text{OBSERVAR} \longrightarrow \text{INTERPRETAR} \longrightarrow \text{DECIDIR} \longrightarrow \text{ACTUAR} \longrightarrow \text{VERIFICAR} \longrightarrow \text{REGISTRAR} \longrightarrow \text{MEJORAR} \circlearrowleft$$

```text
             ┌─────────────────────┐
             │   ENTORNO FÍSICO    │
             │ Vehículos, personas,│
             │ accesos, objetos... │
             └──────────┬──────────┘
                        │
                        ▼
                 ┌─────────────┐
                 │  OBSERVAR   │  Cámaras y Sensores
                 └──────┬──────┘
                        │
                        ▼
                 ┌─────────────┐
                 │ INTERPRETAR │  ¿Qué y quién está ahí? (Placa, tipo, estado)
                 └──────┬──────┘
                        │
                        ▼
                 ┌─────────────┐
                 │   DECIDIR   │  ¿Qué debe ocurrir según las reglas?
                 └──────┬──────┘
                        │
                        ▼
                 ┌─────────────┐
                 │   ACTUAR    │  Dispositivos físicos (Barrera, semáforo, relé)
                 └──────┬──────┘
                        │
                        ▼
                 ┌─────────────┐
                 │  VERIFICAR  │  ¿La acción física realmente ocurrió?
                 └──────┬──────┘
                        │
                        ▼
                 ┌─────────────┐
                 │  REGISTRAR  │  Auditoría, telemetría y trazabilidad
                 └──────┬──────┘
                        │
                        └──────────► MEJORAR (Calibración, datos dudosos, reentrenamiento)
```

---

## 2. Caso de Uso Rector: La Caseta Inteligente de Acceso Vehicular

Para entender VIGIA en la práctica, el proyecto adopta como **caso de uso rector inicial** la automatización de una caseta de acceso vehicular:

```text
                    ENTORNO FÍSICO
                          │
                          ▼
                    🚗 Vehículo
                          │
                          ▼
                       OBSERVAR
                    Cámara + sensores
                          │
                          ▼
                      INTERPRETAR
             Vehículo + placa + contexto
                          │
                          ▼
                       DECIDIR
                ¿Tiene autorización?
                    │          │
                   NO         SÍ
                    │          │
                    ▼          ▼
                  Denegar    Abrir
                               │
                               ▼
                            ACTUAR
                         Barrera / servo
                               │
                               ▼
                          VERIFICAR
                    ¿La barrera realmente
                           subió?
                    ¿El vehículo cruzó?
                               │
                               ▼
                          REGISTRAR
                     Acceso + resultado
                               │
                               ▼
                           MEJORAR
                Datos dudosos / métricas /
                    calibración / ML
```

### VIGIA no es la caseta
La caseta vehicular es la demostración inicial del sistema. VIGIA es la **capacidad general de automatizar el entorno físico**, aplicable en el futuro a:
* Casetas de acceso y estacionamientos inteligentes.
* Cruces viales y semaforización adaptativa (demostrado en el prototipo de referencia `VR_Semaforo`).
* Áreas restringidas y control de accesos peatonales.
* Supervisión de procesos en entornos industriales.

---

## 3. Las Tecnologías como Herramientas (No como Fin)

En VIGIA, las tecnologías aparecen únicamente cuando resuelven una necesidad real dentro del ciclo:

| Herramienta | Necesidad Real en VIGIA | En qué parte del ciclo participa |
| :--- | :--- | :--- |
| **Visión Computacional** | Detectar vehículos, leer placas y reconocer situaciones sin intervención humana. | **Observar e Interpretar** |
| **IoT / Hardware** | Leer sensores físicos (presencia, lazos magnéticos) y comandar barreras, semáforos o relés. | **Observar, Actuar y Verificar** |
| **Machine Learning / IA** | Interpretar información visual compleja o aprender de detecciones dudosas registradas. | **Interpretar y Mejorar** |
| **Automatización / Reglas** | Evaluar permisos de acceso, condiciones seguras y tiempos de espera de forma determinista. | **Decidir** |
| **Base de Datos** | Recordar vehículos registrados, placas autorizadas, historial de accesos y configuración. | **Decidir y Registrar** |
| **Business Intelligence (BI)**| Analizar flujos a lo largo del tiempo: horas pico, tasas de denegación, tiempos de cruce. | **Registrar y Mejorar** |
| **Blockchain** *(Condicional)* | Solo si un requisito exige trazabilidad inmutable y auditoría descentralizada estricta. | **Registrar** |

> **Principio Rector:**  
> `IDEA DE VIGIA` $\to$ `NECESIDAD REAL` $\to$ `¿QUÉ DEBE HACER EL SISTEMA?` $\to$ `COMPONENTE MÍNIMO` $\to$ `IMPLEMENTACIÓN SIMPLE`.  
> *"VIGIA debe crecer en capacidad, no en complejidad gratuita."*

---

## 4. Producto $\neq$ Implementación

Es fundamental mantener esta distinción en todo el repositorio:
* Si el bus de eventos en memoria se reemplaza por llamadas directas: **VIGIA sigue siendo VIGIA.**
* Si Arduino se cambia por ESP32 o una Raspberry Pi: **VIGIA sigue siendo VIGIA.**
* Si el modelo de visión YOLO se cambia por otro detector: **VIGIA sigue siendo VIGIA.**
* Si PostgreSQL se cambia por SQLite para simplificar el MVP: **VIGIA sigue siendo VIGIA.**

La arquitectura y el software son **medios**. El producto y su ciclo físico son el **objetivo**.

---

## 5. Estructura General del Repositorio

La organización de carpetas responde a la necesidad de mantener responsabilidades claras y componentes sencillos:

```text
VIGIA_Vision_Systems/
│
├── README.md                      # [Este documento] Identidad, ciclo fundamental y caso rector
│
├── Docs/                          # Documentación técnica, metodológica y de requisitos (01 al 09)
│   ├── README.md                  # Índice maestro y mapa conceptual de lectura
│   ├── 01_estructura_del_proyecto.md # ¿Quién es responsable de qué? (Módulos y ownership)
│   ├── 02_arquitectura_del_sistema.md # ¿Cómo se relacionan los módulos para cumplir el ciclo?
│   ├── 03_roadmap.md              # ¿En qué orden construiremos las capacidades de VIGIA?
│   ├── 04_estandares_de_desarrollo.md # ¿Cómo debe escribirse y mantenerse el código simple?
│   ├── 05_marco_de_planificacion_y_ejecucion.md # Marco Scrum paralelo y Workstreams
│   ├── 06_propuesta_del_proyecto.md # Visión ejecutiva y caso rector
│   ├── 07_cronograma_maestro.md   # Plan temporal sincronizado (Sep-Dic 2026)
│   ├── 08_matriz_de_riesgos.md    # Matriz consolidada de riesgos y mitigaciones
│   ├── 09_especificacion_de_requisitos.md # Requisitos Funcionales, No Funcionales y User Stories
│   ├── Gest_Proy_Soft/            # Material de soporte académico y plantillas UX
│   └── Archive/                   # Documentación y borradores históricos
│
├── VR_Semaforo/                   # [Proyecto de Referencia / PoC funcional] (Intacto)
│                                  # Prototipo previo de semáforo inteligente para estudio y auditoría.
│
├── VIGIA_Core/                    # Coordina el estado del entorno y garantiza decisiones seguras
│   └── README.md
│
├── VIGIA_Vision/                  # Ojos de VIGIA: captura video e interpreta lo que ve
│   └── README.md
│
├── VIGIA_IoT/                     # Brazos y tacto de VIGIA: sensores, actuadores y verificación física
│   └── README.md
│
├── VIGIA_Automation/              # Inteligencia de decisión: reglas y políticas operativas
│   └── README.md
│
├── VIGIA_API/                     # Puerta de comunicación para supervisión e integración externa
│   └── README.md
│
├── VIGIA_Dashboard/               # Interfaz visual de supervisión y control operativo humano
│   └── README.md
│
├── tests/                         # Pruebas automatizadas del ciclo físico mediante simulación/mocks
│   └── README.md
│
├── scripts/                       # Utilidades auxiliares para desarrollo y mantenimiento
│   └── README.md
│
└── .gitignore                     # Exclusiones de control de versiones limpias y profesionales
```

---

## 6. Relación entre Módulos al Servicio del Ciclo

Los componentes de software existen exclusivamente para articular el ciclo físico de la caseta o entorno:

```text
 ┌──────────────┐         ┌──────────────┐
 │ VIGIA_Vision │         │  VIGIA_IoT   │
 │ (Cámaras/LPR)│         │ (Sensores)   │
 └──────┬───────┘         └──────┬───────┘
        │                        │
        │ Observación interpretada│ Señal física (Auto presente)
        └───────────┬────────────┘
                    ▼
           ┌─────────────────┐
           │   VIGIA_Core    │ <───> ┌───────────┐
           │ (Estado Actual) │       │ VIGIA_API │ <───> ┌─────────────────┐
           └────────┬────────┘       └───────────┘       │ VIGIA_Dashboard │
                    │ Contexto                           │  (Supervisión)  │
                    ▼                                    └─────────────────┘
         ┌────────────────────┐
         │  VIGIA_Automation  │  Evalúa: ¿Vehículo autorizado?
         │  (Motor de Reglas) │  Decide: Ordenar apertura de barrera
         └──────────┬─────────┘
                    │ Decisión
                    ▼
           ┌─────────────────┐
           │   VIGIA_Core    │  Valida seguridad y comanda acción
           └────────┬────────┘
                    │ Orden de actuación
                    ▼
             ┌─────────────┐
             │  VIGIA_IoT  │ ──> ACTÚA: Activa motor de barrera
             └──────┬──────┘
                    │
                    ▼ VERIFICA: Sensor confirma barrera abierta
           ┌─────────────────┐
           │   VIGIA_Core    │ ──> REGISTRA el acceso
           └────────┬────────┘
                    │
                    ▼ MEJORA: Archiva imágenes dudosas para reentrenamiento
```

---

## 7. Roadmap Orientado a Capacidades

El desarrollo del sistema no se mide en "carpetas programadas", sino en **capacidades reales del producto**:

* **Capacidad 1 — Observar e Identificar:** Detectar vehículos y reconocer placas con cámaras.
* **Capacidad 2 — Decidir:** Evaluar si el vehículo está autorizado según la base de datos y reglas.
* **Capacidad 3 — Actuar:** Comandar la barrera física o semáforo mediante microcontroladores.
* **Capacidad 4 — Verificar:** Comprobar mediante sensores que la barrera realmente abrió y que el vehículo cruzó.
* **Capacidad 5 — Registrar:** Generar la bitácora inmutable de accesos para auditoría y seguridad.
* **Capacidad 6 — Supervisar:** Permitir al operador ver el estado en vivo y actuar en contingencias desde el Dashboard.
* **Capacidad 7 — Mejorar:** Retroalimentar el sistema con casos de detección dudosos para mejorar los modelos de IA.

---

## 8. Estado Actual

El repositorio se encuentra en su **Fase 0 (Arquitectura y Fundaciones)**:
* La idea fundamental del producto, su caso de uso rector y sus principios de diseño están formalizados.
* Los espacios modulares están preparados sin código prematuro ni sobreingeniería.
* El prototipo funcional previo `VR_Semaforo/` permanece intacto para ser auditado en la Fase 1.
