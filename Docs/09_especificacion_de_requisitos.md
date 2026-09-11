# VIGIA Vision Systems

## 09 — Especificación de Requisitos de Software y Dominio

**Estado:** Activo / Fase 0 (Línea Base para Refinamiento en Sprint 1)  
**Versión:** 1.1 (Alineación Arquitectónica y Desacoplamiento de Decisiones de Implementación)  
**Fuente de Verdad:** Requisitos Funcionales, No Funcionales e Historias de Usuario  
**Responsables de Gobernanza:** Josue (Product Owner) & Naty (QA / Business Analyst)  
**Propósito:** Definir formalmente los requisitos funcionales, requisitos no funcionales, reglas de negocio, invariantes de seguridad e historias de usuario para el caso de uso rector de VIGIA Vision Systems: la **Caseta Inteligente de Acceso Vehicular**.

---

# 1. Introducción y Alcance del Caso Rector

### 1.1 Objetivo del Producto
Gobernar el acceso de vehículos en una caseta mediante un ciclo cerrado en tiempo real que integra:
$$\text{Observar} \longrightarrow \text{Interpretar} \longrightarrow \text{Decidir} \longrightarrow \text{Actuar} \longrightarrow \text{Verificar} \longrightarrow \text{Registrar} \longrightarrow \text{Mejorar}$$

### 1.2 Actores del Sistema
1. **Vehículo / Conductor:** Entidad física que busca ingresar por el carril de acceso.
2. **Operador de Caseta / Guardia:** Usuario humano que supervisa el carril mediante el Dashboard y ejecuta mandos manuales supervisados ante contingencias.
3. **Administrador del Sistema:** Usuario que gestiona la lista de placas autorizadas, horarios y consulta auditorías.
4. **VIGIA (Plataforma Autónoma):** Agente de software/hardware que percibe, decide, actúa y verifica en lazo cerrado.

---

# 2. Requisitos Funcionales (RF)

| ID | Nombre del Requisito | Descripción Funcional | Módulo Responsable | Estado |
| :-: | :--- | :--- | :---: | :---: |
| **RF-01** | **Captura de Flujo de Video** | El sistema debe capturar video en tiempo real desde una cámara orientada al carril de acceso a una tasa configurable. | `VIGIA_Vision` | 🟢 DEFINIDO |
| **RF-02** | **Detección de Presencia Vehicular** | El sistema debe detectar automáticamente la presencia de un vehículo cuando entra en la zona de aproximación visual o activa un sensor físico. | `VIGIA_Vision` / `VIGIA_IoT` | 🟢 DEFINIDO |
| **RF-03** | **Localización y Reconocimiento de Placa (LPR)** | El sistema debe segmentar la placa de matrícula del vehículo y extraer su cadena de caracteres junto con un índice de confianza. | `VIGIA_Vision` | 🟢 DEFINIDO |
| **RF-04** | **Evaluación Determinista de Autorización** | El sistema debe contrastar la placa reconocida y el momento del acceso contra las políticas y listas de vehículos autorizados. | `VIGIA_Automation` | 🟢 DEFINIDO |
| **RF-05** | **Validación de Invariantes de Seguridad** | `VIGIA_Core` debe validar que no existan condiciones de riesgo físico (ej. vehículo en zona de trayectoria de barrera o paro de emergencia activo) antes de autorizar cualquier actuación mecánica. | `VIGIA_Core` | 🟢 DEFINIDO |
| **RF-06** | **Comando de Actuación Física (Apertura)** | El sistema debe enviar la orden de apertura a la barrera electromecánica y conmutar la señalización física a paso habilitado si el acceso es concedido. | `VIGIA_IoT` | 🟢 DEFINIDO |
| **RF-07** | **Verificación Sensorial de Apertura** | El sistema debe confirmar mediante sensores físicos de tope/posición que la barrera alcanzó la posición abierta antes de considerar completada la maniobra. | `VIGIA_IoT` / `VIGIA_Core` | 🟢 DEFINIDO |
| **RF-08** | **Detección y Verificación de Cruce Completo** | El sistema debe confirmar mediante sensores de despeje (fotoceldas/lazos) que el vehículo completó el cruce antes de ordenar el cierre de la barrera. | `VIGIA_IoT` / `VIGIA_Core` | 🟢 DEFINIDO |
| **RF-09** | **Comando de Cierre Seguro** | El sistema debe ordenar el descenso de la barrera y conmutar la señalización a estado cerrado/alto tras confirmar el despeje físico del carril. | `VIGIA_IoT` | 🟢 DEFINIDO |
| **RF-10** | **Registro Persistente de Auditoría y Trazabilidad** | El sistema debe registrar de forma persistente y estructurada en almacenamiento local la fecha, hora, placa leída, nivel de confianza, decisión tomada, ruta de evidencia fotográfica y confirmaciones sensoriales para fines de auditoría y trazabilidad. *(Nota: mecanismos específicos de inmutabilidad criptográfica o hardware se evaluarán si surge el requisito).* | `VIGIA_Core` / Adaptador DB | 🟢 DEFINIDO |
| **RF-11** | **Monitoreo Visual en Dashboard** | El sistema debe presentar en tiempo real al operador el estado actual del carril (Libre / En Espera / Autorizado / Cruzando / Denegado), vista de cámara y eventos operativos. | `VIGIA_Dashboard` / `VIGIA_API` | 🟢 DEFINIDO |
| **RF-12** | **Apertura Manual Supervisada** | El operador de caseta debe poder accionar la apertura manual supervisada desde el Dashboard ante excepciones, registrando obligatoriamente el evento y usuario. | `VIGIA_Dashboard` / `VIGIA_Core` | 🟢 DEFINIDO |
| **RF-13** | **Exportación de Casos Dudosos (Active Learning)** | El sistema debe archivar automáticamente imágenes de detecciones con baja confianza de lectura para enriquecer datasets de calibración posterior. | `VIGIA_Vision` | 🟢 DEFINIDO |
| **RF-14** | **Gestión de Lista de Autorizados** | El sistema debe permitir registrar, actualizar y dar de baja placas autorizadas con sus rangos de horario permitidos. | `VIGIA_API` | `[PENDIENTE DE DEFINICIÓN DE ESQUEMA DETALLADO EN SPRINT 1]` |
| **RF-15** | **Alerta por Bloqueo o Anomalía Mecánica** | El sistema debe emitir una alerta sonora/visual si la barrera no responde dentro del tiempo límite previsto tras la orden de maniobra. | `VIGIA_Core` / `VIGIA_Dashboard` | `[PENDIENTE DE DEFINICIÓN DE TIMEOUT EN SPRINT 1]` |

