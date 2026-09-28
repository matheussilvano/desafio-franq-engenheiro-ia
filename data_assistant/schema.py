from __future__ import annotations
from .database import Database

def inspect_schema(db: Database, sample_rows: int = 2) -> dict:
    schema: dict = {}
    with db.connect() as con:
        names = [r['name'] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for table in names:
            quoted = '"' + table.replace('"', '""') + '"'
            schema[table] = {
                'columns': [dict(r) for r in con.execute(f'PRAGMA table_info({quoted})')],
                'foreign_keys': [dict(r) for r in con.execute(f'PRAGMA foreign_key_list({quoted})')],
                'sample': [dict(r) for r in con.execute(f'SELECT * FROM {quoted} LIMIT ?', (sample_rows,))],
            }
    return schema

def schema_prompt(schema: dict, limit: int = 7000) -> str:
    lines=[]
    for name, item in schema.items():
        cols=', '.join(f"{c['name']} ({c['type']})" for c in item['columns'])
        fks=', '.join(f"{x['from']}->{x['table']}.{x['to']}" for x in item['foreign_keys']) or 'none'
        lines.append(f'TABLE {name}: {cols}. FKs: {fks}. Samples: {item["sample"]}')
    return '\n'.join(lines)[:limit]
