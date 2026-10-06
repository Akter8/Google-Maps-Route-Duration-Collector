from datetime import date

import pytest

from dashboard.data import (
    DashboardConfigurationError, READ_OBSERVATIONS_SQL, database_url,
    query_observations,
)


class Cursor:
    def __init__(self): self.executed = None
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def execute(self, sql, params): self.executed = (sql, params)
    def fetchall(self): return [{"route_id": "R1", "direction": "outbound"}]


class Connection:
    def __init__(self): self.cursor_instance = Cursor()
    def cursor(self, **kwargs): return self.cursor_instance


def test_database_url_comes_from_dashboard_streamlit_secrets_only():
    assert database_url({"database": {"url": "postgresql://dashboard_reader:password@example/db"}}).startswith("postgresql://dashboard_reader")


@pytest.mark.parametrize("secrets", ({}, {"database": {}}, {"database": {"url": ""}}))
def test_missing_dashboard_secrets_raise_actionable_error(secrets):
    with pytest.raises(DashboardConfigurationError, match="Streamlit Secrets"):
        database_url(secrets)


def test_dashboard_query_is_parameterized_and_read_only():
    connection = Connection()
    rows = query_observations(connection, date(2026, 9, 1), date(2026, 9, 30))
    sql, params = connection.cursor_instance.executed
    assert rows == [{"route_id": "R1", "direction": "outbound"}]
    assert params == (date(2026, 9, 1), date(2026, 9, 30))
    assert sql == READ_OBSERVATIONS_SQL
    assert sql.strip().upper().startswith("SELECT")
    assert not any(word in sql.upper() for word in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"))
