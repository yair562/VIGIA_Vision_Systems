# Diagramas de Bloques — VIGÍA Vision Systems

## 1. Propósito

Esta carpeta contiene los diagramas de bloques de VIGÍA Vision Systems. Su objetivo es documentar la arquitectura del sistema mediante la representación de sus componentes principales, sus responsabilidades y las relaciones de comunicación o dependencia entre ellos.

Los diagramas se organizan en tres niveles complementarios: arquitectura general, arquitectura interna del motor de visión artificial y arquitectura de persistencia.

## 2. Inventario de diagramas

| Identificador | Archivo                                      | Descripción                                                                                                                                          |
| ------------- | -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| DB-01         | `DB-01_ARQUITECTURA.drawio.svg`              | Presenta la arquitectura general de VIGÍA Vision Systems y las relaciones entre sus principales subsistemas y componentes.                           |
| DB-02         | `DB-02_ARQUITECTURA_MOTOR.drawio.svg`        | Describe la organización interna del motor de visión artificial, sus componentes de captura y procesamiento y la generación de resultados de visión. |
| DB-03         | `DB-03_ARQUITECTURA_PERSISTENCIA.drawio.svg` | Representa la arquitectura de persistencia de detecciones y la gestión del almacenamiento de evidencias fotográficas.                                |

## 3. Descripción de los diagramas

### DB-01. Arquitectura general del sistema

Representa los principales componentes de VIGÍA Vision Systems y su distribución arquitectónica.

Su finalidad es proporcionar una visión global del sistema y facilitar la comprensión de las responsabilidades de los subsistemas, sus dependencias y las relaciones entre los componentes.

### DB-02. Arquitectura interna del motor de visión artificial

Representa los componentes involucrados en la captura y el procesamiento de imágenes, la detección de vehículos, el reconocimiento de placas cuando se encuentre implementado e integrado, y la generación del resultado de visión.

La arquitectura documentada debe respetar la separación de responsabilidades entre `VIGIA_Vision` y `VIGIA_Core`, así como la reutilización del contrato canónico `VisionResult`.

El diagrama describe la organización de los componentes; no sustituye al diagrama de flujo que detalla las decisiones y los pasos de ejecución del procesamiento.

### DB-03. Arquitectura de persistencia y almacenamiento de evidencias

Representa los componentes responsables de preparar los datos de una detección, gestionar su persistencia y almacenar las evidencias fotográficas correspondientes.

Considera la separación entre:

- **Datos de detección:** información estructurada que puede registrarse en PostgreSQL conforme al esquema vigente.
- **Evidencias fotográficas:** archivos almacenados en el sistema de archivos y referenciados según el diseño de persistencia.
- **Capa de persistencia:** componentes responsables de coordinar las operaciones y acceder al repositorio de datos.

El diseño debe contemplar que el almacenamiento de archivos y las transacciones de PostgreSQL son recursos independientes. Por ello, un fallo en uno de ellos puede dejar un resultado parcial que requiera tratamiento específico.

## 4. Criterios de interpretación

Los diagramas de bloques representan componentes, responsabilidades y relaciones arquitectónicas.

No deben interpretarse como diagramas de flujo, diagramas de secuencia ni evidencia suficiente de que todas las conexiones estén implementadas y operativas.

Las relaciones representadas deberán mantenerse alineadas con los contratos entre módulos, los modelos de dominio, el esquema de PostgreSQL y el código fuente vigente.

## 5. Documentación de referencia

Los diagramas se complementan con la documentación técnica de la Fase 1, especialmente:

- `DOC-01_modelos_dominio.md`: modelos de dominio y contratos canónicos.
- `DOC-02_auditoria_esquema_bd.md`: auditoría del esquema relacional.
- `DOC-03_asignacion_validacion_posiciones.md`: reglas de configuración y validación de la topología operativa.
- `DOC-04_contratos_entre_modulos.md`: contratos de integración entre componentes.
- `DOC-05_plan_pruebas_unitarias.md`: estrategia de verificación y pruebas.
- `DOC-06_matriz_trazabilidad.md`: relación entre requisitos y componentes, si está disponible en la versión documental vigente.

La documentación de referencia establece el contexto arquitectónico; la implementación real debe verificarse en el repositorio antes de declarar un componente o una integración como operativos.

## 6. Formato y convenciones

Los diagramas se encuentran en formato SVG exportado desde draw.io.

Los identificadores `DB-01`, `DB-02` y `DB-03` permiten referenciarlos de forma consistente en la documentación de arquitectura, las revisiones técnicas y la trazabilidad del proyecto.

## 7. Estructura de la carpeta

```text
13_Diagramas_de_bloques/
├── DB-01_ARQUITECTURA.drawio.svg
├── DB-02_ARQUITECTURA_MOTOR.drawio.svg
├── DB-03_ARQUITECTURA_PERSISTENCIA.drawio.svg
└── README.md
```

## 8. Mantenimiento documental

Ante cualquier cambio relevante en los módulos, sus contratos, la persistencia o las responsabilidades arquitectónicas, deberá revisarse el diagrama afectado.

Antes de publicar una actualización, se deberá comprobar que:

1. Los componentes representados corresponden al diseño vigente.
2. Las relaciones entre componentes están respaldadas por los contratos o las decisiones arquitectónicas documentadas.
3. No se presentan funcionalidades planificadas como implementaciones terminadas.
4. El inventario de esta carpeta coincide con los archivos disponibles.
