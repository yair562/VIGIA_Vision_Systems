# VIGIA Vision Systems

## 06 — Propuesta del Proyecto

**Estado:** Activo / Propuesta Ejecutiva  
**Versión:** 1.0  
**Audiencia:** Presentación Académica, Evaluación Institucional y Dirección de Proyecto  
**Propósito:** Presentar formal y conceptualmente la iniciativa tecnológica VIGIA Vision Systems, su justificación, alcance, objetivos y modelo de desarrollo para el caso rector de automatización física.

---

# 1. VIGIA Vision Systems

### 1.1 Descripción de la Iniciativa Tecnológica
**VIGIA Vision Systems** es una iniciativa de desarrollo tecnológico orientada a la creación de una plataforma inteligente para la supervisión, análisis y automatización de entornos del mundo real.

La naturaleza del proyecto radica en cerrar la brecha entre el procesamiento digital de información y la dinámica del espacio físico. VIGIA concibe el entorno no como un conjunto de eventos aislados, sino como un sistema continuo donde sensores ópticos y físicos capturan la realidad, algoritmos de análisis extraen contexto significativo, un motor de reglas evalúa decisiones autorizadas y actuadores electromecánicos ejecutan acciones inmediatas, verificando su cumplimiento en tiempo real.

VIGIA no es una empresa comercialmente constituida ni un producto terminado en el mercado; representa un proyecto integral de ingeniería aplicada enfocado en resolver problemas reales de interacción físico-digital con criterios de robustez, trazabilidad y mínima complejidad.

### 1.2 Misión
Desarrollar soluciones de software y hardware integradas que transformen la observación del entorno físico en decisiones autónomas, seguras y verificables, optimizando el control operativo y la supervisión de accesos mediante la convergencia de visión artificial, sistemas embebidos y automatización.

### 1.3 Visión
Consolidar a VIGIA como una plataforma modular, confiable y escalable para la gobernanza de entornos físicos inteligentes, capaz de adaptarse a diversos escenarios de control de accesos, logística e instalaciones industriales sin requerir rediseños estructurales en su núcleo tecnológico.

### 1.4 Propuesta de Valor
La diferenciación fundamental de VIGIA reside en su concepción sistémica:

> **VIGIA no es simplemente un sistema de cámaras ni un software aislado de lectura de matrículas (LPR).**

Mientras que las soluciones convencionales suelen limitarse a grabar video o mostrar alertas en pantalla dejando la acción y comprobación en manos humanas, VIGIA **integra el ciclo operacional completo**:
* **Percibe** con cámaras y sensores.
* **Evalúa** bajo reglas lógicas e invariantes de seguridad.
* **Actúa** directamente sobre barreras o dispositivos físicos.
* **Verifica** en lazo cerrado que la acción mecánica realmente ocurrió.
* **Registra** evidencia estructurada para auditoría y mejora continua.

---

# 2. El Proyecto VIGIA

### 2.1 Planteamiento del Problema
En la gestión contemporánea de entornos físicos —tales como accesos vehiculares, estacionamientos y perímetros restringidos— predominan procesos operativos vulnerables a deficiencias sistemáticas:
* **Dependencia de procesos manuales:** La verificación visual de credenciales y el accionamiento manual de barreras provocan lentitud en horas pico y fatiga en el personal de guardia.
* **Falta de información en tiempo real:** Los responsables de seguridad carecen de datos estructurados e inmediatos sobre aforos, estados de carriles o incidencias mecánicas.
* **Sistemas aislados y desarticulados:** Es común encontrar cámaras de circuito cerrado (CCTV), barreras electromecánicas y bases de datos operando de manera independiente, sin comunicación nativa entre sí.
* **Ausencia de trazabilidad y auditoría:** Ante un incidente o paso no autorizado, con frecuencia no existe una correlación temporal confiable entre la decisión de apertura, la evidencia fotográfica y la lectura del sensor físico.
* **Dificultad de integración:** La combinación de sensores físicos, visión artificial y lógica de negocio suele abordarse mediante adaptaciones improvisadas que generan fallas operativas frecuentes.

### 2.2 Solución Propuesta
VIGIA propone una arquitectura unificada que conecta armónicamente el mundo físico con el mundo lógico a través de un ciclo continuo de siete etapas:

