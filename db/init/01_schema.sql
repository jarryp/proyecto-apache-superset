-- Esquema en estrella del caso "Inversiones Palacios" (idéntico al modelo
-- de la Semana 4/5): ventas es la tabla de hechos; productos y clientes
-- son las dimensiones. Los tipos y restricciones se derivan de una
-- inspección real de los 3 CSV de origen: sin duplicados ni huérfanos en
-- las llaves primarias/foráneas, num_factura y codigo_producto son
-- alfanuméricos, y 486 de los 5.305 productos llegan sin descripción
-- (categorizados igualmente como "SIN_DESCRIPCION"): es el mismo hallazgo
-- de calidad que motiva la columna descripcion_faltante en ventas, por lo
-- que aquí se documenta permitiendo NULL en vez de forzar un NOT NULL que
-- rompería la carga real.

CREATE TABLE productos (
    codigo_producto VARCHAR(20)  PRIMARY KEY,
    descripcion     VARCHAR(255),
    categoria       VARCHAR(50)  NOT NULL
);

CREATE TABLE clientes (
    id_cliente INTEGER      PRIMARY KEY,
    pais       VARCHAR(100) NOT NULL
);

CREATE TABLE ventas (
    id_venta             INTEGER       PRIMARY KEY,
    num_factura          VARCHAR(20)   NOT NULL,
    codigo_producto      VARCHAR(20)   NOT NULL REFERENCES productos(codigo_producto),
    cantidad             INTEGER       NOT NULL,
    fecha                TIMESTAMP     NOT NULL,
    precio_unitario      NUMERIC(12,4) NOT NULL,
    -- id_cliente puede ser NULL: existen ventas sin cliente identificado
    -- (ver columna cliente_identificado), tal como en la base de la Sem. 5.
    id_cliente           INTEGER       REFERENCES clientes(id_cliente),
    pais                 VARCHAR(100)  NOT NULL,
    es_cancelacion       BOOLEAN       NOT NULL,
    cliente_identificado BOOLEAN       NOT NULL,
    descripcion_faltante BOOLEAN       NOT NULL,
    revisar_precio       BOOLEAN       NOT NULL,
    hoja_origen          VARCHAR(50)
);

-- Índices sobre las llaves foráneas y la fecha: con 1,03M filas de hechos,
-- son obligatorios para que los filtros y cruces de Superset respondan
-- en tiempos interactivos (objetivo: < 3 s por gráfico en frío).
CREATE INDEX idx_ventas_codigo_producto ON ventas (codigo_producto);
CREATE INDEX idx_ventas_id_cliente      ON ventas (id_cliente);
CREATE INDEX idx_ventas_fecha           ON ventas (fecha);
CREATE INDEX idx_ventas_pais            ON ventas (pais);
