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
