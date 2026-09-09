# VIGIA Vision Systems

## 02 — Arquitectura Conceptual del Sistema

**Estado:** Activo / Fase 0  
**Versión:** 1.2 (Alineación con el Producto Físico)  
**Pregunta Central:** *¿Cómo se relacionan los componentes para cumplir el ciclo de VIGIA?*  
**Propósito:** Definir el modelo arquitectónico conceptual de VIGIA, el ciclo operativo en lazo cerrado (*Closed-Loop*), la caseta inteligente como aplicación rectora, la verificación física, la mejora continua y la distinción fundamental entre producto e implementación.

---

# 1. Visión Arquitectónica General

VIGIA es una plataforma de automatización inteligente orientada a gobernar entornos físicos. Su propósito no es servir de escaparate a tecnologías de moda, sino resolver un problema concreto mediante una secuencia armónica:

```text
ENTORNO FÍSICO
      ↓
   OBSERVAR
      ↓
 INTERPRETAR
      ↓
   DECIDIR
      ↓
    ACTUAR
      ↓
  VERIFICAR
      ↓
  REGISTRAR
      ↓
   MEJORAR
      ↺
```

---

# 2. El Ciclo Operativo Fundamental en Detalle

Cada etapa del ciclo responde a una necesidad física verificable:

### 2.1 Entorno Físico
El espacio del mundo real donde suceden los eventos: una caseta vehicular, un acceso a estacionamiento, un cruce con semáforos, un área restringida o una línea de producción. En él se encuentran objetos, vehículos, personas y dispositivos.

### 2.2 Observar (`Observe`)
* **Qué hace:** Adquiere señales crudas del entorno mediante cámaras de video y sensores físicos.
* **Componentes que participan:** `VIGIA_Vision` (flujos de video) y `VIGIA_IoT` (sensores de masa metálica, fotoceldas, botones peatonales).
* **Resultado:** Señales digitales y cuadros de imagen listos para ser comprendidos.

### 2.3 Interpretar (`Interpret`)
* **Qué hace:** Convierte señales visuales crudas en información semántica con significado para el negocio.
* **Componentes que participan:** `VIGIA_Vision` (modelos de detección de objetos, clasificación y reconocimiento de caracteres de placas - LPR).
* **Resultado:** "Vehículo sedán aproximándose al carril 1 con placa detectada `XYZ-789` (confianza 0.94)".

### 2.4 Decidir (`Decide`)
* **Qué hace:** Determina qué acción debe ocurrir en el entorno físico con base en la información interpretada, las reglas de negocio y el estado actual del sistema.
* **Componentes que participan:** `VIGIA_Automation` (evaluación de reglas y políticas de acceso) y `VIGIA_Core` (validación de seguridad y consistencia física).
* **Ejemplo:** *SI placa `XYZ-789` está en el registro de residentes autorizados Y la barrera está actualmente cerrada $\to$ AUTORIZAR APERTURA.*

### 2.5 Actuar (`Act`)
* **Qué hace:** Transmite una orden de control hacia el mundo real a través de actuadores físicos.
* **Componentes que participan:** `VIGIA_IoT` (microcontroladores Arduino/ESP32, relevadores, servomotores, displays, semáforos).
* **Resultado:** El servomotor levanta el brazo de la barrera vehicular o el semáforo conmuta a verde.

### 2.6 Verificar (`Verify`) — *El Lazo Cerrado*
* **Qué hace:** Comprueba mediante sensores físicos que la acción ordenada realmente se cumplió en el mundo real antes de asumir el nuevo estado.
* **Componentes que participan:** `VIGIA_IoT` y `VIGIA_Core`.
* **Diferencia con un simple ACK:** No es solo saber que el microcontrolador recibió la orden de software, sino **confirmar físicamente** que la barrera llegó al sensor de tope superior o que el vehículo efectivamente cruzó la fotocelda de seguridad.

### 2.7 Registrar (`Record`)
* **Qué hace:** Almacena de forma inmutable la bitácora de la operación (fecha, hora, placa, imagen de evidencia, decisión tomada, tiempos de apertura y confirmación de cruce) para auditoría, seguridad y supervisión humana.
* **Componentes que participan:** `VIGIA_Core` y el adaptador de persistencia.

### 2.8 Mejorar (`Improve`) — *Retroalimentación Continua*
* **Qué hace:** Aprovecha la experiencia registrada para calibrar el sistema y aumentar su precisión con el tiempo.
* **Componentes que participan:** `VIGIA_Vision` (archivado de detecciones con baja confianza para enriquecer datasets de reentrenamiento) y `VIGIA_Automation` (análisis de métricas de congestión para ajustar tiempos de espera).

---

# 3. Aplicación Rectora: Caseta Inteligente de Acceso Vehicular

Para comprobar que toda la arquitectura está al servicio del producto, VIGIA adopta la caseta vehicular como su caso de uso rector inicial:

