# Suite de Pruebas Automatizadas — VIGIA Vision Systems

**Entorno Central de Validación, Integración y Calidad del Software**

---

## 1. Filosofía de Testing

En **VIGIA Vision Systems**, la testeabilidad es un principio arquitectónico no negociable. Todo componente crítico debe diseñarse de forma modular e inyectable para poder ser probado de manera completamente aislada y automatizada.

### Principio de Independencia de Hardware
Ninguna prueba automatizada debe fallar o quedar bloqueada por la ausencia de hardware físico:
* Las cámaras físicas se reemplazan por **fixtures de video simulado o generadores sintéticos de frames**.
* Los microcontroladores (Arduino/ESP32) y sensores físicos se reemplazan por **dispositivos simulados (`mocks`/`stubs`)** que implementan los mismos contratos de comunicación.
* El reloj del sistema y los temporizadores de semáforos deben poder ser controlados o acelerados en las pruebas de automatización.

---

## 2. Organización Prevista de la Suite de Pruebas

Conforme se desarrolle el código en las fases subsiguientes, este directorio estructurará las pruebas en:

```text
tests/
├── README.md                  # [Este documento] Filosofía y pautas de testing
├── conftest.py                # Fixtures globales compartidos de pytest
│
├── unit/                      # Pruebas unitarias aisladas por módulo
│   ├── test_core/             # Validación del bus de eventos, estado y modelos
│   ├── test_vision/           # Validación de preprocesamiento, inferencia y tracking con frames sintéticos
│   ├── test_iot/              # Validación de protocolos, tramas seriales y parsing de sensores con mocks
│   ├── test_automation/       # Validación de evaluación de reglas, disparadores y tiempos de ciclo
│   └── test_api/              # Validación de endpoints, validación de schemas y autenticación
│
├── integration/               # Pruebas de integración entre subsistemas
│   ├── test_vision_to_core/   # Detección simulada -> publicación en EventBus
│   ├── test_core_to_rules/    # Evento de tráfico -> decisión del RulesEngine
│   └── test_rules_to_iot/     # Decisión tomada -> comando despachado a dispositivo simulado
│
└── mocks/                     # Utilidades de simulación y dobles de prueba
    ├── mock_camera.py         # Emulador de stream de video en bucle
    ├── mock_serial.py         # Emulador de puerto serie de Arduino
    └── mock_devices.py        # Sensores y semáforos virtuales
```

---

## 3. Estado Actual

> **IMPORTANTE:**  
> En esta etapa (**Fase 0**), no se introducen tests ficticios o vacíos innecesarios.  
> Las suites de pruebas se crearán en sincronía con la implementación de cada módulo a partir de la Fase 2, utilizando `pytest`.
