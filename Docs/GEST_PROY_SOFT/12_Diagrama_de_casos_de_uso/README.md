# Diagramas de Casos de Uso — VIGÍA Vision Systems

## 1. Propósito

Esta carpeta contiene los diagramas de casos de uso de VIGÍA Vision Systems. Su objetivo es representar las interacciones entre los actores del sistema y las funcionalidades disponibles según sus responsabilidades.

Los diagramas permiten identificar los límites funcionales del sistema, las operaciones asociadas a cada actor y las relaciones entre los casos de uso.

## 2. Inventario de diagramas

| Identificador | Archivo                           | Descripción                                                                                             |
| ------------- | --------------------------------- | ------------------------------------------------------------------------------------------------------- |
| DCU-01        | `DCU-01_VIGIA_ADMIN.drawio.svg`   | Representa los casos de uso asociados al administrador del sistema y sus responsabilidades funcionales. |
| DCU-02        | `DCU-02_VIGIA_GUARDIA.drawio.svg` | Representa los casos de uso asociados al guardia y sus operaciones dentro del sistema.                  |

## 3. Alcance

Los diagramas documentan las funcionalidades desde la perspectiva de los actores que interactúan con VIGÍA.

- **Administrador:** representa las operaciones administrativas contempladas en el diseño del sistema.
- **Guardia:** representa las operaciones relacionadas con la supervisión y la gestión operativa del acceso vehicular.

Las funcionalidades específicas, así como las relaciones entre actores y casos de uso, deben interpretarse conforme a lo representado en cada diagrama.

## 4. Convenciones

Los diagramas se encuentran en formato SVG exportado desde draw.io, lo que permite consultarlos en navegadores web y otras herramientas compatibles con este formato.

Los identificadores `DCU-01` y `DCU-02` permiten referenciar cada diagrama de manera consistente en la documentación técnica del proyecto.

## 5. Relación con la arquitectura

Los diagramas de casos de uso complementan la documentación de arquitectura, los modelos de dominio y las especificaciones funcionales de VIGÍA Vision Systems.

Su función es describir **qué funcionalidades ofrece el sistema y quién interactúa con ellas**, sin detallar la implementación interna de los módulos.

## 6. Ubicación

```text
12_Diagrama_de_casos_de_uso/
├── DCU-01_VIGIA_ADMIN.drawio.svg
├── DCU-02_VIGIA_GUARDIA.drawio.svg
└── README.md
```

## 7. Mantenimiento documental

Cuando se modifiquen los casos de uso, deberá actualizarse el diagrama correspondiente y verificarse su consistencia con los requisitos funcionales y la documentación vigente del proyecto.
