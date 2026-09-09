# VIGIA_IoT

**Subsistema de Interfaz Física: Sensores, Actuadores y Verificación en Lazo Cerrado**

---

## 1. Responsabilidad del Módulo

`VIGIA_IoT` es el puente tangible entre el software de **VIGIA Vision Systems** y el mundo físico:
$$\text{Observar (Sensores)} \longrightarrow \text{Interpretar} \longrightarrow \text{Decidir} \longrightarrow \mathbf{ACTUAR} \longrightarrow \mathbf{VERIFICAR} \longrightarrow \text{Registrar} \longrightarrow \text{Mejorar}$$

Su función es doble:
1. **Sensórica (Entrada):** Leer las magnitudes físicas del entorno (presencia de vehículos sobre lazos inductivos, detección de obstáculos en fotoceldas, botones de llamada).
2. **Actuación y Verificación Física (Salida):** Enviar comandos físicos a actuadores (levantar barrera con servomotor, conmutar semáforo a verde) y **comprobar mediante sensores de confirmación** que la acción física realmente ocurrió en el mundo real (el sensor de final de carrera detecta la barrera arriba; la fotocelda detecta que el auto cruzó).

```text
               COMANDOS DE ACTUACIÓN               VERIFICACIÓN FÍSICA
             (Core -> IoT -> Hardware)          (Hardware -> IoT -> Core)

              VIGIA_Core (Ordena)               Sensor Físico (Confirma)
                      │                                    │
                      ▼                                    ▼
             [Driver de Hardware]                 [Lectura de Sensor]
                      │                                    │
                      ▼                                    ▼
              Actuador Físico                   VIGIA_Core (Verificado)
           (Servomotor de Barrera)           (Barrera arriba / Auto cruzó)
```

---

## 2. Contrato de Comunicación Física

* **Canal de Sensores (Entrada):**
  * Emisión de eventos cuando el entorno cambia: `AutoDetectadoEnEntrada`, `ObstaculoEnBarrera`, `AutoCruzoBarrera`.
* **Canal de Actuadores (Salida):**
  * Ejecución de órdenes de actuación: `AbrirBarrera`, `CerrarBarrera`, `PonerSemaforoVerde`, `PonerSemaforoRojo`.
* **Canal de Verificación Física:**
  * Reporte de comprobación física en el entorno: `BarreraAbiertaConfirmada`, `CarrilDespejadoConfirmado`.

---

## 3. Componentes Previstos (Fase 4 del Roadmap)

* **Serial / USB Connection:** Comunicación estable con placas Arduino o ESP32 con auto-reconexión en caliente.
* **Firmware Modular:** Código simple para el microcontrolador que controla los pines de relés/servos y reporta las interrupciones de sensores.
* **Sensor Filters:** Filtrado digital de señales para evitar lecturas falsas (*debounce* de botones y sensores ópticos).
* **Fail-Safe Watchdog:** Mecanismo de seguridad que mantiene la barrera abierta o en modo seguro si se pierde la comunicación con el computador principal.

---

## 4. Estado Actual

> **IMPORTANTE:**  
> En esta etapa (**Fase 0**), este módulo permanece intencionalmente sin código de implementación.  
> Se desarrollará en la Fase 4 del Roadmap aprovechando los aprendizajes del firmware previo de `VR_Semaforo/arduino/`.
