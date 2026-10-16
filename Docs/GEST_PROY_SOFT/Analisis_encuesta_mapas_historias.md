# Análisis de encuesta, mapas de empatía e historias de usuario

**Proyecto:** VIGÍA Vision Systems  
**Tipo de documento:** Análisis de trazabilidad y propuesta para validación  
**Fecha del análisis:** 16 de octubre de 2026  
**Estado:** Propuesta; no sustituye los documentos oficiales de requisitos

> Este documento es un análisis nuevo. No modifica ni sobrescribe la encuesta, los
> requisitos, el mapa de empatía ni las historias de usuario existentes.

## 1. Inventario de fuentes consultadas

| Fuente | Versión/fecha disponible | Uso en el análisis | Limitaciones o discrepancias |
|---|---|---|---|
| `03_Requerimientos_funcionales_no_funcionales/Resultados_Encuesta.md` | v1.0, 16 de octubre de 2026 | Frecuencias, porcentajes y respuestas cualitativas reportadas | No contiene el export de respuestas individuales. Varias frecuencias son aproximadas y algunas categorías no tienen porcentaje desglosado. |
| `03_Requerimientos_funcionales_no_funcionales/Requerimientos_funcionales.md` | v1.2, 14 de octubre de 2026 | Alcance funcional aprobado para la versión 1 | Define RF-01 a RF-15; el README general todavía menciona RF-01 a RF-13. |
| `03_Requerimientos_funcionales_no_funcionales/Requerimientos_no_funcionales.md` | v1.2, 23 de septiembre de 2026 | Restricciones de seguridad, integridad, consulta, rendimiento y operación | No asigna métricas cuantitativas para rendimiento, disponibilidad o recuperación. |
| `03_Requerimientos_funcionales_no_funcionales/Requisitos_legales_y_cumplimiento.md` | v1.0, 22 de septiembre de 2026 | Restricciones de privacidad, aviso, señalización y protección de datos | Las obligaciones se asignan principalmente a la institución responsable del tratamiento. |
| `04_Mapa_de_empatia/Mapa_de_Empatia.pdf` | Archivo existente, 2 páginas; fecha del archivo 22 de septiembre de 2026 | Revisión del mapa vigente | El artefacto contiene más de cuatro áreas de análisis; debe reestructurarse para cumplir la regla de cuatro cuadrantes. |
| `04_Mapa_de_empatia/README.md` | Estado: en desarrollo | Confirmación de los temas incluidos en el mapa vigente | Enumera “ve”, “oye”, “esfuerzos/frustraciones” y “resultados/deseos”, además de los cuadrantes solicitados. |
| `06_Historias_de_usuario/Historias_de_usuario.md` | v1.0, 21 de septiembre de 2026 | Comparación con las historias existentes | HU-02, HU-03 y HU-05 introducen barrera, sensores, semáforo, Core, IoT y apertura manual sin referencia a RF vigente. |

### 1.1. Búsqueda de la fuente original de la encuesta

Se revisaron los nombres y contenidos disponibles dentro del repositorio. No se
encontró un archivo CSV, XLSX, formulario exportado, base de respuestas ni
documento con las respuestas individuales. Por tanto, las afirmaciones
estadísticas de este análisis se limitan a lo publicado en
`Resultados_Encuesta.md`. Las frecuencias marcadas como aproximadas no deben
tratarse como conteos auditados.

## 2. Síntesis verificable de los resultados de la encuesta

La compilación indica 49 respuestas para las preguntas 1 a 7 y 50 para las
preguntas 8 a 10.

