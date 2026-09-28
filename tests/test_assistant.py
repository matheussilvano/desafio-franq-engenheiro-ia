import shutil, sqlite3
from pathlib import Path
import pytest
from data_assistant.database import Database
from data_assistant.schema import inspect_schema
from data_assistant.security import UnsafeSQL, validate_read_only_sql
from data_assistant.llm import FakePlanner
from data_assistant.agent import DataAgent
from data_assistant.models import VisualizationSpec

SOURCE = Path(__file__).parents[1] / 'anexo_desafio_1.db'
@pytest.fixture
def db(tmp_path):
    target=tmp_path/'challenge.db'; shutil.copy(SOURCE, target); return Database(target)

def test_dynamic_schema_introspection(db):
    schema=inspect_schema(db)
    assert {'clientes','compras','suporte','campanhas_marketing'} <= schema.keys()
    assert any(c['name']=='valor_total_gasto' for c in schema['clientes']['columns'])
    assert 'Reclamação' in schema['suporte']['domain_values']['tipo_contato']

def test_read_only_connection_and_select(db):
    assert db.query('SELECT COUNT(*) AS total FROM clientes').rows[0]['total'] == 100
    with pytest.raises(sqlite3.OperationalError):
        with db.connect() as con: con.execute("INSERT INTO clientes(nome) VALUES ('x')")

@pytest.mark.parametrize('sql', ['DELETE FROM clientes', 'DROP TABLE clientes', 'SELECT 1; SELECT 2', 'PRAGMA journal_mode=WAL'])
def test_destructive_sql_is_blocked(sql):
    with pytest.raises(UnsafeSQL): validate_read_only_sql(sql)

def test_sqlite_error_is_returned(db):
    result=db.query('SELECT does_not_exist FROM clientes')
    assert result.error and 'no such column' in result.error

def test_repair_is_limited_and_works(db):
    agent=DataAgent(db, FakePlanner(['SELECT broken FROM clientes'], 'SELECT COUNT(*) AS total FROM clientes'), 1)
    response=agent.ask('quantos?')
    assert response.trace.retries == 1 and response.results[-1].rows[0]['total']==100

def test_visualization_spec_validation():
    assert VisualizationSpec('bar','estado','total').validate(['estado','total'])
    assert not VisualizationSpec('bar','missing','total').validate(['estado','total'])

def test_join_question_with_fake_llm(db):
    sql="SELECT c.estado, COUNT(*) AS total FROM compras p JOIN clientes c ON c.id=p.cliente_id GROUP BY c.estado"
    assert DataAgent(db, FakePlanner([sql])).ask('compras por estado').results[0].rows

def test_aggregation_and_dates(db):
    sql="SELECT strftime('%Y-%m', data_compra) AS mes, COUNT(*) AS total FROM compras GROUP BY mes ORDER BY mes"
    response=DataAgent(db, FakePlanner([sql])).ask('tendência mensal')
    assert len(response.results[0].rows) > 1 and response.visualization.type == 'line'

def test_month_without_year_uses_latest_available_month(db):
    """Regression: never intersect global max (July) with requested May."""
    sql = """SELECT c.estado, COUNT(DISTINCT c.id) AS num_clientes
    FROM clientes c JOIN compras co ON c.id = co.cliente_id
    WHERE co.canal = 'App' AND strftime('%Y-%m', co.data_compra) = '2025-05'
    GROUP BY c.estado ORDER BY num_clientes DESC, c.estado LIMIT 5"""
    response = DataAgent(db, FakePlanner([sql])).ask('Liste os 5 estados com maior número de clientes que compraram via app em maio.')
    assert [(row['estado'], row['num_clientes']) for row in response.results[0].rows] == [
        ('São Paulo', 6), ('Minas Gerais', 3), ('Santa Catarina', 3), ('Alagoas', 2), ('Espírito Santo', 2)]
    assert any('2025-05' in item for item in response.trace.temporal_interpretation)
    assert response.trace.tables_used == ['clientes', 'compras']

def test_contradictory_temporal_empty_result_is_repaired(db):
    wrong = """SELECT c.estado FROM clientes c JOIN compras co ON c.id=co.cliente_id
    WHERE co.canal='App' AND strftime('%Y-%m', co.data_compra) =
    (SELECT strftime('%Y-%m', MAX(data_compra)) FROM compras) AND strftime('%m', co.data_compra)='05'"""
    corrected = "SELECT DISTINCT c.estado FROM clientes c JOIN compras co ON c.id=co.cliente_id WHERE co.canal='App' AND strftime('%Y-%m', co.data_compra)='2025-05'"
    response = DataAgent(db, FakePlanner([wrong], corrected), 1).ask('compras via app em maio')
    assert response.trace.retries == 1 and len(response.results[-1].rows) > 0

def test_limited_ranking_without_tie_breaker_is_repaired(db):
    wrong = "SELECT estado, COUNT(*) AS total FROM clientes GROUP BY estado ORDER BY total DESC LIMIT 5"
    corrected = "SELECT estado, COUNT(*) AS total FROM clientes GROUP BY estado ORDER BY total DESC, estado ASC LIMIT 5"
    response = DataAgent(db, FakePlanner([wrong], corrected), 1).ask('liste os 5 estados')
    assert response.trace.retries == 1

def test_nonexistent_month_is_a_legitimate_empty_result(db):
    response = DataAgent(db, FakePlanner(["SELECT * FROM compras WHERE strftime('%m', data_compra)='02' AND 1=0"]), 1).ask('compras em fevereiro')
    assert response.results[0].rows == [] and response.trace.retries == 0

def test_recent_period_expressions_are_profiled(db):
    schema = inspect_schema(db)
    from data_assistant.temporal import resolve_period
    assert resolve_period('tendência no último ano', schema, db).interpretations
    assert resolve_period('resultado do último mês', schema, db).queries

def test_latest_year_and_six_months_are_resolved_from_data(db):
    schema = inspect_schema(db)
    from data_assistant.temporal import resolve_period
    annual = resolve_period('dados do ano mais recente', schema, db)
    six_months = resolve_period('dados dos últimos 6 meses', schema, db)
    assert 'maior data disponível' in annual.interpretations[0]
    assert 'maior data disponível' in six_months.interpretations[0]
