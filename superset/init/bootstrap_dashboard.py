#!/usr/bin/env python3
"""Construye por código, vía la API REST de Superset, todo lo que en la
Semana 5 se documentó como un plan manual para Power BI: la conexión a la
base analítica, el dataset, las 5 métricas equivalentes a las medidas DAX,
las 9 visualizaciones y el dashboard "Inversiones Palacios".

Se ejecuta una sola vez dentro del contenedor superset-init, contra un
servidor Superset temporal levantado en localhost:8088 (ver entrypoint.sh).
Es idempotente: si un objeto (base, dataset, métrica, gráfico, dashboard)
ya existe, se reutiliza/actualiza en vez de duplicarse, de modo que
"docker compose up" repetido no genere copias.
"""
import json
import os
import sys
import time

import requests

BASE_URL = "http://localhost:8088"

ADMIN_USERNAME = os.environ["ADMIN_USERNAME"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
POSTGRES_USER = os.environ["POSTGRES_USER"]
POSTGRES_PASSWORD = os.environ["POSTGRES_PASSWORD"]
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "db")
POSTGRES_PORT_INTERNAL = os.environ.get("POSTGRES_PORT_INTERNAL", "5432")
ANALYTICS_DB_NAME = os.environ.get("ANALYTICS_DB_NAME", "inversiones_palacios")

DATABASE_NAME = "Inversiones Palacios (PostgreSQL)"
DATASET_TABLE = "v_ventas_enriquecida"
DASHBOARD_TITLE = "Inversiones Palacios — KPIs de Ventas"
DASHBOARD_SLUG = "inversiones-palacios"

METRICS = [
    {
        # Métrica por defecto que Superset auto-genera para todo dataset
        # nuevo (COUNT(*)). Al reemplazar la colección de métricas por
        # completo vía PUT con solo las 5 métricas de negocio, esta se
        # perdía — y varios controles internos de Superset (entre ellos
        # el filtro nativo "Rango de fecha") la dan por hecho, fallando
        # con "Metric 'count' does not exist" si no está. Se restaura
        # aquí explícitamente.
        "metric_name": "count",
        "verbose_name": "COUNT(*)",
        "metric_type": "count",
        "expression": "COUNT(*)",
    },
    {
        "metric_name": "ventas_netas",
        "verbose_name": "Ventas Netas",
        "metric_type": "SUM",
        "expression": "SUM(CASE WHEN es_cancelacion = false THEN monto ELSE 0 END)",
        "d3format": ",.2f",
    },
    {
        "metric_name": "unidades_vendidas",
        "verbose_name": "Unidades Vendidas",
        "metric_type": "SUM",
        "expression": "SUM(CASE WHEN es_cancelacion = false THEN cantidad ELSE 0 END)",
        "d3format": ",.0f",
    },
    {
        "metric_name": "ticket_promedio",
        "verbose_name": "Ticket Promedio",
        "metric_type": None,
        "expression": (
            "SUM(CASE WHEN es_cancelacion = false THEN monto ELSE 0 END) / "
            "NULLIF(COUNT(DISTINCT CASE WHEN es_cancelacion = false THEN num_factura END), 0)"
        ),
        "d3format": ",.2f",
    },
    {
        "metric_name": "pct_sin_cliente",
        "verbose_name": "% Clientes No Identificados",
        "metric_type": None,
        "expression": (
            "100.0 * SUM(CASE WHEN cliente_identificado = false THEN 1 ELSE 0 END) / "
            "NULLIF(COUNT(*), 0)"
        ),
        "d3format": ",.1f",
    },
    {
        "metric_name": "tasa_cancelacion",
        "verbose_name": "Tasa de Cancelación",
        "metric_type": None,
        "expression": (
            "100.0 * SUM(CASE WHEN es_cancelacion = true THEN 1 ELSE 0 END) / "
            "NULLIF(COUNT(*), 0)"
        ),
        "d3format": ",.2f",
    },
]

session = requests.Session()


def log(msg: str) -> None:
    print(f"[bootstrap] {msg}", flush=True)


def wait_for_server(timeout_s: int = 120) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = session.get(f"{BASE_URL}/health", timeout=5)
            if r.status_code == 200:
                log("Servidor temporal de Superset respondiendo.")
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise SystemExit("El servidor de Superset no respondió a tiempo.")


