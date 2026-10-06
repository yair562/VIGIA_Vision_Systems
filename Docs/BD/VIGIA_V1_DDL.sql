-- =============================================================================
-- VIGIA Vision Systems — Base de Datos V1
-- Script DDL — Diseño Físico PostgreSQL
-- Motor: PostgreSQL 15+
-- Versión del Modelo: 1.0 (Línea Base Congelada — VIGIA V1)
-- Estado: CONGELADO OFICIALMENTE — Octubre 2026
-- Propósito: Demostración de entidades y estructura de la BD
-- =============================================================================
-- EJECUCIÓN SEGURA: Este script es idempotente.
-- Ejecutar en una base de datos limpia o de prueba.
-- Requiere la extensión pgcrypto para gen_random_uuid().
-- =============================================================================

-- Habilitar generación de UUIDs
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================================================
-- BORRADO EN ORDEN INVERSO (respeta integridad referencial)
-- =============================================================================
DROP TABLE IF EXISTS alerta           CASCADE;
DROP TABLE IF EXISTS evento_acceso    CASCADE;
DROP TABLE IF EXISTS deteccion        CASCADE;
DROP TABLE IF EXISTS area_vision      CASCADE;
DROP TABLE IF EXISTS camara           CASCADE;
DROP TABLE IF EXISTS vehiculo         CASCADE;
DROP TABLE IF EXISTS persona          CASCADE;
DROP TABLE IF EXISTS usuario          CASCADE;

-- =============================================================================
-- 1. PERSONA — Padrón Institucional
--    Miembros de la comunidad educativa autorizados para registrar vehículos.
-- =============================================================================
CREATE TABLE persona (
    id_persona           UUID                     PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo_institucional VARCHAR(20)              NOT NULL UNIQUE,
    nombre               VARCHAR(60)              NOT NULL,
    primer_apellido      VARCHAR(50)              NOT NULL,
    segundo_apellido     VARCHAR(50)              NULL,
    tipo_persona         VARCHAR(20)              NOT NULL,
    activo               BOOLEAN                  NOT NULL DEFAULT TRUE,
    creado_en            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_tipo_persona
        CHECK (tipo_persona IN ('ALUMNO', 'DOCENTE', 'ADMINISTRATIVO'))
);

COMMENT ON TABLE  persona                     IS 'Padrón institucional de miembros autorizados para registrar vehículos.';
COMMENT ON COLUMN persona.codigo_institucional IS 'Matrícula estudiantil o número de nómina del empleado.';
COMMENT ON COLUMN persona.tipo_persona         IS 'Clasificación: ALUMNO | DOCENTE | ADMINISTRATIVO';
COMMENT ON COLUMN persona.activo               IS 'Borrado lógico: FALSE deshabilita al miembro sin eliminar registros históricos.';

-- =============================================================================
-- 2. VEHICULO — Lista Blanca Institucional
--    Parque vehicular registrado y acreditado para acceder a las instalaciones.
-- =============================================================================
CREATE TABLE vehiculo (
    id_vehiculo  UUID                     PRIMARY KEY DEFAULT gen_random_uuid(),
    id_persona   UUID                     NOT NULL,
    placa        VARCHAR(15)              NOT NULL UNIQUE,
    tipo_vehiculo VARCHAR(20)             NOT NULL,
    marca        VARCHAR(40)              NULL,
    modelo       VARCHAR(40)              NULL,
    color        VARCHAR(30)              NULL,
    activo       BOOLEAN                  NOT NULL DEFAULT TRUE,
    creado_en    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_vehiculo_persona
        FOREIGN KEY (id_persona) REFERENCES persona (id_persona) ON DELETE RESTRICT,

    CONSTRAINT chk_tipo_vehiculo
        CHECK (tipo_vehiculo IN ('AUTOMOVIL', 'CAMIONETA', 'MOTOCICLETA'))
);