---

# 3. Requisitos No Funcionales (RNF)

| ID | Categoría | Requisito de Calidad | Métrica / Criterio Objetivo | Estado |
| :-: | :--- | :--- | :--- | :---: |
| **RNF-01** | **Rendimiento** | Tiempo de ciclo de decisión (desde la detección del frame hasta la emisión del comando de apertura). | $\le 1.5\text{ s}$ en hardware objetivo de borde. | `[VALOR OBJETIVO DE INGENIERÍA — SUJETO A BENCHMARK EN SPRINT 2]` |
| **RNF-02** | **Confiabilidad** | Operación autónoma en el borde sin requerir conexión continua a servicios en la nube. | 100% de funciones operativas en entorno local. | 🟢 DEFINIDO |
| **RNF-03** | **Testeabilidad** | Los módulos de software deben poder probarse sin requerir microcontrolador ni cámara física conectados. | Cobertura mediante emuladores seriales y fixtures de video en `tests/`. | 🟢 DEFINIDO |
| **RNF-04** | **Seguridad Física** | Prioridad incondicional de seguridad (*Fail-Safe*) sobre órdenes de automatización o mandos remotos. | Bloqueo físico de descenso ante detección de obstáculos. | 🟢 DEFINIDO |
| **RNF-05** | **Modularidad** | Acoplamiento débil entre módulos periféricos mediante contratos de datos mediadas por el Core. | Cero dependencias directas entre Visión e IoT. | 🟢 DEFINIDO |
| **RNF-06** | **Mantenibilidad** | Código modular en Python conforme a estándares de legibilidad, modularidad y tipado definidos en `Docs/04`. | Aprobación de suites de pruebas y estándares de estilo. | 🟢 DEFINIDO |

---

# 4. Historias de Usuario (User Stories — Sprint 1)

### HU-01: Detección y Lectura de Placa de Residente
* **Como** sistema VIGIA,
* **quiero** detectar el vehículo que se aproxima y extraer los caracteres de su matrícula,
* **para** verificar si cuenta con autorización de acceso sin requerir captura manual.
* **Criterios de Aceptación:**
  * **Dado que** un vehículo ingresa al área de aproximación de la cámara de carril,
  * **Cuando** el pipeline de visión procesa el cuadro de video,
  * **Entonces** emite un evento estructurado de observación (`ObservationEvent`) con la placa detectada y un índice de confianza `[VALOR OBJETIVO INICIAL ≥ 0.80 — SUJETO A CALIBRACIÓN EN SPRINT 1/2]`.

