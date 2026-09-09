# VIGIA_Automation

**Subsistema de Reglas de Negocio, Políticas Operativas y Toma de Decisiones**

---

## 1. Responsabilidad del Módulo

`VIGIA_Automation` es el subsistema encargado de la fase de **Decidir** en VIGIA:
$$\text{Observar} \longrightarrow \text{Interpretar} \longrightarrow \mathbf{DECIDIR} \longrightarrow \text{Actuar} \longrightarrow \text{Verificar} \longrightarrow \text{Registrar} \longrightarrow \text{Mejorar}$$

Su función es evaluar la información interpretada del entorno físico frente a un conjunto de reglas y políticas de negocio para determinar **qué debe suceder**:

### Ejemplo en la Caseta Inteligente:
* **Regla 1:** *SI la placa del vehículo está en la lista de autorizados Y el acceso está dentro del horario permitido $\to$ AUTORIZAR APERTURA.*
* **Regla 2:** *SI el vehículo no está registrado o la placa es desconocida $\to$ MANTENER CERRADA y solicitar registro al guardia/dashboard.*
* **Regla 3:** *SI el sensor de despeje confirma que el vehículo cruzó $\to$ ORDENAR CIERRE seguro de la barrera.*
* **Regla 4 (Seguridad):** *SI la fotocelda detecta un obstáculo debajo de la barrera $\to$ CANCELAR CIERRE de inmediato.*

---

## 2. Componentes Previstos (Fase 3 del Roadmap)

* **Rules Engine (`Motor de Reglas`):** Evaluador determinista de condiciones lógicas y comparaciones sobre el estado del entorno.
* **Access Policies (`Políticas de Acceso`):** Criterios de autorización según listas de placas, roles (residentes, visitantes, servicios de emergencia) y horarios.
* **Operational Modes (`Modos Operativos`):** Lógica para alternar entre modo automático, modo supervisado por guardia, modo libre (barrera abierta en eventos) o modo contingencia.
* **Timers & Delays (`Temporizadores`):** Tiempos de tolerancia antes de alertas por vehículo detenido o barrera trabada.

> **Delimitación con el Core:**  
> `VIGIA_Automation` **evalúa las reglas del negocio**, pero no maneja directamente la conexión serial con motores ni almacena el estado físico maestro; esa orquestación y validación de invariantes de seguridad pertenece a `VIGIA_Core`.

---

## 3. Estado Actual

> **IMPORTANTE:**  
> En esta etapa (**Fase 0**), este módulo permanece intencionalmente sin código de implementación.  
> Se desarrollará en la Fase 3 del Roadmap para habilitar la capacidad de decidir y autorizar accesos.
