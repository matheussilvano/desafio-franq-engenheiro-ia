"""Data-driven interpretation of dates used by the planner and result validator."""
from __future__ import annotations

import re
from datetime import date
from dataclasses import dataclass, field
from typing import Any

from .database import Database

MONTHS = {
    'janeiro': '01', 'fevereiro': '02', 'março': '03', 'marco': '03',
    'abril': '04', 'maio': '05', 'junho': '06', 'julho': '07', 'agosto': '08',
    'setembro': '09', 'outubro': '10', 'novembro': '11', 'dezembro': '12',
}

@dataclass
class TemporalResolution:
    context: str = ''
    interpretations: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    has_requested_month_data: bool | None = None
    expected_year_months: list[str] = field(default_factory=list)

def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'

def _month_start(value: str, months_back: int) -> str:
    current = date.fromisoformat(value[:10])
    month_index = current.year * 12 + current.month - 1 - months_back
    return f'{month_index // 12:04d}-{month_index % 12 + 1:02d}-01'

def resolve_period(question: str, schema: dict[str, Any], db: Database) -> TemporalResolution:
    """Profile date columns in the actual database; no calendar year is assumed."""
    normalized = question.casefold()
    requested = next((number for name, number in MONTHS.items() if re.search(rf'\b{name}\b', normalized)), None)
    needs_recent = any(term in normalized for term in ('último mês', 'ultimo mês', 'último ano', 'ultimo ano', 'ano mais recente', 'período mais recente', 'periodo mais recente', 'últimos 6 meses', 'ultimos 6 meses'))
    if not requested and not needs_recent:
        return TemporalResolution()
    profiles: list[tuple[str, str, dict[str, Any]]] = []
    resolution = TemporalResolution()
    for table, definition in schema.items():
        for column in definition['columns']:
            name = column['name']
            if 'data' not in name.casefold() and 'date' not in name.casefold():
                continue
            table_q, column_q = _quote(table), _quote(name)
            sql = f"SELECT MIN({column_q}) AS min_data, MAX({column_q}) AS max_data FROM {table_q}"
            result = db.query(sql)
            resolution.queries.append(sql)
            if result.rows and result.rows[0]['max_data']:
                profiles.append((table, name, result.rows[0]))
    if requested:
        matching: list[tuple[str, str, str]] = []
        for table, column, _ in profiles:
            table_q, column_q = _quote(table), _quote(column)
            sql = f"SELECT MAX({column_q}) AS max_data FROM {table_q} WHERE strftime('%m', {column_q}) = '{requested}'"
            result = db.query(sql)
            resolution.queries.append(sql)
            if result.rows and result.rows[0]['max_data']:
                date = result.rows[0]['max_data']
                matching.append((table, column, date))
                resolution.expected_year_months.append(date[:7])
        resolution.has_requested_month_data = bool(matching)
        if matching:
            details = '; '.join(f'{table}.{column}: {date[:7]}' for table, column, date in matching)
            resolution.interpretations.append(f"{next(name for name, number in MONTHS.items() if number == requested)} foi interpretado no período mais recente disponível para esse mês ({details}).")
        else:
            resolution.interpretations.append(f"Não há registros em {next(name for name, number in MONTHS.items() if number == requested)} nas colunas temporais disponíveis.")
    if needs_recent:
        if 'últimos 6 meses' in normalized or 'ultimos 6 meses' in normalized:
            months_back, label = 5, 'últimos 6 meses'
        elif 'último ano' in normalized or 'ultimo ano' in normalized:
            months_back, label = 11, 'últimos 12 meses'
        elif 'último mês' in normalized or 'ultimo mês' in normalized:
            months_back, label = 0, 'mês mais recente disponível'
        else:
            months_back, label = 0, 'período mais recente disponível'
        windows = []
        for table, column, values in profiles:
            maximum = values['max_data']
            start = _month_start(maximum, months_back)
            windows.append(f'{table}.{column}: {start} a {maximum}')
        if windows:
            resolution.interpretations.append(f'{label.capitalize()} ancorado(s) na maior data disponível de cada fonte: ' + '; '.join(windows) + '.')
    resolution.context = '\n'.join(resolution.interpretations)
    return resolution
