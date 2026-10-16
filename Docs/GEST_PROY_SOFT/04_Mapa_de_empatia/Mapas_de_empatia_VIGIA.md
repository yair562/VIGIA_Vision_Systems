# Mapas de empatía — VIGÍA Vision Systems

**Proyecto:** VIGÍA Vision Systems  
**Área:** Diseño centrado en el usuario y análisis de necesidades  
**Estado:** Propuesta pendiente de validación  
**Fecha:** 16 de octubre de 2026

## Nota metodológica

Estos mapas son una interpretación analítica de los resultados disponibles de la
encuesta y de los requisitos vigentes. No son una transcripción literal de
testimonios. Las frases entre comillas del borrador se transformaron en
afirmaciones analíticas para no presentar testimonios inventados.

Cada punto utiliza una etiqueta:

- **[ED] Evidencia directa:** se encuentra explícitamente en la encuesta o en un
  requisito vigente.
- **[IR] Interpretación razonable:** se deriva de la evidencia, pero no fue
  expresada literalmente por una persona entrevistada.
- **[HP] Hipótesis pendiente:** requiere validación con usuarios, observación o
  una nueva encuesta.

La encuesta disponible no identifica formalmente estos roles ni confirma el uso
de una tablet. Por ello, los perfiles y las afirmaciones específicas de
operación se consideran propuestas de diseño, no perfiles estadísticamente
validados.

---

## Mapa de empatía 1: Administrador del sistema

**Perfil propuesto:** Persona responsable de consultar, administrar y
supervisar la información de vehículos y eventos de VIGÍA.  
**Estado del perfil:** Hipótesis pendiente de validación.  
**Relación con el alcance:** RF-07, RF-08 y RF-12 a RF-15; RNF-01, RNF-02,
RNF-06, RNF-07 y RNF-11.

### 1. Lo que dice

- **[IR]** Necesita consultar los registros de acceso para conocer qué
  vehículos fueron detectados y cuándo ocurrió el evento.
- **[IR]** Espera que la información de los vehículos esté organizada y sea
  fácil de localizar.
- **[IR]** Necesita identificar si un vehículo coincide con un registro de
  autorización o requiere una revisión adicional.
- **[ED]** La encuesta muestra que el 36.7 % de los participantes considera
  preocupante no contar con un registro confiable de entradas y salidas.
- **[ED]** El 46 % eligió consultar toda la información disponible sobre los
  vehículos registrados.

### 2. Lo que piensa

- **[IR]** Considera que disponer de registros organizados facilita la
  supervisión y la revisión de incidentes.
- **[IR]** Puede preocuparse de que la falta de información confiable dificulte
  determinar si un acceso fue legítimo.
- **[IR]** Espera que los datos de vehículos y eventos sean consistentes y
  permitan consultas sin confusiones.
- **[ED]** Los requisitos establecen que debe distinguirse entre un vehículo
  sin autorización coincidente y un evento en el que no fue posible leer la
  matrícula (RF-11).
- **[HP]** Debe validarse qué operaciones puede realizar este perfil y qué
  información puede consultar o modificar según su rol.

### 3. Lo que siente

- **[IR]** Puede sentir preocupación ante la posibilidad de que un acceso
  irregular no quede registrado correctamente.
- **[IR]** Puede necesitar confianza en la información utilizada para
  supervisar las operaciones.
- **[IR]** Puede experimentar inquietud cuando no dispone de evidencia
  suficiente para aclarar un incidente.
- **[ED]** El 63.2 % de los participantes indicó sentirse muy inseguro o poco
  seguro respecto al control actual de vehículos.
- **[IR]** Puede sentir mayor tranquilidad cuando consulta registros claros y
  puede dar seguimiento a los eventos.

### 4. Lo que hace

- **[ED]** El alcance funcional contempla consultar eventos y la información
  disponible de los vehículos relacionados (RF-12).
- **[ED]** Puede filtrar registros por criterios habilitados, incluyendo fecha
  y matrícula cuando estén disponibles (RF-13).
- **[ED]** Puede administrar registros de vehículos si cuenta con la
  autorización correspondiente (RF-07 y RF-08).
- **[IR]** Revisa los datos relacionados con un evento cuando necesita aclarar
  una situación.
- **[HP]** Debe validarse si también administra usuarios, permisos, alertas o
  políticas de conservación de datos; esas tareas no están definidas
  explícitamente en los RF.

---

