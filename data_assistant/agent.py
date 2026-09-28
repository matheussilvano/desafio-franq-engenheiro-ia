from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Any
from .database import Database
from .llm import Planner
from .models import ExecutionTrace, QueryResult, VisualizationSpec
from .schema import inspect_schema, schema_prompt
from .security import UnsafeSQL

@dataclass
class AgentResponse:
    answer: str
    results: list[QueryResult]
    visualization: VisualizationSpec
    trace: ExecutionTrace

class DataAgent:
    """Explicit graph-like orchestration: inspect → plan → validate/execute → repair → present."""
    def __init__(self, db: Database, planner: Planner, max_retries: int = 2):
        self.db, self.planner, self.max_retries = db, planner, max_retries

    def ask(self, question: str) -> AgentResponse:
        started=time.perf_counter(); trace=ExecutionTrace(question)
        trace.steps.append('Schema inspecionado dinamicamente')
        schema=inspect_schema(self.db); trace.schema_used=schema; context=schema_prompt(schema)
        trace.steps.append('Plano e SQL gerados pelo agente')
        plan=self.planner.plan(question, context); trace.plan=plan.summary
        results=[]
        for initial_sql in plan.sql:
            sql=initial_sql
            for attempt in range(self.max_retries + 1):
                trace.sql_queries.append(sql)
                try: result=self.db.query(sql)
                except UnsafeSQL as exc: result=QueryResult(sql, [], [], str(exc))
                if not result.error:
                    results.append(result); trace.query_results_summary.append(f'{len(result.rows)} linha(s) retornada(s).'); break
                trace.errors.append(result.error)
                if attempt >= self.max_retries:
                    results.append(result); break
                trace.retries += 1; trace.steps.append(f'SQL corrigido após erro: {result.error}')
                sql=self.planner.repair(question, context, sql, result.error)
        good=[r for r in results if not r.error]
        viz=self.choose_visualization(good[-1] if good else None)
        trace.visualization=viz; trace.final_answer=self.answer_from_results(plan.summary, good, results)
        trace.elapsed_ms=round((time.perf_counter()-started)*1000)
        return AgentResponse(trace.final_answer, results, viz, trace)

    @staticmethod
    def choose_visualization(result: QueryResult | None) -> VisualizationSpec:
        if not result or not result.columns: return VisualizationSpec('none', title='Sem dados')
        cols=result.columns; numeric=[c for c in cols if result.rows and isinstance(result.rows[0].get(c), (int,float)) and not isinstance(result.rows[0].get(c), bool)]
        if len(result.rows)==1 and numeric: return VisualizationSpec('metric', y=numeric[-1], title='Resultado')
        if len(result.rows)>1 and numeric:
            x=next((c for c in cols if c not in numeric), None)
            if x: return VisualizationSpec('line' if any(k in x.lower() for k in ('data','mes','mês','ano','period')) else 'bar', x, numeric[-1], 'Resultado')
        return VisualizationSpec('table', title='Resultado detalhado')

    @staticmethod
    def answer_from_results(plan: str, good: list[QueryResult], all_results: list[QueryResult]) -> str:
        if not good:
            err=next((r.error for r in all_results if r.error), 'erro desconhecido')
            return f'Não foi possível concluir a consulta. Detalhe: {err}'
        count=sum(len(r.rows) for r in good)
        if count == 0: return f'{plan} Não encontrei dados para esses critérios.'
        # The UI exposes raw result rows; no LLM gets an opportunity to fabricate values.
        return f'{plan} A consulta retornou {count} linha(s). Veja o resultado abaixo.'
