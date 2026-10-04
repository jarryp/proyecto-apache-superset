-- Vista analítica que Superset consume como dataset único. Centraliza:
--  1) la columna "monto" (= cantidad * precio_unitario), equivalente a la
--     columna "Monto" creada en Power Query en la Semana 5;
--  2) la clasificación de los códigos que NO son mercancía real
--     (POST, DOT, M/m = POSTAGE, DOTCOM POSTAGE y Manual) detectados en
--     el hallazgo de la Semana 5. La decisión tomada aquí es: NO
--     eliminarlos del origen ni de esta vista (se conservan, igual que
--     las cancelaciones), pero sí marcarlos con
--     es_cargo_administrativo = true para poder excluirlos del ranking
--     de "top productos" sin perder trazabilidad del dato crudo.
CREATE OR REPLACE VIEW v_ventas_enriquecida AS
SELECT
    v.id_venta,
    v.num_factura,
    v.codigo_producto,
    -- 486 de los 5.305 productos llegan sin descripción de origen; se
    -- muestra un rótulo legible en vez de NULL, sin alterar el dato crudo.
    COALESCE(p.descripcion, '(sin descripción)') AS descripcion,
    p.categoria,
    v.cantidad,
    v.fecha,
    v.precio_unitario,
    (v.cantidad * v.precio_unitario)::NUMERIC(14, 2) AS monto,
    v.id_cliente,
    v.pais,
    v.es_cancelacion,
    v.cliente_identificado,
    v.descripcion_faltante,
    v.revisar_precio,
    v.hoja_origen,
    (v.codigo_producto IN ('POST', 'DOT', 'M', 'm')) AS es_cargo_administrativo
FROM ventas v
JOIN productos p ON p.codigo_producto = v.codigo_producto;

COMMENT ON VIEW v_ventas_enriquecida IS
    'Dataset único registrado en Superset. Une ventas con productos, agrega '
    'monto calculado y la bandera es_cargo_administrativo (hallazgo Manual/'
    'POSTAGE/DOTCOM POSTAGE de la Semana 5).';