### HU-02: Autorización y Apertura Automática
* **Como** conductor autorizado,
* **quiero** que la barrera vehicular se levante automáticamente al identificarse mi vehículo,
* **para** ingresar a las instalaciones con mínima demora.
* **Criterios de Aceptación:**
  * **Dado que** el Core recibe una observación con una placa registrada en horario válido,
  * **Cuando** el motor de reglas aprueba el acceso y el Core valida que el carril está despejado,
  * **Entonces** se comanda la apertura física hacia el subsistema IoT y se conmuta la señalización a paso habilitado.

### HU-03: Verificación Sensorial de Cruce y Cierre Seguro
* **Como** responsable de seguridad física,
* **quiero** que la barrera descienda únicamente tras verificar que el vehículo completó el cruce,
* **para** evitar colisiones mecánicas y daños a personas o vehículos.
* **Criterios de Aceptación:**
  * **Dado que** la barrera se encuentra abierta y el vehículo inicia su trayectoria de cruce,
  * **Cuando** el sensor de despeje detecta el paso y posteriormente reporta el carril libre,
  * **Entonces** el sistema aguarda el tiempo de tolerancia de seguridad `[VALOR OBJETIVO: 2 s — PARAMETRIZABLE]` y ordena el descenso seguro de la barrera.

### HU-04: Registro Persistente de Auditoría del Acceso
* **Como** administrador de accesos,
* **quiero** que cada evento de cruce genere un registro persistente con fecha, hora, placa y evidencia fotográfica,
* **para** mantener trazabilidad y respaldo ante auditorías operativas.
* **Criterios de Aceptación:**
  * **Dado que** finaliza una interacción de acceso (autorizado o denegado),
  * **Cuando** el Core concluye el ciclo del evento,
  * **Entonces** se almacena en la base de datos local un registro con `id_evento`, `timestamp`, `placa`, `resultado` y el enlace a la captura de imagen archivada.

### HU-05: Supervisión y Apertura Manual por el Operador
* **Como** operador de guardia en caseta,
* **quiero** visualizar el estado del carril en el Dashboard y pulsar un comando de apertura manual ante contingencias,
* **para** gestionar accesos especiales o resolver fallos temporales de identificación.
* **Criterios de Aceptación:**
  * **Dado que** el operador requiere autorizar el paso de un vehículo no registrado (ej. servicios de emergencia),
  * **Cuando** acciona el comando de apertura manual en la interfaz de supervisión,
  * **Entonces** el sistema valida la autorización del operador, emite el comando de apertura y registra el evento bajo la categoría `ACCESO_MANUAL_SUPERVISADO`.

---

# 5. Reglas de Negocio e Invariantes de Seguridad

### 5.1 Reglas de Negocio Operativas (`VIGIA_Automation`)
* **RN-01 (Condición de Autorización):** Un vehículo se autoriza SI y solo SI su placa coincide con un registro activo en la base de datos Y la hora de solicitud se encuentra dentro del intervalo horario permitido.
* **RN-02 (Respuesta ante No Autorizado):** Si la placa no existe en el registro o el horario no es válido, el sistema mantiene la barrera cerrada y emite notificación de atención al Dashboard.
* **RN-03 (Tiempo Máximo de Espera):** Si un vehículo autorizado no inicia el cruce dentro de una ventana máxima configurable `[PROPUESTA: 30 segundos — SUJETO A CALIBRACIÓN]`, el sistema emite alerta preventiva antes de ordenar el cierre de seguridad.

### 5.2 Invariantes Físicas de Seguridad (`VIGIA_Core`)
* **INV-01 (Protección Anti-Aplastamiento):** Bajo ninguna circunstancia se ejecutará la orden de cierre si el sensor de presencia/fotocelda detecta un objeto en la zona de trayectoria de la barrera.
* **INV-02 (Confirmación de Barrera Abierta):** No se considerará habilitado el paso hasta recibir la confirmación física del sensor de final de carrera superior.
* **INV-03 (Comportamiento Seguro ante Falla de Enlace):** Si se interrumpe la comunicación serial con el microcontrolador, el sistema pasará a estado de alerta y mantendrá la señalización restrictiva hasta su restablecimiento.
