from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Any
from .database import Database
from .llm import Planner
from .models import ExecutionTrace, QueryResult, VisualizationSpec
from .schema import inspect_schema, schema_prompt
from .security import UnsafeSQL
from .temporal import TemporalResolution, resolve_period

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
        temporal = resolve_period(question, schema, self.db)
        trace.temporal_interpretation = temporal.interpretations
        trace.investigation_queries.extend(temporal.queries)
        if temporal.interpretations: trace.steps.append('Período resolvido com dados disponíveis')
        trace.steps.append('Plano e SQL gerados pelo agente')
        plan=self.planner.plan(question, context, temporal.context); trace.plan=plan.summary
        results=[]
        for initial_sql in plan.sql:
            sql=initial_sql
            for attempt in range(self.max_retries + 1):
                trace.sql_queries.append(sql)
                try: result=self.db.query(sql)
                except UnsafeSQL as exc: result=QueryResult(sql, [], [], str(exc))
                if not result.error:
                    semantic_issue = self._semantic_issue(result, sql, temporal)
                    if semantic_issue and attempt < self.max_retries:
                        trace.errors.append(semantic_issue)
                        trace.retries += 1
                        trace.steps.append(f'Consulta investigada/corrigida: {semantic_issue}')
                        sql = self.planner.repair(question, f'{context}\nRESOLUÇÃO TEMPORAL:\n{temporal.context}', sql, semantic_issue)
                        continue
                    results.append(result); trace.query_results_summary.append(f'{len(result.rows)} linha(s) retornada(s).'); break
                trace.errors.append(result.error)
                if attempt >= self.max_retries:
                    results.append(result); break
                trace.retries += 1; trace.steps.append(f'SQL corrigido após erro: {result.error}')
                sql=self.planner.repair(question, f'{context}\nRESOLUÇÃO TEMPORAL:\n{temporal.context}', sql, result.error)
        good=[r for r in results if not r.error]
        trace.tables_used = self._tables_used(trace.sql_queries, schema)
        viz=self.choose_visualization(good[-1] if good else None)
        trace.visualization=viz; trace.final_answer=self.answer_from_results(plan.summary, good, results)
        trace.elapsed_ms=round((time.perf_counter()-started)*1000)
        return AgentResponse(trace.final_answer, results, viz, trace)

    @staticmethod
    def _tables_used(sql_queries: list[str], schema: dict) -> list[str]:
        combined = '\n'.join(sql_queries).casefold()
        return [table for table in schema if __import__('re').search(rf'\b{__import__("re").escape(table.casefold())}\b', combined)]

    @staticmethod
    def _semantic_issue(result: QueryResult, sql: str, temporal: TemporalResolution) -> str | None:
        """Conservative post-execution check. Legitimate absence is not retried."""
        normalized = sql.casefold()
        # A limited ranking without a secondary order makes tied rows non-repeatable.
        # This is data independent and applies to every ranked query, not an example.
        import re
        if re.search(r'\border\s+by\s+[^,;]+?\s+desc\s+limit\s+\d+', normalized, re.S):
            return 'Validação semântica: ranking com LIMIT não possui critério de desempate determinístico. Ordene também pela dimensão exibida.'
        if result.rows:
            return None
        if temporal.has_requested_month_data is False:
            return None
        # A month-only request has a known compatible YYYY-MM. A different literal,
        # or MAX(date) mixed with a month predicate, is evidence of contradiction.
        if temporal.expected_year_months:
            if any(period in normalized for period in temporal.expected_year_months):
                return None
            if "strftime('%m'" in normalized and ('max(' in normalized or "strftime('%y-%m'" in normalized):
                return 'Validação semântica: resultado vazio com filtro temporal potencialmente contraditório. Use o período resolvido e investigue os valores reais.'
        return None

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
