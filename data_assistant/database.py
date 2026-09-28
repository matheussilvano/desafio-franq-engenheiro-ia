from __future__ import annotations
import sqlite3
from pathlib import Path
from .security import validate_read_only_sql
from .models import QueryResult

class Database:
    def __init__(self, path: str | Path): self.path = Path(path).resolve()
    def connect(self) -> sqlite3.Connection:
        if not self.path.exists(): raise FileNotFoundError(f'Banco não encontrado: {self.path}')
        con = sqlite3.connect(f'{self.path.as_uri()}?mode=ro', uri=True)
        con.row_factory = sqlite3.Row
        return con
    def query(self, sql: str) -> QueryResult:
        validate_read_only_sql(sql)
        try:
            with self.connect() as con:
                cur = con.execute(sql)
                rows = [dict(row) for row in cur.fetchall()]
                return QueryResult(sql, [x[0] for x in cur.description or []], rows)
        except sqlite3.Error as exc:
            return QueryResult(sql, [], [], str(exc))