| Pregunta | Resultado reportado | Lectura sustentada |
|---|---|---|
| 1. Utilidad del sistema | 37/49, 75.5 %: “Definitivamente sí”; 12/49, 24.5 %: “Tal vez”; 0: “No lo creo” | Hay aceptación inicial favorable, pero no equivale a aprobación del producto ni a intención de uso. |
| 2. Edad | 14/49, 28.6 %: 18-21; 15/49, 30.6 %: 22-28; 14/49, 28.6 %: 43 o más; dos rangos intermedios sin frecuencia separada | La distribución completa no puede reconstruirse con exactitud. No se usará para definir perfiles funcionales. |
| 3. Género | 26/49, 53.1 %: hombre; 23/49, 46.9 %: mujer | Describe la muestra, pero no determina roles ni permisos del sistema. |
| 4. Seguridad del control actual | 11/49, 22.4 %: muy inseguro; 20/49, 40.8 %: poco seguro; 16/49, 32.7 %: neutral; 2/49, 4.1 %: seguro; 0: muy seguro | 31/49, 63.2 %, reportan una percepción baja de seguridad. |
| 5. Principal preocupación | 24/49, 49 %: vigilancia insuficiente; 18/49, 36.7 %: falta de registro confiable; 7/49, 14.3 %: dificultad para identificar visitas, proveedores o inquilinos | Las necesidades más fuertes son detectar y conservar trazabilidad; identificar personas específicas es una preocupación minoritaria en esta muestra. |
| 6. Sensación ante cámaras inteligentes | 30/49, 61.2 %: protección y tranquilidad; 14/49, 28.6 %: control y orden; 5 respuestas restantes agrupadas sin porcentaje exacto | La asociación predominante es positiva, pero existe un grupo con indiferencia, duda o miedo que requiere consideración de privacidad y comunicación. |
| 7. Espacio de mayor utilidad | 23/49, 46.9 %: casa/residencia; 12/49, 24.5 %: institución/escuela/negocio; 10/49, 20.4 %: fraccionamiento/condominio; 4/49, 8.2 %: trabajo/oficina | La residencia es el escenario más mencionado, no una decisión de despliegue aprobada. |
| 8. Información útil | 23/50, 46 %: toda la información anterior; 14/50, 28 %: placa; 8/50, 16 %: fecha y hora; 5 respuestas agrupadas para imagen, marca, color o historial, sin porcentaje exacto | Existe interés por una consulta integral; debe distinguirse la información efectivamente recolectada de la que solo se desea consultar. |
| 9. Alertas | 32/50, 64 %: muy importante; 17/50, 34 %: importante; 1 respuesta restante: poco o nada importante, sin desglose adicional | 49/50, 98 %, valora las alertas como importantes o muy importantes. No define canal, destinatario ni regla de autorización. |
| 10. Característica adicional | 50 respuestas; se mencionan “Ninguna” y comentarios adicionales, sin desglose | No es válido priorizar una funcionalidad adicional con esta fuente. |

### 2.1. Hallazgos principales

1. La preocupación más respaldada es la vigilancia insuficiente: 24 de 49
   respuestas, 49 %.
2. La segunda preocupación es la pérdida de trazabilidad de entradas y salidas:
   18 de 49 respuestas, 36.7 %.
3. La percepción actual de seguridad es baja o muy baja para 31 de 49
   participantes, 63.2 %.
4. Las alertas ante vehículos no autorizados tienen la mayor prioridad
   declarada: 49 de 50 respuestas, 98 %, sumando “importante” y “muy
   importante”.
5. La utilidad percibida y la sensación de protección son señales de
   aceptación inicial, no evidencia de que todos los participantes sean
   operadores, administradores o conductores autorizados.

## 3. Perfiles de usuario respaldados por la evidencia

### Perfil P-01: Usuario del entorno protegido

- **Evidencia directa:** Los participantes respondieron sobre su hogar,
  fraccionamiento, trabajo o institución; 23 de 49 señalaron una residencia
  como el espacio de mayor utilidad.
- **Interpretación razonable:** Este perfil representa a la persona que espera
  mayor seguridad y visibilidad sobre los accesos de su entorno.
- **Hipótesis pendiente:** No se sabe si esta persona será quien consulte el
  sistema, si tendrá una cuenta, ni si será residente, visitante, trabajador o
  responsable del sitio.
- **No se infiere:** Un permiso concreto, una identidad, una edad objetivo ni
  una necesidad de apertura automática.

### Perfil P-02: Personal autorizado de supervisión

- **Evidencia directa:** Los RF vigentes requieren mostrar información al
  “personal autorizado” y administrar vehículos y eventos.
- **Interpretación razonable:** Para operar la consulta, administración y
  atención de alertas se necesita un perfil con acceso controlado.
- **Hipótesis pendiente:** La encuesta no preguntó por puesto, frecuencia de
  operación, turnos, volumen de eventos, roles internos ni canal preferido de
  alerta.
- **No se infiere:** Que este perfil sea guardia, administrador de accesos,
  auditor o propietario; esos nombres requieren validación del equipo.