COMMENT ON TABLE  vehiculo              IS 'Lista blanca de vehículos autorizados para acceder a las instalaciones.';
COMMENT ON COLUMN vehiculo.placa        IS 'Matrícula alfanumérica vehicular sin guiones ni espacios.';
COMMENT ON COLUMN vehiculo.tipo_vehiculo IS 'Tipo de unidad: AUTOMOVIL | CAMIONETA | MOTOCICLETA';
COMMENT ON COLUMN vehiculo.activo       IS 'Borrado lógico: FALSE revoca la autorización de acceso del vehículo.';

-- Índice de búsqueda por placa (consulta crítica de VIGIA_Core en tiempo real)
CREATE INDEX idx_vehiculo_placa ON vehiculo (placa);

-- =============================================================================
-- 3. USUARIO — Cuentas de Software y Seguridad RBAC
--    Cuentas autenticables para operadores de caseta, administradores y auditores.
-- =============================================================================
CREATE TABLE usuario (
    id_usuario      UUID                     PRIMARY KEY DEFAULT gen_random_uuid(),
    username        VARCHAR(30)              NOT NULL UNIQUE,
    contrasena_hash VARCHAR(255)             NOT NULL,
    nombre_completo VARCHAR(100)             NOT NULL,
    rol             VARCHAR(20)              NOT NULL,
    activo          BOOLEAN                  NOT NULL DEFAULT TRUE,
    creado_en       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_rol_usuario
        CHECK (rol IN ('ADMINISTRADOR', 'OPERADOR', 'AUDITOR'))
);

COMMENT ON TABLE  usuario               IS 'Cuentas autenticables del sistema con control de acceso basado en roles (RBAC).';
COMMENT ON COLUMN usuario.contrasena_hash IS 'Contraseña cifrada con bcrypt o argon2. Nunca texto plano.';
COMMENT ON COLUMN usuario.rol            IS 'Rol RBAC: ADMINISTRADOR | OPERADOR | AUDITOR';
COMMENT ON COLUMN usuario.activo         IS 'Borrado lógico: FALSE deshabilita la cuenta sin eliminar su historial de acciones.';

-- =============================================================================
-- 4. CAMARA — Fuentes de Video
--    Dispositivos físicos de captura óptica instalados en puntos de control.
-- =============================================================================
CREATE TABLE camara (
    id_camara        UUID                     PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo           VARCHAR(20)              NOT NULL UNIQUE,
    nombre           VARCHAR(60)              NOT NULL,
    uri_stream       VARCHAR(255)             NOT NULL,
    resolucion_ancho INTEGER                  NULL,
    resolucion_alto  INTEGER                  NULL,
    activa           BOOLEAN                  NOT NULL DEFAULT TRUE,
    creado_en        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_resolucion_ancho CHECK (resolucion_ancho IS NULL OR resolucion_ancho > 0),
    CONSTRAINT chk_resolucion_alto  CHECK (resolucion_alto  IS NULL OR resolucion_alto  > 0)
);

COMMENT ON TABLE  camara           IS 'Dispositivos físicos de captura óptica instalados en los puntos de control.';
COMMENT ON COLUMN camara.codigo    IS 'Nemotécnico único del dispositivo. Ejemplo: CAM-ENTRADA-01';
COMMENT ON COLUMN camara.uri_stream IS 'Cadena de conexión RTSP o índice de dispositivo USB (ej. /dev/video0 o 0).';
COMMENT ON COLUMN camara.activa    IS 'Indica si la cámara está operativa en tiempo real.';

-- =============================================================================
-- 5. AREA_VISION — Regiones de Interés (ROI)
--    Zona lógica configurable dentro del cuadro de visión de una cámara.
-- =============================================================================
CREATE TABLE area_vision (
    id_area_vision UUID                     PRIMARY KEY DEFAULT gen_random_uuid(),
    id_camara      UUID                     NOT NULL,
    codigo         VARCHAR(20)              NOT NULL,
    nombre         VARCHAR(60)              NOT NULL,
    tipo_movimiento VARCHAR(15)             NOT NULL,
    x_min          NUMERIC(4, 3)            NOT NULL,
    y_min          NUMERIC(4, 3)            NOT NULL,
    x_max          NUMERIC(4, 3)            NOT NULL,
    y_max          NUMERIC(4, 3)            NOT NULL,
    activa         BOOLEAN                  NOT NULL DEFAULT TRUE,
    creado_en      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_area_vision_camara
        FOREIGN KEY (id_camara) REFERENCES camara (id_camara) ON DELETE RESTRICT,

    CONSTRAINT chk_tipo_movimiento_area
        CHECK (tipo_movimiento IN ('ENTRADA', 'SALIDA')),

    CONSTRAINT chk_coordenadas_roi
        CHECK (
            x_min >= 0.000 AND x_min <= 1.000 AND
            y_min >= 0.000 AND y_min <= 1.000 AND
            x_max >= 0.000 AND x_max <= 1.000 AND
            y_max >= 0.000 AND y_max <= 1.000 AND
            x_min < x_max AND
            y_min < y_max
        )
);