```text
               ┌──────────────────────────────┐
               │        ENTORNO FÍSICO        │
               │ (Vehículos, carriles, paso)  │
               └──────────────┬───────────────┘
                              │
                              ▼
                     [1. PERCIBIR]
                     Cámaras y Sensores
                              │ Observación estructurada
                              ▼
                     [2. DECIDIR]
                     Reglas de Acceso e Invariantes
                              │ Comando autorizado
                              ▼
                     [3. ACTUAR]
                     Barrera física y Señalización
                              │
                              ▼
                     [4. VERIFICAR]
                     Lazo cerrado sensorial (ACK físico)
                              │ Confirmación / Anomalía
                              ▼
                     [5. REGISTRAR]
                     Trazabilidad y Evidencia fotográfica
                              │
                              ▼
                     [6. SUPERVISAR]
                     Visualización en tiempo real
                              │
                              ▼
                     [7. MEJORAR]
                     Calibración y métricas de desempeño
```

### 2.3 Objetivo General
Desarrollar y validar una plataforma modular e inteligente capaz de supervisar, gobernar y automatizar un entorno físico en tiempo real, integrando visión computacional, sensores, controladores IoT y software de toma de decisiones deterministas en un ciclo cerrado y verificable.

### 2.4 Objetivos Específicos
1. **Percepción Inteligente:** Desarrollar la capacidad de capturar video del entorno, detectar la aproximación de vehículos y reconocer ópticamente sus matrículas vehiculares en forma de observaciones estructuradas.
2. **Decisión Determinista:** Implementar un gestor de estado y un motor de reglas que evalúe permisos de acceso de manera segura, garantizando que ninguna acción física se ejecute si viola restricciones de seguridad.
3. **Actuación y Control Embebido:** Diseñar la interfaz de hardware y firmware para comandar de manera confiable dispositivos electromecánicos (barreras y semáforos) mediante protocolos de comunicación robustos.
4. **Verificación en Lazo Cerrado:** Establecer un mecanismo de instrumentación sensorial que compruebe físicamente el cumplimiento de las maniobras comandadas y detecte anomalías o bloqueos mecánicos.
5. **Memoria Operacional y Auditoría:** Construir un repositorio de persistencia local que conserve la cronología completa de cada evento, correlacionando la decisión tomada con la evidencia fotográfica y la telemetría física.
6. **Validación Integral del Sistema:** Demostrar y documentar el funcionamiento ininterrumpido del sistema completo en un escenario de prueba representativo bajo condiciones normales y casos límite.

### 2.5 Caso de Uso Inicial: Caseta Inteligente de Acceso Vehicular
Para demostrar la viabilidad técnica y operacional de VIGIA, se adopta como **caso de uso rector inicial** la automatización de una **Caseta de Acceso Vehicular**:

1. **Aproximación:** Un vehículo ingresa al carril de acceso; el sistema detecta su presencia visualmente.
2. **Identificación:** Se localiza la placa de circulación y se realiza la lectura de sus caracteres.
3. **Evaluación:** El sistema contrasta la placa con el registro de permisos y horarios permitidos.
4. **Actuación:** Si el acceso es legítimo y no hay riesgos físicos, se ordena el levantamiento de la barrera y se enciende la luz verde.
5. **Verificación:** Sensores de posición confirman que la barrera subió; sensores de despeje confirman que el vehículo cruzó completamente antes de bajarla.
6. **Auditoría:** Se almacena el registro exacto del cruce junto con la captura fotográfica del móvil para posterior consulta del personal de seguridad.

### 2.6 Alcance del Proyecto

#### Dentro del Alcance Inicial:
* Diseño e implementación de la plataforma base y sus módulos de coordinación (`VIGIA_Core`).
* Integración funcional de visión artificial para detección y lectura de matrículas.
* Controlador de hardware embebido con lectura de sensores y control de servomotores / barrera.
* Panel web básico de supervisión para visualización de estado y eventos en tiempo real.
* Registro estructurado local de auditoría y almacenamiento de capturas de evidencia.
* Validación experimental del ciclo completo en maqueta de pruebas / banco de laboratorio.

#### Fuera del Alcance Inicial:
* Despliegue comercial o instalación industrial en fraccionamientos a escala real.
* Cobertura de otros entornos físicos (cruces semafóricos complejos, aforos peatonales múltiples).
* Conexión con infraestructuras externas complejas en la nube o pagos en línea.
* Módulos avanzados de autoaprendizaje en producción (*Active Learning* continuo automatizado).

