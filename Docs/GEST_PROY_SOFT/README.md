# GEST_PROY_SOFT — Gestión de Proyectos de Software

**Proyecto:** VIGIA Vision Systems *(Iniciativa Académica / Empresa)*  
**Producto:** VIGIA *(Plataforma de Supervisión, Análisis y Automatización de Entornos Físicos)*  
**Área:** Gestión de Proyectos de Software y Diseño Centrado en el Usuario  
**Estado:** Activo / Fase 0 — Sprint 0  

---

## 1. Propósito de `GEST_PROY_SOFT`

El directorio `GEST_PROY_SOFT` es el espacio formal y centralizado para almacenar, estructurar y consultar los **entregables oficiales de Gestión de Proyectos de Software** del proyecto VIGIA Vision Systems.

Esta organización permite:
* Facilitar la navegación, evaluación y presentación del proyecto directamente desde GitHub.
* Establecer una correspondencia unívoca entre las 20 categorías de entregables y los integrantes responsables del equipo.
* Mantener una nomenclatura estandarizada, profesional y reutilizable sin nombres de personas incrustados en los nombres de archivo.
* Diferenciar claramente entre entregables técnicos propios del proyecto y plantillas/ejemplos institucionales de referencia.

---

## 2. Matriz Oficial de Roles y Entregables

El equipo está integrado por seis integrantes que desempeñan ocho puestos o funciones oficiales distribuidos entre ellos:

| Categoría | Entregable Oficial | Puesto / Rol Oficial | Responsable | Directorio |
| :---: | :--- | :--- | :--- | :--- |
| **01** | **Ficha de descripción de roles** | Ingenieros de Software + Ing. de Diseño Eléctrico | **Yair** | [`01_Ficha_descripcion_de_roles/`](./01_Ficha_descripcion_de_roles/) |
| **02** | **Logos, asegurando accesibilidad** | CIO + Ing. de Diseño de Circuitos | **Ernesto** | [`02_Logos_accesibilidad/`](./02_Logos_accesibilidad/) |
| **03** | **Requerimientos funcionales y no funcionales** | Ingenieros de Software + Ing. de Diseño Eléctrico | **Yair** | [`03_Requerimientos_funcionales_no_funcionales/`](./03_Requerimientos_funcionales_no_funcionales/) |
| **04** | **Mapa de empatía** | Analistas | **Estef** | [`04_Mapa_de_empatia/`](./04_Mapa_de_empatia/) |
| **05** | **Creación de personas** | UX / UI | **Natalia** | [`05_Creacion_de_personas/`](./05_Creacion_de_personas/) |
| **06** | **Historia de usuario** | Product Owner (PO) | **Vianey** | [`06_Historias_de_usuario/`](./06_Historias_de_usuario/) |
| **07** | **Todas las hojas del formato de reuniones** | Ing. de Procesos | **Josué** | [`07_Formato_de_reuniones/`](./07_Formato_de_reuniones/) |
| **08** | **Mapas de recorrido** | CIO + Ing. de Diseño de Circuitos | **Ernesto** | [`08_Mapas_de_recorrido/`](./08_Mapas_de_recorrido/) |
| **09** | **Wireframes** | TBD | **TBD** | [`09_Wireframes/`](./09_Wireframes/) |
| **10** | **Mockups** | TBD | **TBD** | [`10_Mockups/`](./10_Mockups/) |
| **11** | **Diagrama de flujo** | TBD | **TBD** | [`11_Diagrama_de_flujo/`](./11_Diagrama_de_flujo/) |
| **12** | **Diagrama de casos de uso** | TBD | **TBD** | [`12_Diagrama_de_casos_de_uso/`](./12_Diagrama_de_casos_de_uso/) |
| **13** | **Diagramas de bloques** | TBD | **TBD** | [`13_Diagramas_de_bloques/`](./13_Diagramas_de_bloques/) |
| **14** | **Modelo del prototipo** | TBD | **TBD** | [`14_Modelo_del_prototipo/`](./14_Modelo_del_prototipo/) |
| **15** | **Memoria técnica** | TBD | **TBD** | [`15_Memoria_tecnica/`](./15_Memoria_tecnica/) |
| **16** | **Fichas técnicas** | TBD | **TBD** | [`16_Fichas_tecnicas/`](./16_Fichas_tecnicas/) |
| **17** | **Materiales del proyecto** | TBD | **TBD** | [`17_Materiales_del_proyecto/`](./17_Materiales_del_proyecto/) |
| **18** | **Costos y presupuestos** | TBD | **TBD** | [`18_Costos_y_presupuestos/`](./18_Costos_y_presupuestos/) |
| **19** | **Plan de calidad** | TBD | **TBD** | [`19_Plan_de_calidad/`](./19_Plan_de_calidad/) |
| **20** | **Entregas de la semana y la siguiente** | TBD | **TBD** | [`20_Entregas_de_la_semana_y_la_siguiente/`](./20_Entregas_de_la_semana_y_la_siguiente/) |