def login() -> None:
    r = session.post(
        f"{BASE_URL}/api/v1/security/login",
        json={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD,
            "provider": "db",
            "refresh": True,
        },
        timeout=15,
    )
    r.raise_for_status()
    token = r.json()["access_token"]
    session.headers.update({"Authorization": f"Bearer {token}"})
    log("Login OK.")


def refresh_csrf() -> None:
    r = session.get(f"{BASE_URL}/api/v1/security/csrf_token/", timeout=15)
    r.raise_for_status()
    csrf = r.json()["result"]
    session.headers.update({"X-CSRFToken": csrf, "Referer": BASE_URL})


def _raise_with_body(r: requests.Response) -> None:
    if not r.ok:
        print(f"[bootstrap] ERROR {r.request.method} {r.request.url} -> {r.status_code}", file=sys.stderr)
        print(r.text[:4000], file=sys.stderr)
        r.raise_for_status()


def api_get(path: str) -> dict:
    r = session.get(f"{BASE_URL}{path}", timeout=30)
    _raise_with_body(r)
    return r.json()


def api_post(path: str, payload: dict) -> dict:
    refresh_csrf()
    r = session.post(f"{BASE_URL}{path}", json=payload, timeout=30)
    _raise_with_body(r)
    return r.json()


def api_put(path: str, payload: dict) -> dict:
    refresh_csrf()
    r = session.put(f"{BASE_URL}{path}", json=payload, timeout=30)
    _raise_with_body(r)
    return r.json()


def find_by_field(list_path: str, field: str, value) -> dict | None:
    data = api_get(f"{list_path}?q=(page_size:200)")
    for item in data.get("result", []):
        if item.get(field) == value:
            return item
    return None


def get_or_create_database() -> int:
    existing = find_by_field("/api/v1/database/", "database_name", DATABASE_NAME)
    if existing:
        log(f"Base '{DATABASE_NAME}' ya existía (id={existing['id']}).")
        return existing["id"]
    uri = (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT_INTERNAL}/{ANALYTICS_DB_NAME}"
    )
    result = api_post(
        "/api/v1/database/",
        {
            "database_name": DATABASE_NAME,
            "sqlalchemy_uri": uri,
            "expose_in_sqllab": True,
            "allow_run_async": True,
            "allow_ctas": False,
            "allow_cvas": False,
            "allow_dml": False,
        },
    )
    db_id = result["id"]
    log(f"Base de datos creada (id={db_id}).")
    return db_id


def get_or_create_dataset(database_id: int) -> int:
    existing = find_by_field("/api/v1/dataset/", "table_name", DATASET_TABLE)
    if existing:
        log(f"Dataset '{DATASET_TABLE}' ya existía (id={existing['id']}).")
        dataset_id = existing["id"]
    else:
        result = api_post(
            "/api/v1/dataset/",
            {
                "database": database_id,
                "schema": "public",
                "table_name": DATASET_TABLE,
            },
        )
        dataset_id = result["id"]
        log(f"Dataset creado (id={dataset_id}).")

    # PUT reemplaza la colección completa de métricas: para que sea
    # idempotente hay que reenviar el "id" de las métricas que ya existen
    # (si no, Superset las interpreta como metric_name duplicados y
    # responde 422 "One or more metrics already exist").
    current = api_get(f"/api/v1/dataset/{dataset_id}")
    existing_by_name = {m["metric_name"]: m["id"] for m in current["result"].get("metrics", [])}
    metrics_payload = []
    for metric in METRICS:
        entry = dict(metric)
        if metric["metric_name"] in existing_by_name:
            entry["id"] = existing_by_name[metric["metric_name"]]
        metrics_payload.append(entry)

    api_put(f"/api/v1/dataset/{dataset_id}", {"metrics": metrics_payload})
    log("Métricas (equivalentes a las medidas DAX de la Semana 5) sincronizadas.")
    return dataset_id


def _simple_filters(adhoc_filters: list) -> list:
    """Convierte adhoc_filters (formato de params/form_data) al formato
    plano {col, op, val} que espera el query_context. Solo cubre filtros
    SIMPLE, que son los únicos usados en este dashboard."""
    out = []
    for f in adhoc_filters:
        if f.get("expressionType") == "SIMPLE":
            out.append({"col": f["subject"], "op": f["operator"], "val": f["comparator"]})
    return out