## Mapa de empatía 2: Guardia de seguridad

**Perfil propuesto:** Persona que supervisa físicamente el acceso vehicular y
utiliza el sistema como apoyo para revisar la información disponible.  
**Estado del perfil:** Hipótesis pendiente de validación.  
**Relación con el alcance:** RF-02, RF-03, RF-09 a RF-15; RNF-01, RNF-02,
RNF-06, RNF-11, RNF-13 y RNF-15.

> El uso de una tablet se conserva como contexto propuesto del perfil, pero no
> se presenta como una capacidad aprobada ni como un dato comprobado por la
> encuesta.

### 1. Lo que dice

- **[IR]** Necesita saber si el vehículo que se presenta coincide con una
  autorización registrada.
- **[IR]** Espera que la información se muestre de manera clara para revisarla
  oportunamente.
- **[IR]** Necesita identificar un vehículo sin autorización coincidente y
  conocer la información disponible del evento.
- **[IR]** Puede preferir consultar los datos del vehículo y del evento sin
  cambiar innecesariamente entre pantallas.
- **[ED]** El 98 % de los participantes consideró importante o muy importante
  recibir una alerta ante un vehículo no autorizado.

### 2. Lo que piensa

- **[IR]** Considera que una identificación incorrecta puede provocar
  confusiones durante el control de acceso.
- **[IR]** Necesita distinguir rápidamente entre un vehículo autorizado, uno
  sin coincidencia y un caso en el que la matrícula no pudo leerse.
- **[IR]** Espera que las alertas correspondan a situaciones que realmente
  requieren atención.
- **[IR]** Puede preocuparse de que una demora del sistema dificulte atender
  oportunamente los vehículos.
- **[ED]** RF-11 exige diferenciar un vehículo sin autorización coincidente de
  un evento sin matrícula identificable.
- **[HP]** Debe validarse si conserva la decisión final de permitir o rechazar
  el acceso y cuál es el procedimiento cuando la información es insuficiente.

### 3. Lo que siente

- **[IR]** Puede sentir responsabilidad por verificar correctamente los
  vehículos que se presentan en el acceso.
- **[IR]** Puede experimentar preocupación ante la posibilidad de dejar pasar
  un vehículo sin autorización.
- **[IR]** Puede sentir frustración cuando la información es confusa,
  incompleta o tarda en aparecer.
- **[IR]** Puede sentir presión cuando debe mantener la vigilancia y atender
  varias situaciones al mismo tiempo.
- **[IR]** Puede sentir mayor confianza cuando contrasta la información del
  sistema con lo que observa directamente.
- **[ED]** El 61.2 % relacionó las cámaras inteligentes con protección y
  tranquilidad, aunque la encuesta no preguntó específicamente a guardias.

### 4. Lo que hace

- **[HP]** Observa el vehículo que se presenta en el acceso y consulta la
  información disponible en la interfaz; debe confirmarse mediante observación.
- **[ED]** Consulta la matrícula, la fecha, la hora y la evidencia visual cuando
  esos datos están disponibles en el evento de alerta (RF-15).
- **[ED]** Contrasta la matrícula identificada con los registros de vehículos
  autorizados mediante la lógica prevista en RF-09 y RF-10.
- **[ED]** Revisa las alertas visuales generadas cuando se cumplen las
  condiciones configuradas (RF-14).
- **[HP]** Solicita apoyo o aplica un procedimiento manual cuando no puede
  confirmar la autorización; el procedimiento no está definido en los RF.
- **[HP]** No se confirma que opere barreras, sensores, semáforos o comandos
  IoT; esas capacidades no forman parte de los requisitos funcionales vigentes.

---

## Observaciones para validación

1. Confirmar si “Administrador del sistema” y “Guardia de seguridad” son roles
   reales del proyecto o si deben sustituirse por “personal autorizado de
   supervisión”, que es la denominación utilizada en los RF.
2. Confirmar si el guardia utilizará una tablet y cuáles serán sus permisos.
3. Definir la regla operativa para considerar un vehículo autorizado, así como
   quién puede crear, actualizar o revocar esa autorización.
4. Definir qué canal de alerta se aprobará. Los RF actuales solo establecen
   una alerta visual.
5. Validar mediante entrevistas u observación las afirmaciones marcadas como
   **[HP]**.
6. Mantener separadas las preocupaciones del usuario de las capacidades
   técnicas todavía no aprobadas, como apertura automática, sensores o IoT.
