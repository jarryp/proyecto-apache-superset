"""Configuración de Apache Superset para el caso Inversiones Palacios.

Se monta como /app/pythonpath/superset_config.py en todos los
contenedores basados en la imagen de Superset (superset-init, superset,
superset-worker), tal como exige el PYTHONPATH por defecto de la imagen.
Todos los valores sensibles llegan por variable de entorno (.env); nada
queda hardcodeado en este archivo.
"""
import os

from flask_caching.backends.rediscache import RedisCache  # noqa: F401  (registra el backend)


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Variable de entorno requerida no definida: {name}")
    return value


# --- Metadatos de Superset: base PostgreSQL separada de la analítica ---
DB_USER = _env("POSTGRES_USER")
DB_PASSWORD = _env("POSTGRES_PASSWORD")
DB_HOST = os.getenv("POSTGRES_HOST", "db")
DB_PORT = os.getenv("POSTGRES_PORT_INTERNAL", "5432")
SUPERSET_META_DB = _env("SUPERSET_META_DB")

SQLALCHEMY_DATABASE_URI = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{SUPERSET_META_DB}"
)

SECRET_KEY = _env("SUPERSET_SECRET_KEY")

# --- Redis: cache de resultados de gráficos + broker de Celery ---
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = os.getenv("REDIS_PORT_INTERNAL", "6379")

CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
    "CACHE_KEY_PREFIX": "superset_cache_",
    "CACHE_REDIS_HOST": REDIS_HOST,
    "CACHE_REDIS_PORT": REDIS_PORT,
    "CACHE_REDIS_DB": 1,
}
DATA_CACHE_CONFIG = CACHE_CONFIG
FILTER_STATE_CACHE_CONFIG = CACHE_CONFIG
EXPLORE_FORM_DATA_CACHE_CONFIG = CACHE_CONFIG


class CeleryConfig:
    broker_url = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
    result_backend = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
    imports = ("superset.sql_lab",)
    worker_prefetch_multiplier = 1
    task_acks_late = False
    task_annotations = {
        "sql_lab.get_sql_results": {"rate_limit": "100/s"},
    }


CELERY_CONFIG = CeleryConfig

# --- Rendimiento: objetivo < 3 s en frío / < 1 s con caché tibia sobre
#     la tabla de hechos de 1,03M filas (ver sección 4.4 del prompt maestro) ---
SQLLAB_CTAS_NO_LIMIT = True
SUPERSET_WEBSERVER_TIMEOUT = 300
SQLLAB_TIMEOUT = 120
SQL_MAX_ROW = 100000

FEATURE_FLAGS = {
    "DASHBOARD_NATIVE_FILTERS": True,
    "DASHBOARD_CROSS_FILTERS": True,
    "DASHBOARD_RBAC": False,
    "ENABLE_TEMPLATE_PROCESSING": True,
}

# CSRF sigue activo (comportamiento por defecto de Superset); el bootstrap
# vía API obtiene su token de /api/v1/security/csrf_token/ en cada corrida.
WTF_CSRF_ENABLED = True