COMMENT ON TABLE  area_vision                IS 'Regiones de interés (ROI) lógicas dentro del encuadre de una cámara para análisis de matrículas.';
COMMENT ON COLUMN area_vision.tipo_movimiento IS 'Orientación del flujo de tránsito: ENTRADA | SALIDA';
COMMENT ON COLUMN area_vision.x_min          IS 'Coordenada normalizada X mínima en rango [0.000, 1.000].';
COMMENT ON COLUMN area_vision.x_max          IS 'Coordenada normalizada X máxima en rango [0.000, 1.000].';
COMMENT ON COLUMN area_vision.y_min          IS 'Coordenada normalizada Y mínima en rango [0.000, 1.000].';
COMMENT ON COLUMN area_vision.y_max          IS 'Coordenada normalizada Y máxima en rango [0.000, 1.000].';

-- =============================================================================
-- 6. DETECCION — Bitácora de Observaciones Visuales
--    Registro puro e inmutable de cada inferencia del subsistema VIGIA_Vision.
-- =============================================================================
CREATE TABLE deteccion (
    id_deteccion       UUID                     PRIMARY KEY DEFAULT gen_random_uuid(),
    id_area_vision     UUID                     NOT NULL,
    fecha_hora         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    placa_detectada    VARCHAR(15)              NULL,
    confianza_placa    NUMERIC(4, 3)            NULL,
    tipo_vehiculo_pred VARCHAR(20)              NULL,
    confianza_vehiculo NUMERIC(4, 3)            NULL,
    ruta_evidencia_foto VARCHAR(255)            NOT NULL,

    CONSTRAINT fk_deteccion_area_vision
        FOREIGN KEY (id_area_vision) REFERENCES area_vision (id_area_vision) ON DELETE RESTRICT,

    CONSTRAINT chk_confianza_placa
        CHECK (confianza_placa IS NULL OR (confianza_placa >= 0.000 AND confianza_placa <= 1.000)),

    CONSTRAINT chk_confianza_vehiculo
        CHECK (confianza_vehiculo IS NULL OR (confianza_vehiculo >= 0.000 AND confianza_vehiculo <= 1.000))
);

COMMENT ON TABLE  deteccion                   IS 'Bitácora inmutable de inferencias generadas por VIGIA_Vision. Un registro por detección óptica.';
COMMENT ON COLUMN deteccion.placa_detectada   IS 'Caracteres leídos por el OCR. NULL si no se logró lectura válida.';
COMMENT ON COLUMN deteccion.confianza_placa   IS 'Probabilidad de exactitud del OCR en rango [0.000, 1.000].';
COMMENT ON COLUMN deteccion.tipo_vehiculo_pred IS 'Tipo de vehículo inferido por el clasificador visual.';
COMMENT ON COLUMN deteccion.ruta_evidencia_foto IS 'Ruta local o URL a la fotografía forense guardada en disco.';

-- Índice para búsqueda rápida de detecciones por área y tiempo
CREATE INDEX idx_deteccion_area_fecha ON deteccion (id_area_vision, fecha_hora DESC);
CREATE INDEX idx_deteccion_placa      ON deteccion (placa_detectada);

