"""Racing database connections always return named rows."""

from ..build import connect as base_connect


def connect(dsn, **kwargs):
    from psycopg.rows import dict_row

    return base_connect(dsn, row_factory=dict_row, **kwargs)
