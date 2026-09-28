from __future__ import annotations
import re

class UnsafeSQL(ValueError): pass
_BLOCKED = re.compile(r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|DETACH|VACUUM|PRAGMA|REINDEX|ANALYZE)\b', re.I)

def _without_literals(sql: str) -> str:
    return re.sub(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"", "''", sql, flags=re.S)

def validate_read_only_sql(sql: str) -> None:
    clean = _without_literals(sql).strip()
    if not clean: raise UnsafeSQL('SQL vazio.')
    # sqlite execute accepts one statement; make the policy explicit before execution.
    if ';' in clean.rstrip(';'): raise UnsafeSQL('Múltiplas instruções SQL não são permitidas.')
    if not re.match(r'^(SELECT|WITH)\b', clean, re.I): raise UnsafeSQL('Apenas consultas SELECT ou WITH ... SELECT são permitidas.')
    if _BLOCKED.search(clean): raise UnsafeSQL('Comando SQL não permitido em acesso somente leitura.')
