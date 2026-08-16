import sqlite3
from types import SimpleNamespace
from urllib.parse import urlsplit

from fastapi.testclient import TestClient


class FakeD1Query:
    def __init__(self, database, sql):
        self.database = database
        self.sql = sql
        self.parameters = ()

    def bind(self, *parameters):
        self.parameters = parameters
        return self

    async def first(self):
        cursor = self.database.connection.execute(self.sql, self.parameters)
        row = cursor.fetchone()
        return dict(row) if row is not None else None

    async def all(self):
        cursor = self.database.connection.execute(self.sql, self.parameters)
        return SimpleNamespace(results=[dict(row) for row in cursor.fetchall()])

    async def run(self):
        cursor = self.database.connection.execute(self.sql, self.parameters)
        self.database.connection.commit()
        return SimpleNamespace(meta=SimpleNamespace(last_row_id=cursor.lastrowid))


class FakeD1:
    def __init__(self, schema):
        self.connection = sqlite3.connect(":memory:", check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(schema)

    def prepare(self, sql):
        return FakeD1Query(self, sql)

    def reset(self):
        self.connection.executescript(
            "DELETE FROM transactions; DELETE FROM categories; DELETE FROM accounts;"
        )
        self.connection.commit()


class InProcessApp:
    def __init__(self, app, database):
        self.app = app
        self.database = database

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        scope["env"] = SimpleNamespace(money_manager=self.database)
        await self.app(scope, receive, send)


class InProcessRequests:
    def __init__(self, client):
        self.client = client

    def _request(self, method, url, **kwargs):
        parsed = urlsplit(url)
        return self.client.request(method, parsed.path, **kwargs)

    def get(self, url, **kwargs):
        return self._request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._request("POST", url, **kwargs)

    def patch(self, url, **kwargs):
        return self._request("PATCH", url, **kwargs)

    def delete(self, url, **kwargs):
        return self._request("DELETE", url, **kwargs)


def create_client(app, schema):
    database = FakeD1(schema)
    return database, TestClient(InProcessApp(app, database))
