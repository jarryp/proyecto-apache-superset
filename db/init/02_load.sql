-- Carga masiva de los 3 CSV de origen usando COPY (no INSERT fila por
-- fila: con 1,03M filas en ventas.csv, INSERT sería órdenes de magnitud
-- más lento). Los archivos se montan de solo lectura en /data dentro del
-- contenedor de PostgreSQL (ver volumen "data" en docker-compose.yml).
-- Orden obligatorio: dimensiones antes que hechos, por las FK.

COPY productos (codigo_producto, descripcion, categoria)
FROM '/data/productos.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

COPY clientes (id_cliente, pais)
FROM '/data/clientes.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

-- En formato CSV, un campo vacío sin comillas se interpreta como NULL
-- por defecto: cubre los id_cliente en blanco de las ventas sin cliente
-- identificado, sin necesidad de una cláusula NULL explícita.
COPY ventas (
    id_venta, num_factura, codigo_producto, cantidad, fecha,
    precio_unitario, id_cliente, pais, es_cancelacion,
    cliente_identificado, descripcion_faltante, revisar_precio, hoja_origen
)
FROM '/data/ventas.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

-- Verificación rápida de conteos esperados (visible en los logs de
-- inicialización del contenedor db, para diagnóstico temprano).
DO $$
DECLARE
    n_productos INTEGER;
    n_clientes  INTEGER;
    n_ventas    INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_productos FROM productos;
    SELECT COUNT(*) INTO n_clientes  FROM clientes;
    SELECT COUNT(*) INTO n_ventas    FROM ventas;
    RAISE NOTICE 'Carga completada -> productos: %, clientes: %, ventas: %',
        n_productos, n_clientes, n_ventas;
END $$;
