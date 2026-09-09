# VIGIA Vision Systems

## 04 — Estándares y Convenciones de Desarrollo

**Estado:** Activo / Fase 0  
**Versión:** 1.0  
**Propósito:** Establecer los lineamientos de codificación, convenciones de Git, gestión de configuración, logging, pruebas y disciplina técnica para garantizar la calidad, mantenibilidad y legibilidad del código de VIGIA Vision Systems.

---

# 1. Filosofía y Principio Arquitectónico Global — OBLIGATORIO

VIGIA se rige por un principio de ingeniería riguroso: **claridad, modularidad y robustez antes que optimización prematura o complejidad innecesaria**.

### 1.1 El Principio Rector

Toda decisión de diseño, arquitectura, documentación o implementación debe seguir:

```text
IDEA DE VIGIA
     ↓
NECESIDAD REAL
     ↓
¿QUÉ DEBE HACER EL SISTEMA?
     ↓
COMPONENTE MÍNIMO NECESARIO
     ↓
INTEGRACIÓN CON VIGIA
     ↓
IMPLEMENTACIÓN SIMPLE
```

**NUNCA seguir el antipatrón:**

```text
TECNOLOGÍA INTERESANTE
     ↓
"¿DÓNDE LA METEMOS?"
     ↓
NUEVO SUBSISTEMA
     ↓
NUEVO PROCESO
     ↓
NUEVAS DEPENDENCIAS
     ↓
COMPLEJIDAD
     ↓
VIGIA SE ALEJA DE SU PROPÓSITO
```

### 1.2 Regla de Mínima Complejidad Suficiente

VIGIA debe implementar la **solución mínima suficiente** para resolver correctamente una necesidad real, manteniendo interfaces claras y capacidad razonable de evolución.

**Queda estrictamente prohibido agregar:**
* Microservicios innecesarios.
* Brokers o colas de mensajería externas sin necesidad.
* Capas artificiales o abstracciones prematuras.
* Patrones de diseño por moda.
* Bases de datos adicionales sin justificación.
* Procesos de sincronización innecesarios o sistemas de auditoría excesivos.
* Infraestructura distribuida sin una necesidad real.
* Tecnologías únicamente para demostrar que fueron utilizadas.

> Si una necesidad puede resolverse correctamente dentro de un componente existente, **NO crees otro componente**. La complejidad debe estar plenamente justificada por una necesidad concreta.

### 1.3 Filtro de las Tecnologías (Las 6 Preguntas Obligatorias)

Para cada tecnología propuesta (especialmente en IA, Machine Learning, Blockchain, BI, IoT o Robótica), se debe responder primero:

1. ¿Qué necesidad real de VIGIA resuelve?
2. ¿Qué problema concreto evita o mejora?
3. ¿Puede resolverse con la infraestructura existente?
4. ¿Cuál es la implementación mínima?
5. ¿Qué complejidad adicional introduce?
6. ¿Esa complejidad está justificada?

Si una tecnología no aporta suficiente valor demostrable, **NO se introduce**. No se asume que deben convertirse en subsistemas independientes por formar parte de requisitos académicos; los requisitos académicos deben resolverse de la forma más natural y mínima posible dentro del sistema.

### 1.4 Regla del Flujo Simple

El sistema debe preservar siempre el flujo conceptual directo:

$$\text{PERCEPCIÓN} \longrightarrow \text{ESTADO / CONTEXTO} \longrightarrow \text{DECISIÓN} \longrightarrow \text{ACCIÓN} \longrightarrow \text{RESULTADO} \longrightarrow \text{REGISTRO}$$

No se introducen etapas intermedias salvo justificación explícita.

### 1.5 Regla Contra el God Module

La simplicidad **no significa concentrar todo en `VIGIA_Core`**. Si una responsabilidad pertenece claramente a Visión, Automatización o Hardware IoT, debe residir allí. El equilibrio del sistema es:

$$\text{Responsabilidad Clara} + \text{Componente Suficiente} + \text{Bajo Acoplamiento} + \text{Baja Complejidad}$$

### 1.6 Máxima Final del Proyecto

> **"VIGIA debe crecer en capacidad, no en complejidad gratuita."**

---

# 2. Estilo de Código Python

* **Estándar:** Cumplimiento de **PEP 8** en todo el código Python.
* **Tipado estático (Type Hints):** Uso obligatorio de anotaciones de tipo (`typing` estándar de Python 3.10+) en todas las firmas de funciones, métodos y atributos de clase:
  ```python
  def calculate_traffic_density(vehicle_count: int, zone_area_m2: float) -> float:
      if zone_area_m2 <= 0:
          raise ValueError("zone_area_m2 debe ser estrictamente positivo.")
      return vehicle_count / zone_area_m2
  ```