def build_query_context(dataset_id: int, viz_type: str, params: dict) -> dict:
    """Construye el query_context que el propio frontend de Superset genera
    a partir de "params" al renderizar un gráfico. Se guarda junto con el
    gráfico para que quede reproducible (GET /api/v1/chart/{id}/data/) y
    no dependa de que el navegador lo recalcule. Las 4 formas usadas aquí
    (big_number_total, dist_bar, table, echarts_timeseries_line) se
    verificaron en vivo contra esta misma versión de Superset (4.1.1)
    antes de fijarlas."""
    filters = _simple_filters(params.get("adhoc_filters", []))

    if viz_type == "big_number_total":
        query = {
            "metrics": [params["metric"]],
            "extras": {"having": "", "where": ""},
            "filters": filters,
            "row_limit": 1,
        }
    elif viz_type in ("dist_bar", "table"):
        metrics = params["metrics"]
        query = {
            "metrics": metrics,
            "columns": params.get("groupby", []),
            "extras": {"having": "", "where": ""},
            "filters": filters,
            "orderby": [[metrics[0], False]] if params.get("order_desc") else [],
            "row_limit": params.get("row_limit", 100),
        }
    elif viz_type == "echarts_timeseries_line":
        query = {
            "metrics": params["metrics"],
            "groupby": params.get("groupby", []),
            "granularity": params.get("granularity_sqla", "fecha"),
            "time_range": params.get("time_range", "No filter"),
            "extras": {
                "having": "",
                "where": "",
                "time_grain_sqla": params.get("time_grain_sqla", "P1M"),
            },
            "filters": filters,
            "row_limit": params.get("row_limit", 10000),
            "is_timeseries": True,
        }
    else:
        raise ValueError(f"viz_type sin query_context definido: {viz_type}")

    return {
        "datasource": {"id": dataset_id, "type": "table"},
        "queries": [query],
        "form_data": {"datasource": f"{dataset_id}__table", "viz_type": viz_type, **params},
        "result_format": "json",
        "result_type": "full",
    }


def get_or_create_chart(
    slice_name: str, viz_type: str, params: dict, dataset_id: int, dashboard_id: int
) -> int:
    existing = find_by_field("/api/v1/chart/", "slice_name", slice_name)
    params_full = {"datasource": f"{dataset_id}__table", "viz_type": viz_type, **params}
    payload = {
        "slice_name": slice_name,
        "viz_type": viz_type,
        "datasource_id": dataset_id,
        "datasource_type": "table",
        "params": json.dumps(params_full),
        "query_context": json.dumps(build_query_context(dataset_id, viz_type, params)),
        # Vincula el gráfico al dashboard (la relación se define desde el
        # lado del gráfico, no del dashboard: ver campo "dashboards" en
        # GET /api/v1/chart/{id}).
        "dashboards": [dashboard_id],
    }
    if existing:
        api_put(f"/api/v1/chart/{existing['id']}", payload)
        log(f"Gráfico '{slice_name}' actualizado (id={existing['id']}).")
        return existing["id"]
    result = api_post("/api/v1/chart/", payload)
    chart_id = result["id"]
    log(f"Gráfico '{slice_name}' creado (id={chart_id}).")
    return chart_id


def kpi_params(metric: str) -> dict:
    return {
        "metric": metric,
        "adhoc_filters": [],
        "header_font_size": 0.4,
        "subheader_font_size": 0.15,
        "y_axis_format": "SMART_NUMBER",
        "time_range": "No filter",
    }


