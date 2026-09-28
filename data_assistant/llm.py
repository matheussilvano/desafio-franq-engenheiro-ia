from __future__ import annotations
import json
from typing import Protocol
from .models import QueryPlan

class Planner(Protocol):
    def plan(self, question: str, schema: str) -> QueryPlan: ...
    def repair(self, question: str, schema: str, sql: str, error: str) -> str: ...

class OpenAIPlanner:
    """Thin, centralized OpenAI adapter. JSON is validated before it reaches SQLite."""
    def __init__(self, api_key: str, model: str):
        from openai import OpenAI
        self.client, self.model = OpenAI(api_key=api_key), model

    def _json(self, instructions: str, prompt: str) -> dict:
        response = self.client.responses.create(model=self.model, instructions=instructions,
            input=prompt, text={"format": {"type": "json_object"}}, temperature=0)
        return json.loads(response.output_text)

    def plan(self, question: str, schema: str) -> QueryPlan:
        data = self._json(
            'Você é um planejador SQL SQLite. Retorne APENAS JSON {"summary":str,"sql":[str],"tables":[str]}. '
            'Use exclusivamente SELECT/CTEs, no máximo 3 SQLs. Não invente tabela/coluna. Datas ISO usam strftime. '
            'Para “último ano”, descubra a data máxima nos dados quando necessário.',
            f'SCHEMA REAL:\n{schema}\n\nPERGUNTA:\n{question}\n\nRetorne o objeto em JSON.')
        sql = data.get('sql', [])
        if not isinstance(sql, list) or not all(isinstance(x, str) for x in sql): raise ValueError('Resposta LLM sem lista sql válida.')
        return QueryPlan(str(data.get('summary', 'Consulta aos dados.')), sql, list(data.get('tables', [])))

    def repair(self, question: str, schema: str, sql: str, error: str) -> str:
        data = self._json('Retorne APENAS JSON {"sql":str}. Corrija a consulta SQLite usando o schema. Somente SELECT/CTE.',
            f'Pergunta: {question}\nSchema:\n{schema}\nSQL com erro:\n{sql}\nErro SQLite:\n{error}\n\nRetorne o objeto em JSON.')
        value = data.get('sql')
        if not isinstance(value, str): raise ValueError('Resposta de reparo sem SQL.')
        return value

class FakePlanner:
    """Dublê para testes; não é usado pela aplicação em produção."""
    def __init__(self, sql: list[str], repaired: str | None = None): self.sql, self.repaired = sql, repaired
    def plan(self, question: str, schema: str) -> QueryPlan: return QueryPlan('Plano de teste.', self.sql)
    def repair(self, question: str, schema: str, sql: str, error: str) -> str:
        if self.repaired is None: raise ValueError('Sem reparo configurado')
        return self.repaired