* **Longitud de línea:** Límite máximo sugerido de 88 a 100 caracteres por línea.
* **Docstrings:** Documentación obligatoria en clases y métodos públicos siguiendo el formato estándar de Google o NumPy docstrings, explicando propósito, argumentos (`Args`), retorno (`Returns`) y posibles excepciones (`Raises`).
* **Imports:** Ordenados según PEP 8:
  1. Biblioteca estándar de Python.
  2. Dependencias externas de terceros instaladas (p. ej. `pydantic`, `numpy`).
  3. Módulos internos del proyecto (imports absolutos preferidos sobre relativos).

---

# 3. Convenciones de Nombres (`Naming Conventions`)

* **Módulos y paquetes:** Minúsculas y guiones bajos (`snake_case`): `event_bus.py`, `video_stream.py`.
* **Clases y Tipos:** Notación PascalCase: `TrafficSignalController`, `DetectionEvent`, `SerialAdapter`.
* **Interfaces y Clases Base Abstractas:** Prefijo `I` o sufijo `Base`/`Interface`: `IVisionDetector`, `BaseCommunicationAdapter`.
* **Funciones y Métodos:** Minúsculas y guiones bajos (`snake_case`): `process_frame()`, `publish_event()`, `get_active_devices()`.
* **Variables y Atributos:** Minúsculas y guiones bajos (`snake_case`): `current_state`, `camera_fps`.
* **Constantes:** Mayúsculas con guiones bajos (`UPPER_CASE`): `DEFAULT_TIMEOUT_SECONDS = 5.0`, `MAX_RETRY_ATTEMPTS = 3`.
* **Variables privadas o protegidas:** Prefijo con guion bajo simple: `_serial_connection`, `_internal_cache`.

---

# 4. Convenciones de Carpetas y Paquetes (`Folder Conventions`)

* Cada módulo de primer nivel (`VIGIA_Core`, `VIGIA_Vision`, etc.) funciona como un paquete modular aislado.
* Cuando se comience la implementación, cada paquete contendrá un archivo `__init__.py` que expondrá únicamente su API pública mediante `__all__`.
* Los recursos estáticos, plantillas, configuraciones de ejemplo o firmwares deben residir en subcarpetas dedicadas dentro del módulo correspondiente (p. ej. `firmware/` dentro de `VIGIA_IoT/`).
* Todo módulo contará con su respectivo subdirectorio de pruebas dentro de `tests/` reflejando la misma estructura interna.

---

# 5. Fronteras de Módulos (`Module Boundaries`)

* **Regla de Dependencia Unidireccional:**
  * Los módulos de la periferia (`VIGIA_Vision`, `VIGIA_IoT`, `VIGIA_Automation`, `VIGIA_API`, `VIGIA_Dashboard`) solo pueden depender e importar contratos, interfaces y eventos definidos en `VIGIA_Core`.
  * `VIGIA_Core` **nunca** debe importar código de ningún módulo periférico.
* **Prohibición de Dependencias Circulares:**
  * Queda estrictamente prohibido que `VIGIA_Vision` importe directamente código de `VIGIA_IoT`, o que `VIGIA_API` interactúe directamente con librerías de hardware sin pasar por el núcleo.

---

# 6. Convenciones de Git y Control de Versiones

### 6.1 Mensajes de Commit (Conventional Commits)
Los commits deben seguir el estándar de commits semánticos en formato imperativo:
```text
<tipo>(<alcance opcional>): <descripción breve en presente>

[cuerpo opcional con detalles y justificación del cambio]
```
* **Tipos principales:**
  * `feat:` Nueva funcionalidad o capacidad.
  * `fix:` Corrección de un bug o fallo.
  * `docs:` Cambios exclusivamente en documentación.
  * `refactor:` Modificación de código que no altera el comportamiento externo.
  * `test:` Adición o corrección de pruebas automatizadas.
  * `chore:` Tareas de mantenimiento, dependencias o configuración de build.
  * `arch:` Cambios en la estructura arquitectónica o contratos base.

### 6.2 Estrategia de Ramas
* `main`: Rama principal de producción, siempre estable y desplegable.
* `develop`: Rama integradora del desarrollo activo.
* `feature/<nombre-feature>`: Ramas de características específicas (p. ej. `feature/event-bus`, `feature/camera-rtsp`).
* `fix/<nombre-bug>`: Ramas para resolución de incidencias.

---

# 7. Variables de Entorno y Secretos (`Environment Variables`)

* **Cero Secretos en el Repositorio:** Jamás se deben subir al control de versiones contraseñas, tokens de autenticación, llaves privadas, IPs sensibles o rutas absolutas de máquinas locales.
* **Archivo `.env`:** Toda variable de entorno debe residir en un archivo local `.env`, el cual debe estar explícitamente ignorado en `.gitignore`.
* **Archivo de plantilla `.env.example`:** Se mantendrá en la raíz un archivo de ejemplo con valores ficticios y comentarios explicativos para facilitar la incorporación de nuevos colaboradores.

