# VIGIA_Core

**Núcleo de Dominio, Estado del Entorno, Seguridad y Coordinación del Ciclo**

---

## 1. Responsabilidad del Módulo

`VIGIA_Core` es el cerebro coordinador de la plataforma **VIGIA Vision Systems**. Su propósito es mantener la representación del estado actual del entorno físico, asegurar que las decisiones respeten las restricciones de seguridad física y coordinar el avance del ciclo:

$$\text{Observar} \longrightarrow \text{Interpretar} \longrightarrow \text{Decidir} \longrightarrow \text{Actuar} \longrightarrow \text{Verificar} \longrightarrow \text{Registrar} \longrightarrow \text{Mejorar}$$

### Sus funciones esenciales son:
1. **Mantener la representación del estado del entorno:** Saber con certeza qué ocurre en el espacio físico (ej. en la caseta: vehículo presente en sensor, placa leída `XYZ-789`, estado de la barrera: cerrada/subiendo/abierta, autorización vigente).
2. **Garantizar la seguridad física (`Safety Enforcement`):** Actuar como guardián de condiciones físicas no negociables (ej. no bajar la barrera si la fotocelda detecta que el auto está debajo; no abrir si el sistema está en paro de emergencia).
3. **Coordinar el flujo:** Conectar la información interpretada por `VIGIA_Vision`, las reglas de decisión de `VIGIA_Automation` y las órdenes físicas de `VIGIA_IoT`.
4. **Verificar el resultado en lazo cerrado:** Contrastar la orden enviada con la confirmación sensorial del entorno antes de dar por completada la acción.
5. **Definir los modelos canónicos de dominio y contratos de persistencia:** Modelos inmutables (`VehicleDetection`, `AccessRecord`) e interfaces abstractas mínimas para guardar eventos y auditoría (`IRepository`, `IAuditLogger`).

> **Delimitación Crítica:**  
> `VIGIA_Core` **no contiene motores de inferencia de IA** (YOLO/PyTorch), **no maneja conexiones seriales ni pines de hardware**, **no incluye rutas HTTP/web** ni **se acopla a un motor de base de datos específico**.

---

## 2. Componentes Previstos (Fase 3 del Roadmap)

* **State Manager (`Gestor de Estado del Entorno`):** Memoria activa del estado físico del sistema.
* **Safety Enforcer (`Guardián de Seguridad`):** Invariantes físicas de seguridad que protegen a vehículos, personas y equipos.
* **Domain Models (`Modelos de Dominio`):** Entidades canónicas de datos (`Vehicle`, `Plate`, `AccessEvent`, `DeviceStatus`).
* **Interfaces de Persistencia y Auditoría:** Contratos abstractos simples para almacenar la bitácora histórica y datos de mejora.
* **Configuration Manager (`Gestor de Configuración`):** Parámetros del entorno, tiempos y umbrales.

---

## 3. Estado Actual

> **IMPORTANTE:**  
> En esta etapa (**Fase 0**), este módulo permanece intencionalmente sin código de implementación.  
> Se desarrollará como parte de la construcción de capacidades en el Roadmap, tras concluir la auditoría técnica de `VR_Semaforo/`.