El conductor autorizado, el administrador de accesos y el operador de guardia
que aparecen en las historias existentes no quedan demostrados como perfiles
de la encuesta. Pueden mantenerse como hipótesis de diseño del caso rector,
pero no como perfiles validados por esta evidencia.

## 4. Mapas de empatía

### 4.1. Mapa P-01 — Usuario del entorno protegido

Los marcadores distinguen la fuerza de cada afirmación:

- **[ED] Evidencia directa:** aparece explícitamente en los resultados.
- **[IR] Interpretación razonable:** deriva del patrón de resultados, sin ser una
  frase textual de un participante.
- **[HP] Hipótesis pendiente:** requiere entrevistas, observación o una nueva
  encuesta.

#### Lo que dice

- **[ED]** El 75.5 % considera que un sistema como VIGÍA definitivamente sería
  útil para su entorno.
- **[ED]** El 49 % identifica la vigilancia insuficiente como la principal
  preocupación.
- **[ED]** El 36.7 % señala la falta de un registro confiable de entradas y
  salidas.
- **[IR]** Es razonable interpretar que espera mejorar la visibilidad de los
  accesos, pero no se dispone de una cita textual individual.

#### Lo que piensa

- **[IR]** Puede considerar insuficiente el control actual cuando no existe
  evidencia consultable de quién entró o salió.
- **[IR]** Puede valorar una consulta que reúna placa, fecha, hora e imagen
  cuando esos datos estén disponibles.
- **[HP]** Debe validarse si espera consultar directamente el sistema o solo
  recibir información del personal autorizado.

#### Lo que siente

- **[ED]** El 63.2 % se siente muy inseguro o poco seguro sobre el control
  actual de vehículos.
- **[ED]** El 61.2 % asocia las cámaras inteligentes con protección y
  tranquilidad.
- **[ED]** Una parte de las respuestas se agrupó como indiferencia, duda o
  miedo, pero no se publicó su desglose exacto.
- **[IR]** La seguridad percibida puede mejorar si el sistema ofrece
  información comprensible, sin eliminar las preocupaciones de privacidad.

#### Lo que hace

- **[ED]** Responde sobre accesos en hogares, fraccionamientos, trabajos e
  instituciones, y prioriza la residencia como escenario de utilidad.
- **[IR]** Puede buscar confirmación de un acceso o de un vehículo cuando
  necesita revisar un evento.
- **[HP]** No está demostrado que registre vehículos, consulte filtros o
  atienda alertas personalmente; debe observarse el proceso real.

### 4.2. Mapa P-02 — Personal autorizado de supervisión

Este mapa combina el alcance formal de los RF con las necesidades expresadas
por la muestra. El rol operativo exacto sigue pendiente de validación.

#### Lo que dice

- **[ED]** Los participantes priorizan detectar vehículos extraños o
  sospechosos (49 %) y conservar un registro confiable (36.7 %).
- **[ED]** El 98 % considera importante o muy importante recibir alertas ante
  vehículos no autorizados.
- **[IR]** El personal que atiende el sistema necesitaría información del evento
  que permita revisar la alerta, no solo un aviso sin contexto.

#### Lo que piensa

- **[IR]** Puede necesitar distinguir un vehículo sin coincidencia de un evento
  cuya matrícula no pudo leerse; esa distinción está prevista en RF-11.
- **[IR]** Puede priorizar una consulta filtrable para localizar eventos por
  fecha y matrícula.
- **[HP]** Debe validarse qué regla define “autorizado”, quién puede modificar
  vehículos y qué tiempo de atención se considera aceptable.

#### Lo que siente

- **[IR]** Puede experimentar presión cuando la vigilancia actual no permite
  confirmar un acceso o cuando una alerta carece de evidencia suficiente.
- **[IR]** Puede sentir mayor confianza si los registros son consistentes y la
  interfaz diferencia eventos ordinarios de los que requieren atención.
- **[HP]** No hay datos para afirmar emociones específicas de operadores,
  guardias o administradores.

#### Lo que hace

- **[ED]** El alcance vigente le asigna consultar eventos, consultar vehículos,
  filtrar registros y administrar vehículos.
- **[IR]** Puede revisar la evidencia visual y la fecha/hora asociadas a una
  alerta para decidir una acción operativa conforme a su autoridad.
- **[HP]** No está probado que abra barreras, opere sensores, use un semáforo o
  ejecute comandos IoT; esas actividades no están en los RF vigentes.

## 5. Matriz de trazabilidad entre hallazgos, necesidades y requisitos