### 2.7 Resultado Esperado
El proyecto concluirá con una **demostración funcional integrada** donde la plataforma VIGIA ejecute de punta a punta el ciclo rector ante vehículos reales o a escala controlada, evidenciando de forma tangible:
$$\text{Percibir} \longrightarrow \text{Decidir} \longrightarrow \text{Actuar} \longrightarrow \text{Verificar} \longrightarrow \text{Registrar}$$

---

# 3. Equipo y Metodología de Trabajo

### 3.1 Organización Multidisciplinaria
El desarrollo de VIGIA es ejecutado por un equipo multidisciplinario estructurado en áreas de especialidad técnica:
* **Producto y Arquitectura:** Dirección general del producto, requerimientos y gobernanza del sistema.
* **AI / Computer Vision:** Procesamiento de imágenes, localización de placas y algoritmos de lectura óptica.
* **Backend y Servicios:** Lógica de estados de carril, reglas de negocio y persistencia de auditoría.
* **Frontend y Dashboard:** Diseño de experiencia operativa, interfaces de visualización y monitoreo en vivo.
* **Hardware y Sistemas Embebidos (IoT):** Diseño de circuitos, firmware de control, sensores y actuadores.
* **DevOps e Infraestructura:** Estandarización de entornos de prueba y empaquetado para hardware de borde.
* **Datos e Inteligencia Operativa:** Modelado relacional, preservación de evidencias y telemetría.
* **Investigación de Mercado y Web Institucional:** Validación de usuarios, análisis de viabilidad y difusión del proyecto.

### 3.2 Metodología de Ejecución
El proyecto opera bajo:

> **Scrum como marco de trabajo ágil, con desarrollo paralelo por dominios y coordinación mediante un Roadmap común de capacidades.**

Los diferentes frentes de ingeniería (hardware, visión, backend, interfaz) avanzan de forma simultánea. Para evitar que el avance de un área bloquee a las demás, el trabajo se coordina mediante **contratos de interfaces formales, datos simulados y pruebas de integración periódicas**, asegurando que cada componente pueda ser probado individualmente antes de la convergencia final.

---

# 4. Impacto y Proyección

### 4.1 Valor Técnico y Académico
El proyecto constituye un ejercicio riguroso de integración físico-digital. Permite converger disciplinas de inteligencia artificial, visión por computadora, programación en tiempo real, electrónica embebida e ingeniería de software moderna en una sola solución cohesiva, aplicando buenas prácticas de desacoplamiento y control de lazo cerrado.

### 4.2 Valor Práctico y Operativo
VIGIA demuestra cómo transformar una caseta convencional en un punto de acceso ágil, minimizando demoras, reduciendo el margen de error o soborno en accesos no autorizados y proveyendo certeza forense absoluta a los administradores del inmueble.

### 4.3 Escalabilidad y Evolución Futura
La caseta vehicular representa únicamente el escenario de validación inicial. Gracias a su arquitectura desacoplada centrada en el ciclo físico, la plataforma VIGIA proyecta una evolución natural hacia:
* **Control de accesos peatonales y corporativos.**
* **Administración inteligente de estacionamientos y conteo de cajones.**
* **Semaforización adaptativa y cruces viales urbanos.**
* **Supervisión de seguridad y control de perímetros en instalaciones críticas.**
* **Monitoreo de flujo y trazabilidad de materiales en entornos industriales.**

*(Estas aplicaciones representan oportunidades de escalabilidad tecnológica a mediano plazo, no compromisos inmediatos de la primera etapa).*

---

# 5. Conclusión

**VIGIA Vision Systems** aborda una necesidad crítica en la interacción entre la tecnología y el entorno físico: la falta de sistemas integrados que no solo observen la realidad, sino que actúen sobre ella de forma controlada, segura y auditable.

El proyecto propone una plataforma integral que sustituye los esquemas aislados tradicionales por un ciclo cerrado de percepción, decisión, control y verificación. Al adoptar la **Caseta Inteligente de Acceso Vehicular** como caso de uso inicial, el equipo valida la madurez de su tecnología en un escenario medible, tangible y de alto impacto operativo.

> **La Caseta Inteligente de Acceso Vehicular es el primer escenario de validación de una plataforma tecnológica más amplia: VIGIA Vision Systems.**
