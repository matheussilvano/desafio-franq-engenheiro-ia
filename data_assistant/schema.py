from __future__ import annotations
from .database import Database

def inspect_schema(db: Database, sample_rows: int = 2) -> dict:
    schema: dict = {}
    with db.connect() as con:
        names = [r['name'] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for table in names:
            quoted = '"' + table.replace('"', '""') + '"'
            columns = [dict(r) for r in con.execute(f'PRAGMA table_info({quoted})')]
            # Small, named categorical dimensions are safe and useful context for
            # semantic filters. This avoids guessing business values from samples.
            domain_values = {}
            for column in columns:
                column_name = column['name']
                if column['type'].upper() != 'TEXT' or not any(word in column_name.casefold() for word in ('canal', 'tipo', 'categoria', 'estado', 'status', 'genero')):
                    continue
                col_q = '"' + column_name.replace('"', '""') + '"'
                values = [row[0] for row in con.execute(f'SELECT DISTINCT {col_q} FROM {quoted} WHERE {col_q} IS NOT NULL ORDER BY 1 LIMIT 30')]
                domain_values[column_name] = values
            schema[table] = {
                'columns': columns,
                'foreign_keys': [dict(r) for r in con.execute(f'PRAGMA foreign_key_list({quoted})')],
                'sample': [dict(r) for r in con.execute(f'SELECT * FROM {quoted} LIMIT ?', (sample_rows,))],
                'domain_values': domain_values,
            }
    return schema

def schema_prompt(schema: dict, limit: int = 7000) -> str:
    lines=[]
    for name, item in schema.items():
        cols=', '.join(f"{c['name']} ({c['type']})" for c in item['columns'])
        fks=', '.join(f"{x['from']}->{x['table']}.{x['to']}" for x in item['foreign_keys']) or 'none'
        lines.append(f'TABLE {name}: {cols}. FKs: {fks}. Valores categóricos reais: {item.get("domain_values", {})}. Samples: {item["sample"]}')
    return '\n'.join(lines)[:limit]