---

# 8. Gestión de Configuración (`Configuration Management`)

* **Configuración declarativa:** Los parámetros del sistema (umbrales de detección, zonas de interés, tiempos de semáforo, puertos serie) se almacenarán en archivos estructurados (`.yaml` o `.json`).
* **Acceso tipado:** La configuración se consumirá en código a través de clases tipadas y validadas (como modelos de configuración basados en Pydantic o dataclasses), evitando el acceso inseguro mediante diccionarios genéricos (`config["key"]`).
* **Cero Hardcoding:** Se prohíbe escribir constantes de entorno directamente en el código fuente.

---

# 9. Logging y Observabilidad (`Logging`)

* **Prohibición expresa de `print()`:** Queda terminantemente prohibido utilizar sentencias `print()` para diagnóstico o flujo en código de producción.
* **Módulo estándar `logging`:** Todo mensaje debe emitirse a través del logger estándar de Python configurado para el módulo:
  ```python
  import logging

  logger = logging.getLogger(__name__)

  logger.info("Iniciando captura de video en stream: %s", stream_url)
  logger.warning("Caída de cuadros detectada en cámara %s. FPS actual: %d", camera_id, fps)
  logger.error("Fallo de comunicación con microcontrolador en puerto %s", port, exc_info=True)
  ```
* **Niveles de severidad:**
  * `DEBUG`: Diagnóstico detallado para desarrollo e investigación interna.
  * `INFO`: Eventos rutinarios de operación normal (conexión de dispositivo, inicio de servicio).
  * `WARNING`: Anomalías no fatales o degradación transitoria (reintentos, latencia alta).
  * `ERROR`: Fallas en una operación específica que no detienen el sistema completo.
  * `CRITICAL`: Condiciones catastróficas que impiden la operación segura del sistema.

---

# 10. Manejo de Errores y Excepciones (`Error Handling`)

* **Jerarquía de Excepciones Propias:** Cada módulo definirá su jerarquía de excepciones heredando de una clase base común del proyecto (`VIGIAException`):
  ```python
  class VIGIAException(Exception):
      """Excepción base para todos los errores de VIGIA."""
      pass

  class HardwareCommunicationError(VIGIAException):
      """Fallo de comunicación con un dispositivo físico o microcontrolador."""
      pass
  ```
* **No silenciar errores:** Queda prohibido el uso de bloques `except Exception: pass` sin registro o relanzamiento.
* **Operación a prueba de fallos (`Fail-safe`):** Si un subsistema crítico (visión o IoT) falla, el sistema debe transicionar a un estado de seguridad degradado (p. ej. semáforo en modo intermitente ámbar/rojo seguro) antes de fallar de manera silenciosa o impredecible.

---

# 11. Filosofía de Pruebas (`Testing Philosophy`)

* **Testeabilidad sin hardware físico:** Ninguna prueba automatizada debe depender de que una placa Arduino o una cámara física estén conectadas al equipo de desarrollo. Se emplearán mocks, fixtures y datos grabados.
* **Tipología de pruebas:**
  * **Unitarias (`Unit Tests`):** Pruebas aisladas y ultrarrápidas de métodos, algoritmos y reglas lógicas.
  * **Integración (`Integration Tests`):** Validación de la interacción entre módulos (p. ej. emisión de un evento en `VIGIA_Core` y reacción en `VIGIA_Automation`).
  * **Contratos (`Contract Tests`):** Validación de que los mensajes y esquemas cumplen las especificaciones acordadas.
* **Herramienta:** Se adoptará `pytest` como framework oficial de pruebas del proyecto.

---

# 12. Estándares de Documentación

* Todo cambio arquitectónico o modificación a un contrato entre módulos debe reflejarse en los documentos de `Docs/`.
* El código fuente debe ser autodocumentado mediante nombres claros y expresivos; los comentarios deben responder al **por qué** se tomó una decisión y no al **qué** hace la instrucción elemental.

---

# 13. Gestión de Dependencias (`Dependency Management`)

* **Aislamiento en entornos virtuales:** Todo desarrollo debe ejecutarse dentro de un entorno virtual dedicado (`.venv`).
* **Requisitos explícitos y limpios:** Se mantendrán archivos de requerimientos con versiones acotadas para evitar incompatibilidades en compilaciones futuras.
* **No sobrecargar con librerías innecesarias:** Antes de agregar una nueva dependencia externa al proyecto, se debe evaluar si la funcionalidad puede resolverse con la biblioteca estándar o si el impacto en peso y seguridad se justifica.
