#!/usr/bin/env python3

from __future__ import annotations

import os
import re
from typing import Any, Iterable


POSTGRES_SCHEME_PATTERN = re.compile(r"^postgres(?:ql)?://", re.IGNORECASE)


def database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def database_backend(url: str | None = None) -> str:
    normalized_url = (url if url is not None else database_url()).strip()
    if POSTGRES_SCHEME_PATTERN.search(normalized_url):
        return "postgres"
    return "sqlite"


def import_psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "DATABASE_URL 指向 PostgreSQL，但缺少 psycopg。请安装：python3 -m pip install 'psycopg[binary]>=3,<4'"
        ) from exc
    return psycopg, dict_row


def translate_sqlite_placeholders(sql: str) -> str:
    result: list[str] = []
    in_single_quote = False
    in_double_quote = False
    index = 0
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        if char == "'" and not in_double_quote:
            result.append(char)
            if in_single_quote and next_char == "'":
                result.append(next_char)
                index += 2
                continue
            in_single_quote = not in_single_quote
            index += 1
            continue
        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            result.append(char)
            index += 1
            continue
        if char == "?" and not in_single_quote and not in_double_quote:
            result.append("%s")
        else:
            result.append(char)
        index += 1
    return "".join(result)


class RuntimeCursor:
    def __init__(self, cursor: Any, backend: str):
        self._cursor = cursor
        self.backend = backend

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self) -> int:
        return int(getattr(self._cursor, "rowcount", -1) or 0)

    def __iter__(self):
        return iter(self._cursor)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        close = getattr(self._cursor, "close", None)
        if close:
            close()
        return False


class RuntimeConnection:
    def __init__(self, connection: Any, backend: str):
        self._connection = connection
        self.backend = backend

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> RuntimeCursor:
        query = translate_sqlite_placeholders(sql) if self.backend == "postgres" else sql
        cursor = self._connection.execute(query, tuple(params or ()))
        return RuntimeCursor(cursor, self.backend)

    def executemany(self, sql: str, seq_of_params: Iterable[Iterable[Any]]) -> None:
        query = translate_sqlite_placeholders(sql) if self.backend == "postgres" else sql
        if self.backend == "postgres":
            with self._connection.cursor() as cursor:
                cursor.executemany(query, [tuple(params) for params in seq_of_params])
            return
        self._connection.executemany(query, seq_of_params)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def transaction(self):
        if self.backend == "postgres":
            return self._connection.transaction()
        return self._connection

    def __enter__(self):
        enter = getattr(self._connection, "__enter__", None)
        if enter:
            enter()
        return self

    def __exit__(self, exc_type, exc, tb):
        exit_method = getattr(self._connection, "__exit__", None)
        suppress = False
        if exit_method:
            suppress = bool(exit_method(exc_type, exc, tb))
        close = getattr(self._connection, "close", None)
        if close:
            close()
        return suppress


def connect_runtime_db(url: str | None = None) -> RuntimeConnection:
    backend = database_backend(url)
    if backend == "postgres":
        psycopg, dict_row = import_psycopg()
        connection = psycopg.connect((url or database_url()).strip(), row_factory=dict_row)
        return RuntimeConnection(connection, "postgres")
    from sqlite_store import connect_db as connect_sqlite_db, ensure_database

    ensure_database()
    return RuntimeConnection(connect_sqlite_db(), "sqlite")


def runtime_database_summary(url: str | None = None) -> dict[str, Any]:
    backend = database_backend(url)
    if backend == "sqlite":
        from sqlite_store import DB_PATH

        return {
            "backend": "sqlite",
            "database": str(DB_PATH),
            "configured": True,
        }
    return {
        "backend": "postgres",
        "database": (url or database_url()).split("@")[-1],
        "configured": bool(url or database_url()),
    }