-- =============================================================================
-- 7. EVENTO_ACCESO — Auditoría Maestra de Transacciones
--    Bitácora central de cada intento y decisión de cruce vehicular.
-- =============================================================================
CREATE TABLE evento_acceso (
    id_evento_acceso     UUID                     PRIMARY KEY DEFAULT gen_random_uuid(),
    id_deteccion         UUID                     NULL,
    id_vehiculo          UUID                     NULL,
    id_usuario_operador  UUID                     NULL,
    fecha_hora           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    placa_efectiva       VARCHAR(15)              NULL,
    tipo_movimiento      VARCHAR(15)              NOT NULL,
    tipo_acceso          VARCHAR(25)              NOT NULL,
    resultado_acceso     VARCHAR(15)              NOT NULL,
    motivo_decision      VARCHAR(50)              NOT NULL,
    observaciones        TEXT                     NULL,

    CONSTRAINT fk_evento_deteccion
        FOREIGN KEY (id_deteccion)        REFERENCES deteccion (id_deteccion) ON DELETE RESTRICT,

    CONSTRAINT fk_evento_vehiculo
        FOREIGN KEY (id_vehiculo)         REFERENCES vehiculo  (id_vehiculo)  ON DELETE RESTRICT,

    CONSTRAINT fk_evento_usuario_operador
        FOREIGN KEY (id_usuario_operador) REFERENCES usuario   (id_usuario)   ON DELETE RESTRICT,

    CONSTRAINT chk_tipo_movimiento_evento
        CHECK (tipo_movimiento    IN ('ENTRADA', 'SALIDA')),

    CONSTRAINT chk_tipo_acceso
        CHECK (tipo_acceso        IN ('AUTOMATICO', 'MANUAL_SUPERVISADO')),

    CONSTRAINT chk_resultado_acceso
        CHECK (resultado_acceso   IN ('PERMITIDO', 'DENEGADO')),

    CONSTRAINT chk_motivo_decision
        CHECK (motivo_decision    IN (
            'VEHICULO_AUTORIZADO',
            'VISITA_JUSTIFICADA',
            'PLACA_NO_REGISTRADA',
            'VEHICULO_INACTIVO',
            'APERTURA_EMERGENCIA',
            'PLACA_ILEGIBLE_MANUAL',
            'TIMEOUT_PASO',
            'OBSTACULO_SENSOR'
        ))
);

COMMENT ON TABLE  evento_acceso                  IS 'Auditoría maestra e inmutable de cada transacción de cruce vehicular.';
COMMENT ON COLUMN evento_acceso.id_deteccion     IS 'NULL en aperturas manuales de emergencia sin intervención de cámara.';
COMMENT ON COLUMN evento_acceso.id_vehiculo      IS 'NULL para visitantes, proveedores o vehículos no registrados.';
COMMENT ON COLUMN evento_acceso.id_usuario_operador IS 'NULL en accesos automáticos aprobados por VIGIA_Core.';
COMMENT ON COLUMN evento_acceso.placa_efectiva   IS 'Matrícula validada o resuelta. NULL si la placa fue ilegible y no capturada.';
COMMENT ON COLUMN evento_acceso.tipo_movimiento  IS 'Snapshot inmutable del movimiento al momento del cruce: ENTRADA | SALIDA';
COMMENT ON COLUMN evento_acceso.tipo_acceso      IS 'Modalidad de operación: AUTOMATICO | MANUAL_SUPERVISADO';
COMMENT ON COLUMN evento_acceso.resultado_acceso IS 'Decisión tomada: PERMITIDO | DENEGADO';

-- Índices de consulta frecuente
CREATE INDEX idx_evento_fecha            ON evento_acceso (fecha_hora DESC);
CREATE INDEX idx_evento_placa_efectiva   ON evento_acceso (placa_efectiva);
CREATE INDEX idx_evento_resultado        ON evento_acceso (resultado_acceso);