| ID | Hallazgo de origen | Necesidad | Tipo de respaldo | Requisitos relacionados | Cobertura |
|---|---|---|---|---|---|
| H-01 | P4: 63.2 % se siente muy inseguro o poco seguro | Mejorar la visibilidad del control de accesos | Evidenciada; solución concreta pendiente de validar | RF-01, RF-02, RF-03, RF-11 | Parcial: cubre detección e identificación, pero no define una métrica de mejora percibida. |
| H-02 | P5: 49 % reporta vigilancia insuficiente | Detectar vehículos y diferenciar eventos sin autorización de matrículas ilegibles | Evidenciada | RF-01 a RF-03, RF-09 a RF-11 | Cubierta funcionalmente, sujeta a pruebas de visión y condiciones de captura. |
| H-03 | P5: 36.7 % reporta falta de registro confiable | Mantener trazabilidad consultable de los accesos | Evidenciada | RF-04 a RF-06, RF-12, RF-13; RNF-07 | Cubierta, pero faltan reglas de retención, volumen y disponibilidad. |
| H-04 | P8: 46 % elige toda la información disponible | Consultar la información disponible de un vehículo y evento | Evidenciada como preferencia | RF-05, RF-06, RF-12, RF-13, RF-15; RNF-11 | Parcial: marca, color e historial no están garantizados por RF; solo se muestran datos disponibles. |
| H-05 | P9: 98 % considera importantes las alertas | Recibir y atender alertas con contexto suficiente | Evidenciada | RF-10, RF-11, RF-14, RF-15; RNF-11 | Parcial: existe alerta visual, pero faltan destinatario, canal, prioridad y regla operativa. |
| H-06 | P6: 61.2 % asocia cámaras con protección y tranquilidad | Usar vigilancia sin exponer datos innecesarios | Interpretada con respaldo y restricción de privacidad | RNF-04, RNF-05, RNF-06, RNF-12; RLC-01 a RLC-06 | Parcial: las obligaciones institucionales y la configuración concreta aún deben definirse. |
| H-07 | P1 y P7: utilidad alta y preferencia por residencia | Validar el escenario de despliegue prioritario | Evidenciada como percepción, no como decisión | Pendiente de asignación | Sin requisito: requiere decisión de alcance y validación con responsables del sitio. |
| H-08 | P10: respuestas abiertas sin desglose | Evaluar características adicionales sin inventarlas | Insuficiente | Pendiente de asignación | Sin cobertura: se requiere el texto completo y codificación de respuestas. |

## 6. Propuesta de historias de usuario

Todas las historias siguientes son **propuestas pendientes de validación**. Se
derivan de necesidades con evidencia y se limitan a los RF, RNF y RLC vigentes.
Los criterios no agregan apertura de barrera, sensores, semáforos, IoT,
notificaciones externas ni otras capacidades que no estén aprobadas en dichos
catálogos.

### HU-AN-01 — Detectar e identificar un vehículo

- **Perfil:** Personal autorizado de supervisión (P-02).
- **Historia:** **Como** personal autorizado de supervisión, **quiero**
  disponer de la detección de vehículos y de la matrícula cuando la imagen
  permita leerla, **para** revisar si existe un registro de autorización.
- **Hallazgo o necesidad de origen:** H-01 y H-02; vigilancia insuficiente y
  necesidad de detectar vehículos.
- **Requisitos relacionados:** RF-01, RF-02, RF-03.
- **Criterios de aceptación:**
  1. **Dado** que una cámara configurada captura un acceso vehicular, **cuando**
     el sistema procesa la imagen, **entonces** registra la detección del
     vehículo conforme al resultado disponible.
  2. **Dado** que la matrícula es legible en la imagen, **cuando** finaliza el
     análisis, **entonces** el evento conserva la matrícula identificada.
  3. **Dado** que la matrícula no es legible, **cuando** finaliza el análisis,
     **entonces** el evento no se clasifica como matrícula identificada.
- **Prioridad:** Alta; la vigilancia insuficiente fue la preocupación más
  frecuente (49 %).
- **Estado:** Pendiente de validación.

### HU-AN-02 — Consultar un registro confiable de accesos

- **Perfil:** Personal autorizado de supervisión (P-02).
- **Historia:** **Como** personal autorizado de supervisión, **quiero**
  consultar eventos de acceso con fecha, hora y evidencia disponible, **para**
  reconstruir qué ocurrió en un acceso.