def build_charts(dataset_id: int, dashboard_id: int) -> dict:
    ids = {}
    ids["kpi_ventas_netas"] = get_or_create_chart(
        "KPI · Ventas Netas", "big_number_total", kpi_params("ventas_netas"), dataset_id, dashboard_id
    )
    ids["kpi_unidades"] = get_or_create_chart(
        "KPI · Unidades Vendidas", "big_number_total", kpi_params("unidades_vendidas"), dataset_id, dashboard_id
    )
    ids["kpi_ticket"] = get_or_create_chart(
        "KPI · Ticket Promedio", "big_number_total", kpi_params("ticket_promedio"), dataset_id, dashboard_id
    )
    ids["kpi_sin_cliente"] = get_or_create_chart(
        "KPI · % Sin Cliente Identificado", "big_number_total", kpi_params("pct_sin_cliente"), dataset_id, dashboard_id
    )
    ids["kpi_cancelacion"] = get_or_create_chart(
        "KPI · Tasa de Cancelación", "big_number_total", kpi_params("tasa_cancelacion"), dataset_id, dashboard_id
    )
    ids["line_mensual"] = get_or_create_chart(
        "Ventas Netas por Mes",
        "echarts_timeseries_line",
        {
            "granularity_sqla": "fecha",
            "time_grain_sqla": "P1M",
            "time_range": "No filter",
            "metrics": ["ventas_netas"],
            "groupby": [],
            "adhoc_filters": [],
            "row_limit": 10000,
            "x_axis_time_format": "smart_date",
            "y_axis_format": "SMART_NUMBER",
            "rich_tooltip": True,
            "show_legend": True,
        },
        dataset_id,
        dashboard_id,
    )
    ids["bar_categoria"] = get_or_create_chart(
        "Ventas Netas por Categoría",
        "dist_bar",
        {
            "metrics": ["ventas_netas"],
            "groupby": ["categoria"],
            "adhoc_filters": [],
            "row_limit": 25,
            "order_desc": True,
            "y_axis_format": "SMART_NUMBER",
        },
        dataset_id,
        dashboard_id,
    )
    ids["bar_pais"] = get_or_create_chart(
        "Ventas Netas por País",
        "dist_bar",
        {
            "metrics": ["ventas_netas"],
            "groupby": ["pais"],
            "adhoc_filters": [],
            "row_limit": 25,
            "order_desc": True,
            "y_axis_format": "SMART_NUMBER",
        },
        dataset_id,
        dashboard_id,
    )
    ids["tabla_top_productos"] = get_or_create_chart(
        "Top 10 Productos por Ventas Netas",
        "table",
        {
            "query_mode": "aggregate",
            # Se agrupa por codigo_producto + descripcion, no solo por
            # descripcion: 486 productos sin descripción de origen (ver
            # 01_schema.sql) quedarían agregados bajo la misma etiqueta
            # "(sin descripción)" si solo se agrupara por descripcion,
            # distorsionando el top 10 igual que el hallazgo Manual/
            # POSTAGE de la Semana 5. Se detectó en vivo durante las
            # pruebas de este bootstrap.
            "groupby": ["codigo_producto", "descripcion"],
            "metrics": ["ventas_netas"],
            "adhoc_filters": [
                {
                    "clause": "WHERE",
                    "subject": "es_cargo_administrativo",
                    "operator": "==",
                    "comparator": False,
                    "expressionType": "SIMPLE",
                }
            ],
            "row_limit": 10,
            "order_desc": True,
            "show_cell_bars": True,
        },
        dataset_id,
        dashboard_id,
    )
    return ids


def build_position_json(ids: dict) -> dict:
    def chart_node(node_id, chart_id, name, width, height, parents):
        return {
            "type": "CHART",
            "id": node_id,
            "children": [],
            "parents": parents,
            "meta": {
                "chartId": chart_id,
                "width": width,
                "height": height,
                "sliceName": name,
            },
        }

    def row_node(row_id, children, parents):
        return {
            "type": "ROW",
            "id": row_id,
            "children": children,
            "parents": parents,
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        }

    root_parents = ["ROOT_ID", "GRID_ID"]
    position = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {
            "type": "GRID",
            "id": "GRID_ID",
            "children": ["ROW-kpis", "ROW-line", "ROW-bars", "ROW-table"],
            "parents": ["ROOT_ID"],
        },
        "ROW-kpis": row_node(
            "ROW-kpis",
            ["CHART-kpi1", "CHART-kpi2", "CHART-kpi3", "CHART-kpi4", "CHART-kpi5"],
            root_parents,
        ),
        "CHART-kpi1": chart_node("CHART-kpi1", ids["kpi_ventas_netas"], "Ventas Netas", 2, 50, root_parents + ["ROW-kpis"]),
        "CHART-kpi2": chart_node("CHART-kpi2", ids["kpi_unidades"], "Unidades Vendidas", 2, 50, root_parents + ["ROW-kpis"]),
        "CHART-kpi3": chart_node("CHART-kpi3", ids["kpi_ticket"], "Ticket Promedio", 2, 50, root_parents + ["ROW-kpis"]),
        "CHART-kpi4": chart_node("CHART-kpi4", ids["kpi_sin_cliente"], "% Sin Cliente", 3, 50, root_parents + ["ROW-kpis"]),
        "CHART-kpi5": chart_node("CHART-kpi5", ids["kpi_cancelacion"], "Tasa de Cancelación", 3, 50, root_parents + ["ROW-kpis"]),
        "ROW-line": row_node("ROW-line", ["CHART-line"], root_parents),
        "CHART-line": chart_node("CHART-line", ids["line_mensual"], "Ventas Netas por Mes", 12, 55, root_parents + ["ROW-line"]),
        "ROW-bars": row_node("ROW-bars", ["CHART-bar-cat", "CHART-bar-pais"], root_parents),
        "CHART-bar-cat": chart_node("CHART-bar-cat", ids["bar_categoria"], "Ventas Netas por Categoría", 6, 55, root_parents + ["ROW-bars"]),
        "CHART-bar-pais": chart_node("CHART-bar-pais", ids["bar_pais"], "Ventas Netas por País", 6, 55, root_parents + ["ROW-bars"]),
        "ROW-table": row_node("ROW-table", ["CHART-table"], root_parents),
        "CHART-table": chart_node("CHART-table", ids["tabla_top_productos"], "Top 10 Productos por Ventas Netas", 12, 55, root_parents + ["ROW-table"]),
    }
    return position