-- =============================================================================
-- 8. ALERTA — Incidentes de Seguridad y Excepciones Operativas
--    Advertencias y anomalías generadas por el sistema durante el ciclo de acceso.
-- =============================================================================
CREATE TABLE alerta (
    id_alerta             UUID                     PRIMARY KEY DEFAULT gen_random_uuid(),
    id_evento_acceso      UUID                     NULL,
    id_deteccion          UUID                     NULL,
    id_usuario_atendio    UUID                     NULL,
    fecha_hora            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    tipo_alerta           VARCHAR(30)              NOT NULL,
    nivel_prioridad       VARCHAR(15)              NOT NULL,
    estado_alerta         VARCHAR(15)              NOT NULL DEFAULT 'PENDIENTE',
    descripcion           TEXT                     NOT NULL,
    fecha_hora_atencion   TIMESTAMP WITH TIME ZONE NULL,
    notas_resolucion      TEXT                     NULL,

    CONSTRAINT fk_alerta_evento_acceso
        FOREIGN KEY (id_evento_acceso)   REFERENCES evento_acceso (id_evento_acceso) ON DELETE RESTRICT,

    CONSTRAINT fk_alerta_deteccion
        FOREIGN KEY (id_deteccion)       REFERENCES deteccion      (id_deteccion)     ON DELETE RESTRICT,

    CONSTRAINT fk_alerta_usuario_atendio
        FOREIGN KEY (id_usuario_atendio) REFERENCES usuario         (id_usuario)      ON DELETE RESTRICT,

    -- Toda alerta debe tener al menos un origen (evento o detección)
    CONSTRAINT chk_alerta_origen_no_huerfana
        CHECK (id_evento_acceso IS NOT NULL OR id_deteccion IS NOT NULL),

    CONSTRAINT chk_tipo_alerta
        CHECK (tipo_alerta IN (
            'PLACA_ILEGIBLE',
            'ACCESO_NO_AUTORIZADO',
            'TIMEOUT_PASO',
            'OBSTACULO_SENSOR'
        )),

    CONSTRAINT chk_nivel_prioridad
        CHECK (nivel_prioridad IN ('BAJA', 'MEDIA', 'ALTA', 'CRITICA')),

    CONSTRAINT chk_estado_alerta
        CHECK (estado_alerta   IN ('PENDIENTE', 'ATENDIDA', 'DESCARTADA'))
);

COMMENT ON TABLE  alerta                        IS 'Registro de incidentes de seguridad, anomalías físicas y excepciones operativas.';
COMMENT ON COLUMN alerta.id_evento_acceso       IS 'Evento de acceso anómalo que generó esta alerta. NULL si el origen es solo una detección.';
COMMENT ON COLUMN alerta.id_deteccion           IS 'Detección visual que detonó la alerta directamente. NULL si el origen es solo un evento.';
COMMENT ON COLUMN alerta.id_usuario_atendio     IS 'NULL hasta que un operador o auditor gestiona el incidente.';
COMMENT ON COLUMN alerta.tipo_alerta            IS 'Categoría: PLACA_ILEGIBLE | ACCESO_NO_AUTORIZADO | TIMEOUT_PASO | OBSTACULO_SENSOR';
COMMENT ON COLUMN alerta.nivel_prioridad        IS 'Gravedad del incidente: BAJA | MEDIA | ALTA | CRITICA';
COMMENT ON COLUMN alerta.estado_alerta          IS 'Ciclo de vida: PENDIENTE | ATENDIDA | DESCARTADA';
COMMENT ON COLUMN alerta.fecha_hora_atencion    IS 'Momento en que el operador cerró o resolvió el incidente.';

-- Índices para el panel de alertas del Dashboard
CREATE INDEX idx_alerta_estado          ON alerta (estado_alerta);
CREATE INDEX idx_alerta_prioridad_fecha ON alerta (nivel_prioridad, fecha_hora DESC);

-- =============================================================================
-- FIN DEL SCRIPT DDL — VIGIA V1
-- =============================================================================
-- Entidades creadas: 8
--   1. persona        — Padrón institucional
--   2. vehiculo       — Lista blanca vehicular
--   3. usuario        — Cuentas RBAC del software
--   4. camara         — Dispositivos de captura óptica
--   5. area_vision    — Regiones de interés (ROI)
--   6. deteccion      — Bitácora de observaciones visuales
--   7. evento_acceso  — Auditoría maestra de transacciones
--   8. alerta         — Incidentes y excepciones operativas
-- =============================================================================
