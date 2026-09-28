from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Literal

@dataclass
class QueryPlan:
    summary: str
    sql: list[str]
    tables: list[str] = field(default_factory=list)

@dataclass
class QueryResult:
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    error: str | None = None

@dataclass
class VisualizationSpec:
    type: Literal['none', 'metric', 'table', 'bar', 'line'] = 'table'
    x: str | None = None
    y: str | None = None
    title: str = ''
    orientation: Literal['v', 'h'] = 'v'

    def validate(self, columns: list[str]) -> bool:
        allowed = {'none', 'metric', 'table', 'bar', 'line'}
        if self.type not in allowed: return False
        if self.type in {'bar', 'line'}: return bool(self.x in columns and self.y in columns and self.x != self.y)
        if self.type == 'metric': return bool(self.y in columns)
        return True

@dataclass
class ExecutionTrace:
    question: str
    schema_used: dict[str, Any] = field(default_factory=dict)
    tables_used: list[str] = field(default_factory=list)
    temporal_interpretation: list[str] = field(default_factory=list)
    investigation_queries: list[str] = field(default_factory=list)
    plan: str = ''
    steps: list[str] = field(default_factory=list)
    sql_queries: list[str] = field(default_factory=list)
    query_results_summary: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    retries: int = 0
    visualization: VisualizationSpec | None = None
    final_answer: str = ''
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]: return asdict(self)
