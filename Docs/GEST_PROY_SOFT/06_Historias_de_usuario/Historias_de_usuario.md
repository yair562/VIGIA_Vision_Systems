# 06 — Historias de Usuario (User Stories)

**Proyecto:** VIGIA Vision Systems  
**Producto:** VIGIA *(Caseta Inteligente de Acceso Vehicular)*  
**Área:** Gestión de Producto y Requisitos Ágiles  
**Responsable del Entregable:** Vianey  
**Puesto / Rol del Responsable:** Product Owner (PO)  
**Versión:** 1.0  
**Fecha:** 21 de septiembre de 2026  

---

## 1. Catálogo de Historias de Usuario del Caso Rector

### HU-01: Detección y Lectura de Placa de Residente
* **Como** sistema VIGIA,
* **quiero** detectar el vehículo que se aproxima y extraer los caracteres de su matrícula,
* **para** verificar si cuenta con autorización de acceso sin requerir captura manual.
* **Criterios de Aceptación:**
  * **Dado que** un vehículo ingresa al área de aproximación de la cámara de carril,
  * **Cuando** el pipeline de visión procesa el cuadro de video,
  * **Entonces** emite un evento estructurado de observación (`ObservationEvent`) con la placa detectada y un índice de confianza.

---

### HU-02: Autorización y Apertura Automática
* **Como** conductor autorizado,
* **quiero** que la barrera vehicular se levante automáticamente al identificarse mi vehículo,
* **para** ingresar a las instalaciones con mínima demora.
* **Criterios de Aceptación:**
  * **Dado que** el Core recibe una observación con una placa registrada en horario válido,
  * **Cuando** el motor de reglas aprueba el acceso y el Core valida que el carril está despejado,
  * **Entonces** se comanda la apertura física hacia el subsistema IoT y se conmuta la señalización a paso habilitado.

---

### HU-03: Verificación Sensorial de Cruce y Cierre Seguro
* **Como** responsable de seguridad física,
* **quiero** que la barrera descienda únicamente tras verificar que el vehículo completó el cruce,
* **para** evitar colisiones mecánicas y daños a personas o vehículos.
* **Criterios de Aceptación:**
  * **Dado que** la barrera se encuentra abierta y el vehículo inicia su trayectoria de cruce,
  * **Cuando** el sensor de despeje detecta el paso y posteriormente reporta el carril libre,
  * **Entonces** el sistema aguarda el tiempo de tolerancia de seguridad y ordena el descenso seguro de la barrera.

---

### HU-04: Registro Persistente de Auditoría del Acceso
* **Como** administrador de accesos,
* **quiero** que cada evento de cruce genere un registro persistente con fecha, hora, placa y evidencia fotográfica,
* **para** mantener trazabilidad y respaldo ante auditorías operativas.
* **Criterios de Aceptación:**
  * **Dado que** finaliza una interacción de acceso (autorizado o denegado),
  * **Cuando** el Core concluye el ciclo del evento,
  * **Entonces** se almacena en la base de datos local un registro con `id_evento`, `timestamp`, `placa`, `resultado` y el enlace a la captura de imagen archivada.

---

### HU-05: Supervisión y Apertura Manual por el Operador
* **Como** operador de guardia en caseta,
* **quiero** visualizar el estado del carril en el Dashboard y pulsar un comando de apertura manual ante contingencias,
* **para** gestionar accesos especiales o resolver fallos temporales de identificación.
* **Criterios de Aceptación:**
  * **Dado que** el operador requiere autorizar el paso de un vehículo no registrado (ej. servicios de emergencia),
  * **Cuando** acciona el comando de apertura manual en la interfaz de supervisión,
  * **Entonces** el sistema valida la autorización del operador, emite el comando de apertura y registra el evento bajo la categoría `ACCESO_MANUAL_SUPERVISADO`.
