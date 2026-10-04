-- Base de datos separada para los metadatos de Apache Superset
-- (conexiones, dashboards, usuarios, permisos). Se mantiene aislada
-- de la base analítica "inversiones_palacios" por buenas prácticas
-- de separación de responsabilidades.
CREATE DATABASE superset_meta;
