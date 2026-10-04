# Inversiones Palacios — Dashboard BI (Docker + PostgreSQL + Apache Superset)

Solución completa de Semana 6: reemplaza el *plan* de Power BI de la Semana 5 por
un dashboard **funcional**, levantado íntegramente con `docker compose`, sobre el
mismo esquema en estrella (`ventas`, `productos`, `clientes`). Ver
`Documento_Solucion_Semana6.md` para la explicación completa (arquitectura, modelo
de datos, hallazgos y comparación con Power BI/Tableau).

## 1. Prerrequisitos

- Docker Engine + Docker Compose v2.
- Puerto `8088` libre en el host (Superset). Puerto `5433` libre si se deja
  expuesto PostgreSQL para inspección (opcional, configurable en `.env`).
- Los 3 CSV de origen ya están copiados en `data/` (`productos.csv`,
  `clientes.csv`, `ventas.csv`), tomados de `SEMANA_05/ENTREGABLE_5/`.

## 2. Arranque

```bash
cd ENTREGA_06
cp .env.example .env
# Editar .env: reemplazar los 3 valores "CAMBIAR_..." con contraseñas propias
# y un SUPERSET_SECRET_KEY generado con: openssl rand -base64 42

docker compose up -d --build
```

Esto, en orden automático (sin intervención manual):

1. Levanta `db` (PostgreSQL) y `redis`, y espera a que ambos estén `healthy`.
2. Corre `superset-init`: migra la base de metadatos, crea el usuario admin,
   inicializa roles y **construye por código** la conexión, el dataset, las 5
   métricas, los 9 gráficos y el dashboard completo (vía la API REST de Superset).
   Termina y sale con código 0.
3. Arrancan `superset` (puerto 8088) y `superset-worker`.

### Verificar que todo quedó arriba

```bash
docker compose ps
# db, redis, superset deben decir "healthy"; superset-init debe aparecer
# como "Exited (0)" — es un contenedor de un solo uso, no un error.
```

```bash
docker compose logs superset-init | tail -20
# Debe terminar con: "[init] superset-init completado con éxito."
```

### Acceder al dashboard

1. Abrir `http://localhost:8088`.
2. Iniciar sesión con `ADMIN_USERNAME` / `ADMIN_PASSWORD` del `.env`.
3. **Cambiar la contraseña** desde el ícono de usuario (esquina superior derecha)
   en el primer acceso.
4. Ir a *Dashboards* → **"Inversiones Palacios — KPIs de Ventas"**. Debe abrir ya
   poblado con las 9 visualizaciones, sin configuración adicional.

## 3. Plan de pruebas

### 3.1 Integridad de carga
En *SQL Lab* de Superset (o `docker exec ip_db psql -U <user> -d <db>`):
```sql
SELECT (SELECT COUNT(*) FROM productos) AS productos,
       (SELECT COUNT(*) FROM clientes)  AS clientes,
       (SELECT COUNT(*) FROM ventas)    AS ventas;
-- Esperado: 5305 | 5942 | 1033036
```

### 3.2 KPIs contra la referencia de la Semana 5
Comparar las 5 tarjetas del dashboard con la tabla de la sección 8 de
`Documento_Solucion_Semana6.md`. Deben coincidir dentro del margen de redondeo
(Ventas Netas £20.317.584, Unidades 10.886.598, Ticket £448,16, % sin cliente
22,8 %, Tasa de cancelación 1,85 %).

### 3.3 Interactividad de filtros
Aplicar el filtro nativo de **país** (p. ej. "United Kingdom") y confirmar que
las 9 visualizaciones se actualizan de forma cruzada.

### 3.4 Calidad de datos
En el gráfico "Top 10 Productos", confirmar que **no** aparecen `POSTAGE`,
`DOTCOM POSTAGE` ni `Manual`, y que el primer lugar es un producto real
(`REGENCY CAKESTAND 3 TIER`, ~£330.590), no la etiqueta "(sin descripción)".

### 3.5 Persistencia (sin perder datos)
```bash
docker compose down       # sin -v: los volúmenes se conservan
docker compose up -d
docker exec ip_db psql -U <user> -d <db> -c "SELECT COUNT(*) FROM ventas;"
# Debe seguir devolviendo 1033036, sin recargar los CSV
```

### 3.6 Reproducibilidad total desde cero
```bash
docker compose down -v         # borra también los volúmenes (datos y metadatos)
docker compose up -d --build
# Repetir las pruebas 3.1 y 3.2: deben dar exactamente los mismos resultados,
# sin ningún paso manual salvo el login inicial.
```

### 3.7 Rendimiento
Con las herramientas de desarrollador del navegador (pestaña Network), medir el
tiempo de cada gráfico al abrir el dashboard: objetivo < 3 s en frío. Recargar la
página: con caché de Redis tibia, debe bajar a < 1 s.

## 4. Verificación por API (alternativa a la UI, usada para probar esta misma
   solución antes de entregarla)

```bash
# Login y token
TOKEN=$(curl -s -X POST http://localhost:8088/api/v1/security/login \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\",\"provider\":\"db\",\"refresh\":true}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# Datos de un gráfico (ejemplo: id=1, KPI Ventas Netas)
curl -s http://localhost:8088/api/v1/chart/1/data/ -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

## 5. Apagar la solución

```bash
docker compose down       # conserva los datos (volúmenes)
docker compose down -v    # borra todo, incluidos los datos, para partir de cero
```

## 6. Estructura del proyecto

```
ENTREGA_06/
├── docker-compose.yml
├── .env.example
├── db/init/            # 00_databases.sql, 01_schema.sql, 02_load.sql, 03_views.sql
├── data/                # productos.csv, clientes.csv, ventas.csv
├── superset/
│   ├── Dockerfile              # apache/superset:4.1.1 + psycopg2-binary
│   ├── superset_config.py
│   └── init/
│       ├── entrypoint.sh
│       └── bootstrap_dashboard.py   # construye el dashboard vía API REST
├── Documento_Solucion_Semana6.md
└── README.md
```
