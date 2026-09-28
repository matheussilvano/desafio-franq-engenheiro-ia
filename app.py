from __future__ import annotations

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from data_assistant.agent import DataAgent
from data_assistant.config import Settings
from data_assistant.database import Database
from data_assistant.llm import OpenAIPlanner

load_dotenv()
st.set_page_config(page_title='Painel de análise', page_icon='◈', layout='wide')
st.markdown("""
<style>
[data-testid="stHeader"], [data-testid="stToolbar"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }
.block-container { max-width: 1280px; padding-top: 3rem; padding-bottom: 4rem; }
[data-testid="stSidebar"] { background: #f7f8fa; border-right: 1px solid #e4e7ec; }
[data-testid="stSidebar"] .stButton button { background:#fff; border:1px solid #d0d5dd; color:#344054; text-align:left; min-height:48px; border-radius:6px; font-size:.88rem; }
[data-testid="stSidebar"] .stButton button:hover { border-color:#175cd3; color:#175cd3; }
.product-kicker { color:#175cd3; font-size:.78rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; margin-bottom:.45rem; }
.product-title { color:#101828; font-size:2.15rem; font-weight:650; letter-spacing:-.045em; margin:0; }
.product-description { color:#667085; font-size:1rem; margin:.55rem 0 2rem; }
.section-label { color:#344054; font-weight:650; font-size:1rem; margin:0 0 .55rem; }
.result-header { border-top:1px solid #eaecf0; margin-top:2rem; padding-top:1.5rem; color:#101828; font-size:1.15rem; font-weight:650; }
div[data-testid="stExpander"] { border:1px solid #eaecf0; border-radius:8px; box-shadow:none; }
div[data-testid="stForm"] { border:1px solid #d0d5dd; background:#fff; border-radius:8px; padding:1rem 1rem .35rem; }
.stButton button[kind="primary"] { background:#175cd3; border-color:#175cd3; border-radius:6px; font-weight:600; }
.stDataFrame { border:1px solid #eaecf0; border-radius:8px; overflow:hidden; }
</style>
""", unsafe_allow_html=True)
st.markdown('<div class="product-kicker">Inteligência comercial</div><h1 class="product-title">Painel de análise de dados</h1><p class="product-description">Consulte a base operacional e visualize resultados auditáveis em tempo real.</p>', unsafe_allow_html=True)

examples = [
    'Liste os 5 estados com maior número de clientes que compraram via app em maio.',
    'Quantos clientes interagiram com campanhas de WhatsApp em 2024?',
    'Quais categorias de produto tiveram o maior número de compras em média por cliente?',
    'Qual o número de reclamações não resolvidas por canal?',
    'Qual a tendência de reclamações por canal no último ano?',
]
with st.sidebar:
    st.markdown('### Consultas frequentes')
    st.caption('Use como ponto de partida')
    for i, query in enumerate(examples):
        if st.button(query, key=f'ex{i}', use_container_width=True):
            st.session_state.question = query

settings = Settings.from_env()
if not settings.openai_api_key:
    st.warning('Configure OPENAI_API_KEY no ambiente/.env para habilitar as consultas.')
with st.form('analysis_form', clear_on_submit=False):
    st.markdown('<div class="section-label">Nova consulta</div>', unsafe_allow_html=True)
    question = st.text_area('Descreva a análise que precisa', key='question', placeholder='Ex.: Qual foi a receita por estado no último ano?', height=92, label_visibility='collapsed')
    submitted = st.form_submit_button('Executar análise', type='primary')

if submitted and question.strip():
    if not settings.openai_api_key:
        st.stop()
    try:
        with st.spinner('Consultando a base de dados...'):
            response = DataAgent(Database(settings.database_path), OpenAIPlanner(settings.openai_api_key, settings.openai_model), settings.max_sql_retries).ask(question)
        st.markdown('<div class="result-header">Resultado da análise</div>', unsafe_allow_html=True)
        st.caption(question)
        st.write(response.answer)
        valid = [item for item in response.results if not item.error]
        if valid:
            result, df, spec = valid[-1], pd.DataFrame(valid[-1].rows), response.visualization
            if spec.type == 'metric':
                st.metric(spec.y or 'Resultado', result.rows[0][spec.y])
            elif spec.type == 'bar':
                st.bar_chart(df, x=spec.x, y=spec.y)
            elif spec.type == 'line':
                st.line_chart(df, x=spec.x, y=spec.y)
            st.dataframe(df, use_container_width=True, hide_index=True)
        with st.expander('Detalhes da consulta e auditoria'):
            st.write('**Estratégia:**', response.trace.plan)
            st.write('**Interpretação temporal:**', ' '.join(response.trace.temporal_interpretation) or 'Não aplicável.')
            st.write('**Tabelas efetivamente consultadas:**', ', '.join(response.trace.tables_used) or 'Não identificadas.')
            st.write(f'**Correções de SQL:** {response.trace.retries} · **Tempo de execução:** {response.trace.elapsed_ms} ms')
            if response.trace.investigation_queries:
                st.write('**Queries de investigação:**')
                for sql in response.trace.investigation_queries:
                    st.code(sql, language='sql')
            st.write('**Queries finais/executadas:**')
            for sql in response.trace.sql_queries:
                st.code(sql, language='sql')
            if response.trace.errors:
                st.warning('\n'.join(response.trace.errors))
    except Exception as exc:
        st.error(f'Não foi possível processar a consulta: {exc}')