- **Hallazgo o necesidad de origen:** H-03 y H-04; registro confiable e interés
  por información integral.
- **Requisitos relacionados:** RF-04, RF-05, RF-06, RF-12, RF-13, RF-15.
- **Criterios de aceptación:**
  1. **Dado** un evento detectado, **cuando** termina su procesamiento,
     **entonces** se almacena con la fecha y hora correspondientes.
  2. **Dado** que existe evidencia visual asociada, **cuando** el personal
     autorizado consulta el evento, **entonces** puede visualizarla junto con
     la información disponible.
  3. **Dado** que el usuario proporciona un criterio habilitado, **cuando**
     ejecuta la consulta, **entonces** el sistema filtra por fecha o matrícula
     cuando ese dato esté disponible.
- **Prioridad:** Alta; 36.7 % reportó falta de registro confiable y 46 % eligió
  toda la información disponible.
- **Estado:** Pendiente de validación.

### HU-AN-03 — Administrar vehículos autorizados

- **Perfil:** Personal autorizado de supervisión (P-02).
- **Historia:** **Como** personal autorizado de supervisión, **quiero**
  registrar y actualizar los datos de vehículos y su estado de autorización,
  **para** que la comparación de accesos utilice información vigente.
- **Hallazgo o necesidad de origen:** H-02 y H-05; detectar vehículos y
  determinar coincidencias de autorización.
- **Requisitos relacionados:** RF-07, RF-08, RF-09, RF-10; RNF-07.
- **Criterios de aceptación:**
  1. **Dado** que el usuario tiene autorización para administrar vehículos,
     **cuando** registra una matrícula y su estado, **entonces** el sistema
     valida y almacena el registro.
  2. **Dado** un vehículo con matrícula identificada, **cuando** el sistema
     compara la matrícula con los registros, **entonces** determina si existe
     una autorización vigente conforme a los datos almacenados.
  3. **Dado** un dato que incumple una regla de integridad, **cuando** se intenta
     guardar, **entonces** el sistema rechaza la operación sin corromper los
     registros existentes.
- **Prioridad:** Alta; la alerta depende de una autorización registrada y
  vigente, aunque la encuesta no define el proceso administrativo.
- **Estado:** Pendiente de validación.

### HU-AN-04 — Revisar una alerta de vehículo sin autorización coincidente

- **Perfil:** Personal autorizado de supervisión (P-02).
- **Historia:** **Como** personal autorizado de supervisión, **quiero** recibir
  una alerta visual con el evento que la originó, **para** atender un vehículo
  sin coincidencia de autorización con información suficiente.
- **Hallazgo o necesidad de origen:** H-05; 98 % consideró importantes o muy
  importantes las alertas.
- **Requisitos relacionados:** RF-10, RF-11, RF-14, RF-15; RNF-11, RNF-15.
- **Criterios de aceptación:**
  1. **Dado** un evento cuya matrícula identificada no coincide con una
     autorización vigente, **cuando** se evalúan las condiciones configuradas,
     **entonces** el sistema genera una alerta visual.
  2. **Dado** que se genera una alerta, **cuando** el personal autorizado la
     consulta, **entonces** se muestra la matrícula, fecha, hora y evidencia
     visual cuando estén disponibles.
  3. **Dado** que no fue posible leer la matrícula, **cuando** se registra el
     evento, **entonces** el sistema lo diferencia de un vehículo identificado
     sin autorización coincidente.
- **Prioridad:** Alta; es el hallazgo cuantitativamente más fuerte (98 %).
- **Estado:** Pendiente de validación.

### HU-AN-05 — Acceder de forma controlada a información de vehículos y eventos

- **Perfil:** Personal autorizado de supervisión (P-02).
- **Historia:** **Como** personal autorizado, **quiero** acceder solo a las
  operaciones y registros que correspondan a mi rol, **para** consultar la
  información necesaria sin exponer datos protegidos.
- **Hallazgo o necesidad de origen:** H-06 y la necesidad de confianza y
  protección asociada a las cámaras.
- **Requisitos relacionados:** RNF-01, RNF-02, RNF-04, RNF-06, RNF-11, RNF-12;
  RLC-01 a RLC-06.