```text
                    VIGIA
                      │
          ┌───────────┼───────────┐
          │           │           │
       CÁMARA       SENSORES    USUARIO / DASHBOARD
          │           │           │
          └───────────┼───────────┘
                      ▼
               INTERPRETACIÓN
                      │
          ┌───────────┴───────────┐
          │                       │
     ¿Vehículo?               ¿Placa?
          │                       │
          └───────────┬───────────┘
                      ▼
                   DECISIÓN
                      │
             ┌────────┴────────┐
             │                 │
          AUTORIZAR          DENEGAR
             │                 │
             ▼                 ▼
          ABRIR             MANTENER CERRADA /
          BARRERA           SOLICITAR REGISTRO
             │
             ▼
          ACTUAR (Servomotor / Relé)
             │
             ▼
          VERIFICAR (Sensor confirma barrera arriba y auto cruzando)
             │
             ▼
          REGISTRAR (Bitácora de acceso con evidencia)
             │
             ▼
          MEJORAR (Datos dudosos guardados para reentrenamiento)
```

### VIGIA es una Plataforma, no un dispositivo
La caseta es el demostrador principal del producto. La misma arquitectura resuelve:
```text
                  VIGIA
                    │
       ┌────────────┼────────────┐
       │            │            │
    PERCEPCIÓN   DECISIÓN      ACCIÓN
       │            │            │
       └────────────┼────────────┘
                    │
             APLICACIONES
                    │
       ┌────────────┼────────────┐
       │            │            │
    Caseta       Tráfico      Industria
   inteligente   inteligente   automatizada
```

---

# 4. Producto $\neq$ Implementación

Es fundamental que la documentación no confunda el concepto de VIGIA con las decisiones técnicas contingentes de software:

```text
CONCEPTO DE VIGIA (Permanente)            IMPLEMENTACIÓN ACTUAL (Intercambiable)
───────────────────────────────           ──────────────────────────────────────
Observar el entorno físico                Cámara USB, RTSP o simulación con video
Interpretar visualmente                    YOLOv8, YOLOv10 o detector clásico
Gobernar el estado y la seguridad         VIGIA_Core (en memoria)
Evaluar reglas de decisión                VIGIA_Automation (motor de reglas)
Interactuar con actuadores                VIGIA_IoT (Arduino, ESP32 o Raspberry Pi)
Supervisar la operación                   VIGIA_Dashboard (interfaz web reactiva)
Registrar la experiencia                  Persistencia en SQLite / base de datos simple
```

* Si mañana la comunicación cambia de un bus en memoria a llamadas directas: **VIGIA sigue siendo VIGIA.**
* Si cambiamos Arduino por ESP32: **VIGIA sigue siendo VIGIA.**
* Si cambiamos el modelo de visión: **VIGIA sigue siendo VIGIA.**
* Si cambiamos el motor de almacenamiento: **VIGIA sigue siendo VIGIA.**

---

# 5. Organización y Desacoplamiento de Módulos

Para evitar que los módulos se enreden en dependencias cruzadas (el antipatrón "código espagueti" que sufrió el prototipo anterior `VR_Semaforo`), la interacción se organiza de forma mediada:

```text
       CÁMARAS                        SENSORES FÍSICOS
          │                                  │
          ▼                                  ▼
    VIGIA_Vision                         VIGIA_IoT
          │                                  │
          │ "Auto con placa ABC-123"         │ "Auto pisando sensor"
          └─────────────────┬────────────────┘
                            ▼
                       VIGIA_Core ◄───► VIGIA_API ◄───► VIGIA_Dashboard
                     (Estado Actual)                     (Supervisión)
                            │
                            ▼ Contexto
                    VIGIA_Automation (Evalúa: ¿Placa autorizada? -> SÍ)
                            │
                            ▼ Decisión
                       VIGIA_Core (Valida seguridad del estado)
                            │
                            ▼ Orden de actuación
                        VIGIA_IoT (Pulso a servomotor de barrera)
                            │
                            ▼ VERIFICACIÓN: Sensor confirma apertura
                       VIGIA_Core (Registra evento / retroalimenta)
```

### Reglas de Interacción:
1. **Los módulos periféricos no se comunican entre sí:** `VIGIA_Vision` no envía comandos directos a `VIGIA_IoT`. Toda acción pasa por el Core y las reglas de decisión para garantizar que el estado del sistema sea siempre coherente.
2. **Sin burocracias de software artificiales:** La comunicación interna es directa y en memoria. No se añaden brokers externos (Kafka, Redis, RabbitMQ) ni procesos distribuidos innecesarios.
3. **Testeabilidad sin hardware:** Cada módulo puede probarse de forma aislada inyectando datos de prueba (videos grabados o sensores simulados).

---

# 6. Principios Rectores de Ingeniería

1. **Simplicidad Suficiente:** Implementar la solución mínima que resuelva correctamente la necesidad real.
2. **Abstracción de Hardware y Modelos:** El núcleo no depende de pines ni de puertos fijos; la visión no depende rígidamente de una sola arquitectura de red neuronal.
3. **Configuración sobre Código Quemado:** Cero IPs, puertos COM o credenciales fijas en el código fuente.
4. **Observabilidad Práctica:** Logs claros, métricas de detección y registro de eventos para diagnóstico sin sobrecargar el sistema.

> **Máxima Final:**  
> **"VIGIA debe crecer en capacidad, no en complejidad gratuita."**