def build_native_filters() -> list:
    return [
        {
            "id": "NATIVE_FILTER-pais",
            "name": "País",
            "filterType": "filter_select",
            "targets": [{"datasetId": None, "column": {"name": "pais"}}],
            "controlValues": {"enableEmptyFilter": False, "multiSelect": True},
            "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
            "type": "NATIVE_FILTER",
        },
        {
            "id": "NATIVE_FILTER-categoria",
            "name": "Categoría",
            "filterType": "filter_select",
            "targets": [{"datasetId": None, "column": {"name": "categoria"}}],
            "controlValues": {"enableEmptyFilter": False, "multiSelect": True},
            "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
            "type": "NATIVE_FILTER",
        },
        {
            "id": "NATIVE_FILTER-fecha",
            "name": "Rango de fecha",
            "filterType": "filter_time",
            "targets": [{"datasetId": None, "column": {"name": "fecha"}}],
            "controlValues": {},
            "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
            "type": "NATIVE_FILTER",
        },
    ]


def get_or_create_dashboard_shell() -> int:
    """Crea (o recupera) el dashboard vacío. Se hace ANTES que los
    gráficos porque la asociación gráfico-dashboard se define en el lado
    del gráfico (campo "dashboards" en /api/v1/chart/), no al revés."""
    existing = find_by_field("/api/v1/dashboard/", "dashboard_title", DASHBOARD_TITLE)
    if existing:
        log(f"Dashboard '{DASHBOARD_TITLE}' ya existía (id={existing['id']}).")
        return existing["id"]
    result = api_post(
        "/api/v1/dashboard/",
        {"dashboard_title": DASHBOARD_TITLE, "slug": DASHBOARD_SLUG, "published": True},
    )
    dash_id = result["id"]
    log(f"Dashboard '{DASHBOARD_TITLE}' creado (id={dash_id}).")
    return dash_id


def finalize_dashboard(dashboard_id: int, dataset_id: int, chart_ids: dict) -> None:
    """Aplica el layout (position_json) y los filtros nativos, una vez que
    los 9 gráficos ya existen y ya están vinculados al dashboard."""
    position = build_position_json(chart_ids)
    native_filters = build_native_filters()
    for f in native_filters:
        f["targets"][0]["datasetId"] = dataset_id

    json_metadata = json.dumps(
        {"native_filter_configuration": native_filters, "cross_filters_enabled": True}
    )
    api_put(
        f"/api/v1/dashboard/{dashboard_id}",
        {
            "position_json": json.dumps(position),
            "json_metadata": json_metadata,
            "published": True,
        },
    )
    log(f"Layout y filtros nativos del dashboard (id={dashboard_id}) aplicados.")


def main() -> None:
    wait_for_server()
    login()
    database_id = get_or_create_database()
    dataset_id = get_or_create_dataset(database_id)
    dashboard_id = get_or_create_dashboard_shell()
    chart_ids = build_charts(dataset_id, dashboard_id)
    finalize_dashboard(dashboard_id, dataset_id, chart_ids)
    log(f"Bootstrap completado. Dashboard id={dashboard_id}, slug='{DASHBOARD_SLUG}'.")


if __name__ == "__main__":
    main()