- **Criterios de aceptación:**
  1. **Dado** un usuario autenticado, **cuando** solicita una función
     restringida, **entonces** el sistema verifica su autorización antes de
     mostrar o modificar información.
  2. **Dado** un usuario sin permiso para un registro u operación, **cuando**
     intenta acceder, **entonces** el sistema impide el acceso.
  3. **Dado** un evento técnico, **cuando** se registra para diagnóstico,
     **entonces** no contiene contraseñas ni datos sensibles innecesarios.
- **Prioridad:** Media-alta; no es la preocupación más frecuente, pero es una
  condición de confianza y cumplimiento para operar los hallazgos anteriores.
- **Estado:** Pendiente de validación.

### 6.1. Historias existentes que requieren decisión

| Historia existente | Problema de trazabilidad | Decisión requerida |
|---|---|---|
| HU-01 | Es compatible en parte con RF-02 y RF-03, pero `ObservationEvent` e índice de confianza no están definidos en los RF. | Confirmar si esos términos son diseño técnico o ampliar formalmente requisitos. |
| HU-02 | Apertura automática, barrera, carril despejado, semáforo e IoT no están en RF-01 a RF-15. | Excluir de la versión 1 o crear y aprobar requisitos específicos. |
| HU-03 | Sensor de despeje, tiempo de tolerancia y descenso de barrera no están en los RF. | Excluir de la versión 1 o crear y aprobar requisitos de seguridad física. |
| HU-04 | Registro, placa y evidencia son compatibles con RF-04 a RF-06, pero `resultado` y enlace de imagen no tienen formato formal aprobado. | Definir el esquema de datos y asignar requisitos verificables. |
| HU-05 | Apertura manual, comandos y categoría `ACCESO_MANUAL_SUPERVISADO` no están en los RF. | Excluir de la versión 1 o aprobar la capacidad y su matriz de permisos. |

## 7. Dudas y decisiones que requieren validación del equipo

1. ¿Quiénes son los usuarios reales del sistema: personal de supervisión,
   administración, auditoría, residentes u otros?
2. ¿El caso rector incluye físicamente una barrera, sensores, semáforo y
   actuadores IoT? Si la respuesta es sí, deben incorporarse y aprobarse los RF
   y RNF correspondientes; si no, deben retirarse de las historias.
3. ¿Qué significa exactamente “vehículo autorizado” y quién puede crear,
   modificar o revocar esa autorización?
4. ¿Cuál es el canal de alerta aprobado? Los RF actuales solo especifican una
   alerta visual; no autorizan correo, SMS, aplicación móvil, audio ni
   notificaciones push.
5. ¿Qué datos se almacenan realmente: matrícula, fecha, hora, imagen, marca,
   color e historial? Debe verificarse la disponibilidad técnica y la base
   jurídica de cada dato.
6. ¿Cuál es la política de retención y eliminación de imágenes y registros?
   Debe coordinarse con RNF-10, RNF-12 y RLC-01 a RLC-06.
7. ¿Qué umbrales cuantitativos se usarán para aceptar rendimiento,
   disponibilidad, recuperación y conservación de respaldos? RNF-13 y RNF-14
   actualmente no los especifican.
8. ¿Puede compartirse el export original de la encuesta y el texto completo de
   la pregunta 10? Sin esa fuente no es posible auditar las frecuencias
   aproximadas ni priorizar características adicionales.
9. ¿Debe el mapa final representar dos perfiles o un único perfil operativo?
   La encuesta no levantó roles, por lo que esta decisión debe tomarla el
   equipo y documentarse.
10. ¿Debe actualizarse el README general para reflejar RF-01 a RF-15 y
    RNF-01 a RNF-15? Su inventario está desactualizado frente a los archivos
    vigentes.

## 8. Conclusión

La encuesta respalda tres necesidades principales: mejorar la vigilancia,
conservar trazabilidad de accesos y recibir alertas ante vehículos sin
autorización coincidente. Los RF actuales cubren una primera versión de esas
necesidades mediante captura, análisis, registro, consulta, administración y
alerta visual. La evidencia no valida por sí sola perfiles operativos
concretos, apertura automática, sensores, actuadores ni funcionalidades
adicionales.

Los mapas propuestos respetan exactamente los cuatro cuadrantes solicitados y
separan evidencia, interpretación e hipótesis. Las historias propuestas son
trazables a necesidades y requisitos existentes, pero permanecen pendientes
de validación hasta resolver las decisiones de perfiles, datos, alertas,
métricas y alcance físico del caso rector.