---

## 3. Estructura Oficial de Directorios

`GEST_PROY_SOFT/` contiene exclusivamente las **veinte (20) categorías principales** de entregables:

```text
Docs/
└── GEST_PROY_SOFT/
    ├── README.md                                       # [Este documento] Índice y matriz de entregables
    ├── 01_Ficha_descripcion_de_roles/                  # Ficha de puesto y descripción de responsabilidades
    │   └── Ficha_descripcion_de_roles.md               # [En desarrollo] Documentación preliminar de puestos/roles
    ├── 02_Logos_accesibilidad/                         # Identidad visual institucional y versión de alto contraste
    │   ├── README.md                                   # [En desarrollo] Especificaciones y criterios WCAG
    │   └── svg/                                        # [Entregable] Recursos gráficos vectoriales SVG (empresa y producto)
    ├── 03_Requerimientos_funcionales_no_funcionales/   # Catálogo formal de RF, RNF y RLC
    │   ├── Requerimientos_funcionales.md               # [En desarrollo] RF-01 a RF-13
    │   ├── Requerimientos_no_funcionales.md            # [En desarrollo] RNF-01 a RNF-12
    │   └── Requisitos_legales_y_cumplimiento.md        # [En desarrollo] RLC-01 a RLC-06
    ├── 04_Mapa_de_empatia/                             # Artefacto de empatía con usuarios y operadores
    │   ├── README.md                                   # [En desarrollo] Estado y especificaciones del mapa
    │   └── Ejemplo_mapas_de_empatia.pptx               # [Plantilla / Referencia] Material institucional de ejemplo
    ├── 05_Creacion_de_personas/                        # Arquetipos de usuario del sistema
    │   ├── README.md                                   # [En desarrollo] Especificaciones de arquetipos
    │   └── Ejemplo_creacion_de_personas.pptx           # [Plantilla / Referencia] Material institucional de ejemplo
    ├── 06_Historias_de_usuario/                        # Historias de usuario del caso rector
    │   ├── README.md                                   # [En desarrollo] Índice y estado de historias
    │   ├── Historias_de_usuario.md                     # [En desarrollo] Catálogo base de historias HU-01..HU-05
    │   └── Ejemplo_historias_de_usuario.pptx           # [Plantilla / Referencia] Material institucional de ejemplo
    ├── 07_Formato_de_reuniones/                        # Formato y actas de minutas de reuniones de equipo
    │   ├── README.md                                   # Gobernanza y control de sesiones
    │   └── Formato_acta_de_reunion_TESH.pdf            # [Formato institucional] Formato oficial de actas
    ├── 08_Mapas_de_recorrido/                          # Mapas de viaje de usuario (Customer Journey Maps)
    ├── 09_Wireframes/                                  # Estructuras de baja fidelidad de las interfaces
    ├── 10_Mockups/                                     # Representaciones visuales de las interfaces
    ├── 11_Diagrama_de_flujo/                           # Flujo de operación y decisiones del sistema
    ├── 12_Diagrama_de_casos_de_uso/                    # Actores, casos de uso y relaciones
    ├── 13_Diagramas_de_bloques/                        # Arquitectura funcional y bloques del sistema
    ├── 14_Modelo_del_prototipo/                        # Modelo y evidencia del prototipo
    ├── 15_Memoria_tecnica/                             # Memoria técnica del proyecto
    ├── 16_Fichas_tecnicas/                             # Fichas de componentes y recursos técnicos
    ├── 17_Materiales_del_proyecto/                     # Inventario de materiales requeridos
    ├── 18_Costos_y_presupuestos/                       # Cantidades, precios y estimación presupuestaria
    ├── 19_Plan_de_calidad/                             # Criterios, verificaciones y evidencias de calidad
    └── 20_Entregas_de_la_semana_y_la_siguiente/       # Seguimiento de entregas y próximos compromisos
```

> **Nota de organización:** La documentación institucional de soporte académico (`Memoria_Tecnica_de_proyecto.pdf` y `Plan_de_calidad.pdf`) se encuentra debidamente resguardada en [`Docs/Referencias/`](../Referencias/).

---

## 4. Convenciones de Nomenclatura

* **Sin nombres personales en archivos:** La autoría y responsabilidad se gestiona a nivel de documentación y metadatos, garantizando nombres de archivo estandarizados y limpios (`Ficha_descripcion_de_roles.md`, `Historias_de_usuario.md`, etc.).
* **Transparencia entre entregables y plantillas:** Los recursos institucionales de referencia se prefijan explícitamente con `Ejemplo_` o se mantienen en `Docs/Referencias/` para distinguirlos claramente de los entregables desarrollados específicamente para VIGIA.
* **Separación de responsabilidades:** Cada carpeta contiene su respectivo archivo descriptivo o recurso de presentación, facilitando la auditoría y entrega modular.